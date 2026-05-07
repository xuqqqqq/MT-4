"""Problem-state extraction for agent-style heuristic selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean, pstdev

from autosolver.evaluator import Evaluator, acceptance_probability
from autosolver.model import Assignment, Instance


@dataclass(frozen=True)
class InstanceFeatures:
    order_count: int
    rider_count: int
    edge_count: int
    edge_density: float
    total_rider_capacity: int
    capacity_ratio: float
    max_riders_per_order: int
    avg_candidates_per_order: float
    avg_accept_prob: float
    accept_prob_std: float
    avg_cost: float
    cost_std: float
    avg_top_accept_prob: float
    avg_top2_accept_prob: float
    bundle_discount_count: int
    bundle_density: float
    graph_skew: float
    scenario_tags: tuple[str, ...]

    def to_dict(self) -> dict[str, float | int | str | tuple[str, ...]]:
        return asdict(self)


@dataclass(frozen=True)
class SolutionFeatures:
    expected_accepted: float
    total_cost: float
    offer_count: int
    assigned_order_count: int
    multi_offer_order_count: int
    avg_offers_per_assigned_order: float
    capacity_used_ratio: float
    feasible: bool

    def to_dict(self) -> dict[str, float | int | bool]:
        return asdict(self)


def extract_instance_features(instance: Instance) -> InstanceFeatures:
    order_count = len(instance.orders)
    rider_count = len(instance.riders)
    edge_count = len(instance.edges)
    total_pairs = max(1, order_count * rider_count)
    edge_density = edge_count / total_pairs
    total_capacity = sum(rider.max_orders for rider in instance.riders)
    capacity_ratio = total_capacity / max(1, order_count)

    candidates_per_order = [len(instance.candidate_edges(order.id)) for order in instance.orders]
    probabilities = [edge.accept_prob for edge in instance.edges if edge.feasible]
    costs = [edge.cost for edge in instance.edges if edge.feasible]
    top_probabilities = []
    top2_probabilities = []
    for order in instance.orders:
        ranked = sorted((edge.accept_prob for edge in instance.candidate_edges(order.id)), reverse=True)
        if ranked:
            top_probabilities.append(ranked[0])
            top2_probabilities.append(acceptance_probability(tuple(ranked[:2])))

    rider_edge_counts: dict[str, int] = {rider.id: 0 for rider in instance.riders}
    for edge in instance.edges:
        rider_edge_counts[edge.rider_id] = rider_edge_counts.get(edge.rider_id, 0) + 1
    graph_skew = (max(rider_edge_counts.values()) / max(1, mean(rider_edge_counts.values()))) if rider_edge_counts else 0.0
    bundle_density = len(instance.bundle_discounts) / max(1, order_count)

    return InstanceFeatures(
        order_count=order_count,
        rider_count=rider_count,
        edge_count=edge_count,
        edge_density=edge_density,
        total_rider_capacity=total_capacity,
        capacity_ratio=capacity_ratio,
        max_riders_per_order=instance.max_riders_per_order,
        avg_candidates_per_order=mean(candidates_per_order) if candidates_per_order else 0.0,
        avg_accept_prob=mean(probabilities) if probabilities else 0.0,
        accept_prob_std=pstdev(probabilities) if len(probabilities) > 1 else 0.0,
        avg_cost=mean(costs) if costs else 0.0,
        cost_std=pstdev(costs) if len(costs) > 1 else 0.0,
        avg_top_accept_prob=mean(top_probabilities) if top_probabilities else 0.0,
        avg_top2_accept_prob=mean(top2_probabilities) if top2_probabilities else 0.0,
        bundle_discount_count=len(instance.bundle_discounts),
        bundle_density=bundle_density,
        graph_skew=graph_skew,
        scenario_tags=tuple(_scenario_tags(edge_density, capacity_ratio, instance.max_riders_per_order, bundle_density, graph_skew)),
    )


def extract_solution_features(
    instance: Instance,
    assignment: Assignment,
    evaluator: Evaluator | None = None,
) -> SolutionFeatures:
    evaluator = evaluator or Evaluator()
    objective = evaluator.evaluate(instance, assignment)
    assigned_order_count = len(assignment.offers)
    multi_offer_count = sum(1 for riders in assignment.offers.values() if len(riders) > 1)
    offer_count = assignment.offer_count()
    total_capacity = sum(rider.max_orders for rider in instance.riders)
    return SolutionFeatures(
        expected_accepted=objective.expected_accepted,
        total_cost=objective.total_cost,
        offer_count=offer_count,
        assigned_order_count=assigned_order_count,
        multi_offer_order_count=multi_offer_count,
        avg_offers_per_assigned_order=offer_count / max(1, assigned_order_count),
        capacity_used_ratio=offer_count / max(1, total_capacity),
        feasible=objective.feasible,
    )


def _scenario_tags(
    edge_density: float,
    capacity_ratio: float,
    max_riders_per_order: int,
    bundle_density: float,
    graph_skew: float,
) -> list[str]:
    tags: list[str] = []
    if max_riders_per_order > 1:
        tags.append("multiposting")
    if bundle_density > 0:
        tags.append("bundles")
    if capacity_ratio < 1.2:
        tags.append("capacity_tight")
    elif capacity_ratio > 2.5:
        tags.append("capacity_loose")
    if edge_density < 0.08:
        tags.append("sparse")
    elif edge_density > 0.30:
        tags.append("dense")
    if graph_skew > 2.0:
        tags.append("rider_skew")
    return tags
