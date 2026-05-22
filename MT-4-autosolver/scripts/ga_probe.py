"""Offline memetic grouping probe for the MT-4 one-file solver.

This script is intentionally not imported by submission.py.  It uses the
current solver internals as a local teacher: evolve task partitions, repair
them with the existing assignment/local-search routines, and report whether a
new grouping basin beats the submitted baseline on local proxies.
"""

from __future__ import print_function

import argparse
import importlib.util
import random
import time
from pathlib import Path


def load_submission(root):
    path = root / "submission.py"
    spec = importlib.util.spec_from_file_location("submission_probe", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args():
    parser = argparse.ArgumentParser(description="Run an offline memetic grouping probe")
    parser.add_argument("--case", action="append", help="Case path. Defaults to selected hidden-like cases.")
    parser.add_argument("--case-dir", default="outputs/hidden_like_cases")
    parser.add_argument("--seconds", type=float, default=12.0)
    parser.add_argument("--population", type=int, default=48)
    parser.add_argument("--generations", type=int, default=80)
    parser.add_argument("--seed", type=int, default=20260522)
    parser.add_argument("--model", default="auto", choices=("auto", "prop", "seq", "best", "mix"))
    parser.add_argument("--out-dir", help="Optional directory for best output pyrepr files")
    return parser.parse_args()


def main():
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    sub = load_submission(root)
    cases = resolve_cases(root, args)
    for case_path in cases:
        run_case(sub, case_path, args)
    return 0


def resolve_cases(root, args):
    if args.case:
        return [Path(item).resolve() for item in args.case]
    names = [
        "low_willingness_seed501.txt",
        "scarce_couriers_seed401.txt",
        "high_noise_seed601.txt",
        "medium_seed203.txt",
    ]
    directory = root / args.case_dir
    return [directory / name for name in names if (directory / name).exists()]


def run_case(sub, case_path, args):
    text = case_path.read_text(encoding="utf-8")
    p = sub._parse_input(text)
    model = p.n_tasks and ("prop" if len(p.all_couriers) >= p.n_tasks else "seq")
    if args.model != "auto":
        model = args.model
    rng = random.Random(args.seed + p.n_tasks * 131 + len(p.all_couriers) * 17)
    deadline = time.time() + args.seconds

    baseline_state = state_from_output(sub, p, sub.solve(text))
    if model == "best":
        baseline_value = state_best_score_value(sub, p, baseline_state)
    elif model == "mix":
        baseline_value = state_mix_value(sub, p, baseline_state)
    else:
        baseline_value = sub._state_model_value(p, baseline_state, model)
    best_groups, best_state, best_value, source = seed_population(sub, p, model, rng, args.population)
    if baseline_value < best_value:
        best_value = baseline_value
        best_state = baseline_state
        best_groups = tuple(offer[0].mask for offer in baseline_state if offer)
        source = "submission"

    population = []
    seen = set()
    for groups in initial_groupings(sub, p, rng):
        groups = normalize_groups(sub, p, groups)
        key = tuple(groups)
        if key not in seen:
            seen.add(key)
            population.append((score_groups(sub, p, groups, model), groups))
    while len(population) < args.population:
        parent = best_groups or tuple(sub._all_single_grouping(p))
        groups = mutate_groups(sub, p, parent, rng)
        key = tuple(groups)
        if key not in seen:
            seen.add(key)
            population.append((score_groups(sub, p, groups, model), groups))
    population.sort(key=lambda item: item[0][0])
    population = population[: args.population]

    generation = 0
    evals = len(population)
    while generation < args.generations and time.time() < deadline:
        generation += 1
        elites = [groups for _, groups in population[: max(4, args.population // 6)]]
        children = []
        while len(children) < args.population and time.time() < deadline:
            if rng.random() < 0.55 and len(elites) >= 2:
                left, right = rng.sample(elites, 2)
                child = crossover_groups(sub, p, left, right, rng)
            else:
                child = rng.choice(elites)
            child = mutate_groups(sub, p, child, rng)
            key = tuple(child)
            if key in seen:
                continue
            seen.add(key)
            children.append((score_groups(sub, p, child, model), child))
            evals += 1
        population.extend(children)
        population.sort(key=lambda item: item[0][0])
        population = population[: args.population]
        if population and population[0][0][0] < best_value - 1e-9:
            best_value = population[0][0][0]
            best_state = population[0][0][1]
            best_groups = tuple(population[0][1])
            source = "ga_gen{}".format(generation)

    # Spend a small offline repair budget on the best basin only.
    if best_state and model not in ("best", "mix") and time.time() < deadline:
        repair_deadline = min(deadline, time.time() + max(0.1, args.seconds * 0.12))
        repaired = sub._local_improve_expected(p, best_state, repair_deadline, model)
        repaired_value = sub._state_model_value(p, repaired, model)
        if repaired_value < best_value:
            best_value = repaired_value
            best_state = repaired
            source += "+repair"

    print(
        "{case:28s} model={model:4s} base={base:9.3f} best={best:9.3f} "
        "delta={delta:8.3f} groups={groups:2d} offers={offers:3d} "
        "src={src} evals={evals}".format(
            case=case_path.stem,
            model=model,
            base=baseline_value,
            best=best_value,
            delta=best_value - baseline_value,
            groups=len(best_state or []),
            offers=sum(len(offers) for offers in (best_state or [])),
            src=source,
            evals=evals,
        )
    )
    if best_value < baseline_value - 1e-9:
        print("  group_sizes={}".format(",".join(str(bin(mask).count("1")) for mask in best_groups)))
        print("  group_masks={}".format(",".join(str(mask) for mask in best_groups)))
    if args.out_dir and best_state:
        out_dir = Path(args.out_dir)
        if not out_dir.is_absolute():
            out_dir = Path(__file__).resolve().parents[1] / out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "{}_seed{}.pyrepr".format(case_path.stem, args.seed)
        out_path.write_text(repr(sub._state_to_output(best_state)) + "\n", encoding="utf-8")
        print("  wrote={}".format(out_path))


def seed_population(sub, p, model, rng, limit):
    best_groups = None
    best_state = None
    best_value = 1e100
    best_source = "none"
    count = 0
    for groups in initial_groupings(sub, p, rng):
        value, state = score_groups(sub, p, groups, model)
        count += 1
        if value < best_value:
            best_value = value
            best_state = state
            best_groups = tuple(groups)
            best_source = "seed{}".format(count)
        if count >= limit:
            break
    return best_groups, best_state, best_value, best_source


def initial_groupings(sub, p, rng):
    yield sub._all_single_grouping(p)
    yield sub._make_forced_pair_grouping(p)
    for mode in ("pair_raw", "pair_half", "pair_gain"):
        for threshold in (-220.0, -140.0, -80.0, -40.0, -10.0, 0.0, 10.0, 25.0, 40.0, 60.0):
            yield sub._make_expected_grouping(p, mode, threshold, 0.0, 17)
    for alpha in (0.0, 0.5, 1.0, 2.0, -1.0):
        yield sub._make_greedy_grouping(p, alpha, 0.0, 0.0, 29)
    if 25 <= p.n_tasks <= 32:
        configs = (
            ("potential_half", 3, -80.0),
            ("potential_raw", 3, -80.0),
            ("potential_gain", 4, -80.0),
            ("potential_gain", 5, -120.0),
        )
        seed = 53
        for mode, top_k, threshold in configs:
            yield sub._make_matching_grouping(p, mode, top_k, threshold, 0.0, seed, True)
            seed += 13


def score_groups(sub, p, groups, model):
    groups = normalize_groups(sub, p, groups)
    assign_model = "prop" if model in ("best", "mix") else model
    state = sub._greedy_expected_assignment(p, groups, assign_model, False)
    if model == "best":
        value = state_best_score_value(sub, p, state)
    elif model == "mix":
        value = state_mix_value(sub, p, state)
    else:
        value = sub._state_model_value(p, state, model)
    return value, state


def state_mix_value(sub, p, state):
    # Keep prop as the anchor while nudging away from bad winner-score basins.
    return sub._state_model_value(p, state, "prop") + 0.18 * state_best_score_value(sub, p, state)


def state_best_score_value(sub, p, state):
    value = 0.0
    covered = 0
    used_tasks = set()
    used_couriers = set()
    for offers in state:
        if not offers:
            continue
        task_ids = [task.strip() for task in offers[0].task_str.split(",")]
        if any(task in used_tasks for task in task_ids):
            return 1e100
        reject_prob = 1.0
        best_score = None
        for cand in offers:
            if cand.courier in used_couriers:
                return 1e100
            used_couriers.add(cand.courier)
            reject_prob *= max(0.0, min(1.0, 1.0 - cand.p))
            if best_score is None or cand.score < best_score:
                best_score = cand.score
        value += (1.0 - reject_prob) * best_score + reject_prob * sub.FAIL_PENALTY * offers[0].task_count
        covered += offers[0].task_count
        for task_id in task_ids:
            used_tasks.add(task_id)
    value += sub.FAIL_PENALTY * max(0, p.n_tasks - covered)
    return value


def normalize_groups(sub, p, groups):
    out = []
    used = 0
    for mask in groups:
        if mask and not (mask & used) and mask in p.by_mask:
            out.append(mask)
            used |= mask
    missing = p.all_task_mask & ~used
    bit = 1
    while missing:
        if missing & 1:
            if bit in p.by_mask:
                out.append(bit)
        missing >>= 1
        bit <<= 1
    return tuple(sorted(out))


def mutate_groups(sub, p, groups, rng):
    groups = list(groups)
    if not groups:
        return normalize_groups(sub, p, groups)
    remove_target = rng.randint(1, 4 if p.n_tasks <= 32 else 5)
    picked = rng.sample(range(len(groups)), min(remove_target, len(groups)))
    released = 0
    kept = []
    for idx, mask in enumerate(groups):
        if idx in picked:
            released |= mask
        else:
            kept.append(mask)
    if sub._bit_count(released) > 10:
        bits = sub._bits(released)
        keep_bits = bits[:10]
        released = 0
        for idx in keep_bits:
            released |= 1 << idx
    parts = sub._enumerate_partitions(p, released)
    if parts:
        choice = list(rng.choice(parts))
        rng.shuffle(choice)
        kept.extend(choice)
    return normalize_groups(sub, p, kept)


def crossover_groups(sub, p, left, right, rng):
    child = []
    used = 0
    for mask in left:
        if rng.random() < 0.5 and not (mask & used):
            child.append(mask)
            used |= mask
    for mask in right:
        if not (mask & used):
            child.append(mask)
            used |= mask
    return normalize_groups(sub, p, child)


def state_from_output(sub, p, result):
    state = []
    for row in result:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        task_key = ",".join(sorted(str(row[0]).split(",")))
        mask = 0
        for task in task_key.split(","):
            task = task.strip()
            if task in p.task_to_idx:
                mask |= 1 << p.task_to_idx[task]
        offers = []
        by_courier = p.by_mask_courier.get(mask, {})
        for courier in row[1] or []:
            item = by_courier.get(str(courier).strip())
            if item is not None:
                offers.append(item)
        if offers:
            state.append(offers)
    return state


if __name__ == "__main__":
    raise SystemExit(main())
