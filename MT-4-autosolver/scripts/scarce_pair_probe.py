"""Probe uncovered-task single-to-pair repairs without touching submission.py."""

from __future__ import print_function

import argparse
import importlib.util
import os
import sys


def load_solver(path):
    spec = importlib.util.spec_from_file_location("sub", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def result_to_state(sub, p, result):
    state = []
    for task_str, couriers in result:
        mask = 0
        for task in str(task_str).split(","):
            task = task.strip()
            if task in p.task_to_idx:
                mask |= 1 << p.task_to_idx[task]
        offers = []
        for courier in couriers:
            cand = p.by_mask_courier.get(mask, {}).get(str(courier).strip())
            if cand is not None:
                offers.append(cand)
        if offers:
            state.append(sorted(offers, key=lambda c: (c.score, -c.p, c.courier)))
    return state


def covered_mask(state):
    out = 0
    for offers in state:
        if offers:
            out |= offers[0].mask
    return out


def used_couriers(state):
    out = set()
    for offers in state:
        for cand in offers:
            out.add(cand.courier)
    return out


def improve_pair_group(sub, p, offers, used_base, model):
    if not offers:
        return offers
    mask = offers[0].mask
    task_count = sub._bit_count(mask)
    if model == "prop":
        cur = sub._group_value_prop(offers, task_count)
    else:
        cur = sub._official_expected_value(p, [offers])
    by_courier = set(c.courier for c in offers)
    choices = []
    for cand in p.by_mask.get(mask, []):
        if cand.courier in used_base or cand.courier in by_courier:
            continue
        trial = offers + [cand]
        if model == "prop":
            val = sub._group_value_prop(trial, task_count)
        else:
            val = sub._official_expected_value(p, [trial])
        saving = cur - val
        if saving > 1e-9:
            choices.append((saving, cand))
    choices.sort(reverse=True, key=lambda x: x[0])
    for _, cand in choices[:3]:
        trial = offers + [cand]
        if model == "prop":
            val = sub._group_value_prop(trial, task_count)
        else:
            val = sub._official_expected_value(p, [trial])
        if val + 1e-9 < cur:
            offers = trial
            cur = val
            by_courier.add(cand.courier)
    return sorted(offers, key=lambda c: (c.score, -c.p, c.courier))


def probe(sub, p, state, model):
    base_value = sub._state_model_value(p, state, model)
    best_value = base_value
    best_state = state
    missing = p.all_task_mask & ~covered_mask(state)
    if not missing:
        return base_value, best_value, state, "covered"
    missing_bits = list(sub._bits(missing))
    attempts = 0
    for missing_idx in missing_bits:
        missing_mask = 1 << missing_idx
        for remove_idx, offers in enumerate(state):
            if not offers or offers[0].task_count != 1:
                continue
            old_mask = offers[0].mask
            pair_mask = old_mask | missing_mask
            if pair_mask == old_mask or pair_mask not in p.by_mask:
                continue
            base = [list(x) for i, x in enumerate(state) if i != remove_idx]
            used_base = used_couriers(base)
            for pair_cand in p.by_mask.get(pair_mask, []):
                if pair_cand.courier in used_base:
                    continue
                pair_offers = improve_pair_group(sub, p, [pair_cand], used_base, model)
                trial = base + [pair_offers]
                value = sub._state_model_value(p, trial, model)
                attempts += 1
                if value + 1e-9 < best_value:
                    best_value = value
                    best_state = trial
    return base_value, best_value, best_state, attempts


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", default="submission.py")
    parser.add_argument("--case-dir", default="outputs/calibrated_scarce_probe")
    args = parser.parse_args(argv)
    sub = load_solver(args.solver)
    for name in sorted(os.listdir(args.case_dir)):
        if not name.endswith(".txt"):
            continue
        path = os.path.join(args.case_dir, name)
        text = open(path, "r", encoding="utf-8").read()
        p = sub._parse_input(text)
        model = "prop" if len(p.all_couriers) >= p.n_tasks else "seq"
        state = result_to_state(sub, p, sub.solve(text))
        base, best, best_state, attempts = probe(sub, p, state, model)
        print("%-28s model=%s base=%9.3f best=%9.3f covered=%2d/%2d attempts=%s offers=%d" % (
            name[:-4],
            model,
            base,
            best,
            sub._covered_task_count(best_state),
            p.n_tasks,
            attempts,
            sum(len(x) for x in best_state),
        ))


if __name__ == "__main__":
    main()
