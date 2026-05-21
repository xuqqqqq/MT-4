"""Report which local proxy tracks online score deltas within each case.

Absolute online scores are hard to infer because most non-public cases are
hidden and our local cases are only synthetic proxies.  For solver tuning, the
more useful question is narrower: when two submitted versions changed the same
case, did a local proxy move in the same direction and by a similar amount?

This script consumes ``outputs/objective_inference_combined.json`` by default
and emits per-case pairwise delta diagnostics.  It intentionally avoids third
party dependencies so it can run in the contest environment too.
"""

from __future__ import print_function

import argparse
import itertools
import json
from collections import defaultdict


DEFAULT_COLUMNS = (
    "prop_penalty",
    "uniform_penalty",
    "seq_penalty",
    "subset_mean_penalty",
    "best_score_penalty",
)


def build_parser():
    parser = argparse.ArgumentParser(description="Compare online deltas with local proxy deltas")
    parser.add_argument(
        "--input",
        default="outputs/objective_inference_combined.json",
        help="Objective inference JSON containing a records array",
    )
    parser.add_argument("--out", help="Optional JSON output path")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    with open(args.input, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    records = data.get("records", data if isinstance(data, list) else [])
    report = build_report(records)
    print_report(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
    return 0


def build_report(records):
    by_case = defaultdict(list)
    for row in records:
        case = str(row.get("case", "")).strip()
        if case:
            by_case[case].append(row)

    case_reports = []
    for case in sorted(by_case):
        rows = by_case[case]
        pair_reports = []
        for column in DEFAULT_COLUMNS:
            pairs = []
            for left, right in itertools.combinations(rows, 2):
                if left.get(column) is None or right.get(column) is None:
                    continue
                online_delta = as_float(right.get("online_score")) - as_float(left.get("online_score"))
                proxy_delta = as_float(right.get(column)) - as_float(left.get(column))
                if abs(online_delta) <= 1e-9 and abs(proxy_delta) <= 1e-9:
                    continue
                pairs.append((proxy_delta, online_delta))
            if not pairs:
                continue
            signed = [1 for proxy_delta, online_delta in pairs if proxy_delta * online_delta > 0.0]
            opposite = [1 for proxy_delta, online_delta in pairs if proxy_delta * online_delta < 0.0]
            zero_miss = [
                1
                for proxy_delta, online_delta in pairs
                if abs(proxy_delta) <= 1e-9 and abs(online_delta) > 1e-9
            ]
            mae_delta = mean(abs(proxy_delta - online_delta) for proxy_delta, online_delta in pairs)
            pair_reports.append(
                {
                    "proxy": column,
                    "pair_count": len(pairs),
                    "same_direction_rate": len(signed) / float(len(pairs)),
                    "opposite_direction_rate": len(opposite) / float(len(pairs)),
                    "zero_proxy_online_moved": len(zero_miss),
                    "mae_delta": mae_delta,
                    "examples": [
                        {"proxy_delta": round(proxy_delta, 6), "online_delta": round(online_delta, 6)}
                        for proxy_delta, online_delta in pairs[:6]
                    ],
                }
            )
        pair_reports.sort(key=lambda item: (-item["same_direction_rate"], item["mae_delta"]))
        case_reports.append({"case": case, "record_count": len(rows), "proxies": pair_reports})
    return {"case_count": len(case_reports), "cases": case_reports}


def as_float(value):
    if value in ("", None):
        return 0.0
    return float(str(value).replace(",", ""))


def mean(values):
    values = list(values)
    return sum(values) / float(len(values)) if values else 0.0


def print_report(report):
    print("cases: {}".format(report["case_count"]))
    for case_report in report["cases"]:
        print("\n{case} records={record_count}".format(**case_report))
        for item in case_report["proxies"][:3]:
            print(
                "  {proxy:22s} n={pair_count:2d} same={same_direction_rate:4.2f} "
                "opp={opposite_direction_rate:4.2f} zero_miss={zero_proxy_online_moved:2d} "
                "mae_delta={mae_delta:7.3f}".format(**item)
            )


if __name__ == "__main__":
    raise SystemExit(main())
