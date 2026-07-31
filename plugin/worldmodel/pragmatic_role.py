"""App-agnostic UI pragmatic roles — label vs CTA vs nav vs status.

``semantic_role`` stays display text. This module answers what *kind* of UI
thing an entity is, so screen/candidates/capabilities never bind on strings alone.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Dict, Iterable, Optional, Sequence, Set, Tuple

from plugin.worldmodel.belief import Belief
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.entities.normalize import _clean_label

Bounds = Tuple[float, float, float, float]

BELIEF_KEY = "pragmatic_role"


class UiPragmaticRole(str, Enum):
    NAV_CHROME = "nav_chrome"
    STATUS = "status"
    CTA = "cta"
    CONTENT = "content"
    INPUT = "input"
    DECORATIVE = "decorative"
    UNKNOWN = "unknown"


# Soft morphology priors (app-agnostic). Region/geometry win on conflict.
_NAV_PLURALS: Set[str] = {
    "calls",
    "chats",
    "updates",
    "settings",
    "favourites",
    "favorites",
    "starred",
    "archived",
    "status",
    "communities",
}
_CTA_VERBS: Set[str] = {
    "send",
    "forward",
    "share",
    "call",
    "voice",
    "video",
    "end call",
    "decline",
    "cancel",
    "ok",
    "close",
    "later",
    "not now",
    "allow",
    "don't allow",
    "dont allow",
    "more",
    "menu",
    "info",
    "new chat",
    "search",
}
_DECORATIVE_IMAGE_MARKERS: Set[str] = {
    "avatar",
    "image",
    "photo",
    "picture",
    "profile",
    "thumbnail",
    "icon",
    "cover",
}
_STATUS_MARKERS = re.compile(
    r"\b(calling|ringing|encrypted|typing|online|last seen|unread|"
    r"call in progress|incoming call|ongoing call)\b",
    re.I,
)


def _area(b: Bounds) -> float:
    if len(b) < 4:
        return 0.0
    return max(0.0, float(b[2])) * max(0.0, float(b[3]))


def has_clickable_geometry(e: Entity) -> bool:
    return _area(tuple(e.bounds or (0, 0, 0, 0))) >= 16.0


def entity_display_text(e: Entity) -> str:
    """Primary display string for role inference (deduped; not identity)."""
    attrs = e.attributes or {}
    parts: list[str] = []
    seen: set[str] = set()
    for raw in (
        e.label,
        e.semantic_role,
        attrs.get("description"),
        attrs.get("AXDescription"),
    ):
        s = _clean_label(str(raw or "")).strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        parts.append(s)
    return " ".join(parts).strip()


def get_pragmatic_role(e: Entity) -> UiPragmaticRole:
    b = e.belief(BELIEF_KEY)
    if b is not None and b.value:
        try:
            return UiPragmaticRole(str(b.value))
        except ValueError:
            pass
    raw = (e.attributes or {}).get("pragmatic_role")
    if raw:
        try:
            return UiPragmaticRole(str(raw))
        except ValueError:
            pass
    return UiPragmaticRole.UNKNOWN


def get_pragmatic_confidence(e: Entity, default: float = 0.0) -> float:
    b = e.belief(BELIEF_KEY)
    if b is None:
        return default
    return float(b.confidence)


def set_pragmatic_role(
    e: Entity,
    role: UiPragmaticRole,
    *,
    confidence: float,
    source: str,
    detail: str = "",
) -> None:
    conf = max(0.05, min(0.99, float(confidence)))
    existing = e.belief(BELIEF_KEY)
    if existing is None:
        e.beliefs[BELIEF_KEY] = Belief(value=role.value, confidence=conf, evidence=[])
    else:
        e.beliefs[BELIEF_KEY] = existing.blend(
            role.value,
            conf,
            source=source,
            prop=BELIEF_KEY,
            detail=detail or role.value,
        )
    e.attributes["pragmatic_role"] = role.value
    e.attributes["pragmatic_role_confidence"] = round(
        float(e.beliefs[BELIEF_KEY].confidence), 4
    )


def _morphology_prior(lab: str, etype: str) -> Tuple[Optional[UiPragmaticRole], float]:
    low = lab.lower().strip()
    if not low:
        return UiPragmaticRole.UNKNOWN, 0.2
    if low in _NAV_PLURALS:
        return UiPragmaticRole.NAV_CHROME, 0.7
    if _STATUS_MARKERS.search(low) or "end-to-end" in low:
        return UiPragmaticRole.STATUS, 0.75
    if low in _CTA_VERBS or low.startswith("end call") or low.startswith("send "):
        return UiPragmaticRole.CTA, 0.65
    if etype == "textfield":
        return UiPragmaticRole.INPUT, 0.85
    return None, 0.0


def infer_pragmatic_role_stage2(e: Entity) -> None:
    """Stage 2 prior from AX type, actions, geometry, weak morphology."""
    lab = entity_display_text(e)
    etype = (e.entity_type or "").lower()
    actions = set(e.actions or [])
    geom = has_clickable_geometry(e)

    if etype in {"image", "photo"}:
        low = lab.lower()
        if not low or any(marker in low for marker in _DECORATIVE_IMAGE_MARKERS):
            set_pragmatic_role(
                e,
                UiPragmaticRole.DECORATIVE,
                confidence=0.88,
                source="stage2_image_decorative",
            )
            return
        morph, mconf = _morphology_prior(lab, etype)
        if morph == UiPragmaticRole.CTA and geom:
            set_pragmatic_role(e, morph, confidence=mconf * 0.65, source="stage2_image_cta")
            return
        set_pragmatic_role(
            e,
            UiPragmaticRole.UNKNOWN,
            confidence=0.35,
            source="stage2_image_unknown",
        )
        return

    if etype in {"window", "group", "scroll"} and not actions:
        set_pragmatic_role(
            e, UiPragmaticRole.DECORATIVE, confidence=0.8, source="stage2_ax", detail="container"
        )
        return

    if not geom and etype not in {"textfield"}:
        morph, mconf = _morphology_prior(lab, etype)
        if morph == UiPragmaticRole.STATUS:
            set_pragmatic_role(e, morph, confidence=mconf * 0.6, source="stage2_ghost_status")
        else:
            set_pragmatic_role(
                e,
                UiPragmaticRole.DECORATIVE if not lab else UiPragmaticRole.UNKNOWN,
                confidence=0.7,
                source="stage2_no_geometry",
            )
        return

    if etype == "textfield" or "type" in actions:
        set_pragmatic_role(e, UiPragmaticRole.INPUT, confidence=0.9, source="stage2_input")
        return

    morph, mconf = _morphology_prior(lab, etype)
    interactive = bool(actions) or etype in {"button", "link", "menu"}

    if morph == UiPragmaticRole.NAV_CHROME and interactive:
        set_pragmatic_role(e, morph, confidence=mconf, source="stage2_nav_morph")
        return
    if morph == UiPragmaticRole.STATUS:
        set_pragmatic_role(
            e,
            morph,
            confidence=mconf if not interactive else mconf * 0.7,
            source="stage2_status_morph",
        )
        return
    if morph == UiPragmaticRole.CTA and interactive:
        set_pragmatic_role(e, morph, confidence=mconf, source="stage2_cta_morph")
        return

    if interactive and geom:
        set_pragmatic_role(e, UiPragmaticRole.CTA, confidence=0.45, source="stage2_interactive")
        return

    if etype == "static" and lab:
        set_pragmatic_role(e, UiPragmaticRole.STATUS, confidence=0.4, source="stage2_static")
        return

    set_pragmatic_role(e, UiPragmaticRole.UNKNOWN, confidence=0.25, source="stage2_fallback")


def refine_pragmatic_roles_with_regions(
    entities: Sequence[Entity],
    *,
    entity_region_kind: Dict[int, str],
) -> None:
    """Stage 3–5: reweight roles using scene region membership."""
    for e in entities:
        if not e.visible:
            continue
        kind = (entity_region_kind.get(e.id) or "").lower()
        current = get_pragmatic_role(e)
        lab = entity_display_text(e).lower()

        if kind in {"navigation", "sidebar"} and lab in _NAV_PLURALS:
            set_pragmatic_role(
                e, UiPragmaticRole.NAV_CHROME, confidence=0.9, source="region_nav", detail=kind
            )
            continue
        if kind == "navigation":
            set_pragmatic_role(
                e, UiPragmaticRole.NAV_CHROME, confidence=0.75, source="region_nav", detail=kind
            )
            continue
        if kind == "status_bar":
            set_pragmatic_role(
                e, UiPragmaticRole.STATUS, confidence=0.85, source="region_status", detail=kind
            )
            continue
        if kind == "composer":
            if e.entity_type == "textfield":
                set_pragmatic_role(
                    e, UiPragmaticRole.INPUT, confidence=0.95, source="region_composer"
                )
            elif "voice message" in lab or "type a message" in lab:
                set_pragmatic_role(
                    e, UiPragmaticRole.CTA, confidence=0.7, source="region_composer_cta"
                )
            continue
        if kind in {"header", "floating_menu", "toolbar", "modal"}:
            if current in {UiPragmaticRole.UNKNOWN, UiPragmaticRole.CTA} and has_clickable_geometry(e):
                if lab in _NAV_PLURALS:
                    set_pragmatic_role(
                        e, UiPragmaticRole.NAV_CHROME, confidence=0.7, source="region_header_nav"
                    )
                else:
                    set_pragmatic_role(
                        e, UiPragmaticRole.CTA, confidence=0.8, source="region_header_cta"
                    )
            continue
        if kind in {"timeline", "conversation"}:
            if e.entity_type in {"button", "link", "static"} and "unread" in lab:
                set_pragmatic_role(
                    e, UiPragmaticRole.CONTENT, confidence=0.75, source="region_timeline_row"
                )
            elif current == UiPragmaticRole.UNKNOWN and lab:
                set_pragmatic_role(
                    e, UiPragmaticRole.CONTENT, confidence=0.5, source="region_timeline"
                )


def apply_app_vocabulary_hints(
    entities: Sequence[Entity],
    *,
    nav_labels: Optional[Iterable[str]] = None,
    cta_labels: Optional[Iterable[str]] = None,
    status_labels: Optional[Iterable[str]] = None,
) -> None:
    """Optional overlay boost — does not own role membership alone."""
    nav = {_clean_label(x).lower() for x in (nav_labels or []) if x}
    cta = {_clean_label(x).lower() for x in (cta_labels or []) if x}
    status = {_clean_label(x).lower() for x in (status_labels or []) if x}
    for e in entities:
        if not e.visible:
            continue
        lab = _clean_label(e.label or e.semantic_role or "").lower()
        if not lab:
            continue
        if lab in nav and has_clickable_geometry(e):
            set_pragmatic_role(e, UiPragmaticRole.NAV_CHROME, confidence=0.92, source="app_vocab_nav")
        elif lab in cta and has_clickable_geometry(e):
            set_pragmatic_role(e, UiPragmaticRole.CTA, confidence=0.92, source="app_vocab_cta")
        elif lab in status or any(lab.startswith(s) for s in status if len(s) > 3):
            set_pragmatic_role(e, UiPragmaticRole.STATUS, confidence=0.85, source="app_vocab_status")


def role_compatible_for_family(role: UiPragmaticRole, action_family: str) -> bool:
    """Hard gate: which pragmatic roles may bind to an action family."""
    fam = (action_family or "").lower()
    if fam in {"start_call", "end_call", "dismiss", "forward_message", "select_content"}:
        return role == UiPragmaticRole.CTA
    if fam in {"open_search", "type_query"}:
        return role in {UiPragmaticRole.INPUT, UiPragmaticRole.CTA, UiPragmaticRole.NAV_CHROME}
    if fam in {"open_contact", "select_forward_target"}:
        return role in {UiPragmaticRole.CONTENT, UiPragmaticRole.CTA, UiPragmaticRole.UNKNOWN}
    if fam == "explore_chrome":
        return role in {UiPragmaticRole.CTA, UiPragmaticRole.NAV_CHROME}
    if fam == "observe":
        return True
    return role != UiPragmaticRole.DECORATIVE


def is_active_call_evidence(e: Entity) -> bool:
    """True if entity is real call-state evidence (CTA hangup or status ringing)."""
    if not e.visible:
        return False
    role = get_pragmatic_role(e)
    lab = entity_display_text(e).lower()
    if role == UiPragmaticRole.NAV_CHROME:
        return False
    if lab in {"call", "voice", "video", "audio", "start call", "start voice call", "start video call"}:
        return False
    if role == UiPragmaticRole.CTA and (
        lab in {"end call", "decline"} or lab.startswith("end call")
    ):
        return has_clickable_geometry(e)
    if role == UiPragmaticRole.STATUS and _STATUS_MARKERS.search(lab):
        return "encrypted" not in lab and has_clickable_geometry(e)
    if role in {UiPragmaticRole.UNKNOWN, UiPragmaticRole.CTA} and has_clickable_geometry(e):
        if re.search(r"\b(calling|ringing|incoming call|ongoing call|call in progress)\b", lab):
            return True
        if lab in {"end call", "decline"}:
            return True
    return False


WA_NAV_LABELS = ("Calls", "Chats", "Updates", "Settings", "Starred", "Favourites", "Favorites")
WA_CTA_LABELS = (
    "End Call",
    "End call",
    "Decline",
    "Voice",
    "Voice Call",
    "Audio Call",
    "Call",
    "Forward",
    "Send",
    "Later",
    "Not Now",
    "Cancel",
    "OK",
    "Close",
)
WA_STATUS_LABELS = ("end-to-end encrypted", "Calling", "Ringing")
