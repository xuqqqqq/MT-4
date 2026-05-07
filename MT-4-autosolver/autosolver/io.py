"""JSON adapter layer.

The official contest input format is not available yet. This adapter gives us
one stable internal JSON shape for generated cases and experiments.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autosolver.model import Assignment, BundleDiscount, Edge, Instance, Order, Rider


def instance_to_dict(instance: Instance) -> dict[str, Any]:
    return {
        "name": instance.name,
        "max_riders_per_order": instance.max_riders_per_order,
        "orders": [
            {"id": order.id, "demand": order.demand, "priority": order.priority}
            for order in instance.orders
        ],
        "riders": [
            {"id": rider.id, "max_orders": rider.max_orders}
            for rider in instance.riders
        ],
        "edges": [
            {
                "order_id": edge.order_id,
                "rider_id": edge.rider_id,
                "cost": edge.cost,
                "accept_prob": edge.accept_prob,
                "feasible": edge.feasible,
            }
            for edge in instance.edges
        ],
        "bundle_discounts": [
            {
                "rider_id": discount.rider_id,
                "order_ids": list(discount.order_ids),
                "discount": discount.discount,
            }
            for discount in instance.bundle_discounts
        ],
        "metadata": dict(instance.metadata),
    }


def instance_from_dict(data: dict[str, Any]) -> Instance:
    return Instance(
        name=data.get("name", "instance"),
        max_riders_per_order=int(data.get("max_riders_per_order", 3)),
        orders=tuple(Order(**order) for order in data.get("orders", [])),
        riders=tuple(Rider(**rider) for rider in data.get("riders", [])),
        edges=tuple(Edge(**edge) for edge in data.get("edges", [])),
        bundle_discounts=tuple(
            BundleDiscount(
                rider_id=discount["rider_id"],
                order_ids=tuple(discount["order_ids"]),
                discount=float(discount["discount"]),
            )
            for discount in data.get("bundle_discounts", [])
        ),
        metadata=data.get("metadata", {}),
    )


def assignment_to_dict(assignment: Assignment) -> dict[str, Any]:
    return {"offers": {order_id: list(riders) for order_id, riders in assignment.offers.items()}}


def assignment_from_dict(data: dict[str, Any]) -> Assignment:
    return Assignment({order_id: tuple(riders) for order_id, riders in data.get("offers", {}).items()})


def read_instance(path: str | Path) -> Instance:
    with Path(path).open("r", encoding="utf-8") as handle:
        return instance_from_dict(json.load(handle))


def write_instance(instance: Instance, path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(instance_to_dict(instance), handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def write_assignment(assignment: Assignment, path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(assignment_to_dict(assignment), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
