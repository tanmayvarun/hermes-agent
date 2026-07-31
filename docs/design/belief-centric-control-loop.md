# BELIEF-CENTRIC CONTROL LOOP
## Model-Based Runtime Design Specification

**Status:** Architectural design specification

**Runtime invariant**  
Maintain the best current belief about the world; choose actions that advance the goal or reduce decision-critical uncertainty; revise beliefs from consequences.

## Purpose

This document defines the control contract for migrating the agent from action-centric retry logic to model-based, belief-state control. It is intended to guide implementation, review, testing, and staged replacement of the current procedural controller.

## 1. Architectural shift

The current controller is transition-aware and materially better than a naive retry loop. However, its centre of gravity remains action-centric: it observes a state, ranks actions, executes one, records whether it worked, and then boosts, suppresses, retries, or backtracks.

| Action-centric runtime | Belief-centric runtime |
| --- | --- |
| Learns which actions succeeded or failed in a state. | Maintains hypotheses about the world and treats actions as experiments that test or change those hypotheses. |

The required inversion is:

`State -> Action -> Outcome -> Suppress/Boost`

becomes

`Beliefs -> Uncertainty -> Hypotheses -> Experiment -> Observation -> Belief update`

Failure is not a special control branch. It is evidence. A failed actuator call, an unchanged world, an empty perception frame, and a contradicted world model are different events and must update different beliefs.

## 2. Runtime invariants

- Executor success is evidence that an action was attempted, not proof that the intended world transition occurred.
- No visible transition is not automatically evidence of no effect; observation may be incomplete, stale, occluded, or unavailable.
- Absence of evidence is not evidence of absence.
- World signatures may be used for caching and retrieval, but they do not define the latent state of the world.
- Legacy suppression, retry counters, and action-family statistics may influence priors, but must not directly determine the next action.
- Every selected action must declare what belief it is intended to change or test and what outcomes are expected.
- The same visible frame may produce different actions when latent beliefs or prior evidence differ.
- When uncertainty is below a commitment threshold and one safe action dominates alternatives, the runtime must act rather than observe indefinitely.

## 3. First-class runtime objects

Belief, uncertainty, hypothesis, experiment, and expectation are distinct concepts and must be represented by distinct data types. Conflating them will recreate the current architecture under new names.

### 3.1 Belief

An evidence-backed proposition about the world.

Minimum fields: proposition; value; confidence; status; supporting evidence; contradicting evidence; source reliability; updated_at; valid_until; provenance.

### 3.2 Uncertainty

A decision-relevant question whose unresolved state blocks progress, safety, or confident interpretation.

Minimum fields: question; importance; blocking goal predicates; candidate values; current entropy or confidence gap; staleness.

### 3.3 Hypothesis

A candidate explanation for an uncertainty.

Minimum fields: explanation; confidence; supporting evidence; contradicting evidence; causal assumptions; predicted observations; discriminating experiments.

### 3.4 Experiment

An available action chosen to advance the goal, reduce uncertainty, or both.

Minimum fields: capability; target; kind; beliefs tested; beliefs changed; expected goal progress; expected information gain; risk; cost; reversibility; preconditions.

### 3.5 Expectation

A prediction about what should and should not be observed after an experiment.

Minimum fields: predicted world changes; predicted non-changes; expected affordances; timing; contradiction conditions; sensor requirements; side effects.

### 3.6 Goal condition

A desired belief state, not merely a task kind string.

Minimum fields: proposition; desired value; required confidence; evidence requirements; terminal or intermediate status.

```python
@dataclass
class Belief:
    proposition: str
    value: Any
    confidence: float
    status: BeliefStatus
    supporting_evidence: list[EvidenceRef]
    contradicting_evidence: list[EvidenceRef]
    updated_at: float
    valid_until: float | None

@dataclass
class Uncertainty:
    question: str
    importance: float
    blocking_goals: list[str]
    candidate_values: list[Any]

@dataclass
class Hypothesis:
    explanation: str
    confidence: float
    supports: list[EvidenceRef]
    contradicts: list[EvidenceRef]
    predictions: list[Prediction]

@dataclass
class Experiment:
    capability: str
    target: str | None
    kind: ExperimentKind
    tests: list[str]
    expected_goal_progress: float
    expected_information_gain: float
    risk: float
    cost: float
    reversible: bool

@dataclass
class Expectation:
    predicted_observations: list[Prediction]
    predicted_non_observations: list[Prediction]
    contradiction_conditions: list[Predicate]
    timeout_ms: int
    required_sensors: list[str]
```

