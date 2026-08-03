# World-model critic (propose → review → act)

**Status:** Active — structural critic realized; soft LLM critic optional later.

## Contract

```text
sensors + affordance frontier → multimodal perceptor → proposal packet
                ↓
     world critic (accept / reject / edit + reasons)
                ↓
        accepted world document
                ↓
   decision consultation (which capability advances the goal?)
                ↓
   capabilities + motors admissible on that node
                ↓
     runtime facts written back as evidence
```

The perceptor does heavy multimodal work. It does **not** commit belief state,
and it does **not** get the last word on the next move. The critic merges a
residual update into the prior accepted document; the decision-maker then picks
one capability over that accepted world.

What the perceptor is given, and the ranked action frontier it returns, are
described in [affordance-frontier.md](affordance-frontier.md). The critic and
the decision stage below operate on the document that call produces.

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
paths, or click scripts. Grounding stays with the perceptor: when the decision
keeps a pointer-shaped family, the perceptor's `target_point` / `target_id`
ride along.

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
