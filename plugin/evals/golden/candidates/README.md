# Golden annotation candidates

Output of `python -m plugin.evals.golden.harvest_run`.

These lines are **not gold**. They are frozen failure/interest snippets from
zarooratwala run JSONL for a human to promote into `corpus/vN/<module>.jsonl`
with checked labels.

Prefer promoting:

- `transition_eval` / `verification` with `outcome=regression`
- `executive_judgement` with `meta_action` in verify/think after an open
- `stalled` + slow `screen_understanding`
- `ax_settle_regression_diagnostic`
