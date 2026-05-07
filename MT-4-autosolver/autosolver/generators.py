"""Synthetic case generator for development before official data arrives."""

from __future__ import annotations

import random
from collections.abc import Callable

from autosolver.model import BundleDiscount, Edge, Instance, Order, Rider


def tiny_manual() -> Instance:
    return Instance(
        name="tiny_manual",
        orders=(Order("o1"), Order("o2")),
        riders=(Rider("r1", max_orders=1), Rider("r2", max_orders=1)),
        max_riders_per_order=1,
        edges=(
            Edge("o1", "r1", cost=1.0, accept_prob=0.90),
            Edge("o1", "r2", cost=8.0, accept_prob=0.40),
            Edge("o2", "r1", cost=7.0, accept_prob=0.30),
            Edge("o2", "r2", cost=1.0, accept_prob=0.90),
        ),
        metadata={"expected_best": {"expected_accepted": 1.8, "total_cost": 2.0}},
    )


def single_best_rider() -> Instance:
    orders = tuple(Order(f"o{i}") for i in range(1, 7))
    riders = tuple(Rider(f"r{i}", max_orders=3) for i in range(1, 4))
    edges: list[Edge] = []
    for index, order in enumerate(orders):
        best = riders[index % len(riders)]
        for rider in riders:
            is_best = rider.id == best.id
            edges.append(
                Edge(
                    order.id,
                    rider.id,
                    cost=1.0 if is_best else 5.0 + index,
                    accept_prob=0.92 if is_best else 0.45,
                )
            )
    return Instance(
        name="single_best_rider",
        orders=orders,
        riders=riders,
        edges=tuple(edges),
        max_riders_per_order=1,
    )


def bundle_wins() -> Instance:
    orders = tuple(Order(f"o{i}") for i in range(1, 4))
    riders = (Rider("solo", max_orders=3), Rider("bundle", max_orders=3))
    edges = tuple(
        [
            Edge("o1", "solo", cost=2.0, accept_prob=0.90),
            Edge("o2", "solo", cost=2.0, accept_prob=0.90),
            Edge("o3", "solo", cost=2.0, accept_prob=0.90),
            Edge("o1", "bundle", cost=3.2, accept_prob=0.90),
            Edge("o2", "bundle", cost=3.2, accept_prob=0.90),
            Edge("o3", "bundle", cost=3.2, accept_prob=0.90),
        ]
    )
    return Instance(
        name="bundle_wins",
        orders=orders,
        riders=riders,
        edges=edges,
        max_riders_per_order=1,
        bundle_discounts=(BundleDiscount("bundle", ("o1", "o2", "o3"), discount=5.0),),
    )


def multi_offer_probability() -> Instance:
    return Instance(
        name="multi_offer_probability",
        orders=(Order("o1"), Order("o2")),
        riders=(Rider("r1", 2), Rider("r2", 2), Rider("r3", 2)),
        max_riders_per_order=3,
        edges=(
            Edge("o1", "r1", 1.0, 0.40),
            Edge("o1", "r2", 1.2, 0.35),
            Edge("o1", "r3", 1.1, 0.30),
            Edge("o2", "r1", 1.0, 0.20),
            Edge("o2", "r2", 1.1, 0.25),
            Edge("o2", "r3", 1.0, 0.80),
        ),
    )


def rider_shortage() -> Instance:
    orders = tuple(Order(f"o{i}") for i in range(1, 9))
    riders = (Rider("r1", max_orders=2), Rider("r2", max_orders=2))
    edges = tuple(
        Edge(order.id, rider.id, cost=1.0 + (index % 4), accept_prob=0.55 + 0.04 * (index % 5))
        for index, order in enumerate(orders)
        for rider in riders
    )
    return Instance(
        name="rider_shortage",
        orders=orders,
        riders=riders,
        edges=edges,
        max_riders_per_order=1,
    )


def dense_conflict() -> Instance:
    orders = tuple(Order(f"o{i}") for i in range(1, 25))
    riders = tuple(Rider(f"r{i}", max_orders=6) for i in range(1, 6))
    edges: list[Edge] = []
    for order_index, order in enumerate(orders):
        for rider_index, rider in enumerate(riders):
            preferred = rider_index == 0
            edges.append(
                Edge(
                    order.id,
                    rider.id,
                    cost=1.0 + rider_index * 1.7 + (order_index % 3) * 0.2,
                    accept_prob=0.88 if preferred else 0.62 - rider_index * 0.03,
                )
            )
    return Instance(
        name="dense_conflict",
        orders=orders,
        riders=riders,
        edges=tuple(edges),
        max_riders_per_order=1,
    )


def large_random(seed: int = 42, order_count: int = 220, rider_count: int = 45) -> Instance:
    rng = random.Random(seed)
    orders = tuple(Order(f"o{i}") for i in range(1, order_count + 1))
    riders = tuple(Rider(f"r{i}", max_orders=rng.randint(5, 9)) for i in range(1, rider_count + 1))
    edges: list[Edge] = []
    for order in orders:
        candidate_count = rng.randint(4, min(12, rider_count))
        for rider in rng.sample(riders, candidate_count):
            edges.append(
                Edge(
                    order.id,
                    rider.id,
                    cost=round(rng.uniform(1.0, 18.0), 3),
                    accept_prob=round(rng.uniform(0.08, 0.92), 3),
                )
            )
    return Instance(
        name="large_random",
        orders=orders,
        riders=riders,
        edges=tuple(edges),
        max_riders_per_order=2,
        metadata={"seed": seed},
    )


def random_case(
    name: str = "random",
    seed: int = 0,
    order_count: int = 30,
    rider_count: int = 8,
    density: float = 0.45,
    max_riders_per_order: int = 2,
) -> Instance:
    rng = random.Random(seed)
    orders = tuple(Order(f"o{i}") for i in range(1, order_count + 1))
    riders = tuple(Rider(f"r{i}", max_orders=max(1, order_count // rider_count + 2)) for i in range(1, rider_count + 1))
    edges: list[Edge] = []
    for order in orders:
        order_edges = []
        for rider in riders:
            if rng.random() <= density:
                order_edges.append(
                    Edge(
                        order.id,
                        rider.id,
                        cost=round(rng.uniform(1.0, 12.0), 3),
                        accept_prob=round(rng.uniform(0.10, 0.95), 3),
                    )
                )
        if not order_edges:
            rider = rng.choice(riders)
            order_edges.append(Edge(order.id, rider.id, cost=5.0, accept_prob=0.5))
        edges.extend(order_edges)
    return Instance(
        name=name,
        orders=orders,
        riders=riders,
        edges=tuple(edges),
        max_riders_per_order=max_riders_per_order,
        metadata={"seed": seed, "density": density},
    )


CASE_GENERATORS: dict[str, Callable[[], Instance]] = {
    "tiny_manual": tiny_manual,
    "single_best_rider": single_best_rider,
    "bundle_wins": bundle_wins,
    "multi_offer_probability": multi_offer_probability,
    "rider_shortage": rider_shortage,
    "dense_conflict": dense_conflict,
    "large_random": large_random,
}


def generate_case(name: str) -> Instance:
    try:
        return CASE_GENERATORS[name]()
    except KeyError as exc:
        available = ", ".join(sorted(CASE_GENERATORS))
        raise ValueError(f"unknown case {name!r}; available cases: {available}") from exc
