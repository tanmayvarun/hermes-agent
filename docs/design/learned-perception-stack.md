# Learned Perception Stack

Status: design note

## Goal

Make perception a learned, transformer-centric representation subsystem that
produces a trustworthy, temporally stable world model before the controller
tries to plan harder.

Perception should not be a single prose-producing model call. It should be a
typed subsystem that combines deterministic sensors, learned semantic
reconstruction, temporal reconciliation, uncertainty tracking, and explicit
validation.

## Core principle

The target architecture is:

```text
AX + screenshot + OCR + prior frame + action history
→ deterministic sensor association
→ transformer semantic reconstruction
→ typed scene / object / relation / capability outputs
→ temporal reconciliation
→ contract validation
→ belief update
→ controller
```

That keeps perception responsible for representation, while the control loop
remains responsible for branch choice, risk gating, and backtracking.

## Typed perception contract

Perception should emit a structured result, not a prose summary:

```python
PerceptionResult(
    surfaces=...,
    objects=...,
    relations=...,
    capability_hypotheses=...,
    transition_interpretation=...,
    ambiguities=...,
    quality=...,
)
```

### Surfaces

Semantic interface areas:

- application window
- conversation pane
- message timeline
- composer
- sidebar
- header
- context menu
- call picker
- modal

### Objects

Meaningful semantic objects:

- conversation
- contact
- group
- message
- URL
- attachment
- input field
- menu item
- toolbar control

### Relations

Typed relationships between objects:

- message belongs_to conversation
- URL contained_in message
- menu anchored_to control
- Voice item belongs_to call picker
- mic belongs_to composer

### Capability hypotheses

Relational capabilities with providers and preconditions:

- `ForwardObject`
- `RecordVoiceMessage`
- `RevealCommunicationOptions`

Capabilities must name:

- provider entity
- subject object
- containing surface
- preconditions
- expected effects
- confidence
- risk class

### Transition interpretation

The perception model should explicitly compare the current frame against the
prior one:

- what appeared
- what disappeared
- what persisted
- what became occluded
- what moved
- what changed relations
- whether the observation was degraded

## Temporal contract

Not currently observed does not mean gone.

Perception should preserve object permanence through a typed track:

```python
ObjectTrack(
    current_id,
    previous_id,
    identity_confidence,
    status="visible" | "occluded" | "stale" | "gone",
)
```

This is essential for GUI tasks where menus appear, headers are occluded, and
conversation content persists across state changes.

## Sensor staging

Use a staged pipeline rather than one giant prompt.

### Stage A: low-level proposals

Inputs:

- screenshot
- AX tree
- OCR
- prior frame

Outputs:

- candidate regions
- candidate controls
- candidate text objects
- candidate image/icon objects

### Stage B: semantic reconstruction

Group proposals into semantic objects and surfaces.

### Stage C: relation inference

Infer ownership and anchoring relations.

### Stage D: capability inference

Infer typed capabilities from the reconstructed scene.

### Stage E: temporal reconciliation

Compare with the previous world state and update tracks.

### Stage F: goal-conditioned relevance

Rank the objects, relations, and uncertainties that matter for the current
goal, without distorting the objective scene model.

## Confidence contract

Do not compress all uncertainty into one score.

Track confidence independently for:

- existence
- identity
- semantic type
- region membership
- relation
- actionability
- capability
- temporal persistence

This prevents a control-control mixup like:

```text
high object confidence
→ mistaken call capability
```

## Validation

Deterministic validation should run before and after the learned model:

### Before the model

- associate overlapping AX, OCR, and screenshot proposals
- attach geometry and hierarchy to candidate tokens

### After the model

- verify that provider entities exist
- verify that claimed relations are geometrically plausible
- verify that actionability matches the current surface
- reject invalid references rather than hallucinating world state

## Evaluation order

Build the eval stack in this order:

1. Static scene understanding
2. Object and surface identification
3. Relation inference
4. Capability precision
5. Temporal persistence and occlusion handling
6. Goal-conditioned relevance ranking
7. End-to-end control loop regression

The benchmark must measure structure, not only task success.

Important metrics:

- object detection recall
- semantic-type accuracy
- relation accuracy
- capability precision
- object identity persistence
- transition classification accuracy
- goal-relevance ranking
- calibration error
- unsafe false-positive rate

## Implementation order

Recommended priority:

1. Define the typed perception contract.
2. Record perception traces with all raw sensors.
3. Build atomic perception evals.
4. Add staged reconstruction.
5. Add temporal reconciliation.
6. Add confidence calibration.
7. Use traces to tune routing, prompt shape, and model choice.

## Boundary

The perception stack should answer:

- what entities and surfaces exist?
- how are they related?
- what persisted or changed?
- what capabilities do they provide?
- which claims are uncertain?
- what additional observation would resolve the uncertainty?

It should not answer:

- what should the agent do next?

That remains the controller’s job.
