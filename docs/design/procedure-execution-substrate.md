# Procedure Execution Substrate

## Goal

Hermes should not jump from prompt text directly to actuator ranking. A goal
should first be mapped to a declarative procedure, and that procedure should
provide the ordered subgoals that steer perception and action toward a
convergent path.

## Design

- Procedures are JSON-backed and generic.
- The core selector chooses the best matching procedure from the prompt,
  goal kind, app, and task vocabulary.
- A procedure describes ordered stages, required bindings, recovery hints, and
  confidence thresholds for irreversible steps.
- The active stage is a first-class runtime signal. The controller should
  compute it from the current world state and expose it to perception,
  candidate generation, and the selector.
- Leaf overlays may contribute app-specific semantics, but they do not own the
  procedure itself.
- The controller should treat the selected procedure as a middleware layer
  between user intent and actuator choice.
- UI and terminal entry points must both derive the same structured goal
  contract before execution. The UI may add the contract to `system_message`,
  but it must not invent its own alternate task shape when the prompt already
  matches a supported procedure family.

## Contract

1. Read the prompt and current goal.
2. Auto-select the best matching procedure definition.
3. Bind the procedure to the goal.
4. Emit procedure stage objectives as the ordered intent hypotheses.
5. Let the world model, capability graph, and current procedure stage decide
   which actuator is safe.
6. Record success / failure memory against the procedure family and goal
   family.
7. Reuse the same contract-fingerprinted model binding in UI and terminal so
   composer defaults cannot drift from the backend runtime default.
8. Treat canonical prompt regressions such as
   `find the zarooratwala link sent to kulvinder on whatsapp and forward to
   pallavi` as first-class members of the forward-message procedure family, not
   as ad hoc terminal scripts.

## Why this matters

The system has been missing a stable intermediate representation between prompt
interpretation and low-level navigation. Procedures give the agent a reusable
shape for hard tasks like WhatsApp message retrieval and forwarding, so the
loop can converge instead of thrashing between visually plausible but
goal-irrelevant controls. The `zarooratwala` forward prompt is the current
canonical regression for that contract: if the prompt enters through the UI,
the terminal runner, or a benchmark harness, it should bind the same
`whatsapp_forward_message` procedure and preserve the same source-first stage
ordering.
