"""Structured user reference — interpreted name + kind (not raw string matching)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class Reference:
    """Semantic interpretation of a user referring expression."""

    raw: str
    name: str  # canonical display-name hypothesis
    kind: str = "unknown"  # contact | group | community | unknown
    confidence: float = 0.5
    search_hypotheses: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Reference":
        return cls(
            raw=str(d.get("raw") or ""),
            name=str(d.get("name") or d.get("raw") or ""),
            kind=str(d.get("kind") or "unknown"),
            confidence=float(d.get("confidence") or 0.5),
            search_hypotheses=list(d.get("search_hypotheses") or []),
        )

    @property
    def active_name(self) -> str:
        return (self.name or self.raw or "").strip()
