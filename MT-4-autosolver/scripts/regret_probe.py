"""Probe regret-based extra-offer assignment without changing submission.py."""

from __future__ import print_function

import argparse
import importlib.util
import os
import sys
import time


def load_solver(path):
    spec = importlib.util.spec_from_file_location("sub", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def regret_assignment(sub, p, groups, model, weight):
    state = [[] for _ in groups]
    used = set()
    initial = sub._min_cost_assignment_expected(p, groups)
    if initial is None:
        return []
    for i, cand in enumerate(initial):
        state[i].append(cand)
        used.add(cand.courier)
    while len(used) < len(p.all_couriers):
        best = None
        for courier in p.all_couriers:
            if courier in used:
                continue
            choices = []
            for gi, mask in enumerate(groups):
                cand = p.by_mask_courier.get(mask, {}).get(courier)
                if cand is None:
                    continue
                tc = sub._bit_count(mask)
                if model == "prop":
                    cv = sub._group_value_prop(state[gi], tc)
                    tv = sub._group_value_prop(state[gi] + [cand], tc)
                else:
                    cv = sub._official_expected_value(p, [state[gi]])
                    tv = sub._official_expected_value(p, [state[gi] + [cand]])
                saving = cv - tv
                if saving > 1e-12:
                    choices.append((saving, gi, cand))
            if not choices:
                continue
            choices.sort(reverse=True, key=lambda x: x[0])
            top = choices[0]
            second = choices[1][0] if len(choices) > 1 else 0.0
            key = top[0] + weight * (top[0] - second)
            if best is None or key > best[0]:
                best = (key, top[0], top[1], top[2])
        if best is None:
            break
        _, _, gi, cand = best
        state[gi].append(cand)
        used.add(cand.courier)
    return [sorted(x, key=lambda c: (c.score, -c.p, c.courier)) for x in state if x]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", default="submission.py")
    parser.add_argument("--case-dir", default="outputs/hidden_like_cases")
    parser.add_argument("--weights", default="-0.5,-0.25,0.25,0.5,1.0")
    parser.add_argument("--final-groups", action="store_true")
    args = parser.parse_args(argv)

    sub = load_solver(args.solver)
    weights = [float(x) for x in args.weights.split(",") if x.strip()]
    for name in sorted(os.listdir(args.case_dir)):
        if not name.endswith(".txt"):
            continue
        path = os.path.join(args.case_dir, name)
        text = open(path, "r", encoding="utf-8").read()
        p = sub._parse_input(text)
        model = "prop" if len(p.all_couriers) >= p.n_tasks else "seq"
        if args.final_groups:
            solved = sub.solve(text)
            groups = []
            for task_str, _couriers in solved:
                mask = 0
                for task in str(task_str).split(","):
                    task = task.strip()
                    if task in p.task_to_idx:
                        mask |= 1 << p.task_to_idx[task]
                if mask:
                    groups.append(mask)
            groups = sub._groups_key(groups)
        else:
            groups = sub._make_matching_grouping(p, "potential_half", 3, -80.0, 0.0, 17, True)
        base = sub._greedy_expected_assignment(p, groups, model, True)
        base_value = sub._state_model_value(p, base, model)
        best = (base_value, None, base)
        start = time.time()
        for weight in weights:
            state = regret_assignment(sub, p, groups, model, weight)
            value = sub._state_model_value(p, state, model)
            if value < best[0]:
                best = (value, weight, state)
        print("%-28s base=%9.3f best=%9.3f w=%s groups=%d offers=%d time=%5.1fms" % (
            name[:-4],
            base_value,
            best[0],
            best[1],
            len(best[2]),
            sum(len(x) for x in best[2]),
            (time.time() - start) * 1000.0,
        ))


if __name__ == "__main__":
    main()
