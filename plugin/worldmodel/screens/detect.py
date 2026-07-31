"""Layer 7 — screen detection via entity-graph signature hash."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence

from plugin.worldmodel.entities.entity import Entity


@dataclass
class Screen:
    id: int
    application: str
    signature: str
    label: str = ""  # human name if known (Conversation, Search, …)
    kind: str = "unknown"  # generic screen kind: list | search | detail | call | dialog | menu | input | unknown
    entity_ids: List[int] = field(default_factory=list)
    visit_count: int = 1

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "Screen":
        return cls(
            id=int(d["id"]),
            application=str(d.get("application") or ""),
            signature=str(d.get("signature") or ""),
            label=str(d.get("label") or ""),
            kind=str(d.get("kind") or "unknown"),
            entity_ids=list(d.get("entity_ids") or []),
            visit_count=int(d.get("visit_count") or 1),
        )


def layout_hash(entities: Sequence[Entity], *, grid: int = 8) -> str:
    """Coarse spatial hash of interactive entities."""
    cells = []
    for e in entities:
        if e.entity_type in {"group", "scroll", "window"}:
            continue
        x, y, w, h = e.bounds
        cx = int((x + w / 2) // max(grid, 1))
        cy = int((y + h / 2) // max(grid, 1))
        cells.append(f"{e.role}:{e.semantic_role}:{cx},{cy}")
    cells.sort()
    raw = "|".join(cells)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def screen_signature(entities: Sequence[Entity], application: str) -> str:
    top = [
        f"{e.entity_type}:{e.semantic_role}"
        for e in entities
        if e.visible and e.entity_type not in {"group", "scroll"}
    ]
    top.sort()
    top_key = ",".join(top[:40])
    return f"{application}::{hashlib.sha256((top_key + layout_hash(entities)).encode()).hexdigest()[:20]}"


def _scene_region_kinds(scene_graph: Optional[dict]) -> set[str]:
    kinds: set[str] = set()
    if not isinstance(scene_graph, dict):
        return kinds
    for region in scene_graph.get("regions") or []:
        if not isinstance(region, dict):
            continue
        kind = str(region.get("kind") or "").strip().lower()
        if kind:
            kinds.add(kind)
    return kinds


def _classify_screen_kind(
    entities: Sequence[Entity],
    *,
    scene_graph: Optional[dict] = None,
) -> str:
    """Generic screen-state classifier from structure, not app vocabulary."""
    from plugin.worldmodel.pragmatic_role import (
        UiPragmaticRole,
        entity_display_text,
        get_pragmatic_role,
        infer_pragmatic_role_stage2,
        is_active_call_evidence,
    )

    for e in entities:
        if e.visible and get_pragmatic_role(e) == UiPragmaticRole.UNKNOWN:
            infer_pragmatic_role_stage2(e)

    labels = [(e.semantic_role or e.label or "").lower().strip() for e in entities if e.visible]
    joined = " ".join(labels)
    scene_kinds = _scene_region_kinds(scene_graph)

    visible = [e for e in entities if e.visible]
    has_input = any(
        e.entity_type == "textfield"
        and get_pragmatic_role(e) in {UiPragmaticRole.INPUT, UiPragmaticRole.UNKNOWN}
        for e in visible
    )
    has_search_input = any(
        e.entity_type == "textfield"
        and (
            "search" in (e.semantic_role or e.label or "").lower()
            or "searchfield" in (e.role or "").lower()
        )
        and get_pragmatic_role(e) in {UiPragmaticRole.INPUT, UiPragmaticRole.UNKNOWN}
        for e in visible
    )
    has_composer = any(
        tok in joined
        for tok in ("type a message", "compose", "write a message", "message input")
    )
    has_blocking_overlay = any(
        tok in joined for tok in ("storage is too full", "free up space", "no space left on device")
    ) or bool(scene_kinds & {"modal", "floating_menu"})
    has_call_surface = any(
        (
            get_pragmatic_role(e) == UiPragmaticRole.CTA
            and (
                (e.semantic_role or e.label or "").lower().strip().startswith("end call")
                or (e.semantic_role or e.label or "").lower().strip() == "decline"
            )
        )
        for e in visible
    ) or bool(scene_kinds & {"call", "call_window"}) or any(
        re.search(r"\b(calling|ringing|incoming call|ongoing call|call in progress)\b", (e.semantic_role or e.label or "").lower())
        and get_pragmatic_role(e) in {UiPragmaticRole.STATUS, UiPragmaticRole.CTA}
        for e in visible
    )
    nav_density = sum(1 for e in visible if get_pragmatic_role(e) == UiPragmaticRole.NAV_CHROME)
    cta_density = sum(1 for e in visible if get_pragmatic_role(e) == UiPragmaticRole.CTA)
    content_density = sum(1 for e in visible if get_pragmatic_role(e) == UiPragmaticRole.CONTENT)
    list_like_context = bool(
        nav_density >= 2
        or "list" in joined
        or "sidebar" in scene_kinds
        or "navigation" in scene_kinds
    )
    detail_like_context = bool(
        has_composer
        or "timeline" in scene_kinds
        or "conversation" in scene_kinds
        or content_density >= 3
    )

    if has_blocking_overlay:
        return "dialog"
    if has_call_surface:
        return "call"
    if has_search_input:
        return "search"
    if has_composer or (has_input and detail_like_context):
        return "detail"
    if list_like_context and not detail_like_context:
        return "list"
    if has_input and not has_search_input:
        return "input"
    if cta_density >= 3 and not content_density:
        return "menu"
    if detail_like_context:
        return "detail"
    return "unknown"


def _legacy_screen_label(kind: str) -> str:
    mapping = {
        "detail": "conversation",
        "list": "conversation",
        "search": "search",
        "call": "call",
        "dialog": "dialog",
        "menu": "menu",
        "input": "search",
        "unknown": "",
    }
    return mapping.get(kind, kind or "")


def guess_screen_label(entities: Sequence[Entity], *, scene_graph: Optional[dict] = None) -> str:
    """Return the legacy screen label for compatibility."""
    return _legacy_screen_label(_classify_screen_kind(entities, scene_graph=scene_graph))


def guess_screen_kind(entities: Sequence[Entity], *, scene_graph: Optional[dict] = None) -> str:
    """Return the generic screen kind used by the core perception stack."""
    return _classify_screen_kind(entities, scene_graph=scene_graph)

class ScreenDetector:
    def __init__(self) -> None:
        self._screens: Dict[str, Screen] = {}  # signature -> Screen
        self._next_id = 1

    @property
    def screens(self) -> Dict[str, Screen]:
        return self._screens

    def detect(self, entities: Sequence[Entity], application: str, *, scene_graph: Optional[dict] = None) -> Screen:
        sig = screen_signature(entities, application)
        kind = guess_screen_kind(entities, scene_graph=scene_graph)
        fresh = guess_screen_label(entities, scene_graph=scene_graph)
        if sig in self._screens:
            s = self._screens[sig]
            s.visit_count += 1
            s.entity_ids = [e.id for e in entities if e.visible]
            # Re-label so a sticky wrong guess (e.g. call on chat list) can recover
            if fresh:
                s.label = fresh
            if kind:
                s.kind = kind
            return s
        label = fresh or f"Screen #{self._next_id}"
        screen = Screen(
            id=self._next_id,
            application=application,
            signature=sig,
            label=label,
            kind=kind or "unknown",
            entity_ids=[e.id for e in entities if e.visible],
        )
        self._next_id += 1
        self._screens[sig] = screen
        return screen

    def get_by_id(self, screen_id: int) -> Optional[Screen]:
        for s in self._screens.values():
            if s.id == screen_id:
                return s
        return None