## 4. Belief status and temporal semantics

The world model must preserve object permanence and distinguish observation failure from world change. A proposition that is not currently visible must not be deleted by default.

| Status | Meaning |
| --- | --- |
| CONFIRMED | Strong recent evidence supports the proposition. |
| PROVISIONAL | Plausible but not yet adequately confirmed. |
| STALE | Previously supported, but evidence is older than the validity horizon. |
| OCCLUDED | Not currently observable, but no evidence indicates that it ceased to exist. |
| CONTRADICTED | Current evidence conflicts with the proposition. |
| UNKNOWN | Insufficient evidence to assign a meaningful value. |

Required semantic distinction:

- not observed now  !=  ceased to exist
- empty perception  !=  no world change
- executor returned ok  !=  goal-relevant transition succeeded

## 5. Evidence and belief update contract

All belief mutation must pass through an explicit update mechanism. Beliefs must not be changed ad hoc inside controller branches.

- Record the prior value and confidence.
- Identify every supporting and contradicting evidence item used.
- Weight evidence by source reliability, freshness, independence, and relevance.
- Produce a posterior value, confidence, and status.
- Record why the update occurred and which expectation was confirmed or violated.
- Retain provenance so the decision can be explained and replayed.
- Allow later evidence to reverse an update without losing history.

```python
BeliefUpdate(
    proposition="source_object_selected",
    prior=0.63,
    posterior=0.21,
    evidence=[
        Evidence(source="pyobjc_ax", observation="AXSelected absent", reliability=0.85),
        Evidence(source="vision", observation="no selection marker", reliability=0.70),
    ],
    cause="expected selection markers absent after settled perception",
)
```

The first implementation may use calibrated heuristics rather than exact Bayesian inference, but the interface must preserve Bayesian semantics: prior, evidence likelihood or reliability, posterior, and provenance.

## 6. Model-based control cycle

ingest evidence -> update beliefs -> evaluate goal predicates -> identify decision-critical uncertainties -> generate or retrieve competing hypotheses -> generate candidate experiments -> attach expectations to each experiment -> score experiments -> execute one experiment -> observe consequences -> compare observation with expectations -> update beliefs and hypothesis confidence -> repeat

### 6.1 Active uncertainty selection

The runtime should focus on uncertainties that materially block the next safe or useful step. It should not attempt to resolve every unknown in the world model.

- How strongly does this uncertainty block a goal predicate?
- Could acting without resolving it cause irreversible harm?
- Would resolving it change the preferred action?
- Is the belief stale, contradicted, or supported only by one weak source?

### 6.2 Hypothesis generation

Hypotheses may come from deterministic rules, retrieved prior experience, domain adapters, or an LLM. The source must be recorded. An LLM-generated hypothesis is a proposal, not evidence.

```python
generate(
    goal,
    belief_state,
    active_uncertainty,
    recent_transition,
    available_capabilities,
) -> list[Hypothesis]
```

### 6.3 Experiment generation

Experiments are classified as observational, interventional, or mixed.

- Observational: Acquire information without intending to alter the task state: inspect, search, query, reobserve.
- Interventional: Primarily alter the world: send, submit, delete, move, forward.
- Mixed: Both change state and reveal information: open, scroll, select, expand.

## 7. Experiment scoring and information gain

The runtime must not choose an experiment merely because it has failed fewer times. It should compare expected goal value, uncertainty reduction, cost, risk, latency, and reversibility.

`Expected utility = expected goal progress + value of information - risk - cost - delay - irreversible downside`

Operationally, information gain means: how much would the possible outcomes of this experiment change the ranking of currently plausible hypotheses or the preferred next action?

### 7.1 Discrimination requirement

Every information-seeking experiment should specify expected outcomes under each material hypothesis. An experiment is informative when competing hypotheses predict materially different results.

