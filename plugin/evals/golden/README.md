# Hermes module golden corpus

Eval-only, versioned ground truth for **individual cognitive modules** and
**cross-module flows**.

This is not training data. It is the gold standard you run every change against
so a regression names the *layer* that broke (perceive / critic / meta / brain /
actor / handoff / reflect / flow) instead of only “the zarooratwala task failed.”

**Phenomenon curriculum** (environmental blockers, prerequisite children,
effect verification, trajectories) lives beside this track in
[`plugin/evals/phenomena/`](../phenomena/README.md) — organized by phenomenon,
seeded from live runs (e.g. `20260810_161105`), with harvest → annotate → promote.

**Promotion policy (mandatory):** after every live run, freeze **each new failure
and each new success** as a golden — module case for a single layer, `flow/`
case when the bug spans modules (e.g. surprise → reflect diagnosis → brain).
Tag with the run stamp (`145239`). Never leave a diagnosed stall without a case.

## Layout

```text
corpus/v1/
  perceive.jsonl
  critic.jsonl
  meta_action.jsonl
  brain.jsonl
  actor.jsonl
  brain_actor_handoff.jsonl
  reflect.jsonl
  flow.jsonl           # cross-module recoveries
  ui.jsonl             # UI recoverability (wrong selection → revert_effects)
  _manifest.json
candidates/          # harvest output — NOT gold until a human promotes it
```

## Discipline

1. **Eval only** — never train on these labels.
2. **Version freeze** — `v1` does not casually change. Material gold edits go in
   `v2` with a changelog note in the new manifest.
3. **Failure first** — every live stall should be frozen here with human gold.
4. **No self-scoring** — do not set gold fields from the recorded model reply
   for the same field being scored (see `plugin/evals/annotations.py`).
5. **Screenshots stay out of git** — cases may reference
   `plugin/experiments/fixtures/perceptor/live_forward/<name>.png`.

## Modules

| Module | What gold asserts |
| --- | --- |
| perceive | surface, open conversation, target visibility, no search-chrome open |
| critic | accepted surface/open after a proposal; refuse search-field chrome as open |
| meta_action | next meta move (reflect on surprise / perceive / act / …); never hard VERIFY preempt |
| brain | capability family on accepted world (e.g. locate_content after open) |
| actor | complete motor brief lands (or refuses); no re-choice; field_role / open_search_ui; perception-confirm stale refuse |
| brain_actor_handoff | brain next_action + world → ActorBrief; also `perceptor_brain_actor` pipeline (objects → consultation → brief) |
| reflect | surprise → REFLECT; discovery inputs; `diagnosis_seed` (ReflectDiagnosis); brain *consumes* repair (block-repeat / re-ground / override Observe) |
| flow | Cross-module: e.g. measured surprise + weak model → finalize diagnosis → brain repair (145239 Forward picker miss) |
| ui | UI recoverability: selection consistency, `revert_effects` plan/approve/execute, post-revert reselect (132831 wrong multi-select) |

Live zarooratwala **actuation** failures (perceive/brain OK, motor wrong) are frozen under
`actor/live_*` and `brain_actor_handoff/live_*` (132948 picker Cmd+F, 135732 reveal point
overwritten by sidebar AX, 131333 destination contact vs message).

**Action-area / wrong-grounding resistance** (app-agnostic): capabilities bind to a logical
region (`filter_input`, `content_object`, `candidate_row`, …) via
`plugin/agent/capabilities/action_area.py`. High error-cost families (type into filter,
irreversible commit) refuse in `validate_brief` when the bound kind/label is outside that
area — even if an earlier stage latched a matches_goal row. Frozen under
`brain_actor_handoff/type_binds_filter_*`, `type_refuses_when_only_wrong_area_geometry`,
`live_095344_*`, and `actor/refuse_type_wrong_action_area_*`.

Live **reflect/flow** failure **145239**: menu Forward via `AXPress … in background`,
predicted `forward_picker`, got selection chrome (`1 Selected` + toolbar Forward);
decision chose Observe — frozen under `reflect/live_145239_*` and
`flow/live_145239_*`.

