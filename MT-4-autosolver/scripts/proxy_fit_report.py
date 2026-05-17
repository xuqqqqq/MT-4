"""Compare local proxy scores against known online leaderboard scores.

Usage:

    python scripts/proxy_fit_report.py \
        --summary outputs/compare_proxy_uniform/summary.json \
        --online outputs/online_scores.csv \
        --solver submission

The online CSV may contain either:

    case,online_score

or:

    solver,case,online_score

When repeated benchmark rows exist, this script uses the median local score for
each ``solver/case`` pair.  It is intentionally dependency-free so it can be
used on the contest machine as a quick calibration check.
"""

import argparse
import csv
import json
import math
from pathlib import Path


PROXY_COLUMNS = (
    "prop_penalty",
    "seq_penalty",
    "uniform_penalty",
    "best_score_penalty",
)


def build_parser():
    parser = argparse.ArgumentParser(description="Fit local proxy metrics to online scores")
    parser.add_argument("--summary", required=True, help="Benchmark summary JSON or CSV")
    parser.add_argument("--online", required=True, help="Online score JSON or CSV")
    parser.add_argument("--solver", help="Only compare one solver name")
    parser.add_argument("--out", help="Optional JSON report output path")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    summary_rows = load_rows(Path(args.summary))
    online_scores = load_online_scores(Path(args.online))

    grouped = {}
    for row in summary_rows:
        solver = str(row.get("solver", ""))
        if args.solver and solver != args.solver:
            continue
        case = str(row.get("case", ""))
        online = find_online_score(online_scores, solver, case)
        if online is None:
            continue
        grouped.setdefault((solver, case), {"online": online, "rows": []})["rows"].append(row)

    records = []
    for key in sorted(grouped):
        solver, case = key
        item = grouped[key]
        merged = {"solver": solver, "case": case, "online_score": item["online"]}
        for column in PROXY_COLUMNS:
            values = []
            for row in item["rows"]:
                if column in row and row[column] not in ("", None):
                    values.append(float(row[column]))
            merged[column] = median(sorted(values)) if values else None
        records.append(merged)

    if not records:
        raise SystemExit("no overlapping solver/case rows between summary and online scores")

    proxy_stats = []
    for column in PROXY_COLUMNS:
        pairs = [(item[column], item["online_score"]) for item in records if item[column] is not None]
        if pairs:
            proxy_stats.append(metric_report(column, pairs))

    print("cases matched: {}".format(len(records)))
    print("")
    print("{:20s} {:>10s} {:>10s} {:>10s} {:>10s} {:>10s}".format(
        "proxy", "MAE", "RMSE", "bias", "pearson", "spearman"
    ))
    for item in sorted(proxy_stats, key=lambda value: value["mae"]):
        print("{proxy:20s} {mae:10.3f} {rmse:10.3f} {bias:10.3f} {pearson:10.3f} {spearman:10.3f}".format(**item))

    print("")
    print("{:24s} {:28s} {:>10s} {:>10s} {:>10s} {:>10s}".format(
        "solver", "case", "online", "prop", "seq", "uniform"
    ))
    for item in records:
        print("{solver:24s} {case:28s} {online:>10s} {prop:>10s} {seq:>10s} {uniform:>10s}".format(
            solver=item["solver"],
            case=item["case"],
            online=fmt_float(item["online_score"]),
            prop=fmt_float(item["prop_penalty"]),
            seq=fmt_float(item["seq_penalty"]),
            uniform=fmt_float(item["uniform_penalty"]),
        ))

    report = {"records": records, "proxy_stats": sorted(proxy_stats, key=lambda value: value["mae"])}
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

    return 0


def load_rows(path):
    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "rows" in data:
            return data["rows"]
        raise SystemExit("unsupported summary JSON shape: {}".format(path))

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_online_scores(path):
    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        rows = normalize_online_json(data)
    else:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))

    scores = {}
    for row in rows:
        case = str(row.get("case", "")).strip()
        if not case:
            continue
        solver = str(row.get("solver", "")).strip() or None
        raw_score = row.get("online_score", row.get("score"))
        if raw_score in ("", None):
            continue
        scores[(solver, case)] = float(str(raw_score).replace(",", ""))
    return scores


def normalize_online_json(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        rows = []
        for key in sorted(data):
            value = data[key]
            if isinstance(value, dict):
                row = dict(value)
                row.setdefault("case", key)
                rows.append(row)
            else:
                rows.append({"case": key, "online_score": value})
        return rows
    raise SystemExit("unsupported online JSON shape")


def find_online_score(scores, solver, case):
    if (solver, case) in scores:
        return scores[(solver, case)]
    if (None, case) in scores:
        return scores[(None, case)]
    return None


def metric_report(name, pairs):
    errors = [local - online for local, online in pairs]
    mae = sum(abs(item) for item in errors) / len(errors)
    rmse = math.sqrt(sum(item * item for item in errors) / len(errors))
    bias = sum(errors) / len(errors)
    locals_ = [local for local, online in pairs]
    online_values = [online for local, online in pairs]
    return {
        "proxy": name,
        "count": len(pairs),
        "mae": round(mae, 6),
        "rmse": round(rmse, 6),
        "bias": round(bias, 6),
        "pearson": round(pearson(locals_, online_values), 6),
        "spearman": round(pearson(ranks(locals_), ranks(online_values)), 6),
    }


def pearson(left, right):
    if len(left) != len(right) or len(left) < 2:
        return 0.0
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = 0.0
    left_var = 0.0
    right_var = 0.0
    for left_value, right_value in zip(left, right):
        left_delta = left_value - left_mean
        right_delta = right_value - right_mean
        numerator += left_delta * right_delta
        left_var += left_delta * left_delta
        right_var += right_delta * right_delta
    denominator = math.sqrt(left_var * right_var)
    if denominator <= 0.0:
        return 0.0
    return numerator / denominator


def ranks(values):
    indexed = sorted((value, index) for index, value in enumerate(values))
    result = [0.0] * len(values)
    position = 0
    while position < len(indexed):
        end = position + 1
        while end < len(indexed) and indexed[end][0] == indexed[position][0]:
            end += 1
        rank = 0.5 * (position + end - 1) + 1.0
        for offset in range(position, end):
            result[indexed[offset][1]] = rank
        position = end
    return result


def median(values):
    if not values:
        return None
    count = len(values)
    middle = count // 2
    if count % 2:
        return values[middle]
    return 0.5 * (values[middle - 1] + values[middle])


def fmt_float(value):
    if value is None:
        return "n/a"
    return "{:.3f}".format(value)


if __name__ == "__main__":
    raise SystemExit(main())
