import unittest

from autosolver.official import (
    OfficialAssignment,
    OfficialEvaluator,
    OfficialOffer,
    OfficialPortfolioSolver,
    parse_official_input,
    solve,
)


SMALL_OFFICIAL = """task_id_list\tcourier_id\ttotal_score\twillingness
T1\tC1\t1.0\t0.90
T1\tC2\t2.0\t0.80
T2\tC1\t3.0\t0.70
T2\tC2\t1.0\t0.90
T1,T2\tC3\t1.5\t0.40
T1,T2\tC4\t2.0\t0.50
"""


class OfficialFormatTest(unittest.TestCase):
    def test_parse_official_tsv(self) -> None:
        instance = parse_official_input(SMALL_OFFICIAL)
        self.assertEqual(len(instance.task_ids), 2)
        self.assertEqual(len(instance.courier_ids), 4)
        self.assertEqual(len(instance.candidates), 6)
        self.assertIsNotNone(instance.candidate("T1,T2", "C3"))

    def test_evaluator_allows_multi_offer_on_same_task_bundle(self) -> None:
        instance = parse_official_input(SMALL_OFFICIAL)
        assignment = OfficialAssignment((OfficialOffer("T1,T2", ("C3", "C4")),))
        objective = OfficialEvaluator().evaluate(instance, assignment)
        self.assertTrue(objective.feasible, objective.violations)
        self.assertEqual(objective.covered_task_count, 2)
        self.assertAlmostEqual(objective.expected_accepted, 1.4)

    def test_evaluator_rejects_overlapping_task_bundles(self) -> None:
        instance = parse_official_input(SMALL_OFFICIAL)
        assignment = OfficialAssignment(
            (
                OfficialOffer("T1", ("C1",)),
                OfficialOffer("T1,T2", ("C3",)),
            )
        )
        objective = OfficialEvaluator().evaluate(instance, assignment)
        self.assertFalse(objective.feasible)
        self.assertTrue(any("multiple bundles" in violation for violation in objective.violations))

    def test_portfolio_returns_feasible_solution(self) -> None:
        instance = parse_official_input(SMALL_OFFICIAL)
        report = OfficialPortfolioSolver(time_limit_sec=1.0).solve(instance)
        self.assertTrue(report.objective.feasible, report.objective.violations)
        self.assertGreater(report.objective.expected_accepted, 0.0)

    def test_contest_solve_entrypoint_shape(self) -> None:
        result = solve(SMALL_OFFICIAL)
        self.assertIsInstance(result, list)
        self.assertTrue(result)
        task_key, couriers = result[0]
        self.assertIsInstance(task_key, str)
        self.assertIsInstance(couriers, list)


if __name__ == "__main__":
    unittest.main()
