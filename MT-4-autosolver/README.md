# Delivery AutoSolver Prototype

This repository contains a dependency-free Python framework for the delivery
assignment challenge. It keeps the early synthetic framework while adding a
dedicated adapter for the official TSV candidate format:

- `autosolver.model`: stable internal `Instance`, `Assignment`, `Edge`, and
  bundle discount types.
- `autosolver.evaluator`: temporary lexicographic evaluator.
- `autosolver.generators`: synthetic cases for development and regression.
- `autosolver.solvers`: baseline greedy, random, marginal-probability, bundle,
  and local-search solvers.
- `autosolver.algorithm_generation`: API-driven heuristic generation. The API
  returns bounded JSON specs, not executable Python code.
- `autosolver.generated_solver`: safe interpreter for generated heuristic specs.
- `autosolver.portfolio`: time-budgeted multi-solver runner that keeps the best
  feasible result.
- `autosolver.io`: internal JSON adapter to be replaced or wrapped when the
  official input/output format arrives.
- `autosolver.official`: official TSV adapter, evaluator, solver portfolio, and
  contest `solve(input_text)` implementation.

## Current scoring assumption

The temporary objective follows the contest brief as currently understood:

1. Maximize expected accepted order count.
2. Minimize total cost/score among equal expected acceptance.
3. Minimize offer count as a deterministic tie-breaker.

When an order is offered to multiple riders, expected acceptance is computed as:

```text
1 - product(1 - p_order_rider)
```

## Usage

List built-in synthetic cases:

```powershell
python -m autosolver --list-cases
```

Run the default case:

```powershell
python -m autosolver --case tiny_manual
```

Run a larger generated case with a 9 second portfolio budget:

```powershell
python -m autosolver --case large_random --time-limit 9
```

Run a stress case:

```powershell
python -m autosolver --list-stress-cases
python -m autosolver --stress-case complex_mixed_city --time-limit 9
```

Run the HeurAgenix-lite agent selector:

```powershell
python -m autosolver --stress-case complex_mixed_city --agent --time-limit 9
python scripts/run_experiments.py --stress-only --agent --time-limit 9
```

Generate new heuristic specs before solving:

```powershell
python -m autosolver --case multi_offer_probability --agent --generate-algorithms 3 --print-generated-specs
python scripts/run_experiments.py --agent --generate-algorithms 3 --time-limit 9
```

Use an external OpenAI-compatible generation API:

```powershell
$env:AUTOSOLVER_LLM_API_KEY = "your-api-key"
$env:AUTOSOLVER_LLM_MODEL = "your-model-name"
python -m autosolver --stress-case complex_mixed_city --agent --generate-algorithms 4 --algorithm-generator openai-compatible
```

The external API is asked to return JSON heuristic specs only. The runtime does
not execute generated source code; it converts validated specs into
`GeneratedGreedySolver` instances and lets the portfolio evaluator keep or drop
them by score.

Some OpenAI-compatible providers can take longer than the local solver budget to
generate specs. Use `--llm-timeout 90` for slower endpoints during offline
strategy exploration; keep generated specs cached or switch back to `template`
mode if the official 10-second path must include generation.

Run a full experiment batch and save generated cases plus summary reports:

```powershell
python scripts/run_experiments.py --include-stress --time-limit 9
```

Dump a synthetic case and solve from JSON:

```powershell
python -m autosolver --case bundle_wins --dump-case bundle_wins.json
python -m autosolver --input bundle_wins.json --json
```

Run an official TSV case:

```powershell
python -m autosolver --official-input large_seed301.txt --time-limit 9
python -m autosolver --official-input large_seed301.txt --time-limit 9 --output official_result.json
```

The contest-style entrypoint is [official_solver.py](official_solver.py), which
defines `solve(input_text: str) -> list`.

Run attribution-friendly official TSV benchmarks before using online attempts:

```powershell
python scripts/run_official_benchmarks.py --solver submission.py --repeat 3 --extra-case outputs/official_large_seed301_copy.txt
```

The benchmark writes per-run rows plus repeat min/median/max summaries in
`outputs/official_benchmarks/summary.*` and
`outputs/official_benchmarks/repeat_stats.*`.

Calibrate generated hidden-like cases against the observed online score table:

```powershell
python scripts/calibrate_hidden_like_cases.py --solver submission.py --trials 8
python scripts/run_official_benchmarks.py --solver submission.py --case-dir outputs/calibrated_hidden_like_cases --extra-case outputs/official_large_seed301_copy.txt
```

Research notes and no-repeat lessons are tracked in
[docs/research_notes.md](docs/research_notes.md).

Run tests:

```powershell
python -m unittest discover -s tests
```

## Official-data notes

The official TSV rows are treated as candidate hyper-edges:
`task_id_list + courier_id -> total_score, willingness`. A `task_id_list` can
contain one task or a bundled pair. The current official evaluator maximizes
expected accepted task count using `willingness`, then deterministic task
coverage, then total score. If the released judge uses a different priority,
only `OfficialEvaluator.better` should need to change.
