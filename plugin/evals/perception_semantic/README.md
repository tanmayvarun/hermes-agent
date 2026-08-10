# Semantic perception goldens

Eval for **world understanding**, not “did it eventually click the right button?”

Every production perception failure should land here as a frozen case that tests,
independently:

| Layer | Question |
| --- | --- |
| Surface reconstruction | Base + foreground / active interaction surface |
| Ownership | Claims/objects bound to the correct owner surface |
| Predicate / typed state | `source_message_selected_count` ≠ `destination_selected_count` |
| Cross-surface isolation | Evidence from surface A cannot satisfy predicates of surface B |
| Affordance extraction | Grounded actions on the active surface |
| Task-conditioned actions | Acceptable next actions for the current intention |
| Forbidden actions / safety | e.g. Forward commit inadmissible without destination |
| Production projector | Real `_build_messages` path (ownership addendum + executive question) |

## Seed family (live 184742)

Phenomenon tags: `nested_surfaces`, `cross_surface_selection`, `foreground_authority`,
`selection_state_typing`.

Canonical case:

`fixtures/cross_surface/whatsapp_forward_picker_source_1_dest_0.json`

- Packet: goal + AX with parentage + executive destination question + frontier
- Screenshot: `plugin/experiments/fixtures/perceptor/cross_surface_184742/frame_0001.png` (not in git)
- Annotated world: picker foreground, source count=1 on conversation, destination count=0
- Contaminated reply: `destination_selected=true` from background chrome (must be detected, then scrubbed)
- Forbidden: `destination_selected=true` from source-selection ownership

Metamorphic expansion (`--expand-metamorphic`):

- background selected count 1→2→3 (destination stays false)
- destination name Tanmay→Rahul
- causal positive: recipient checkbox selected → destination_selected true

## Run

```bash
python -m plugin.evals.perception_semantic
python -m plugin.evals.perception_semantic --expand-metamorphic
python -m plugin.evals.perception_semantic --json
```

CI gate: `semantic_perception_zero_cross_surface_contamination` (package check).

## Adding a live failure

Prefer the harvest → annotate → promote loop:

```bash
# Preferred: full production packet from a recorded frame
python -m plugin.evals.perception_semantic.harvest_failure \
  --from-frame plugin/experiments/fixtures/perceptor/live_forward/frame_0284.json

# Or: auto-detect contamination / forbidden-commit steps in a live run
python -m plugin.evals.perception_semantic.harvest_failure \
  --from-run /tmp/hermes-runs/20260809_184742 --auto-fail

# Annotate eval_candidates/<id>/annotation.json, then:
python -m plugin.evals.perception_semantic.promote \
  --candidate eval_candidates/run_20260809_184742_step_0015 \
  --phenomenon cross_surface
```

Each candidate freezes:

```text
screenshot + ax + executive_context + model_input + model_output + transition
```

Enable automatic candidate dumps on the next live run:

```bash
export HERMES_PERCEPTOR_RECORD_DIR=plugin/experiments/fixtures/perceptor/live_<stamp>
export HERMES_PERCEPTION_EVAL_CANDIDATES_DIR=plugin/evals/perception_semantic/eval_candidates
```

Manual path (still valid):

1. Freeze `packet` + screenshot under `plugin/experiments/fixtures/perceptor/<stamp>/`
2. Copy a case JSON under `fixtures/<phenomenon>/`
3. Annotate surfaces, typed claims, affordances, acceptable/forbidden actions
4. Optionally attach the bad model reply as `contaminated_response`
5. Tag `phenomena` (not only `app`)
