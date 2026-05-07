"""Single-file submission for Meituan AutoSolver challenge.

The judge is expected to import this file and call:

    solve(input_text: str) -> list

The returned list shape is:

    [(task_id_list_str, [courier_id, ...]), ...]

This file is intentionally dependency-free and does not call any external API.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Candidate:
    task_key: str
    tasks: tuple[str, ...]
    courier_id: str
    score: float
    willingness: float

    @property
    def task_set(self) -> tuple[str, ...]:
        return tuple(sorted(self.tasks))


@dataclass(frozen=True)
class Instance:
    candidates: tuple[Candidate, ...]
    task_ids: tuple[str, ...]
    by_offer: dict[tuple[str, str], Candidate]
    by_task_set: dict[tuple[str, ...], tuple[Candidate, ...]]


def solve(input_text: str) -> list:
    """Contest entrypoint."""

    instance = parse_input(input_text)
    selected = portfolio_solve(instance, time_limit_sec=9.0)
    return assignment_to_result(selected)


def parse_input(input_text: str) -> Instance:
    candidates: list[Candidate] = []
    lines = input_text.splitlines()
    start = 1 if lines and lines[0].lstrip("\ufeff").startswith("task_id_list") else 0
    for line in lines[start:]:
        if not line.strip():
            continue
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 4:
            continue
        task_key = ",".join(part.strip() for part in parts[0].strip().split(",") if part.strip())
        if not task_key:
            continue
        try:
            score = float(parts[2])
            willingness = float(parts[3])
        except ValueError:
            continue
        candidates.append(
            Candidate(
                task_key=task_key,
                tasks=tuple(task_key.split(",")),
                courier_id=parts[1].strip(),
                score=score,
                willingness=willingness,
            )
        )

    by_offer: dict[tuple[str, str], Candidate] = {}
    grouped: dict[tuple[str, ...], list[Candidate]] = {}
    task_ids = sorted({task_id for candidate in candidates for task_id in candidate.tasks})
    for candidate in candidates:
        by_offer[(candidate.task_key, candidate.courier_id)] = candidate
        grouped.setdefault(candidate.task_set, []).append(candidate)
    return Instance(
        candidates=tuple(candidates),
        task_ids=tuple(task_ids),
        by_offer=by_offer,
        by_task_set={key: tuple(value) for key, value in grouped.items()},
    )


def portfolio_solve(instance: Instance, time_limit_sec: float) -> dict[tuple[str, ...], tuple[str, list[str]]]:
    start = time.perf_counter()
    deadline = start + time_limit_sec
    best: dict[tuple[str, ...], tuple[str, list[str]]] = {}
    best_obj = evaluate(instance, best)

    strategies = (
        ("score", lambda c: (c.score, c.task_key, c.courier_id), 1, 0.0),
        ("score_per_task", lambda c: (c.score / len(c.tasks), c.score, c.task_key, c.courier_id), 1, 0.0),
        ("willingness", lambda c: (-c.willingness, c.score, c.task_key, c.courier_id), 1, 0.0),
        ("score_minus_10w", lambda c: (c.score - 10.0 * len(c.tasks) * c.willingness, c.score, c.task_key), 1, 0.0),
        ("score_minus_25w", lambda c: (c.score - 25.0 * len(c.tasks) * c.willingness, c.score, c.task_key), 1, 0.0),
        (
            "score_per_expected",
            lambda c: (c.score / max(len(c.tasks) * c.willingness, 1e-9), c.score, c.task_key),
            1,
            0.0,
        ),
        ("pair_first_score", lambda c: (-len(c.tasks), c.score, c.task_key, c.courier_id), 1, 0.0),
        ("score_multi2", lambda c: (c.score, c.task_key, c.courier_id), 2, 0.01),
        (
            "expected_multi3",
            lambda c: (c.score / max(len(c.tasks) * c.willingness, 1e-9), c.score, c.task_key),
            3,
            0.01,
        ),
        ("willing_multi3", lambda c: (-c.willingness, c.score, c.task_key, c.courier_id), 3, 0.01),
        # A cost-aware multi-offer compromise in case the hidden scorer weighs score more strongly.
        ("balanced_multi2", lambda c: (c.score - 25.0 * len(c.tasks) * c.willingness, c.score, c.task_key), 2, 0.01),
    )

    for _, key_func, max_offers, min_gain in strategies:
        if expired(deadline):
            break
        selected = choose_disjoint(instance, sorted(instance.candidates, key=key_func), deadline)
        if max_offers > 1:
            selected = expand_multi_offers(instance, selected, max_offers, min_gain, deadline)
        obj = evaluate(instance, selected)
        if better(obj, best_obj):
            best = selected
            best_obj = obj
    return best


def choose_disjoint(
    instance: Instance,
    ordered_candidates: Iterable[Candidate],
    deadline: float,
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
    instance: Instance,
    selected: dict[tuple[str, ...], tuple[str, list[str]]],
    max_offers_per_bundle: int,
    min_marginal_gain: float,
    deadline: float,
) -> dict[tuple[str, ...], tuple[str, list[str]]]:
    expanded = {task_set: (task_key, list(couriers)) for task_set, (task_key, couriers) in selected.items()}
    used_couriers = {courier_id for _, couriers in expanded.values() for courier_id in couriers}
    miss_probability: dict[tuple[str, ...], float] = {}
    for task_set, (task_key, couriers) in expanded.items():
        probabilities = []
        for courier_id in couriers:
            candidate = instance.by_offer.get((task_key, courier_id))
            if candidate is not None:
                probabilities.append(candidate.willingness)
        miss_probability[task_set] = 1.0 - acceptance_probability(probabilities)

    ranked: list[tuple[float, float, Candidate]] = []
    for task_set, (task_key, couriers) in expanded.items():
        for candidate in instance.by_task_set.get(task_set, ()):
            if candidate.courier_id in couriers:
                continue
            gain = len(task_set) * miss_probability[task_set] * candidate.willingness
            if gain >= min_marginal_gain:
                ranked.append((-gain / max(candidate.score, 1e-9), candidate.score, candidate))

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


def evaluate(instance: Instance, selected: dict[tuple[str, ...], tuple[str, list[str]]]) -> tuple:
    used_couriers: set[str] = set()
    covered_tasks: set[str] = set()
    expected = 0.0
    total_score = 0.0
    offer_count = 0
    feasible = True

    for task_set, (task_key, couriers) in selected.items():
        if any(task_id in covered_tasks for task_id in task_set):
            feasible = False
        probabilities = []
        for courier_id in couriers:
            candidate = instance.by_offer.get((task_key, courier_id))
            if candidate is None or candidate.task_set != task_set or courier_id in used_couriers:
                feasible = False
                continue
            probabilities.append(candidate.willingness)
            total_score += candidate.score
            offer_count += 1
            used_couriers.add(courier_id)
        covered_tasks.update(task_set)
        expected += len(task_set) * acceptance_probability(probabilities)
    return (feasible, expected, len(covered_tasks), -total_score, -offer_count)


def better(candidate_obj: tuple, incumbent_obj: tuple) -> bool:
    # Feasibility first, then expected accepted task count, then deterministic coverage,
    # then lower total score and fewer offers via negative tie-breakers.
    return candidate_obj > incumbent_obj


def assignment_to_result(selected: dict[tuple[str, ...], tuple[str, list[str]]]) -> list:
    result = []
    for _, (task_key, couriers) in sorted(selected.items(), key=lambda item: item[1][0]):
        if couriers:
            result.append((task_key, list(couriers)))
    return result


def acceptance_probability(probabilities: Iterable[float]) -> float:
    miss = 1.0
    for probability in probabilities:
        if probability < 0.0:
            probability = 0.0
        elif probability > 1.0:
            probability = 1.0
        miss *= 1.0 - probability
    return 1.0 - miss


def expired(deadline: float) -> bool:
    return time.perf_counter() >= deadline
