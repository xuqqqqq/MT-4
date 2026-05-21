"""Infer how local proxy metrics relate to online contest scores.

This is an offline diagnostic tool, not part of the submitted solver.  It joins
benchmark summaries produced by ``run_official_benchmarks.py`` with known online
score CSVs, then reports:

* raw proxy error,
* affine calibration ``online ~= a * proxy + b``,
* small linear blends of proxy columns with leave-one-out error,
* per-family residuals that reveal where a proxy is misleading.

The data set is tiny, so this script is deliberately conservative: it treats a
low training error as suspicious unless leave-one-out error also improves.
"""

from __future__ import print_function

import argparse
import csv
import json
import math
import re
from pathlib import Path


DEFAULT_PROXY_COLUMNS = (
    "prop_penalty",
    "seq_penalty",
    "uniform_penalty",
    "subset_mean_penalty",
    "best_score_penalty",
)


def build_parser():
    parser = argparse.ArgumentParser(description="Infer objective proxy fit")
    parser.add_argument(
        "--summary",
        action="append",
        default=[],
        help="Benchmark summary JSON/CSV. Can be repeated.",
    )
    parser.add_argument(
        "--online",
        action="append",
        default=[],
        help="Online score JSON/CSV. Can be repeated; pairs with --summary by position.",
    )
    parser.add_argument(
        "--fit-json",
        action="append",
        default=[],
        help="Existing proxy_fit_report JSON. Can be repeated.",
    )
    parser.add_argument("--solver", help="Only compare one solver name for summary inputs")
    parser.add_argument(
        "--case-alias",
        action="append",
        default=[],
        help="Map benchmark case name to online case name, e.g. official_large_seed301_copy=large_seed301.",
    )
    parser.add_argument("--out", help="Optional JSON report output")
    parser.add_argument("--markdown", help="Optional Markdown report output")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    aliases = parse_aliases(args.case_alias)
    records = []

    if args.summary or args.online:
        if len(args.summary) != len(args.online):
            raise SystemExit("--summary and --online must be supplied the same number of times")
        for index, (summary_path, online_path) in enumerate(zip(args.summary, args.online)):
            source = Path(summary_path).stem
            records.extend(
                join_summary_online(
                    Path(summary_path),
                    Path(online_path),
                    args.solver,
                    aliases,
                    source,
                )
            )

    for fit_path in args.fit_json:
        records.extend(load_fit_json(Path(fit_path)))

    if not records:
        raise SystemExit("no records loaded")

    proxy_columns = available_proxy_columns(records)
    raw_stats = []
    affine_stats = []
    for column in proxy_columns:
        pairs = [(float(row[column]), float(row["online_score"])) for row in records if row.get(column) is not None]
        if len(pairs) < 2:
            continue
        raw_stats.append(raw_metric_report(column, pairs))
        affine_stats.append(affine_metric_report(column, pairs))

    blend_specs = build_blend_specs(proxy_columns)
    blend_stats = []
    for name, columns in blend_specs:
        usable = [row for row in records if all(row.get(column) is not None for column in columns)]
        if len(usable) > len(columns) + 1:
            blend_stats.append(linear_blend_report(name, columns, usable))

    family_residuals = []
    for column in proxy_columns:
        family_residuals.extend(build_family_residuals(records, column))

    report = {
        "record_count": len(records),
        "proxy_columns": proxy_columns,
        "raw_proxy_stats": sorted(raw_stats, key=lambda item: item["mae"]),
        "affine_proxy_stats": sorted(affine_stats, key=lambda item: item["loocv_mae"]),
        "linear_blend_stats": sorted(blend_stats, key=lambda item: item["loocv_mae"]),
        "family_residuals": family_residuals,
        "records": records,
    }

    print_report(report)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
    if args.markdown:
        md_path = Path(args.markdown)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown(report), encoding="utf-8")
    return 0


def parse_aliases(items):
    aliases = {}
    for item in items:
        if "=" not in item:
            raise SystemExit("bad --case-alias {!r}; expected old=new".format(item))
        old, new = item.split("=", 1)
        aliases[old.strip()] = new.strip()
    return aliases


