"""Probe courier-overlap pair grouping without touching submission.py.

The current solver builds most pair groups from direct pair savings.  This
offline probe tests a different seed: pair two tasks when their best single
couriers strongly overlap and those couriers also have a feasible pair offer.
That mirrors the "order-combination first, then matching" shape in on-demand
delivery work, but keeps the experiment safely outside the submitted solver.
"""

from __future__ import print_function

import argparse
import random
import time
from pathlib import Path

import ga_probe


def parse_args():
    parser = argparse.ArgumentParser(description="Probe top-courier-overlap grouping")
    parser.add_argument("--case", action="append")
    parser.add_argument("--case-dir", default="outputs/hidden_like_cases")
    parser.add_argument("--top-k", default="3,4,5,6")
    parser.add_argument("--weights", default="0.15,0.30,0.50,0.80,1.20")
    parser.add_argument("--thresholds", default="-120,-80,-40,-10,0,15,30")
    parser.add_argument("--noise", default="0,8,20")
    parser.add_argument("--seed", type=int, default=20260522)
    parser.add_argument("--model", default="mix", choices=("prop", "seq", "best", "mix"))
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--seconds", type=float, default=0.8)
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
    names = [
        "high_noise_seed601.txt",
        "large_seed301.txt",
        "large_seed302.txt",
        "low_willingness_seed501.txt",
        "medium_seed201.txt",
        "medium_seed202.txt",
        "medium_seed203.txt",
        "scarce_couriers_seed401.txt",
        "small_seed100.txt",
    ]
    directory = root / args.case_dir
    return [directory / name for name in names if (directory / name).exists()]


def parse_float_list(text):
    return [float(item) for item in text.split(",") if item.strip()]


def parse_int_list(text):
    return [int(item) for item in text.split(",") if item.strip()]


def run_case(sub, case_path, args):
    text = case_path.read_text(encoding="utf-8")
    p = sub._parse_input(text)
    base_state = ga_probe.state_from_output(sub, p, sub.solve(text))
    base_value = score_state(sub, p, base_state, args.model)
    best_value = base_value
    best_state = base_state
    best_meta = "submission"
    evals = 0
    start = time.time()

    top_ks = parse_int_list(args.top_k)
    weights = parse_float_list(args.weights)
    thresholds = parse_float_list(args.thresholds)
    noises = parse_float_list(args.noise)
    for top_k in top_ks:
        shared = build_shared_scores(sub, p, top_k)
        for weight in weights:
            for threshold in thresholds:
                for noise in noises:
                    groups = make_overlap_grouping(
                        sub,
                        p,
                        shared,
                        top_k,
                        weight,
                        threshold,
                        noise,
                        args.seed + evals * 17,
                    )
                    value, state = ga_probe.score_groups(sub, p, groups, args.model)
                    evals += 1
                    if args.repair and value < best_value + 5.0:
                        model = "prop" if args.model in ("best", "mix") else args.model
                        repaired = sub._local_improve_expected(p, state, time.time() + args.seconds, model)
                        value = score_state(sub, p, repaired, args.model)
                        state = repaired
                    if value < best_value - 1e-9:
                        best_value = value
                        best_state = state
                        best_meta = "k{} w{} t{} n{}".format(top_k, weight, threshold, noise)

    print(
        "{case:28s} base={base:9.3f} best={best:9.3f} delta={delta:8.3f} "
        "evals={evals:4d} offers={offers:3d} src={src} time={time_ms:6.1f}ms".format(
            case=case_path.stem,
            base=base_value,
            best=best_value,
            delta=best_value - base_value,
            evals=evals,
            offers=sum(len(offers) for offers in best_state),
            src=best_meta,
            time_ms=(time.time() - start) * 1000.0,
        )
    )
    if best_value < base_value - 1e-9:
        print("  groups={}".format(",".join(str(offers[0].mask) for offers in best_state if offers)))
        print_metrics(sub, p, base_state, best_state)


def score_state(sub, p, state, model):
    if model == "best":
        return ga_probe.state_best_score_value(sub, p, state)
    if model == "mix":
        return ga_probe.state_mix_value(sub, p, state)
    return sub._state_model_value(p, state, model)


def print_metrics(sub, p, base_state, best_state):
    parts = []
    for model in ("prop", "seq", "best", "mix"):
        base = score_state(sub, p, base_state, model)
        best = score_state(sub, p, best_state, model)
        parts.append("{}:{:.3f}->{:.3f}({:+.3f})".format(model, base, best, best - base))
    print("  metrics " + " ".join(parts))


