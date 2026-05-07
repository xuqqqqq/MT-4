"""Official TSV adapter and solver portfolio.

The contest data is a set of candidate assignments. Each row is a hyper-edge:
one courier can be offered either one task or a bundled pair of tasks.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable, Protocol


@dataclass(frozen=True)
class OfficialCandidate:
    task_key: str
    tasks: tuple[str, ...]
    courier_id: str
    total_score: float
    willingness: float

    @property
    def task_set(self) -> tuple[str, ...]:
        return tuple(sorted(self.tasks))


@dataclass(frozen=True)
class OfficialInstance:
    candidates: tuple[OfficialCandidate, ...]
    task_ids: tuple[str, ...]
    courier_ids: tuple[str, ...]
    _candidate_by_offer: dict[tuple[str, str], OfficialCandidate]
    _candidates_by_task_set: dict[tuple[str, ...], tuple[OfficialCandidate, ...]]

    @classmethod
    def from_candidates(cls, candidates: Iterable[OfficialCandidate]) -> "OfficialInstance":
        candidate_tuple = tuple(candidates)
        task_ids = tuple(sorted({task_id for candidate in candidate_tuple for task_id in candidate.tasks}))
        courier_ids = tuple(sorted({candidate.courier_id for candidate in candidate_tuple}))
        by_offer: dict[tuple[str, str], OfficialCandidate] = {}
        by_task_set: dict[tuple[str, ...], list[OfficialCandidate]] = {}
        for candidate in candidate_tuple:
            by_offer[(candidate.task_key, candidate.courier_id)] = candidate
            by_task_set.setdefault(candidate.task_set, []).append(candidate)
        return cls(
            candidates=candidate_tuple,
            task_ids=task_ids,
            courier_ids=courier_ids,
            _candidate_by_offer=by_offer,
            _candidates_by_task_set={key: tuple(value) for key, value in by_task_set.items()},
        )

    def candidate(self, task_key: str, courier_id: str) -> OfficialCandidate | None:
        return self._candidate_by_offer.get((task_key, courier_id))

    def candidates_for_task_set(self, task_set: tuple[str, ...]) -> tuple[OfficialCandidate, ...]:
        return self._candidates_by_task_set.get(tuple(sorted(task_set)), ())


@dataclass(frozen=True)
class OfficialOffer:
    task_key: str
    courier_ids: tuple[str, ...]


@dataclass(frozen=True)
class OfficialAssignment:
    offers: tuple[OfficialOffer, ...]

    @classmethod
    def empty(cls) -> "OfficialAssignment":
        return cls(())

    def to_result(self) -> list[tuple[str, list[str]]]:
        return [(offer.task_key, list(offer.courier_ids)) for offer in self.offers if offer.courier_ids]


@dataclass(frozen=True)
class OfficialObjective:
    expected_accepted: float
    covered_task_count: int
    total_score: float
    offer_count: int
    feasible: bool
    violations: tuple[str, ...] = ()

    def label(self) -> str:
        status = "feasible" if self.feasible else "infeasible"
        return (
            f"{status}: expected={self.expected_accepted:.6f}, "
            f"covered={self.covered_task_count}, score={self.total_score:.3f}, offers={self.offer_count}"
        )


class OfficialEvaluator:
    """Temporary evaluator matching the current public brief.

    We optimize expected accepted task count first, then deterministic task
    coverage, then total score. If the official scorer turns out to ignore
    willingness, this class is the only place that needs a priority change.
    """

    def evaluate(self, instance: OfficialInstance, assignment: OfficialAssignment) -> OfficialObjective:
        violations: list[str] = []
        used_couriers: set[str] = set()
        task_owner: dict[str, str] = {}
        expected_accepted = 0.0
        total_score = 0.0
        offer_count = 0

        for offer in assignment.offers:
            if not offer.courier_ids:
                continue
            candidates = []
            task_set: tuple[str, ...] | None = None
            for courier_id in offer.courier_ids:
                candidate = instance.candidate(offer.task_key, courier_id)
                if candidate is None:
                    violations.append(f"unknown candidate ({offer.task_key}, {courier_id})")
                    continue
                if task_set is None:
                    task_set = candidate.task_set
                elif task_set != candidate.task_set:
                    violations.append(f"task key {offer.task_key} maps to inconsistent task sets")
                if courier_id in used_couriers:
                    violations.append(f"courier {courier_id} is used more than once")
                used_couriers.add(courier_id)
                candidates.append(candidate)
                total_score += candidate.total_score
                offer_count += 1

            if task_set is None:
                continue
            owner_key = ",".join(task_set)
            for task_id in task_set:
                previous = task_owner.get(task_id)
                if previous is not None and previous != owner_key:
                    violations.append(f"task {task_id} appears in multiple bundles")
                task_owner[task_id] = owner_key
            expected_accepted += len(task_set) * acceptance_probability(candidate.willingness for candidate in candidates)

        return OfficialObjective(
            expected_accepted=expected_accepted,
            covered_task_count=len(task_owner),
            total_score=total_score,
            offer_count=offer_count,
            feasible=not violations,
            violations=tuple(violations),
        )

    def better(self, candidate: OfficialObjective, incumbent: OfficialObjective) -> bool:
        if candidate.feasible != incumbent.feasible:
            return candidate.feasible
        if not candidate.feasible:
            return len(candidate.violations) < len(incumbent.violations)
        if abs(candidate.expected_accepted - incumbent.expected_accepted) > 1e-9:
            return candidate.expected_accepted > incumbent.expected_accepted
        if candidate.covered_task_count != incumbent.covered_task_count:
            return candidate.covered_task_count > incumbent.covered_task_count
        if abs(candidate.total_score - incumbent.total_score) > 1e-9:
            return candidate.total_score < incumbent.total_score
        return candidate.offer_count < incumbent.offer_count


class OfficialSolver(Protocol):
    name: str

    def solve(
        self,
        instance: OfficialInstance,
        evaluator: OfficialEvaluator,
        deadline: float | None = None,
    ) -> OfficialAssignment:
        ...


@dataclass(frozen=True)
class OfficialRun:
    solver_name: str
    elapsed_sec: float
    objective: OfficialObjective | None
    error: str | None = None


@dataclass(frozen=True)
class OfficialReport:
    assignment: OfficialAssignment
    objective: OfficialObjective
    best_solver: str
    elapsed_sec: float
    runs: tuple[OfficialRun, ...]


@dataclass(frozen=True)
class OfficialGreedySolver:
    name: str
    priority: str
    willingness_weight: float = 0.0
    max_offers_per_bundle: int = 1
    min_marginal_gain: float = 0.0

    def solve(
        self,
        instance: OfficialInstance,
        evaluator: OfficialEvaluator,
        deadline: float | None = None,
    ) -> OfficialAssignment:
        selected = choose_disjoint_candidates(instance, sorted(instance.candidates, key=self._key), deadline)
        if self.max_offers_per_bundle > 1:
            selected = expand_multi_offers(
                instance,
                selected,
                self.max_offers_per_bundle,
                self.min_marginal_gain,
                deadline,
            )
        return assignment_from_selected(selected)

    def _key(self, candidate: OfficialCandidate) -> tuple[float, float, float, str, str]:
        task_count = max(1, len(candidate.tasks))
        expected = task_count * candidate.willingness
        if self.priority == "score_per_task":
            primary = candidate.total_score / task_count
        elif self.priority == "willingness":
            primary = -candidate.willingness
        elif self.priority == "score_minus_willingness":
            primary = candidate.total_score - self.willingness_weight * expected
        elif self.priority == "score_per_expected":
            primary = candidate.total_score / max(expected, 1e-9)
        elif self.priority == "pair_first_score":
            primary = -task_count * 10_000 + candidate.total_score
        else:
            primary = candidate.total_score
        return (primary, candidate.total_score, -candidate.willingness, candidate.task_key, candidate.courier_id)


@dataclass(frozen=True)
class OfficialRepairSolver:
    """Small local replacement search over the strongest greedy starts."""

    name: str = "official_repair"
    candidate_limit: int = 300

    def solve(
        self,
        instance: OfficialInstance,
        evaluator: OfficialEvaluator,
        deadline: float | None = None,
    ) -> OfficialAssignment:
        starts = [
            OfficialGreedySolver("start_score", "score").solve(instance, evaluator, deadline),
            OfficialGreedySolver("start_expected", "score_per_expected").solve(instance, evaluator, deadline),
            OfficialGreedySolver("start_willing", "willingness").solve(instance, evaluator, deadline),
            OfficialGreedySolver("start_pair", "score_per_task").solve(instance, evaluator, deadline),
        ]
        assignment, objective = best_assignment(instance, evaluator, starts)
        checked = 0
        for candidate in sorted(instance.candidates, key=lambda item: item.total_score / max(item.willingness, 1e-9)):
            if expired(deadline) or checked >= self.candidate_limit:
                break
            checked += 1
            trial = repair_with_candidate(instance, assignment, candidate)
            trial_objective = evaluator.evaluate(instance, trial)
            if evaluator.better(trial_objective, objective):
                assignment = trial
                objective = trial_objective
        return assignment


class OfficialPortfolioSolver:
    def __init__(
        self,
        solvers: tuple[OfficialSolver, ...] | list[OfficialSolver] | None = None,
        evaluator: OfficialEvaluator | None = None,
        time_limit_sec: float = 9.0,
    ) -> None:
        self.solvers = tuple(solvers or default_official_solvers())
        self.evaluator = evaluator or OfficialEvaluator()
        self.time_limit_sec = time_limit_sec

    def solve(self, instance: OfficialInstance) -> OfficialReport:
        start = time.perf_counter()
        deadline = start + self.time_limit_sec
        best = OfficialAssignment.empty()
        best_objective = self.evaluator.evaluate(instance, best)
        best_solver = "empty"
        runs: list[OfficialRun] = []
        for solver in self.solvers:
            if expired(deadline):
                break
            solver_start = time.perf_counter()
            try:
                assignment = solver.solve(instance, self.evaluator, deadline)
                objective = self.evaluator.evaluate(instance, assignment)
                elapsed = time.perf_counter() - solver_start
                runs.append(OfficialRun(solver.name, elapsed, objective))
                if self.evaluator.better(objective, best_objective):
                    best = assignment
                    best_objective = objective
                    best_solver = solver.name
            except Exception as exc:  # pragma: no cover - defensive portfolio isolation
                runs.append(OfficialRun(solver.name, time.perf_counter() - solver_start, None, repr(exc)))
        return OfficialReport(best, best_objective, best_solver, time.perf_counter() - start, tuple(runs))


def parse_official_input(input_text: str) -> OfficialInstance:
    candidates: list[OfficialCandidate] = []
    lines = input_text.splitlines()
    start = 0
    if lines and lines[0].lstrip("\ufeff").startswith("task_id_list"):
        start = 1
    for line in lines[start:]:
        if not line.strip():
            continue
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 4:
            continue
        task_key = ",".join(part.strip() for part in parts[0].strip().split(",") if part.strip())
        tasks = tuple(task_key.split(",")) if task_key else ()
        if not tasks:
            continue
        try:
            total_score = float(parts[2])
            willingness = float(parts[3])
        except ValueError:
            continue
        candidates.append(
            OfficialCandidate(
                task_key=task_key,
                tasks=tasks,
                courier_id=parts[1].strip(),
                total_score=total_score,
                willingness=willingness,
            )
        )
    return OfficialInstance.from_candidates(candidates)


def solve(input_text: str) -> list[tuple[str, list[str]]]:
    instance = parse_official_input(input_text)
    report = OfficialPortfolioSolver(time_limit_sec=9.0).solve(instance)
    return report.assignment.to_result()


def default_official_solvers() -> list[OfficialSolver]:
    return [
        OfficialGreedySolver("official_score_greedy", "score"),
        OfficialGreedySolver("official_score_per_task", "score_per_task"),
        OfficialGreedySolver("official_willingness", "willingness"),
        OfficialGreedySolver("official_score_minus_10w", "score_minus_willingness", willingness_weight=10.0),
        OfficialGreedySolver("official_score_minus_25w", "score_minus_willingness", willingness_weight=25.0),
        OfficialGreedySolver("official_score_per_expected", "score_per_expected"),
        OfficialGreedySolver("official_pair_first_score", "pair_first_score"),
        OfficialGreedySolver("official_score_multi2", "score", max_offers_per_bundle=2, min_marginal_gain=0.01),
        OfficialGreedySolver("official_expected_multi3", "score_per_expected", max_offers_per_bundle=3, min_marginal_gain=0.01),
        OfficialGreedySolver("official_willing_multi3", "willingness", max_offers_per_bundle=3, min_marginal_gain=0.01),
    ]


def acceptance_probability(probabilities: Iterable[float]) -> float:
    miss_probability = 1.0
    for probability in probabilities:
        miss_probability *= 1.0 - max(0.0, min(1.0, probability))
    return 1.0 - miss_probability


def expired(deadline: float | None) -> bool:
    return deadline is not None and time.perf_counter() >= deadline


def choose_disjoint_candidates(
    instance: OfficialInstance,
    ordered_candidates: Iterable[OfficialCandidate],
    deadline: float | None,
) -> dict[tuple[str, ...], tuple[str, list[str]]]:
    selected: dict[tuple[str, ...], tuple[str, list[str]]] = {}
    covered_tasks: set[str] = set()
    used_couriers: set[str] = set()
    for candidate in ordered_candidates:
        if expired(deadline):
            break
        task_set = candidate.task_set
        if candidate.courier_id in used_couriers:
            continue
        if any(task_id in covered_tasks for task_id in task_set):
            continue
        selected[task_set] = (candidate.task_key, [candidate.courier_id])
        covered_tasks.update(task_set)
        used_couriers.add(candidate.courier_id)
        if len(covered_tasks) == len(instance.task_ids):
            break
    return selected


def expand_multi_offers(
    instance: OfficialInstance,
    selected: dict[tuple[str, ...], tuple[str, list[str]]],
    max_offers_per_bundle: int,
    min_marginal_gain: float,
    deadline: float | None,
) -> dict[tuple[str, ...], tuple[str, list[str]]]:
    expanded = {task_set: (task_key, list(couriers)) for task_set, (task_key, couriers) in selected.items()}
    used_couriers = {courier_id for _, couriers in expanded.values() for courier_id in couriers}
    miss_probability = {
        task_set: 1.0 - acceptance_probability(
            instance.candidate(task_key, courier_id).willingness
            for courier_id in couriers
            if instance.candidate(task_key, courier_id) is not None
        )
        for task_set, (task_key, couriers) in expanded.items()
    }
    ranked: list[tuple[float, float, OfficialCandidate]] = []
    for task_set, (task_key, couriers) in expanded.items():
        for candidate in instance.candidates_for_task_set(task_set):
            if candidate.courier_id in couriers:
                continue
            gain = len(task_set) * miss_probability[task_set] * candidate.willingness
            if gain >= min_marginal_gain:
                ranked.append((-gain / max(candidate.total_score, 1e-9), candidate.total_score, candidate))
    for _, _, candidate in sorted(ranked):
        if expired(deadline):
            break
        task_set = candidate.task_set
        task_key, couriers = expanded[task_set]
        if len(couriers) >= max_offers_per_bundle:
            continue
        if candidate.courier_id in used_couriers:
            continue
        gain = len(task_set) * miss_probability[task_set] * candidate.willingness
        if gain < min_marginal_gain:
            continue
        couriers.append(candidate.courier_id)
        used_couriers.add(candidate.courier_id)
        miss_probability[task_set] *= 1.0 - candidate.willingness
    return expanded


def assignment_from_selected(selected: dict[tuple[str, ...], tuple[str, list[str]]]) -> OfficialAssignment:
    offers = [
        OfficialOffer(task_key, tuple(couriers))
        for _, (task_key, couriers) in sorted(selected.items(), key=lambda item: item[1][0])
        if couriers
    ]
    return OfficialAssignment(tuple(offers))


def best_assignment(
    instance: OfficialInstance,
    evaluator: OfficialEvaluator,
    assignments: Iterable[OfficialAssignment],
) -> tuple[OfficialAssignment, OfficialObjective]:
    best = OfficialAssignment.empty()
    best_objective = evaluator.evaluate(instance, best)
    for assignment in assignments:
        objective = evaluator.evaluate(instance, assignment)
        if evaluator.better(objective, best_objective):
            best = assignment
            best_objective = objective
    return best, best_objective


def repair_with_candidate(
    instance: OfficialInstance,
    assignment: OfficialAssignment,
    candidate: OfficialCandidate,
) -> OfficialAssignment:
    candidate_tasks = set(candidate.task_set)
    offers: list[OfficialOffer] = []
    used_couriers: set[str] = {candidate.courier_id}
    for offer in assignment.offers:
        offer_candidate = instance.candidate(offer.task_key, offer.courier_ids[0]) if offer.courier_ids else None
        if offer_candidate is None:
            continue
        if candidate_tasks.intersection(offer_candidate.task_set):
            continue
        if candidate.courier_id in offer.courier_ids:
            continue
        kept_couriers = tuple(courier_id for courier_id in offer.courier_ids if courier_id not in used_couriers)
        if kept_couriers:
            offers.append(OfficialOffer(offer.task_key, kept_couriers))
            used_couriers.update(kept_couriers)
    offers.append(OfficialOffer(candidate.task_key, (candidate.courier_id,)))
    covered = {task_id for offer in offers for task_id in offer.task_key.split(",")}
    for filler in sorted(instance.candidates, key=lambda item: item.total_score):
        if set(filler.tasks).intersection(covered):
            continue
        if filler.courier_id in used_couriers:
            continue
        offers.append(OfficialOffer(filler.task_key, (filler.courier_id,)))
        covered.update(filler.tasks)
        used_couriers.add(filler.courier_id)
        if len(covered) == len(instance.task_ids):
            break
    return OfficialAssignment(tuple(sorted(offers, key=lambda offer: offer.task_key)))
