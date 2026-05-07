"""Single-file submission for the AutoSolver challenge.

This file is written for old Python 3 runtimes, including Python 3.5/3.6:
no dataclasses, no f-strings, no external packages, and no network calls.

The judge should call:

    solve(input_text: str) -> list
"""

import time


class Candidate(object):
    __slots__ = ("task_key", "tasks", "courier_id", "score", "willingness")

    def __init__(self, task_key, tasks, courier_id, score, willingness):
        self.task_key = task_key
        self.tasks = tasks
        self.courier_id = courier_id
        self.score = score
        self.willingness = willingness

    @property
    def task_set(self):
        return tuple(sorted(self.tasks))


class Instance(object):
    __slots__ = ("candidates", "task_ids", "by_offer", "by_task_set")

    def __init__(self, candidates, task_ids, by_offer, by_task_set):
        self.candidates = candidates
        self.task_ids = task_ids
        self.by_offer = by_offer
        self.by_task_set = by_task_set


def solve(input_text: str) -> list:
    """Contest entrypoint: return [(task_id_list_str, [courier_id, ...]), ...]."""

    instance = parse_input(input_text)
    selected = portfolio_solve(instance, 9.0)
    return assignment_to_result(selected)


def parse_input(input_text):
    candidates = []
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
        task_key = ",".join([part.strip() for part in parts[0].strip().split(",") if part.strip()])
        if not task_key:
            continue
        try:
            score = float(parts[2])
            willingness = float(parts[3])
        except ValueError:
            continue
        candidates.append(Candidate(task_key, tuple(task_key.split(",")), parts[1].strip(), score, willingness))

    by_offer = {}
    grouped = {}
    task_set_all = set()
    for candidate in candidates:
        by_offer[(candidate.task_key, candidate.courier_id)] = candidate
        grouped.setdefault(candidate.task_set, []).append(candidate)
        for task_id in candidate.tasks:
            task_set_all.add(task_id)

    by_task_set = {}
    for key, value in grouped.items():
        by_task_set[key] = tuple(value)

    return Instance(tuple(candidates), tuple(sorted(task_set_all)), by_offer, by_task_set)


def portfolio_solve(instance, time_limit_sec):
    deadline = time.perf_counter() + time_limit_sec
    best = {}
    best_obj = evaluate(instance, best)

    strategies = (
        (lambda c: (c.score, c.task_key, c.courier_id), 1, 0.0),
        (lambda c: (c.score / len(c.tasks), c.score, c.task_key, c.courier_id), 1, 0.0),
        (lambda c: (-c.willingness, c.score, c.task_key, c.courier_id), 1, 0.0),
        (lambda c: (c.score - 10.0 * len(c.tasks) * c.willingness, c.score, c.task_key), 1, 0.0),
        (lambda c: (c.score - 25.0 * len(c.tasks) * c.willingness, c.score, c.task_key), 1, 0.0),
        (lambda c: (c.score / max(len(c.tasks) * c.willingness, 1e-9), c.score, c.task_key), 1, 0.0),
        (lambda c: (-len(c.tasks), c.score, c.task_key, c.courier_id), 1, 0.0),
        (lambda c: (c.score, c.task_key, c.courier_id), 2, 0.01),
        (lambda c: (c.score / max(len(c.tasks) * c.willingness, 1e-9), c.score, c.task_key), 3, 0.01),
        (lambda c: (-c.willingness, c.score, c.task_key, c.courier_id), 3, 0.01),
        (lambda c: (c.score - 25.0 * len(c.tasks) * c.willingness, c.score, c.task_key), 2, 0.01),
    )

    for key_func, max_offers, min_gain in strategies:
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


def choose_disjoint(instance, ordered_candidates, deadline):
    selected = {}
    covered_tasks = set()
    used_couriers = set()
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


def expand_multi_offers(instance, selected, max_offers_per_bundle, min_marginal_gain, deadline):
    expanded = {}
    for task_set, value in selected.items():
        expanded[task_set] = (value[0], list(value[1]))

    used_couriers = set()
    for _, couriers in expanded.values():
        used_couriers.update(couriers)

    miss_probability = {}
    for task_set, value in expanded.items():
        task_key, couriers = value
        probabilities = []
        for courier_id in couriers:
            candidate = instance.by_offer.get((task_key, courier_id))
            if candidate is not None:
                probabilities.append(candidate.willingness)
        miss_probability[task_set] = 1.0 - acceptance_probability(probabilities)

    ranked = []
    for task_set, value in expanded.items():
        _, couriers = value
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


def evaluate(instance, selected):
    used_couriers = set()
    covered_tasks = set()
    expected = 0.0
    total_score = 0.0
    offer_count = 0
    feasible = True

    for task_set, value in selected.items():
        task_key, couriers = value
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


def better(candidate_obj, incumbent_obj):
    return candidate_obj > incumbent_obj


def assignment_to_result(selected):
    result = []
    for _, value in sorted(selected.items(), key=lambda item: item[1][0]):
        task_key, couriers = value
        if couriers:
            result.append((task_key, list(couriers)))
    return result


def acceptance_probability(probabilities):
    miss = 1.0
    for probability in probabilities:
        if probability < 0.0:
            probability = 0.0
        elif probability > 1.0:
            probability = 1.0
        miss *= 1.0 - probability
    return 1.0 - miss


def expired(deadline):
    return time.perf_counter() >= deadline
