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
