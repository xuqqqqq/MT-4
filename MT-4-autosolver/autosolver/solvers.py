"""Baseline and improvement solvers for the portfolio runner."""

from __future__ import annotations

import random
import time
from heapq import heappop, heappush
from dataclasses import dataclass
from itertools import product
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


def can_add_to_state(
    instance: Instance,
    offers: dict[str, list[str]],
    rider_loads: dict[str, int],
    order_id: str,
    rider_id: str,
) -> bool:
    if rider_id in offers.get(order_id, []):
        return False
    edge = instance.edge(order_id, rider_id)
    if edge is None or not edge.feasible:
        return False
    if len(offers.get(order_id, [])) >= instance.max_riders_per_order:
        return False
    return rider_loads.get(rider_id, 0) < instance.rider(rider_id).max_orders


def add_to_state(offers: dict[str, list[str]], rider_loads: dict[str, int], order_id: str, rider_id: str) -> None:
    offers.setdefault(order_id, []).append(rider_id)
    rider_loads[rider_id] = rider_loads.get(rider_id, 0) + 1


def assignment_from_state(offers: dict[str, list[str]]) -> Assignment:
    return Assignment({order_id: tuple(riders) for order_id, riders in offers.items()})


def state_from_assignment(instance: Instance, assignment: Assignment) -> tuple[dict[str, list[str]], dict[str, int], dict[str, float]]:
    offers = {order_id: list(riders) for order_id, riders in assignment.offers.items()}
    rider_loads = {rider.id: 0 for rider in instance.riders}
    miss_probability = {order.id: 1.0 for order in instance.orders}
    for order_id, riders in offers.items():
        for rider_id in riders:
            edge = instance.edge(order_id, rider_id)
            if edge is None or not edge.feasible:
                continue
            rider_loads[rider_id] = rider_loads.get(rider_id, 0) + 1
            miss_probability[order_id] *= 1.0 - edge.accept_prob
    return offers, rider_loads, miss_probability


def edge_preference(edge: Edge) -> tuple[float, float, str]:
    return (-edge.accept_prob, edge.cost, edge.rider_id)


def edge_value(edge: Edge) -> float:
    return edge.accept_prob / max(edge.cost, 0.001)


def expand_with_marginal_offers(
    instance: Instance,
    assignment: Assignment,
    deadline: float | None,
    min_gain: float = 0.005,
) -> Assignment:
    """Add offers by current marginal acceptance using a stale-safe heap."""

    offers, rider_loads, miss_probability = state_from_assignment(instance, assignment)
    priority = {order.id: order.priority for order in instance.orders}
    version = {order.id: 0 for order in instance.orders}
    heap: list[tuple[float, float, str, str, int]] = []

    for edge in instance.edges:
        if not edge.feasible:
            continue
        gain = priority[edge.order_id] * miss_probability[edge.order_id] * edge.accept_prob
        if gain >= min_gain:
            heappush(heap, (-gain, edge.cost, edge.order_id, edge.rider_id, version[edge.order_id]))

    while heap and not expired(deadline):
        negative_gain, cost, order_id, rider_id, item_version = heappop(heap)
        if item_version != version[order_id]:
            edge = instance.edge(order_id, rider_id)
            if edge is None or not edge.feasible:
                continue
            gain = priority[order_id] * miss_probability[order_id] * edge.accept_prob
            if gain >= min_gain:
                heappush(heap, (-gain, edge.cost, order_id, rider_id, version[order_id]))
            continue
        if -negative_gain < min_gain:
            break
        if not can_add_to_state(instance, offers, rider_loads, order_id, rider_id):
            continue
        edge = instance.edge(order_id, rider_id)
        if edge is None:
            continue
        offers.setdefault(order_id, []).append(rider_id)
        rider_loads[rider_id] = rider_loads.get(rider_id, 0) + 1
        miss_probability[order_id] *= 1.0 - edge.accept_prob
        version[order_id] += 1
    return assignment_from_state(offers)


