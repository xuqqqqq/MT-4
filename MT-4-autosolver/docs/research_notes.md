# Research Notes For Solver Iteration

This file captures external-method takeaways and how they map to the delivery
assignment solver.  It is intentionally practical: use it to decide what to try
next and what not to repeat.

## HeurAgenix Takeaways

The useful lesson from HeurAgenix is not to put an LLM on the 10-second online
path.  The paper and repository describe a two-stage hyper-heuristic workflow:

1. Build a problem-state representation and seed heuristics.
2. Evolve or generate candidate heuristics offline.
3. Evaluate them on smoke, validation, and test data.
4. Select the best heuristic dynamically from state features.

For this contest, the practical equivalent is:

- Keep `submission.py` deterministic and dependency-free.
- Generate/evaluate new heuristic variants offline.
- Log output hashes, local proxy scores, coverage, offers, and runtime for every
  variant.
- Only submit variants whose intended case changes are attributable and whose
  non-target cases stay stable.

## Optimization Framing

The official TSV rows form candidate hyper-edges:

```text
(task bundle, courier) -> score, willingness
```

A feasible output selects disjoint task bundles and assigns each courier at most
once.  Multi-offer groups make each task bundle a small set-function: adding a
courier has diminishing expected-acceptance benefit, while score also changes
the expected penalty.  This is closer to submodular welfare / generalized
assignment / set packing than to plain bipartite matching.

Useful algorithm families from that framing:

- Hyper-heuristic selection by instance features.
- Lagrangian or price-guided assignment to handle courier conflicts.
- Ejection-chain or large-neighborhood repair when simple move/swap is locally
  stuck.
- Matheuristic exact repair on a small destroyed neighborhood.

External-method checkpoints:

- HeurAgenix motivates the offline loop: generate candidate heuristics, evaluate
  them on a benchmark battery, and only then promote them to the online path.
- Very-large-scale / variable-neighborhood GAP heuristics point to destroying a
  small assignment neighborhood and approximately resolving that subproblem,
  rather than adding more one-edge swaps.
- Constrained-submodular greedy-local-search results support using marginal
  gains for multi-offer additions, but also warn that fixed greedy order alone
  can get stuck under matroid-like courier/task conflicts.

## Current Empirical Lessons

- Local generated cases are guardrails, not online score proxies.  Several
  local low-willingness improvements were online no-ops.
- `large_seed301` is different: its online score matches local `prop` penalty
  closely, so it is useful for validating scoring and deterministic output.
- `scarce_couriers_seed401` is not coverage-lexicographic.  Online feedback
  showed a `40/40` solution can be worse than the current `39/40` solution by
  about 44 penalty points.
- The 715.57 jump came from structural repartition/local finishing, not from
  more seed candidates.

## No-Repeat List

- Do not add more low-willingness grouping seeds unless they force a hidden-case
  output change or come with a new selector rationale.
- Do not force scarce coverage unless scalar penalty also improves.
- Do not tune dense time budgets from local public-large behavior alone.
- Do not add broad tail polish; it has repeatedly perturbed large/high-noise
  cases without reliable gain.

## Next High-Value Directions

- Build calibrated validation cases by matching the current solver's online
  score table more closely than the current hidden-like generator.
- Try price-guided single-task assignment for complete dense cases, but require
  a public `large_seed301` improvement before touching submission.
- Try ejection-chain repair for scarce cases where one uncovered task can enter
  only if a chain of pair/single replacements makes room.
- Keep all experiments logged through `scripts/run_official_benchmarks.py`.

## Calibrated Hidden-Like Suite

`scripts/calibrate_hidden_like_cases.py` searches row-level transforms for the
generated hidden-like cases so the current online-proven solver lands closer to
the observed leaderboard scores.  It writes:

- `outputs/calibrated_hidden_like_cases/*.txt`
- `outputs/calibrated_hidden_like_cases/summary.csv`
- `outputs/calibrated_hidden_like_cases/summary.json`

First calibration pass with 8 trials per case:

- `large_seed301` is anchored by the provided public input and matches online:
  local `667.084` versus online `667.11`.
- `medium_seed201` calibrated tightly: local `499.193` versus online `488.30`.
- `large_seed302` is closer but still high: local `677.269` versus online
  `635.51`.
- `low_willingness_seed501`, `scarce_couriers_seed401`, `high_noise_seed601`,
  `small_seed100`, and `tiny_seed42` still need structural generator changes,
  not just score/probability scaling.
- Repeated benchmark runs show that some calibrated cases are time/order
  sensitive: `large_seed302` produced three different output hashes in three
  repeats, while `medium_seed201` was stable.  Future comparisons should report
  repeat min/median/max for shaky cases instead of trusting a single run.
- `scripts/run_official_benchmarks.py` now writes
  `outputs/official_benchmarks/repeat_stats.csv/json` to make that variance
  visible by default.
