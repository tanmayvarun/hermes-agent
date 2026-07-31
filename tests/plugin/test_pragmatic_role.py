"""Pragmatic role layer — label vs CTA vs nav vs status."""

from __future__ import annotations

from typing import Dict, List, Optional

import pytest

from plugin.agent.apps.whatsapp import WhatsAppOverlay
from plugin.agent.apps.whatsapp_targets import resolve_whatsapp_target
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.policy.candidates import enumerate_candidates
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.whatsapp_view import WhatsAppWorldView
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel
from plugin.worldmodel.pragmatic_role import (
    UiPragmaticRole,
    get_pragmatic_role,
    infer_pragmatic_role_stage2,
    is_active_call_evidence,
)
from plugin.worldmodel.scene.reconstruct import reconstruct_world_graph
from plugin.worldmodel.screens.detect import guess_screen_kind, guess_screen_label


def _entity(
    eid: int,
    *,
    etype: str = "button",
    label: str,
    bounds=(0.0, 0.0, 40.0, 40.0),
    description: str = "",
    role: str = "AXButton",
    actions: Optional[List[str]] = None,
) -> Entity:
    attrs: Dict = {}
    if description:
        attrs["description"] = description
    e = Entity(
        id=eid,
        entity_type=etype,
        semantic_role=label,
        label=label,
        role=role,
        bounds=bounds,
        actions=actions if actions is not None else (["click"] if etype in {"button", "link", "menu"} else []),
        attributes=attrs,
        visible=True,
    )
    infer_pragmatic_role_stage2(e)
    return e


def _seed(entities: List[Entity], app: str = "WhatsApp") -> WorldModel:
    wm = WorldModel()
    wm.active_app = app
    wm.entities = {e.id: e for e in entities}
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = max(e.id for e in entities) + 1 if entities else 1
    return wm


def test_calls_nav_is_nav_chrome_not_active_call():
    e = _entity(1, label="Calls", bounds=(40, 40, 60, 30))
    assert get_pragmatic_role(e) == UiPragmaticRole.NAV_CHROME
    assert is_active_call_evidence(e) is False


def test_end_call_cta_is_active_call_evidence():
    e = _entity(1, label="End Call", bounds=(900, 700, 80, 40))
    assert get_pragmatic_role(e) == UiPragmaticRole.CTA
    assert is_active_call_evidence(e) is True


def test_ghost_end_call_not_active():
    e = _entity(1, label="End Call", bounds=(0, 0, 0, 0))
    assert is_active_call_evidence(e) is False


def test_chat_list_guess_screen_not_call():
    ents = [
        _entity(1, label="Chats", bounds=(40, 40, 60, 30)),
        _entity(2, label="Calls", bounds=(120, 40, 60, 30)),
        _entity(3, label="List of chats", etype="static", bounds=(40, 100, 300, 400), actions=[]),
        _entity(4, label="end-to-end encrypted", etype="static", bounds=(400, 500, 200, 20), actions=[]),
        _entity(5, label="Search", etype="button", bounds=(40, 80, 80, 28)),
        _entity(6, label="End Call", bounds=(0, 0, 0, 0)),
    ]
    assert guess_screen_label(ents) != "call"
    view = WhatsAppWorldView.from_world_model(_seed(ents))
    assert view.screen != "CALLING"
    assert view.call_state != "ringing"


def test_synthesized_dialog_does_not_override_strong_conversation_state():
    wm = _seed(
        [
            _entity(
                1,
                label="Messages in chat with Kulvinder Ji",
                etype="static",
                bounds=(400, 20, 400, 30),
                actions=[],
            ),
            _entity(2, label="Type a message", etype="textfield", bounds=(400, 900, 600, 40)),
            _entity(3, label="Kulvinder Ji", bounds=(40, 200, 280, 48)),
        ]
    )
    wm.last_perception_synthesis = {
        "cache_key": "x",
        "summary": {
            "screen_type": "dialog",
            "active_surface": "dialog",
            "likely_next_family": "dismiss",
            "likely_next_target": "Snehil",
            "likely_next_text": "",
            "confidence": 0.42,
            "avoid_families": [],
            "supporting_evidence": ["weak"],
            "contradictions": [],
            "needs_followup_observe": False,
            "raw": {},
        },
    }
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.screen == "CONVERSATION"
    assert view.composer_visible is True


