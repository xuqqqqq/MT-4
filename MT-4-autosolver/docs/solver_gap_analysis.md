# Solver Gap Analysis

This note records the current diagnosis after adopting the online-scored
`710.71` solver.  It is meant to stop us from repeating low-value hill-climbing
attempts.

## Objective Inference

The online objective is most likely an expected penalty over each selected task
group:

```text
group penalty =
    P(any courier accepts) * E(score of winning courier | accepted)
  + P(no courier accepts) * 100 * task_count
```

The stable part is the rejection probability:

```text
P(no courier accepts) = product(1 - willingness_i)
```

The unstable part is the winning-courier score.  The input does not reveal the
real first-accept timing model, so the local harness tracks several proxies:

- `prop_penalty`: accepted score is willingness-weighted average.
- `seq_penalty`: accepted score follows a deterministic sorted offer order.
- `uniform_penalty`: accepted score is arithmetic mean of offered scores.
- `subset_mean_penalty`: accepting couriers are sampled independently and the
  winner is uniform among acceptors.

Across the available online history, `uniform_penalty` and `prop_penalty` have
the best calibrated fit, but the family residuals are large.  In the combined
report, low-willingness rows are about `+312` online-vs-uniform while small rows
are about `-91`; one global proxy cannot safely guide every case.

## Structural Weaknesses

- The solver has a single-incumbent funnel.  `AutoSolverAgent` keeps only one
  best state, so later deep search operates on one basin even if a worse early
  candidate would improve more after repair.
- Low-willingness solutions are pair-heavy and already locally hard.  Current
  2/3/4-group repartition and a prototype 5/6-group destroy-repair did not
  improve calibrated low cases, so more fixed-mask or small-mask crawling is
  unlikely to help.
- Scarce repair has historically been proxy-fragile.  Forcing `40/40` can make
  online score worse than `39/40`, so any scarce repair must improve scalar
  expected penalty rather than coverage alone.
- Public large looks close to the `prop` objective.  Offline CP-SAT-like teacher
  files with much lower `seq` values do not necessarily imply online gains,
  because the online large score tracks `prop`/uniform more closely than `seq`.

## Current Candidate

The only code-path change kept from this round is a narrow low-willingness
construction penalty adjustment:

```python
if 25 <= n_tasks <= 32 and couriers >= tasks and avg_willingness < 0.071:
    FAIL_PENALTY = 114.0
```

Local evidence:

- `calibrated_low_probe/low_willingness_seed501`: `prop 1781.382 -> 1773.875`,
  same coverage `30/30`, offers `72 -> 74`.
- Hidden-like `low_willingness_seed501`, `high_noise_seed601`, medium, large,
  scarce, small, and tiny outputs stayed unchanged in the guard run.
- This is not guaranteed online: a similar `114` lower band was a no-op on an
  older branch.  Treat it as a low-risk probe, not a solved low-willingness fix.

## Rejected This Round

- `subset_mean` as a replacement objective: useful as a diagnostic, but the
  combined leave-one-out fit is worse than calibrated `uniform/prop`.
- Scarce single-state objective alignment plus sparse beam: it did not change
  hidden-like or calibrated scarce outputs, so the added beam time was removed.
- Low 5/6-group destroy-repair: checked thousands of local repartitions on
  hidden-like and calibrated low probes and found no improving move.
- Public-large pair ejection LNS: the teacher's lower objective was mostly a
  `seq` improvement; local `prop` did not improve from the current large basin.

## Next Useful Experiments

- Implement a true small elite pool only if instrumentation proves that a
  non-best early state can beat the incumbent after final repair.
- For scarce, try a priced ejection chain that targets uncovered tasks without
  accepting coverage-only regressions.
- For low, search outside the existing pair-heavy basin by changing candidate
  construction, not by adding more fixed-mask local moves.
