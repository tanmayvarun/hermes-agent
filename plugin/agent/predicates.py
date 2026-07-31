"""World predicates — success depends on observed WorldModel state, not executor OK."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from plugin.worldmodel.model import WorldModel


@dataclass
class PredicateResult:
    passed: bool
    reason: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class WorldPredicate(Protocol):
    name: str

    def evaluate(self, world: WorldModel) -> PredicateResult: ...


def _clean(s: str) -> str:
    from plugin.worldmodel.entities.normalize import _clean_label

    return _clean_label(s or "").lower()


def _joined(world: WorldModel) -> str:
    parts: List[str] = []
    for e in world.entities.values():
        if not e.visible:
            continue
        parts.append(e.label or "")
        parts.append(e.semantic_role or "")
        parts.append(str(e.attributes.get("value") or ""))
    return " ".join(parts).lower()


@dataclass
class ApplicationActive:
    app: str = "WhatsApp"
    name: str = "ApplicationActive"

    def evaluate(self, world: WorldModel) -> PredicateResult:
        active = _clean(world.active_app)
        needle = _clean(self.app)
        ok = needle in active or active in needle
        return PredicateResult(ok, f"active_app={world.active_app!r}", {"active_app": world.active_app})


@dataclass
class SearchInputVisible:
    name: str = "SearchInputVisible"

    def evaluate(self, world: WorldModel) -> PredicateResult:
        from plugin.agent.whatsapp_view import WhatsAppWorldView

        view = WhatsAppWorldView.from_world_model(world)
        return PredicateResult(
            view.search_visible,
            f"search_visible={view.search_visible}",
            {"search_query": view.search_query, "screen": view.screen},
        )


@dataclass
class SearchInputFocused:
    name: str = "SearchInputFocused"

    def evaluate(self, world: WorldModel) -> PredicateResult:
        from plugin.agent.whatsapp_view import WhatsAppWorldView

        view = WhatsAppWorldView.from_world_model(world)
        ok = view.search_focused or (view.search_visible and view.screen in {"SEARCH", "SEARCH_RESULTS"})
        return PredicateResult(
            ok,
            f"search_focused={view.search_focused} screen={view.screen}",
            view.to_dict(),
        )


def _search_hint(world: WorldModel) -> str:
    hints = getattr(world, "overlay_hints", None) or {}
    return str(hints.get("search_query") or "")


@dataclass
class SearchQueryEquals:
    query: str
    name: str = "SearchQueryEquals"

    def evaluate(self, world: WorldModel) -> PredicateResult:
        from plugin.agent.whatsapp_view import WhatsAppWorldView

        hint = _search_hint(world)
        view = WhatsAppWorldView.from_world_model(world, search_query_hint=hint)
        q = _clean(self.query)
        observed = _clean(view.search_query)
        ok = bool(q) and (observed == q or q in observed)
        return PredicateResult(
            ok,
            f"expected={self.query!r} observed={view.search_query!r}",
            {"expected": self.query, "observed": view.search_query, "hint": hint},
        )


@dataclass
class ContactResultVisible:
    contact: str
    name: str = "ContactResultVisible"

    def evaluate(self, world: WorldModel) -> PredicateResult:
        from plugin.agent.whatsapp_view import WhatsAppWorldView, resolve_contact_entity

        hint = _search_hint(world)
        view = WhatsAppWorldView.from_world_model(world, search_query_hint=hint)
        needle = _clean(self.contact)
        hits = [c for c in view.visible_contacts if needle == _clean(c) or needle in _clean(c)]
        if not hits and resolve_contact_entity(world, self.contact) is not None:
            hits = [self.contact]
        return PredicateResult(
            bool(hits),
            f"contacts={view.visible_contacts[:8]}",
            {"hits": hits, "visible_contacts": view.visible_contacts[:20]},
        )


@dataclass
class ConversationOpen:
    contact: str
    name: str = "ConversationOpen"

    def evaluate(self, world: WorldModel) -> PredicateResult:
        from plugin.agent.whatsapp_view import WhatsAppWorldView, contact_matches

        hint = _search_hint(world)
        view = WhatsAppWorldView.from_world_model(world, search_query_hint=hint)
        needle = _clean(self.contact)
        open_c = view.open_conversation or ""
        ok = contact_matches(open_c, self.contact, min_score=0.75) and (
            view.screen == "CONVERSATION" or view.composer_visible
        )
        return PredicateResult(
            ok,
            f"screen={view.screen} open={view.open_conversation!r}",
            view.to_dict(),
        )


@dataclass
class VoiceCallActionAvailable:
    name: str = "VoiceCallActionAvailable"

    def evaluate(self, world: WorldModel) -> PredicateResult:
        from plugin.agent.whatsapp_view import WhatsAppWorldView

        view = WhatsAppWorldView.from_world_model(world)
        return PredicateResult(
            view.voice_call_available,
            f"voice_call_available={view.voice_call_available}",
            view.to_dict(),
        )


@dataclass
class CallStateIs:
    state: str  # ringing | idle | …
    name: str = "CallStateIs"

    def evaluate(self, world: WorldModel) -> PredicateResult:
        from plugin.agent.whatsapp_view import WhatsAppWorldView

        view = WhatsAppWorldView.from_world_model(world)
        expected = _clean(self.state)
        observed = _clean(view.call_state or "idle")
        if expected in {"idle", "not_ringing", ""}:
            ok = observed in {"idle", ""} or view.call_state is None
            return PredicateResult(
                ok,
                f"expected=idle observed={view.call_state!r}",
                view.to_dict(),
            )
        ok = observed == expected or (expected == "ringing" and observed in {"ringing", "calling"})
        return PredicateResult(
            ok,
            f"expected={self.state!r} observed={view.call_state!r}",
            view.to_dict(),
        )


@dataclass
class NoUnexpectedDialog:
    name: str = "NoUnexpectedDialog"

    def evaluate(self, world: WorldModel) -> PredicateResult:
        from plugin.agent.whatsapp_view import WhatsAppWorldView

        view = WhatsAppWorldView.from_world_model(world)
        ok = len(view.unexpected_dialogs) == 0
        return PredicateResult(
            ok,
            f"dialogs={view.unexpected_dialogs}",
            {"unexpected_dialogs": view.unexpected_dialogs},
        )


def evaluate_all(world: WorldModel, predicates: List[WorldPredicate]) -> PredicateResult:
    evidences: Dict[str, Any] = {}
    for p in predicates:
        r = p.evaluate(world)
        evidences[getattr(p, "name", type(p).__name__)] = r.evidence or {"passed": r.passed, "reason": r.reason}
        if not r.passed:
            return PredicateResult(False, r.reason, evidences)
    return PredicateResult(True, "all predicates passed", evidences)
