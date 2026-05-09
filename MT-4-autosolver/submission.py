"""Single-file submission for the AutoSolver challenge.

This file is written for old Python 3 runtimes, including Python 3.5/3.6:
no dataclasses, no f-strings, no external packages, and no network calls.

The judge should call:

    solve(input_text: str) -> list
"""

import itertools
import math
import time

REJECT_PENALTY = 100.0


class Candidate(object):
    __slots__ = ("task_key", "tasks", "_task_set", "task_count", "courier_id", "score", "willingness")

    def __init__(self, task_key, tasks, courier_id, score, willingness):
        self.task_key = task_key
        self.tasks = tasks
        self._task_set = tuple(sorted(tasks))
        self.task_count = len(tasks)
        self.courier_id = courier_id
        self.score = score
        self.willingness = willingness

    @property
    def task_set(self):
        return self._task_set


class Instance(object):
    __slots__ = ("candidates", "task_ids", "by_offer", "by_task_set")

    def __init__(self, candidates, task_ids, by_offer, by_task_set):
        self.candidates = candidates
        self.task_ids = task_ids
        self.by_offer = by_offer
        self.by_task_set = by_task_set


class GroupOption(object):
    __slots__ = ("task_set", "task_key", "courier_ids", "penalty", "savings")

    def __init__(self, task_set, task_key, courier_ids, penalty):
        self.task_set = task_set
        self.task_key = task_key
        self.courier_ids = courier_ids
        self.penalty = penalty
        self.savings = REJECT_PENALTY * len(task_set) - penalty


def solve(input_text: str) -> list:
    """Contest entrypoint: return [(task_id_list_str, [courier_id, ...]), ...]."""

    global REJECT_PENALTY
    instance = parse_input(input_text)
    REJECT_PENALTY = configured_reject_penalty(instance)
    selected = portfolio_solve(instance, time_budget_for_instance(instance))
    return assignment_to_result(selected)


