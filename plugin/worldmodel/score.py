"""WorldViewScore — faithfulness from fused beliefs (no agreement floors)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from plugin.perception.observation import Observation
from plugin.worldmodel.model import WorldPatch

_CHROME_ONLY_ROLES = {
    "axapplication",
    "axwindow",
    "axmenubar",
    "axmenubaritem",
    "axmenu",
    "axmenuitem",
}


def _node_text(node: Any) -> str:
    parts = [
        getattr(node, "name", ""),
        getattr(node, "description", ""),
        getattr(node, "value", ""),
    ]
    return " ".join(str(part or "").strip() for part in parts if str(part or "").strip()).strip()


def _content_node_counts(obs: Observation) -> tuple[int, int]:
    content = 0
    chrome = 0
    for node in obs.nodes or []:
        role = str(getattr(node, "role", "") or "").strip().lower()
        if role in _CHROME_ONLY_ROLES:
            chrome += 1
            continue
        if _node_text(node):
            content += 1
    return content, chrome


@dataclass
class WorldViewScore:
    overall: float = 0.0
    retention: float = 1.0
    source_agreement: float = 1.0
    coverage: float = 1.0
    semantic_consistency: float = 1.0
    mean_belief: float = 0.0
    freshness_s: float = 0.0
    degraded: bool = False
    needs_reobserve: bool = False
    components: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _mean_entity_belief_confidence(entities: List[Any]) -> float:
    if not entities:
        return 0.0
    vals = []
    for e in entities:
        c = getattr(e, "confidence", None)
        if c is not None:
            vals.append(float(c))
            continue
        beliefs = getattr(e, "beliefs", None) or {}
        if beliefs:
            vals.append(sum(float(b.confidence) for b in beliefs.values()) / max(1, len(beliefs)))
    return sum(vals) / len(vals) if vals else 0.0


def compute_worldview_score(
    obs: Observation,
    patch: WorldPatch,
    *,
    source_agreement: Optional[float] = None,
    semantic_consistency: Optional[float] = None,
    fusion_meta: Optional[Dict[str, Any]] = None,
    entities: Optional[List[Any]] = None,
) -> WorldViewScore:
    retention = float(patch.retention) if patch.retention is not None else 1.0
    ret_n = 1.0 if retention <= 0.0 and not patch.matched_ids else max(0.0, min(1.0, retention))

    node_count = len(obs.nodes)
    app_content_node_count, chrome_only_node_count = _content_node_counts(obs)
    has_shot = bool(
        getattr(obs, "screenshot_path", None) or getattr(obs, "screenshot", None)
    )
    try:
        from plugin.perception.coverage_quality import compute_coverage_quality

        cq = compute_coverage_quality(
            nodes=list(obs.nodes or []),
            has_screenshot=has_shot,
            ax_transport_ok=True,
        )
        cov = float(cq.task_coverage)
        coverage_quality = cq.to_dict()
    except Exception:
        cov = obs.coverage
        if cov is None:
            cov = 0.2 if node_count > 0 else 0.0
        # Never treat tiny shell trees as full coverage.
        if node_count <= 3 and float(cov) >= 0.99:
            cov = 0.2
        coverage_quality = {}
    cov = max(0.0, min(1.0, float(cov)))

    agree = source_agreement
    if agree is None and fusion_meta:
        agree = fusion_meta.get("agreement")
    assemble_mode = bool(
        isinstance(fusion_meta, dict) and fusion_meta.get("fusion_mode") == "assemble"
    )
    if agree is None:
        # Assemble-only (and other non-rival paths) have no agreement signal.
        # Do not invent a mid penalty that thrash-reobserves a usable tree.
        agree = 1.0 if app_content_node_count > 0 else (0.5 if node_count > 0 else 0.0)
    agree = max(0.0, min(1.0, float(agree)))

    mean_belief = _mean_entity_belief_confidence(entities or [])
    if mean_belief <= 0.0 and cov > 0:
        # Projection path: use coverage as proxy until beliefs attached
        mean_belief = cov

    sem = semantic_consistency
    if sem is None:
        conflict_n = 0
        if fusion_meta and not assemble_mode:
            conflict_n = int(fusion_meta.get("conflict_count") or len(fusion_meta.get("conflicts") or []))
        sem = max(0.3, 0.9 - 0.05 * conflict_n) if not obs.degraded else 0.5
        # Assemble + chrome-only must not claim perfect semantic consistency.
        if assemble_mode and not obs.degraded and app_content_node_count > 0:
            sem = 1.0
        elif assemble_mode and app_content_node_count == 0:
            sem = min(float(sem), 0.35)
    sem = max(0.0, min(1.0, float(sem)))

    needs = bool(getattr(patch, "needs_reobserve", False))
    # Rival fusion used to set needs_reobserve from agreement/conflicts. Assembly
    # never does; only real emptiness (handled below) may escalate.
    if fusion_meta and fusion_meta.get("needs_reobserve") and not assemble_mode:
        needs = True
    task_sufficient = app_content_node_count >= 3 or bool(
        any(
            bool(getattr(node, "value", None))
            or str(getattr(node, "name", "") or "").strip()
            for node in obs.nodes or []
            if str(getattr(node, "role", "") or "").strip().lower()
            not in {"axapplication", "axwindow", "axmenubar", "axmenubaritem", "axmenu", "axmenuitem"}
        )
    )
    if node_count >= 4 and not task_sufficient:
        needs = True
    if node_count <= 1:
        needs = True
    # Chrome-only shell: force reobserve / OCR path.
    if app_content_node_count == 0 and node_count > 0:
        needs = True
        task_sufficient = False

    degraded = bool(obs.degraded) or cov < 0.5 or agree < 0.35 or mean_belief < 0.4 or needs or not task_sufficient
    # Belief-centric overall (no artificial agreement floors)
    overall = 0.25 * ret_n + 0.20 * cov + 0.20 * agree + 0.15 * sem + 0.20 * mean_belief
    if degraded:
        overall *= 0.9
    if needs:
        overall = min(overall, 0.55)
    if node_count <= 1:
        overall = min(overall, 0.2)
    if app_content_node_count == 0:
        overall = min(overall, 0.35)

    components = {
        "node_count": node_count,
        "app_content_node_count": app_content_node_count,
        "chrome_only_node_count": chrome_only_node_count,
        "task_sufficient": task_sufficient,
        "source": obs.source,
        "retention_raw": retention,
        "fusion": fusion_meta or {},
        "mean_belief": round(mean_belief, 4),
        "needs_reobserve": needs,
        "coverage_quality": coverage_quality,
    }
    return WorldViewScore(
        overall=round(overall, 4),
        retention=round(ret_n, 4),
        source_agreement=round(agree, 4),
        coverage=round(cov, 4),
        semantic_consistency=round(sem, 4),
        mean_belief=round(mean_belief, 4),
        freshness_s=0.0,
        degraded=degraded,
        needs_reobserve=needs,
        components=components,
    )
