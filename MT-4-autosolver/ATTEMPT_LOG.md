# AutoSolver Attempt Log

This file is the guardrail for future changes. Before changing `submission.py`,
add a short hypothesis here; after local or online feedback, record the result
and whether the idea is kept, reverted, or banned. The goal is to stop repeating
similar experiments under different names.

## Fixed Experiment Template

- Hypothesis:
- Code change:
- Local evidence:
- Online evidence:
- Decision:
- Lesson:

## Current Stable Baseline

- Commit: `7d23212` (`Restore stable line after small-beam regression`)
- `submission.py` blob: `e1572127a89b59517880c02ba96c8bee5fbce3ef`
- Verification: `python -m py_compile submission.py`; `python -m unittest discover -s tests -q` passed 23 tests.
- Best known online family: around `747.04` average, but online large-case scores are sensitive to code shape and timing.

Known stable-ish score profile:

- `high_noise_seed601`: `556.65`
- `large_seed301`: best seen around `700.76`, but unstable submissions can fall to `750+`
- `large_seed302`: best seen around `651.72`, but unstable submissions can fall to `703+`
- `low_willingness_seed501`: `1830.54`
- `medium_seed201`: best seen `531.83`
- `medium_seed202`: best seen `610.12`
- `medium_seed203`: best seen `519.38`
- `scarce_couriers_seed401`: `1589.86`, usually `38/40`
- `small_seed100`: `326.78`
- `tiny_seed42`: `152.80`

## Retrospectives

### Low-willingness fanout branch

- Hypothesis: hidden `low_willingness_seed501` needs aggressive multi-offer/fanout and can be detected by median willingness.
- Code change: added a low-willingness branch that selected broader fanout earlier.
- Online evidence: average `860.45`; `low_willingness_seed501` worsened to `2362.10`; medium/high-noise cases also worsened.
- Decision: reverted.
- Lesson: the low-willingness detector is too broad and the branch changes too many 30-task cases. Do not add early-return fanout branches without a much sharper classifier.

### Universal courier reassignment polish

- Hypothesis: after portfolio selection, moving or swapping couriers between accepted bundles can reduce expected penalty.
- Code change: ran reassignment polish broadly after the main portfolio.
- Online evidence: average `763.08`; `low_willingness_seed501` improved slightly to `1815.06`, but large/high-noise/medium cases regressed.
- Decision: reverted.
- Lesson: local evaluator likes these moves more than the judge does. Broad reassignment polish is not reliable.

### Restricted reassignment polish

- Hypothesis: the reassignment idea is only harmful because it runs too broadly; restrict it to low/compact cases.
- Code change: gated the polish to narrower case classes.
- Online evidence: average `758.28`; `low_willingness_seed501` improved slightly, but `large_seed301` and `large_seed302` fell into bad bands.
- Decision: reverted.
- Lesson: even gated tail logic perturbs timing/code path enough to hurt large cases. Avoid tail polish unless the large path is proven unchanged.

### Fixed-depth dense repair

- Hypothesis: dense large cases need more deterministic repair depth to stabilize improvements.
- Code change: changed dense repair loop depth/timing.
- Online evidence: average `1088.37`; `large_seed302` timed out.
- Decision: reverted.
- Lesson: dense large instances are deadline-sensitive. Do not increase dense-path work near the 10-second boundary.

### Small-case beam packing

- Hypothesis: `small_seed100` is low-hanging fruit and can be improved with a tiny beam without touching larger cases.
- Code change: added a `<=15` task beam polish after portfolio.
- Online evidence: average `759.87`; `small_seed100` did not improve, while `large_seed301`/`large_seed302` fell into bad bands.
- Decision: reverted.
- Lesson: adding code anywhere in `submission.py` can perturb online timing or code-shape behavior. Small-case improvements are not worth submitting unless large outputs are locked.

## Current No-Repeat List

- Do not add low-willingness early-return/fanout branches.
- Do not add broad or lightly-gated reassignment polish.
- Do not increase dense repair depth or dense time budget.
- Do not add post-portfolio tail polish unless it is proven not to affect large cases.
- Do not trust local expected-penalty improvements alone; online feedback has repeatedly contradicted that proxy.
- Do not submit changes that only improve one synthetic/local case while moving public `large_seed301` output or runtime.

## Next Useful Directions

- Build local diagnostics before changing the submission path: strategy attribution, output hashes, and per-branch timing on true `large_seed301`.
- Prefer structural alternatives that can be compared offline without touching `submission.py` first.
- If a new idea is tried in `submission.py`, require a clear predicted target case, unchanged large-case behavior when intended, and an explicit rollback plan.

## Active Experiment: Structural Search for Scarce/Low Cases

