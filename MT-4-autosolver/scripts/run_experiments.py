"""Generate cases and benchmark the current solver portfolio."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autosolver.generators import CASE_GENERATORS, STRESS_CASE_GENERATORS
from autosolver.io import write_instance
from autosolver.portfolio import PortfolioSolver


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AutoSolver experiments on synthetic cases")
    parser.add_argument("--out", default="outputs/experiments", help="directory for generated cases and reports")
    parser.add_argument("--time-limit", type=float, default=9.0, help="portfolio budget per case")
    parser.add_argument("--include-stress", action="store_true", help="include large stress cases")
    parser.add_argument("--stress-only", action="store_true", help="run only large stress cases")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = Path(args.out)
    case_dir = output_dir / "cases"
    case_dir.mkdir(parents=True, exist_ok=True)

    generators = {}
    if not args.stress_only:
        generators.update(CASE_GENERATORS)
    if args.include_stress or args.stress_only:
        generators.update(STRESS_CASE_GENERATORS)

    rows = []
    for name, generator in sorted(generators.items()):
        instance = generator()
        case_path = case_dir / f"{instance.name}.json"
        write_instance(instance, case_path)
        report = PortfolioSolver(time_limit_sec=args.time_limit).solve(instance)
        row = {
            "case": name,
            "instance": instance.name,
            "orders": len(instance.orders),
            "riders": len(instance.riders),
            "edges": len(instance.edges),
            "discounts": len(instance.bundle_discounts),
            "best_solver": report.best_solver,
            "expected_accepted": f"{report.objective.expected_accepted:.9f}",
            "total_cost": f"{report.objective.total_cost:.3f}",
            "offer_count": report.objective.offer_count,
            "elapsed_sec": f"{report.elapsed_sec:.6f}",
        }
        rows.append(row)
        print(
            f"{name:26s} best={report.best_solver:24s} "
            f"expected={report.objective.expected_accepted:10.6f} "
            f"cost={report.objective.total_cost:11.3f} "
            f"offers={report.objective.offer_count:5d} "
            f"time={report.elapsed_sec:7.4f}s"
        )

    csv_path = output_dir / "summary.csv"
    json_path = output_dir / "summary.json"
    if rows:
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        with json_path.open("w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    print(f"wrote {csv_path}")
    print(f"wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