```text
H1: source object not selected          0.55
H2: forward actuator failed             0.30
H3: perception is stale                 0.15

Experiment A: click Forward again
- weakly discriminates H1 and H2

Experiment B: inspect selection state using independent AX and vision sources
- strongly discriminates H1, H2, and H3
```

### 7.2 Commitment rule

To prevent observation thrashing, the runtime must commit when uncertainty is below a configured threshold, expected information gain is low, and one safe experiment has clearly higher expected utility than alternatives.

## 8. Expectations and transition evaluation

An action is not complete until its expectations have been compared with evidence. Expectations must cover more than a single visual predicate.

- Expected world changes and expected non-changes.
- Expected new or removed affordances.
- Expected timing and settlement window.
- Contradiction conditions.
- Required sensors and acceptable source degradation.
- Possible side effects and irreversible consequences.

```python
Expectation(
    experiment="forward_message",
    within_ms=1500,
    expected_belief_changes=["destination_picker_visible -> true"],
    expected_affordances=["select_forward_target"],
    contradiction_conditions=["current_chat_closed", "selection_marker_disappears"],
    required_sensors=["pyobjc_ax or vision"],
)
```

### 8.1 Outcome taxonomy

| Outcome | Interpretation |
| --- | --- |
| EXPECTED_CONFIRMED | Observed evidence matches the predicted transition. |
| EXPECTED_PARTIAL | Some expected changes occurred; state remains unresolved. |
| WORLD_NO_CHANGE | Reliable observation indicates the relevant world state did not change. |
| ACTUATION_FAILURE | The action was not successfully executed or reached the intended target. |
| PERCEPTION_FAILURE | The runtime cannot reliably determine whether the world changed. |
| PRIOR_BELIEF_WRONG | Evidence contradicts a pre-action assumption. |
| UNEXPECTED_CHANGE | The world changed in an unpredicted way. |
| GOAL_SATISFIED | Evidence meets the goal-condition confidence threshold. |

## 9. Belief graph semantics

The term belief graph refers to a typed graph, not a dictionary of scalar confidence values.

- Node types: entities, propositions, uncertainties, hypotheses, goals, experiments, expectations, observations.
- Edge types: supports, contradicts, depends_on, predicts, tests, changes, enables, blocks, satisfies, refers_to.

```text
Hypothesis: source not selected -> predicts -> Observation: no selected marker
Experiment: inspect source row -> tests -> Hypothesis: source not selected
Belief: destination picker absent -> blocks -> Goal condition: destination chosen
```

## 10. Role of action experience

Action history remains useful, but only as supporting evidence or a prior for experiment scoring.

- A repeated actuator failure may lower actuator-reliability belief.
- A previously successful capability may receive a modest prior boost.
- A state-action pair may be cached for efficiency.
- Historical outcomes may help retrieve reusable hypotheses or experiments.

Action experience must not directly suppress an action solely because a counter crossed an arbitrary threshold. Any suppression must be justified by a belief such as low actuator reliability, high risk, known irreversibility, or low expected information value.

## 11. Integration with existing components

- Fusion and perception: Produce evidence and source-reliability metadata. They do not directly decide whether an action succeeded.
- World model: Owns temporally persistent beliefs, entities, relations, statuses, and provenance.
- Decision engine: Selects active uncertainty, hypotheses, and experiments. It must not operate primarily on retry counters.
- Transition evaluator: Compares expectations with observations and emits evidence-level outcome classification.
- Experience memory: Supplies priors, retrieved hypotheses, and historical evidence. It is not the top-level policy.
- Task procedures: Provide goal decomposition, domain constraints, and candidate capabilities without becoming rigid scripts.
- LLM: Interprets goals, generates hypotheses, proposes experiments, and explains contradictions. It is a consultant within the runtime, not the runtime itself.

## 12. Migration strategy

The change should be introduced in parallel rather than by inserting a belief graph into the existing procedural controller. Otherwise the system will contain two competing brains and legacy branches will continue to dominate.

### Phase 0 — Instrument in shadow mode

Construct beliefs, uncertainties, hypotheses, experiments, and expectations alongside the current controller. Log the belief planner recommendation without allowing it to act.

### Phase 1 — Belief-based diagnosis

Use the new transition model to classify world no-change, actuation failure, perception failure, wrong prior belief, unexpected change, and unresolved state. Keep legacy action selection.

