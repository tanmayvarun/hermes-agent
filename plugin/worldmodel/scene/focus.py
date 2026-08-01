"""Goal-conditioned focus subgraph construction.

The scene graph is the full structural world. The active cognitive subgraph is
the slice we want the controller and LLM consultant to reason over right now.
"""

from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Sequence, Set

from plugin.agent.goal import Goal
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.entities.normalize import _clean_label
from plugin.worldmodel.scene.types import (
    ActiveCognitiveSubgraph,
    AttentionSubgraph,
    RegionKind,
    SurfaceState,
    WorldGraph,
)

if TYPE_CHECKING:
    from plugin.worldmodel.capability import CapabilityGraph


def _phase_from_view(goal: Optional[Goal], view: Dict[str, Any]) -> str:
    screen = str(view.get("screen") or view.get("screen_kind") or view.get("wa_screen") or "").strip().lower()
    active_surface = str(view.get("active_surface") or "").strip().lower()
    call_state = str(view.get("call_state") or "").strip().lower()
    if screen == "calling" or call_state in {"ringing", "calling", "connected"} or active_surface == "call_picker":
        return "calling"
    if bool(view.get("blocking_overlay")) or screen == "dialog" or bool(view.get("has_dialog")):
        return "dialog"
    if screen == "conversation" or bool(view.get("open_conversation")) or bool(view.get("composer_visible")):
        return "conversation"
    if screen in {"search", "search_results"} or bool(view.get("search_focused")) or bool(view.get("search_visible")) or bool(view.get("search_query")):
        return "search"
    if screen == "list" or bool(view.get("visible_contacts")):
        return "list"
    if goal is not None and goal.kind == "whatsapp_voice_call":
        return "calling" if bool(view.get("call_available")) else "conversation"
    return "unknown"


def _surface_state_from_view(view: Dict[str, Any], phase: str) -> SurfaceState:
    base = str(view.get("app") or view.get("active_app") or view.get("window_name") or "").strip().lower()
    if not base and str(view.get("screen") or view.get("screen_kind") or "").strip():
        base = "whatsapp_main_window"
    sidebar = ""
    main = ""
    overlay = ""
    screen = str(view.get("screen") or view.get("screen_kind") or view.get("wa_screen") or "").strip().lower()
    active_surface = str(view.get("active_surface") or "").strip().lower()
    if bool(view.get("blocking_overlay")) or screen == "dialog":
        overlay = "dialog"
    elif active_surface == "call_picker" or phase == "calling":
        overlay = "call_picker"
    elif active_surface == "menu":
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


def _region_ids_for_kinds(graph: WorldGraph, kinds: Iterable[RegionKind]) -> List[str]:
    wanted = {kind for kind in kinds}
    out: List[str] = []
    for region in graph.regions:
        if region.kind in wanted and region.id not in out:
            out.append(region.id)
    return out


def _all_visible_entities(entities: Sequence[Entity]) -> List[Entity]:
    return [e for e in entities if getattr(e, "visible", False)]


def _entity_blob(entity: Entity) -> str:
    desc = entity.attributes.get("description") or entity.attributes.get("AXDescription") or ""
    value = entity.attributes.get("value") or entity.attributes.get("AXValue") or ""
    return _clean_label(" ".join([entity.label or "", entity.semantic_role or "", str(desc), str(value)])).lower()


def _goal_terms(goal: Optional[Goal]) -> List[str]:
    if goal is None:
        return []
    terms = [
        goal.contact or "",
        goal.target_contact or "",
        goal.link_query or "",
        goal.prompt or "",
        goal.description or "",
    ]
    if goal.kind:
        terms.append(goal.kind)
    return [term for term in (_clean_label(t).lower() for t in terms) if term]


def _matches_goal(entity: Entity, goal_terms: Sequence[str]) -> bool:
    if not goal_terms:
        return False
    blob = _entity_blob(entity)
    if not blob:
        return False
    compact_blob = re.sub(r"[^a-z0-9]+", "", blob.lower())
    for term in goal_terms:
        cleaned = _clean_label(term).lower()
        if not cleaned:
            continue
        compact_term = re.sub(r"[^a-z0-9]+", "", cleaned)
        if cleaned in blob or (compact_term and compact_term in compact_blob):
            return True
        if compact_term and len(compact_term) >= 6:
            if SequenceMatcher(None, compact_term, compact_blob).ratio() >= 0.78:
                return True
    return False


