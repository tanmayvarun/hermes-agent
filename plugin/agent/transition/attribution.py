"""Causal failure attribution across independent hypothesis layers.

Invariant
---------
A downstream action failure must not invalidate an upstream belief unless the
resulting observation provides evidence against that belief.

Two kinds of uncertainty (must not be collapsed):

* Intent uncertainty — did the user mean this reference?
* World uncertainty — given the correct target, how do we act on this screen?

``start_call`` / ``center=None`` / NO_EFFECT is world/actuation uncertainty.
It must trigger re-observe + fresh affordance search in the current world —
never ``advance search hypothesis``.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from plugin.agent.action import Action
from plugin.agent.goal import Goal
from plugin.agent.transition.belief_state import BeliefStatus, BeliefUpdate
from plugin.agent.transition.types import TransitionOutcome, TransitionResult
from plugin.perception.evidence import EvidenceRef


class FailureDomain(str, Enum):
    NONE = "none"
    REFERENCE = "reference"
    ENTITY = "entity"
    ACTUATION = "actuation"
    PERCEPTION = "perception"
    UNKNOWN = "unknown"


class EffectKind(str, Enum):
    """Finer grain than a single NO_EFFECT bucket."""

    GOAL_SATISFIED = "goal_satisfied"
    PROGRESS = "progress"
    PROMISING_UNRESOLVED = "promising_unresolved"
    REGRESSION = "regression"
    UNCERTAIN = "uncertain"
    # Splits of former NO_EFFECT:
    NOT_ATTEMPTED = "not_attempted"
    MISSING_GEOMETRY = "missing_geometry"
    ACTUATOR_FAILED = "actuator_failed"
    NO_TRANSITION = "no_transition"
    TRANSITION_NOT_PERCEIVED = "transition_not_perceived"
    REDUNDANT_ALREADY_SATISFIED = "redundant_already_satisfied"


@dataclass
class LayerBeliefDeltas:
    reference_resolution: float = 0.0
    entity_resolution: float = 0.0
    target_actionability: float = 0.0
    actuator_reliability: float = 0.0
    perception_reliability: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class TransitionAssessment:
    action_family: str = ""
    outcome: str = TransitionOutcome.UNCERTAIN.value
    effect_kind: str = EffectKind.UNCERTAIN.value
    likely_failure_domain: str = FailureDomain.NONE.value
    affected_beliefs: LayerBeliefDeltas = field(default_factory=LayerBeliefDeltas)
    belief_updates: list = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    notes: list = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_family": self.action_family,
            "outcome": self.outcome,
            "effect_kind": self.effect_kind,
            "likely_failure_domain": self.likely_failure_domain,
            "affected_beliefs": self.affected_beliefs.to_dict(),
            "belief_updates": [u.to_dict() for u in self.belief_updates],
            "evidence": self.evidence,
            "notes": list(self.notes),
        }

    @property
    def implicates_reference(self) -> bool:
        return (
            self.likely_failure_domain == FailureDomain.REFERENCE.value
            or self.affected_beliefs.reference_resolution < -0.15
        )


@dataclass
class HypothesisLayers:
    """Run-local independent confidence for the three hypothesis layers."""

    reference_confidence: float = 0.88
    entity_confidence: float = 0.0
    actuation_confidence: float = 0.7
    last_effect_kind: str = ""
    last_failure_domain: str = FailureDomain.NONE.value
    ineffective_actuators: Dict[str, int] = field(default_factory=dict)

    def apply(self, assessment: TransitionAssessment) -> None:
        b = assessment.affected_beliefs
        self.reference_confidence = _clamp(self.reference_confidence + b.reference_resolution)
        self.entity_confidence = _clamp(self.entity_confidence + b.entity_resolution)
        self.actuation_confidence = _clamp(self.actuation_confidence + b.actuator_reliability)
        self.last_effect_kind = assessment.effect_kind
        self.last_failure_domain = assessment.likely_failure_domain
        if assessment.effect_kind in {
            EffectKind.MISSING_GEOMETRY.value,
            EffectKind.ACTUATOR_FAILED.value,
            EffectKind.NO_TRANSITION.value,
        }:
            key = str(assessment.evidence.get("actuator") or assessment.action_family or "unknown")
            self.ineffective_actuators[key] = self.ineffective_actuators.get(key, 0) + 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reference_confidence": self.reference_confidence,
            "entity_confidence": self.entity_confidence,
            "actuation_confidence": self.actuation_confidence,
            "last_effect_kind": self.last_effect_kind,
            "last_failure_domain": self.last_failure_domain,
            "ineffective_actuators": dict(self.ineffective_actuators),
        }


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def parse_motor_landed_point(message: Any) -> Optional[List[float]]:
    """Extract ``center=(x, y)`` from an executor message, if present.

    This is measured motor geometry — where the hands landed — distinct from
    the brain's intended ``target_point``. REFLECT needs both to discover
    wrong-region clicks without task-specific hardcoding.
    """
    msg = str(message or "")
    m = re.search(
        r"center\s*=\s*\(\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*\)",
        msg,
        re.I,
    )
    if not m:
        return None
    try:
        return [float(m.group(1)), float(m.group(2))]
    except (TypeError, ValueError):
        return None


def parse_execution_detail(execution: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize executor payload into grounding/attempt signals."""
    execution = execution or {}
    msg = str(execution.get("message") or "")
    ok = bool(execution.get("ok"))
    backend = str(execution.get("backend") or "")
    center_none = bool(re.search(r"center\s*=\s*None", msg, re.I))
    missing_bounds = "no bounds" in msg.lower() or "missing" in msg.lower() and "bound" in msg.lower()
    pressed = "axpress" in msg.lower() or "press" in msg.lower()
    landed = parse_motor_landed_point(msg)
    return {
        "attempted": ok or bool(msg),
        "executor_ok": ok,
        "actuator": backend or ("ax" if pressed else "unknown"),
        "missing_geometry": center_none or missing_bounds,
        "message": msg[:240],
        "motor_landed_point": landed,
    }