def join_summary_online(summary_path, online_path, solver_filter, aliases, source):
    summary_rows = load_rows(summary_path)
    online_scores = load_online_scores(online_path)
    enriched = []
    for row in summary_rows:
        solver = str(row.get("solver", ""))
        if solver_filter and solver != solver_filter:
            continue
        case = str(row.get("case", "")).strip()
        canonical_case = aliases.get(case, case)
        online = find_online_score(online_scores, solver, canonical_case)
        if online is None:
            continue
        item = dict(row)
        item["source"] = source
        item["solver"] = solver
        item["case"] = canonical_case
        item["benchmark_case"] = case
        item["was_case_alias"] = bool(case in aliases)
        item["online_score"] = online
        item["family"] = case_family(canonical_case)
        enriched.append(item)

    alias_keys = set((row["solver"], row["case"]) for row in enriched if row["was_case_alias"])
    filtered = []
    for row in enriched:
        key = (row["solver"], row["case"])
        if key in alias_keys and not row["was_case_alias"]:
            continue
        filtered.append(row)

    grouped = {}
    for row in filtered:
        key = (row["source"], row["solver"], row["case"])
        grouped.setdefault(key, []).append(row)

    records = []
    for key in sorted(grouped):
        source_name, solver, case = key
        group = grouped[key]
        merged = {
            "source": source_name,
            "solver": solver,
            "case": case,
            "family": case_family(case),
            "online_score": float(group[0]["online_score"]),
            "benchmark_cases": ",".join(sorted(set(str(row.get("benchmark_case", "")) for row in group))),
        }
        columns = set()
        for row in group:
            columns.update(row)
        for column in sorted(columns):
            if column in merged or column in ("source", "solver", "case", "family", "online_score", "benchmark_case"):
                continue
            values = []
            for row in group:
                value = row.get(column)
                number = as_float(value)
                if number is not None:
                    values.append(number)
            if values:
                merged[column] = median(sorted(values))
        records.append(merged)
    return records


def load_fit_json(path):
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    records = []
    for row in data.get("records", []):
        item = dict(row)
        item.setdefault("source", path.stem)
        item.setdefault("family", case_family(str(item.get("case", ""))))
        records.append(item)
    return records


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
    rows = load_rows(path)
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


def find_online_score(scores, solver, case):
    if (solver, case) in scores:
        return scores[(solver, case)]
    if (None, case) in scores:
        return scores[(None, case)]
    return None


def available_proxy_columns(records):
    columns = []
    for column in DEFAULT_PROXY_COLUMNS:
        if any(row.get(column) is not None for row in records):
            columns.append(column)
    for row in records:
        for column in sorted(row):
            if column.endswith("_penalty") and column not in columns:
                columns.append(column)
    return columns


def raw_metric_report(name, pairs):
    errors = [local - online for local, online in pairs]
    return {
        "proxy": name,
        "count": len(pairs),
        "mae": round(mean(abs(item) for item in errors), 6),
        "rmse": round(math.sqrt(mean(item * item for item in errors)), 6),
        "bias_local_minus_online": round(mean(errors), 6),
        "pearson": round(pearson([item[0] for item in pairs], [item[1] for item in pairs]), 6),
    }


def affine_metric_report(name, pairs):
    x_values = [item[0] for item in pairs]
    y_values = [item[1] for item in pairs]
    a, b = fit_affine(x_values, y_values)
    predictions = [a * value + b for value in x_values]
    loocv_predictions = []
    for index in range(len(pairs)):
        train_x = [x for pos, x in enumerate(x_values) if pos != index]
        train_y = [y for pos, y in enumerate(y_values) if pos != index]
        ta, tb = fit_affine(train_x, train_y)
        loocv_predictions.append(ta * x_values[index] + tb)
    return {
        "proxy": name,
        "count": len(pairs),
        "a": round(a, 8),
        "b": round(b, 8),
        "train_mae": round(mae(predictions, y_values), 6),
        "train_rmse": round(rmse(predictions, y_values), 6),
        "loocv_mae": round(mae(loocv_predictions, y_values), 6),
        "loocv_rmse": round(rmse(loocv_predictions, y_values), 6),
    }


