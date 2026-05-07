"""Baseline and improvement solvers for the portfolio runner."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Protocol

from autosolver.evaluator import Evaluator
from autosolver.model import Assignment, Edge, Instance


class Solver(Protocol):
    name: str

    def solve(
        self,
        instance: Instance,
        evaluator: Evaluator,
        deadline: float | None = None,
    ) -> Assignment:
        ...


def expired(deadline: float | None) -> bool:
    return deadline is not None and time.perf_counter() >= deadline


def can_add(instance: Instance, assignment: Assignment, order_id: str, rider_id: str) -> bool:
    if rider_id in assignment.riders_for(order_id):
        return False
    edge = instance.edge(order_id, rider_id)
    if edge is None or not edge.feasible:
        return False
    if len(assignment.riders_for(order_id)) >= instance.max_riders_per_order:
        return False
    current_load = assignment.rider_loads().get(rider_id, 0)
    return current_load < instance.rider(rider_id).max_orders


def edge_preference(edge: Edge) -> tuple[float, float, str]:
    return (-edge.accept_prob, edge.cost, edge.rider_id)


def edge_value(edge: Edge) -> float:
    return edge.accept_prob / max(edge.cost, 0.001)


@dataclass(frozen=True)
class EmptySolver:
    name: str = "empty"

    def solve(self, instance: Instance, evaluator: Evaluator, deadline: float | None = None) -> Assignment:
        return Assignment.empty()


@dataclass(frozen=True)
class OrderGreedySolver:
    name: str = "order_greedy"

    def solve(self, instance: Instance, evaluator: Evaluator, deadline: float | None = None) -> Assignment:
        assignment = Assignment.empty()
        order_priority = sorted(
            instance.orders,
            key=lambda order: (
                -max((edge.accept_prob for edge in instance.candidate_edges(order.id)), default=0.0),
                order.id,
            ),
        )
        for order in order_priority:
            if expired(deadline):
                break
            candidates = sorted(instance.candidate_edges(order.id), key=edge_preference)
            for edge in candidates:
                if can_add(instance, assignment, order.id, edge.rider_id):
                    assignment = assignment.with_offer(order.id, edge.rider_id)
                    break
        return assignment


@dataclass(frozen=True)
class RiderGreedySolver:
    name: str = "rider_greedy"

    def solve(self, instance: Instance, evaluator: Evaluator, deadline: float | None = None) -> Assignment:
        assignment = Assignment.empty()
        for rider in sorted(instance.riders, key=lambda item: item.id):
            if expired(deadline):
                break
            rider_edges = sorted(
                (edge for edge in instance.edges if edge.rider_id == rider.id and edge.feasible),
                key=lambda edge: (-edge_value(edge), edge.cost, edge.order_id),
            )
            for edge in rider_edges:
                if expired(deadline):
                    break
                if can_add(instance, assignment, edge.order_id, rider.id):
                    assignment = assignment.with_offer(edge.order_id, rider.id)
                if assignment.rider_loads().get(rider.id, 0) >= rider.max_orders:
                    break
        return assignment


@dataclass(frozen=True)
class BundleGreedySolver:
    name: str = "bundle_greedy"

    def solve(self, instance: Instance, evaluator: Evaluator, deadline: float | None = None) -> Assignment:
        assignment = Assignment.empty()
        bundle_candidates = []
        for rider in instance.riders:
            for discount in instance.bundle_discounts_for(rider.id):
                edges = [instance.edge(order_id, rider.id) for order_id in discount.order_ids]
                if any(edge is None or not edge.feasible for edge in edges):
                    continue
                total_prob = sum(edge.accept_prob for edge in edges if edge is not None)
                total_cost = sum(edge.cost for edge in edges if edge is not None)
                bundle_candidates.append(
                    (
                        -discount.discount,
                        -(total_prob / max(total_cost - discount.discount, 0.001)),
                        rider.id,
                        discount.order_ids,
                    )
                )
        for _, _, rider_id, order_ids in sorted(bundle_candidates):
            if expired(deadline):
                break
            trial = assignment
            for order_id in order_ids:
                if not can_add(instance, trial, order_id, rider_id):
                    trial = assignment
                    break
                trial = trial.with_offer(order_id, rider_id)
            assignment = trial

        filler = OrderGreedySolver().solve(instance, evaluator, deadline)
        best_assignment, _ = evaluator.best(instance, [assignment, self._merge(instance, assignment, filler)])
        return best_assignment

    def _merge(self, instance: Instance, first: Assignment, second: Assignment) -> Assignment:
        merged = first
        for order_id, riders in second.offers.items():
            for rider_id in riders:
                if can_add(instance, merged, order_id, rider_id):
                    merged = merged.with_offer(order_id, rider_id)
        return merged


@dataclass(frozen=True)
class MarginalProbabilitySolver:
    min_gain: float = 0.005
    name: str = "marginal_probability"

    def solve(self, instance: Instance, evaluator: Evaluator, deadline: float | None = None) -> Assignment:
        offers: dict[str, list[str]] = {}
        rider_loads = {rider.id: 0 for rider in instance.riders}
        miss_probability = {order.id: 1.0 for order in instance.orders}
        priority = {order.id: order.priority for order in instance.orders}
        ordered_edges = tuple(edge for edge in instance.edges if edge.feasible)

        while not expired(deadline):
            best_edge: Edge | None = None
            best_gain = self.min_gain
            best_cost = float("inf")
            for edge in ordered_edges:
                if expired(deadline):
                    break
                if edge.rider_id in offers.get(edge.order_id, []):
                    continue
                if len(offers.get(edge.order_id, [])) >= instance.max_riders_per_order:
                    continue
                if rider_loads[edge.rider_id] >= instance.rider(edge.rider_id).max_orders:
                    continue
                gain = priority[edge.order_id] * miss_probability[edge.order_id] * edge.accept_prob
                if gain > best_gain or (abs(gain - best_gain) <= 1e-12 and edge.cost < best_cost):
                    best_edge = edge
                    best_gain = gain
                    best_cost = edge.cost
            if best_edge is None:
                break
            offers.setdefault(best_edge.order_id, []).append(best_edge.rider_id)
            rider_loads[best_edge.rider_id] += 1
            miss_probability[best_edge.order_id] *= 1.0 - best_edge.accept_prob
        return Assignment({order_id: tuple(riders) for order_id, riders in offers.items()})


@dataclass(frozen=True)
class RandomSolver:
    seed: int = 13
    iterations: int = 160
    name: str = "random"

    def solve(self, instance: Instance, evaluator: Evaluator, deadline: float | None = None) -> Assignment:
        rng = random.Random(self.seed)
        best_assignment = Assignment.empty()
        best_objective = evaluator.evaluate(instance, best_assignment)
        for _ in range(self.iterations):
            if expired(deadline):
                break
            assignment = Assignment.empty()
            orders = list(instance.orders)
            rng.shuffle(orders)
            for order in orders:
                if expired(deadline):
                    break
                edges = list(instance.candidate_edges(order.id))
                rng.shuffle(edges)
                target_count = rng.randint(0, min(instance.max_riders_per_order, len(edges)))
                for edge in edges:
                    if len(assignment.riders_for(order.id)) >= target_count:
                        break
                    if can_add(instance, assignment, order.id, edge.rider_id):
                        assignment = assignment.with_offer(order.id, edge.rider_id)
            objective = evaluator.evaluate(instance, assignment)
            if evaluator.better(objective, best_objective):
                best_assignment = assignment
                best_objective = objective
        return best_assignment


@dataclass(frozen=True)
class LocalSearchSolver:
    seed: int = 29
    iterations: int = 600
    name: str = "local_search"

    def solve(self, instance: Instance, evaluator: Evaluator, deadline: float | None = None) -> Assignment:
        rng = random.Random(self.seed)
        starts = [
            OrderGreedySolver().solve(instance, evaluator, deadline),
            RiderGreedySolver().solve(instance, evaluator, deadline),
            MarginalProbabilitySolver().solve(instance, evaluator, deadline),
        ]
        assignment, objective = evaluator.best(instance, starts)
        all_pairs = [(edge.order_id, edge.rider_id) for edge in instance.edges if edge.feasible]
        for _ in range(self.iterations):
            if expired(deadline):
                break
            if not all_pairs:
                break
            order_id, rider_id = rng.choice(all_pairs)
            if rider_id in assignment.riders_for(order_id):
                trial = assignment.without_offer(order_id, rider_id)
            elif can_add(instance, assignment, order_id, rider_id):
                trial = assignment.with_offer(order_id, rider_id)
            else:
                continue
            trial_objective = evaluator.evaluate(instance, trial)
            if evaluator.better(trial_objective, objective):
                assignment = trial
                objective = trial_objective
        return assignment


def default_solvers() -> list[Solver]:
    return [
        EmptySolver(),
        OrderGreedySolver(),
        RiderGreedySolver(),
        BundleGreedySolver(),
        MarginalProbabilitySolver(),
        RandomSolver(),
        LocalSearchSolver(),
    ]
