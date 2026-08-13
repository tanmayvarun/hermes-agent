# Interface Foundation Model

## Goal

Hermes should learn UI tasks from interface-state transitions, not from
hardcoded click sequences.

The core question is:

> given the current perceived UI state and a candidate action, what next state
> is most likely, and is that action worth taking?

That keeps the control loop generic while allowing app-specific behavior to
live only at the edges.

The generic core also needs to synthesize prompt-level intent before it
chooses actuators. A goal is not just a contact name or a surface label; it is
an ordered set of subgoals such as "find the source content", "inspect the
timeline", and "choose the destination". Leaf overlays may describe the
surface, but they must not own this decomposition.

The preferred mechanism for that decomposition is a declarative procedure:
the core should auto-fetch the best matching procedure for the prompt, bind it
to the goal, and use the procedure stages as the next-level intent hypothesis.

The same work loop must be shared by every user-facing surface. The CLI, TUI,
desktop app, and Terminal-launched runners are just hooks into the same
observe → decide → act → observe controller; they may render different chrome,
but they must not own separate task semantics or separate notions of progress.
Run-relative clocks and no-progress watchdogs belong to the shared work loop,
while the UI turn clock is only a presentation aid.

**Client vs runtime (locked roof):** see
[`personal-agent-brain-and-substrates.md`](personal-agent-brain-and-substrates.md).
Clients are adapters; cognition and execution policy live in HermesRuntime.
Current code still has chat (`AIAgent`) vs executive closed-loop
(`run_goal_closed_loop`) divergence — documented there as debt to converge
behavior-preservingly, not as a second architecture.

## Core principle

- Core learning stays generic across apps.
- App-specific knowledge stays in thin overlays and leaf policies.
- The model should reason over state, action, confidence, and outcome.
- The agent should reuse trajectory memory across related goals when the
  interface family is similar.

## What the core learns

- state signatures and state buckets
- action families and their observed outcomes
- progress vs no-effect vs regression signals
- success and failure memory for related goals
- confidence calibration for risky or irreversible actuators
- prompt-derived subgoals and intent hypotheses
- procedure selection and procedure-bound stage ordering

## What the leaves may learn

- app vocabulary and aliases
- surface-specific semantic labels
- local progress signals for a given app
- extra parsing hints for a specific overlay
- prompt-to-intent annotations that help the core rank plausible next steps

Leaf learning may improve perception, but it must not encode step-by-step
policy or actuator preference.

## Decision contract

The controller should treat each candidate action as a hypothesis:

1. observe the current state
2. synthesize prompt-level subgoals from the user's intent
3. generate plausible candidate actions
4. score them with generic policy and memory
5. use higher confidence for irreversible actions
6. observe the next state and record the transition
7. update success and failure memory

That loop replaces brittle heuristics with reusable experience.

## Trajectory memory

Trajectory memory should store both:

- exact-goal signal, for precision
- family-level signal, for reuse across related tasks

For example, voice-call and video-call goals should share broad trajectory
knowledge while still keeping their exact signatures separate.

## Non-goals

- No app-specific click scripts in the core
- No hardcoded actuator choice from label text alone
- No fixed WhatsApp-only recovery rules in the generic controller
- No heuristics that bypass the model when perception is uncertain