def test_dialog_hints_do_not_override_list_context_without_modal_evidence():
    wm = _seed(
        [
            _entity(1, label="Search", etype="textfield", role="AXSearchField", bounds=(40, 40, 300, 30), actions=["click", "type"]),
            _entity(2, label="Later", etype="button", bounds=(900, 220, 120, 40)),
            _entity(3, label="Papaji", etype="static", bounds=(900, 80, 220, 30), actions=[]),
            _entity(4, label="Chats", bounds=(40, 40, 60, 30)),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.screen in {"SEARCH", "SEARCH_RESULTS", "LIST", "CONVERSATION"}
    assert view.screen != "DIALOG"


def test_synthesized_dialog_needs_empty_surface_not_list_context():
    wm = _seed(
        [
            _entity(1, label="Search", etype="textfield", role="AXSearchField", bounds=(40, 40, 300, 30), actions=["click", "type"]),
            _entity(2, label="Papaji", etype="static", bounds=(900, 80, 220, 30), actions=[]),
            _entity(3, label="Kulvinder Ji", etype="button", bounds=(60, 160, 260, 56), description="Chat row"),
            _entity(4, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    wm.last_perception_synthesis = {
        "cache_key": "x",
        "summary": {
            "screen_type": "dialog",
            "active_surface": "dialog",
            "likely_next_family": "dismiss",
            "likely_next_target": "Papaji",
            "likely_next_text": "",
            "confidence": 0.86,
            "avoid_families": [],
            "supporting_evidence": ["weak"],
            "contradictions": [],
            "needs_followup_observe": False,
            "raw": {},
        },
    }
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.screen in {"LIST", "SEARCH", "SEARCH_RESULTS", "CONVERSATION"}
    assert view.screen != "DIALOG"


def test_followup_observe_signal_does_not_become_dialog():
    wm = _seed(
        [
            _entity(1, label="Search", etype="textfield", role="AXSearchField", bounds=(40, 40, 300, 30), actions=["click", "type"]),
            _entity(2, label="Kulvinder Ji", etype="button", bounds=(60, 160, 260, 56), description="Chat row"),
            _entity(3, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    wm.last_perception_synthesis = {
        "cache_key": "x",
        "summary": {
            "screen_type": "dialog",
            "active_surface": "dialog",
            "likely_next_family": "observe",
            "likely_next_target": "",
            "likely_next_text": "",
            "confidence": 0.7,
            "avoid_families": [],
            "supporting_evidence": ["followup"],
            "contradictions": [],
            "needs_followup_observe": True,
            "raw": {},
        },
    }
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.screen in {"LIST", "SEARCH", "SEARCH_RESULTS", "CONVERSATION"}
    assert view.blocking_overlay is False
    assert view.screen != "DIALOG"


def test_voice_resolves_to_header_not_mic():
    wm = _seed(
        [
            _entity(1, label="Voice message", bounds=(1600, 1000, 48, 48)),
            _entity(2, label="Voice", bounds=(900, 40, 36, 36)),
            _entity(3, label="Type a message", etype="textfield", bounds=(400, 1000, 800, 40)),
        ]
    )
    hit = resolve_whatsapp_target(wm, "Voice", action="click", action_family="start_call")
    assert hit is not None
    assert hit.label == "Voice"


def test_search_button_on_list_not_search_screen():
    ents = [
        _entity(1, label="Chats", bounds=(40, 40, 60, 30)),
        _entity(2, label="List of chats", etype="static", bounds=(40, 100, 300, 400), actions=[]),
        _entity(3, label="Search", etype="button", bounds=(200, 40, 60, 28)),
    ]
    assert guess_screen_label(ents) == "conversation"


def test_generic_screen_kind_can_unlock_forward_search_on_detail_surface():
    wm = _seed(
        [
            _entity(1, label="Chats", bounds=(40, 40, 60, 30)),
            _entity(2, label="Search", etype="button", bounds=(200, 40, 60, 28)),
        ]
    )
    overlay = WhatsAppOverlay()
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zaroortwala",
    )
    feats = StateFeatures(
        screen_kind="detail",
        screen_bucket="conversation",
        extras={
            "forward_phase": "OPEN_SOURCE",
            "resolution_policy": "auto",
            "resolution_confidence": 1.0,
        },
    )
    cands = enumerate_candidates(goal, wm, feats, overlay)
    assert any(a.action_family == "type_query" for a in cands)


def test_generic_call_label_on_list_does_not_become_call_screen():
    ents = [
        _entity(1, label="Chats", bounds=(40, 40, 60, 30)),
        _entity(2, label="Call", etype="button", bounds=(200, 40, 60, 28)),
        _entity(3, label="Kulvinder Ji", etype="button", bounds=(60, 160, 260, 56), description="Chat row"),
        _entity(4, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
    ]
    assert guess_screen_kind(ents) != "call"
    view = WhatsAppWorldView.from_world_model(_seed(ents))
    assert view.screen != "CALLING"


def test_decision_engine_falls_back_when_llm_selector_returns_no_choice(monkeypatch):
    from plugin.agent.decision import DecisionEngine

    monkeypatch.setattr(
        "plugin.agent.decision.select_action_with_llm",
        lambda *args, **kwargs: (None, {"reason": "not_ambiguous_enough"}),
    )
    monkeypatch.setattr("plugin.agent.decision.synthesize_perception", lambda *args, **kwargs: None)
    wm = _seed(
        [
            _entity(1, label="Chats", bounds=(40, 40, 60, 30)),
            _entity(2, label="Search", etype="button", bounds=(200, 40, 60, 28)),
        ]
    )
    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")
    decision = DecisionEngine().decide(goal, wm, ExecutionState())
    assert decision is not None


def test_generic_screen_kind_detects_blocking_overlay_without_app_vocab():
    ents = [
        _entity(1, label="Storage is too full", etype="static", bounds=(120, 120, 420, 48), actions=[]),
        _entity(2, label="Exit", etype="button", bounds=(120, 500, 240, 40)),
    ]
    assert guess_screen_kind(ents) == "dialog"
    assert guess_screen_label(ents) == "dialog"


def test_generic_screen_kind_detects_input_surface_without_app_specific_words():
    ents = [
        _entity(
            1,
            label="Find",
            etype="textfield",
            role="AXSearchField",
            bounds=(40, 40, 300, 30),
            actions=["click", "type"],
        ),
        _entity(2, label="Result A", etype="static", bounds=(40, 100, 300, 40), actions=[]),
        _entity(3, label="Result B", etype="static", bounds=(40, 150, 300, 40), actions=[]),
    ]
    assert guess_screen_kind(ents) == "search"
    assert guess_screen_label(ents) == "search"


def test_forward_status_text_not_forward_cta_candidate():
    wm = _seed(
        [
            _entity(
                1,
                label="Messages in chat with Kulvinder",
                etype="static",
                bounds=(400, 20, 400, 30),
                actions=[],
            ),
            _entity(2, label="Forwarded", etype="static", bounds=(450, 200, 120, 20), actions=[]),
            _entity(3, label="Type a message", etype="textfield", bounds=(400, 900, 600, 40)),
        ]
    )
    reconstruct_world_graph(list(wm.entities.values()), app="WhatsApp")
    overlay = WhatsAppOverlay()
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zaroortwala",
    )
    feats = overlay.features(wm, goal)
    # "Forwarded" must not look like forward picker chrome → must not skip to PICK_DEST
    assert feats.extras.get("forward_phase") == "OPEN_SOURCE" or feats.extras.get(
        "forward_phase"
    ) in {"FIND_LINK", "OPEN_FORWARD", "OPEN_SOURCE"}
    from plugin.agent.apps.whatsapp import _forward_chrome_visible, _infer_forward_phase

    view = WhatsAppWorldView.from_world_model(wm)
    assert _forward_chrome_visible(wm) is False
    phase = _infer_forward_phase(goal, wm, view, leftover=False)
    assert phase != "PICK_DEST"
    assert phase in {"OPEN_SOURCE", "FIND_LINK", "OPEN_FORWARD"}

    feats.extras["forward_phase"] = "OPEN_FORWARD"
    feats.extras["open_conversation"] = "Kulvinder"
    cands = enumerate_candidates(goal, wm, feats, overlay)
    forward_ctas = [
        a
        for a in cands
        if a.action_family == "forward_message"
        and (a.semantic_target or "").lower() == "forwarded"
    ]
    assert forward_ctas == []


def test_navigation_region_or_nav_role_for_tabs():
    ents = [
        _entity(1, label="Chats", bounds=(20, 30, 50, 28)),
        _entity(2, label="Calls", bounds=(80, 30, 50, 28)),
        _entity(3, label="Updates", bounds=(140, 30, 60, 28)),
        _entity(4, label="Settings", bounds=(210, 30, 60, 28)),
        _entity(5, label="Papaji", bounds=(400, 200, 200, 40)),
        _entity(6, label="Type a message", etype="textfield", bounds=(400, 900, 600, 40)),
    ]
    graph = reconstruct_world_graph(ents, app="WhatsApp")
    kinds = {r.kind.value for r in graph.regions}
    assert "navigation" in kinds or get_pragmatic_role(ents[1]) == UiPragmaticRole.NAV_CHROME