- Hypothesis: the remaining useful gain is more likely in `scarce_couriers_seed401` and `low_willingness_seed501` than in dense large-case micro-tuning.
- Guardrail: avoid changing dense large-case behavior unless a local diagnostic clearly proves why it should improve.
- Planned local evidence: strategy attribution, output hashes, coverage/offers, and expected-penalty comparison on true `large_seed301` plus hidden-like generated cases.
- Local evidence: low-willingness generated case is the only hidden-like case classified by `is_low_willingness_instance`; expanding the current best low solution from max 3 offers to max 6 offers after option search improves local expected penalty from `1592.432` to `1439.004` with unchanged coverage and all 75 couriers used.
- Planned code change: add a low-only final fanout refinement on the incumbent, not an early-return fanout branch.
- Verification: compared current code against stable `HEAD:MT-4-autosolver/submission.py` on true `large_seed301` plus all generated hidden-like cases; every non-low case had identical output hash, while low improved from `1592.432` to `1439.004`.
- Online evidence: average `760.40`; `low_willingness_seed501` stayed at `1830.54`, while `large_seed301` regressed to `755.68` and `large_seed302` stayed in the bad `703.32` band.
- Decision: reverted.
- Lesson: low-only postprocessing still does not affect the official low case as expected and can perturb large-case online behavior. Do not submit post-portfolio fanout refinements.
- Status: failed online, code reverted.

## Active Experiment: Deterministic Dense Fast Path

- Hypothesis: complete-pair dense large cases are score-unstable because time-bound `repair_search` stops after different candidate counts when code shape changes.
- Local evidence: on true `large_seed301`, starting from the strongest dense strategy (`score - 25*w`, max 3 offers) and running a fixed 220 repair candidates reaches local expected penalty `694.855` in about `5.9s`; the current full portfolio reaches about `703.401` locally and online can fall to the `755+` band.
- Guardrail: only activate for `is_complete_pair_dense_instance(instance)`; non-dense large/medium/scarce/low cases should keep the stable path.
- Planned code change: add a complete-pair dense fast path at the start of `portfolio_solve`.
- Verification: stable-vs-current comparison on true `large_seed301` plus generated hidden-like cases showed only true dense `large_seed301` changed (`702.354 -> 694.855`, `6.882s -> 5.893s`); every non-dense generated case had identical output hash.
- Risk: synthetic complete-pair dense variants are not uniformly improved, so this is an online candidate aimed specifically at the official complete-pair large behavior.
- Refinement: choose dense willingness weight `25` for low-willingness/full-cost dense cases like true `large_seed301`, and `35` for higher-willingness or stronger bundle-discount dense cases to reduce risk on large302-like variants.
- Online evidence: average `762.15`; `large_seed301` worsened to `759.16`, `large_seed302` worsened to `723.97`, and no target case improved enough to compensate.
- Decision: reverted.
- Lesson: replacing the dense portfolio with a deterministic fast path overfits local `large_seed301`; official large behavior prefers the original portfolio even when local proxy says otherwise.
- Status: failed online, code reverted.
## Failed Experiment: Preserve Algorithm, Reduce Runtime Variance

- Hypothesis: the stable portfolio is close to the best known line, but online results vary because the time-bound loops stop at different points; safe micro-optimizations may let the same algorithm run more consistently.
- Local evidence: `cProfile` on true `large_seed301` shows `Candidate.task_set` triggers hundreds of thousands of repeated `sorted(self.tasks)` calls.
- Planned code change: cache each candidate's sorted task set and task count during parsing, then variants tried penalty fields and complete-pair dense budget caps (`5.5s`, later `6.55s`).
- Verification: unit tests passed locally, but online feedback twice showed the cache/budget line was unsafe despite attractive public-large local hashes.
- Online evidence: first LNS submission had `high_noise_seed601=error`, `large_seed301=743.54`, `large_seed302=703.32`; then task-set-only cache with `6.55s` dense budget again had `high_noise_seed601=error`, `large_seed301=758.97`, `large_seed302=706.38`.
- Decision: fully reverted, restoring the known stable baseline behavior.
- Lesson: even performance-only/cache changes can trigger hidden high-noise failures and move dense large cases into worse online bands. Do not submit runtime/cache/dense-budget changes again from local hash evidence.
- Status: failed online, code reverted.

## Failed Experiment: Bounded Matching LNS

- Hypothesis: medium/high non-dense cases might improve if weak selected task-pair groups were removed and refilled from precomputed group options.
- Local evidence before submission: generated high-noise/medium/large302 proxy penalties improved while true dense large, low, scarce, small, and tiny stayed hash-identical.
- Online evidence: average `1000.53`; `high_noise_seed601` returned `error`, `large_seed301` worsened to `743.54`, and `large_seed302` worsened to `703.32`. Medium and low moved only slightly, not enough to offset the failure.
- Decision: reverted immediately to the safe runtime-cache line.
- Lesson: output-changing LNS based on local expected penalty is not reliable, and even gated non-dense changes can trigger hidden high-noise legality/runtime failures. Do not reintroduce LNS without first reproducing the high-noise error mechanism locally.
- Status: failed online, code reverted.

