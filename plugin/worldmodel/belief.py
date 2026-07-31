"""Probabilistic beliefs over entity properties (SLAM-style GUI state)."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from plugin.perception.evidence import Evidence, EvidenceRef


@dataclass
class Belief:
    """Posterior estimate for one property."""

    value: Any
    confidence: float = 0.5
    updated_at: float = field(default_factory=time.time)
    evidence: List[EvidenceRef] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "confidence": round(float(self.confidence), 4),
            "updated_at": self.updated_at,
            "evidence": [e.to_dict() for e in self.evidence[-8:]],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Belief":
        refs = []
        for e in d.get("evidence") or []:
            if isinstance(e, dict):
                refs.append(EvidenceRef(**{k: e[k] for k in ("source", "property", "value", "confidence", "ts", "detail") if k in e}))
        return cls(
            value=d.get("value"),
            confidence=float(d.get("confidence") or 0.5),
            updated_at=float(d.get("updated_at") or time.time()),
            evidence=refs,
        )

    def blend(self, other_value: Any, other_conf: float, *, source: str, prop: str, detail: str = "") -> "Belief":
        """Weighted confidence blend; conflict lowers confidence."""
        oc = max(0.0, min(1.0, float(other_conf)))
        sc = max(0.0, min(1.0, float(self.confidence)))
        same = self.value == other_value
        if same:
            # Reinforce
            new_c = min(0.99, sc + (1.0 - sc) * oc * 0.55)
            new_v = other_value if oc >= sc else self.value
        else:
            # Conflict — prefer higher confidence, shrink certainty
            if oc > sc:
                new_v = other_value
                new_c = oc * (1.0 - 0.35 * sc)
            else:
                new_v = self.value
                new_c = sc * (1.0 - 0.35 * oc)
            new_c = max(0.15, min(0.85, new_c))
        ref = EvidenceRef(source=source, property=prop, value=other_value, confidence=oc, ts=time.time(), detail=detail)
        ev = list(self.evidence[-7:]) + [ref]
        return Belief(value=new_v, confidence=new_c, updated_at=time.time(), evidence=ev)

    def decay(self, factor: float = 0.92) -> "Belief":
        return Belief(
            value=self.value,
            confidence=max(0.05, float(self.confidence) * factor),
            updated_at=self.updated_at,
            evidence=list(self.evidence),
        )


def belief_from_evidence(ev: Evidence) -> Belief:
    return Belief(
        value=ev.value,
        confidence=float(ev.confidence),
        updated_at=float(ev.ts),
        evidence=[EvidenceRef.from_evidence(ev)],
    )
