"""Domain model shared by parsers, evaluators, and solvers.

The official contest schema is not available yet, so this module keeps the
core representation intentionally small and adapter-friendly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping


def _as_tuple(values: Iterable[Any]) -> tuple[Any, ...]:
    return tuple(values)


def _unique_stable(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values))


@dataclass(frozen=True)
class Order:
    id: str
    demand: int = 1
    priority: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", str(self.id))
        if self.demand <= 0:
            raise ValueError(f"order {self.id!r} demand must be positive")
        if self.priority <= 0:
            raise ValueError(f"order {self.id!r} priority must be positive")


@dataclass(frozen=True)
class Rider:
    id: str
    max_orders: int = 3

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", str(self.id))
        if self.max_orders < 0:
            raise ValueError(f"rider {self.id!r} max_orders must be non-negative")


@dataclass(frozen=True)
class Edge:
    order_id: str
    rider_id: str
    cost: float
    accept_prob: float
    feasible: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "order_id", str(self.order_id))
        object.__setattr__(self, "rider_id", str(self.rider_id))
        if self.cost < 0:
            raise ValueError("edge cost must be non-negative")
        if not 0 <= self.accept_prob <= 1:
            raise ValueError("edge accept_prob must be in [0, 1]")


@dataclass(frozen=True)
class BundleDiscount:
    rider_id: str
    order_ids: tuple[str, ...]
    discount: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "rider_id", str(self.rider_id))
        object.__setattr__(self, "order_ids", tuple(sorted(_unique_stable(self.order_ids))))
        if len(self.order_ids) < 2:
            raise ValueError("bundle discounts need at least two orders")
        if self.discount < 0:
            raise ValueError("bundle discount must be non-negative")


@dataclass(frozen=True)
class Instance:
    orders: tuple[Order, ...]
    riders: tuple[Rider, ...]
    edges: tuple[Edge, ...]
    name: str = "instance"
    max_riders_per_order: int = 3
    bundle_discounts: tuple[BundleDiscount, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    _orders_by_id: Mapping[str, Order] = field(init=False, repr=False)
    _riders_by_id: Mapping[str, Rider] = field(init=False, repr=False)
    _edges_by_pair: Mapping[tuple[str, str], Edge] = field(init=False, repr=False)
    _edges_by_order: Mapping[str, tuple[Edge, ...]] = field(init=False, repr=False)
    _discounts_by_rider: Mapping[str, tuple[BundleDiscount, ...]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        orders = _as_tuple(self.orders)
        riders = _as_tuple(self.riders)
        edges = _as_tuple(self.edges)
        bundle_discounts = _as_tuple(self.bundle_discounts)
        object.__setattr__(self, "orders", orders)
        object.__setattr__(self, "riders", riders)
        object.__setattr__(self, "edges", edges)
        object.__setattr__(self, "bundle_discounts", bundle_discounts)
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

        if self.max_riders_per_order < 0:
            raise ValueError("max_riders_per_order must be non-negative")

        orders_by_id = {order.id: order for order in orders}
        riders_by_id = {rider.id: rider for rider in riders}
        if len(orders_by_id) != len(orders):
            raise ValueError("duplicate order ids are not allowed")
        if len(riders_by_id) != len(riders):
            raise ValueError("duplicate rider ids are not allowed")

        edges_by_pair: dict[tuple[str, str], Edge] = {}
        edges_by_order: dict[str, list[Edge]] = {order.id: [] for order in orders}
        for edge in edges:
            if edge.order_id not in orders_by_id:
                raise ValueError(f"edge references unknown order {edge.order_id!r}")
            if edge.rider_id not in riders_by_id:
                raise ValueError(f"edge references unknown rider {edge.rider_id!r}")
            pair = (edge.order_id, edge.rider_id)
            if pair in edges_by_pair:
                raise ValueError(f"duplicate edge {pair!r}")
            edges_by_pair[pair] = edge
            edges_by_order[edge.order_id].append(edge)

        discounts_by_rider: dict[str, list[BundleDiscount]] = {rider.id: [] for rider in riders}
        for discount in bundle_discounts:
            if discount.rider_id not in riders_by_id:
                raise ValueError(f"discount references unknown rider {discount.rider_id!r}")
            unknown_orders = [order_id for order_id in discount.order_ids if order_id not in orders_by_id]
            if unknown_orders:
                raise ValueError(f"discount references unknown orders {unknown_orders!r}")
            discounts_by_rider[discount.rider_id].append(discount)

        object.__setattr__(self, "_orders_by_id", MappingProxyType(orders_by_id))
        object.__setattr__(self, "_riders_by_id", MappingProxyType(riders_by_id))
        object.__setattr__(self, "_edges_by_pair", MappingProxyType(edges_by_pair))
        object.__setattr__(
            self,
            "_edges_by_order",
            MappingProxyType({key: tuple(value) for key, value in edges_by_order.items()}),
        )
        object.__setattr__(
            self,
            "_discounts_by_rider",
            MappingProxyType({key: tuple(value) for key, value in discounts_by_rider.items()}),
        )

    @property
    def order_ids(self) -> tuple[str, ...]:
        return tuple(order.id for order in self.orders)

    @property
    def rider_ids(self) -> tuple[str, ...]:
        return tuple(rider.id for rider in self.riders)

    def order(self, order_id: str) -> Order:
        return self._orders_by_id[str(order_id)]

    def rider(self, rider_id: str) -> Rider:
        return self._riders_by_id[str(rider_id)]

    def edge(self, order_id: str, rider_id: str) -> Edge | None:
        return self._edges_by_pair.get((str(order_id), str(rider_id)))

    def candidate_edges(self, order_id: str, only_feasible: bool = True) -> tuple[Edge, ...]:
        edges = self._edges_by_order.get(str(order_id), ())
        if only_feasible:
            return tuple(edge for edge in edges if edge.feasible)
        return edges

    def bundle_discounts_for(self, rider_id: str) -> tuple[BundleDiscount, ...]:
        return self._discounts_by_rider.get(str(rider_id), ())


@dataclass(frozen=True)
class Assignment:
    """A proposed set of offers.

    ``offers`` maps an order id to one or more riders who receive the order.
    An omitted order is interpreted as rejected/unassigned.
    """

    offers: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized: dict[str, tuple[str, ...]] = {}
        for order_id, riders in self.offers.items():
            unique_riders = _unique_stable(riders)
            if unique_riders:
                normalized[str(order_id)] = unique_riders
        object.__setattr__(self, "offers", MappingProxyType(normalized))

    @classmethod
    def empty(cls) -> "Assignment":
        return cls({})

    def riders_for(self, order_id: str) -> tuple[str, ...]:
        return self.offers.get(str(order_id), ())

    def with_offer(self, order_id: str, rider_id: str) -> "Assignment":
        order_key = str(order_id)
        rider_key = str(rider_id)
        offers = {key: list(value) for key, value in self.offers.items()}
        offers.setdefault(order_key, [])
        if rider_key not in offers[order_key]:
            offers[order_key].append(rider_key)
        return Assignment({key: tuple(value) for key, value in offers.items()})

    def without_offer(self, order_id: str, rider_id: str) -> "Assignment":
        order_key = str(order_id)
        rider_key = str(rider_id)
        offers = {key: list(value) for key, value in self.offers.items()}
        if order_key in offers:
            offers[order_key] = [value for value in offers[order_key] if value != rider_key]
            if not offers[order_key]:
                del offers[order_key]
        return Assignment({key: tuple(value) for key, value in offers.items()})

    def offer_count(self) -> int:
        return sum(len(riders) for riders in self.offers.values())

    def rider_loads(self) -> dict[str, int]:
        loads: dict[str, int] = {}
        for riders in self.offers.values():
            for rider_id in riders:
                loads[rider_id] = loads.get(rider_id, 0) + 1
        return loads

    def rider_orders(self) -> dict[str, tuple[str, ...]]:
        grouped: dict[str, list[str]] = {}
        for order_id, riders in self.offers.items():
            for rider_id in riders:
                grouped.setdefault(rider_id, []).append(order_id)
        return {rider_id: tuple(order_ids) for rider_id, order_ids in grouped.items()}