def build_blend_specs(proxy_columns):
    specs = []
    for column in proxy_columns:
        specs.append((column + "_affine", (column,)))
    wanted = [
        ("prop_uniform", ("prop_penalty", "uniform_penalty")),
        ("prop_subset_mean", ("prop_penalty", "subset_mean_penalty")),
        ("prop_seq_uniform", ("prop_penalty", "seq_penalty", "uniform_penalty")),
        (
            "all_expected_proxies",
            ("prop_penalty", "seq_penalty", "uniform_penalty", "subset_mean_penalty", "best_score_penalty"),
        ),
    ]
    available = set(proxy_columns)
    for name, columns in wanted:
        if all(column in available for column in columns):
            specs.append((name, columns))
    seen = set()
    out = []
    for name, columns in specs:
        key = (name, columns)
        if key not in seen:
            out.append((name, columns))
            seen.add(key)
    return out


def linear_blend_report(name, columns, records):
    x = [[1.0] + [float(row[column]) for column in columns] for row in records]
    y = [float(row["online_score"]) for row in records]
    coeffs = fit_linear(x, y)
    predictions = [dot(coeffs, row) for row in x]
    loocv_predictions = []
    for index in range(len(records)):
        train_x = [row for pos, row in enumerate(x) if pos != index]
        train_y = [value for pos, value in enumerate(y) if pos != index]
        local_coeffs = fit_linear(train_x, train_y)
        loocv_predictions.append(dot(local_coeffs, x[index]))
    return {
        "model": name,
        "columns": columns,
        "count": len(records),
        "coefficients": [round(item, 8) for item in coeffs],
        "train_mae": round(mae(predictions, y), 6),
        "train_rmse": round(rmse(predictions, y), 6),
        "loocv_mae": round(mae(loocv_predictions, y), 6),
        "loocv_rmse": round(rmse(loocv_predictions, y), 6),
    }


def build_family_residuals(records, column):
    grouped = {}
    for row in records:
        if row.get(column) is None:
            continue
        family = row.get("family") or case_family(str(row.get("case", "")))
        residual = float(row["online_score"]) - float(row[column])
        grouped.setdefault(family, []).append(residual)
    out = []
    for family in sorted(grouped):
        values = grouped[family]
        out.append(
            {
                "proxy": column,
                "family": family,
                "count": len(values),
                "online_minus_proxy_mean": round(mean(values), 6),
                "online_minus_proxy_min": round(min(values), 6),
                "online_minus_proxy_max": round(max(values), 6),
            }
        )
    return out


def fit_affine(x_values, y_values):
    if not x_values:
        return 0.0, 0.0
    x_mean = mean(x_values)
    y_mean = mean(y_values)
    denom = sum((x - x_mean) * (x - x_mean) for x in x_values)
    if denom <= 1e-12:
        return 0.0, y_mean
    a = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values)) / denom
    b = y_mean - a * x_mean
    return a, b


def fit_linear(x_rows, y_values):
    cols = len(x_rows[0])
    matrix = [[0.0] * cols for _ in range(cols)]
    vector = [0.0] * cols
    ridge = 1e-8
    for row, y in zip(x_rows, y_values):
        for i in range(cols):
            vector[i] += row[i] * y
            for j in range(cols):
                matrix[i][j] += row[i] * row[j]
    for i in range(1, cols):
        matrix[i][i] += ridge
    return solve_linear_system(matrix, vector)