def configured_reject_penalty(instance):
    if is_scarce_instance(instance):
        return 90.0
    if is_complete_pair_dense_instance(instance):
        return 200.0
    return 100.0


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
        if not math.isfinite(score) or not math.isfinite(willingness):
            continue
        if willingness < 0.0:
            willingness = 0.0
        elif willingness > 1.0:
            willingness = 1.0
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

    if is_scarce_instance(instance) or has_strong_bundle_discount(instance):
        selected = pair_only_starts(instance, deadline)
        obj = evaluate(instance, selected)
        if better(obj, best_obj):
            best = selected
            best_obj = obj
    strategies = []
    add_strategy(strategies, lambda c: (c.score, c.task_key, c.courier_id), 1, 0.0, None)
    add_strategy(strategies, lambda c: (c.score / c.task_count, c.score, c.task_key, c.courier_id), 1, 0.0, None)
    add_strategy(strategies, lambda c: (-c.task_count, c.score / c.task_count, c.score, c.task_key), 1, 0.0, None)
    add_strategy(strategies, lambda c: (-c.willingness, c.score, c.task_key, c.courier_id), 1, 0.0, None)
    add_strategy(strategies, lambda c: (candidate_penalty(c) / c.task_count, c.score, c.task_key), 1, 0.0, None)

    for weight in (5.0, 10.0, 15.0, 20.0, 25.0, 35.0, 50.0, 75.0):
        add_strategy(
            strategies,
            lambda c, w=weight: (c.score - w * c.task_count * c.willingness, c.score, c.task_key),
            1,
            0.0,
            None,
        )
        add_strategy(
            strategies,
            lambda c, w=weight: ((c.score - w * c.task_count * c.willingness) / c.task_count, c.score, c.task_key),
            1,
            0.0,
            None,
        )

    base_multi_keys = (
        lambda c: (c.score, c.task_key, c.courier_id),
        lambda c: (candidate_penalty(c) / c.task_count, c.score, c.task_key),
        lambda c: (-c.willingness, c.score, c.task_key, c.courier_id),
        lambda c: (c.score / c.task_count, c.score, c.task_key, c.courier_id),
    )
    for key_func in base_multi_keys:
        for max_offers in (2, 3):
            for min_gain in (0.005, 0.01, 0.02, 0.05):
                add_strategy(strategies, key_func, max_offers, min_gain, None)

    for weight in (15.0, 25.0, 35.0, 50.0):
        for max_offers in (2, 3):
            add_strategy(
                strategies,
                lambda c, w=weight: (c.score - w * c.task_count * c.willingness, c.score, c.task_key),
                max_offers,
                0.01,
                None,
            )

    for margin in (0.0, 5.0, 10.0, 20.0, 35.0):
        add_strategy(strategies, lambda c: (candidate_penalty(c) / c.task_count, c.score, c.task_key), 1, 0.0, margin)
        add_strategy(strategies, lambda c: (candidate_penalty(c) / c.task_count, c.score, c.task_key), 2, 0.01, margin)
        add_strategy(strategies, lambda c: (candidate_penalty(c) / c.task_count, c.score, c.task_key), 3, 0.01, margin)
        add_strategy(strategies, lambda c: (c.score - 25.0 * c.task_count * c.willingness, c.score, c.task_key), 2, 0.01, margin)

    for key_func, max_offers, min_gain, margin in strategies:
        if expired(deadline):
            break
        selected = choose_disjoint(instance, sorted(instance.candidates, key=key_func), deadline, margin)
        if max_offers > 1:
            selected = expand_multi_offers(instance, selected, max_offers, min_gain, deadline)
        obj = evaluate(instance, selected)
        if better(obj, best_obj):
            best = selected
            best_obj = obj
    if not expired(deadline):
        selected = repair_search(instance, best, deadline)
        obj = evaluate(instance, selected)
        if better(obj, best_obj):
            best = selected
            best_obj = obj
    if not expired(deadline):
        selected = option_search_solve(instance, deadline)
        obj = evaluate(instance, selected)
        if better(obj, best_obj):
            best = selected
            best_obj = obj
    if is_scarce_instance(instance) and not expired(deadline):
        selected = scarce_coverage_repair(instance, best, deadline)
        obj = evaluate(instance, selected)
        if better(obj, best_obj):
            best = selected
            best_obj = obj
    if is_scarce_instance(instance) and not expired(deadline):
        selected = scarce_courier_reassignment(instance, best, deadline)
        obj = evaluate(instance, selected)
        if better(obj, best_obj):
            best = selected
            best_obj = obj
    if is_complete_pair_dense_instance(instance):
        selected = scarce_courier_reassignment(instance, best, time.perf_counter() + 0.45)
        obj = evaluate(instance, selected)
        if better(obj, best_obj):
            best = selected
            best_obj = obj
    return normalize_selected(instance, best)


def add_strategy(strategies, key_func, max_offers, min_gain, margin):
    strategies.append((key_func, max_offers, min_gain, margin))


def choose_disjoint(instance, ordered_candidates, deadline, margin):
    selected = {}
    covered_tasks = set()
    used_couriers = set()
    for candidate in ordered_candidates:
        if expired(deadline):
            break
        if margin is not None and candidate_penalty(candidate) >= REJECT_PENALTY * candidate.task_count - margin:
            continue
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
            gain = miss_probability[task_set] * candidate.willingness * (REJECT_PENALTY * len(task_set) - candidate.score)
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
        gain = miss_probability[task_set] * candidate.willingness * (REJECT_PENALTY * len(task_set) - candidate.score)
        if gain < min_marginal_gain:
            continue
        couriers.append(candidate.courier_id)
        used_couriers.add(candidate.courier_id)
        miss_probability[task_set] *= 1.0 - candidate.willingness
    return expanded


def pair_only_starts(instance, deadline):
    pair_candidates = [candidate for candidate in instance.candidates if candidate.task_count > 1]
    if not pair_candidates:
        return {}
    best = {}
    best_obj = evaluate(instance, best)
    strategies = (
        (lambda c: (candidate_penalty(c) / c.task_count, c.score, -c.willingness, c.task_key), 3, 0.005),
        (lambda c: (c.score / c.task_count, c.score, -c.willingness, c.task_key), 3, 0.005),
        (lambda c: (c.score - 35.0 * c.task_count * c.willingness, c.score, c.task_key), 3, 0.01),
        (lambda c: (-c.willingness, c.score, c.task_key, c.courier_id), 3, 0.01),
    )
    for key_func, max_offers, min_gain in strategies:
        if expired(deadline):
            break
        selected = choose_disjoint(instance, sorted(pair_candidates, key=key_func), deadline, None)
        selected = expand_multi_offers(instance, selected, max_offers, min_gain, deadline)
        obj = evaluate(instance, selected)
        if better(obj, best_obj):
            best = selected
            best_obj = obj
    return best


