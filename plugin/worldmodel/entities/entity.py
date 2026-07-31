"""Entity types — Layer 5. Plugin-owned, no LLM."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from plugin.worldmodel.belief import Belief

Bounds = Tuple[float, float, float, float]


@dataclass
class Entity:
    id: int
    entity_type: str  # button | textfield | list | static | unknown
    semantic_role: str
    actions: List[str] = field(default_factory=list)
    role: str = ""
    label: str = ""
    bounds: Bounds = (0.0, 0.0, 0.0, 0.0)
    parent_id: Optional[int] = None
    child_ids: List[int] = field(default_factory=list)
    visible: bool = True
    enabled: bool = True
    aliases: List[int] = field(default_factory=list)
    snapshot_count: int = 1
    raw_ax_id: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    # Probabilistic layer
    confidence: float = 1.0
    beliefs: Dict[str, Belief] = field(default_factory=dict)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    miss_frames: int = 0
    entity_key: str = ""

    def __post_init__(self) -> None:
        # IdentityTracker uses Entity(**to_dict()) which dictifies Beliefs
        coerced: Dict[str, Belief] = {}
        for k, v in (self.beliefs or {}).items():
            if isinstance(v, Belief):
                coerced[k] = v
            elif isinstance(v, dict):
                coerced[k] = Belief.from_dict(v)
        self.beliefs = coerced
        if self.bounds is not None and not isinstance(self.bounds, tuple):
            self.bounds = tuple(self.bounds)  # type: ignore[assignment]

    def belief(self, prop: str) -> Optional[Belief]:
        return self.beliefs.get(prop)

    def belief_confidence(self, prop: str, default: float = 0.0) -> float:
        b = self.beliefs.get(prop)
        return default if b is None else float(b.confidence)

    @property
    def pragmatic_role(self) -> str:
        """Display-independent UI role (nav_chrome|cta|status|…)."""
        from plugin.worldmodel.pragmatic_role import get_pragmatic_role

        return get_pragmatic_role(self).value

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Entity":
        bounds = d.get("bounds") or (0, 0, 0, 0)
        beliefs_raw = d.get("beliefs") or {}
        beliefs: Dict[str, Belief] = {}
        for k, v in beliefs_raw.items():
            if isinstance(v, Belief):
                beliefs[k] = v
            elif isinstance(v, dict):
                beliefs[k] = Belief.from_dict(v)
        return cls(
            id=int(d["id"]),
            entity_type=str(d.get("entity_type") or "unknown"),
            semantic_role=str(d.get("semantic_role") or ""),
            actions=list(d.get("actions") or []),
            role=str(d.get("role") or ""),
            label=str(d.get("label") or ""),
            bounds=tuple(bounds),  # type: ignore[arg-type]
            parent_id=d.get("parent_id"),
            child_ids=list(d.get("child_ids") or []),
            visible=bool(d.get("visible", True)),
            enabled=bool(d.get("enabled", True)),
            aliases=list(d.get("aliases") or []),
            snapshot_count=int(d.get("snapshot_count") or 1),
            raw_ax_id=str(d.get("raw_ax_id") or ""),
            attributes=dict(d.get("attributes") or {}),
            confidence=float(d.get("confidence") if d.get("confidence") is not None else 1.0),
            beliefs=beliefs,
            evidence=list(d.get("evidence") or []),
            miss_frames=int(d.get("miss_frames") or 0),
            entity_key=str(d.get("entity_key") or ""),
        )
