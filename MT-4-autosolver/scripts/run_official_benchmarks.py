"""Benchmark contest-style TSV solvers with attribution-friendly metrics.

This script is deliberately separate from ``submission.py``.  It is an offline
HeurAgenix-style evaluation harness: run candidate solvers, record hashes,
coverage, local proxy scores, and timing, then compare strategy changes before
spending scarce online submissions.
"""

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path


FAIL_PENALTY = 100.0


def build_parser():
    parser = argparse.ArgumentParser(description="Run official TSV solver benchmarks")
    parser.add_argument(
        "--solver",
        action="append",
        required=True,
        help="Path to a Python file defining solve(input_text: str) -> list. Can be repeated.",
    )
    parser.add_argument(
        "--case",
        action="append",
        help="Official TSV case path. Can be repeated. If omitted, use --case-dir.",
    )
    parser.add_argument(
        "--case-dir",
        default="outputs/hidden_like_cases",
        help="Directory containing *.txt official-format cases when --case is omitted.",
    )
    parser.add_argument(
        "--extra-case",
        action="append",
        default=[],
        help="Additional case path, useful for the public large_seed301 copy.",
    )
    parser.add_argument("--repeat", type=int, default=1, help="Repeat each solver/case run")
    parser.add_argument("--out", default="outputs/official_benchmarks", help="Output directory")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = resolve_cases(root, args.case, args.case_dir, args.extra_case)
    if not cases:
        raise SystemExit("no cases found")

    rows = []
    for solver_path in args.solver:
        module = load_solver(Path(solver_path))
        solver_name = Path(solver_path).stem
        for case_path in cases:
            text = case_path.read_text(encoding="utf-8")
            candidates = parse_candidates(text)
            for repeat_index in range(args.repeat):
                start = time.perf_counter()
                error = ""
                result = []
                try:
                    result = module.solve(text)
                except Exception as exc:  # pragma: no cover - diagnostic path
                    error = type(exc).__name__ + ": " + str(exc)
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                metrics = evaluate_result(candidates, result) if not error else empty_metrics()
                row = {
                    "solver": solver_name,
                    "solver_path": str(Path(solver_path).resolve()),
                    "case": case_path.stem,
                    "case_path": str(case_path.resolve()),
                    "repeat": repeat_index,
                    "elapsed_ms": round(elapsed_ms, 3),
                    "output_hash": output_hash(result),
                    "error": error,
                }
                row.update(metrics)
                rows.append(row)
                print(
                    "{solver:24s} {case:28s} "
                    "prop={prop:9.3f} seq={seq:9.3f} "
                    "covered={covered:3d}/{tasks:3d} "
                    "offers={offers:3d} time={time_ms:7.1f}ms "
                    "hash={hash_value} {error}".format(
                        solver=solver_name,
                        case=case_path.stem,
                        prop=row["prop_penalty"],
                        seq=row["seq_penalty"],
                        covered=row["covered_tasks"],
                        tasks=row["task_count"],
                        offers=row["offer_count"],
                        time_ms=elapsed_ms,
                        hash_value=row["output_hash"][:8],
                        error=error,
                    )
                )

    csv_path = out_dir / "summary.csv"
    json_path = out_dir / "summary.json"
    stats_path = out_dir / "repeat_stats.csv"
    stats_json_path = out_dir / "repeat_stats.json"
    if rows:
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        with json_path.open("w", encoding="utf-8") as handle:
            json.dump(rows, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        stats = build_repeat_stats(rows)
        with stats_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(stats[0]) if stats else [])
            if stats:
                writer.writeheader()
                writer.writerows(stats)
        with stats_json_path.open("w", encoding="utf-8") as handle:
            json.dump(stats, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        for item in stats:
            if item["repeat_count"] > 1:
                print(
                    "STATS {solver:24s} {case:28s} "
                    "prop_min={prop_min:9.3f} prop_med={prop_median:9.3f} prop_max={prop_max:9.3f} "
                    "hashes={hash_count:2d}".format(**item)
                )
    print("wrote {}".format(csv_path))
    print("wrote {}".format(json_path))
    print("wrote {}".format(stats_path))
    print("wrote {}".format(stats_json_path))
    return 0


def build_repeat_stats(rows):
    grouped = {}
    for row in rows:
        key = (row["solver"], row["case"])
        grouped.setdefault(key, []).append(row)

    stats = []
    for key in sorted(grouped):
        solver, case = key
        group = grouped[key]
        props = sorted(float(item["prop_penalty"]) for item in group)
        seqs = sorted(float(item["seq_penalty"]) for item in group)
        times = sorted(float(item["elapsed_ms"]) for item in group)
        hashes = sorted(set(item["output_hash"][:8] for item in group))
        stats.append(
            {
                "solver": solver,
                "case": case,
                "repeat_count": len(group),
                "prop_min": round(props[0], 6),
                "prop_median": round(median(props), 6),
                "prop_max": round(props[-1], 6),
                "seq_min": round(seqs[0], 6),
                "seq_median": round(median(seqs), 6),
                "seq_max": round(seqs[-1], 6),
                "time_min_ms": round(times[0], 3),
                "time_median_ms": round(median(times), 3),
                "time_max_ms": round(times[-1], 3),
                "hash_count": len(hashes),
                "hashes": " ".join(hashes[:12]),
            }
        )
    return stats


def median(values):
    count = len(values)
    middle = count // 2
    if count % 2:
        return values[middle]
    return 0.5 * (values[middle - 1] + values[middle])


def resolve_cases(root, explicit_cases, case_dir, extra_cases):
    paths = []
    if explicit_cases:
        paths.extend(Path(item) for item in explicit_cases)
    else:
        directory = Path(case_dir)
        if not directory.is_absolute():
            directory = root / directory
        paths.extend(sorted(directory.glob("*.txt")))
    paths.extend(Path(item) for item in extra_cases)
    resolved = []
    seen = set()
    for path in paths:
        full = path.resolve()
        if full.exists() and full not in seen:
            resolved.append(full)
            seen.add(full)
    return resolved


def load_solver(path: Path):
    full = path.resolve()
    spec = importlib.util.spec_from_file_location(full.stem + "_bench", str(full))
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load solver {}".format(full))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "solve"):
        raise RuntimeError("{} does not define solve(input_text)".format(full))
    return module


def parse_candidates(text):
    rows = []
    task_ids = set()
    candidate_by_key = {}
    lines = text.strip().splitlines()
    start = 1 if lines and lines[0].startswith("task_id_list") else 0
    for line in lines[start:]:
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 4:
            continue
        task_key = normalize_task_key(parts[0])
        courier = parts[1].strip()
        try:
            score = float(parts[2])
            willingness = float(parts[3])
        except ValueError:
            continue
        task_tuple = tuple(part for part in task_key.split(",") if part)
        for task_id in task_tuple:
            task_ids.add(task_id)
        item = {
            "task_key": task_key,
            "task_tuple": task_tuple,
            "courier": courier,
            "score": score,
            "p": max(0.0, min(1.0, willingness)),
            "task_count": len(task_tuple),
        }
        rows.append(item)
        candidate_by_key[(task_key, courier)] = item
    return {
        "rows": rows,
        "task_ids": task_ids,
        "candidate_by_key": candidate_by_key,
    }


def evaluate_result(candidates, result):
    task_count = len(candidates["task_ids"])
    used_tasks = set()
    used_couriers = set()
    prop_penalty = 0.0
    seq_penalty = 0.0
    total_score = 0.0
    offer_count = 0
    group_count = 0
    violations = []

    for row in result or []:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            violations.append("bad output row")
            continue
        task_key = normalize_task_key(str(row[0]))
        couriers = list(row[1] or [])
        offers = []
        for courier in couriers:
            item = candidates["candidate_by_key"].get((task_key, str(courier).strip()))
            if item is None:
                violations.append("unknown candidate {}/{}".format(task_key, courier))
                continue
            offers.append(item)

        if not offers:
            continue
        group_count += 1
        task_tuple = offers[0]["task_tuple"]
        if any(task_id in used_tasks for task_id in task_tuple):
            violations.append("duplicate task in {}".format(task_key))
        for task_id in task_tuple:
            used_tasks.add(task_id)

        reject_prob = 1.0
        p_sum = 0.0
        weighted_score = 0.0
        seq_group = 0.0
        for item in sorted(offers, key=lambda value: (value["score"], -value["p"], value["courier"])):
            courier = item["courier"]
            if courier in used_couriers:
                violations.append("duplicate courier {}".format(courier))
            used_couriers.add(courier)
            p = item["p"]
            score = item["score"]
            p_sum += p
            weighted_score += p * score
            seq_group += reject_prob * p * score
            reject_prob *= max(0.0, min(1.0, 1.0 - p))
            total_score += score
            offer_count += 1

        task_group_count = len(task_tuple)
        avg_score = weighted_score / p_sum if p_sum > 0.0 else FAIL_PENALTY * task_group_count
        prop_penalty += (1.0 - reject_prob) * avg_score + reject_prob * FAIL_PENALTY * task_group_count
        seq_penalty += seq_group + reject_prob * FAIL_PENALTY * task_group_count

    uncovered = max(0, task_count - len(used_tasks))
    prop_penalty += FAIL_PENALTY * uncovered
    seq_penalty += FAIL_PENALTY * uncovered
    return {
        "prop_penalty": round(prop_penalty, 6),
        "seq_penalty": round(seq_penalty, 6),
        "covered_tasks": len(used_tasks),
        "task_count": task_count,
        "uncovered_tasks": uncovered,
        "group_count": group_count,
        "offer_count": offer_count,
        "total_score": round(total_score, 6),
        "violation_count": len(violations),
        "violations": "; ".join(violations[:5]),
    }


def empty_metrics():
    return {
        "prop_penalty": 0.0,
        "seq_penalty": 0.0,
        "covered_tasks": 0,
        "task_count": 0,
        "uncovered_tasks": 0,
        "group_count": 0,
        "offer_count": 0,
        "total_score": 0.0,
        "violation_count": 1,
        "violations": "solver error",
    }


def normalize_task_key(value):
    return ",".join(sorted(part.strip() for part in value.split(",") if part.strip()))


def output_hash(result):
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