def classify_effect_kind(
    *,
    outcome: str,
    transition: Optional[TransitionResult],
    execution: Optional[Dict[str, Any]],
    before_features: Optional[Dict[str, Any]] = None,
    after_features: Optional[Dict[str, Any]] = None,
) -> EffectKind:
    if outcome == TransitionOutcome.GOAL_SATISFIED.value:
        return EffectKind.GOAL_SATISFIED
    if outcome == TransitionOutcome.PROGRESS.value:
        return EffectKind.PROGRESS
    if outcome == TransitionOutcome.PROMISING_UNRESOLVED.value:
        return EffectKind.PROMISING_UNRESOLVED
    if outcome == TransitionOutcome.REGRESSION.value:
        return EffectKind.REGRESSION

    detail = parse_execution_detail(execution)
    if not detail["attempted"] and not detail["executor_ok"]:
        return EffectKind.NOT_ATTEMPTED
    if detail["missing_geometry"]:
        return EffectKind.MISSING_GEOMETRY
    if detail["attempted"] and not detail["executor_ok"]:
        return EffectKind.ACTUATOR_FAILED

    tr = transition
    changed = bool(tr.changed) if tr else False
    if detail["executor_ok"] and not changed:
        # Already-desired state? e.g. call already ringing bits
        af = after_features or {}
        bf = before_features or {}
        if af.get("call_ringing") and bf.get("call_ringing"):
            return EffectKind.REDUNDANT_ALREADY_SATISFIED
        return EffectKind.NO_TRANSITION
    if detail["executor_ok"] and changed and outcome == TransitionOutcome.UNCERTAIN.value:
        return EffectKind.TRANSITION_NOT_PERCEIVED
    if outcome == TransitionOutcome.NO_EFFECT.value:
        return EffectKind.NO_TRANSITION
    return EffectKind.UNCERTAIN


