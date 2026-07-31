"""Belief-centric runtime types for the model-based control loop.

These types are intentionally generic so controller, transition attribution,
and future planners can share the same contract.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from plugin.perception.evidence import EvidenceRef


class BeliefStatus(str, Enum):
    CONFIRMED = "confirmed"
    PROVISIONAL = "provisional"
    STALE = "stale"
    OCCLUDED = "occluded"
    CONTRADICTED = "contradicted"
    UNKNOWN = "unknown"


class ExperimentKind(str, Enum):
    OBSERVATIONAL = "observational"
    INTERVENTIONAL = "interventional"
    MIXED = "mixed"


@dataclass
class Belief:
    proposition: str
    value: Any
    confidence: float
    status: str = BeliefStatus.UNKNOWN.value
    supporting_evidence: List[EvidenceRef] = field(default_factory=list)
    contradicting_evidence: List[EvidenceRef] = field(default_factory=list)
    source_reliability: float = 0.0
    updated_at: float = field(default_factory=time.time)
    valid_until: Optional[float] = None
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["confidence"] = round(float(self.confidence), 4)
        out["supporting_evidence"] = [e.to_dict() for e in self.supporting_evidence[-8:]]
        out["contradicting_evidence"] = [e.to_dict() for e in self.contradicting_evidence[-8:]]
        return out


@dataclass
class Uncertainty:
    question: str
    importance: float
    blocking_goal_predicates: List[str] = field(default_factory=list)
    candidate_values: List[Any] = field(default_factory=list)
    confidence_gap: float = 0.0
    staleness: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Hypothesis:
    explanation: str
    confidence: float
    supporting_evidence: List[EvidenceRef] = field(default_factory=list)
    contradicting_evidence: List[EvidenceRef] = field(default_factory=list)
    causal_assumptions: List[str] = field(default_factory=list)
    predicted_observations: List[str] = field(default_factory=list)
    discriminating_experiments: List[str] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["confidence"] = round(float(self.confidence), 4)
        out["supporting_evidence"] = [e.to_dict() for e in self.supporting_evidence[-8:]]
        out["contradicting_evidence"] = [e.to_dict() for e in self.contradicting_evidence[-8:]]
        return out


@dataclass
class Experiment:
    capability: str
    target: Optional[str] = None
    kind: str = ExperimentKind.MIXED.value
    beliefs_tested: List[str] = field(default_factory=list)
    beliefs_changed: List[str] = field(default_factory=list)
    expected_goal_progress: float = 0.0
    expected_information_gain: float = 0.0
    risk: float = 0.0
    cost: float = 0.0
    reversible: bool = True
    preconditions: List[str] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Expectation:
    predicted_world_changes: List[str] = field(default_factory=list)
    predicted_non_changes: List[str] = field(default_factory=list)
    expected_affordances: List[str] = field(default_factory=list)
    timing_ms: int = 0
    contradiction_conditions: List[str] = field(default_factory=list)
    sensor_requirements: List[str] = field(default_factory=list)
    side_effects: List[str] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GoalCondition:
    proposition: str
    desired_value: Any
    required_confidence: float = 0.8
    evidence_requirements: List[str] = field(default_factory=list)
    status: str = "intermediate"
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BeliefUpdate:
    proposition: str
    prior: float
    posterior: float
    evidence: List[EvidenceRef] = field(default_factory=list)
    cause: str = ""
    value: Any = None
    status: str = BeliefStatus.UNKNOWN.value
    source_reliability: float = 0.0
    updated_at: float = field(default_factory=time.time)
    reversible: bool = True
    expectation_id: str = ""
    hypothesis_id: str = ""
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["prior"] = round(float(self.prior), 4)
        out["posterior"] = round(float(self.posterior), 4)
        out["evidence"] = [e.to_dict() for e in self.evidence[-8:]]
        return out

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BeliefUpdate":
        refs: List[EvidenceRef] = []
        for item in d.get("evidence") or []:
            if isinstance(item, EvidenceRef):
                refs.append(item)
            elif isinstance(item, dict):
                refs.append(
                    EvidenceRef(
                        source=str(item.get("source") or ""),
                        property=str(item.get("property") or ""),
                        value=item.get("value"),
                        confidence=float(item.get("confidence") or 0.0),
                        ts=float(item.get("ts") or 0.0),
                        detail=str(item.get("detail") or ""),
                    )
                )
        return cls(
            proposition=str(d.get("proposition") or ""),
            prior=float(d.get("prior") or 0.0),
            posterior=float(d.get("posterior") or 0.0),
            evidence=refs,
            cause=str(d.get("cause") or ""),
            value=d.get("value"),
            status=str(d.get("status") or BeliefStatus.UNKNOWN.value),
            source_reliability=float(d.get("source_reliability") or 0.0),
            updated_at=float(d.get("updated_at") or time.time()),
            reversible=bool(d.get("reversible", True)),
            expectation_id=str(d.get("expectation_id") or ""),
            hypothesis_id=str(d.get("hypothesis_id") or ""),
            provenance=dict(d.get("provenance") or {}),
        )


@dataclass
class BeliefStore:
    beliefs: Dict[str, Belief] = field(default_factory=dict)
    uncertainties: Dict[str, Uncertainty] = field(default_factory=dict)
    hypotheses: Dict[str, Hypothesis] = field(default_factory=dict)
    experiments: Dict[str, Experiment] = field(default_factory=dict)
    expectations: Dict[str, Expectation] = field(default_factory=dict)
    goal_conditions: Dict[str, GoalCondition] = field(default_factory=dict)
    belief_updates: List[BeliefUpdate] = field(default_factory=list)
    active_uncertainty_id: str = ""
    active_hypothesis_ids: List[str] = field(default_factory=list)
    active_experiment_id: str = ""
    active_expectation_id: str = ""

    def _status_for(self, confidence: float, existing: Optional[Belief] = None) -> str:
        conf = max(0.0, min(1.0, float(confidence)))
        if existing is not None and existing.status == BeliefStatus.OCCLUDED.value and conf >= 0.4:
            return BeliefStatus.OCCLUDED.value
        if conf >= 0.85:
            return BeliefStatus.CONFIRMED.value
        if conf >= 0.55:
            return BeliefStatus.PROVISIONAL.value
        if conf <= 0.15:
            return BeliefStatus.CONTRADICTED.value
        return BeliefStatus.UNKNOWN.value

    def apply_update(self, update: BeliefUpdate) -> Belief:
        prior = self.beliefs.get(update.proposition)
        prior_conf = float(prior.confidence if prior is not None else update.prior)
        confidence = max(0.0, min(1.0, float(update.posterior)))
        status = update.status if update.status != BeliefStatus.UNKNOWN.value else self._status_for(confidence, prior)
        if prior is None:
            belief = Belief(
                proposition=update.proposition,
                value=update.value,
                confidence=confidence,
                status=status,
                supporting_evidence=list(update.evidence) if confidence >= prior_conf else [],
                contradicting_evidence=[] if confidence >= prior_conf else list(update.evidence),
                source_reliability=float(update.source_reliability or 0.0),
                updated_at=update.updated_at,
                valid_until=None,
                provenance=dict(update.provenance or {}),
            )
        else:
            supporting = list(prior.supporting_evidence)
            contradicting = list(prior.contradicting_evidence)
            if confidence >= prior_conf:
                supporting.extend(update.evidence)
            else:
                contradicting.extend(update.evidence)
            belief = Belief(
                proposition=update.proposition,
                value=update.value if update.value is not None else prior.value,
                confidence=confidence,
                status=status,
                supporting_evidence=supporting[-8:],
                contradicting_evidence=contradicting[-8:],
                source_reliability=max(prior.source_reliability, float(update.source_reliability or 0.0)),
                updated_at=update.updated_at,
                valid_until=prior.valid_until,
                provenance={**prior.provenance, **(update.provenance or {})},
            )
        self.beliefs[update.proposition] = belief
        self.belief_updates.append(update)
        return belief

    def belief(self, proposition: str) -> Optional[Belief]:
        return self.beliefs.get(proposition)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beliefs": {k: v.to_dict() for k, v in self.beliefs.items()},
            "uncertainties": {k: v.to_dict() for k, v in self.uncertainties.items()},
            "hypotheses": {k: v.to_dict() for k, v in self.hypotheses.items()},
            "experiments": {k: v.to_dict() for k, v in self.experiments.items()},
            "expectations": {k: v.to_dict() for k, v in self.expectations.items()},
            "goal_conditions": {k: v.to_dict() for k, v in self.goal_conditions.items()},
            "belief_updates": [u.to_dict() for u in self.belief_updates[-32:]],
            "active_uncertainty_id": self.active_uncertainty_id,
            "active_hypothesis_ids": list(self.active_hypothesis_ids),
            "active_experiment_id": self.active_experiment_id,
            "active_expectation_id": self.active_expectation_id,
        }
