"""Generate local official-format cases shaped like the hidden judge names.

The real hidden inputs are unavailable, so these cases are not score proxies.
They are guardrails for runtime and failure modes: high noise, scarce couriers,
low willingness, medium/large dense candidate pools, and tiny/small sanity sets.
"""

import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate hidden-like official TSV cases")
    parser.add_argument("--out", default="outputs/hidden_like_cases", help="output directory")
    parser.add_argument("--bench", action="store_true", help="run submission.solve on generated cases")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    specs = [
        ("tiny_seed42", 42, 6, 12, "normal"),
        ("small_seed100", 100, 15, 30, "normal"),
        ("medium_seed201", 201, 30, 60, "normal"),
        ("medium_seed202", 202, 30, 55, "bundle_heavy"),
        ("medium_seed203", 203, 30, 70, "conflict"),
        ("large_seed301", 301, 40, 80, "normal"),
        ("large_seed302", 302, 40, 80, "bundle_heavy"),
        ("scarce_couriers_seed401", 401, 40, 38, "scarce"),
        ("low_willingness_seed501", 501, 30, 75, "low_willingness"),
        ("high_noise_seed601", 601, 30, 75, "high_noise"),
    ]

    paths = []
    for name, seed, task_count, courier_count, scenario in specs:
        rows = generate_rows(seed, task_count, courier_count, scenario)
        path = out_dir / (name + ".txt")
        write_tsv(path, rows)
        paths.append(path)
        print(f"wrote {path} rows={len(rows)} scenario={scenario}")

    if args.bench:
        import submission

        for path in paths:
            text = path.read_text(encoding="utf-8")
            start = time.perf_counter()
            result = submission.solve(text)
            elapsed = time.perf_counter() - start
            instance = submission.parse_input(text)
            selected = selected_from_result(instance, result)
            objective = submission.evaluate(instance, selected)
            print(
                f"{path.name:28s} elapsed={elapsed:7.3f}s "
                f"rows={sum(1 for _ in path.open(encoding='utf-8')) - 1:6d} "
                f"groups={len(result):3d} offers={sum(len(row[1]) for row in result):3d} "
                f"covered={objective[2]:3d}/{len(instance.task_ids):3d} proxy={-objective[1]:9.3f}"
            )
    return 0


