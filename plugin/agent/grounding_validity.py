"""Authoritative executable-grounding checks shared by Controller and Actor.

Controller must not decide geometry is executable with a looser definition than
Actor. Repair completion and actuation both go through ``_normalize_to_screen``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

_MENU_SURFACES = frozenset(
    {
        "context_menu",
        "action_menu",
        "menu",
        "overlay",
        "forward_sheet",
        "share_sheet",
    }
)


def _label_hit(text: str, target: str) -> bool:
    t = str(text or "").strip().lower()
    want = str(target or "").strip().lower()
    return bool(t) and bool(want) and (want in t or t in want)


def resolve_active_frame_graph(state: Any) -> Tuple[Any, Any, str]:
    """Return (graph, surface_dict_or_obj, capture_id) for the current perceive.

    Never invents a capture_id — only uses stamped FrameGraph / surface / doc
    provenance so a missing stamp does not spuriously fail freshness.
    """
    from plugin.perception.coordinate_frame import FrameGraph

    doc = getattr(state, "unified_world_document", None) or {}
    if not isinstance(doc, dict):
        doc = {}
    surface = doc.get("task_surface")
    if surface is None:
        surface = getattr(state, "task_surface", None)
    stamped = doc.get("frame_graph")
    graph = None
    if isinstance(stamped, FrameGraph):
        graph = stamped
    elif isinstance(stamped, dict):
        graph = FrameGraph.from_dict(stamped)
    if graph is None and isinstance(surface, dict) and surface.get("frame_graph"):
        graph = FrameGraph.from_dict(surface.get("frame_graph"))
    if graph is None and surface is not None:
        stamped_obj = getattr(surface, "frame_graph", None)
        if isinstance(stamped_obj, FrameGraph):
            graph = stamped_obj
        elif isinstance(stamped_obj, dict):
            graph = FrameGraph.from_dict(stamped_obj)
    capture_id = ""
    if graph is not None:
        capture_id = str(getattr(graph, "capture_id", "") or "").strip()
    if not capture_id and isinstance(doc, dict):
        capture_id = str(doc.get("capture_id") or "").strip()
    if not capture_id and isinstance(surface, dict):
        capture_id = str(surface.get("capture_id") or "").strip()
    if not capture_id and surface is not None:
        capture_id = str(getattr(surface, "capture_id", "") or "").strip()
    return graph, surface, capture_id


def _extract_point_bounds(
    item: Dict[str, Any],
) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float, float, float]]]:
    point = None
    raw_point = item.get("point") or item.get("target_point")
    if isinstance(raw_point, (list, tuple)) and len(raw_point) >= 2:
        try:
            point = (float(raw_point[0]), float(raw_point[1]))
        except (TypeError, ValueError):
            point = None
    if point is None:
        for act in item.get("actuators") or []:
            if not isinstance(act, dict):
                continue
            ap = act.get("point")
            if isinstance(ap, (list, tuple)) and len(ap) >= 2:
                try:
                    point = (float(ap[0]), float(ap[1]))
                    break
                except (TypeError, ValueError):
                    continue
    bounds = None
    raw_b = item.get("bounds")
    if isinstance(raw_b, (list, tuple)) and len(raw_b) >= 4:
        try:
            bounds = (
                float(raw_b[0]),
                float(raw_b[1]),
                float(raw_b[2]),
                float(raw_b[3]),
            )
        except (TypeError, ValueError):
            bounds = None
    return point, bounds


def _item_capture_id(item: Dict[str, Any]) -> str:
    g = item.get("grounding")
    if isinstance(g, dict):
        cid = str(g.get("capture_id") or "").strip()
        if cid:
            return cid
    return str(
        item.get("capture_id")
        or item.get("grounding_capture_id")
        or ""
    ).strip()


def _item_space(item: Dict[str, Any]) -> str:
    return str(item.get("coordinate_space") or "").strip().lower()


def _item_frame_id(item: Dict[str, Any]) -> str:
    return str(
        item.get("coordinate_frame_id")
        or item.get("frame_id")
        or ""
    ).strip()


def belongs_to_active_surface(
    item: Dict[str, Any],
    *,
    active_surface: str,
) -> bool:
    """True when the target is still applicable on the current surface/layer."""
    owner = str(item.get("owner_surface") or item.get("surface") or "").strip().lower()
    active = str(active_surface or "").strip().lower()
    if not owner:
        # Untagged owner: allow only when active surface is a menu overlay
        # (typical Forward CTA) or when we have no surface info at all.
        return (not active) or active in _MENU_SURFACES or active == "conversation"
    if not active:
        return True
    if owner == active:
        return True
    if owner in _MENU_SURFACES and active in _MENU_SURFACES:
        return True
    return False


def grounding_is_executable(
    item: Dict[str, Any],
    *,
    graph: Any = None,
    surface: Any = None,
    current_capture_id: str = "",
) -> bool:
    """Actor-grade check: tagged space + fresh capture + transform succeeds."""
    space = _item_space(item)
    if space not in {"screen", "image"}:
        return False
    point, bounds = _extract_point_bounds(item)
    if point is None and bounds is None:
        return False
    item_cid = _item_capture_id(item)
    graph_cid = str(current_capture_id or "").strip()
    if graph is not None and not graph_cid:
        graph_cid = str(getattr(graph, "capture_id", "") or "").strip()
    # Freshness: when the active graph is capture-stamped, grounding must match.
    if graph_cid and item_cid != graph_cid:
        return False
    if graph_cid and not item_cid:
        return False

    from plugin.agent.actor import _normalize_to_screen

    pt, bd, audit = _normalize_to_screen(
        point,
        bounds,
        coordinate_space=space,
        surface=surface,
        frame_id=_item_frame_id(item),
        graph=graph,
        grounding_capture_id=item_cid or graph_cid,
        allow_legacy_geometry=False,
    )
    if isinstance(audit, dict) and audit.get("grounding_uncertain"):
        return False
    return pt is not None or bd is not None


def grounding_repair_satisfied(state: Any) -> bool:
    """True only when the named reground target is fresh + executable now."""
    target = str(getattr(state, "grounding_reground_target", "") or "").strip().lower()
    if not target:
        return False
    doc = getattr(state, "unified_world_document", None) or {}
    if not isinstance(doc, dict):
        return False
    active_surface = str(doc.get("surface") or "").strip().lower()
    graph, surface, current_capture_id = resolve_active_frame_graph(state)

    for obj in doc.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        if not _label_hit(str(obj.get("text") or obj.get("label") or ""), target):
            continue
        if not belongs_to_active_surface(obj, active_surface=active_surface):
            continue
        if grounding_is_executable(
            obj,
            graph=graph,
            surface=surface,
            current_capture_id=current_capture_id,
        ):
            return True

    for aff in getattr(state, "last_grounded_affordance_set", None) or []:
        if not isinstance(aff, dict):
            continue
        if not _label_hit(
            str(aff.get("target_label") or aff.get("label") or ""), target
        ):
            continue
        if not (aff.get("actuators") or []):
            continue
        if not belongs_to_active_surface(aff, active_surface=active_surface):
            continue
        # Affordance-only path requires stamped capture + executable geometry.
        if grounding_is_executable(
            aff,
            graph=graph,
            surface=surface,
            current_capture_id=current_capture_id,
        ):
            return True
    return False


def current_capture_id_from_state(state: Any) -> str:
    """Capture id for stamping affordance sets at publish time."""
    _graph, _surface, cid = resolve_active_frame_graph(state)
    return cid