## Failed Experiment: Scarce-Only Coverage Beam

- Hypothesis: `scarce_couriers_seed401` could be improved safely by adding a strict scarce-only bitmask beam after the stable portfolio, leaving low-willingness disabled and dense large classified out.
- Code change: commit `a498d4f` added `ENABLE_SCARCE_SPECIAL=True`, a scarce pair/single beam, and disabled low fanout code.
- Local evidence: compile/tests passed; official `large_seed301` did not trigger scarce/low special locally and stayed in the known proxy band.
- Online evidence: average `756.49`; `scarce_couriers_seed401` stayed exactly `1589.86` and `38/40`, while `large_seed301` regressed to `740.55` and `large_seed302` to `706.38`.
- Decision: reverted.
- Lesson: even a post-dense, strict-scarce branch can perturb large online behavior without helping scarce. Do not add scarce beam code to the submitted file unless it replaces a proven scarce output with online evidence.
- Status: failed online, code reverted.

## Failed Experiment: Pair-Swap Repair Revival

- Hypothesis: bounded two-pair repair from commit `c4265ca` might improve non-dense medium/high-noise/low-like cases while skipping scarce and complete-pair dense cases.
- Code change: revived `pair_swap_repair()` for non-scarce, non-complete-dense instances plus a capped low-willingness `expand_multi_offers(..., max=3)` tail.
- Local evidence: unit tests passed; generated hidden-like suite improved high-noise, both generated large variants, low-willingness, and all three medium cases while scarce/small/tiny stayed unchanged.
- Online evidence: average `759.87`; high-noise, low-willingness, scarce, small, and tiny were unchanged, while `large_seed301` regressed to `750.36`, `large_seed302` to `703.32`, and medium cases also worsened versus the best stable family.
- Decision: reverted.
- Lesson: pair-swap/fixed-partition repair is another local-proxy trap. Do not revive `c4265ca` or similar non-dense pair-repair code unless the hidden large/high-noise bad-band mechanism is reproduced locally.
- Status: failed online, code reverted.

## Failed Experiment: Dense Budget Stabilization

- Hypothesis: complete-pair dense cases are not helped by extra late repair time; local public `large_seed301` falls into the stable `695.089` band at a `6.0s` dense budget, while later time slices can change output and online submissions often fall into bad large bands after code-shape changes.
- Code change: reduce `time_budget_for_instance()` for `is_complete_pair_dense_instance(instance)` from `6.8` to `6.0`, leaving all non-dense cases unchanged.
- Local evidence: true public `large_seed301` budget sweep showed `6.0` and `6.4` consistently return `695.089`; `5.2/5.6` return `701.481`; `7.2+` return `696.244`.
- Verification: compile and unit tests passed; true public `large_seed301` repeated smoke returned the same `695.089` output hash on all 4 runs; generated hidden-like cases did not trigger the dense classifier.
- Online evidence: average `761.64`; `large_seed301` worsened to `768.08`, `large_seed302` stayed in the bad `703.32` band, and no other case improved.
- Decision: reverted.
- Lesson: public large local hashes and budget sweeps are not predictive enough for online dense cases. Do not tune dense time budget again without a new scoring/legality insight.
- Status: failed online, code reverted.

## Active Experiment: Adopt 719 Reference Baseline

- Trigger: user provided `solution_719.61(1).py`, an online-scored reference solution around `719.61`.
- Hypothesis: the main gap is not another small repair on the 747 family; the reference solution's expected-cost grouping model is closer to the hidden judge even though our local proxy often ranks it worse.
- Code change: replace the submitted `MT-4-autosolver/submission.py` with the provided 719 reference solver as a new baseline.
- Local evidence: under our proxy evaluator, the reference is not uniformly better (`large_seed301` and generated medium/high cases are worse), which confirms the proxy is unreliable and online evidence should dominate.
- Online evidence: average `719.61`; every listed case improved versus the old 747-family baseline except tiny stayed tied, with the biggest remaining penalties in `low_willingness_seed501=1806.07` and `scarce_couriers_seed401=1588.94`.
- Guardrail: previous stable baseline remains recoverable at commit `4d83bf0`; this submission is intended to establish a stronger online floor before further hybridization.

## Active Experiment: Targeted Extra Search for Low/Scarce