def generate_rows(seed, task_count, courier_count, scenario):
    rng = random.Random(seed)
    tasks = [f"T{i:04d}" for i in range(task_count)]
    couriers = [f"C{i:03d}" for i in range(courier_count)]
    rows = []

    if scenario == "scarce":
        single_degree = min(courier_count, 18)
        bundle_degree = min(courier_count, 16)
        pair_count = task_count * (task_count - 1) // 2
    elif scenario == "low_willingness":
        single_degree = min(courier_count, 45)
        bundle_degree = min(courier_count, 36)
        pair_count = min(task_count * (task_count - 1) // 2, 520)
    elif scenario == "high_noise":
        single_degree = min(courier_count, 52)
        bundle_degree = min(courier_count, 44)
        pair_count = min(task_count * (task_count - 1) // 2, 560)
    else:
        single_degree = min(courier_count, 40 if task_count >= 30 else 24)
        bundle_degree = min(courier_count, 34 if task_count >= 30 else 18)
        pair_count = min(task_count * (task_count - 1) // 2, 500 if task_count >= 30 else 90)

    courier_bias = {courier: rng.uniform(-8.0, 8.0) for courier in couriers}
    courier_reliability = {courier: rng.uniform(-0.10, 0.12) for courier in couriers}
    if scenario == "conflict":
        for courier in couriers[: max(4, courier_count // 8)]:
            courier_bias[courier] -= 10.0
            courier_reliability[courier] += 0.16

    for task_index, task in enumerate(tasks):
        sampled = rng.sample(couriers, single_degree)
        for courier in sampled:
            score = single_score(rng, task_index, courier_bias[courier], scenario)
            willingness = single_willingness(rng, courier_reliability[courier], scenario)
            rows.append((task, courier, score, willingness))

    pairs = all_pairs(tasks)
    rng.shuffle(pairs)
    for task_a, task_b in pairs[:pair_count]:
        key = task_a + "," + task_b
        for courier in rng.sample(couriers, bundle_degree):
            score = bundle_score(rng, courier_bias[courier], scenario)
            willingness = bundle_willingness(rng, courier_reliability[courier], scenario)
            rows.append((key, courier, score, willingness))

    if scenario == "high_noise":
        add_noise_rows(rng, rows, tasks, couriers)

    rng.shuffle(rows)
    return rows


def single_score(rng, task_index, bias, scenario):
    base = rng.uniform(18.0, 80.0) + bias + (task_index % 5) * 1.7
    if scenario == "scarce":
        base += rng.uniform(8.0, 28.0)
    if scenario == "high_noise" and rng.random() < 0.08:
        base += rng.uniform(50.0, 180.0)
    return round(max(1.0, min(220.0, base)), 3)


def bundle_score(rng, bias, scenario):
    base = rng.uniform(34.0, 120.0) + bias * 1.4
    if scenario == "bundle_heavy":
        base *= rng.uniform(0.55, 0.85)
    if scenario == "scarce":
        base += rng.uniform(12.0, 34.0)
    if scenario == "high_noise" and rng.random() < 0.10:
        base *= rng.uniform(0.45, 2.2)
    return round(max(2.0, min(260.0, base)), 3)


def single_willingness(rng, reliability, scenario):
    if scenario == "low_willingness":
        value = rng.betavariate(1.1, 7.5) * 0.75 + reliability * 0.4
    elif scenario == "high_noise":
        value = rng.betavariate(1.6, 3.2) + reliability + rng.uniform(-0.20, 0.20)
    else:
        value = rng.betavariate(2.2, 2.8) + reliability
    return round(clamp(value, 0.01, 0.97), 4)


def bundle_willingness(rng, reliability, scenario):
    if scenario == "low_willingness":
        value = rng.betavariate(1.0, 8.0) * 0.70 + reliability * 0.35
    elif scenario == "high_noise":
        value = rng.betavariate(1.4, 3.5) + reliability + rng.uniform(-0.25, 0.25)
    else:
        value = rng.betavariate(2.0, 3.4) + reliability
    return round(clamp(value, 0.01, 0.95), 4)


def add_noise_rows(
    rng,
    rows,
    tasks,
    couriers,
):
    for _ in range(200):
        task = rng.choice(tasks)
        if rng.random() < 0.55:
            other = rng.choice([candidate for candidate in tasks if candidate != task])
            task = ",".join(sorted((task, other)))
        courier = rng.choice(couriers)
        score = round(rng.choice([rng.uniform(1.0, 12.0), rng.uniform(120.0, 300.0)]), 3)
        willingness = round(clamp(rng.uniform(-0.2, 1.2), 0.0, 1.0), 4)
        rows.append((task, courier, score, willingness))


def all_pairs(tasks):
    pairs = []
    for index, task_a in enumerate(tasks):
        for task_b in tasks[index + 1 :]:
            pairs.append((task_a, task_b))
    return pairs


def write_tsv(path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("task_id_list\tcourier_id\ttotal_score\twillingness\n")
        for task_key, courier, score, willingness in rows:
            handle.write(f"{task_key}\t{courier}\t{score}\t{willingness}\n")


def selected_from_result(instance, result):
    selected = {}
    for task_key, couriers in result:
        task_set = tuple(sorted(part.strip() for part in task_key.split(",") if part.strip()))
        selected[task_set] = (task_key, list(couriers))
    return selected


def clamp(value, low, high):
    return max(low, min(high, value))


if __name__ == "__main__":
    raise SystemExit(main())
