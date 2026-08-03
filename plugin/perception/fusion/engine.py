"""Property-level evidence fusion — hypotheses → FusedFrame with beliefs."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

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

# Source reliability priors for property fusion
SOURCE_PRIOR = {
    "pyobjc_ax": 1.0,
    "macapptree": 0.75,
    "screen2ax": 0.8,
    "vision": 0.8,
    "execution": 1.05,
    "fixture": 0.95,
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
            "meta": self.meta,
            # compat with old WorldViewScore readers
            "actionable_agreed": self.meta.get("actionable_agreed", 0),
            "actionable_total": self.meta.get("actionable_total", 0),
        }


@dataclass
class FusedFrame:
    """One fused perception cycle — beliefs, not a raw tree."""

    timestamp: float
    app_name: str
    window_name: str
    entities: List[FusedEntity]
    report: FusionReport
    events: List[ObservationEvent] = field(default_factory=list)
    screenshot_path: Optional[str] = None

    def mean_confidence(self) -> float:
        if not self.entities:
            return 0.0
        return sum(e.confidence for e in self.entities) / len(self.entities)

    def to_observation(self) -> Observation:
        """Compat projection: beliefs → AxNode list for legacy ingest paths."""
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
        degraded = self.report.needs_reobserve or (
            self.report.agreement is not None and self.report.agreement < 0.4
        )
        return Observation(
            timestamp=self.timestamp,
            app_name=self.app_name,
            window_name=self.window_name,
            nodes=nodes,
            screenshot_path=self.screenshot_path,
            source="fused:" + "+".join(self.report.sources or ["none"]),
            coverage=min(1.0, max(0.0, self.mean_confidence())),
            degraded=degraded,
            meta={"fusion": self.report.to_dict(), "fused_frame": True},
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


class FusionEngine:
    """Fuse EntityHypothesis lists property-by-property."""

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
        events = [ObservationEvent.from_bundle(b) for b in bundles]
        hyps: List[EntityHypothesis] = []
        hyp_counts: Dict[str, int] = {}
        latencies: Dict[str, float] = {}
        node_counts: Dict[str, int] = {}
        healthy_bundles = [b for b in bundles if self._bundle_is_healthy(b)]
        active_bundles = healthy_bundles if healthy_bundles else list(bundles)

        for b in active_bundles:
            latencies[b.source_id] = b.latency_ms
            node_counts[b.source_id] = len(b.observation.nodes or [])
            sid = (b.source_id or "").lower()
            if sid in {"screen2ax", "vision"} or "vision" in sid:
                interpreted = self.vision_interp.interpret(b)
            else:
                interpreted = self.ax_interp.interpret(b)
            hyp_counts[b.source_id] = len(interpreted)
            hyps.extend(interpreted)

        frame = self._fuse_hypotheses_core(
            hyps,
            app=app or next((b.observation.app_name for b in bundles if b.observation.app_name), ""),
            window=next((b.observation.window_name for b in bundles if b.observation.window_name), ""),
            screenshot=next((b.observation.screenshot_path for b in bundles if b.observation.screenshot_path), None),
            sources=[b.source_id for b in active_bundles],
            events=events,
            latencies_ms=latencies,
            node_counts=node_counts,
            hypothesis_counts=hyp_counts,
            healthy_source_count=len(healthy_bundles),
            ignored_sources=[b.source_id for b in bundles if b not in active_bundles],
        )
        frame = self._refine_with_llm_referee(
            frame,
            bundles=bundles,
            app=app or next((b.observation.app_name for b in bundles if b.observation.app_name), ""),
            window=next((b.observation.window_name for b in bundles if b.observation.window_name), ""),
            screenshot=next((b.observation.screenshot_path for b in bundles if b.observation.screenshot_path), None),
            events=events,
            latencies_ms=latencies,
            node_counts=node_counts,
            hypothesis_counts=hyp_counts,
        )
        # If property fusion collapses to an empty frame, preserve the richest
        # live source instead of discarding the whole observation. This keeps
        # the agent adaptive under partial-fusion failures.
        if not frame.entities:
            fallback = self._fallback_source_preserving_frame(
                active_bundles,
                app=app or next((b.observation.app_name for b in bundles if b.observation.app_name), ""),
                window=next((b.observation.window_name for b in bundles if b.observation.window_name), ""),
                screenshot=next((b.observation.screenshot_path for b in bundles if b.observation.screenshot_path), None),
                events=events,
                latencies_ms=latencies,
                node_counts=node_counts,
                hypothesis_counts=hyp_counts,
            )
            if fallback is not None and fallback.entities:
                return fallback
        return frame

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
        frame = self._fuse_hypotheses_core(
            hyps,
            app=app,
            window=window,
            screenshot=screenshot,
            sources=sources,
            events=events,
            latencies_ms=latencies_ms,
            node_counts=node_counts,
            hypothesis_counts=hypothesis_counts,
            healthy_source_count=len(sources or []),
            ignored_sources=[],
        )
        return self._refine_with_llm_referee(
            frame,
            bundles=None,
            app=app,
            window=window,
            screenshot=screenshot,
            events=events,
            latencies_ms=latencies_ms,
            node_counts=node_counts,
            hypothesis_counts=hypothesis_counts,
            hyps=hyps,
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
        if not self._should_consult_llm_referee(frame, bundles=bundles, node_counts=node_counts):
            return frame

        payload = self._build_referee_payload(
            frame,
            bundles=bundles,
            app=app,
            window=window,
            screenshot=screenshot,
            latencies_ms=latencies_ms,
            node_counts=node_counts,
            hypothesis_counts=hypothesis_counts,
            hyps=hyps,
        )
        decision = self.referee.decide(payload)
        self._annotate_referee(frame, decision, payload)

        if decision.action == "prefer_source" and decision.preferred_source_id:
            preferred_frame = self._frame_from_preferred_source(
                preferred_source_id=decision.preferred_source_id,
                bundles=bundles or [],
                frame=frame,
                app=app,
                window=window,
                screenshot=screenshot,
                events=events,
                latencies_ms=latencies_ms,
                node_counts=node_counts,
                hypothesis_counts=hypothesis_counts,
            )
            if preferred_frame is not None:
                self._annotate_referee(preferred_frame, decision, payload)
                return preferred_frame

        if decision.should_reobserve:
            frame.report.needs_reobserve = True
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