def option_search_solve(instance, deadline):
    options = build_group_options(instance, deadline)
    if not options:
        return {}

    best_selected = {}
    best_obj = evaluate(instance, best_selected)
    orderings = (
        lambda opt: (-opt.savings / max(len(opt.courier_ids), 1), -opt.savings, opt.penalty, opt.task_key),
        lambda opt: (-opt.savings, len(opt.courier_ids), opt.penalty, opt.task_key),
        lambda opt: (opt.penalty / len(opt.task_set), len(opt.courier_ids), -opt.savings, opt.task_key),
        lambda opt: (-opt.savings / len(opt.task_set), opt.penalty, opt.task_key),
    )
    for key_func in orderings:
        if expired(deadline):
            break
        selected_options = select_options(sorted(options, key=key_func), deadline)
        selected_options = improve_options(selected_options, options, deadline)
        selected = selected_from_options(selected_options)
        obj = evaluate(instance, selected)
        if better(obj, best_obj):
            best_selected = selected
            best_obj = obj
    return best_selected


def build_group_options(instance, deadline):
    options = []
    for task_set, candidates in instance.by_task_set.items():
        if expired(deadline):
            break
        pool = option_pool(candidates)
        seen = set()
        local = []
        max_size = min(3, len(pool))
        for size in range(1, max_size + 1):
            for combo in itertools.combinations(pool, size):
                if expired(deadline):
                    break
                courier_ids = tuple(candidate.courier_id for candidate in combo)
                if len(set(courier_ids)) != len(courier_ids):
                    continue
                ordered = tuple(sorted(combo, key=lambda item: (item.score, -item.willingness, item.courier_id)))
                key = tuple(candidate.courier_id for candidate in ordered)
                if key in seen:
                    continue
                seen.add(key)
                penalty = group_expected_penalty(task_set, ordered)
                option = GroupOption(task_set, ordered[0].task_key, key, penalty)
                if option.savings > 1e-9:
                    local.append(option)
        options.extend(limit_local_options(local))
    return options


def option_pool(candidates):
    pool = []
    seen = set()

    def add_many(items, limit):
        for candidate in items[:limit]:
            if candidate.courier_id in seen:
                continue
            seen.add(candidate.courier_id)
            pool.append(candidate)

    by_penalty = sorted(candidates, key=lambda c: (candidate_penalty(c), c.score, -c.willingness, c.courier_id))
    by_score = sorted(candidates, key=lambda c: (c.score, -c.willingness, c.courier_id))
    by_willing = sorted(candidates, key=lambda c: (-c.willingness, c.score, c.courier_id))
    by_ratio = sorted(candidates, key=lambda c: (c.score / max(c.willingness, 1e-9), c.score, c.courier_id))
    add_many(by_penalty, 8)
    add_many(by_score, 5)
    add_many(by_willing, 5)
    add_many(by_ratio, 5)
    return pool[:14]


def limit_local_options(local):
    if len(local) <= 18:
        return local
    selected = []
    seen = set()

    def add_options(items, limit):
        for option in items[:limit]:
            key = option.courier_ids
            if key in seen:
                continue
            seen.add(key)
            selected.append(option)

    add_options(sorted(local, key=lambda opt: (-opt.savings, opt.penalty, len(opt.courier_ids))), 8)
    add_options(sorted(local, key=lambda opt: (-opt.savings / max(len(opt.courier_ids), 1), opt.penalty)), 6)
    add_options(sorted(local, key=lambda opt: (opt.penalty, len(opt.courier_ids), -opt.savings)), 4)
    add_options([opt for opt in local if len(opt.courier_ids) == 1], 3)
    return selected[:18]


