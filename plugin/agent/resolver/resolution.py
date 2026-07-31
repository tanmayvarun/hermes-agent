"""Resolution outcome — intent confidence, not just a name match."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from plugin.worldmodel.entities.entity import Entity

# Single calibrated policy (no per-signal magic margins)
AUTO_RESOLVE = 0.90
OBSERVE_BAND = 0.60  # [OBSERVE_BAND, AUTO) → keep observing / refine search
# below OBSERVE_BAND → ask for confirmation after reasonable attempts


@dataclass
class EvidenceItem:
    signal: str
    value: float
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RankedCandidate:
    name: str
    entity_id: Optional[int] = None
    confidence: float = 0.0
    name_similarity: float = 0.0
    history: float = 0.0
    frequency: float = 0.0
    recency: float = 0.0
    goal_compat: float = 0.0
    evidence: List[EvidenceItem] = field(default_factory=list)
    entity: Optional[Entity] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "entity_id": self.entity_id,
            "confidence": round(self.confidence, 4),
            "name_similarity": round(self.name_similarity, 4),
            "history": round(self.history, 4),
            "frequency": round(self.frequency, 4),
            "recency": round(self.recency, 4),
            "goal_compat": round(self.goal_compat, 4),
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass
class Resolution:
    """Estimate of which entity the user intended."""

    query: str
    winner: Optional[Entity] = None
    winner_name: Optional[str] = None
    confidence: float = 0.0
    candidates: List[RankedCandidate] = field(default_factory=list)
    evidence: List[EvidenceItem] = field(default_factory=list)
    policy: str = "ask"  # auto | observe | ask

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "winner_name": self.winner_name,
            "winner_id": None if self.winner is None else self.winner.id,
            "confidence": round(self.confidence, 4),
            "policy": self.policy,
            "candidates": [c.to_dict() for c in self.candidates[:8]],
            "evidence": [e.to_dict() for e in self.evidence],
        }

    @property
    def auto(self) -> bool:
        return self.policy == "auto" and self.winner is not None

    @property
    def needs_confirmation(self) -> bool:
        return self.policy == "ask"

    @property
    def should_observe(self) -> bool:
        return self.policy == "observe"


def policy_for_confidence(confidence: float) -> str:
    if confidence >= AUTO_RESOLVE:
        return "auto"
    if confidence >= OBSERVE_BAND:
        return "observe"
    return "ask"
