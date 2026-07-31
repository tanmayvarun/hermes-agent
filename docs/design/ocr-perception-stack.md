# OCR in the perception stack

## Goal

When accessibility trees and semantic text reconstruction are not enough, the
perception stack should be able to recover a stronger view of the screen from
OCR without hardcoding app-specific logic.

## Design

- OCR is a generic perception capability.
- App-specific overlays may consume OCR-derived entities, but they must not own
  OCR policy or engine selection.
- The perception stack can switch engines based on the current use case and the
  observed success rate of each engine.
- OCR should be treated as an additional visibility dimension, especially on
  retries when the agent already knows the primary accessibility path was
  incomplete.
- OCR output should feed the generic world model and confidence system, not
  a per-app actuator policy.
- For hard app flows, OCR is most useful after the agent has already seen a
  plausible surface and needs one more visibility channel to confirm or
  reject the current hypothesis.

## Learning contract

The OCR layer can learn from history in a generic way:

- which engine works better for a use case
- which screenshot shapes produce reliable text recovery
- how often OCR improves downstream perception on retries

When OCR helps the agent avoid a wrong next step, that improvement should be
learned as a reusable perception result, not as an app-specific rule.

That learning remains generic. A WhatsApp overlay may benefit from OCR on a
chat list or message thread, but the overlay itself should only consume the
resulting semantic entities and confidence values.

## Engine policy

The repo integrates two local OCR engines:

- `PaddleOCR` for denser, document-like or structured layouts.
- `EasyOCR` for lighter-weight UI screenshots and quick recovery.

Selection should follow this order:

1. Prefer the engine that has the better observed success rate for the current
   use case when enough history exists.
2. Otherwise use the task shape:
   - document-like tasks prefer `PaddleOCR`
   - UI/chat-like tasks prefer `EasyOCR`
3. Retry paths may force OCR when a screenshot is available, so the agent can
   use the extra signal before giving up or trying a wrong actuator.

## Related model families

OCR is only one member of the broader screen-understanding stack.

- `OmniParser`-style screen parsers should emit structured elements and
  coordinates as another perception channel.
- `UI-TARS` / `ShowUI` / `OS-Atlas`-style models belong in the action-prior
  layer, where they suggest plausible next UI actions but do not bypass the
  world model.
- Hosted computer-use APIs are another action-prior source, not a new app
  overlay policy.

All of those families should be wired through generic registries and adapted
into the world model / confidence system, not hardcoded into WhatsApp or any
other leaf overlay.

## Boundary

OCR may help recover:

- conversation headers
- message text
- visible links and captions
- control labels when AX is incomplete

OCR must not:

- pick the final actuator by label alone
- bypass confidence gating for irreversible actions
- encode app-specific step sequences in the OCR layer

## Non-goals

- No per-app OCR heuristics in app overlays.
- No hardcoded actuator choice based on OCR labels alone.
- No replacement of accessibility as the primary signal when AX is already
  sufficient.