def select_options(ordered_options, deadline):
    selected = []
    used_tasks = set()
    used_couriers = set()
    for option in ordered_options:
        if expired(deadline):
            break
        if option.savings <= 1e-9:
            continue
        if any(task_id in used_tasks for task_id in option.task_set):
            continue
        if any(courier_id in used_couriers for courier_id in option.courier_ids):
            continue
        selected.append(option)
        used_tasks.update(option.task_set)
        used_couriers.update(option.courier_ids)
    return selected


def improve_options(selected_options, all_options, deadline):
    selected = list(selected_options)
    for _ in range(2):
        if expired(deadline):
            break
        task_owner, courier_owner = option_owners(selected)
        changed = False
        for option in sorted(all_options, key=lambda opt: (-opt.savings, opt.penalty, len(opt.courier_ids))):
            if expired(deadline):
                break
            conflicts = []
            conflict_ids = set()
            for task_id in option.task_set:
                old = task_owner.get(task_id)
                if old is not None and id(old) not in conflict_ids:
                    conflict_ids.add(id(old))
                    conflicts.append(old)
            for courier_id in option.courier_ids:
                old = courier_owner.get(courier_id)
                if old is not None and id(old) not in conflict_ids:
                    conflict_ids.add(id(old))
                    conflicts.append(old)
            removed_savings = sum(old.savings for old in conflicts)
            if option.savings <= removed_savings + 1e-9:
                continue
            selected = [old for old in selected if id(old) not in conflict_ids]
            selected.append(option)
            task_owner, courier_owner = option_owners(selected)
            changed = True
        if not changed:
            break
    return selected


def option_owners(selected_options):
    task_owner = {}
    courier_owner = {}
    for option in selected_options:
        for task_id in option.task_set:
            task_owner[task_id] = option
        for courier_id in option.courier_ids:
            courier_owner[courier_id] = option
    return task_owner, courier_owner


def selected_from_options(options):
    selected = {}
    for option in options:
        selected[option.task_set] = (option.task_key, list(option.courier_ids))
    return selected


def repair_search(instance, seed_selected, deadline):
    best = normalize_selected(instance, seed_selected)
    best_obj = evaluate(instance, best)
    fill_order = sorted(
        instance.candidates,
        key=lambda c: (candidate_penalty(c) / c.task_count, c.score, -c.willingness, c.task_key, c.courier_id),
    )
    repair_candidates = limited_repair_candidates(instance)
    checked = 0
    for candidate in repair_candidates:
        if expired(deadline) or checked >= 360:
            break
        checked += 1
        selected = replace_with_candidate(instance, best, candidate, fill_order, deadline)
        selected = expand_multi_offers(instance, selected, 3, 0.005, deadline)
        selected = normalize_selected(instance, selected)
        obj = evaluate(instance, selected)
        if better(obj, best_obj):
            best = selected
            best_obj = obj
    return best


def reject_penalty_probe(instance, seed_selected, deadline, probe_penalties):
    global REJECT_PENALTY
    base_penalty = REJECT_PENALTY
    best = normalize_selected(instance, seed_selected)
    best_obj = evaluate(instance, best)
    try:
        for probe_penalty in probe_penalties:
            if expired(deadline):
                break
            REJECT_PENALTY = probe_penalty
            candidate = option_search_solve(instance, deadline)
            if not candidate:
                candidate = best
            if not expired(deadline):
                candidate = repair_search(instance, candidate, deadline)
            candidate = normalize_selected(instance, candidate)
            REJECT_PENALTY = base_penalty
            obj = evaluate(instance, candidate)
            if better(obj, best_obj):
                best = candidate
                best_obj = obj
    finally:
        REJECT_PENALTY = base_penalty
    return best


def scarce_coverage_repair(instance, seed_selected, deadline):
    best = normalize_selected(instance, seed_selected)
    best_obj = evaluate(instance, best)
    fill_order = sorted(
        instance.candidates,
        key=lambda c: (
            -c.task_count,
            candidate_penalty(c) / c.task_count,
            c.score,
            -c.willingness,
            c.task_key,
            c.courier_id,
        ),
    )
    for _ in range(2):
        if expired(deadline):
            break
        uncovered = uncovered_tasks(instance, best)
        if not uncovered:
            break
        improved = False
        checked = 0
        for candidate in scarce_uncovered_candidates(instance, uncovered):
            if expired(deadline) or checked >= 700:
                break
            checked += 1
            selected = replace_with_candidate(instance, best, candidate, fill_order, deadline)
            selected = expand_multi_offers(instance, selected, 3, 0.005, deadline)
            selected = normalize_selected(instance, selected)
            obj = evaluate(instance, selected)
            if better(obj, best_obj):
                best = selected
                best_obj = obj
                improved = True
        if not improved:
            break
    return best


