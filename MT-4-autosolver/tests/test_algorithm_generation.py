import unittest
from unittest.mock import patch

from autosolver.agent import HeurAgenixLiteAgent
from autosolver.algorithm_generation import TemplateAlgorithmGenerator, make_algorithm_generator, parse_specs
from autosolver.evaluator import Evaluator
from autosolver.generated_solver import GeneratedGreedySolver, HeuristicSpec
from autosolver.generators import multi_offer_probability, tiny_manual


class FixedGenerator:
    def generate(self, instance, count: int = 4) -> list[HeuristicSpec]:
        return [
            HeuristicSpec(
                name=f"fixed_{index + 1}",
                description="test generated heuristic",
                order_priority="best_probability",
                edge_accept_weight=1.0,
                edge_cost_weight=0.02,
                multi_offer=instance.max_riders_per_order > 1,
                max_offers_per_order=2,
            )
            for index in range(count)
        ]


class AlgorithmGenerationTest(unittest.TestCase):
    def test_parse_specs_accepts_json_block(self) -> None:
        specs = parse_specs(
            """
            ```json
            {
              "heuristics": [
                {
                  "name": "Prob Win!",
                  "description": "favor probability",
                  "order_priority": "best_probability",
                  "edge_accept_weight": 2.0,
                  "edge_cost_weight": 0.1,
                  "multi_offer": true,
                  "max_offers_per_order": 3
                }
              ]
            }
            ```
            """,
            count=1,
        )
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].name, "prob_win")
        self.assertTrue(specs[0].multi_offer)
        self.assertEqual(specs[0].max_offers_per_order, 3)

    def test_template_generator_returns_requested_specs_up_to_template_count(self) -> None:
        specs = TemplateAlgorithmGenerator().generate(multi_offer_probability(), count=3)
        self.assertEqual(len(specs), 3)
        self.assertTrue(all(spec.name.startswith("api_like_") for spec in specs))

    def test_make_generator_rejects_openai_compatible_without_model(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError):
                make_algorithm_generator("openai-compatible", model=None)

    def test_generated_greedy_solver_returns_feasible_assignment(self) -> None:
        instance = multi_offer_probability()
        solver = GeneratedGreedySolver(
            HeuristicSpec(
                name="test_multi",
                order_priority="best_probability",
                edge_accept_weight=1.0,
                edge_cost_weight=0.01,
                multi_offer=True,
                max_offers_per_order=2,
            )
        )
        objective = Evaluator().evaluate(instance, solver.solve(instance, Evaluator()))
        self.assertTrue(objective.feasible, objective.violations)
        self.assertGreater(objective.offer_count, 0)

    def test_generated_solver_falls_back_when_threshold_scale_is_too_high(self) -> None:
        instance = tiny_manual()
        solver = GeneratedGreedySolver(
            HeuristicSpec(
                name="over_threshold",
                edge_accept_weight=1.0,
                edge_cost_weight=10.0,
                min_edge_score=9999.0,
            )
        )
        objective = Evaluator().evaluate(instance, solver.solve(instance, Evaluator()))
        self.assertTrue(objective.feasible, objective.violations)
        self.assertGreater(objective.offer_count, 0)

    def test_agent_includes_api_generated_specs_in_portfolio(self) -> None:
        instance = tiny_manual()
        agent = HeurAgenixLiteAgent(
            time_limit_sec=1.0,
            algorithm_generator=FixedGenerator(),
            generated_count=2,
        )
        report = agent.solve(instance)
        self.assertTrue(report.objective.feasible, report.objective.violations)
        self.assertEqual(len(report.decision.generated_specs), 2)
        self.assertIn("generated_fixed_1", report.decision.selected_solvers)
        self.assertTrue(any(run.solver_name == "generated_fixed_1" for run in report.portfolio.runs))


if __name__ == "__main__":
    unittest.main()