@dataclass(frozen=True)
class EmptySolver:
    name: str = "empty"

    def solve(self, instance: Instance, evaluator: Evaluator, deadline: float | None = None) -> Assignment:
        return Assignment.empty()


@dataclass(frozen=True)
class OrderGreedySolver:
    name: str = "order_greedy"

    def solve(self, instance: Instance, evaluator: Evaluator, deadline: float | None = None) -> Assignment:
        offers: dict[str, list[str]] = {}
        rider_loads = {rider.id: 0 for rider in instance.riders}
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
                if can_add_to_state(instance, offers, rider_loads, order.id, edge.rider_id):
                    add_to_state(offers, rider_loads, order.id, edge.rider_id)
                    break
        return assignment_from_state(offers)


@dataclass(frozen=True)
class RiderGreedySolver:
    name: str = "rider_greedy"

    def solve(self, instance: Instance, evaluator: Evaluator, deadline: float | None = None) -> Assignment:
        offers: dict[str, list[str]] = {}
        rider_loads = {rider.id: 0 for rider in instance.riders}
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
                if can_add_to_state(instance, offers, rider_loads, edge.order_id, rider.id):
                    add_to_state(offers, rider_loads, edge.order_id, rider.id)
                if rider_loads.get(rider.id, 0) >= rider.max_orders:
                    break
        return assignment_from_state(offers)


@dataclass(frozen=True)
class GlobalProbabilityGreedySolver:
    name: str = "global_probability_greedy"

    def solve(self, instance: Instance, evaluator: Evaluator, deadline: float | None = None) -> Assignment:
        offers: dict[str, list[str]] = {}
        rider_loads = {rider.id: 0 for rider in instance.riders}
        for edge in sorted(instance.edges, key=edge_preference):
            if expired(deadline):
                break
            if can_add_to_state(instance, offers, rider_loads, edge.order_id, edge.rider_id):
                add_to_state(offers, rider_loads, edge.order_id, edge.rider_id)
        return assignment_from_state(offers)


@dataclass(frozen=True)
class GlobalValueGreedySolver:
    name: str = "global_value_greedy"

    def solve(self, instance: Instance, evaluator: Evaluator, deadline: float | None = None) -> Assignment:
        offers: dict[str, list[str]] = {}
        rider_loads = {rider.id: 0 for rider in instance.riders}
        for edge in sorted(instance.edges, key=lambda edge: (-edge_value(edge), -edge.accept_prob, edge.cost)):
            if expired(deadline):
                break
            if can_add_to_state(instance, offers, rider_loads, edge.order_id, edge.rider_id):
                add_to_state(offers, rider_loads, edge.order_id, edge.rider_id)
        return assignment_from_state(offers)


@dataclass(frozen=True)
class RegretGreedySolver:
    name: str = "regret_greedy"

    def solve(self, instance: Instance, evaluator: Evaluator, deadline: float | None = None) -> Assignment:
        offers: dict[str, list[str]] = {}
        rider_loads = {rider.id: 0 for rider in instance.riders}
        ranked_orders = []
        for order in instance.orders:
            candidates = sorted(instance.candidate_edges(order.id), key=edge_preference)
            best_probability = candidates[0].accept_prob if candidates else 0.0
            second_probability = candidates[1].accept_prob if len(candidates) > 1 else 0.0
            regret = best_probability - second_probability
            ranked_orders.append((-order.priority * regret, len(candidates), -best_probability, order.id, candidates))

        for _, _, _, order_id, candidates in sorted(ranked_orders):
            if expired(deadline):
                break
            for edge in candidates:
                if can_add_to_state(instance, offers, rider_loads, order_id, edge.rider_id):
                    add_to_state(offers, rider_loads, order_id, edge.rider_id)
                    break
        return assignment_from_state(offers)


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
        return expand_with_marginal_offers(instance, Assignment.empty(), deadline, self.min_gain)


