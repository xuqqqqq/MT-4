"""Probe a wider pair-rematching LNS neighborhood.

The submitted solver mostly explores repartitions of 2-4 existing groups.
The offline GA found a better medium_seed203 basin by changing seven pairs at
once, so this script tests a deterministic matching-style neighborhood without
touching submission.py.
"""

from __future__ import print_function

import argparse
import itertools
import random
import time
from pathlib import Path

import ga_probe


def parse_args():
    parser = argparse.ArgumentParser(description="Probe pair-rematching LNS")
    parser.add_argument("--case", action="append")
    parser.add_argument("--case-dir", default="outputs/hidden_like_cases")
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--seed", type=int, default=20260522)
    parser.add_argument("--model", default="mix", choices=("prop", "seq", "best", "mix"))
    parser.add_argument("--max-groups", type=int, default=7)
    parser.add_argument("--trials", type=int, default=5000)
    parser.add_argument("--out-dir")
    return parser.parse_args()


def main():
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    sub = ga_probe.load_submission(root)
    cases = resolve_cases(root, args)
    for path in cases:
        run_case(sub, path, args)
    return 0


def resolve_cases(root, args):
    if args.case:
        return [Path(item).resolve() for item in args.case]
    names = ["medium_seed201.txt", "medium_seed202.txt", "medium_seed203.txt", "high_noise_seed601.txt"]
    base = root / args.case_dir
    return [base / name for name in names if (base / name).exists()]


def run_case(sub, case_path, args):
    text = case_path.read_text(encoding="utf-8")
    p = sub._parse_input(text)
    rng = random.Random(args.seed + p.n_tasks * 193 + len(p.all_couriers) * 31)
    deadline = time.time() + args.seconds
    base_state = ga_probe.state_from_output(sub, p, sub.solve(text))
    base_groups = tuple(offer[0].mask for offer in base_state if offer)
    best_groups = base_groups
    best_state = base_state
    best_value = score_state(sub, p, base_state, args.model)
    pair_positions = [i for i, mask in enumerate(best_groups) if sub._bit_count(mask) == 2]
    evals = 0
    hits = 0

    pair_cost = make_pair_cost(sub, p, args.model)
    local_badness = make_local_badness(sub, p, best_state, args.model)
    planned = planned_subsets(best_groups, pair_positions, local_badness, args.max_groups)
    seen = set()

    while time.time() < deadline and evals < args.trials:
        if planned:
            selected = planned.pop(0)
        else:
            size = rng.randint(3, min(args.max_groups, max(3, len(pair_positions))))
            weights = [max(0.01, local_badness.get(best_groups[i], 1.0)) for i in pair_positions]
            selected = weighted_sample(pair_positions, weights, size, rng)
        selected = tuple(sorted(selected))
        if selected in seen:
            continue
        seen.add(selected)
        released = 0
        kept = []
        for i, mask in enumerate(best_groups):
            if i in selected:
                released |= mask
            else:
                kept.append(mask)
        if sub._bit_count(released) > args.max_groups * 2:
            continue
        new_parts = best_pair_partition(sub, p, released, pair_cost)
        if not new_parts:
            continue
        old_parts = tuple(sorted(best_groups[i] for i in selected))
        if tuple(sorted(new_parts)) == old_parts:
            continue
        groups = tuple(sorted(kept + list(new_parts)))
        value, state = ga_probe.score_groups(sub, p, groups, args.model)
        evals += 1
        if value + 1e-9 < best_value:
            best_value = value
            best_state = state
            best_groups = tuple(offer[0].mask for offer in state if offer)
            pair_positions = [i for i, mask in enumerate(best_groups) if sub._bit_count(mask) == 2]
            local_badness = make_local_badness(sub, p, best_state, args.model)
            planned = planned_subsets(best_groups, pair_positions, local_badness, args.max_groups)
            seen.clear()
            hits += 1
            print("  hit value={:.3f} delta={:.3f} groups={}".format(best_value, best_value - score_state(sub, p, base_state, args.model), ",".join(str(x) for x in new_parts)))

    print(
        "{case:28s} model={model:4s} base={base:9.3f} best={best:9.3f} "
        "delta={delta:8.3f} hits={hits} evals={evals}".format(
            case=case_path.stem,
            model=args.model,
            base=score_state(sub, p, base_state, args.model),
            best=best_value,
            delta=best_value - score_state(sub, p, base_state, args.model),
            hits=hits,
            evals=evals,
        )
    )
    if best_value + 1e-9 < score_state(sub, p, base_state, args.model):
        print("  group_masks={}".format(",".join(str(mask) for mask in best_groups)))
    print_metrics(sub, p, base_state, best_state)
    if args.out_dir and best_state:
        out_dir = Path(args.out_dir)
        if not out_dir.is_absolute():
            out_dir = Path(__file__).resolve().parents[1] / out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "{}_pairdp.pyrepr".format(case_path.stem)
        out_path.write_text(repr(sub._state_to_output(best_state)) + "\n", encoding="utf-8")
        print("  wrote={}".format(out_path))