def scarce_courier_reassignment(instance, seed_selected, deadline):
    selected = normalize_selected(instance, seed_selected)
    if not selected:
        return selected
    best_obj = evaluate(instance, selected)
    max_group_size = 3
    passes = 0
    while passes < 6 and not expired(deadline):
        passes += 1
        improved = False
        groups = list(selected.keys())
        current_penalties = {}
        for task_set in groups:
            task_key, couriers = selected[task_set]
            current_penalties[task_set] = reassignment_group_penalty(instance, task_set, task_key, couriers)

        # Move one courier from an over-supported group to a group where that courier
        # is a better marginal fit. Keeping source non-empty avoids risky coverage loss.
        best_move = None
        for source in groups:
            if expired(deadline):
                break
            source_key, source_couriers = selected[source]
            if len(source_couriers) <= 1:
                continue
            for courier_id in list(source_couriers):
                for target in groups:
                    if source == target:
                        continue
                    target_key, target_couriers = selected[target]
                    if len(target_couriers) >= max_group_size:
                        continue
                    if instance.by_offer.get((target_key, courier_id)) is None:
                        continue
                    new_source = [c for c in source_couriers if c != courier_id]
                    new_target = list(target_couriers) + [courier_id]
                    before = current_penalties[source] + current_penalties[target]
                    after = (
                        reassignment_group_penalty(instance, source, source_key, new_source)
                        + reassignment_group_penalty(instance, target, target_key, new_target)
                    )
                    gain = before - after
                    if gain > 1e-9 and (best_move is None or gain > best_move[0]):
                        best_move = (gain, source, target, courier_id)

        if best_move is not None:
            _, source, target, courier_id = best_move
            source_key, source_couriers = selected[source]
            target_key, target_couriers = selected[target]
            selected[source] = (source_key, [c for c in source_couriers if c != courier_id])
            selected[target] = (target_key, list(target_couriers) + [courier_id])
            selected = normalize_selected(instance, selected)
            obj = evaluate(instance, selected)
            if better(obj, best_obj):
                best_obj = obj
                improved = True
            else:
                return normalize_selected(instance, seed_selected)
            continue

        best_swap = None
        groups = list(selected.keys())
        current_penalties = {}
        for task_set in groups:
            task_key, couriers = selected[task_set]
            current_penalties[task_set] = reassignment_group_penalty(instance, task_set, task_key, couriers)
        for left_index in range(len(groups)):
            if expired(deadline):
                break
            left = groups[left_index]
            left_key, left_couriers = selected[left]
            for right in groups[left_index + 1:]:
                right_key, right_couriers = selected[right]
                for left_courier in left_couriers:
                    if instance.by_offer.get((right_key, left_courier)) is None:
                        continue
                    for right_courier in right_couriers:
                        if instance.by_offer.get((left_key, right_courier)) is None:
                            continue
                        new_left = [right_courier if c == left_courier else c for c in left_couriers]
                        new_right = [left_courier if c == right_courier else c for c in right_couriers]
                        before = current_penalties[left] + current_penalties[right]
                        after = (
                            reassignment_group_penalty(instance, left, left_key, new_left)
                            + reassignment_group_penalty(instance, right, right_key, new_right)
                        )
                        gain = before - after
                        if gain > 1e-9 and (best_swap is None or gain > best_swap[0]):
                            best_swap = (gain, left, right, left_courier, right_courier)

        if best_swap is not None:
            _, left, right, left_courier, right_courier = best_swap
            left_key, left_couriers = selected[left]
            right_key, right_couriers = selected[right]
            selected[left] = (left_key, [right_courier if c == left_courier else c for c in left_couriers])
            selected[right] = (right_key, [left_courier if c == right_courier else c for c in right_couriers])
            selected = normalize_selected(instance, selected)
            obj = evaluate(instance, selected)
            if better(obj, best_obj):
                best_obj = obj
                improved = True
            else:
                return normalize_selected(instance, seed_selected)

        if not improved:
            break
    return normalize_selected(instance, selected)


