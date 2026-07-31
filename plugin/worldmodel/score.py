"""WorldViewScore — faithfulness from fused beliefs (no agreement floors)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from plugin.perception.observation import Observation
from plugin.worldmodel.model import WorldPatch


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

    cov = obs.coverage
    if cov is None:
        cov = 1.0 if len(obs.nodes) > 0 else 0.0
    cov = max(0.0, min(1.0, float(cov)))

    agree = source_agreement
    if agree is None and fusion_meta:
        agree = fusion_meta.get("agreement")
    if agree is None:
        # Unknown agreement (single source) — neutral, not floored high
        agree = 0.65 if len(obs.nodes) > 0 else 0.0
    agree = max(0.0, min(1.0, float(agree)))

    mean_belief = _mean_entity_belief_confidence(entities or [])
    if mean_belief <= 0.0 and cov > 0:
        # Projection path: use coverage as proxy until beliefs attached
        mean_belief = cov

    sem = semantic_consistency
    if sem is None:
        conflict_n = 0
        if fusion_meta:
            conflict_n = int(fusion_meta.get("conflict_count") or len(fusion_meta.get("conflicts") or []))
        sem = max(0.3, 0.9 - 0.05 * conflict_n) if not obs.degraded else 0.5
    sem = max(0.0, min(1.0, float(sem)))

    needs = bool(getattr(patch, "needs_reobserve", False))
    if fusion_meta and fusion_meta.get("needs_reobserve"):
        needs = True
    node_count = len(obs.nodes)
    if node_count <= 1:
        needs = True

    degraded = bool(obs.degraded) or cov < 0.5 or agree < 0.35 or mean_belief < 0.4 or needs
    # Belief-centric overall (no artificial agreement floors)
    overall = 0.25 * ret_n + 0.20 * cov + 0.20 * agree + 0.15 * sem + 0.20 * mean_belief
    if degraded:
        overall *= 0.9
    if needs:
        overall = min(overall, 0.55)
    if node_count <= 1:
        overall = min(overall, 0.2)

    components = {
        "node_count": node_count,
        "source": obs.source,
        "retention_raw": retention,
        "fusion": fusion_meta or {},
        "mean_belief": round(mean_belief, 4),
        "needs_reobserve": needs,
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
