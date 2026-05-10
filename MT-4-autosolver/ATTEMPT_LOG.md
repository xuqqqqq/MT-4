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
- Planned code change: cache each candidate's sorted task set and task count during parsing, then cache penalty fields and cap complete-pair dense runtime to avoid a previously bad local hash.
- Verification: unit tests passed locally, but online feedback showed the dense cap/cache line was not safe enough.
- Online evidence: during the LNS submission, `large_seed301` scored `743.54` even though LNS was skipped for complete-pair dense inputs; this implicates the runtime-cache/dense-budget line rather than LNS. `large_seed302` also remained in the bad `703.32` band.
- Decision: reverted together with LNS fallout, restoring the known stable baseline behavior.
- Lesson: even performance-only/cache changes can move deadline-sensitive outputs into worse online bands. Do not submit runtime/cache changes unless the exact online stable hash is preserved or the online score is already confirmed.
- Status: failed online, code reverted.

## Failed Experiment: Bounded Matching LNS

- Hypothesis: medium/high non-dense cases might improve if weak selected task-pair groups were removed and refilled from precomputed group options.
- Local evidence before submission: generated high-noise/medium/large302 proxy penalties improved while true dense large, low, scarce, small, and tiny stayed hash-identical.
- Online evidence: average `1000.53`; `high_noise_seed601` returned `error`, `large_seed301` worsened to `743.54`, and `large_seed302` worsened to `703.32`. Medium and low moved only slightly, not enough to offset the failure.
- Decision: reverted immediately to the safe runtime-cache line.
- Lesson: output-changing LNS based on local expected penalty is not reliable, and even gated non-dense changes can trigger hidden high-noise legality/runtime failures. Do not reintroduce LNS without first reproducing the high-noise error mechanism locally.
- Status: failed online, code reverted.
