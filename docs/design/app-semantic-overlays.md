# App Semantic Overlays

Hermes should keep a generic world model at the core and allow thin
app-specific semantic overlays at the edges.

The core world model is responsible for the reusable facts:
- entities, labels, bounds, visibility
- scene regions and screen segmentation
- pragmatic roles and capability grounding
- confidence, risk, and reversibility signals
- goal-conditioned content-object discovery and binding

An app-specific overlay is responsible for the meanings that are unique to one
surface:
- active conversation headers
- app-specific affordance phases
- surface-specific progress signals
- bindings that only make sense inside that app's vocabulary

The overlay may expose read-only derived hints back to the core, including
surface labels, candidate regions, and visibility signals. It should not be the
place where prompt intent is decomposed into subgoals; that remains a core
responsibility so the same reasoning loop works across apps.

The overlay may also expose thin, read-only hints about model-backed
perception or action priors, but it must never own the model registry or the
ranking policy. The core decides which screen parsers, grounding models, or
computer-use priors to call.

Prompt-to-procedure selection also lives in the core. If a prompt needs a
convergent execution shape, the generic procedure registry should attach that
shape to the goal before the overlay contributes surface-specific hints.

The overlay must stay thin. It should derive from the generic world model and
the generic capability system, not replace them. Its job is to interpret the
world, not to plan actions or rank actuators.

## Content objects

When a surface contains messages, notes, files, or search hits, the overlay
should expose them as normalized content objects and stop there. The generic
core then:

- scores candidate objects against the goal
- reranks ambiguous cases with an LLM
- binds the chosen object to the task

That means a WhatsApp overlay may expose message rows, URL metadata, sender
names, timestamps, and container context, but it should not decide which row
is the source message. The object-discovery core owns that choice.

## Core vs leaf learning

The core perception stack should stay reusable across apps:

- sensor fusion
- OCR and other fallback visibility channels
- screen parser models such as OmniParser-style element extractors
- action-prior models such as UI-TARS, ShowUI, OS-Atlas, or hosted computer-use APIs
- confidence calibration
- risk / reversibility gating
- world-model updates and recovery

The leaf layer may learn app-specific semantics over time:

- surface vocabulary and aliases
- region cues for that app's layout
- affordance names that only make sense in that app
- recovery hints after the generic path is uncertain

Those learned leaf signals are annotations, not policy. They can improve what
the core sees, but they must not decide the action themselves.

## WhatsApp training ladder

WhatsApp is a good example of why the core must learn before it acts.
Forwarding and calling are not the first lesson. The agent should first learn
to read the chat, then understand which visible thing is the source message,
and only later treat the message as a candidate for forwarding.

The recommended training order is:

1. Read the chat list and identify the current conversation.
2. Read the latest visible message in a conversation.
3. Locate a specific message or link in the source thread.
4. Distinguish text, link, media, and document surfaces.
5. Scroll and backtrack without losing the source thread.
6. Forward the found content to a destination contact.
7. Handle overlays, picker chrome, and ambiguous surfaces.

For this ladder, contact rows are only gateways into the source chat. They are
not evidence that the message content itself has been found.

## Design rules

- Keep per-app semantic parsing isolated to the overlay layer.
- Prefer reusable primitives in the world model, scene graph, and capability
  graph before adding app-specific branches.
- Keep procedure selection and stage ordering in the core; overlays only
  provide bindings and surface vocabulary.
- Do not move task policy, actuator selection, or confidence gating into the
  overlay.
- If an app-specific concept can be named generically, prefer the generic
  primitive and let the overlay map to it.
- App overlays may expose derived fields such as `open_conversation`,
  `search_query`, or `forward_phase`, but only as read-only semantic views.
- App overlays may adapt from history, but only by emitting better semantic
  descriptions and confidence-bearing hints. They may not hardcode step-by-step
  flows or actuator preferences.
- App overlays may help the core see why a prompt is promising, but they must
  not turn that into a fixed sequence of actions.

## Why this exists

Some UI systems expose meaningful app semantics only through a combination of
layout, labels, and local vocabulary. A thin overlay lets Hermes understand
those semantics without spreading app knowledge through the generic control
loop.

That keeps the architecture reusable:
- new apps can add their own thin overlay when needed
- generic perception stays shared
- irreversible action policy remains centralized
- the model still gets the final say when choosing among candidate actuators
