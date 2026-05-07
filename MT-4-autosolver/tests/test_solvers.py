import unittest

from autosolver.agent import HeurAgenixLiteAgent
from autosolver.evaluator import Evaluator
from autosolver.generators import CASE_GENERATORS, complex_mixed_city, large_random, tiny_manual
from autosolver.portfolio import PortfolioSolver
from autosolver.solvers import default_solvers


class SolverTest(unittest.TestCase):
    def test_all_solvers_return_feasible_on_tiny_manual(self) -> None:
        instance = tiny_manual()
        evaluator = Evaluator()
        for solver in default_solvers():
            with self.subTest(solver=solver.name):
                assignment = solver.solve(instance, evaluator)
                objective = evaluator.evaluate(instance, assignment)
                self.assertTrue(objective.feasible, objective.violations)

    def test_portfolio_matches_tiny_manual_expected_best(self) -> None:
        instance = tiny_manual()
        report = PortfolioSolver(time_limit_sec=1.0).solve(instance)
        self.assertTrue(report.objective.feasible)
        self.assertAlmostEqual(report.objective.expected_accepted, 1.8)
        self.assertAlmostEqual(report.objective.total_cost, 2.0)

    def test_portfolio_handles_all_named_synthetic_cases(self) -> None:
        for name, generator in CASE_GENERATORS.items():
            with self.subTest(case=name):
                instance = generator()
                report = PortfolioSolver(time_limit_sec=1.0).solve(instance)
                self.assertTrue(report.objective.feasible, report.objective.violations)
                self.assertGreaterEqual(report.objective.expected_accepted, 0.0)
                self.assertLessEqual(report.elapsed_sec, 1.25)

    def test_large_random_finishes_under_budget(self) -> None:
        instance = large_random(seed=7, order_count=160, rider_count=35)
        report = PortfolioSolver(time_limit_sec=2.0).solve(instance)
        self.assertTrue(report.objective.feasible, report.objective.violations)
        self.assertLessEqual(report.elapsed_sec, 2.25)

    def test_stress_generator_can_scale_down_for_fast_regression(self) -> None:
        instance = complex_mixed_city(seed=11, order_count=50, rider_count=12)
        report = PortfolioSolver(time_limit_sec=1.0).solve(instance)
        self.assertTrue(report.objective.feasible, report.objective.violations)
        self.assertEqual(len(instance.orders), 50)
        self.assertGreater(len(instance.edges), 0)

    def test_agent_selects_multiposting_heuristics(self) -> None:
        instance = large_random(seed=3, order_count=40, rider_count=10)
        agent = HeurAgenixLiteAgent(time_limit_sec=1.0)
        decision = agent.decide(instance)
        self.assertIn("multiposting", decision.scenario_tags)
        self.assertIn("marginal_probability", decision.selected_solvers)
        self.assertIn("coverage_then_marginal", decision.selected_solvers)

    def test_agent_solves_scaled_stress_case(self) -> None:
        instance = complex_mixed_city(seed=12, order_count=60, rider_count=14)
        report = HeurAgenixLiteAgent(time_limit_sec=1.0).solve(instance)
        self.assertTrue(report.objective.feasible, report.objective.violations)
        self.assertGreaterEqual(report.objective.expected_accepted, 0.0)


if __name__ == "__main__":
    unittest.main()