def print_metrics(sub, p, base_state, best_state):
    parts = []
    for model in ("prop", "seq", "best", "mix"):
        base = score_state(sub, p, base_state, model)
        best = score_state(sub, p, best_state, model)
        parts.append("{}:{:.3f}->{:.3f}({:+.3f})".format(model, base, best, best - base))
    print("  metrics " + " ".join(parts))


def score_state(sub, p, state, model):
    if model == "best":
        return ga_probe.state_best_score_value(sub, p, state)
    if model == "mix":
        return ga_probe.state_mix_value(sub, p, state)
    return sub._state_model_value(p, state, model)


def make_pair_cost(sub, p, model):
    cache = {}

    def cost(mask):
        if mask not in cache:
            state = sub._greedy_expected_assignment(p, (mask,), "prop" if model in ("best", "mix") else model, False)
            cache[mask] = score_state(sub, p, state, model) if state else 1e80
        return cache[mask]

    return cost


def make_local_badness(sub, p, state, model):
    out = {}
    for offers in state:
        if not offers:
            continue
        mask = offers[0].mask
        out[mask] = score_state(sub, p, [offers], model) / max(1, sub._bit_count(mask))
    return out


def planned_subsets(groups, pair_positions, badness, max_groups):
    ranked = sorted(pair_positions, key=lambda i: badness.get(groups[i], 0.0), reverse=True)
    out = []
    for size in range(min(max_groups, len(ranked)), 2, -1):
        top = ranked[: min(len(ranked), size + 5)]
        for combo in itertools.combinations(top, size):
            out.append(tuple(sorted(combo)))
            if len(out) >= 800:
                return out
    return out


def weighted_sample(items, weights, size, rng):
    pool = list(zip(items, weights))
    out = []
    for _ in range(min(size, len(pool))):
        total = sum(w for _, w in pool)
        pick = rng.random() * total
        acc = 0.0
        chosen = 0
        for i, (_, weight) in enumerate(pool):
            acc += weight
            if acc >= pick:
                chosen = i
                break
        item, _ = pool.pop(chosen)
        out.append(item)
    return out


def best_pair_partition(sub, p, released, pair_cost):
    bits = sub._bits(released)
    n = len(bits)
    if n < 2 or n % 2:
        return None
    full = (1 << n) - 1
    dp = {0: (0.0, ())}
    for mask in range(full + 1):
        if mask not in dp:
            continue
        if mask == full:
            continue
        first = None
        for i in range(n):
            if not (mask & (1 << i)):
                first = i
                break
        if first is None:
            continue
        for j in range(first + 1, n):
            if mask & (1 << j):
                continue
            pair = (1 << bits[first]) | (1 << bits[j])
            if pair not in p.by_mask:
                continue
            new_mask = mask | (1 << first) | (1 << j)
            new_value = dp[mask][0] + pair_cost(pair)
            old = dp.get(new_mask)
            if old is None or new_value < old[0]:
                dp[new_mask] = (new_value, dp[mask][1] + (pair,))
    return dp.get(full, (None, None))[1]


if __name__ == "__main__":
    raise SystemExit(main())
