# Affordance frontier (current-node closure → brain transition)

**Status:** Active — stage0 passive frontier → stage1 suggestions → critic → same-node closure → brain.

A world model that knows only which objects exist is not enough. The agent must
know what can be done **on the current UI node**, including controls that appear
only after a reversible stimulus (hover, dropdown, context-click). Those reveals
still belong to the **same node**. The **next node** is one brain-chosen
transition away.

```text
stage0: screenshot + OCR geometry + AX + passive frontier
        ↓
stage1 multimodal: world proposal + suggested_actions[] (why)
        ↓
world critic: accept / reject / edit Δworld
        ↓
current-node closure (affordance_explore): reversible probes / soft fold
        ↓
executive/brain: one capability over accepted world + closed frontier
        ↓
runtime execute → thin motor ok/fail → must stage1 re-perceive → restart
```

AX settle after act is diagnostic only; it does not choose VERIFY or rewrite
world belief. See world-model-critic.md (one-executive contract).

## Node model

| Concept | Meaning |
| --- | --- |
| **Current node** | Everything available in this interaction state, including stimulus-revealed menus/toolbars |
| **Same-node probe** | Hover / reveal_actions / open dropdown — does not leave the node |
| **Transition** | Brain-executed capability that changes state (open chat, Send, navigate) |
| **Closure** | While processing the current node, identify and add all same-node affordances before choosing a transition |

Each frontier entry carries `node_scope`: `current` | `transition`.

## Three classes (within a node)

| Class | Packet field | Meaning |
| --- | --- | --- |
| visible | `observed_actions` | available right now |
| latent | `latent_actions` | same-node; needs named trigger |
| hidden / probe | `probe_actions` | unknown; worth a reversible stimulus |

## Stage1 suggestions + affordance QC

The multimodal model may return `suggested_actions[]` with `why` — visual
ranking over the frontier. Advisory only. The brain may follow or override.

When stage0 already surfaced candidate affordances, stage1 also emits
`affordance_qc: {expected_found, missing, notes}` — internal quality control
before perception returns to the brain (did we figure out Forward / Send?).

## Resilience (barren frontier → reperceive)

If the closed frontier still lacks task-critical same-node labels (e.g. Forward
on a zarooratwala message conversation), the brain treats the node as barren:

- heuristic prefers `observe` with an explicit gap reason
- LLM choices that assume the missing latent (transitions / commits) are
  overridden to `observe`; same-node gap closers (`reveal_actions`,
  `select_content`) still run
- `request_reperceive` sets `last_perception_query` so the next look hunts for
  the missing affordances

## Evals (Zarooratwala)

`plugin/evals/affordance_exploration.py` scores real corpus I/O for:

1. critical latent recall (Forward / Reply / Copy; Send on picker)
2. node-closure completeness
3. stage1 `affordance_qc` honesty
4. brain barren → reperceive resilience

```bash
python -m plugin.evals.affordance_exploration
```

## Implementation

- `plugin/agent/affordance_frontier.py` — passive assemble
- `plugin/agent/affordance_explore.py` — post-critic `close_current_node_frontier`
- `_frontier_for_packet` / stage1 prompt in `unified_cognition.py`
- `plugin/agent/brain.py` — sole chooser after closure; barren reperceive
- `plugin/evals/affordance_exploration.py` — zarooratwala affordance evals

Toggles:

- `HERMES_AFFORDANCE_FRONTIER=0` — omit passive frontier from packet
- `HERMES_PERCEPTION_NODE_CLOSURE=0` — skip post-critic closure
- `HERMES_PERCEPTION_EXPLORE=1` — enable motorized probes (when wired)
