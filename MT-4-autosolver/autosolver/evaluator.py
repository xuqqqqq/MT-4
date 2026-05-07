"""Temporary evaluator for synthetic cases and strategy comparison."""

from __future__ import annotations

from dataclasses import dataclass
from math import prod

from autosolver.model import Assignment, Instance


EPS = 1e-9


@dataclass(frozen=True)
class Objective:
    expected_accepted: float
    total_cost: float
    offer_count: int
    feasible: bool
    violations: tuple[str, ...] = ()

    def label(self) -> str:
        status = "feasible" if self.feasible else "infeasible"
        return (
            f"{status}: expected={self.expected_accepted:.6f}, "
            f"cost={self.total_cost:.3f}, offers={self.offer_count}"
        )


class Evaluator:
    """Lexicographic evaluator.

    Current contest assumption:
    1. Maximize expected accepted order count.
    2. Minimize total cost among equal expected acceptance.
    3. Minimize number of offers as a deterministic final tie-breaker.
    """

    def __init__(self, eps: float = EPS) -> None:
        self.eps = eps

    def evaluate(self, instance: Instance, assignment: Assignment) -> Objective:
        violations: list[str] = []
        total_cost = 0.0
        expected_accepted = 0.0

        rider_loads = assignment.rider_loads()
        for rider_id, load in sorted(rider_loads.items()):
            if rider_id not in instance.rider_ids:
                violations.append(f"unknown rider {rider_id!r}")
                continue
            max_orders = instance.rider(rider_id).max_orders
            if load > max_orders:
                violations.append(f"rider {rider_id!r} load {load} exceeds max_orders {max_orders}")

        for order_id, riders in sorted(assignment.offers.items()):
            if order_id not in instance.order_ids:
                violations.append(f"unknown order {order_id!r}")
                continue
            if len(riders) > instance.max_riders_per_order:
                violations.append(
                    f"order {order_id!r} has {len(riders)} riders, "
                    f"limit is {instance.max_riders_per_order}"
                )

            miss_probability = 1.0
            for rider_id in riders:
                edge = instance.edge(order_id, rider_id)
                if edge is None:
                    violations.append(f"missing edge order={order_id!r} rider={rider_id!r}")
                    continue
                if not edge.feasible:
                    violations.append(f"infeasible edge order={order_id!r} rider={rider_id!r}")
                    continue
                total_cost += edge.cost
                miss_probability *= 1.0 - edge.accept_prob

            expected_accepted += instance.order(order_id).priority * (1.0 - miss_probability)

        total_cost -= self._bundle_discount(instance, assignment)
        total_cost = max(0.0, total_cost)
        return Objective(
            expected_accepted=expected_accepted,
            total_cost=total_cost,
            offer_count=assignment.offer_count(),
            feasible=not violations,
            violations=tuple(violations),
        )

    def better(self, candidate: Objective, incumbent: Objective | None) -> bool:
        if incumbent is None:
            return True
        if candidate.feasible != incumbent.feasible:
            return candidate.feasible
        if candidate.expected_accepted > incumbent.expected_accepted + self.eps:
            return True
        if incumbent.expected_accepted > candidate.expected_accepted + self.eps:
            return False
        if candidate.total_cost < incumbent.total_cost - self.eps:
            return True
        if incumbent.total_cost < candidate.total_cost - self.eps:
            return False
        return candidate.offer_count < incumbent.offer_count

    def best(
        self,
        instance: Instance,
        assignments: list[Assignment] | tuple[Assignment, ...],
    ) -> tuple[Assignment, Objective]:
        best_assignment = Assignment.empty()
        best_objective: Objective | None = None
        for assignment in assignments:
            objective = self.evaluate(instance, assignment)
            if self.better(objective, best_objective):
                best_assignment = assignment
                best_objective = objective
        if best_objective is None:
            best_objective = self.evaluate(instance, best_assignment)
        return best_assignment, best_objective

    def _bundle_discount(self, instance: Instance, assignment: Assignment) -> float:
        discount_total = 0.0
        rider_orders = assignment.rider_orders()
        for rider_id, order_ids in rider_orders.items():
            assigned = set(order_ids)
            discounts = []
            for discount in instance.bundle_discounts_for(rider_id):
                if set(discount.order_ids).issubset(assigned):
                    discounts.append(discount.discount)
            discount_total += sum(discounts)
        return discount_total


def acceptance_probability(probabilities: list[float] | tuple[float, ...]) -> float:
    """Probability that at least one rider accepts an order."""

    if not probabilities:
        return 0.0
    return 1.0 - prod(1.0 - probability for probability in probabilities)
