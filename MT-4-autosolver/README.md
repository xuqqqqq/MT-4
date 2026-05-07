# Delivery AutoSolver Prototype

This repository contains a first-pass, dependency-free Python framework for the
delivery assignment challenge. The official data schema is not available yet, so
the code is organized around replaceable adapters:

- `autosolver.model`: stable internal `Instance`, `Assignment`, `Edge`, and
  bundle discount types.
- `autosolver.evaluator`: temporary lexicographic evaluator.
- `autosolver.generators`: synthetic cases for development and regression.
- `autosolver.solvers`: baseline greedy, random, marginal-probability, bundle,
  and local-search solvers.
- `autosolver.portfolio`: time-budgeted multi-solver runner that keeps the best
  feasible result.
- `autosolver.io`: internal JSON adapter to be replaced or wrapped when the
  official input/output format arrives.

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

Run a full experiment batch and save generated cases plus summary reports:

```powershell
python scripts/run_experiments.py --include-stress --time-limit 9
```

Dump a synthetic case and solve from JSON:

```powershell
python -m autosolver --case bundle_wins --dump-case bundle_wins.json
python -m autosolver --input bundle_wins.json --json
```

Run tests:

```powershell
python -m unittest discover -s tests
```

## Next official-data step

When the contest examples arrive, add a parser/writer for the official schema and
map it to `Instance`/`Assignment`. The solvers and portfolio runner should not
need structural rewrites unless the official constraints add new state that is
not represented yet.
