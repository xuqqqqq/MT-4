"""Run multiple solvers under a shared time budget and keep the best result."""

from __future__ import annotations

import time
from dataclasses import dataclass

from autosolver.evaluator import Evaluator, Objective
from autosolver.model import Assignment, Instance
from autosolver.solvers import Solver, default_solvers


@dataclass(frozen=True)
class SolverRun:
    solver_name: str
    elapsed_sec: float
    objective: Objective | None
    error: str | None = None


@dataclass(frozen=True)
class PortfolioReport:
    assignment: Assignment
    objective: Objective
    best_solver: str
    elapsed_sec: float
    runs: tuple[SolverRun, ...]


class PortfolioSolver:
    TIME_SLICED_SOLVERS = frozenset({"swap_search", "random", "local_search"})

    def __init__(
        self,
        solvers: list[Solver] | tuple[Solver, ...] | None = None,
        evaluator: Evaluator | None = None,
        time_limit_sec: float = 9.0,
        per_solver_limit_sec: float | None = None,
    ) -> None:
        self.solvers = tuple(solvers or default_solvers())
        self.evaluator = evaluator or Evaluator()
        self.time_limit_sec = time_limit_sec
        self.per_solver_limit_sec = per_solver_limit_sec

    def solve(self, instance: Instance) -> PortfolioReport:
        start = time.perf_counter()
        deadline = start + self.time_limit_sec
        best_assignment = Assignment.empty()
        best_objective = self.evaluator.evaluate(instance, best_assignment)
        best_solver = "empty"
        runs: list[SolverRun] = []

        for index, solver in enumerate(self.solvers):
            if time.perf_counter() >= deadline:
                break
            solver_start = time.perf_counter()
            solver_deadline = self._solver_deadline(solver.name, solver_start, deadline, len(self.solvers) - index)
            try:
                assignment = solver.solve(instance, self.evaluator, solver_deadline)
                objective = self.evaluator.evaluate(instance, assignment)
                elapsed = time.perf_counter() - solver_start
                runs.append(SolverRun(solver.name, elapsed, objective))
                if self.evaluator.better(objective, best_objective):
                    best_assignment = assignment
                    best_objective = objective
                    best_solver = solver.name
            except Exception as exc:  # pragma: no cover - defensive portfolio isolation
                elapsed = time.perf_counter() - solver_start
                runs.append(SolverRun(solver.name, elapsed, None, error=repr(exc)))

        return PortfolioReport(
            assignment=best_assignment,
            objective=best_objective,
            best_solver=best_solver,
            elapsed_sec=time.perf_counter() - start,
            runs=tuple(runs),
        )

    def _solver_deadline(
        self,
        solver_name: str,
        solver_start: float,
        global_deadline: float,
        remaining_solvers: int,
    ) -> float:
        if solver_name not in self.TIME_SLICED_SOLVERS:
            return global_deadline

        remaining_time = max(0.0, global_deadline - solver_start)
        dynamic_slice = max(0.01, remaining_time / max(1, remaining_solvers))
        if self.per_solver_limit_sec is not None:
            dynamic_slice = min(dynamic_slice, self.per_solver_limit_sec)
        return min(global_deadline, solver_start + dynamic_slice)