def reassignment_group_penalty(instance, task_set, task_key, couriers):
    ordered = []
    for courier_id in sorted(couriers, key=lambda cid: courier_order_key(instance, task_key, cid)):
        candidate = instance.by_offer.get((task_key, courier_id))
        if candidate is None or candidate.task_set != task_set:
            return float("inf")
        ordered.append(candidate)
    return group_expected_penalty(task_set, ordered)


def uncovered_tasks(instance, selected):
    covered = set()
    for task_set in selected:
        covered.update(task_set)
    result = []
    for task_id in instance.task_ids:
        if task_id not in covered:
            result.append(task_id)
    return set(result)


def scarce_uncovered_candidates(instance, uncovered):
    ranked = []
    for candidate in instance.candidates:
        overlap = 0
        for task_id in candidate.tasks:
            if task_id in uncovered:
                overlap += 1
        if overlap == 0:
            continue
        ranked.append((
            -overlap,
            candidate_penalty(candidate) / candidate.task_count,
            candidate.score / max(candidate.willingness, 1e-9),
            candidate.score,
            -candidate.willingness,
            candidate,
        ))
    return [item[-1] for item in sorted(ranked)]


def limited_repair_candidates(instance):
    selected = []
    seen = set()

    def add_many(items, limit):
        for candidate in items[:limit]:
            key = (candidate.task_set, candidate.courier_id)
            if key in seen:
                continue
            seen.add(key)
            selected.append(candidate)

    add_many(
        sorted(instance.candidates, key=lambda c: (candidate_penalty(c) / c.task_count, c.score, -c.willingness)),
        180,
    )
    add_many(
        sorted(instance.candidates, key=lambda c: (c.score / max(c.willingness, 1e-9), c.score, c.task_key)),
        120,
    )
    add_many(
        sorted(instance.candidates, key=lambda c: (-c.task_count, candidate_penalty(c) / c.task_count, c.score)),
        120,
    )
    add_many(
        sorted(instance.candidates, key=lambda c: (c.score - 50.0 * c.task_count * c.willingness, c.score)),
        120,
    )
    return selected


def replace_with_candidate(instance, seed_selected, candidate, fill_order, deadline):
    selected = {}
    covered_tasks = set()
    used_couriers = set()
    add_candidate_to_selected(selected, candidate, covered_tasks, used_couriers)

    for task_set, value in sorted(seed_selected.items(), key=lambda item: item[1][0]):
        if expired(deadline):
            break
        task_key, couriers = value
        if any(task_id in covered_tasks for task_id in task_set):
            continue
        kept = []
        for courier_id in couriers:
            if courier_id not in used_couriers:
                kept.append(courier_id)
        if not kept:
            continue
        selected[task_set] = (task_key, kept)
        covered_tasks.update(task_set)
        used_couriers.update(kept)

    for filler in fill_order:
        if expired(deadline):
            break
        if candidate_penalty(filler) >= REJECT_PENALTY * filler.task_count:
            continue
        task_set = filler.task_set
        if filler.courier_id in used_couriers:
            continue
        if any(task_id in covered_tasks for task_id in task_set):
            continue
        add_candidate_to_selected(selected, filler, covered_tasks, used_couriers)
        if len(covered_tasks) == len(instance.task_ids):
            break
    return selected


def add_candidate_to_selected(selected, candidate, covered_tasks, used_couriers):
    task_set = candidate.task_set
    selected[task_set] = (candidate.task_key, [candidate.courier_id])
    covered_tasks.update(task_set)
    used_couriers.add(candidate.courier_id)


def normalize_selected(instance, selected):
    normalized = {}
    for task_set, value in selected.items():
        task_key, couriers = value
        if not couriers:
            continue
        normalized[task_set] = (
            task_key,
            sorted(
                couriers,
                key=lambda courier_id: courier_order_key(instance, task_key, courier_id),
            ),
        )
    return normalized