def attribute_transition(
    *,
    action: Action,
    outcome: str,
    transition: Optional[TransitionResult] = None,
    execution: Optional[Dict[str, Any]] = None,
    before_view: Optional[Dict[str, Any]] = None,
    after_view: Optional[Dict[str, Any]] = None,
    before_features: Optional[Dict[str, Any]] = None,
    after_features: Optional[Dict[str, Any]] = None,
    goal: Optional[Goal] = None,
) -> TransitionAssessment:
    """Map observed transition + execution detail → which hypothesis layer to revise."""
    before_view = before_view or {}
    after_view = after_view or {}
    before_features = before_features or {}
    after_features = after_features or {}
    detail = parse_execution_detail(execution)
    effect = classify_effect_kind(
        outcome=outcome,
        transition=transition,
        execution=execution,
        before_features=before_features,
        after_features=after_features,
    )
    beliefs = LayerBeliefDeltas()
    domain = FailureDomain.NONE
    notes: list = []

    conf = float(after_features.get("resolution_confidence") or before_features.get("resolution_confidence") or 0)
    open_before = str(before_view.get("open_conversation") or "")
    open_after = str(after_view.get("open_conversation") or "")
    query_after = str(after_view.get("search_query") or "")
    query_matched = bool(after_features.get("query_matches_goal"))

    if effect == EffectKind.GOAL_SATISFIED:
        beliefs.reference_resolution = 0.05
        beliefs.entity_resolution = 0.1
        beliefs.actuator_reliability = 0.05
    elif effect == EffectKind.PROGRESS:
        beliefs.entity_resolution = 0.08
        beliefs.target_actionability = 0.05
        # Progress never revises intent — even if resolution conf briefly reads 0
        domain = FailureDomain.NONE
    elif effect == EffectKind.PROMISING_UNRESOLVED:
        # Novel branch: preserve entity/reference; boost actionability of new surface
        beliefs.entity_resolution = 0.05
        beliefs.target_actionability = 0.1
        beliefs.actuator_reliability = 0.05
        domain = FailureDomain.NONE
        notes.append("promising_branch_explore_locally")
    elif effect == EffectKind.REGRESSION:
        beliefs.entity_resolution = -0.15
        domain = FailureDomain.ENTITY
        notes.append("regression_implicates_entity_or_nav")
    elif effect == EffectKind.MISSING_GEOMETRY:
        beliefs.target_actionability = -0.35
        beliefs.actuator_reliability = -0.45
        domain = FailureDomain.ACTUATION
        notes.append("center_none_or_missing_bounds")
    elif effect == EffectKind.ACTUATOR_FAILED:
        beliefs.actuator_reliability = -0.55
        beliefs.target_actionability = -0.2
        domain = FailureDomain.ACTUATION
        notes.append("actuator_reported_failure")
    elif effect == EffectKind.NOT_ATTEMPTED:
        beliefs.actuator_reliability = -0.3
        domain = FailureDomain.ACTUATION
        notes.append("execution_not_attempted")
    elif effect == EffectKind.NO_TRANSITION:
        # Downstream stall: prefer actuation/perception, NOT reference,
        # unless search never landed and we have empty candidates.
        if action.action_family in {"start_call", "end_call", "dismiss", "open_contact"}:
            beliefs.target_actionability = -0.3
            beliefs.actuator_reliability = -0.4
            beliefs.perception_reliability = -0.1
            domain = FailureDomain.ACTUATION
            notes.append("no_transition_after_downstream_action")
            # Explicitly leave reference untouched
            beliefs.reference_resolution = 0.0
        elif action.action_family == "type_query":
            # Typing with no query change → actuation/perception of search field
            if not query_matched and not query_after:
                beliefs.actuator_reliability = -0.35
                domain = FailureDomain.ACTUATION
                notes.append("type_did_not_land_query")
            else:
                beliefs.perception_reliability = -0.2
                domain = FailureDomain.PERCEPTION
                notes.append("type_query_present_but_no_world_delta")
        else:
            domain = FailureDomain.UNKNOWN
            beliefs.perception_reliability = -0.15
    elif effect == EffectKind.TRANSITION_NOT_PERCEIVED:
        beliefs.perception_reliability = -0.4
        domain = FailureDomain.PERCEPTION
        notes.append("executor_ok_transition_uncertain")
    elif effect == EffectKind.REDUNDANT_ALREADY_SATISFIED:
        domain = FailureDomain.NONE
        notes.append("desired_state_already_present")

    # Reference layer only when evidence specifically implicates the query.
    # Never on PROGRESS / GOAL — those mean the world moved forward, not that intent is wrong.
    if effect not in {
        EffectKind.PROGRESS,
        EffectKind.PROMISING_UNRESOLVED,
        EffectKind.GOAL_SATISFIED,
        EffectKind.REDUNDANT_ALREADY_SATISFIED,
    }:
        if _reference_implicated(
            action=action,
            effect=effect,
            query_matched=query_matched,
            query_after=query_after,
            conf=conf,
            open_after=open_after,
            after_features=after_features,
            goal=goal,
        ):
            beliefs.reference_resolution = min(beliefs.reference_resolution, -0.25)
            domain = FailureDomain.REFERENCE
            notes.append("evidence_against_reference_hypothesis")

    belief_updates = _belief_updates_for_assessment(
        action=action,
        outcome=outcome,
        effect=effect,
        domain=domain,
        beliefs=beliefs,
        detail=detail,
        before_view=before_view,
        after_view=after_view,
        before_features=before_features,
        after_features=after_features,
        goal=goal,
        notes=notes,
    )

    return TransitionAssessment(
        action_family=action.action_family,
        outcome=outcome,
        effect_kind=effect.value,
        likely_failure_domain=domain.value,
        affected_beliefs=beliefs,
        belief_updates=belief_updates,
        evidence={
            **detail,
            "resolution_confidence": conf,
            "open_before": open_before[:80],
            "open_after": open_after[:80],
            "search_query": query_after[:80],
            "query_matches_goal": query_matched,
            "change_score": transition.change_score if transition else 0.0,
        },
        notes=notes,
    )


