"""Generated heuristic specifications and safe solver instantiation.

Generated algorithms are represented as bounded JSON specs instead of arbitrary
Python code. This gives the AutoSolver an API-driven algorithm-generation path
without executing untrusted model output.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from autosolver.evaluator import Evaluator
from autosolver.model import Assignment, Edge, Instance
from autosolver.solvers import add_to_state, assignment_from_state, can_add_to_state, expired


@dataclass(frozen=True)
class HeuristicSpec:
    name: str
    description: str = ""
    order_priority: str = "best_probability"
    edge_accept_weight: float = 1.0
    edge_cost_weight: float = 0.0
    edge_value_weight: float = 0.0
    rider_load_penalty: float = 0.0
    order_candidate_penalty: float = 0.0
    multi_offer: bool = False
    max_offers_per_order: int = 1
    min_edge_score: float = -10_000.0

    @classmethod
    def from_dict(cls, data: dict[str, Any], fallback_name: str = "generated") -> "HeuristicSpec":
        return cls(
            name=_safe_name(str(data.get("name") or fallback_name)),
            description=str(data.get("description") or ""),
            order_priority=_choice(str(data.get("order_priority") or "best_probability")),
            edge_accept_weight=_bounded_float(data.get("edge_accept_weight", 1.0), -10.0, 10.0),
            edge_cost_weight=_bounded_float(data.get("edge_cost_weight", 0.0), -10.0, 10.0),
            edge_value_weight=_bounded_float(data.get("edge_value_weight", 0.0), -10.0, 10.0),
            rider_load_penalty=_bounded_float(data.get("rider_load_penalty", 0.0), -10.0, 10.0),
            order_candidate_penalty=_bounded_float(data.get("order_candidate_penalty", 0.0), -10.0, 10.0),
            multi_offer=bool(data.get("multi_offer", False)),
            max_offers_per_order=max(1, min(5, int(data.get("max_offers_per_order", 1)))),
            min_edge_score=_bounded_float(data.get("min_edge_score", -10_000.0), -10_000.0, 10_000.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GeneratedGreedySolver:
    spec: HeuristicSpec

    @property
    def name(self) -> str:
        return f"generated_{self.spec.name}"

    def solve(self, instance: Instance, evaluator: Evaluator, deadline: float | None = None) -> Assignment:
        offers: dict[str, list[str]] = {}
        rider_loads = {rider.id: 0 for rider in instance.riders}
        order_candidates = {order.id: instance.candidate_edges(order.id) for order in instance.orders}
        order_sequence = sorted(
            instance.orders,
            key=lambda order: self._order_key(instance, order.id, order_candidates[order.id]),
        )

        for order in order_sequence:
            if expired(deadline):
                break
            target_offers = 1
            if self.spec.multi_offer:
                target_offers = min(instance.max_riders_per_order, self.spec.max_offers_per_order)
            ranked_edges = sorted(
                order_candidates[order.id],
                key=lambda edge: -self._edge_score(instance, edge, offers, rider_loads, order_candidates),
            )
            eligible_edges = [
                edge
                for edge in ranked_edges
                if self._edge_score(instance, edge, offers, rider_loads, order_candidates) >= self.spec.min_edge_score
            ]
            if not eligible_edges:
                eligible_edges = ranked_edges
            for edge in eligible_edges:
                if expired(deadline) or len(offers.get(order.id, [])) >= target_offers:
                    break
                if can_add_to_state(instance, offers, rider_loads, edge.order_id, edge.rider_id):
                    add_to_state(offers, rider_loads, edge.order_id, edge.rider_id)

        return assignment_from_state(offers)

    def _order_key(self, instance: Instance, order_id: str, candidates: tuple[Edge, ...]) -> tuple[float, str]:
        if not candidates:
            return (float("inf"), order_id)
        best_probability = max(edge.accept_prob for edge in candidates)
        avg_cost = sum(edge.cost for edge in candidates) / len(candidates)
        if self.spec.order_priority == "fewest_candidates":
            return (len(candidates), order_id)
        if self.spec.order_priority == "highest_regret":
            ranked = sorted((edge.accept_prob for edge in candidates), reverse=True)
            regret = ranked[0] - (ranked[1] if len(ranked) > 1 else 0.0)
            return (-regret, order_id)
        if self.spec.order_priority == "lowest_cost":
            return (avg_cost, order_id)
        if self.spec.order_priority == "priority":
            return (-instance.order(order_id).priority, order_id)
        return (-best_probability, order_id)

    def _edge_score(
        self,
        instance: Instance,
        edge: Edge,
        offers: dict[str, list[str]],
        rider_loads: dict[str, int],
        order_candidates: dict[str, tuple[Edge, ...]],
    ) -> float:
        rider = instance.rider(edge.rider_id)
        remaining_ratio = (rider.max_orders - rider_loads.get(edge.rider_id, 0)) / max(1, rider.max_orders)
        candidate_count = len(order_candidates.get(edge.order_id, ()))
        return (
            self.spec.edge_accept_weight * edge.accept_prob
            - self.spec.edge_cost_weight * edge.cost
            + self.spec.edge_value_weight * (edge.accept_prob / max(edge.cost, 0.001))
            + self.spec.rider_load_penalty * remaining_ratio
            - self.spec.order_candidate_penalty * candidate_count
        )


def specs_to_solvers(specs: list[HeuristicSpec] | tuple[HeuristicSpec, ...]) -> list[GeneratedGreedySolver]:
    return [GeneratedGreedySolver(spec) for spec in specs]


def _choice(value: str) -> str:
    allowed = {"best_probability", "fewest_candidates", "highest_regret", "lowest_cost", "priority"}
    return value if value in allowed else "best_probability"


def _bounded_float(value: Any, lower: float, upper: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(numeric):
        return 0.0
    if numeric == float("inf"):
        return upper
    if numeric == float("-inf"):
        return lower
    return min(upper, max(lower, numeric))


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in value.lower())
    cleaned = cleaned.strip("_-")
    return cleaned[:48] or "generated"
