"""Layer 1 observation types — LLM-free."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


Bounds = Tuple[float, float, float, float]  # x, y, w, h


@dataclass
class AxNode:
    """Normalized accessibility node (macapptree JSON → Plugin)."""

    role: str = ""
    name: str = ""
    description: str = ""
    value: Optional[str] = None
    enabled: bool = True
    bbox: Bounds = (0.0, 0.0, 0.0, 0.0)
    children: List["AxNode"] = field(default_factory=list)
    raw_id: str = ""
    role_description: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)

    def flatten(self) -> List["AxNode"]:
        out = [self]
        for child in self.children:
            out.extend(child.flatten())
        return out


@dataclass
class Observation:
    """Primary perception unit produced by Layer 1."""

    timestamp: float
    app_name: str
    window_name: str
    bundle_id: str = ""
    ax_tree: Optional[AxNode] = None
    nodes: List[AxNode] = field(default_factory=list)
    screenshot_path: Optional[str] = None
    source: str = "macapptree"  # macapptree | pyobjc | fixture | screen2ax
    coverage: Optional[float] = None
    degraded: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    def summary_yaml(self) -> str:
        """CLI-friendly YAML summary (no full tree dump)."""
        roles: Dict[str, int] = {}
        labels: List[str] = []
        for n in self.nodes:
            roles[n.role or "unknown"] = roles.get(n.role or "unknown", 0) + 1
            label = (n.name or n.description or "").strip()
            if label and len(labels) < 24:
                labels.append(f"{n.role}:{label}"[:80])
        lines = [
            f"App:",
            f"  {self.app_name or '(unknown)'}",
            f"Window:",
            f"  {self.window_name or '(unknown)'}",
            f"Source:",
            f"  {self.source}",
            f"Nodes:",
            f"  {len(self.nodes)}",
        ]
        if self.coverage is not None:
            lines += ["Coverage:", f"  {self.coverage:.2f}"]
        if self.degraded:
            lines += ["Degraded:", "  true"]
        if labels:
            lines.append("Entities:")
            for lab in labels:
                lines.append(f"  - {lab}")
        return "\n".join(lines) + "\n"