### Phase 2 — Narrow control takeover

Allow the belief planner to select experiments for one bounded workflow, such as WhatsApp forwarding. Compare legacy and belief policies in shadow and live evaluation.

### Phase 3 — Remove recovery authority

Legacy suppression and branch logic may supply priors but may not directly choose the next action.

### Phase 4 — Delete duplicated branches

After behavioural parity and regression coverage, remove procedural recovery paths that duplicate belief-based control.

### Phase 5 — Generalise across tasks

Move task-specific beliefs and experiments into domain adapters while preserving the same runtime control contract.

## 13. Acceptance tests

### 13.1 Same visible frame, different latent beliefs

Setup: Provide identical frames. In case A, source selection was previously confirmed. In case B, source selection is uncertain.

Expected behaviour: Case A selects the forward experiment. Case B selects a verification experiment. The difference must be explainable from belief state, not counters.

### 13.2 Empty perception after successful click

Setup: The executor reports success, then the fused perception frame is empty while a prior AX world remains usable.

Expected behaviour: Do not classify the action as NO_EFFECT. Mark the transition as unobservable or perception failure, retain prior beliefs with increased staleness, and select a sensor-recovery experiment.

### 13.3 Competing failure hypotheses

Setup: Maintain plausible hypotheses for actuator failure and source-selection failure.

Expected behaviour: Choose an experiment whose outcomes discriminate between the hypotheses rather than repeating the same action.

### 13.4 Failure as evidence

Setup: An expected observation is contradicted after settled, reliable perception.

Expected behaviour: Update belief confidence, hypothesis ranking, and the next selected experiment. Merely incrementing an action-failure counter is insufficient.

### 13.5 No arbitrary threshold dependence

Setup: Run the same belief state with different legacy failure counts.

Expected behaviour: The selected experiment remains the same unless counts are converted into explicit evidence that changes a relevant belief.

### 13.6 Observation-thrashing guard

Setup: Repeated observations provide diminishing information and one reversible action clearly dominates.

Expected behaviour: The controller commits to the action once the commitment rule is satisfied.

### 13.7 Goal as desired belief

Setup: The UI appears to show completion, but evidence confidence remains below the goal threshold.

Expected behaviour: The runtime continues verification rather than declaring success solely from executor output or task phase.

### 13.8 Transfer across domains

Setup: Create equivalent uncertainty patterns in WhatsApp and a browser workflow.

Expected behaviour: The same hypothesis/experiment machinery is used, with only domain-specific beliefs and capabilities supplied by adapters.

## 14. Non-goals and safeguards

This design does not require exact probabilistic inference in the first implementation.

This design does not remove deterministic safety rules, permission checks, or irreversible-action confirmation.

This design does not require the LLM to control every cycle. Deterministic updates should be preferred when evidence semantics are known.

This design does not eliminate procedures; procedures become sources of goal predicates, constraints, and candidate experiments rather than fixed execution scripts.

This design does not treat every action as safe experimentation. Interventional actions remain subject to risk and reversibility constraints.

## 15. Implementation completion criteria

- The controller can explain the active uncertainty, competing hypotheses, chosen experiment, and expected outcomes before acting.
- The runtime can distinguish action execution, world transition, and perception reliability.
- Belief updates are provenance-preserving and replayable.
- Goals are represented as desired predicates with evidence thresholds.
- Actions are selected from expected utility and information value rather than direct suppression thresholds.
- Object permanence survives temporary sensor loss or empty fusion.
- Legacy action memory is advisory only.
- The acceptance tests pass in deterministic fixtures and end-to-end task runs.
- The forward-message path succeeds because the belief state and experiment selection are correct, not because a growing set of workflow-specific recovery branches handles every failure.

## 16. Relationship to existing design documents

- `procedure-execution-substrate.md`: Defines ordered procedure stages and convergent execution constraints.
- `content-object-discovery.md`: Defines how relevant objects are resolved from visible and latent content.
- `whatsapp-evaluation-ladder.md`: Defines staged WhatsApp training and regression evaluation.
- `task-model-routing.md`: Defines how model families are selected for a task.

This specification: Defines the connective runtime contract: how evidence becomes beliefs, how uncertainty produces experiments, and how consequences revise the world model.