Live **ui** failure **132831**: wrong multi-select (`2 Selected` = zarooratwala + Chunni);
must `invoke_revert_effects` (Escape clear) then reselect — never toolbar Forward.
Frozen under `ui/live_132831_*` (+ 145239 correct-selection regression in `ui/`).

Live **perception-confirm** refusals (rectangle no longer matches before write) are frozen
under `actor/live_*_confirm_*` with `input.perception_confirm` replaying the observed
verdict (152420 wrong OCR, 153356 scrolled list, 041742 Cursor foreground, 045430 empty OCR).

## Anti-regression loop (mandatory)

```text
python -m plugin.evals.check          # mvn-test equivalent (required preflight)
    → live run / stall
    → supervise harvests candidates/
    → human fills gold → promote
    → check must stay green before the next live run
```

Live agent startup is hard-gated on a green package check (server-boot analogy):

1. `python -m plugin.evals.check` must pass (any golden/gate/pytest failure → exit 1)
2. Only then may a live prompt run (`run_forward_zarooratwala.command`,
   `run_forward_message*`, `run_call_pallavi_live`, or any `HERMES_LIVE_GOAL=1`
   closed loop)

`run_goal_closed_loop` refuses to start when `HERMES_LIVE_GOAL=1` unless the
check already passed in-process / via `HERMES_EVAL_PREFLIGHT_DONE=1`.
There is no skip env — red evals always block launch.

Every diagnosed stall or success becomes a case. The gate fails on **any**
failing case id that is not listed in `_manifest.json` → `known_gap_case_ids`
(explicit open debt only — never a silent average).

## Commands

```bash
# Package check — goldens + gates + focused pytest (like mvn test)
python -m plugin.evals.check
python -m plugin.evals.check --quick   # goldens+gates only

# Score frozen gold against current code
python -m plugin.evals.golden.score

# Harvest annotation candidates from zarooratwala run logs (not auto-gold)
python -m plugin.evals.golden.harvest_run --runs plugin/experiments/runs --limit 6

# Promote a human-checked case (bumps manifest)
python -m plugin.evals.golden.promote --case /tmp/case.json --score

# Draft from a harvest line (still needs gold filled in)
python -m plugin.evals.golden.promote \
  --from-candidate plugin/evals/golden/candidates/<stamp>.jsonl --index 0 --dry-run

# Included in the pyramid report / hard gates
python -m plugin.evals.run
```

## Promoting a failure **or** success

1. Freeze inputs (packet / workspace / meta context / measured reflect facts)
   from the run — include executor message, predicted vs observed surface,
   post-world objects. Prefer harvest candidates for the stamp.
2. Write human gold (decision structure, not LLM prose): expected capability,
   repair kind, points, forbidden moves.
3. `python -m plugin.evals.golden.promote --case case.json` (or append a line to
   the right `corpus/vN/<module>.jsonl` / `flow.jsonl` and bump the manifest).
4. Additive only — do not rewrite existing case ids. Tag with run stamp.
5. Run `python -m plugin.evals.golden.score` and a focused pytest on the new id.
   New reds outside `known_gap_case_ids` fail CI.

### ReflectDiagnosis scenarios (`reflect.jsonl`)

| `input.scenario` | Scores |
| --- | --- |
| `meta` | surprise → meta REFLECT |
| `discovery` / `packet` | intended vs landed + hypotheses |
| `diagnosis_seed` | runtime seed / merge → cause, locus, repair |
| `brain` | apply_surprise_explanation (incl. repair override) |
| `brain_reground` | consultation applies corrected_point |

### Flow scenarios (`flow.jsonl`)

| `input.flow` | Scores |
| --- | --- |
| `reflect_repair` | seed+finalize+brain: capability, geometry, motor_constraint |
| `act_intention_reperceive` | stamp act intention → pre-look PERCEIVE → score mismatch → REFLECT |
