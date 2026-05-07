"""HeurAgenix-inspired agent layer for automatic strategy selection.

This module does not put an LLM on the 10-second critical path. Instead, it
implements a lightweight hyper-heuristic selector that reads problem-state
features, prunes the solver pool, runs the selected portfolio, and records the
decision. The shape mirrors HeurAgenix enough that an LLM evolution/reflection
stage can be added later without rewriting the online solver.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from autosolver.evaluator import Evaluator, Objective
from autosolver.features import InstanceFeatures, extract_instance_features
from autosolver.algorithm_generation import AlgorithmGenerator, TemplateAlgorithmGenerator
from autosolver.generated_solver import HeuristicSpec, specs_to_solvers
from autosolver.model import Assignment, Instance
from autosolver.portfolio import PortfolioReport, PortfolioSolver
from autosolver.solvers import Solver, default_solvers


@dataclass(frozen=True)
class AgentDecision:
    selected_solvers: tuple[str, ...]
    scenario_tags: tuple[str, ...]
    rationale: tuple[str, ...]
    features: InstanceFeatures
    generated_specs: tuple[HeuristicSpec, ...] = ()


@dataclass(frozen=True)
class AgentReport:
    assignment: Assignment
    objective: Objective
    decision: AgentDecision
    portfolio: PortfolioReport


class AgentMemory:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None

    def record(self, instance: Instance, report: AgentReport) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "instance": instance.name,
            "features": report.decision.features.to_dict(),
            "selected_solvers": list(report.decision.selected_solvers),
            "scenario_tags": list(report.decision.scenario_tags),
            "rationale": list(report.decision.rationale),
            "generated_specs": [spec.to_dict() for spec in report.decision.generated_specs],
            "best_solver": report.portfolio.best_solver,
            "objective": {
                "expected_accepted": report.objective.expected_accepted,
                "total_cost": report.objective.total_cost,
                "offer_count": report.objective.offer_count,
                "feasible": report.objective.feasible,
            },
            "runs": [
                {
                    "solver": run.solver_name,
                    "elapsed_sec": run.elapsed_sec,
                    "error": run.error,
                    "objective": None
                    if run.objective is None
                    else {
                        "expected_accepted": run.objective.expected_accepted,
                        "total_cost": run.objective.total_cost,
                        "offer_count": run.objective.offer_count,
                        "feasible": run.objective.feasible,
                    },
                }
                for run in report.portfolio.runs
            ],
        }
        with self.path.open("a", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.write("\n")


class HeurAgenixLiteAgent:
    """State-aware hyper-heuristic selector over the existing solver pool."""

    def __init__(
        self,
        solvers: list[Solver] | tuple[Solver, ...] | None = None,
        evaluator: Evaluator | None = None,
        time_limit_sec: float = 9.0,
        memory: AgentMemory | None = None,
        algorithm_generator: AlgorithmGenerator | None = None,
        generated_count: int = 0,
    ) -> None:
        self.solver_pool = tuple(solvers or default_solvers())
        self.evaluator = evaluator or Evaluator()
        self.time_limit_sec = time_limit_sec
        self.memory = memory or AgentMemory()
        self.algorithm_generator = algorithm_generator
        self.generated_count = generated_count

    def solve(self, instance: Instance) -> AgentReport:
        decision = self.decide(instance)
        generated_solvers = specs_to_solvers(decision.generated_specs)
        pool = tuple(self.solver_pool) + tuple(generated_solvers)
        selected = [solver for solver in pool if solver.name in decision.selected_solvers]
        portfolio = PortfolioSolver(
            solvers=selected,
            evaluator=self.evaluator,
            time_limit_sec=self.time_limit_sec,
        ).solve(instance)
        report = AgentReport(
            assignment=portfolio.assignment,
            objective=portfolio.objective,
            decision=decision,
            portfolio=portfolio,
        )
        self.memory.record(instance, report)
        return report

    def decide(self, instance: Instance) -> AgentDecision:
        features = extract_instance_features(instance)
        selected: list[str] = []
        rationale: list[str] = []
        generated_specs: tuple[HeuristicSpec, ...] = ()

        self._add(selected, "order_greedy", rationale, "fast coverage baseline")
        self._add(selected, "regret_greedy", rationale, "protect orders with fragile best-candidate gaps")

        if "multiposting" in features.scenario_tags:
            self._add(selected, "marginal_probability", rationale, "multi-rider offers benefit from marginal acceptance gains")
            self._add(selected, "coverage_then_marginal", rationale, "cover orders first, then use remaining capacity for extra acceptance")

        if "capacity_tight" in features.scenario_tags or "rider_skew" in features.scenario_tags:
            self._add(selected, "global_probability_greedy", rationale, "capacity pressure rewards globally strongest probability edges")
            self._add(selected, "swap_search", rationale, "conflict-heavy states need replacement moves")

        if "bundles" in features.scenario_tags:
            self._add(selected, "bundle_greedy", rationale, "bundle discounts are present")
            self._add(selected, "swap_search", rationale, "bundle and assignment conflicts benefit from local replacements")

        if "sparse" in features.scenario_tags:
            self._add(selected, "global_value_greedy", rationale, "sparse graphs need cost-aware fallback coverage")
            self._add(selected, "swap_search", rationale, "sparse bottlenecks often improve through swaps")

        if features.order_count <= 300:
            self._add(selected, "random", rationale, "small/medium cases can afford randomized diversification")
            self._add(selected, "local_search", rationale, "small/medium cases can afford local improvement")
        else:
            self._add(selected, "swap_search", rationale, "large cases reserve time for bounded, high-value local repair")

        if features.max_riders_per_order <= 1 and features.bundle_density == 0:
            self._add(selected, "rider_greedy", rationale, "single-offer cases need a rider-centric baseline")

        # Keep a safe fallback if a future selector rule is too aggressive.
        if len(selected) < 4:
            for name in ("marginal_probability", "coverage_then_marginal", "local_search"):
                self._add(selected, name, rationale, "fallback solver for selector robustness")

        if self.generated_count > 0:
            generator = self.algorithm_generator or TemplateAlgorithmGenerator()
            try:
                generated_specs = tuple(generator.generate(instance, self.generated_count))
                for spec in generated_specs:
                    self._add(
                        selected,
                        f"generated_{spec.name}",
                        rationale,
                        f"API-generated heuristic spec: {spec.description or 'no description'}",
                    )
            except Exception as exc:
                rationale.append(f"algorithm_generation_failed: {exc}")

        available = {solver.name for solver in self.solver_pool} | {f"generated_{spec.name}" for spec in generated_specs}
        selected = [name for name in selected if name in available]
        return AgentDecision(
            selected_solvers=tuple(selected),
            scenario_tags=features.scenario_tags,
            rationale=tuple(rationale),
            features=features,
            generated_specs=generated_specs,
        )

    def _add(self, selected: list[str], name: str, rationale: list[str], reason: str) -> None:
        if name not in selected:
            selected.append(name)
            rationale.append(f"{name}: {reason}")