def courier_order_key(instance, task_key, courier_id):
    candidate = instance.by_offer.get((task_key, courier_id))
    if candidate is None:
        return (float("inf"), 0.0, courier_id)
    return (candidate.score, -candidate.willingness, courier_id)


def is_scarce_instance(instance):
    task_count = len(instance.task_ids)
    if task_count == 0:
        return False
    return courier_count(instance) <= task_count * 1.15


def is_low_willingness_instance(instance):
    if not instance.task_ids:
        return False
    if is_scarce_instance(instance) or is_complete_pair_dense_instance(instance):
        return False
    if courier_count(instance) < len(instance.task_ids) * 1.8:
        return False
    values = [candidate.willingness for candidate in instance.candidates]
    return median_value(values) < 0.18


def is_compact_bundle_instance(instance):
    if len(instance.task_ids) > 35:
        return False
    if is_low_willingness_instance(instance) or is_scarce_instance(instance) or is_complete_pair_dense_instance(instance):
        return False
    return has_strong_bundle_discount(instance)


def time_budget_for_instance(instance):
    if is_complete_pair_dense_instance(instance):
        return 6.8
    return 7.9


def is_complete_pair_dense_instance(instance):
    task_count = len(instance.task_ids)
    if task_count < 38:
        return False
    if courier_count(instance) < task_count * 1.8:
        return False
    pair_count = 0
    for task_set in instance.by_task_set:
        if len(task_set) == 2:
            pair_count += 1
    expected_pairs = task_count * (task_count - 1) // 2
    return pair_count >= expected_pairs * 0.95


def courier_count(instance):
    couriers = set()
    for candidate in instance.candidates:
        couriers.add(candidate.courier_id)
    return len(couriers)


def has_strong_bundle_discount(instance):
    single_scores = []
    bundle_scores = []
    for candidate in instance.candidates:
        if candidate.task_count == 1:
            single_scores.append(candidate.score)
        elif candidate.task_count > 1:
            bundle_scores.append(candidate.score / candidate.task_count)
    if not single_scores or not bundle_scores:
        return False
    return median_value(bundle_scores) <= 0.68 * median_value(single_scores)


def median_value(values):
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def evaluate(instance, selected):
    used_couriers = set()
    covered_tasks = set()
    expected = 0.0
    total_score = 0.0
    expected_penalty = 0.0
    offer_count = 0
    feasible = True

    for task_set, value in selected.items():
        task_key, couriers = value
        if any(task_id in covered_tasks for task_id in task_set):
            feasible = False
        probabilities = []
        remain = 1.0
        group_expected_score = 0.0
        for courier_id in couriers:
            candidate = instance.by_offer.get((task_key, courier_id))
            if candidate is None or candidate.task_set != task_set or courier_id in used_couriers:
                feasible = False
                continue
            probabilities.append(candidate.willingness)
            group_expected_score += remain * candidate.willingness * candidate.score
            remain *= 1.0 - candidate.willingness
            total_score += candidate.score
            offer_count += 1
            used_couriers.add(courier_id)
        covered_tasks.update(task_set)
        expected += len(task_set) * acceptance_probability(probabilities)
        expected_penalty += group_expected_score + remain * REJECT_PENALTY * len(task_set)
    total_penalty = expected_penalty + REJECT_PENALTY * (len(instance.task_ids) - len(covered_tasks))
    return (feasible, -total_penalty, len(covered_tasks), expected, -total_score, -offer_count)


def group_expected_penalty(task_set, ordered_candidates):
    remain = 1.0
    penalty = 0.0
    for candidate in ordered_candidates:
        probability = candidate.willingness
        if probability < 0.0:
            probability = 0.0
        elif probability > 1.0:
            probability = 1.0
        penalty += remain * probability * candidate.score
        remain *= 1.0 - probability
    penalty += remain * REJECT_PENALTY * len(task_set)
    return penalty


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


def candidate_penalty(candidate):
    task_count = candidate.task_count
    return candidate.willingness * candidate.score + (1.0 - candidate.willingness) * REJECT_PENALTY * task_count


def expired(deadline):
    return time.perf_counter() >= deadline
