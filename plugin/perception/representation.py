"""Typed perception representation.

This is the structured, temporally grounded perception product used by the
runtime. The goal is not to replace the LLM; it is to give the controller and
the human reviewer a stable, inspectable world model that can be rendered into
English without making English the source of truth.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from plugin.agent.goal import Goal
from plugin.agent.features import StateFeatures
from plugin.worldmodel.capability import CapabilityGraph, build_capability_graph
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.entities.normalize import _clean_label
from plugin.worldmodel.model import WorldModel
from plugin.worldmodel.scene import (
    ActiveCognitiveSubgraph,
    RegionKind,
    WorldGraph,
    attach_active_cognitive_subgraph,
    reconstruct_world_graph,
)
from plugin.worldmodel.scene.types import SurfaceState
from plugin.worldmodel.scene.reconstruct import region_kind_for_entity, region_kinds_for_entity

try:  # Best-effort import; the runtime already carries this helper.
    from plugin.worldmodel.scene.focus import _phase_from_view as _focus_phase_from_view
    from plugin.worldmodel.scene.focus import _surface_state_from_view as _focus_surface_state_from_view
except Exception:  # pragma: no cover - import fallback
    _focus_phase_from_view = None
    _focus_surface_state_from_view = None


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            pass
    return str(value)


def _truncate(text: Any, limit: int = 200) -> str:
    clean = " ".join(str(text or "").strip().split())
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 1)].rstrip() + "…"


def _mappingify(features: StateFeatures | Mapping[str, Any]) -> Dict[str, Any]:
    if isinstance(features, StateFeatures):
        return features.to_dict()
    return dict(features or {})


def _features_extras(features: StateFeatures | Mapping[str, Any]) -> Dict[str, Any]:
    raw = _mappingify(features).get("extras") or {}
    return dict(raw) if isinstance(raw, dict) else {}


def _goal_terms(goal: Optional[Goal]) -> List[str]:
    if goal is None:
        return []
    terms = [
        goal.kind,
        goal.contact,
        goal.target_contact,
        goal.link_query,
        goal.prompt,
        goal.description,
    ]
    out: List[str] = []
    seen = set()
    for term in terms:
        cleaned = _clean_label(term).lower()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


def _text_blob(entity: Entity) -> str:
    desc = entity.attributes.get("description") or entity.attributes.get("AXDescription") or ""
    value = entity.attributes.get("value") or entity.attributes.get("AXValue") or ""
    return _clean_label(" ".join([entity.label or "", entity.semantic_role or "", str(desc), str(value)])).lower()


def _surface_kind_for_region(kind: Any) -> str:
    name = str(getattr(kind, "value", kind) or "").strip().lower()
    if name in {"modal", "floating_menu"}:
        return "overlay"
    if name in {"sidebar", "navigation", "status_bar"}:
        return "sidebar"
    if name in {"header", "toolbar", "timeline", "conversation", "composer"}:
        return "main"
    if name:
        return name
    return "unknown"


def _surface_state_from_view(view: Dict[str, Any], phase: str) -> SurfaceState:
    if _focus_surface_state_from_view is not None:
        try:
            return _focus_surface_state_from_view(view, phase)
        except Exception:
            pass
    base = str(view.get("app") or view.get("active_app") or view.get("window_name") or "").strip().lower()
    if not base and str(view.get("screen") or view.get("screen_kind") or "").strip():
        base = "whatsapp_main_window"
    sidebar = ""
    main = ""
    overlay = ""
    screen = str(view.get("screen") or view.get("screen_kind") or view.get("wa_screen") or "").strip().lower()
    if bool(view.get("blocking_overlay")) or screen == "dialog":
        overlay = "dialog"
    elif str(view.get("active_surface") or "").strip().lower() == "call_picker" or phase == "calling":
        overlay = "call_picker"
    elif str(view.get("active_surface") or "").strip().lower() == "menu":
        overlay = "menu"
    if screen in {"search", "search_results"} or bool(view.get("search_query")) or bool(view.get("search_focused")):
        sidebar = "search_results" if bool(view.get("visible_contacts")) else "search"
        main = "conversation" if bool(view.get("open_conversation")) else "search_results"
    elif screen == "conversation" or bool(view.get("open_conversation")):
        sidebar = "search_results" if bool(view.get("visible_contacts")) else "list"
        main = "conversation"
    elif screen == "list" or bool(view.get("visible_contacts")):
        sidebar = "list"
        main = "list"
    else:
        sidebar = "unknown"
        main = "unknown"
    return SurfaceState(
        base_surface=base or "unknown",
        sidebar_surface=sidebar or "unknown",
        main_surface=main or "unknown",
        overlay_surface=overlay,
    )


def _surface_state_from_graph(graph: WorldGraph, view: Dict[str, Any], phase: str) -> SurfaceState:
    return graph.surface_state or _surface_state_from_view(view, phase)


@dataclass
class PerceivedSensor:
    id: str
    kind: str
    source: str = ""
    available: bool = True
    confidence: float = 0.0
    weight: float = 1.0
    path: str = ""
    summary: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "source": self.source,
            "available": bool(self.available),
            "confidence": float(self.confidence),
            "weight": float(self.weight),
            "path": self.path,
            "summary": self.summary,
            "evidence": dict(self.evidence),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PerceivedSensor":
        return cls(
            id=str(d.get("id") or ""),
            kind=str(d.get("kind") or "unknown"),
            source=str(d.get("source") or ""),
            available=bool(d.get("available", True)),
            confidence=float(d.get("confidence") or 0.0),
            weight=float(d.get("weight") or 1.0),
            path=str(d.get("path") or ""),
            summary=str(d.get("summary") or ""),
            evidence=dict(d.get("evidence") or {}),
        )


def _surface_membership_for_entity(graph: WorldGraph, entity: Entity) -> str:
    kinds = list(region_kinds_for_entity(graph, entity.id))
    if not kinds:
        return "base"
    if any(k in {RegionKind.MODAL, RegionKind.FLOATING_MENU} for k in kinds):
        return "overlay"
    if any(k in {RegionKind.SIDEBAR, RegionKind.NAVIGATION, RegionKind.STATUS_BAR} for k in kinds):
        return "sidebar"
    if any(k in {RegionKind.HEADER, RegionKind.TOOLBAR, RegionKind.CONVERSATION, RegionKind.TIMELINE, RegionKind.COMPOSER} for k in kinds):
        return "main"
    return "base"


def _surface_region_ids(graph: WorldGraph, surface_id: str) -> List[str]:
    wanted: set[RegionKind]
    if surface_id == "overlay":
        wanted = {RegionKind.MODAL, RegionKind.FLOATING_MENU}
    elif surface_id == "sidebar":
        wanted = {RegionKind.SIDEBAR, RegionKind.NAVIGATION, RegionKind.STATUS_BAR}
    elif surface_id == "main":
        wanted = {RegionKind.HEADER, RegionKind.TOOLBAR, RegionKind.TIMELINE, RegionKind.CONVERSATION, RegionKind.COMPOSER}
    else:
        wanted = {RegionKind.UNKNOWN}
    return [region.id for region in graph.regions if region.kind in wanted]


def _build_sensors(
    world: WorldModel,
    view: Dict[str, Any],
    features: StateFeatures | Mapping[str, Any],
    previous: Optional["PerceptionResult"],
) -> List[PerceivedSensor]:
    extras = _features_extras(features)
    screenshot_path = str(extras.get("screenshot_path") or view.get("screenshot_path") or "").strip()
    observation_nodes = int(extras.get("observation_node_count") or len(world.entities) or 0)
    content_nodes = int(extras.get("app_content_node_count") or 0)
    chrome_nodes = int(extras.get("chrome_only_node_count") or 0)
    sensors: List[PerceivedSensor] = [
        PerceivedSensor(
            id="screenshot",
            kind="screenshot",
            source="screen_capture",
            available=bool(screenshot_path),
            confidence=0.96 if screenshot_path else 0.0,
            weight=0.42,
            path=screenshot_path,
            summary="screen capture available" if screenshot_path else "no screenshot available",
            evidence={
                "screenshot_error": extras.get("screenshot_error"),
                "screen": view.get("screen"),
                "window_name": view.get("window_name"),
            },
        ),
        PerceivedSensor(
            id="ax",
            kind="accessibility_tree",
            source="ax",
            available=observation_nodes > 0,
            confidence=max(0.2, min(0.95, 0.45 + 0.05 * min(content_nodes, 8))),
            weight=0.34,
            summary=f"{observation_nodes} nodes, {content_nodes} content nodes, {chrome_nodes} chrome-only nodes",
            evidence={
                "node_count": observation_nodes,
                "content_node_count": content_nodes,
                "chrome_only_node_count": chrome_nodes,
                "task_sufficient": bool(extras.get("task_sufficient", True)),
            },
        ),
    ]
    ocr_blob = extras.get("ocr") or extras.get("ocr_run") or extras.get("ocr_result")
    if isinstance(ocr_blob, dict):
        ocr_engine = str(
            ocr_blob.get("engine_id")
            or ocr_blob.get("ocr_engine")
            or ocr_blob.get("engine")
            or "ocr"
        ).strip()
        spans = ocr_blob.get("spans") or ocr_blob.get("text_spans") or []
        sensors.append(
            PerceivedSensor(
                id="ocr",
                kind="ocr",
                source=ocr_engine or "ocr",
                available=bool(spans),
                confidence=max(0.1, min(0.96, float(ocr_blob.get("confidence") or 0.0) or 0.55)),
                weight=0.16,
                summary=f"{len(spans) if isinstance(spans, list) else 0} spans from {ocr_engine or 'ocr'}",
                evidence=_json_safe(ocr_blob),
            )
        )
    if previous is not None:
        sensors.append(
            PerceivedSensor(
                id="temporal",
                kind="temporal_memory",
                source="previous_perception",
                available=True,
                confidence=max(0.35, min(0.98, float(previous.confidence or 0.0))),
                weight=0.18,
                summary=f"previous frame {previous.frame_id or previous.previous_frame_id or 'available'}",
                evidence={
                    "previous_frame_id": previous.frame_id,
                    "previous_primary_surface_id": previous.primary_surface_id,
                    "previous_transition_status": previous.transition.status,
                },
            )
        )
    return sensors


def _object_id_for_entity(entity: Entity) -> str:
    return f"entity:{entity.id}"


def _object_id_for_timeline_row(row: Mapping[str, Any]) -> str:
    payload = {
        "text": _clean_label(row.get("text") or row.get("label") or row.get("description") or ""),
        "urls": [str(u).strip().lower() for u in (row.get("urls") or []) if str(u).strip()],
        "entity_ids": [int(x) for x in (row.get("entity_ids") or row.get("message_ids") or []) if str(x).strip().isdigit()],
        "x": row.get("x"),
        "y": row.get("y"),
    }
    raw = _json_safe(payload)
    digest = hashlib.sha1(repr(raw).encode("utf-8")).hexdigest()[:12]
    return f"timeline:{digest}"


def _object_signature(obj: "PerceivedObject") -> str:
    raw = {
        "kind": obj.kind,
        "label": obj.label,
        "surface_id": obj.surface_id,
        "text": obj.text,
        "url": obj.url,
        "visible": obj.visible,
        "actions": list(obj.actions),
        "entity_ids": list(obj.entity_ids),
    }
    return hashlib.sha1(repr(_json_safe(raw)).encode("utf-8")).hexdigest()[:12]


@dataclass
class PerceivedSurface:
    id: str
    kind: str
    state: str = ""
    confidence: float = 0.0
    entity_ids: List[int] = field(default_factory=list)
    region_ids: List[str] = field(default_factory=list)
    label: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "state": self.state,
            "confidence": float(self.confidence),
            "entity_ids": [int(x) for x in self.entity_ids],
            "region_ids": list(self.region_ids),
            "label": self.label,
            "evidence": dict(self.evidence),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PerceivedSurface":
        return cls(
            id=str(d.get("id") or ""),
            kind=str(d.get("kind") or "unknown"),
            state=str(d.get("state") or ""),
            confidence=float(d.get("confidence") or 0.0),
            entity_ids=[int(x) for x in (d.get("entity_ids") or [])],
            region_ids=[str(x) for x in (d.get("region_ids") or [])],
            label=str(d.get("label") or ""),
            evidence=dict(d.get("evidence") or {}),
        )


@dataclass
class PerceivedObject:
    id: str
    kind: str
    label: str = ""
    surface_id: str = ""
    entity_ids: List[int] = field(default_factory=list)
    confidence: float = 0.0
    visible: bool = True
    text: str = ""
    url: str = ""
    actions: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "surface_id": self.surface_id,
            "entity_ids": [int(x) for x in self.entity_ids],
            "confidence": float(self.confidence),
            "visible": bool(self.visible),
            "text": self.text,
            "url": self.url,
            "actions": list(self.actions),
            "attributes": dict(self.attributes),
            "evidence": dict(self.evidence),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PerceivedObject":
        return cls(
            id=str(d.get("id") or ""),
            kind=str(d.get("kind") or "unknown"),
            label=str(d.get("label") or ""),
            surface_id=str(d.get("surface_id") or ""),
            entity_ids=[int(x) for x in (d.get("entity_ids") or [])],
            confidence=float(d.get("confidence") or 0.0),
            visible=bool(d.get("visible", True)),
            text=str(d.get("text") or ""),
            url=str(d.get("url") or ""),
            actions=[str(x) for x in (d.get("actions") or [])],
            attributes=dict(d.get("attributes") or {}),
            evidence=dict(d.get("evidence") or {}),
        )


@dataclass
class PerceivedRelation:
    id: str
    kind: str
    source_id: str
    source_kind: str
    target_id: str
    target_kind: str
    confidence: float = 0.0
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "target_id": self.target_id,
            "target_kind": self.target_kind,
            "confidence": float(self.confidence),
            "evidence": dict(self.evidence),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PerceivedRelation":
        return cls(
            id=str(d.get("id") or ""),
            kind=str(d.get("kind") or ""),
            source_id=str(d.get("source_id") or ""),
            source_kind=str(d.get("source_kind") or ""),
            target_id=str(d.get("target_id") or ""),
            target_kind=str(d.get("target_kind") or ""),
            confidence=float(d.get("confidence") or 0.0),
            evidence=dict(d.get("evidence") or {}),
        )


@dataclass
class PerceivedCapability:
    id: str
    kind: str
    confidence: float = 0.0
    source_object_ids: List[str] = field(default_factory=list)
    source_surface_ids: List[str] = field(default_factory=list)
    reversible: bool = True
    risk: float = 0.0
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "confidence": float(self.confidence),
            "source_object_ids": list(self.source_object_ids),
            "source_surface_ids": list(self.source_surface_ids),
            "reversible": bool(self.reversible),
            "risk": float(self.risk),
            "evidence": dict(self.evidence),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PerceivedCapability":
        return cls(
            id=str(d.get("id") or ""),
            kind=str(d.get("kind") or ""),
            confidence=float(d.get("confidence") or 0.0),
            source_object_ids=[str(x) for x in (d.get("source_object_ids") or [])],
            source_surface_ids=[str(x) for x in (d.get("source_surface_ids") or [])],
            reversible=bool(d.get("reversible", True)),
            risk=float(d.get("risk") or 0.0),
            evidence=dict(d.get("evidence") or {}),
        )


@dataclass
class PerceptionBeliefPatch:
    persisted_object_ids: List[str] = field(default_factory=list)
    appeared_object_ids: List[str] = field(default_factory=list)
    disappeared_object_ids: List[str] = field(default_factory=list)
    changed_object_ids: List[str] = field(default_factory=list)
    moved_object_ids: List[str] = field(default_factory=list)
    selected_object_ids: List[str] = field(default_factory=list)
    occluded_object_ids: List[str] = field(default_factory=list)
    stale_object_ids: List[str] = field(default_factory=list)
    contradicted_object_ids: List[str] = field(default_factory=list)
    uncertain_object_ids: List[str] = field(default_factory=list)
    observation_quality: str = "unknown"
    confidence: float = 0.0
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "persisted_object_ids": list(self.persisted_object_ids),
            "appeared_object_ids": list(self.appeared_object_ids),
            "disappeared_object_ids": list(self.disappeared_object_ids),
            "changed_object_ids": list(self.changed_object_ids),
            "moved_object_ids": list(self.moved_object_ids),
            "selected_object_ids": list(self.selected_object_ids),
            "occluded_object_ids": list(self.occluded_object_ids),
            "stale_object_ids": list(self.stale_object_ids),
            "contradicted_object_ids": list(self.contradicted_object_ids),
            "uncertain_object_ids": list(self.uncertain_object_ids),
            "observation_quality": self.observation_quality,
            "confidence": float(self.confidence),
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PerceptionBeliefPatch":
        return cls(
            persisted_object_ids=[str(x) for x in (d.get("persisted_object_ids") or [])],
            appeared_object_ids=[str(x) for x in (d.get("appeared_object_ids") or [])],
            disappeared_object_ids=[str(x) for x in (d.get("disappeared_object_ids") or [])],
            changed_object_ids=[str(x) for x in (d.get("changed_object_ids") or [])],
            moved_object_ids=[str(x) for x in (d.get("moved_object_ids") or [])],
            selected_object_ids=[str(x) for x in (d.get("selected_object_ids") or [])],
            occluded_object_ids=[str(x) for x in (d.get("occluded_object_ids") or [])],
            stale_object_ids=[str(x) for x in (d.get("stale_object_ids") or [])],
            contradicted_object_ids=[str(x) for x in (d.get("contradicted_object_ids") or [])],
            uncertain_object_ids=[str(x) for x in (d.get("uncertain_object_ids") or [])],
            observation_quality=str(d.get("observation_quality") or "unknown"),
            confidence=float(d.get("confidence") or 0.0),
            evidence=[str(x) for x in (d.get("evidence") or [])],
        )


@dataclass
class PerceivedTransition:
    action_label: str = ""
    previous_frame_id: str = ""
    current_frame_id: str = ""
    status: str = "unknown"
    summary: str = ""
    confidence: float = 0.0
    belief_patch: PerceptionBeliefPatch = field(default_factory=PerceptionBeliefPatch)
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_label": self.action_label,
            "previous_frame_id": self.previous_frame_id,
            "current_frame_id": self.current_frame_id,
            "status": self.status,
            "summary": self.summary,
            "confidence": float(self.confidence),
            "belief_patch": self.belief_patch.to_dict(),
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PerceivedTransition":
        return cls(
            action_label=str(d.get("action_label") or ""),
            previous_frame_id=str(d.get("previous_frame_id") or ""),
            current_frame_id=str(d.get("current_frame_id") or ""),
            status=str(d.get("status") or "unknown"),
            summary=str(d.get("summary") or ""),
            confidence=float(d.get("confidence") or 0.0),
            belief_patch=PerceptionBeliefPatch.from_dict(d.get("belief_patch") or {}),
            evidence=[str(x) for x in (d.get("evidence") or [])],
        )


@dataclass
class PerceptionResult:
    world_id: str = ""
    app: str = ""
    goal_kind: str = ""
    phase: str = ""
    frame_id: str = ""
    previous_frame_id: str = ""
    primary_surface_id: str = ""
    active_object_ids: List[str] = field(default_factory=list)
    active_relation_ids: List[str] = field(default_factory=list)
    sensors: List[PerceivedSensor] = field(default_factory=list)
    surfaces: List[PerceivedSurface] = field(default_factory=list)
    objects: List[PerceivedObject] = field(default_factory=list)
    relations: List[PerceivedRelation] = field(default_factory=list)
    capabilities: List[PerceivedCapability] = field(default_factory=list)
    transition: PerceivedTransition = field(default_factory=PerceivedTransition)
    narrative: str = ""
    confidence: float = 0.0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "world_id": self.world_id,
            "app": self.app,
            "goal_kind": self.goal_kind,
            "phase": self.phase,
            "frame_id": self.frame_id,
            "previous_frame_id": self.previous_frame_id,
            "primary_surface_id": self.primary_surface_id,
            "active_object_ids": list(self.active_object_ids),
            "active_relation_ids": list(self.active_relation_ids),
            "sensors": [s.to_dict() for s in self.sensors],
            "surfaces": [s.to_dict() for s in self.surfaces],
            "objects": [o.to_dict() for o in self.objects],
            "relations": [r.to_dict() for r in self.relations],
            "capabilities": [c.to_dict() for c in self.capabilities],
            "transition": self.transition.to_dict(),
            "narrative": self.narrative,
            "confidence": float(self.confidence),
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PerceptionResult":
        return cls(
            world_id=str(d.get("world_id") or ""),
            app=str(d.get("app") or ""),
            goal_kind=str(d.get("goal_kind") or ""),
            phase=str(d.get("phase") or ""),
            frame_id=str(d.get("frame_id") or ""),
            previous_frame_id=str(d.get("previous_frame_id") or ""),
            primary_surface_id=str(d.get("primary_surface_id") or ""),
            active_object_ids=[str(x) for x in (d.get("active_object_ids") or [])],
            active_relation_ids=[str(x) for x in (d.get("active_relation_ids") or [])],
            sensors=[PerceivedSensor.from_dict(x) for x in (d.get("sensors") or [])],
            surfaces=[PerceivedSurface.from_dict(x) for x in (d.get("surfaces") or [])],
            objects=[PerceivedObject.from_dict(x) for x in (d.get("objects") or [])],
            relations=[PerceivedRelation.from_dict(x) for x in (d.get("relations") or [])],
            capabilities=[PerceivedCapability.from_dict(x) for x in (d.get("capabilities") or [])],
            transition=PerceivedTransition.from_dict(d.get("transition") or {}),
            narrative=str(d.get("narrative") or ""),
            confidence=float(d.get("confidence") or 0.0),
            notes=[str(x) for x in (d.get("notes") or [])],
        )


def _load_previous_result(
    world: WorldModel,
    previous_result: Optional[PerceptionResult | Mapping[str, Any]] = None,
) -> Optional[PerceptionResult]:
    if previous_result is not None:
        if isinstance(previous_result, PerceptionResult):
            return previous_result
        if isinstance(previous_result, Mapping):
            try:
                return PerceptionResult.from_dict(dict(previous_result))
            except Exception:
                return None
    cached = getattr(world, "last_perception_synthesis", None) or {}
    if isinstance(cached, dict):
        structured = cached.get("structured_perception")
        if isinstance(structured, dict):
            try:
                return PerceptionResult.from_dict(structured)
            except Exception:
                return None
    return None


def structured_perception_bridge(
    result: Optional[PerceptionResult | Mapping[str, Any]] = None,
    *,
    features: StateFeatures | Mapping[str, Any] | None = None,
    world: Optional[WorldModel] = None,
) -> Dict[str, Any]:
    """Return a compact compatibility view derived from structured perception.

    The structured perception result is the source of truth. This bridge keeps
    older decisioning code alive while making the new structured contract the
    first-class source.
    """
    extras: Dict[str, Any] = {}
    if features is not None:
        extras = _features_extras(features)
    legacy = dict(extras.get("perception_summary") or {}) if isinstance(extras.get("perception_summary"), dict) else {}
    structured = _load_previous_result(world or WorldModel(), result) if result is not None or world is not None else None
    if structured is None and result is not None:
        if isinstance(result, Mapping):
            try:
                structured = PerceptionResult.from_dict(dict(result))
            except Exception:
                structured = None
        elif isinstance(result, PerceptionResult):
            structured = result
    if structured is None:
        return legacy
    sensor_kinds = [sensor.kind for sensor in structured.sensors if sensor.kind]
    sensor_sources = [sensor.source for sensor in structured.sensors if sensor.source]
    bridge: Dict[str, Any] = {
        "phase": structured.phase,
        "primary_surface_id": structured.primary_surface_id,
        "frame_id": structured.frame_id,
        "previous_frame_id": structured.previous_frame_id,
        "confidence": round(float(structured.confidence or 0.0), 4),
        "narrative": structured.narrative,
        "active_object_ids": list(structured.active_object_ids),
        "active_relation_ids": list(structured.active_relation_ids),
        "transition_status": structured.transition.status,
        "transition_summary": structured.transition.summary,
        "transition_confidence": round(float(structured.transition.confidence or 0.0), 4),
        "sensor_kinds": sensor_kinds,
        "sensor_sources": sensor_sources,
        "sensor_count": len(structured.sensors),
        "surface_states": [surface.state for surface in structured.surfaces if surface.state],
        "surface_ids": [surface.id for surface in structured.surfaces if surface.id],
        "object_ids": [obj.id for obj in structured.objects if obj.id],
        "goal_kind": structured.goal_kind,
        "app": structured.app,
        "world_id": structured.world_id,
    }
    bridge.update(legacy)
    return bridge


def _view_dict(view: Any) -> Dict[str, Any]:
    if isinstance(view, dict):
        return dict(view)
    if hasattr(view, "to_dict") and callable(view.to_dict):
        try:
            return dict(view.to_dict())
        except Exception:
            pass
    if is_dataclass(view):
        return dict(asdict(view))
    return {}


def _scene_graph_and_capabilities(
    world: WorldModel,
    goal: Optional[Goal],
    view: Dict[str, Any],
) -> tuple[WorldGraph, CapabilityGraph]:
    raw_scene = getattr(world, "last_scene_graph", None) or {}
    if isinstance(raw_scene, dict) and raw_scene:
        graph = WorldGraph.from_dict(raw_scene)
    else:
        graph = reconstruct_world_graph(
            list(world.entities.values()),
            app=world.active_app or (goal.app if goal is not None else ""),
            source_patch_id="perception_result",
        )
    cap_graph_raw = getattr(world, "last_capability_graph", None) or {}
    if isinstance(cap_graph_raw, dict) and cap_graph_raw:
        cap_graph = CapabilityGraph.from_dict(cap_graph_raw)
    else:
        cap_graph = build_capability_graph(
            graph,
            list(world.entities.values()),
            goal=goal,
        )
    if goal is not None:
        try:
            graph = attach_active_cognitive_subgraph(
                graph,
                list(world.entities.values()),
                goal=goal,
                view=view,
                world_id=str(getattr(world.current_screen, "id", "") or getattr(world.current_screen, "signature", "") or ""),
                cap_graph=cap_graph,
            )
        except Exception:
            pass
    return graph, cap_graph


def _surface_labels(graph: WorldGraph, view: Dict[str, Any], phase: str) -> Dict[str, str]:
    state = _surface_state_from_graph(graph, view, phase)
    return {
        "base": state.base_surface or "unknown",
        "sidebar": state.sidebar_surface or "unknown",
        "main": state.main_surface or "unknown",
        "overlay": state.overlay_surface or "",
    }


def _build_surfaces(
    graph: WorldGraph,
    view: Dict[str, Any],
    phase: str,
) -> List[PerceivedSurface]:
    state = _surface_state_from_graph(graph, view, phase)
    labels = _surface_labels(graph, view, phase)
    surfaces: List[PerceivedSurface] = []
    for surface_id, kind, state_value in [
        ("base", "base", labels["base"]),
        ("sidebar", "sidebar", labels["sidebar"]),
        ("main", "main", labels["main"]),
        ("overlay", "overlay", labels["overlay"]),
    ]:
        region_ids = _surface_region_ids(graph, surface_id)
        entity_ids: List[int] = []
        for region in graph.regions:
            if region.id in region_ids:
                for eid in region.entity_ids:
                    if eid not in entity_ids:
                        entity_ids.append(int(eid))
        if not entity_ids and surface_id == "base":
            entity_ids = [int(e.id) for e in graph.context_graph.nodes if getattr(e, "kind", "") == "entity"]  # type: ignore[attr-defined]
        confidence = 0.92 if state_value else 0.55 if surface_id != "overlay" else 0.35
        if surface_id == "overlay" and state.overlay_surface:
            confidence = 0.88
        surfaces.append(
            PerceivedSurface(
                id=surface_id,
                kind=kind,
                state=state_value,
                confidence=confidence,
                entity_ids=entity_ids,
                region_ids=region_ids,
                label=state_value or kind,
                evidence={
                    "surface_state": state.to_dict(),
                    "region_ids": list(region_ids),
                },
            )
        )
    return surfaces


def _build_objects(
    world: WorldModel,
    graph: WorldGraph,
    view: Dict[str, Any],
    *,
    goal: Optional[Goal] = None,
) -> List[PerceivedObject]:
    objects: List[PerceivedObject] = []
    active_surface_by_entity: Dict[int, str] = {}
    for entity in world.entities.values():
        if not entity.visible:
            continue
        surface_id = _surface_membership_for_entity(graph, entity)
        active_surface_by_entity[entity.id] = surface_id
        desc = str(entity.attributes.get("description") or entity.attributes.get("AXDescription") or "")
        value = str(entity.attributes.get("value") or entity.attributes.get("AXValue") or "")
        label = _clean_label(entity.label or entity.semantic_role or desc or value)
        kind = str(entity.entity_type or "unknown")
        blob = _text_blob(entity)
        if "search" in blob and kind == "textfield":
            kind = "search_field"
        elif "message" in blob and kind == "static":
            kind = "message_row"
        elif "call" in blob and kind == "button":
            kind = "call_control"
        objects.append(
            PerceivedObject(
                id=_object_id_for_entity(entity),
                kind=kind or "unknown",
                label=label,
                surface_id=surface_id,
                entity_ids=[int(entity.id)],
                confidence=max(0.05, min(1.0, float(entity.confidence or 1.0))),
                visible=bool(entity.visible),
                text=_truncate(desc or value or label, 240),
                url=str(entity.attributes.get("url") or entity.attributes.get("href") or ""),
                actions=list(entity.actions or []),
                attributes={
                    "role": entity.role,
                    "semantic_role": entity.semantic_role,
                    "raw_ax_id": entity.raw_ax_id,
                    "region_kinds": [k.value for k in region_kinds_for_entity(graph, entity.id)],
                },
                evidence={
                    "entity_id": int(entity.id),
                    "bounds": list(entity.bounds),
                },
            )
        )

    timeline_rows = list(view.get("conversation_timeline") or [])
    if isinstance(timeline_rows, list):
        for row in timeline_rows:
            if not isinstance(row, dict):
                continue
            text = _clean_label(row.get("text") or row.get("label") or "")
            urls = [str(u).strip() for u in (row.get("urls") or []) if str(u).strip()]
            if not text and not urls:
                continue
            source_ids = [
                int(x)
                for x in (row.get("entity_ids") or row.get("message_ids") or [])
                if str(x).strip().isdigit()
            ]
            objects.append(
                PerceivedObject(
                    id=_object_id_for_timeline_row(row),
                    kind="message_cluster",
                    label=_truncate(text or (urls[0] if urls else "message"), 140),
                    surface_id="main",
                    entity_ids=source_ids,
                    confidence=0.9 if text else 0.75,
                    visible=True,
                    text=_truncate(text or " ".join(urls), 280),
                    url=urls[0] if urls else "",
                    actions=["select", "copy", "forward", "reply"],
                    attributes={
                        "row_count": row.get("row_count"),
                        "message_ids": list(row.get("message_ids") or []),
                        "urls": urls,
                    },
                    evidence={
                        "entity_id": row.get("entity_id"),
                        "entity_ids": source_ids,
                        "x": row.get("x"),
                        "y": row.get("y"),
                    },
                )
            )
    return objects


def _relation_id(kind: str, source_id: str, target_id: str) -> str:
    return f"{kind}:{source_id}->{target_id}"


def _build_relations(graph: WorldGraph, objects: Sequence[PerceivedObject]) -> List[PerceivedRelation]:
    relations: List[PerceivedRelation] = []
    object_ids = {obj.id for obj in objects}
    for edge in graph.context_graph.edges:
        src = f"{edge.source.kind}:{edge.source.id}"
        tgt = f"{edge.target.kind}:{edge.target.id}"
        rid = _relation_id(edge.kind.value, src, tgt)
        relations.append(
            PerceivedRelation(
                id=rid,
                kind=edge.kind.value,
                source_id=src,
                source_kind=edge.source.kind,
                target_id=tgt,
                target_kind=edge.target.kind,
                confidence=max(0.1, min(1.0, float(edge.confidence or 1.0))),
                evidence={},
            )
        )
    for obj in objects:
        if obj.surface_id:
            rid = _relation_id("on_surface", obj.id, obj.surface_id)
            relations.append(
                PerceivedRelation(
                    id=rid,
                    kind="on_surface",
                    source_id=obj.id,
                    source_kind="object",
                    target_id=obj.surface_id,
                    target_kind="surface",
                    confidence=0.95,
                    evidence={"surface_id": obj.surface_id},
                )
            )
    # De-duplicate while preserving order.
    dedup: List[PerceivedRelation] = []
    seen = set()
    for rel in relations:
        if rel.id in seen:
            continue
        seen.add(rel.id)
        if rel.source_id in object_ids or rel.source_kind != "object" or rel.kind == "on_surface":
            dedup.append(rel)
    return dedup


def _build_capabilities(
    graph: WorldGraph,
    world: WorldModel,
    goal: Optional[Goal],
    objects: Sequence[PerceivedObject],
    *,
    phase: str,
) -> List[PerceivedCapability]:
    cap_graph = build_capability_graph(
        graph,
        list(world.entities.values()),
        goal=goal,
    )
    caps: List[PerceivedCapability] = []
    selected_ids = list(cap_graph.goal_capability_ids or [])
    if not selected_ids and cap_graph.frontier:
        selected_ids = [node.capability_id for node in cap_graph.frontier[:5]]
    for cap_id in selected_ids[:12]:
        cap = cap_graph.nodes.get(cap_id)
        if cap is None:
            continue
        source_object_ids = [f"entity:{eid}" for eid in cap.provider_entities]
        if not source_object_ids and objects:
            source_object_ids = [objects[0].id]
        source_surface_ids = []
        for obj in objects:
            if obj.id in source_object_ids and obj.surface_id and obj.surface_id not in source_surface_ids:
                source_surface_ids.append(obj.surface_id)
        caps.append(
            PerceivedCapability(
                id=cap.capability_id,
                kind=cap.type,
                confidence=max(0.0, min(1.0, float(cap.confidence or 0.0))),
                source_object_ids=source_object_ids,
                source_surface_ids=source_surface_ids,
                reversible=bool(cap.reversibility),
                risk=max(0.0, min(1.0, float(cap.risk or 0.0))),
                evidence={
                    "predicted_transition": cap.predicted_transition,
                    "visible": cap.visible,
                    "parent_capability_id": cap.parent_capability_id,
                    "phase": phase,
                },
            )
        )
    return caps


def _select_primary_surface(surfaces: Sequence[PerceivedSurface], phase: str) -> str:
    priority = ["overlay", "main", "sidebar", "base"] if phase != "search" else ["sidebar", "main", "overlay", "base"]
    by_id = {s.id: s for s in surfaces}
    for sid in priority:
        surface = by_id.get(sid)
        if surface and (surface.entity_ids or surface.region_ids or surface.state):
            return sid
    return surfaces[0].id if surfaces else ""


def _goal_matching_object(objects: Sequence[PerceivedObject], goal: Optional[Goal]) -> Optional[PerceivedObject]:
    terms = _goal_terms(goal)
    if not terms:
        return None
    ranked = []
    for obj in objects:
        blob = _clean_label(" ".join([obj.label, obj.text, obj.kind, obj.url])).lower()
        score = 0.0
        for term in terms:
            if term and term in blob:
                score = max(score, 1.0 if term == blob else 0.78)
            compact_blob = re.sub(r"[^a-z0-9]+", "", blob)
            compact_term = re.sub(r"[^a-z0-9]+", "", term)
            if compact_term and compact_term in compact_blob:
                score = max(score, 0.72)
        if score > 0.0:
            ranked.append((score, obj))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], item[1].id))
    return ranked[0][1]


def _selected_object_ids(view: Dict[str, Any], objects: Sequence[PerceivedObject]) -> List[str]:
    selected: List[str] = []
    focused_id = view.get("focused_entity_id")
    if str(focused_id or "").strip().isdigit():
        focused_obj = f"entity:{int(focused_id)}"
        if focused_obj in {obj.id for obj in objects}:
            selected.append(focused_obj)
    for obj in objects:
        if "selected" in obj.kind or obj.attributes.get("selected") is True:
            if obj.id not in selected:
                selected.append(obj.id)
    return selected


def _state_signature(surfaces: Sequence[PerceivedSurface], objects: Sequence[PerceivedObject], relations: Sequence[PerceivedRelation]) -> str:
    payload = {
        "surfaces": [s.to_dict() for s in surfaces],
        "objects": [
            {
                "id": obj.id,
                "kind": obj.kind,
                "label": obj.label,
                "surface_id": obj.surface_id,
                "text": obj.text,
                "url": obj.url,
            }
            for obj in objects
        ],
        "relations": [rel.to_dict() for rel in relations],
    }
    return hashlib.sha1(repr(_json_safe(payload)).encode("utf-8")).hexdigest()[:16]


def _diff_objects(
    current: Sequence[PerceivedObject],
    previous: Optional[PerceptionResult],
    *,
    surface_state: SurfaceState,
) -> PerceptionBeliefPatch:
    if previous is None:
        current_ids = [obj.id for obj in current]
        return PerceptionBeliefPatch(
            appeared_object_ids=list(current_ids),
            observation_quality="initial",
            confidence=0.62,
            evidence=["no_previous_perception"],
        )

    prev_by_id = {obj.id: obj for obj in previous.objects}
    curr_by_id = {obj.id: obj for obj in current}
    prev_ids = set(prev_by_id)
    curr_ids = set(curr_by_id)
    persisted = sorted(prev_ids & curr_ids)
    appeared = sorted(curr_ids - prev_ids)
    disappeared = sorted(prev_ids - curr_ids)
    changed: List[str] = []
    moved: List[str] = []
    occluded: List[str] = []
    stale: List[str] = []
    contradicted: List[str] = []
    uncertain: List[str] = []

    for obj_id in persisted:
        prev = prev_by_id[obj_id]
        curr = curr_by_id[obj_id]
        if _object_signature(prev) != _object_signature(curr):
            changed.append(obj_id)
        if prev.surface_id and curr.surface_id and prev.surface_id != curr.surface_id:
            moved.append(obj_id)

    for obj_id in disappeared:
        prev = prev_by_id[obj_id]
        if prev.surface_id in {"main", "sidebar"} and surface_state.overlay_surface:
            occluded.append(obj_id)
        else:
            stale.append(obj_id)

    if not persisted and not appeared and not disappeared and not changed:
        uncertain.extend([obj.id for obj in current[:4]])

    quality = "stable"
    confidence = 0.78
    if appeared or disappeared or changed or moved:
        quality = "changed"
        confidence = 0.72
    if occluded:
        quality = "occluded"
        confidence = 0.69
    if not curr_ids:
        quality = "empty"
        confidence = 0.35

    return PerceptionBeliefPatch(
        persisted_object_ids=persisted,
        appeared_object_ids=appeared,
        disappeared_object_ids=disappeared,
        changed_object_ids=changed,
        moved_object_ids=moved,
        selected_object_ids=[],
        occluded_object_ids=occluded,
        stale_object_ids=stale,
        contradicted_object_ids=contradicted,
        uncertain_object_ids=uncertain,
        observation_quality=quality,
        confidence=max(0.05, min(0.98, confidence)),
        evidence=[
            f"persisted={len(persisted)}",
            f"appeared={len(appeared)}",
            f"disappeared={len(disappeared)}",
            f"changed={len(changed)}",
            f"moved={len(moved)}",
        ],
    )


def _transition_status(patch: PerceptionBeliefPatch) -> str:
    if patch.observation_quality == "initial":
        return "initial"
    if patch.observation_quality == "empty":
        return "uncertain"
    if patch.occluded_object_ids and not patch.appeared_object_ids:
        return "occluded"
    if patch.changed_object_ids or patch.appeared_object_ids or patch.disappeared_object_ids:
        return "changed"
    return "stable"


def _render_narrative(
    *,
    view: Dict[str, Any],
    goal: Optional[Goal],
    surfaces: Sequence[PerceivedSurface],
    objects: Sequence[PerceivedObject],
    capabilities: Sequence[PerceivedCapability],
    transition: PerceivedTransition,
    selected_object: Optional[PerceivedObject],
    phase: str,
) -> str:
    primary_surface = next((s for s in surfaces if s.id == _select_primary_surface(surfaces, phase)), surfaces[0] if surfaces else None)
    active_overlays = [s.state for s in surfaces if s.id == "overlay" and s.state]
    surface_line = primary_surface.state if primary_surface is not None else "unknown"
    task_obj = selected_object.label if selected_object is not None else (goal.contact or goal.link_query or goal.target_contact or goal.kind if goal is not None else "unknown")
    cap_labels = [f"{cap.kind}({cap.confidence:.2f})" for cap in sorted(capabilities, key=lambda c: (-c.confidence, c.id))[:6]]
    uncertain = transition.belief_patch.uncertain_object_ids or []
    persisted = transition.belief_patch.persisted_object_ids[:6]
    appeared = transition.belief_patch.appeared_object_ids[:6]
    disappeared = transition.belief_patch.disappeared_object_ids[:6]
    changed = transition.belief_patch.changed_object_ids[:6]
    occluded = transition.belief_patch.occluded_object_ids[:6]
    lines = [
        "CURRENT STATE",
        f"- Primary surface: {surface_line or 'unknown'}",
        f"- Active overlays: {', '.join(active_overlays) if active_overlays else 'none'}",
        f"- Current task object: {task_obj}",
        f"- Available capabilities: {', '.join(cap_labels) if cap_labels else 'none'}",
        "",
        "TEMPORAL CHANGE",
        f"- Persisted: {', '.join(persisted) if persisted else 'none'}",
        f"- Appeared: {', '.join(appeared) if appeared else 'none'}",
        f"- Disappeared: {', '.join(disappeared) if disappeared else 'none'}",
        f"- Changed: {', '.join(changed) if changed else 'none'}",
        f"- Occluded: {', '.join(occluded) if occluded else 'none'}",
        "",
        "GOAL RELEVANCE",
        f"- Evidence of progress: {selected_object.label if selected_object is not None else 'none'}",
        f"- Current blocker: {view.get('blocking_overlay') and 'blocking_overlay' or ('perception_uncertain' if transition.status in {'uncertain', 'initial'} else 'none')}",
        f"- Relevant affordances: {', '.join(cap_labels[:4]) if cap_labels else 'none'}",
        "",
        "UNCERTAINTY",
        f"- Uncertain claims: {', '.join(uncertain) if uncertain else 'none'}",
        f"- Conflicting evidence: {'; '.join(transition.evidence[:3]) if transition.evidence else 'none'}",
        f"- Useful next observation: {'inspect hidden controls / hover-reveal / refresh temporal evidence' if transition.status in {'uncertain', 'changed'} else 'continue branch execution'}",
    ]
    if goal is not None:
        lines.insert(1, f"- Goal: {goal.description}")
    return "\n".join(lines).strip()


def build_perception_result(
    world: WorldModel,
    view: Mapping[str, Any] | Dict[str, Any],
    features: StateFeatures | Mapping[str, Any],
    *,
    goal: Optional[Goal] = None,
    previous_result: Optional[PerceptionResult | Mapping[str, Any]] = None,
    action_label: str = "",
    previous_frame_id: str = "",
) -> PerceptionResult:
    """Construct the typed, temporally grounded perception representation."""
    view_dict = _view_dict(view)
    extras = _features_extras(features)
    previous = _load_previous_result(world, previous_result)
    graph, cap_graph = _scene_graph_and_capabilities(world, goal, view_dict)
    phase = ""
    if _focus_phase_from_view is not None:
        try:
            phase = _focus_phase_from_view(goal, view_dict)
        except Exception:
            phase = ""
    if not phase:
        screen = str(view_dict.get("screen") or view_dict.get("screen_kind") or "").strip().lower()
        if screen in {"search", "search_results"} or bool(view_dict.get("search_query")):
            phase = "search"
        elif screen == "conversation" or bool(view_dict.get("open_conversation")):
            phase = "conversation"
        elif screen == "calling" or str(view_dict.get("call_state") or "").strip().lower() in {"ringing", "calling", "connected"}:
            phase = "calling"
        elif bool(view_dict.get("blocking_overlay")):
            phase = "dialog"
        elif screen == "list" or bool(view_dict.get("visible_contacts")):
            phase = "list"
        else:
            phase = "unknown"
    surface_state = _surface_state_from_graph(graph, view_dict, phase)
    if graph.active_subgraph is None and goal is not None:
        try:
            graph = attach_active_cognitive_subgraph(
                graph,
                list(world.entities.values()),
                goal=goal,
                view=view_dict,
                world_id=str(getattr(world.current_screen, "id", "") or getattr(world.current_screen, "signature", "") or ""),
                cap_graph=cap_graph,
            )
        except Exception:
            pass
    sensors = _build_sensors(world, view_dict, features, previous)
    surfaces = _build_surfaces(graph, view_dict, phase)
    objects = _build_objects(world, graph, view_dict, goal=goal)
    relations = _build_relations(graph, objects)
    capabilities = _build_capabilities(graph, world, goal, objects, phase=phase)
    selected_object_ids = _selected_object_ids(view_dict, objects)
    selected_object = next((obj for obj in objects if obj.id in selected_object_ids), None)
    belief_patch = _diff_objects(objects, previous, surface_state=surface_state)
    belief_patch.selected_object_ids = list(selected_object_ids)
    transition = PerceivedTransition(
        action_label=action_label,
        previous_frame_id=(
            previous.frame_id
            if previous is not None and previous.frame_id
            else previous.previous_frame_id
            if previous is not None and previous.previous_frame_id
            else previous_frame_id
        ),
        current_frame_id=str(view_dict.get("world_signature") or getattr(world.current_screen, "signature", "") or ""),
        status=_transition_status(belief_patch),
        summary="",
        confidence=max(0.05, min(0.98, belief_patch.confidence)),
        belief_patch=belief_patch,
        evidence=list(belief_patch.evidence),
    )
    transition.summary = (
        f"{transition.status}: persisted={len(belief_patch.persisted_object_ids)} "
        f"appeared={len(belief_patch.appeared_object_ids)} changed={len(belief_patch.changed_object_ids)} "
        f"occluded={len(belief_patch.occluded_object_ids)}"
    )
    frame_id = str(view_dict.get("world_signature") or getattr(world.current_screen, "signature", "") or "")
    if not frame_id:
        frame_id = _state_signature(surfaces, objects, relations)
    primary_surface_id = _select_primary_surface(surfaces, phase)
    active_relation_ids = [rel.id for rel in relations[:60]]
    narrative = _render_narrative(
        view=view_dict,
        goal=goal,
        surfaces=surfaces,
        objects=objects,
        capabilities=capabilities,
        transition=transition,
        selected_object=selected_object,
        phase=phase,
    )
    confidence_bits = [
        float(sensor.confidence or 0.0) for sensor in sensors
    ] + [
        float(surface.confidence or 0.0) for surface in surfaces
    ] + [
        float(obj.confidence or 0.0) for obj in objects[:16]
    ]
    confidence = sum(confidence_bits) / max(1, len(confidence_bits))
    if previous is not None:
        confidence = max(confidence, float(previous.confidence or 0.0) * 0.5 + 0.25)
    if extras.get("perception_incomplete"):
        confidence = min(confidence, 0.72)
    result = PerceptionResult(
        world_id=str(getattr(world, "last_world_signature", "") or getattr(world.current_screen, "signature", "") or ""),
        app=str(world.active_app or view_dict.get("app") or ""),
        goal_kind=str(goal.kind if goal is not None else extras.get("goal_kind") or ""),
        phase=phase,
        frame_id=frame_id,
        previous_frame_id=transition.previous_frame_id,
        primary_surface_id=primary_surface_id,
        active_object_ids=list(selected_object_ids or ([selected_object.id] if selected_object is not None else [])),
        active_relation_ids=active_relation_ids,
        sensors=sensors,
        surfaces=surfaces,
        objects=objects,
        relations=relations,
        capabilities=capabilities,
        transition=transition,
        narrative=narrative,
        confidence=max(0.05, min(0.99, confidence)),
        notes=[
            f"scene_regions={len(graph.regions)}",
            f"capabilities={len(capabilities)}",
            f"phase={phase}",
        ],
    )
    return result


__all__ = [
    "PerceivedSurface",
    "PerceivedObject",
    "PerceivedRelation",
    "PerceivedCapability",
    "PerceptionBeliefPatch",
    "PerceivedTransition",
    "PerceptionResult",
    "build_perception_result",
]