def _reference_implicated(
    *,
    action: Action,
    effect: EffectKind,
    query_matched: bool,
    query_after: str,
    conf: float,
    open_after: str,
    after_features: Dict[str, Any],
    goal: Optional[Goal],
) -> bool:
    """True only when observations attack the reference/query hypothesis."""
    # Downstream call/open stalls never implicate reference by themselves
    if action.action_family in {"start_call", "end_call", "dismiss", "observe"}:
        return False
    if effect in {
        EffectKind.MISSING_GEOMETRY,
        EffectKind.ACTUATOR_FAILED,
        EffectKind.NOT_ATTEMPTED,
        EffectKind.TRANSITION_NOT_PERCEIVED,
    }:
        return False

    policy = str(after_features.get("resolution_policy") or "")
    cands = after_features.get("contact_candidates") or []
    # Successfully entered query + stable empty/weak resolution → reference may be wrong
    if action.action_family == "type_query" and query_matched and query_after:
        if conf < 0.45 and policy in {"ask", "observe", ""}:
            return True
        if not cands and conf < 0.35:
            return True
    if action.action_family == "open_contact":
        # Open clicked but wrong entity in focus vs reference name
        if goal and goal.contact and open_after:
            ref = goal.ensure_reference()
            name = (ref.active_name or "").lower()
            if name and name not in open_after.lower() and conf < 0.5:
                return True
    return False


def _belief_status_for_confidence(confidence: float) -> str:
    conf = max(0.0, min(1.0, float(confidence)))
    if conf >= 0.85:
        return BeliefStatus.CONFIRMED.value
    if conf >= 0.55:
        return BeliefStatus.PROVISIONAL.value
    if conf <= 0.15:
        return BeliefStatus.CONTRADICTED.value
    return BeliefStatus.UNKNOWN.value


def _belief_update(
    *,
    proposition: str,
    posterior: float,
    cause: str,
    evidence: list[EvidenceRef],
    value: Any = None,
    hypothesis_id: str = "",
    expectation_id: str = "",
    reversible: bool = True,
    source_reliability: float = 0.0,
    provenance: Optional[Dict[str, Any]] = None,
) -> BeliefUpdate:
    posterior = max(0.0, min(1.0, float(posterior)))
    prior = 0.5
    return BeliefUpdate(
        proposition=proposition,
        prior=prior,
        posterior=posterior,
        evidence=list(evidence),
        cause=cause,
        value=value,
        status=_belief_status_for_confidence(posterior),
        source_reliability=max(0.0, min(1.0, float(source_reliability))),
        reversible=reversible,
        hypothesis_id=hypothesis_id,
        expectation_id=expectation_id,
        provenance=dict(provenance or {}),
    )