def solve_linear_system(matrix, vector):
    n = len(vector)
    a = [list(matrix[i]) + [vector[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(a[row][col]))
        if abs(a[pivot][col]) <= 1e-10:
            continue
        if pivot != col:
            a[col], a[pivot] = a[pivot], a[col]
        scale = a[col][col]
        for j in range(col, n + 1):
            a[col][j] /= scale
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            if abs(factor) <= 1e-14:
                continue
            for j in range(col, n + 1):
                a[row][j] -= factor * a[col][j]
    return [a[i][n] for i in range(n)]


def case_family(case):
    case = str(case)
    match = re.match(r"(.+?)_seed\d+$", case)
    if match:
        return match.group(1)
    if case.startswith("official_large"):
        return "large"
    return case


def as_float(value):
    if value in ("", None):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def mean(values):
    values = list(values)
    if not values:
        return 0.0
    return sum(values) / float(len(values))


def median(values):
    if not values:
        return None
    count = len(values)
    mid = count // 2
    if count % 2:
        return values[mid]
    return 0.5 * (values[mid - 1] + values[mid])


def mae(predictions, actuals):
    return mean(abs(prediction - actual) for prediction, actual in zip(predictions, actuals))


def rmse(predictions, actuals):
    return math.sqrt(mean((prediction - actual) ** 2 for prediction, actual in zip(predictions, actuals)))


def pearson(left, right):
    if len(left) != len(right) or len(left) < 2:
        return 0.0
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = 0.0
    left_var = 0.0
    right_var = 0.0
    for left_value, right_value in zip(left, right):
        left_delta = left_value - left_mean
        right_delta = right_value - right_mean
        numerator += left_delta * right_delta
        left_var += left_delta * left_delta
        right_var += right_delta * right_delta
    denom = math.sqrt(left_var * right_var)
    if denom <= 0.0:
        return 0.0
    return numerator / denom


def dot(left, right):
    return sum(a * b for a, b in zip(left, right))


def print_report(report):
    print("records: {}".format(report["record_count"]))
    print("\nRaw proxy error")
    for item in report["raw_proxy_stats"]:
        print(
            "  {proxy:22s} MAE={mae:8.3f} RMSE={rmse:8.3f} bias(local-online)={bias_local_minus_online:8.3f} r={pearson:6.3f}".format(
                **item
            )
        )
    print("\nAffine calibration, ranked by leave-one-out MAE")
    for item in report["affine_proxy_stats"]:
        print(
            "  {proxy:22s} y={a:.4f}x+{b:.2f} train={train_mae:8.3f} loo={loocv_mae:8.3f}".format(
                **item
            )
        )
    print("\nLinear blends, ranked by leave-one-out MAE")
    for item in report["linear_blend_stats"]:
        print(
            "  {model:22s} train={train_mae:8.3f} loo={loocv_mae:8.3f} cols={cols}".format(
                model=item["model"],
                train_mae=item["train_mae"],
                loocv_mae=item["loocv_mae"],
                cols=",".join(item["columns"]),
            )
        )
    print("\nFamily residuals for best raw proxy")
    if report["raw_proxy_stats"]:
        best_proxy = report["raw_proxy_stats"][0]["proxy"]
        for item in report["family_residuals"]:
            if item["proxy"] == best_proxy:
                print(
                    "  {family:18s} n={count:2d} online-proxy mean={online_minus_proxy_mean:8.3f} range=[{online_minus_proxy_min:8.3f},{online_minus_proxy_max:8.3f}]".format(
                        **item
                    )
                )


def render_markdown(report):
    lines = []
    lines.append("# Objective Inference Report")
    lines.append("")
    lines.append("Records: `{}`".format(report["record_count"]))
    lines.append("")
    lines.append("## Raw Proxy Error")
    lines.append("")
    lines.append("| proxy | MAE | RMSE | bias local-online | Pearson |")
    lines.append("|---|---:|---:|---:|---:|")
    for item in report["raw_proxy_stats"]:
        lines.append(
            "| {proxy} | {mae:.3f} | {rmse:.3f} | {bias_local_minus_online:.3f} | {pearson:.3f} |".format(
                **item
            )
        )
    lines.append("")
    lines.append("## Affine Calibration")
    lines.append("")
    lines.append("| proxy | formula | train MAE | LOO MAE |")
    lines.append("|---|---|---:|---:|")
    for item in report["affine_proxy_stats"]:
        lines.append(
            "| {proxy} | online ~= {a:.4f} * proxy + {b:.2f} | {train_mae:.3f} | {loocv_mae:.3f} |".format(
                **item
            )
        )
    lines.append("")
    lines.append("## Linear Blends")
    lines.append("")
    lines.append("| model | columns | train MAE | LOO MAE |")
    lines.append("|---|---|---:|---:|")
    for item in report["linear_blend_stats"]:
        lines.append(
            "| {model} | {columns} | {train_mae:.3f} | {loocv_mae:.3f} |".format(
                model=item["model"],
                columns=", ".join(item["columns"]),
                train_mae=item["train_mae"],
                loocv_mae=item["loocv_mae"],
            )
        )
    lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
