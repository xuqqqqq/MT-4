import unittest

from autosolver.evaluator import Evaluator
from autosolver.generators import CASE_GENERATORS, large_random, tiny_manual
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


if __name__ == "__main__":
    unittest.main()
