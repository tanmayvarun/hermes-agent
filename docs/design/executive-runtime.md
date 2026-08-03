# Executive runtime

The control loop used to be a fixed pipeline: perceive → decide → act, every
turn, with task state scattered across a forward-specific phase machine, the
world document, the interaction context and a handful of `ExecutionState`
flags. Perception was unconditional, exploration was keyed by the action rather
than the question it tested, and one domain's knowledge (WhatsApp's forward
phases) lived inside the shared controller.

The executive runtime reframes the loop as an agent that owns the *task*, not
the app: an authoritative workspace, an explicit judgement of whether it can
act, questions it is trying to answer, a value-based choice of what kind of step
to take, and a capability registry it retrieves from. The migration is a
phased, behavior-preserving refactor guarded by characterization tests
(`tests/plugin/test_control_loop_characterization.py`) and the perception eval
report (`docs/design/perception-evals.md`); every slice is diffed against a
frozen baseline so an unintended behavior change shows up immediately.

## Components (`plugin/agent/executive/`)

- **`ExecutiveWorkspace`** (`workspace.py`) — the single authoritative record of
  the task. Read freely; the only mutation path is `commit(WorkspaceProposal)`,
  which applies critic rules (never wipe `open_conversation` from inside a
  conversation, reject unjustified phase regressions, dedupe attempts) and
  returns a `CommitVerdict` explaining what it accepted and why. `open_conversation`,
  task phase and attempt history now live here instead of in duplicate stores;
  `ExecutionState.search_attempt_log` is a read-through view of it.

- **`DecisionSufficiency`** (`sufficiency.py`) — turns "should I observe again?"
  into an explicit judgement. From blocking uncertainties, declared evidence
  gaps, coverage and whether observation is still yielding anything, it decides
  `sufficient_to_act`, `observe_has_value`, which action families the evidence
  is enough for (`sufficient_for_which_actions`) and how strongly it holds the
  verdict (`confidence`). This replaces the `suppress_observe` /
  `identical_observe_streak` heuristic: the streak is now just a fact fed into
  the judgement.

- **Always-on judgement** — every iteration and for *every* goal, the loop
  computes one sufficiency verdict and one meta-action
  (`sync.assess_executive_judgement`), records them on the execution state
  (`last_sufficiency` / `last_meta_action`) and logs an `executive_judgement`
  event. The WhatsApp forward path shares this exact computation for its
  observe-suppression decision rather than owning a parallel copy.

- **Meta-driven perception** — under `HERMES_META_PERCEPTION` the meta-action
  gates the top-of-loop re-perceive: when the executive is `sufficient_to_act`
  and the previous look only re-described a world it had already seen, the loop
  reuses the prior snapshot (`perception_skipped`) instead of perceiving
  unconditionally. It is off by default because making perception conditional
  changes the characterization goldens and must be adopted deliberately; the
  judgement itself is recorded regardless.

- **Belief state** (`workspace.py`) — arbitrary situation facts live in the
  workspace as `Claim`s (value + source + confidence + evidence), proposed via
  `commit_beliefs` and arbitrated by `commit`: a matching value reinforces, an
  empty reading never erases a known fact, and a genuine conflict records a
  first-class `Contradiction` (prior/proposed, both sources, and the resolution)
  before the more confident reading wins. This is the design's core invariant —
  submodules propose, the workspace reconciles — generalised from the
  conversation/phase claims to any fact. Perception seeds `active_app`,
  `surface`, `call_state` and `search_query`; the facts and recent
  contradictions are logged each iteration in the `executive_judgement` event.

- **Questions** (`questions.py`) — `OpenQuestion`, `Hypothesis`, `InformationGap`
  as first-class workspace state. Exploration is keyed by the *question* an
  action tests, not the action, so re-issuing an action that only re-asks a
  settled question is visibly redundant — the root fix for the
  re-search-the-same-thing failure class.

- **Meta-actions** (`meta_action.py`) — `THINK / PERCEIVE / PROBE / ACT / VERIFY
  / BACKTRACK / ASK_USER`, selected by value from the sufficiency verdict and
  budget. Perception stops being unconditional: PERCEIVE is a chosen phase, and
  a stale look yields to BACKTRACK or ACT.

- **Capability registry** (`capabilities.py`) — `CapabilityDescriptor` enriches
  each catalog verb with cost, latency, reliability, preconditions and side
  effects; `CapabilityRegistry` does hierarchical retrieval (filter by
  precondition fit, then rank by value) so consultations get a short relevant
  shortlist instead of the full catalog. Reliability updates from observed
  outcomes.

## Domain generality

The loop is no longer WhatsApp-shaped:

- The overlay registry (`plugin/agent/apps/registry.py`) now falls back to a
  neutral `GenericOverlay` for unknown apps instead of imposing WhatsApp's
  surfaces and forward-picker priors on everything. This was a real bug.
- A second domain, `FilesystemOverlay` (Finder), consumes the same executive
  machinery — workspace, sufficiency, meta-actions, questions, registry —
  without sharing any WhatsApp vocabulary (`tests/plugin/test_filesystem_domain.py`).
- WhatsApp's forward phase machine is demoted to an overlay *hint*:
  `WhatsAppOverlay.observe_blocking_uncertainties` returns a domain-general
  blocking uncertainty the controller feeds into sufficiency, so the shared
  loop no longer reads WhatsApp phase names or binding shapes.

## Temporal-consistency evals

`plugin/evals/temporal.py` adds a layer over run logs measuring the properties
the workspace exists to protect: belief-flip rate, object-identity continuity,
surface stability and unjustified phase-regression rate. Run with
`python -m plugin.evals.run --temporal`.

## Executive-calibration evals

`plugin/evals/executive.py` scores the *judgement* rather than perception, by
correlating each recorded `executive_judgement` with what the loop then did:
`sufficiency_precision` (did "I can act" lead to an action that landed?),
`act_success_rate`, `meta_action_appropriateness` (did the chosen meta-action
match a simple oracle?), and `skip_safety` (were skipped re-perceives followed
by clean transitions?). Run with `python -m plugin.evals.run --executive`.

## Deliberately deferred

- The remaining WhatsApp forward controller branches (`_note_forward_observe`,
  `_bind_forward_after_execution`, `_forward_predicate_gate_after_transition`
  and the `goal.kind == "whatsapp_forward_message"` blocks) are still present.
  Deleting them changes the golden traces by design and should be a focused,
  separately-reviewed change that re-blesses the characterization baseline,
  rather than being bundled into a behavior-preserving slice.
- The filesystem domain is proven at the executive-loop level; wiring it through
  the full macOS Finder perception/execution stack is future work.
- Meta-driven perception ships behind `HERMES_META_PERCEPTION` (off). Making it
  the default is a deliberate follow-up: it changes the golden traces and wants a
  live validation run of the `--executive` calibration metrics before the flag
  is flipped and the baseline re-blessed.