def _select_focus_regions(graph: WorldGraph, phase: str, view: Dict[str, Any]) -> List[str]:
    region_priority: Dict[str, List[RegionKind]] = {
        "calling": [RegionKind.FLOATING_MENU, RegionKind.MODAL, RegionKind.HEADER, RegionKind.TOOLBAR],
        "conversation": [RegionKind.CONVERSATION, RegionKind.TIMELINE, RegionKind.HEADER, RegionKind.COMPOSER],
        "search": [RegionKind.SIDEBAR, RegionKind.NAVIGATION, RegionKind.HEADER, RegionKind.TOOLBAR],
        "dialog": [RegionKind.MODAL, RegionKind.FLOATING_MENU, RegionKind.HEADER, RegionKind.TOOLBAR],
        "list": [RegionKind.SIDEBAR, RegionKind.NAVIGATION, RegionKind.HEADER, RegionKind.TOOLBAR],
    }
    kinds = region_priority.get(phase, [RegionKind.CONVERSATION, RegionKind.TIMELINE, RegionKind.SIDEBAR, RegionKind.HEADER])
    region_ids = _region_ids_for_kinds(graph, kinds)
    if region_ids:
        return region_ids

    if graph.attention and graph.attention.region_ids:
        return [str(rid) for rid in graph.attention.region_ids if rid]

    # Fall back to the densest non-unknown regions so the controller still has
    # a concrete slice to reason over.
    ranked = sorted(
        (r for r in graph.regions if r.kind != RegionKind.UNKNOWN),
        key=lambda r: (-len(r.entity_ids), -float(r.confidence or 0.0), r.id),
    )
    return [r.id for r in ranked[:3] if r.id]


def _select_active_entities(
    graph: WorldGraph,
    entities: Sequence[Entity],
    focus_region_ids: Sequence[str],
    goal: Optional[Goal],
    view: Dict[str, Any],
) -> List[int]:
    by_id = {e.id: e for e in _all_visible_entities(entities)}
    region_by_id = {r.id: r for r in graph.regions}
    active: List[int] = []
    seen: Set[int] = set()

    for rid in focus_region_ids:
        region = region_by_id.get(rid)
        if region is None:
            continue
        for eid in region.entity_ids:
            if eid in seen or eid not in by_id:
                continue
            seen.add(eid)
            active.append(eid)

    # Goal-linked entities should always survive even if their region is fuzzy.
    goal_terms = _goal_terms(goal)
    for entity in by_id.values():
        if entity.id in seen:
            continue
        if _matches_goal(entity, goal_terms):
            seen.add(entity.id)
            active.append(entity.id)

    # Keep the focused entities compact: enough for reasoning, not the whole tree.
    active.sort()
    return active[:80]


def _relation_ids_for_focus(
    graph: WorldGraph,
    focus_region_ids: Sequence[str],
    active_entity_ids: Sequence[int],
) -> List[str]:
    focused_regions = set(focus_region_ids)
    focused_entities = {int(eid) for eid in active_entity_ids}
    rels: List[str] = []
    seen: Set[str] = set()

    def _mark(kind: str, source_kind: str, source_id: str, target_kind: str, target_id: str) -> None:
        key = f"{kind}:{source_kind}:{source_id}->{target_kind}:{target_id}"
        if key not in seen:
            seen.add(key)
            rels.append(key)

    for edge in graph.context_graph.edges:
        src_id = str(edge.source.id)
        tgt_id = str(edge.target.id)
        src_kind = str(edge.source.kind)
        tgt_kind = str(edge.target.kind)
        hit = False
        if src_kind == "region" and src_id in focused_regions:
            hit = True
        if tgt_kind == "region" and tgt_id in focused_regions:
            hit = True
        if src_kind == "entity" and src_id.isdigit() and int(src_id) in focused_entities:
            hit = True
        if tgt_kind == "entity" and tgt_id.isdigit() and int(tgt_id) in focused_entities:
            hit = True
        if hit:
            _mark(edge.kind.value, src_kind, src_id, tgt_kind, tgt_id)
    return rels[:120]


def _grounded_capability_ids(
    graph: WorldGraph,
    entities: Sequence[Entity],
    focus_region_ids: Sequence[str],
    active_entity_ids: Sequence[int],
    goal: Optional[Goal],
    cap_graph: Optional[CapabilityGraph],
) -> List[str]:
    if cap_graph is None:
        return []
    focus_regions = set(focus_region_ids)
    focus_entities = {int(eid) for eid in active_entity_ids}
    ranked: List[str] = []
    for cap in cap_graph.nodes.values():
        if cap.visible and cap.capability_id in cap_graph.goal_capability_ids:
            ranked.append(cap.capability_id)
            continue
        if any(eid in focus_entities for eid in cap.provider_entities):
            ranked.append(cap.capability_id)
            continue
        if focus_regions and any(rid in focus_regions for rid in cap.provider_regions):
            ranked.append(cap.capability_id)
    if not ranked:
        ranked.extend(list(cap_graph.goal_capability_ids))
    # Prefer visible goal-relevant capabilities first.
    dedup: List[str] = []
    seen: Set[str] = set()
    for cap_id in ranked:
        if cap_id and cap_id not in seen:
            seen.add(cap_id)
            dedup.append(cap_id)
    return dedup[:60]


