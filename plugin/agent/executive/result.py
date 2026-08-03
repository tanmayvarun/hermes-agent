"""CapabilityResult — the one envelope every capability returns.

The design's invariant is that the executive updates its own beliefs from a
*uniform* return shape, no matter whether the thing it invoked was a perceptor,
a deterministic tool, or a bounded sub-agent. Today the perceptor returns a
``UnifiedProposal`` and the capability handlers return a ``CapabilityOutcome``;
the executive has to special-case each.

``CapabilityResult`` is that uniform envelope:

- observations            : claims about the world (name/value/confidence/status)
- proposed_belief_updates : facts the executive should arbitrate into its state
- proposed_actions        : ranked actions the capability suggests (advisory)
- side_effects            : what running it changed ("none"/"navigation"/…)
- missing_information     : what it could not establish
- status                  : success | partial | blocked | failed

Adapters wrap the two existing shapes so callers can migrate incrementally
without every producer being rewritten at once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

STATUS_VALUES = ("success", "partial", "blocked", "failed")


@dataclass
class Observation:
    """One claim a capability made about the world."""

    claim: str = ""
    value: str = ""
    confidence: float = 0.0
    status: str = "observed"
    evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim": self.claim,
            "value": self.value,
            "confidence": round(float(self.confidence or 0.0), 3),
            "status": self.status,
            "evidence": self.evidence[:160],
        }


@dataclass
class CapabilityResult:
    """The uniform return shape for perceptors, tools and skills alike."""

    status: str = "success"
    capability: str = ""
    observations: List[Observation] = field(default_factory=list)
    # Facts to arbitrate into the workspace: {name: value} or {name: (value, conf)}.
    proposed_belief_updates: Dict[str, Any] = field(default_factory=dict)
    proposed_actions: List[Dict[str, Any]] = field(default_factory=list)
    side_effects: List[str] = field(default_factory=lambda: ["none"])
    missing_information: List[str] = field(default_factory=list)
    confidence: float = 0.0
    message: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # An unrecognised status fails safe: the executive should not treat an
        # ambiguous return as a success.
        if self.status not in STATUS_VALUES:
            self.status = "failed"

    @property
    def ok(self) -> bool:
        return self.status in {"success", "partial"}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "capability": self.capability,
            "observations": [o.to_dict() for o in self.observations],
            "proposed_belief_updates": dict(self.proposed_belief_updates),
            "proposed_actions": list(self.proposed_actions),
            "side_effects": list(self.side_effects),
            "missing_information": list(self.missing_information),
            "confidence": round(float(self.confidence or 0.0), 3),
            "message": self.message[:200],
        }


def from_capability_outcome(outcome: Any) -> CapabilityResult:
    """Wrap a ``CapabilityOutcome`` (ok/message/evidence) in the envelope."""
    ok = bool(getattr(outcome, "ok", False))
    evidence = dict(getattr(outcome, "evidence", None) or {})
    # A handler that ran but changed nothing useful is "partial", not "failed".
    if ok:
        status = "success"
    elif evidence.get("blocked") or "blocked" in str(getattr(outcome, "message", "")).lower():
        status = "blocked"
    else:
        status = "failed"
    side = evidence.get("side_effects")
    if isinstance(side, str):
        side = [side]
    elif not isinstance(side, list):
        side = ["navigation"] if ok else ["none"]
    return CapabilityResult(
        status=status,
        capability=str(getattr(outcome, "capability", "") or ""),
        proposed_actions=[],
        side_effects=[str(s) for s in side] or ["none"],
        missing_information=[] if ok else [str(getattr(outcome, "message", "") or "capability failed")],
        message=str(getattr(outcome, "message", "") or ""),
        evidence=evidence,
    )


def from_unified_proposal(proposal: Any) -> CapabilityResult:
    """Wrap the perceptor's ``UnifiedProposal`` in the envelope.

    Perception is a capability like any other: its observed_state becomes
    observations, its belief_updates become proposed belief updates, its ranked
    next_actions become advisory proposed_actions, and coverage/evidence_gaps
    become the missing-information account.
    """
    observed = dict(getattr(proposal, "observed_state", None) or {})
    observations: List[Observation] = []
    conf = float(getattr(proposal, "confidence", 0.0) or 0.0)
    for name, value in observed.items():
        if value in (None, "", [], {}):
            continue
        observations.append(
            Observation(claim=str(name), value=str(value), confidence=conf, status="observed")
        )

    belief_updates: Dict[str, Any] = {}
    for update in getattr(proposal, "belief_updates", None) or []:
        if not isinstance(update, dict):
            continue
        key = str(update.get("predicate") or update.get("name") or "").strip()
        if not key:
            continue
        belief_updates[key] = (
            str(update.get("value", "")),
            float(update.get("confidence", conf) or 0.0),
        )

    ranked = [a for a in (getattr(proposal, "next_actions", None) or []) if isinstance(a, dict)]
    if not ranked and isinstance(getattr(proposal, "next_action", None), dict) and proposal.next_action:
        ranked = [proposal.next_action]

    missing = list(getattr(proposal, "missing_evidence", None) or [])
    missing += list(getattr(proposal, "evidence_gaps", None) or [])

    coverage = float(getattr(proposal, "coverage", 1.0) or 1.0)
    status = "success" if coverage >= 0.34 and (observations or ranked) else "partial"

    return CapabilityResult(
        status=status,
        capability="perception",
        observations=observations,
        proposed_belief_updates=belief_updates,
        proposed_actions=ranked,
        side_effects=["none"],
        missing_information=[str(m) for m in missing if str(m).strip()],
        confidence=conf,
        message=str(getattr(proposal, "scene_summary", "") or ""),
        evidence={"coverage": coverage},
    )


def commit_result_beliefs(execution_state: Any, result: CapabilityResult, *, source: str = "") -> None:
    """Route a result's belief updates through the workspace arbitration path."""
    from plugin.agent.executive.sync import commit_beliefs

    facts: Dict[str, Any] = {}
    for obs in result.observations:
        if obs.claim and obs.value:
            facts[obs.claim] = (obs.value, obs.confidence)
    facts.update(result.proposed_belief_updates)
    if facts:
        commit_beliefs(
            execution_state,
            source=source or result.capability or "capability",
            facts=facts,
            confidence=result.confidence,
        )
