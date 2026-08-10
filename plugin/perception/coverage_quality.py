"""Split epistemic coverage — transport health ≠ task knowledge.

AX shell-only (App + Window + unknown) must never report task coverage 1.0.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set

# Roles that are chrome / shell, not task content.
_CHROME_ROLES: Set[str] = {
    "axapplication",
    "application",
    "axwindow",
    "window",
    "axmenubar",
    "menubar",
    "axmenu",
    "menu",
    "axmenuitem",
    "unknown",
    "axunknown",
    "axgroup",  # often empty shell grouping
}


@dataclass
class CoverageQuality:
    sensor_transport_health: float = 0.0
    structural_coverage: float = 0.0
    semantic_coverage: float = 0.0
    task_relevant_coverage: float = 0.0
    actionable_coverage: float = 0.0
    grounding_coverage: float = 0.0
    chrome_only: bool = False
    content_node_count: int = 0
    chrome_node_count: int = 0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k in (
            "sensor_transport_health",
            "structural_coverage",
            "semantic_coverage",
            "task_relevant_coverage",
            "actionable_coverage",
            "grounding_coverage",
        ):
            d[k] = round(float(d[k]), 3)
        return d

    @property
    def task_coverage(self) -> float:
        """Conservative scalar for gates that still want one number."""
        return min(
            self.structural_coverage,
            max(self.semantic_coverage, self.actionable_coverage),
        )


def _role(node: Any) -> str:
    if isinstance(node, dict):
        return str(
            node.get("role") or node.get("ax_role") or node.get("kind") or ""
        ).strip().lower().replace(" ", "")
    return str(getattr(node, "role", "") or "").strip().lower().replace(" ", "")


def _is_chrome(node: Any) -> bool:
    return _role(node) in _CHROME_ROLES


def compute_coverage_quality(
    *,
    nodes: Optional[Sequence[Any]] = None,
    has_screenshot: bool = False,
    ocr_text_count: int = 0,
    semantic_object_count: int = 0,
    actionable_control_count: int = 0,
    grounded_object_count: int = 0,
    task_object_count: int = 0,
    ax_transport_ok: bool = True,
) -> CoverageQuality:
    node_list = list(nodes or [])
    chrome = sum(1 for n in node_list if _is_chrome(n))
    content = max(0, len(node_list) - chrome)
    chrome_only = bool(node_list) and content == 0

    transport = 1.0 if ax_transport_ok else 0.0
    if node_list:
        transport = max(transport, 0.8)

    # Structural: non-chrome AX depth. Shell-only ⇒ ~0.
    if chrome_only:
        structural = 0.05
    elif content >= 8:
        structural = 1.0
    elif content >= 3:
        structural = 0.6 + 0.1 * min(content, 4)
    elif content > 0:
        structural = 0.25 * content
    else:
        structural = 0.0

    # Semantic: OCR / VLM objects.
    sem_score = 0.0
    if semantic_object_count > 0:
        sem_score = min(1.0, 0.35 + 0.1 * semantic_object_count)
    if ocr_text_count > 0:
        sem_score = max(sem_score, min(1.0, 0.3 + 0.05 * min(ocr_text_count, 14)))
    if has_screenshot and sem_score == 0.0:
        sem_score = 0.15  # pixels present but unread

    task_n = max(int(task_object_count), int(semantic_object_count), content)
    task_rel = 0.0
    if task_n > 0:
        task_rel = min(1.0, (semantic_object_count + content) / float(max(task_n, 1)))
    if chrome_only and semantic_object_count == 0:
        task_rel = 0.0

    actionable = 0.0
    if actionable_control_count > 0:
        actionable = min(1.0, 0.4 + 0.15 * actionable_control_count)

    grounding = 0.0
    denom = max(int(task_object_count), int(semantic_object_count), 1)
    if grounded_object_count > 0:
        grounding = min(1.0, grounded_object_count / float(denom))
    if chrome_only and grounded_object_count == 0:
        grounding = 0.0

    notes: List[str] = []
    if chrome_only:
        notes.append("ax_chrome_only")
    if has_screenshot and structural < 0.3:
        notes.append("screenshot_rich_ax_poor")
    if structural >= 0.8 and not has_screenshot:
        notes.append("rich_ax_no_screenshot")
    if actionable == 0.0:
        notes.append("no_actionable_controls")

    return CoverageQuality(
        sensor_transport_health=transport,
        structural_coverage=structural,
        semantic_coverage=sem_score,
        task_relevant_coverage=task_rel,
        actionable_coverage=actionable,
        grounding_coverage=grounding,
        chrome_only=chrome_only,
        content_node_count=content,
        chrome_node_count=chrome,
        notes=notes,
    )


def estimate_task_coverage(
    obs: Any, *, visual_node_estimate: Optional[int] = None
) -> float:
    """Drop-in replacement for fusion estimate_coverage — never 1.0 on shell."""
    nodes = getattr(obs, "nodes", None) or []
    if isinstance(obs, dict):
        nodes = obs.get("nodes") or []
    has_shot = bool(
        getattr(obs, "screenshot_path", None)
        or getattr(obs, "screenshot", None)
        or (isinstance(obs, dict) and (obs.get("screenshot_path") or obs.get("screenshot")))
    )
    q = compute_coverage_quality(
        nodes=nodes,
        has_screenshot=has_shot,
        ax_transport_ok=True,
    )
    # Legacy visual denominator still lowers structural when provided.
    if visual_node_estimate and visual_node_estimate > 0:
        accessible = q.content_node_count
        ratio = min(1.0, accessible / float(visual_node_estimate))
        return min(q.task_coverage, ratio)
    return q.task_coverage
