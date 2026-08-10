"""Assemble multi-source observations for the multimodal perceptor.

This layer enumerates modalities (AX, OCR, screenshot + capture transform).
It does **not** reconcile competing accounts of the screen: no source scoring,
no agreement thresholds, no LLM referee. Semantic fusion belongs to
``unified_cognition``; temporal coherence (x + Δx) belongs to the world critic.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from plugin.perception.evidence import Evidence, EvidenceRef, ObservationEvent
from plugin.perception.hypothesis import EntityHypothesis, hypothesis_key, role_bucket
from plugin.perception.interpreters.ax_tree import AxTreeInterpreter
from plugin.perception.interpreters.vision import VisionInterpreter
from plugin.perception.observation import AxNode, Observation
from plugin.perception.sources.base import ObservationBundle
from plugin.perception.fusion.referee import (
    FusionReferee,
    FusionRefereeDecision,
    FusionSourceSummary,
    summarize_ax_like_node,
)
from plugin.worldmodel.belief import Belief, belief_from_evidence
from plugin.worldmodel.entities.normalize import _ROLE_MAP, _ACTION_MAP, _clean_label

# Legacy prior table kept for unused rivalry helpers below; assembly ignores it.
SOURCE_PRIOR = {
    "pyobjc_ax": 1.0,
    "macapptree": 0.75,
    "screen2ax": 0.8,
    "vision": 0.8,
    "execution": 1.05,
    "fixture": 0.95,
}

# Stable assembly order: accessibility before OCR/vision so chrome + content
# concatenate predictably without implying preference.
_SOURCE_ORDER = {
    "pyobjc_ax": 0,
    "macapptree": 1,
    "screen2ax": 2,
    "vision": 3,
    "execution": 4,
    "fixture": 5,
}


@dataclass
class PropertyConflict:
    entity_key: str
    property: str
    values: Dict[str, Any]
    fused_confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FusedEntity:
    key: str
    role: str
    label: str
    bounds: Tuple[float, float, float, float]
    actions: List[str]
    beliefs: Dict[str, Belief]
    confidence: float
    sources: List[str] = field(default_factory=list)
    raw_refs: Dict[str, Any] = field(default_factory=dict)

    def belief_value(self, prop: str, default: Any = None) -> Any:
        b = self.beliefs.get(prop)
        return default if b is None else b.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "role": self.role,
            "label": self.label,
            "bounds": self.bounds,
            "actions": self.actions,
            "confidence": round(self.confidence, 4),
            "sources": self.sources,
            "beliefs": {k: v.to_dict() for k, v in self.beliefs.items()},
        }


@dataclass
class FusionReport:
    sources: List[str] = field(default_factory=list)
    agreement: Optional[float] = 1.0
    conflicts: List[PropertyConflict] = field(default_factory=list)
    hypothesis_counts: Dict[str, int] = field(default_factory=dict)
    latencies_ms: Dict[str, float] = field(default_factory=dict)
    node_counts: Dict[str, int] = field(default_factory=dict)
    primary_source: str = ""
    needs_reobserve: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sources": self.sources,
            "agreement": None if self.agreement is None else round(self.agreement, 4),
            "conflicts": [c.to_dict() for c in self.conflicts[:32]],
            "hypothesis_counts": self.hypothesis_counts,
            "latencies_ms": self.latencies_ms,
            "node_counts": self.node_counts,
            "primary_source": self.primary_source,
            "needs_reobserve": self.needs_reobserve,
            # Flattened so ingest/score gates see assemble vs rivalry without
            # digging into meta.
            "fusion_mode": self.meta.get("fusion_mode", ""),
            "meta": self.meta,
            # compat with old WorldViewScore readers
            "actionable_agreed": self.meta.get("actionable_agreed", 0),
            "actionable_total": self.meta.get("actionable_total", 0),
        }


@dataclass
class FusedFrame:
    """One assembled perception cycle — enumerated inputs, not a rival reading."""

    timestamp: float
    app_name: str
    window_name: str
    entities: List[FusedEntity]
    report: FusionReport
    events: List[ObservationEvent] = field(default_factory=list)
    screenshot_path: Optional[str] = None
    # Measurements of the capture itself (transform + OCR lines). Assembly
    # concatenates contents; these keys must survive so click geometry and the
    # perceptor's OCR enumeration stay available. See ``carry_forward``.
    source_meta: Dict[str, Any] = field(default_factory=dict)

    def carry_forward(self, bundles: Sequence["ObservationBundle"]) -> "FusedFrame":
        """Adopt the per-frame measurements from the sources that took them.

        Only the keys that describe the capture rather than its contents. The
        first source to supply one wins, which is unambiguous in practice: the
        transform comes from whoever grabbed the screenshot and the OCR read
        from whoever ran the reader.
        """
        for bundle in bundles or []:
            meta = getattr(getattr(bundle, "observation", None), "meta", None)
            if not isinstance(meta, dict):
                continue
            for key in ("capture_frame", "ocr"):
                value = meta.get(key)
                if value and key not in self.source_meta:
                    self.source_meta[key] = value
        return self

    def mean_confidence(self) -> float:
        if not self.entities:
            return 0.0
        return sum(e.confidence for e in self.entities) / len(self.entities)

    def to_observation(self) -> Observation:
        """Compat projection: assembled entities → AxNode list for ingest."""
        nodes: List[AxNode] = []
        for fe in self.entities:
            exists = fe.beliefs.get("exists")
            if exists is not None and exists.value is False and exists.confidence >= 0.7:
                continue
            label = str(fe.belief_value("label", fe.label) or fe.label)
            value = fe.belief_value("value", None)
            focused = bool(fe.belief_value("focused", False))
            enabled = bool(fe.belief_value("enabled", True))
            desc = fe.belief_value("description", "") or ""
            attrs: Dict[str, Any] = {
                "belief_confidence": fe.confidence,
                "sources": list(fe.sources),
                "entity_key": fe.key,
            }
            if focused:
                attrs["focused"] = True
                attrs["AXFocused"] = True
            if value is not None:
                attrs["value"] = value
            if desc:
                attrs["description"] = desc
            for prop, bel in fe.beliefs.items():
                attrs[f"belief_{prop}"] = bel.to_dict()
            nodes.append(
                AxNode(
                    role=fe.role,
                    name=label,
                    description=str(desc) if desc else "",
                    value=None if value is None else str(value),
                    enabled=enabled,
                    bbox=fe.bounds,
                    attributes=attrs,
                    raw_id=str((fe.raw_refs or {}).get("raw_id") or fe.key),
                )
            )
        # Assembly never marks rivalry failure; emptiness alone is degraded.
        coverage = 1.0 if nodes else 0.0
        return Observation(
            timestamp=self.timestamp,
            app_name=self.app_name,
            window_name=self.window_name,
            nodes=nodes,
            screenshot_path=self.screenshot_path,
            source="fused:" + "+".join(self.report.sources or ["none"]),
            coverage=coverage,
            degraded=not bool(nodes),
            meta={
                **dict(self.source_meta or {}),
                "fusion": self.report.to_dict(),
                "fused_frame": True,
            },
        )


def _assoc_key(h: EntityHypothesis) -> str:
    # Soften bbox for cross-source assoc: label+role dominate when labels present
    lab = _clean_label(h.label or "")[:40].lower()
    bucket = role_bucket(h.role)
    if lab:
        return f"{bucket}|{lab}"
    return h.key


def _source_weight(source: str) -> float:
    return float(SOURCE_PRIOR.get(source, 0.7))


def _source_sort_key(source_id: str) -> Tuple[int, str]:
    sid = (source_id or "").lower()
    return (_SOURCE_ORDER.get(sid, 50), sid)


def _node_dedupe_key(node: AxNode) -> Tuple[Any, ...]:
    bbox = node.bbox or (0.0, 0.0, 0.0, 0.0)
    try:
        rounded = tuple(round(float(v), 0) for v in tuple(bbox)[:4])
    except (TypeError, ValueError):
        rounded = (0.0, 0.0, 0.0, 0.0)
    return (
        str(node.role or "").lower(),
        str(node.name or node.description or "").strip().lower()[:80],
        rounded,
    )


def _entity_from_node(node: AxNode, *, source_id: str, index: int) -> FusedEntity:
    """One source node → one entity. No cross-source blending."""
    label = str(node.name or node.description or "").strip()
    attrs = dict(node.attributes or {})
    try:
        conf = float(attrs.get("ocr_confidence") or attrs.get("belief_confidence") or 0.85)
    except (TypeError, ValueError):
        conf = 0.85
    conf = max(0.05, min(0.99, conf))
    key = f"{source_id}|{index}|{label[:40] or node.role or 'node'}"
    beliefs: Dict[str, Belief] = {
        "exists": Belief(value=True, confidence=conf),
        "label": Belief(value=label, confidence=conf),
        "visible": Belief(value=True, confidence=conf),
    }
    if node.value is not None:
        beliefs["value"] = Belief(value=node.value, confidence=conf)
    if attrs.get("focused") or attrs.get("AXFocused"):
        beliefs["focused"] = Belief(value=True, confidence=conf)
    if node.description:
        beliefs["description"] = Belief(value=str(node.description), confidence=conf)
    actions = list(attrs.get("actions") or []) if isinstance(attrs.get("actions"), list) else []
    return FusedEntity(
        key=key,
        role=str(node.role or "AXUnknown"),
        label=label,
        bounds=tuple(node.bbox or (0.0, 0.0, 0.0, 0.0))[:4],  # type: ignore[arg-type]
        actions=actions,
        beliefs=beliefs,
        confidence=conf,
        sources=[source_id],
        raw_refs={"raw_id": node.raw_id or key, "source": source_id},
    )


def _entity_from_hypothesis(hyp: EntityHypothesis, *, index: int) -> FusedEntity:
    label = str(hyp.label or "").strip()
    conf = max(0.05, min(0.99, float(hyp.confidence or 0.8)))
    props = dict(hyp.properties or {})
    beliefs: Dict[str, Belief] = {
        "exists": Belief(value=True, confidence=conf),
        "label": Belief(value=label, confidence=conf),
        "visible": Belief(value=props.get("visible", True), confidence=conf),
    }
    for prop, val in props.items():
        if prop in beliefs:
            continue
        beliefs[prop] = Belief(value=val, confidence=conf)
    return FusedEntity(
        key=str(hyp.key or f"{hyp.source}|{index}|{label[:40]}"),
        role=str(hyp.role or "AXUnknown"),
        label=label,
        bounds=tuple(hyp.bounds or (0.0, 0.0, 0.0, 0.0))[:4],  # type: ignore[arg-type]
        actions=list(hyp.actions or []),
        beliefs=beliefs,
        confidence=conf,
        sources=[str(hyp.source or "unknown")],
        raw_refs=dict(hyp.raw_refs or {}),
    )


def _assemble_report(
    *,
    sources: Sequence[str],
    node_counts: Dict[str, int],
    latencies_ms: Dict[str, float],
    entity_count: int,
    ignored_sources: Optional[Sequence[str]] = None,
    healthy_source_count: Optional[int] = None,
) -> FusionReport:
    """Assembly has no rivalry verdict — agreement and reobserve stay inert."""
    return FusionReport(
        sources=list(sources),
        agreement=None,
        conflicts=[],
        hypothesis_counts={sid: node_counts.get(sid, 0) for sid in sources},
        latencies_ms=dict(latencies_ms),
        node_counts=dict(node_counts),
        primary_source="",
        needs_reobserve=False,
        meta={
            "fusion_mode": "assemble",
            "healthy_source_count": int(
                healthy_source_count if healthy_source_count is not None else len(sources)
            ),
            "ignored_sources": list(ignored_sources or []),
            # Compat leftovers from retired rivalry fusion — always 0 in assemble
            # mode. Do not treat these as "clickable affordance" counts.
            "actionable_agreed": 0,
            "actionable_total": 0,
            "actionable_semantics": "retired_assemble",
            "entity_count": entity_count,
            "conflict_count": 0,
        },
    )


class FusionEngine:
    """Assemble multi-source observations; do not adjudicate between them."""

    def __init__(self) -> None:
        self.ax_interp = AxTreeInterpreter()
        self.vision_interp = VisionInterpreter()
        self.referee = FusionReferee()

    @staticmethod
    def _bundle_is_healthy(bundle: ObservationBundle) -> bool:
        obs = bundle.observation
        node_count = len(obs.nodes or [])
        coverage = float(obs.coverage if obs.coverage is not None else bundle.coverage_self or 0.0)
        if bool(getattr(bundle, "degraded", False)) or bool(getattr(obs, "degraded", False)):
            return False
        if node_count == 0 and coverage <= 0.05:
            return False
        if coverage < 0.1 and node_count < 4:
            return False
        return True

    def fuse_bundles(self, bundles: List[ObservationBundle], *, app: str = "") -> FusedFrame:
        """Concatenate source nodes and carry capture meta — no rivalry."""
        events = [ObservationEvent.from_bundle(b) for b in bundles]
        healthy_bundles = [b for b in bundles if self._bundle_is_healthy(b)]
        # Prefer healthy sources; if every source is a stub, still try them all
        # so a lone degraded read is not discarded.
        active_bundles = healthy_bundles if healthy_bundles else list(bundles)
        active_bundles = sorted(active_bundles, key=lambda b: _source_sort_key(b.source_id))

        latencies: Dict[str, float] = {}
        node_counts: Dict[str, int] = {}
        entities: List[FusedEntity] = []
        seen: set = set()
        for b in active_bundles:
            latencies[b.source_id] = b.latency_ms
            nodes = list(b.observation.nodes or [])
            node_counts[b.source_id] = len(nodes)
            for index, node in enumerate(nodes):
                key = _node_dedupe_key(node)
                if key in seen:
                    continue
                seen.add(key)
                entities.append(_entity_from_node(node, source_id=b.source_id, index=index))

        # If active sources somehow yielded nothing but another bundle had nodes,
        # preserve the richest source rather than return an empty assembly.
        if not entities:
            richest = max(
                bundles,
                key=lambda b: len(b.observation.nodes or []),
                default=None,
            )
            if richest is not None and (richest.observation.nodes or []):
                for index, node in enumerate(richest.observation.nodes or []):
                    entities.append(
                        _entity_from_node(node, source_id=richest.source_id, index=index)
                    )
                if richest.source_id not in node_counts:
                    node_counts[richest.source_id] = len(richest.observation.nodes or [])
                if richest.source_id not in [b.source_id for b in active_bundles]:
                    active_bundles = list(active_bundles) + [richest]

        app_name = app or next(
            (b.observation.app_name for b in bundles if b.observation.app_name), ""
        )
        window = next(
            (b.observation.window_name for b in bundles if b.observation.window_name), ""
        )
        screenshot = next(
            (b.observation.screenshot_path for b in bundles if b.observation.screenshot_path),
            None,
        )
        sources = [b.source_id for b in active_bundles]
        report = _assemble_report(
            sources=sources,
            node_counts=node_counts,
            latencies_ms=latencies,
            entity_count=len(entities),
            ignored_sources=[b.source_id for b in bundles if b not in active_bundles],
            healthy_source_count=len(healthy_bundles),
        )
        frame = FusedFrame(
            timestamp=time.time(),
            app_name=app_name,
            window_name=window,
            entities=entities,
            report=report,
            events=events,
            screenshot_path=screenshot,
        )
        return frame.carry_forward(bundles)

    def fuse_hypotheses(
        self,
        hyps: List[EntityHypothesis],
        *,
        app: str = "",
        window: str = "",
        screenshot: Optional[str] = None,
        sources: Optional[List[str]] = None,
        events: Optional[List[ObservationEvent]] = None,
        latencies_ms: Optional[Dict[str, float]] = None,
        node_counts: Optional[Dict[str, int]] = None,
        hypothesis_counts: Optional[Dict[str, int]] = None,
        healthy_source_count: Optional[int] = None,
        ignored_sources: Optional[List[str]] = None,
    ) -> FusedFrame:
        """Pass through hypotheses one-for-one. No blending, no referee."""
        _ = hypothesis_counts
        entities = [_entity_from_hypothesis(h, index=i) for i, h in enumerate(hyps or [])]
        srcs = list(sources or sorted({str(h.source or "") for h in (hyps or []) if h.source}))
        counts = dict(node_counts or {})
        if not counts:
            for h in hyps or []:
                sid = str(h.source or "unknown")
                counts[sid] = counts.get(sid, 0) + 1
        report = _assemble_report(
            sources=srcs,
            node_counts=counts,
            latencies_ms=dict(latencies_ms or {}),
            entity_count=len(entities),
            ignored_sources=ignored_sources,
            healthy_source_count=healthy_source_count
            if healthy_source_count is not None
            else len(srcs),
        )
        return FusedFrame(
            timestamp=time.time(),
            app_name=app,
            window_name=window,
            entities=entities,
            report=report,
            events=list(events or []),
            screenshot_path=screenshot,
        )

    def _fuse_hypotheses_core(
        self,
        hyps: List[EntityHypothesis],
        *,
        app: str = "",
        window: str = "",
        screenshot: Optional[str] = None,
        sources: Optional[List[str]] = None,
        events: Optional[List[ObservationEvent]] = None,
        latencies_ms: Optional[Dict[str, float]] = None,
        node_counts: Optional[Dict[str, int]] = None,
        hypothesis_counts: Optional[Dict[str, int]] = None,
        healthy_source_count: Optional[int] = None,
        ignored_sources: Optional[List[str]] = None,
    ) -> FusedFrame:
        groups: Dict[str, List[EntityHypothesis]] = {}
        for h in hyps:
            groups.setdefault(_assoc_key(h), []).append(h)

        fused_entities: List[FusedEntity] = []
        conflicts: List[PropertyConflict] = []
        multi_source_keys = 0
        agreed_keys = 0

        for key, group in groups.items():
            srcs = sorted({h.source for h in group})
            if len(srcs) >= 2:
                multi_source_keys += 1
            beliefs: Dict[str, Belief] = {}
            # Seed exists from all sources that saw it
            for h in sorted(group, key=lambda x: -_source_weight(x.source) * x.confidence):
                w = _source_weight(h.source)
                props = dict(h.properties or {})
                props.setdefault("exists", True)
                props.setdefault("label", h.label)
                props.setdefault("visible", True)
                for prop, val in props.items():
                    conf = max(0.05, min(0.99, h.confidence * w))
                    ev = Evidence(
                        entity_key=key,
                        property=prop,
                        value=val,
                        confidence=conf,
                        source=h.source,
                        detail=f"hyp conf={h.confidence:.2f}",
                    )
                    if prop not in beliefs:
                        beliefs[prop] = belief_from_evidence(ev)
                    else:
                        before = beliefs[prop]
                        beliefs[prop] = before.blend(val, conf, source=h.source, prop=prop)
                        if before.value != val:
                            conflicts.append(
                                PropertyConflict(
                                    entity_key=key,
                                    property=prop,
                                    values={before.evidence[-1].source if before.evidence else "?": before.value, h.source: val},
                                    fused_confidence=beliefs[prop].confidence,
                                )
                            )

            # Agreement: same label across sources
            labels = {str(h.label).lower() for h in group if h.label}
            if len(srcs) >= 2 and len(labels) <= 1:
                agreed_keys += 1

            best = max(group, key=lambda h: _source_weight(h.source) * h.confidence)
            label = str(beliefs["label"].value) if "label" in beliefs else best.label
            exists_c = beliefs["exists"].confidence if "exists" in beliefs else best.confidence
            label_c = beliefs["label"].confidence if "label" in beliefs else best.confidence
            ent_conf = min(0.99, 0.5 * exists_c + 0.5 * label_c)
            if len(srcs) >= 2 and len(labels) <= 1:
                ent_conf = min(0.99, ent_conf + 0.08)
            elif len(srcs) == 1:
                ent_conf *= 0.92

            fused_entities.append(
                FusedEntity(
                    key=key,
                    role=best.role,
                    label=label,
                    bounds=best.bounds,
                    actions=list(best.actions),
                    beliefs=beliefs,
                    confidence=ent_conf,
                    sources=srcs,
                    raw_refs=dict(best.raw_refs),
                )
            )

        # Sort: higher confidence / actionable first
        fused_entities.sort(key=lambda e: (-e.confidence, e.label.lower()))

        agreement: Optional[float]
        ignored = list(ignored_sources or [])
        if healthy_source_count is not None and healthy_source_count <= 1 and ignored:
            # Other sources were submitted but degraded/ignored: we expected
            # corroboration and got none, so cross-source agreement is genuinely
            # unknown (not the same as a single source that stands on its own).
            agreement = None
        elif multi_source_keys:
            agreement = agreed_keys / multi_source_keys
        elif fused_entities:
            # A single source that stands alone has nothing to contradict it:
            # report self-agreement rather than "unknown", so downstream gates
            # (which compare agreement to a threshold) treat it as usable.
            agreement = 0.7
        else:
            agreement = 0.0

        if agreement is None:
            needs = not fused_entities
        else:
            needs = agreement < 0.45 or (bool(conflicts) and agreement < 0.6) or not fused_entities
        # Prefer richest semantic source as primary label for report
        primary = ""
        if sources:
            if "pyobjc_ax" in sources:
                primary = "pyobjc_ax"
            else:
                primary = max(sources, key=lambda s: (node_counts or {}).get(s, 0))

        report = FusionReport(
            sources=list(sources or []),
            agreement=agreement,
            conflicts=conflicts[:48],
            hypothesis_counts=dict(hypothesis_counts or {}),
            latencies_ms=dict(latencies_ms or {}),
            node_counts=dict(node_counts or {}),
            primary_source=primary,
            needs_reobserve=needs,
            meta={
                "fusion_mode": "single_source"
                if healthy_source_count is not None and healthy_source_count <= 1
                else ("healthy_source" if healthy_source_count and healthy_source_count < len(sources or []) else "multi_source"),
                "healthy_source_count": int(healthy_source_count if healthy_source_count is not None else len(sources or [])),
                "ignored_sources": list(ignored_sources or []),
                "actionable_agreed": agreed_keys,
                "actionable_total": max(1, multi_source_keys),
                "entity_count": len(fused_entities),
                "conflict_count": len(conflicts),
            },
        )
        return FusedFrame(
            timestamp=time.time(),
            app_name=app,
            window_name=window,
            entities=fused_entities,
            report=report,
            events=list(events or []),
            screenshot_path=screenshot,
        )

    def _refine_with_llm_referee(
        self,
        frame: FusedFrame,
        *,
        bundles: Optional[List[ObservationBundle]],
        app: str = "",
        window: str = "",
        screenshot: Optional[str] = None,
        events: Optional[List[ObservationEvent]] = None,
        latencies_ms: Optional[Dict[str, float]] = None,
        node_counts: Optional[Dict[str, int]] = None,
        hypothesis_counts: Optional[Dict[str, int]] = None,
        hyps: Optional[List[EntityHypothesis]] = None,
    ) -> FusedFrame:
        # Rival fusion is retired: assembly never asks a referee to prefer a
        # source or force reobserve. Helpers below remain until a cleanup PR.
        _ = (
            bundles,
            app,
            window,
            screenshot,
            events,
            latencies_ms,
            node_counts,
            hypothesis_counts,
            hyps,
        )
        return frame

    def _should_consult_llm_referee(
        self,
        frame: FusedFrame,
        *,
        bundles: Optional[List[ObservationBundle]],
        node_counts: Optional[Dict[str, int]],
    ) -> bool:
        healthy_source_count = frame.report.meta.get("healthy_source_count") if isinstance(frame.report.meta, dict) else None
        try:
            healthy_source_count_int = int(healthy_source_count) if healthy_source_count is not None else None
        except Exception:
            healthy_source_count_int = None
        if healthy_source_count_int is not None and healthy_source_count_int <= 1:
            return False
        if not bundles and not frame.entities:
            return False
        if frame.report.needs_reobserve:
            return True
        if not frame.entities:
            return True
        if frame.report.conflicts and frame.report.agreement is not None and frame.report.agreement < 0.6:
            return True
        if bundles:
            richest = max((len(b.observation.nodes or []) for b in bundles), default=0)
            if richest > 0 and len(frame.entities) == 0:
                return True
            if richest >= 20 and len(frame.entities) < max(4, richest // 5):
                return True
        if node_counts:
            richest = max(node_counts.values() or [0])
            if richest >= 20 and len(frame.entities) < max(4, richest // 5):
                return True
        return False

    def _build_referee_payload(
        self,
        frame: FusedFrame,
        *,
        bundles: Optional[List[ObservationBundle]],
        app: str,
        window: str,
        screenshot: Optional[str],
        latencies_ms: Optional[Dict[str, float]],
        node_counts: Optional[Dict[str, int]],
        hypothesis_counts: Optional[Dict[str, int]],
        hyps: Optional[List[EntityHypothesis]],
    ) -> Dict[str, Any]:
        sources: List[Dict[str, Any]] = []
        bundle_map = {b.source_id: b for b in bundles or []}
        source_ids = list(frame.report.sources or [])
        if not source_ids and bundles:
            source_ids = [b.source_id for b in bundles]
        for sid in source_ids:
            bundle = bundle_map.get(sid)
            obs = bundle.observation if bundle is not None else None
            sample_nodes = []
            top_labels: List[str] = []
            top_roles: List[str] = []
            node_total = 0
            coverage = 0.0
            degraded = False
            if obs is not None:
                node_total = len(obs.nodes or [])
                coverage = float(obs.coverage or bundle.coverage_self or 0.0)
                degraded = bool(obs.degraded or bundle.degraded)
                for node in (obs.nodes or [])[:8]:
                    sample_nodes.append(summarize_ax_like_node(node))
                    label = str(getattr(node, "name", "") or getattr(node, "description", "") or "").strip()
                    if label and label not in top_labels and len(top_labels) < 8:
                        top_labels.append(label)
                    role = str(getattr(node, "role", "") or "").strip()
                    if role and role not in top_roles and len(top_roles) < 8:
                        top_roles.append(role)
            sources.append(
                FusionSourceSummary(
                    source_id=sid,
                    node_count=node_total,
                    hypothesis_count=int((hypothesis_counts or {}).get(sid, 0)),
                    coverage=round(coverage, 4),
                    degraded=degraded,
                    latency_ms=float((latencies_ms or {}).get(sid, 0.0)),
                    top_labels=top_labels,
                    top_roles=top_roles,
                    sample_nodes=sample_nodes,
                ).to_dict()
            )

        return {
            "app": app,
            "window": window,
            "screenshot": screenshot,
            "deterministic": {
                "entity_count": len(frame.entities),
                "agreement": round(frame.report.agreement, 4),
                "needs_reobserve": bool(frame.report.needs_reobserve),
                "primary_source": frame.report.primary_source,
                "conflict_count": len(frame.report.conflicts),
                "conflicts": [c.to_dict() for c in frame.report.conflicts[:16]],
                "meta": dict(frame.report.meta or {}),
            },
            "sources": sources,
            "hyps_count": len(hyps or []),
            "node_counts": dict(node_counts or {}),
            "latencies_ms": dict(latencies_ms or {}),
        }

    def _annotate_referee(self, frame: FusedFrame, decision: FusionRefereeDecision, payload: Dict[str, Any]) -> None:
        frame.report.meta = dict(frame.report.meta or {})
        frame.report.meta["llm_referee"] = decision.to_dict()
        frame.report.meta["llm_referee_payload"] = {
            "app": payload.get("app", ""),
            "window": payload.get("window", ""),
            "source_count": len(payload.get("sources") or []),
            "entity_count": payload.get("deterministic", {}).get("entity_count", 0),
        }
        if decision.action == "prefer_source" and decision.preferred_source_id:
            frame.report.primary_source = decision.preferred_source_id

    def _frame_from_preferred_source(
        self,
        *,
        preferred_source_id: str,
        bundles: List[ObservationBundle],
        frame: FusedFrame,
        app: str,
        window: str,
        screenshot: Optional[str],
        events: Optional[List[ObservationEvent]],
        latencies_ms: Optional[Dict[str, float]],
        node_counts: Optional[Dict[str, int]],
        hypothesis_counts: Optional[Dict[str, int]],
    ) -> Optional[FusedFrame]:
        bundle = next((b for b in bundles if b.source_id == preferred_source_id), None)
        if bundle is None:
            return None
        interpreted = self._interpret_bundle(bundle)
        if not interpreted:
            return None
        preferred_frame = self._fuse_hypotheses_core(
            interpreted,
            app=app or bundle.observation.app_name or frame.app_name,
            window=window or bundle.observation.window_name or frame.window_name,
            screenshot=screenshot or bundle.observation.screenshot_path or frame.screenshot_path,
            sources=[bundle.source_id],
            events=events,
            latencies_ms=latencies_ms,
            node_counts=node_counts,
            hypothesis_counts=hypothesis_counts,
        )
        preferred_frame.report.meta = dict(preferred_frame.report.meta or {})
        preferred_frame.report.meta["llm_referee"] = {
            "action": "prefer_source",
            "preferred_source_id": preferred_source_id,
        }
        return preferred_frame

    def _fallback_source_preserving_frame(
        self,
        bundles: List[ObservationBundle],
        *,
        app: str = "",
        window: str = "",
        screenshot: Optional[str] = None,
        events: Optional[List[ObservationEvent]] = None,
        latencies_ms: Optional[Dict[str, float]] = None,
        node_counts: Optional[Dict[str, int]] = None,
        hypothesis_counts: Optional[Dict[str, int]] = None,
    ) -> Optional[FusedFrame]:
        if not bundles:
            return None
        richest = max(bundles, key=lambda b: len(b.observation.nodes or []), default=None)
        if richest is None or not (richest.observation.nodes or []):
            return None
        interpreted = self._interpret_bundle(richest)
        if not interpreted:
            interpreted = self._fallback_bundle_hypotheses(richest)
        if not interpreted:
            return None
        fallback_frame = self._fuse_hypotheses_core(
            interpreted,
            app=app or richest.observation.app_name or "",
            window=window or richest.observation.window_name or "",
            screenshot=screenshot or richest.observation.screenshot_path,
            sources=[richest.source_id],
            events=events,
            latencies_ms=latencies_ms,
            node_counts=node_counts,
            hypothesis_counts=hypothesis_counts,
        )
        fallback_frame.report.meta = dict(fallback_frame.report.meta or {})
        fallback_frame.report.meta["fallback"] = {
            "reason": "preserve_primary_source_after_empty_fusion",
            "source_id": richest.source_id,
            "node_count": len(richest.observation.nodes or []),
        }
        return fallback_frame

    def _interpret_bundle(self, bundle: ObservationBundle) -> List[EntityHypothesis]:
        sid = (bundle.source_id or "").lower()
        if sid in {"screen2ax", "vision"} or "vision" in sid:
            interpreted = self.vision_interp.interpret(bundle)
        else:
            interpreted = self.ax_interp.interpret(bundle)
        if interpreted:
            return interpreted
        return self._fallback_bundle_hypotheses(bundle)

    def _fallback_bundle_hypotheses(self, bundle: ObservationBundle) -> List[EntityHypothesis]:
        """Last-resort, source-preserving hypotheses from raw nodes.

        Interpreters can legitimately drop nodes that are label-less or
        otherwise ambiguous. When the source is still non-empty, we keep a
        conservative low-confidence hypothesis instead of collapsing the
        whole source away.
        """
        out: List[EntityHypothesis] = []
        obs = bundle.observation
        source = bundle.source_id or obs.source or "unknown"
        for node in obs.nodes or []:
            role = str(getattr(node, "role", "") or "")
            etype = _ROLE_MAP.get(role, "unknown")
            raw_name = str(getattr(node, "name", "") or "").strip()
            raw_desc = str(getattr(node, "description", "") or "").strip()
            raw_value = getattr(node, "value", None)
            label = _clean_label(raw_name or raw_desc or ("" if raw_value is None else str(raw_value)) or role or etype)
            if not label:
                label = etype or "unknown"
            bounds = tuple(getattr(node, "bbox", (0.0, 0.0, 0.0, 0.0)))  # type: ignore[arg-type]
            actions = list(_ACTION_MAP.get(etype, []))
            props: Dict[str, Any] = {
                "exists": True,
                "visible": True,
                "enabled": bool(getattr(node, "enabled", True)),
                "focused": bool((getattr(node, "attributes", {}) or {}).get("focused") or (getattr(node, "attributes", {}) or {}).get("AXFocused")),
                "label": label,
                "entity_type": etype,
                "fallback_source": source,
                "fallback_reason": "interpreter_returned_empty",
            }
            if raw_value is not None:
                props["value"] = raw_value
            if raw_desc:
                props["description"] = _clean_label(raw_desc)
            out.append(
                EntityHypothesis.make(
                    role=role or "AXUnknown",
                    label=label,
                    bounds=bounds,  # type: ignore[arg-type]
                    actions=actions,
                    properties=props,
                    confidence=0.18 if label else 0.12,
                    source=source,
                    raw_refs={"raw_id": getattr(node, "raw_id", ""), "role": role, "fallback": True},
                )
            )
        return out


_DEFAULT_ENGINE: Optional[FusionEngine] = None


def get_fusion_engine() -> FusionEngine:
    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is None:
        _DEFAULT_ENGINE = FusionEngine()
    return _DEFAULT_ENGINE