def offer_saving(sub, cand):
    threshold = sub.FAIL_PENALTY * cand.task_count
    return max(0.0, cand.p * (threshold - cand.score))


def build_shared_scores(sub, p, top_k):
    single_values = {}
    single_top = {}
    for mask in p.single_masks:
        ranked = []
        values = {}
        for cand in p.by_mask.get(mask, []):
            value = offer_saving(sub, cand)
            if value > 0.0:
                values[cand.courier] = value
                ranked.append((value, cand.courier))
        ranked.sort(reverse=True)
        single_values[mask] = values
        single_top[mask] = set(courier for _, courier in ranked[:top_k])

    shared = {}
    for mask in p.pair_masks:
        bits = sub._bits(mask)
        if len(bits) != 2:
            continue
        left = 1 << bits[0]
        right = 1 << bits[1]
        left_values = single_values.get(left, {})
        right_values = single_values.get(right, {})
        if not left_values or not right_values:
            continue
        overlap_count = len(single_top.get(left, set()) & single_top.get(right, set()))
        value = 0.0
        for cand in p.by_mask.get(mask, []):
            lv = left_values.get(cand.courier)
            rv = right_values.get(cand.courier)
            if lv is None or rv is None:
                continue
            pair_value = offer_saving(sub, cand)
            if pair_value > 0.0:
                value += min(lv, rv, pair_value)
        if value > 0.0 or overlap_count:
            shared[mask] = value + overlap_count * sub.FAIL_PENALTY * 0.03
    return shared


def make_overlap_grouping(sub, p, shared, top_k, weight, threshold, noise, seed):
    rng = random.Random(seed)
    edges = []
    edge_value = {}
    for mask in p.pair_masks:
        bits = sub._bits(mask)
        if len(bits) != 2:
            continue
        base = sub._matching_edge_value(p, mask, "potential_half", top_k)
        value = base + weight * shared.get(mask, 0.0)
        edge_value[mask] = value
        noisy = value + ((rng.random() - 0.5) * noise if noise else 0.0)
        edges.append((noisy, value, bits[0], bits[1], mask))
    edges.sort(reverse=True)
    mate = [-1] * p.n_tasks
    for _noisy, value, left, right, mask in edges:
        if value < threshold:
            continue
        if mate[left] < 0 and mate[right] < 0:
            mate[left] = right
            mate[right] = left

    # Cheap 2-opt on the overlap-weighted edge values.  This mirrors the
    # submitted matching seed but keeps the alternative objective isolated here.
    improved = True
    while improved:
        improved = False
        pairs = []
        seen = set()
        for i in range(p.n_tasks):
            j = mate[i]
            if j >= 0 and i not in seen and j not in seen:
                pairs.append((min(i, j), max(i, j)))
                seen.add(i)
                seen.add(j)
        for a_idx in range(len(pairs)):
            if improved:
                break
            a, b = pairs[a_idx]
            old_one = (1 << a) | (1 << b)
            for c_idx in range(a_idx + 1, len(pairs)):
                c, d = pairs[c_idx]
                old_two = (1 << c) | (1 << d)
                old_value = edge_value.get(old_one, -1e100) + edge_value.get(old_two, -1e100)
                alt_one = (1 << a) | (1 << c)
                alt_two = (1 << b) | (1 << d)
                alt_value = edge_value.get(alt_one, -1e100) + edge_value.get(alt_two, -1e100)
                if alt_value > old_value + 1e-9:
                    mate[a], mate[c] = c, a
                    mate[b], mate[d] = d, b
                    improved = True
                    break
                alt_one = (1 << a) | (1 << d)
                alt_two = (1 << b) | (1 << c)
                alt_value = edge_value.get(alt_one, -1e100) + edge_value.get(alt_two, -1e100)
                if alt_value > old_value + 1e-9:
                    mate[a], mate[d] = d, a
                    mate[b], mate[c] = c, b
                    improved = True
                    break

    groups = []
    used = 0
    for i in range(p.n_tasks):
        j = mate[i]
        if j > i:
            mask = (1 << i) | (1 << j)
            if mask in p.by_mask:
                groups.append(mask)
                used |= mask
    for i in range(p.n_tasks):
        mask = 1 << i
        if not (used & mask) and mask in p.by_mask:
            groups.append(mask)
    return sub._groups_key(groups)


if __name__ == "__main__":
    raise SystemExit(main())