- Hypothesis: the 719 baseline still uses only a `0.80s` internal budget for medium-sized low-willingness and scarce-courier cases; giving only these two identifiable families more local-search time can improve the two dominant remaining penalties without perturbing large/high/medium.
- Code change: in `_time_budget()`, for `tasks >= 25`, `candidate_count <= 20000`, and either average willingness below `0.16` or fewer couriers than tasks, return `7.0s`; all other budgets stay unchanged.
- Local evidence: generated `low_willingness_seed501` improved under the 719 model from about `1589/1545` prop/seq to `1497/1453`; generated `scarce_couriers_seed401` improved from about `1624/1530` to `1605/1505`.
- Online evidence: average stayed exactly `719.61`; low and scarce scores did not move, so extra time alone is not a useful lever.
- Lesson: keep the budget only as headroom for structural scarce/low candidates; do not submit further time-only changes.

## Active Experiment: Scarce Courier-Aware Pair Seed

- Hypothesis: `scarce_couriers_seed401` is a grouping/coverage issue, not a runtime issue. The 719 solver defines `_make_courier_greedy_grouping()` but never calls it; adding it as one more scarce-only seed can import the old pair-heavy/courier-aware behavior without reviving old broad repair.
- Code change: when `len(all_couriers) < n_tasks`, consider `_make_courier_greedy_grouping()` for alpha `10/25/50/75` under the exact `seq` model before the standard pair-threshold loop.
- Local evidence: on generated scarce, `_make_courier_greedy_grouping(alpha=50, seq)` improves the 719 seq proxy from about `1505` to `1483`, while the branch is not called for large/high/medium/low/small/tiny.
- Risk: hidden scarce may still differ from the generator, but this is a candidate-generation change tightly gated to the observed `39/40` shortfall.
- Online evidence: average stayed exactly `719.61`; all case scores were unchanged, including `scarce_couriers_seed401=1588.94` and `39/40`.
- Lesson: adding scarce seeds without changing the pair/single partition search does not move hidden scarce. Future scarce attempts need a structural repartition or final-selection change, not more seed variants.
- Status: online no-op; retained only as a safe scarce seed for later structural search.

## Active Experiment: Low Multi-Offer Grouping + Scarce Repartition

- Hypothesis: the 719 baseline's main low-willingness miss is that grouping uses the best single first-offer saving, while low probability cases need pair/single choices that account for two-offer acceptance. The scarce miss may be a wrong pair/single decomposition, so the dormant repartition operator should be tried under a strict scarce gate.
- Code change: add a strict low-willingness classifier excluding complete-pair dense large cases; for low-like cases, evaluate pair/single grouping candidates with cached two-offer sequential savings and use `seq` as the selection model. For scarce-like cases, fix `_try_state()` failed-state caching and run `_local_repartition()` on forced-pair and courier-aware groupings.
- Local evidence: generated hidden-like low improved from `seq=1544.972 / prop=1589.023` to `seq=1467.012 / prop=1546.973`; generated high-noise, large, medium, scarce, small, and tiny outputs stayed hash-identical except scarce spent extra time without changing local output.
- Guardrail: true provided `large_seed301.txt` stayed hash-identical to the 719 baseline across 3 runs with `prop=667.084`, so the low classifier did not leak into the dense public large case.
- Risk: online low may not match the local low generator; scarce repartition may remain a no-op if the hidden issue is final ranking rather than decomposition.
- Online evidence: average moved only from `719.61` to `719.50`; low improved `1806.07 -> 1804.94`, while scarce and every other case stayed unchanged.
- Lesson: the low gate is real and safe, but hard-switching low final selection to `seq` is too weak. The online scorer aligns closely with local `prop` on the provided `large_seed301`, so the next attempt should treat prop as the final penalty selector while still using seq as a candidate generator.

## Active Experiment: Prop-Aligned Final Selector for Low and Scarce

- Hypothesis: the leaderboard penalty is closer to `_prop_expected_value()` than the scalar sequential surrogate; the provided `large_seed301.txt` online score `667.11` matches local `prop=667.084`, not local `seq=626.165`. Low/scarce can still use seq candidates, but final selection should prefer prop when coverage does not fall.
- Code change: low-like cases now keep the 2-offer grouping candidates but return to the normal prop final selector. Scarce-like cases generate a prop shadow assignment for the same scarce groupings and may select it only when it does not reduce coverage; a bounded coverage override remains only if extra coverage costs at most `40` prop points.
- Local evidence: relative to `9886d7c`, generated hidden-like low changed from `prop=1509.587` to `1496.676`; generated scarce changed from `prop=1624.352` to `1611.459` with the same `40/40` coverage; high-noise, large, medium, small, and tiny output hashes stayed unchanged.
- Guardrail: true provided `large_seed301.txt` stayed hash-identical across 3 runs with `prop=667.084`.
- Risk: if hidden scarce is scored closer to seq than prop, the prop shadow can worsen scarce despite preserving coverage. Online large evidence makes this risk acceptable for one targeted probe.