def _belief_updates_for_assessment(
    *,
    action: Action,
    outcome: str,
    effect: EffectKind,
    domain: FailureDomain,
    beliefs: LayerBeliefDeltas,
    detail: Dict[str, Any],
    before_view: Dict[str, Any],
    after_view: Dict[str, Any],
    before_features: Dict[str, Any],
    after_features: Dict[str, Any],
    goal: Optional[Goal],
    notes: list,
) -> list[BeliefUpdate]:
    evidence_conf = 0.85 if detail.get("executor_ok") else 0.55
    source = str(detail.get("actuator") or "unknown")
    refs = [
        EvidenceRef(
            source=source,
            property="effect_kind",
            value=effect.value,
            confidence=evidence_conf,
            ts=float(after_features.get("observation_timestamp") or 0.0) or 0.0,
            detail=str(detail.get("message") or "")[:120],
        )
    ]
    updates: list[BeliefUpdate] = []

    if effect == EffectKind.GOAL_SATISFIED:
        updates.append(
            _belief_update(
                proposition="goal_satisfied",
                posterior=0.95,
                cause="goal evidence met",
                evidence=refs,
                value=True,
                hypothesis_id="goal_reached",
                expectation_id="goal_condition",
                source_reliability=evidence_conf,
                provenance={"action_family": action.action_family, "effect_kind": effect.value},
            )
        )
    elif effect == EffectKind.PROGRESS:
        updates.append(
            _belief_update(
                proposition="goal_progressing",
                posterior=0.78,
                cause="observed forward movement toward the goal",
                evidence=refs,
                value=True,
                hypothesis_id="progress_hypothesis",
                expectation_id="progress_transition",
                source_reliability=evidence_conf,
                provenance={"action_family": action.action_family, "effect_kind": effect.value},
            )
        )
    elif effect == EffectKind.PROMISING_UNRESOLVED:
        updates.append(
            _belief_update(
                proposition="branch_promising",
                posterior=0.72,
                cause="new affordances opened without contradiction",
                evidence=refs,
                value=True,
                hypothesis_id="frontier_branch",
                expectation_id="branch_expansion",
                source_reliability=evidence_conf,
                provenance={"action_family": action.action_family, "effect_kind": effect.value},
            )
        )
    elif effect == EffectKind.REGRESSION:
        updates.append(
            _belief_update(
                proposition="current_path_valid",
                posterior=0.22,
                cause="positive contradiction to the current path",
                evidence=refs,
                value=False,
                hypothesis_id="path_regression",
                expectation_id="regression_check",
                source_reliability=evidence_conf,
                provenance={"action_family": action.action_family, "effect_kind": effect.value},
            )
        )
    elif effect == EffectKind.MISSING_GEOMETRY:
        updates.append(
            _belief_update(
                proposition="actuation_geometry_available",
                posterior=0.18,
                cause="executor lacked geometry for a safe actuation",
                evidence=refs,
                value=False,
                hypothesis_id="geometry_missing",
                expectation_id="geometry_check",
                source_reliability=evidence_conf,
                provenance={"action_family": action.action_family, "effect_kind": effect.value},
            )
        )
    elif effect == EffectKind.ACTUATOR_FAILED:
        updates.append(
            _belief_update(
                proposition="actuator_reliable",
                posterior=0.20,
                cause="executor reported failure",
                evidence=refs,
                value=False,
                hypothesis_id="actuator_failure",
                expectation_id="execution_check",
                source_reliability=evidence_conf,
                provenance={"action_family": action.action_family, "effect_kind": effect.value},
            )
        )
    elif effect == EffectKind.NOT_ATTEMPTED:
        updates.append(
            _belief_update(
                proposition="action_attempted",
                posterior=0.08,
                cause="action was not attempted",
                evidence=refs,
                value=False,
                hypothesis_id="attempt_check",
                expectation_id="execution_attempt",
                source_reliability=evidence_conf,
                provenance={"action_family": action.action_family, "effect_kind": effect.value},
            )
        )
    elif effect == EffectKind.NO_TRANSITION:
        if action.action_family == "type_query":
            updates.append(
                _belief_update(
                    proposition="search_query_landed",
                    posterior=0.35 if after_features.get("query_matches_goal") else 0.18,
                    cause="typed query did not produce a stable transition",
                    evidence=refs,
                    value=bool(after_view.get("search_query") or after_features.get("has_text_query")),
                hypothesis_id="search_field_landing",
                expectation_id="search_query_transition",
                source_reliability=evidence_conf,
                provenance={"action_family": action.action_family, "effect_kind": effect.value},
            )
        )
        else:
            updates.append(
                _belief_update(
                    proposition="world_transition_observed",
                    posterior=0.30,
                    cause="executor completed but no world transition was observed",
                    evidence=refs,
                    value=False,
                hypothesis_id="transition_visibility",
                expectation_id="post_action_settle",
                source_reliability=evidence_conf,
                provenance={"action_family": action.action_family, "effect_kind": effect.value},
            )
        )
    elif effect == EffectKind.TRANSITION_NOT_PERCEIVED:
        updates.append(
            _belief_update(
                proposition="perception_reliable",
                posterior=0.24,
                cause="executor success was not confirmed by settled perception",
                evidence=refs,
                value=False,
                hypothesis_id="perception_failure",
                expectation_id="post_action_observation",
                source_reliability=evidence_conf,
                provenance={"action_family": action.action_family, "effect_kind": effect.value},
            )
        )
    elif effect == EffectKind.REDUNDANT_ALREADY_SATISFIED:
        updates.append(
            _belief_update(
                proposition="goal_already_satisfied",
                posterior=0.88,
                cause="desired state already present before action",
                evidence=refs,
                value=True,
                hypothesis_id="already_satisfied",
                expectation_id="goal_confirmation",
                source_reliability=evidence_conf,
                provenance={"action_family": action.action_family, "effect_kind": effect.value},
            )
        )

    # Layer-level belief updates are still emitted as runtime evidence, but they
    # now live alongside explicit belief updates instead of replacing them.
    for prop, delta in (
        ("reference_resolution", beliefs.reference_resolution),
        ("entity_resolution", beliefs.entity_resolution),
        ("target_actionability", beliefs.target_actionability),
        ("actuator_reliability", beliefs.actuator_reliability),
        ("perception_reliability", beliefs.perception_reliability),
    ):
        if abs(delta) < 1e-6:
            continue
        posterior = max(0.0, min(1.0, 0.5 + delta))
        updates.append(
            _belief_update(
                proposition=prop,
                posterior=posterior,
                cause=f"transition attribution updated {prop}",
                evidence=refs,
                value=posterior,
                hypothesis_id=f"{prop}_layer",
                expectation_id=f"{prop}_expectation",
                source_reliability=evidence_conf,
                provenance={"action_family": action.action_family, "effect_kind": effect.value},
            )
        )

    return updates


