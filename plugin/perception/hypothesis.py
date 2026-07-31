"""Entity hypotheses — interpreters emit world claims, not raw sensor dumps."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from plugin.worldmodel.entities.normalize import _clean_label

Bounds = Tuple[float, float, float, float]


def role_bucket(role: str) -> str:
    r = (role or "").lower()
    if "button" in r or "menuitem" in r or "checkbox" in r or "radio" in r:
        return "button"
    if "text" in r or "search" in r or "edit" in r or "combo" in r:
        return "textfield"
    if "link" in r:
        return "link"
    if "static" in r or "text" in r:
        return "static"
    if "cell" in r or "row" in r:
        return "cell"
    return r.replace("ax", "")[:24] or "unknown"


def hypothesis_key(
    role: str,
    label: str,
    bounds: Optional[Bounds] = None,
    *,
    grid: int = 20,
) -> str:
    """Stable association key across sensors (role + label + coarse bbox)."""
    lab = _clean_label(label or "")[:40].lower()
    bucket = role_bucket(role)
    if bounds and len(bounds) >= 2:
        x = int(float(bounds[0]) // grid)
        y = int(float(bounds[1]) // grid)
    else:
        x, y = 0, 0
    return f"{bucket}|{lab}|{x},{y}"


@dataclass
class EntityHypothesis:
    """Independent interpreter's hypothesis about one UI entity."""

    key: str
    role: str = ""
    label: str = ""
    bounds: Bounds = (0.0, 0.0, 0.0, 0.0)
    actions: List[str] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    source: str = ""
    raw_refs: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def make(
        cls,
        *,
        role: str,
        label: str,
        bounds: Bounds = (0.0, 0.0, 0.0, 0.0),
        actions: Optional[List[str]] = None,
        properties: Optional[Dict[str, Any]] = None,
        confidence: float = 0.5,
        source: str = "",
        raw_refs: Optional[Dict[str, Any]] = None,
    ) -> "EntityHypothesis":
        return cls(
            key=hypothesis_key(role, label, bounds),
            role=role,
            label=_clean_label(label),
            bounds=bounds,
            actions=list(actions or []),
            properties=dict(properties or {}),
            confidence=max(0.0, min(1.0, float(confidence))),
            source=source,
            raw_refs=dict(raw_refs or {}),
        )
