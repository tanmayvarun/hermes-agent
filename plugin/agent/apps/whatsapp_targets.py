"""WhatsApp-overfitted click/type target resolution.

Authoritative for live WA binding. Prefers exact labels; bans dangerous
substring matches (Voice→Voice message, Later→End Call); rejects empty-label
and zero-area entities. Capability ``target_entity_id`` is validated here.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Set, Tuple

from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.entities.normalize import _clean_label
from plugin.worldmodel.model import WorldModel

Bounds = Tuple[float, float, float, float]

# Short chrome tokens: never resolve via substring containment.
_NO_SUBSTRING: Set[str] = {
    "voice",
    "call",
    "later",
    "cancel",
    "ok",
    "close",
    "allow",
    "more",
    "menu",
    "info",
    "share",
    "forward",
    "send",
}

_VOICE_CALL_EXACT: Set[str] = {
    "voice",
    "voice call",
    "audio call",
    "call",
    "phone",
}
_VOICE_MESSAGE_BANNED: Set[str] = {
    "voice message",
    "send voice message",
    "record voice message",
}
_DISMISS_EXACT: Set[str] = {
    "not now",
    "later",
    "cancel",
    "ok",
    "close",
    "don't allow",
    "dont allow",
    "allow",
    "dismiss",
}
_END_CALL_EXACT: Set[str] = {"end call", "decline"}
_COMPOSER_MIC: Set[str] = {"voice message", "send voice message"}


def _desc(e: Entity) -> str:
    attrs = e.attributes or {}
    return _clean_label(
        str(attrs.get("description") or attrs.get("AXDescription") or "")
    )


def _lab(e: Entity) -> str:
    return _clean_label(e.label or e.semantic_role or "")


def _primary(e: Entity) -> str:
    return _lab(e) or _desc(e)


def _blob(e: Entity) -> str:
    return f"{_lab(e)} {_desc(e)}".strip().lower()


def _area(e: Entity) -> float:
    b = e.bounds or (0, 0, 0, 0)
    if len(b) < 4:
        return 0.0
    return max(0.0, float(b[2])) * max(0.0, float(b[3]))


def is_clickable_geometry(e: Entity) -> bool:
    return _area(e) >= 16.0


def has_usable_label(e: Entity) -> bool:
    return bool(_primary(e))


def entity_ok_for_click(e: Entity) -> bool:
    return bool(e.visible) and has_usable_label(e) and is_clickable_geometry(e)


def _extent(entities: Sequence[Entity]) -> Bounds:
    xs, ys, rights, bottoms = [], [], [], []
    for e in entities:
        if not e.visible or len(e.bounds or ()) < 4:
            continue
        x, y, w, h = float(e.bounds[0]), float(e.bounds[1]), float(e.bounds[2]), float(e.bounds[3])
        if w <= 0 or h <= 0:
            continue
        xs.append(x)
        ys.append(y)
        rights.append(x + w)
        bottoms.append(y + h)
    if not xs:
        return (0.0, 0.0, 1.0, 1.0)
    x0, y0 = min(xs), min(ys)
    return (x0, y0, max(rights) - x0, max(bottoms) - y0)


def _center_y(e: Entity) -> float:
    b = e.bounds
    return float(b[1]) + float(b[3]) / 2.0


def _center_x(e: Entity) -> float:
    b = e.bounds
    return float(b[0]) + float(b[2]) / 2.0


def in_header_band(e: Entity, entities: Sequence[Entity], *, scene_graph: Optional[dict] = None) -> bool:
    """Prefer scene header/toolbar/floating_menu region when available."""
    kind = _scene_region_kind(e, scene_graph)
    if kind in {"header", "toolbar", "floating_menu", "modal"}:
        return True
    if kind in {"composer", "sidebar", "navigation", "timeline"}:
        return False
    _, y0, _, H = _extent(entities)
    if H < 8:
        return True
    # WhatsApp chat headers are a thin top strip; keep this band conservative so
    # list rows below the header do not get promoted to conversation context.
    header_cut = y0 + min(0.10 * H, 120.0)
    return _center_y(e) <= header_cut


def in_composer_band(e: Entity, entities: Sequence[Entity], *, scene_graph: Optional[dict] = None) -> bool:
    kind = _scene_region_kind(e, scene_graph)
    if kind == "composer":
        return True
    if kind in {"header", "toolbar", "floating_menu", "sidebar", "navigation"}:
        return False
    _, y0, _, H = _extent(entities)
    if H < 8:
        return False
    return _center_y(e) >= y0 + 0.72 * H


def in_sidebar_band(e: Entity, entities: Sequence[Entity], *, scene_graph: Optional[dict] = None) -> bool:
    # Vision-materialised entities are the perceptor's reading of main-pane
    # content, not AX sidebar rows. The geometric left-rail heuristic is
    # meaningless for them (on a chrome-only AX tree the bounding box is built
    # from the vision points themselves, so "left 30%" catches everything), so
    # exempt them outright: a message the perceptor saw is never a sidebar row.
    attrs = getattr(e, "attributes", None)
    if isinstance(attrs, dict) and str(attrs.get("source") or "").strip().lower() == "vision":
        return False
    kind = _scene_region_kind(e, scene_graph)
    if kind in {"sidebar", "navigation"}:
        return True
    if kind in {"header", "composer", "timeline", "floating_menu"}:
        return False
    x0, _, W, _ = _extent(entities)
    if W < 8:
        return True
    # Sidebar rows are anchored to the left edge of the app window. Using a
    # conservative left-edge cutoff avoids treating the right-pane conversation
    # header as a sidebar row in split-pane apps.
    #
    # Prefer explicit scene-graph regions when present; the geometric fallback
    # should only catch genuine left-rail content.
    left_edge = float((e.bounds or (0, 0, 0, 0))[0])
    cutoff = x0 + min(0.30 * W, 460.0)
    return left_edge < cutoff


def _scene_region_kind(e: Entity, scene_graph: Optional[dict]) -> str:
    if not scene_graph:
        return ""
    regions = scene_graph.get("regions") or []
    for r in regions:
        if not isinstance(r, dict):
            continue
        ids = r.get("entity_ids") or []
        if e.id in ids:
            return str(r.get("kind") or "")
    return ""


def _exact_match(e: Entity, semantic: str) -> bool:
    key = _clean_label(semantic).lower()
    if not key:
        return False
    return _lab(e).lower() == key or _desc(e).lower() == key


def _token_match_contact(e: Entity, contact: str) -> bool:
    key = _clean_label(contact).lower()
    if len(key) < 2:
        return False
    blob = _blob(e)
    if not blob:
        return False
    if key == blob or blob.startswith(key + " ") or blob.startswith(key + ",") or key in blob.split():
        return True
    # Multi-token: all significant tokens present
    toks = [t for t in key.split() if len(t) > 2]
    return bool(toks) and all(t in blob for t in toks)


def validate_entity_for_semantic(
    e: Optional[Entity],
    semantic: str,
    *,
    action_family: str = "",
    action: str = "click",
) -> bool:
    """True if grounded entity is acceptable for this WhatsApp semantic."""
    if e is None or not entity_ok_for_click(e):
        return False
    from plugin.worldmodel.pragmatic_role import (
        UiPragmaticRole,
        get_pragmatic_role,
        infer_pragmatic_role_stage2,
        role_compatible_for_family,
    )

    if get_pragmatic_role(e) == UiPragmaticRole.UNKNOWN:
        infer_pragmatic_role_stage2(e)
    fam = (action_family or "").lower()
    if fam and not role_compatible_for_family(get_pragmatic_role(e), fam):
        return False

    if fam in {"open_contact", "select_forward_target"} and e.entity_type in {"image", "photo"}:
        return False

    key = _clean_label(semantic).lower()
    lab = _blob(e)

    if fam == "start_call" or key in _VOICE_CALL_EXACT:
        if get_pragmatic_role(e) == UiPragmaticRole.NAV_CHROME:
            return False
        if any(b in lab for b in _VOICE_MESSAGE_BANNED):
            return False
        if key in {"voice", "voice call", "audio call", "call"}:
            return _lab(e).lower() in _VOICE_CALL_EXACT or _desc(e).lower() in _VOICE_CALL_EXACT
        return _exact_match(e, semantic)

    if fam == "dismiss" or key in _DISMISS_EXACT:
        if any(x in lab for x in ("end call", "decline")):
            return False
        return _exact_match(e, semantic)

    if fam == "end_call" or key in _END_CALL_EXACT:
        return _lab(e).lower() in _END_CALL_EXACT or _desc(e).lower() in _END_CALL_EXACT

    if fam in {"open_contact", "select_forward_target"} or (
        action.lower() == "click" and key not in _NO_SUBSTRING | _VOICE_CALL_EXACT | _DISMISS_EXACT
    ):
        return _token_match_contact(e, semantic)

    if key in _NO_SUBSTRING:
        return _exact_match(e, semantic)

    return _exact_match(e, semantic) or (
        key not in _NO_SUBSTRING and key in lab and len(lab) < len(key) + 48
    )


def _find_exact(wm: WorldModel, names: Iterable[str], *, prefer_header: bool = False) -> Optional[Entity]:
    wanted = {_clean_label(n).lower() for n in names if n}
    ents = [e for e in wm.entities.values() if e.visible and entity_ok_for_click(e)]
    scene = getattr(wm, "last_scene_graph", None) or {}
    if prefer_header:
        header = [e for e in ents if in_header_band(e, ents, scene_graph=scene)]
        pool = header or ents
    else:
        pool = ents
    for e in pool:
        if _lab(e).lower() in wanted or _desc(e).lower() in wanted:
            if prefer_header and in_composer_band(e, ents, scene_graph=scene):
                continue
            return e
    for e in pool:
        if _lab(e).lower() in wanted or _desc(e).lower() in wanted:
            return e
    return None


def resolve_whatsapp_target(
    wm: WorldModel,
    semantic: str,
    *,
    action: str = "click",
    action_family: str = "",
    target_entity_id: Optional[int] = None,
) -> Optional[Entity]:
    """
    Resolve a click/type target for WhatsApp.

    If ``target_entity_id`` is provided but fails validation, re-resolve by semantic.
    """
    from plugin.agent.whatsapp_view import resolve_contact_entity

    sem = _clean_label(semantic or "")
    if not sem and target_entity_id is None:
        return None
    key = sem.lower()
    fam = (action_family or "").lower()
    ents = list(wm.entities.values())

    # Validate pre-bound entity
    if target_entity_id is not None:
        bound = wm.entities.get(int(target_entity_id))
        if (fam == "type_query" or action.lower() == "type") and (
            bound is None or bound.entity_type != "textfield"
        ):
            bound = None
        # Never trust DismissOverlay / empty-geometry binds for hangup
        if fam == "end_call" or key in _END_CALL_EXACT:
            if bound is None or not entity_ok_for_click(bound):
                bound = None
            elif "dismiss" in _blob(bound) and _lab(bound).lower() not in _END_CALL_EXACT:
                bound = None
            elif not validate_entity_for_semantic(bound, sem or "End Call", action_family="end_call", action=action):
                bound = None
            if bound is not None:
                return bound
            # fall through
        elif validate_entity_for_semantic(bound, sem or _primary(bound) if bound else "", action_family=fam, action=action):
            return bound
        # fall through to semantic resolve

    if action.lower() == "type" or fam == "type_query":
        # Prefer a real search textfield; never type into a sidebar button
        # or other non-input surface just because it says "Search".
        if target_entity_id is not None:
            bound = wm.entities.get(int(target_entity_id))
            if bound is not None and bound.visible and bound.entity_type == "textfield":
                return bound
        # Prefer search textfield
        for e in ents:
            if not e.visible or e.entity_type != "textfield":
                continue
            lab = _lab(e).lower()
            if "compose" in lab or "type a message" in lab:
                continue
            if "search" in lab or not lab:
                if entity_ok_for_click(e) or e.entity_type == "textfield":
                    return e
        for e in ents:
            if e.visible and e.entity_type == "textfield" and "compose" not in _lab(e).lower():
                return e
        return None

    # start_call / Voice
    if fam == "start_call" or key in _VOICE_CALL_EXACT:
        hit = _find_exact(wm, ["Voice", "Voice Call", "Audio Call"], prefer_header=True)
        if hit and not any(b in _blob(hit) for b in _VOICE_MESSAGE_BANNED):
            return hit
        if key == "call":
            hit = _find_exact(wm, ["Call", "Phone"], prefer_header=True)
            if hit and "end call" not in _blob(hit):
                return hit
        return None

    # dismiss
    if fam == "dismiss" or key in _DISMISS_EXACT:
        hit = _find_exact(wm, [sem] if sem else list(_DISMISS_EXACT), prefer_header=False)
        if hit and "end call" not in _blob(hit):
            return hit
        return None

    # end_call — exact End Call / Decline only; never Cancel / DismissOverlay
    if fam == "end_call" or key in _END_CALL_EXACT:
        if key in {"cancel", "ok", "close"}:
            return None
        hit = _find_exact(wm, ["End Call", "End call", "Decline"], prefer_header=False)
        if hit is not None and entity_ok_for_click(hit):
            return hit
        return None

    # Search chrome
    if key == "search":
        if action.lower() == "type" or fam == "type_query":
            for e in ents:
                if not e.visible or e.entity_type != "textfield":
                    continue
                lab = _lab(e).lower()
                if "compose" in lab or "type a message" in lab:
                    continue
                if "search" in lab or not lab:
                    return e
            for e in ents:
                if e.visible and e.entity_type == "textfield" and "compose" not in _lab(e).lower():
                    return e
            return None
        for pref in ("button", "textfield", "static"):
            for e in ents:
                if not e.visible or e.entity_type != pref:
                    continue
                if _lab(e).lower() == "search" and "result" not in _lab(e).lower():
                    if entity_ok_for_click(e) or e.entity_type == "textfield":
                        return e
        return None

    # Contacts / open_contact
    if fam in {"open_contact", "select_forward_target"} or (
        action.lower() == "click"
        and key
        and key not in _NO_SUBSTRING
        and key not in _VOICE_CALL_EXACT
        and key not in _DISMISS_EXACT
    ):
        contact = resolve_contact_entity(wm, sem)
        if contact is not None and validate_entity_for_semantic(
            contact, sem, action_family="open_contact", action="click"
        ):
            return contact
        # Sidebar rescan: labeled rows only
        scene = getattr(wm, "last_scene_graph", None) or {}
        sidebar = [
            e
            for e in ents
            if e.visible
            and entity_ok_for_click(e)
            and in_sidebar_band(e, ents, scene_graph=scene)
            and _token_match_contact(e, sem)
        ]
        if sidebar:
            # Prefer shorter labels (contact row vs message preview)
            sidebar.sort(key=lambda e: len(_primary(e)))
            return sidebar[0]
        # Any labeled match
        labeled = [
            e
            for e in ents
            if e.visible and entity_ok_for_click(e) and _token_match_contact(e, sem)
        ]
        if labeled:
            labeled.sort(key=lambda e: (0 if in_sidebar_band(e, ents, scene_graph=scene) else 1, len(_primary(e))))
            return labeled[0]
        return None

    if fam == "forward_message" or key in {"forward", "forward message", "forward messages"}:
        # Forwarding must resolve to the actual message context/menu chrome, not the
        # composer attachment/share surface.
        forward_exact = _find_exact(wm, ["Forward", "Forward message", "Forward messages"], prefer_header=False)
        if forward_exact is not None:
            return forward_exact
        return None

    # Generic exact
    hit = _find_exact(wm, [sem], prefer_header=False)
    if hit:
        return hit
    if key in _NO_SUBSTRING:
        return None
    # Cautious contains for longer labels (links, etc.)
    best = None
    for e in ents:
        if not e.visible or not entity_ok_for_click(e):
            continue
        blob = _blob(e)
        if key in blob and len(blob) < len(key) + 60:
            best = best or e
    return best


def exact_label_visible(wm: WorldModel, label: str) -> bool:
    key = _clean_label(label).lower()
    for e in wm.entities.values():
        if not e.visible:
            continue
        if _lab(e).lower() == key or _desc(e).lower() == key:
            if is_clickable_geometry(e) or e.entity_type == "textfield":
                return True
    return False


def end_call_visible(wm: WorldModel) -> bool:
    return exact_label_visible(wm, "End Call") or exact_label_visible(wm, "End call")


def end_call_clickable(wm: WorldModel) -> bool:
    """True only if End Call / Decline has usable label + clickable geometry."""
    for name in ("End Call", "End call", "Decline"):
        hit = _find_exact(wm, [name], prefer_header=False)
        if hit is not None and entity_ok_for_click(hit):
            return True
    return False


def composer_mic_visible(wm: WorldModel) -> bool:
    for e in wm.entities.values():
        if not e.visible:
            continue
        if _lab(e).lower() in _COMPOSER_MIC or _desc(e).lower() in _COMPOSER_MIC:
            return True
    return False


def voice_call_chrome_visible(wm: WorldModel) -> bool:
    """True if a real call affordance exists (not composer mic)."""
    from plugin.worldmodel.pragmatic_role import UiPragmaticRole, get_pragmatic_role, infer_pragmatic_role_stage2

    ents = [e for e in wm.entities.values() if e.visible]
    scene = getattr(wm, "last_scene_graph", None) or {}
    for e in ents:
        if not entity_ok_for_click(e):
            continue
        if get_pragmatic_role(e) == UiPragmaticRole.UNKNOWN:
            infer_pragmatic_role_stage2(e)
        if get_pragmatic_role(e) == UiPragmaticRole.NAV_CHROME:
            continue
        lab = _lab(e).lower()
        if lab in _VOICE_MESSAGE_BANNED:
            continue
        if lab in _VOICE_CALL_EXACT and not in_composer_band(e, ents, scene_graph=scene):
            if get_pragmatic_role(e) in {UiPragmaticRole.CTA, UiPragmaticRole.UNKNOWN}:
                return True
        if "open call dropdown" in _blob(e):
            return True
    return False
