import unittest

from autosolver.evaluator import Evaluator, acceptance_probability
from autosolver.generators import bundle_wins, tiny_manual
from autosolver.model import Assignment


class EvaluatorTest(unittest.TestCase):
    def test_acceptance_probability_for_multiple_offers(self) -> None:
        self.assertAlmostEqual(acceptance_probability([0.4, 0.35, 0.3]), 0.727)

    def test_tiny_manual_known_assignment(self) -> None:
        instance = tiny_manual()
        assignment = Assignment({"o1": ("r1",), "o2": ("r2",)})
        objective = Evaluator().evaluate(instance, assignment)
        self.assertTrue(objective.feasible)
        self.assertAlmostEqual(objective.expected_accepted, 1.8)
        self.assertAlmostEqual(objective.total_cost, 2.0)

    def test_capacity_violation_is_infeasible(self) -> None:
        instance = tiny_manual()
        assignment = Assignment({"o1": ("r1",), "o2": ("r1",)})
        objective = Evaluator().evaluate(instance, assignment)
        self.assertFalse(objective.feasible)
        self.assertTrue(any("exceeds max_orders" in violation for violation in objective.violations))

    def test_bundle_discount_reduces_cost(self) -> None:
        instance = bundle_wins()
        assignment = Assignment({"o1": ("bundle",), "o2": ("bundle",), "o3": ("bundle",)})
        objective = Evaluator().evaluate(instance, assignment)
        self.assertTrue(objective.feasible)
        self.assertAlmostEqual(objective.total_cost, 4.6)

    def test_lexicographic_comparison_prefers_more_expected_acceptance_first(self) -> None:
        evaluator = Evaluator()
        instance = tiny_manual()
        cheap_low_prob = evaluator.evaluate(instance, Assignment({"o1": ("r2",)}))
        expensive_high_prob = evaluator.evaluate(instance, Assignment({"o1": ("r1",)}))
        self.assertTrue(evaluator.better(expensive_high_prob, cheap_low_prob))


if __name__ == "__main__":
    unittest.main()