@dataclass(frozen=True)
class CoverageThenMarginalSolver:
    min_gain: float = 0.005
    name: str = "coverage_then_marginal"

    def solve(self, instance: Instance, evaluator: Evaluator, deadline: float | None = None) -> Assignment:
        starts = [
            OrderGreedySolver().solve(instance, evaluator, deadline),
            RegretGreedySolver().solve(instance, evaluator, deadline),
            GlobalProbabilityGreedySolver().solve(instance, evaluator, deadline),
        ]
        assignment, _ = evaluator.best(instance, starts)
        return expand_with_marginal_offers(instance, assignment, deadline, self.min_gain)


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
class SwapSearchSolver:
    candidate_limit: int = 1800
    name: str = "swap_search"

    def solve(self, instance: Instance, evaluator: Evaluator, deadline: float | None = None) -> Assignment:
        starts = [
            OrderGreedySolver().solve(instance, evaluator, deadline),
            RegretGreedySolver().solve(instance, evaluator, deadline),
            MarginalProbabilitySolver().solve(instance, evaluator, deadline),
            CoverageThenMarginalSolver().solve(instance, evaluator, deadline),
        ]
        assignment, objective = evaluator.best(instance, starts)
        checked = 0
        for edge in sorted(instance.edges, key=edge_preference):
            if expired(deadline) or checked >= self.candidate_limit:
                break
            if edge.rider_id in assignment.riders_for(edge.order_id):
                continue
            checked += 1
            for trial in self._swap_trials(instance, assignment, edge):
                if expired(deadline):
                    break
                trial_objective = evaluator.evaluate(instance, trial)
                if evaluator.better(trial_objective, objective):
                    assignment = trial
                    objective = trial_objective
                    break
        return assignment

    def _swap_trials(self, instance: Instance, assignment: Assignment, edge: Edge) -> list[Assignment]:
        order_riders = assignment.riders_for(edge.order_id)
        rider_orders = assignment.rider_orders().get(edge.rider_id, ())
        rider_load = len(rider_orders)

        order_removals: list[tuple[tuple[str, str], ...]] = [()]
        if len(order_riders) >= instance.max_riders_per_order:
            order_removals = [((edge.order_id, rider_id),) for rider_id in order_riders]

        rider_removals: list[tuple[tuple[str, str], ...]] = [()]
        if rider_load >= instance.rider(edge.rider_id).max_orders:
            rider_removals = [((order_id, edge.rider_id),) for order_id in rider_orders]

        trials: list[Assignment] = []
        seen: set[tuple[tuple[str, str], ...]] = set()
        for order_choice, rider_choice in product(order_removals, rider_removals):
            removals = tuple(sorted(set(order_choice + rider_choice)))
            if removals in seen:
                continue
            seen.add(removals)
            trial = assignment
            for order_id, rider_id in removals:
                trial = trial.without_offer(order_id, rider_id)
            if can_add(instance, trial, edge.order_id, edge.rider_id):
                trials.append(trial.with_offer(edge.order_id, edge.rider_id))
        return trials


@dataclass(frozen=True)
class LocalSearchSolver:
    seed: int = 29
    iterations: int = 600
    name: str = "local_search"

    def solve(self, instance: Instance, evaluator: Evaluator, deadline: float | None = None) -> Assignment:
        rng = random.Random(self.seed)
        starts = [
            OrderGreedySolver().solve(instance, evaluator, deadline),
            RegretGreedySolver().solve(instance, evaluator, deadline),
            RiderGreedySolver().solve(instance, evaluator, deadline),
            MarginalProbabilitySolver().solve(instance, evaluator, deadline),
            CoverageThenMarginalSolver().solve(instance, evaluator, deadline),
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
        RegretGreedySolver(),
        MarginalProbabilitySolver(),
        CoverageThenMarginalSolver(),
        RiderGreedySolver(),
        BundleGreedySolver(),
        GlobalProbabilityGreedySolver(),
        GlobalValueGreedySolver(),
        SwapSearchSolver(),
        RandomSolver(),
        LocalSearchSolver(),
    ]