def _excluded_regions(
    graph: WorldGraph,
    focus_region_ids: Sequence[str],
    phase: str,
) -> tuple[List[str], Dict[str, str]]:
    focus = set(focus_region_ids)
    excluded: List[str] = []
    reasons: Dict[str, str] = {}
    for region in graph.regions:
        if region.id in focus:
            continue
        if region.kind == RegionKind.UNKNOWN:
            excluded.append(region.id)
            reasons[region.id] = "unassigned_or_low_confidence"
            continue
        if phase in {"conversation", "search", "list"} and region.kind in {RegionKind.MODAL, RegionKind.FLOATING_MENU}:
            excluded.append(region.id)
            reasons[region.id] = "overlay_not_active"
            continue
        if phase == "search" and region.kind in {RegionKind.CONVERSATION, RegionKind.TIMELINE, RegionKind.COMPOSER}:
            excluded.append(region.id)
            reasons[region.id] = "conversation_not_active"
            continue
        if phase == "conversation" and region.kind in {RegionKind.SIDEBAR, RegionKind.NAVIGATION}:
            excluded.append(region.id)
            reasons[region.id] = "sidebar_not_active"
            continue
        if phase == "calling" and region.kind not in {RegionKind.FLOATING_MENU, RegionKind.MODAL, RegionKind.HEADER, RegionKind.TOOLBAR}:
            excluded.append(region.id)
            reasons[region.id] = "call_surface_not_active"
            continue
    return excluded, reasons


def build_active_cognitive_subgraph(
    graph: WorldGraph,
    entities: Sequence[Entity],
    *,
    goal: Optional[Goal] = None,
    view: Optional[Dict[str, Any]] = None,
    world_id: str = "",
    cap_graph: Optional[CapabilityGraph] = None,
) -> ActiveCognitiveSubgraph:
    view = dict(view or {})
    phase = _phase_from_view(goal, view)
    focus_region_ids = _select_focus_regions(graph, phase, view)
    active_entity_ids = _select_active_entities(graph, entities, focus_region_ids, goal, view)
    relevant_relation_ids = _relation_ids_for_focus(graph, focus_region_ids, active_entity_ids)
    grounded_capability_ids = _grounded_capability_ids(
        graph,
        entities,
        focus_region_ids,
        active_entity_ids,
        goal,
        cap_graph,
    )
    excluded_region_ids, exclusion_reasons = _excluded_regions(graph, focus_region_ids, phase)
    unresolved_questions: List[str] = []
    if phase == "conversation" and not active_entity_ids:
        unresolved_questions.append("which timeline region contains the source evidence?")
    if phase == "search" and not view.get("search_query"):
        unresolved_questions.append("which query or result keeps the source conversation in focus?")
    if goal is not None and goal.kind == "whatsapp_forward_message" and not any(
        _matches_goal(entity, _goal_terms(goal))
        for entity in _all_visible_entities(entities)
    ):
        unresolved_questions.append("is the source conversation explicitly grounded yet?")
    if not focus_region_ids:
        unresolved_questions.append("which surface is currently dominant?")

    confidence = 0.22
    confidence += 0.18 if phase != "unknown" else 0.0
    confidence += 0.2 if focus_region_ids else 0.0
    confidence += 0.18 if active_entity_ids else 0.0
    confidence += 0.12 if relevant_relation_ids else 0.0
    confidence += 0.12 if grounded_capability_ids else 0.0
    if graph.attention is not None and graph.attention.region_ids:
        confidence += 0.08
    confidence = max(0.05, min(0.98, confidence))

    return ActiveCognitiveSubgraph(
        world_id=world_id,
        phase=phase,
        focus_region_ids=list(focus_region_ids),
        active_entity_ids=list(active_entity_ids),
        relevant_relation_ids=list(relevant_relation_ids),
        grounded_capability_ids=list(grounded_capability_ids),
        excluded_region_ids=list(excluded_region_ids),
        exclusion_reasons=exclusion_reasons,
        confidence=round(confidence, 4),
        unresolved_questions=unresolved_questions,
    )


def attach_active_cognitive_subgraph(
    graph: WorldGraph,
    entities: Sequence[Entity],
    *,
    goal: Optional[Goal] = None,
    view: Optional[Dict[str, Any]] = None,
    world_id: str = "",
    cap_graph: Optional[CapabilityGraph] = None,
) -> WorldGraph:
    active = build_active_cognitive_subgraph(
        graph,
        entities,
        goal=goal,
        view=view,
        world_id=world_id,
        cap_graph=cap_graph,
    )
    graph.active_subgraph = active
    graph.surface_state = _surface_state_from_view(dict(view or {}), active.phase)
    graph.attention = AttentionSubgraph(
        region_ids=list(active.focus_region_ids),
        entity_ids=list(active.active_entity_ids[:80]),
        goal_kind=str(goal.kind if goal is not None else graph.app or ""),
        residual_mass=max(0.0, 1.0 - active.confidence),
    )
    return graph