def should_advance_reference_hypothesis(
    *,
    assessment: TransitionAssessment,
    layers: HypothesisLayers,
    goal: Goal,
    after_view: Dict[str, Any],
    after_features: Dict[str, Any],
    hyp_index: int,
    n_hypotheses: int,
) -> bool:
    """
    Advance search/reference hypothesis only with positive evidence against intent:

    - attribution implicates REFERENCE (not actuation / not progress)
    - current query was successfully entered
    - resulting world was stably observed
    - no candidate exceeds resolution threshold
    - an alternative hypothesis remains
    """
    if n_hypotheses <= 1 or hyp_index >= n_hypotheses - 1:
        return False
    # Progress / success must never revise the user's reference
    if assessment.outcome in {
        TransitionOutcome.PROGRESS.value,
        TransitionOutcome.PROMISING_UNRESOLVED.value,
        TransitionOutcome.GOAL_SATISFIED.value,
    }:
        return False
    if assessment.effect_kind in {
        EffectKind.PROGRESS.value,
        EffectKind.PROMISING_UNRESOLVED.value,
        EffectKind.GOAL_SATISFIED.value,
        EffectKind.MISSING_GEOMETRY.value,
        EffectKind.ACTUATOR_FAILED.value,
        EffectKind.NOT_ATTEMPTED.value,
    }:
        return False
    if not assessment.implicates_reference:
        return False
    if assessment.likely_failure_domain != FailureDomain.REFERENCE.value:
        return False

    query = str(after_view.get("search_query") or "").strip()
    if not query:
        return False
    if not after_features.get("query_matches_goal"):
        return False

    conf = float(after_features.get("resolution_confidence") or 0)
    policy = str(after_features.get("resolution_policy") or "")
    if conf >= 0.55 and policy == "auto":
        return False

    cands = after_features.get("contact_candidates") or []
    if conf >= 0.55 and cands:
        return False

    if layers.reference_confidence > 0.75 and conf >= 0.4:
        return False

    return True
