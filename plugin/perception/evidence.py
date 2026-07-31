"""Evidence types — sensors emit claims; World Model never sees raw trees."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ObservationEvent:
    """Bus message from a single sensor observation cycle."""

    sensor: str
    timestamp: float
    confidence: float = 1.0
    payload: Dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    degraded: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_bundle(cls, bundle: Any) -> "ObservationEvent":
        """Wrap an ObservationBundle without importing sources (avoid cycles)."""
        obs = getattr(bundle, "observation", None)
        source = str(getattr(bundle, "source_id", "") or getattr(obs, "source", "unknown"))
        conf = 0.3 if getattr(bundle, "degraded", False) else float(getattr(bundle, "coverage_self", 1.0) or 1.0)
        return cls(
            sensor=source,
            timestamp=float(getattr(obs, "timestamp", None) or time.time()),
            confidence=max(0.0, min(1.0, conf)),
            payload={
                "app_name": getattr(obs, "app_name", ""),
                "window_name": getattr(obs, "window_name", ""),
                "node_count": len(getattr(obs, "nodes", None) or []),
                "screenshot_path": getattr(obs, "screenshot_path", None),
                "meta": dict(getattr(obs, "meta", None) or {}),
                "observation": obs,
            },
            latency_ms=float(getattr(bundle, "latency_ms", 0.0) or 0.0),
            degraded=bool(getattr(bundle, "degraded", False)),
        )


@dataclass
class Evidence:
    """A single sourced claim about an entity property."""

    entity_key: str
    property: str
    value: Any
    confidence: float
    source: str
    ts: float = field(default_factory=time.time)
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_key": self.entity_key,
            "property": self.property,
            "value": self.value,
            "confidence": round(float(self.confidence), 4),
            "source": self.source,
            "ts": self.ts,
            "detail": self.detail,
        }


@dataclass
class EvidenceRef:
    """Compact pointer stored on Beliefs / Entities for inspect."""

    source: str
    property: str
    value: Any
    confidence: float
    ts: float = 0.0
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_evidence(cls, ev: Evidence) -> "EvidenceRef":
        return cls(
            source=ev.source,
            property=ev.property,
            value=ev.value,
            confidence=float(ev.confidence),
            ts=float(ev.ts),
            detail=ev.detail,
        )
