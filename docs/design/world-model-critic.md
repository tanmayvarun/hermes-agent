# World-model critic (propose → review → act)

**Status:** Active — structural critic realized; soft LLM critic optional later.

## Contract

```text
stage0 assemble (screenshot + OCR geometry + AX + passive frontier)
                ↓
stage1 multimodal → world proposal + suggested_actions[] (why)
                ↓
world critic (accept / reject / edit + reasons)
                ↓
current-node affordance closure (same-node reversible probes / soft fold)
                ↓
accepted world + closed frontier + suggestion whys
                ↓
executive / brain — one capability (or request another look)
                ↓
runtime execute → thin motor feedback (ok/fail)
                ↓
must re-perceive (stage1) before next capability
```

**One-executive contract:** Screenshot multimodal (+ critic) is the sole source
of truth for the world document. AX + OCR ground clicks only. Post-act AX settle
/ TransitionEvaluator is diagnostic logging — it must not set executive surprise
or preempt the brain with VERIFY. After any non-observe act,
`must_executive_reperceive` forces the next stage1 look.

Stage1 proposes the world and may visually rank suggestions; it does not
commit belief or execute. The critic settles the world document. Affordance
closure then completes the **current UI node** (including stimulus-revealed
options). The brain picks one move over that closed set. See
[affordance-frontier.md](affordance-frontier.md).

## Decision consultation

`plugin/agent/decision_consultation.py` runs after the critic and before any
motor. It is consulted with four inputs and returns one capability:

| Input | Contents |
| --- | --- |
| accepted world | surface, open conversation, focused field role, objects, beliefs |
| task state | phase, source-chat match, located/visible content, attempts, exhausted |
| navigation | reachable surfaces and the capability that opens each, forbidden capabilities |
| goal | source conversation, content query, destination |

Output is `{capability, target, why, confidence}` — never coordinates, menu
paths, or click scripts. Grounding uses the accepted world `objects` (and
frontier targets): pointer-shaped families resolve to `target_id` /
`target_point` from the perceived inventory, not from a perceptor-ranked
`next_action`.

Phases are derived from the accepted world, not from a stored recipe:

```text
choose_destination   surface == forward_picker
invoke_forward       surface == context_menu
reach_source         intended source chat is not the open one
hunt_content         source chat open, queried content not yet reachable
act_on_content       content located or visible
```

Safety is enforced by sanitizing the choice rather than trusting the model:
unknown capabilities, capabilities the navigation graph forbids (sidebar search
on a picker), `locate_content` outside the intended source chat, and
`commit_irreversible` before a commit phase are all rejected. A rejected choice
falls back to a deterministic heuristic over the same brief, so the loop keeps
running with no model reachable.

Toggles: `HERMES_DECISION_CONSULTATION=0` disables the stage entirely;
`HERMES_DECISION_LLM=0` keeps the stage but uses the heuristic chooser only.

## What the critic owns

- Surface identity and legal parent/child jumps (navigation graph)
- `focused_field_role` (sidebar_search vs destination_filter vs …)
- Refusing to wipe `open_conversation` on conversation-descended surfaces
- Emitting gates: `forbid_sidebar_search_motor`, `forbid_source_compose_remap`

## What control must obey

- `ax_starved → compose+type` is illegal on `forward_picker` / dialog / menu
- `ax_type` uses Cmd+F only when accepted role is sidebar search
- Keyboard-open hints apply only on sidebar-search surfaces

## Soft vs hard

| Field | Policy |
| --- | --- |
| surface, field role, open conversation | hard structural gate |
| objects, beliefs, progress notes | soft — prefer proposal when present |

## Implementation

- `plugin/agent/world_critic.py`
- `persist_world_document` in `unified_cognition.py` critiques before store
- `consult_next_capability` in `unified_cognition.py` runs the decision stage
  immediately after the critic accepts the document
- `plugin/agent/decision_consultation.py` builds the brief, consults, sanitizes
- `plugin/agent/affordance_frontier.py` supplies the action topology the
  perceptor reasons over before any of this runs
- Forward-message executor reads `sidebar_search_forbidden(execution_state)`

## Eval

High-level representation checks (not motor/pixel scoring):

```bash
python -m plugin.experiments.world_critic_eval
# or
python -m plugin.experiments.perceptor_eval --frames <dir> --world-critic-scenarios
```

Scenarios cover legal open, picker→search rejection, open-conversation preserve,
field-role coercion, residual progress keep, and a multi-step forward-flow
trajectory that ends by refusing sidebar-search drift on the picker.
