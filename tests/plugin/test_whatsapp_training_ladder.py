"""WhatsApp training ladder — read before actuation, then backtrack/forward.

Each stage is intentionally harder than the previous one:
1. Read the chat header without mistaking contact-card chrome for the open chat.
2. Read the message timeline and prefer the source message over profile/info UI.
3. Keep source bindings stable when the info overlay is visible.
4. Only treat the destination picker as actionable when the picker surface exists.
5. Keep irreversible actuator confidence configurable and non-hardcoded.
6. Treat external-link shares as timeline source messages before forwarding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
from types import SimpleNamespace

import pytest

from plugin.agent.apps.whatsapp import WhatsAppOverlay, build_forward_task_state, _infer_forward_phase
from plugin.agent.decision import DecisionEngine
from plugin.agent.goal import Goal
from plugin.agent.policy.candidates import enumerate_candidates
from plugin.agent.policy.value import predicted_value_delta
from plugin.agent.features import StateFeatures
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.whatsapp_view import WhatsAppWorldView
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel
from plugin.worldmodel.capability import build_capability_graph
from plugin.worldmodel.scene.reconstruct import reconstruct_world_graph


def _entity(
    eid: int,
    *,
    etype: str = "button",
    label: str,
    bounds=(0.0, 0.0, 40.0, 40.0),
    description: str = "",
    value: str = "",
    role: Optional[str] = None,
    actions: Optional[List[str]] = None,
) -> Entity:
    attrs: Dict[str, object] = {}
    if description:
        attrs["description"] = description
    if value:
        attrs["value"] = value
    return Entity(
        id=eid,
        entity_type=etype,
        semantic_role=label,
        label=label,
        role=role or ("AXTextField" if etype == "textfield" else "AXButton"),
        bounds=bounds,
        actions=actions if actions is not None else (["click"] if etype in {"button", "link"} else ["click", "type"] if etype == "textfield" else []),
        attributes=attrs,
        visible=True,
    )


def _seed(entities: List[Entity]) -> WorldModel:
    wm = WorldModel()
    wm.active_app = "WhatsApp"
    wm.entities = {e.id: e for e in entities}
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = max(e.id for e in entities) + 1 if entities else 1
    wm.overlay_hints = {}
    return wm


def _forward_goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
    )


def _maps_forward_goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        # Normalized binding key for the prompt:
        # "find the google maps share link of india coffee house hsr layout and share with pallavi"
        link_query="india coffee house hsr layout",
    )


def _godrej_maps_forward_goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        # Normalized binding key for the prompt:
        # "find the google share location of godrej nurutre electronic city phase 1 and share with pallavi on whatsapp"
        link_query="godrej nurture electronic city phase 1",
    )


def _llm_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


def test_stage_01_header_is_open_chat_not_info_card_chrome():
    """Prompt: identify the current chat before doing anything else."""
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="static", bounds=(900, 20, 180, 34), actions=[]),
            _entity(2, label="Audio", etype="button", bounds=(930, 180, 100, 40)),
            _entity(3, label="Video", etype="button", bounds=(1040, 180, 100, 40)),
            _entity(4, label="Search", etype="button", bounds=(1150, 180, 100, 40)),
            _entity(5, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)

    assert view.screen == "CONVERSATION"
    assert view.open_conversation == "Kulvinder Ji"
    assert "audio" not in {c.lower() for c in view.visible_contacts}
    assert "video" not in {c.lower() for c in view.visible_contacts}
    assert "search" not in {c.lower() for c in view.visible_contacts}


def test_stage_01b_window_title_is_not_promoted_to_open_conversation():
    """Prompt: ignore the app window title when no chat header is visible."""
    wm = _seed(
        [
            _entity(1, label="Settings", etype="button", bounds=(10, 10, 120, 32)),
            _entity(2, label="Chats", etype="button", bounds=(10, 50, 120, 32)),
        ]
    )
    wm.last_window_name = "WhatsApp for Mac"
    view = WhatsAppWorldView.from_world_model(wm)

    assert view.open_conversation in {None, ""}
    assert view.screen in {"LIST", "UNKNOWN"}


def test_stage_02_timeline_message_beats_profile_panel_actions():
    """Prompt: find the source message in the chat timeline, not the side panel."""
    goal = _forward_goal()
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="static", bounds=(900, 20, 180, 34), actions=[]),
            _entity(10, label="Your message, Link, https://www.zarooratwala.com/abc", etype="link", bounds=(920, 420, 300, 60)),
            _entity(11, label="Your photo", etype="static", bounds=(920, 500, 300, 60), description="ZarooratWala – Fresh Groceries Delivered"),
            _entity(12, label="Audio", etype="button", bounds=(930, 180, 100, 40)),
            _entity(13, label="Video", etype="button", bounds=(1040, 180, 100, 40)),
            _entity(14, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    overlay = WhatsAppOverlay()
    feats = overlay.features(wm, goal)
    ft = build_forward_task_state(goal, wm, WhatsAppWorldView.from_world_model(wm), leftover=False)
    cands = enumerate_candidates(goal, wm, feats, overlay)

    assert ft.binding("source_object").resolved_entity_id == 10
    assert ft.binding("source_object").status in {"provisional", "confirmed"}
    assert ft.predicates.source_object_visible is True
    assert any(a.action_family == "select_content" and a.target_entity_id == 10 for a in cands)


def test_conversation_context_window_captures_latest_message_rows():
    """Prompt: reason over the last message window, not one row at a time."""
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="static", bounds=(900, 20, 180, 34), actions=[]),
            _entity(2, label="Info", etype="button", bounds=(1120, 220, 100, 40)),
            _entity(3, label="Your message, Link, https://www.zarooratwala.com/abc", etype="link", bounds=(920, 420, 300, 60)),
            _entity(4, label="Your message, Hello", etype="static", bounds=(920, 500, 300, 60)),
            _entity(5, label="Your message, Thanks", etype="static", bounds=(920, 580, 300, 60)),
            _entity(6, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    texts = [row["text"] for row in view.conversation_messages]
    assert any("zarooratwala" in text.lower() for text in texts)
    assert any("hello" in text.lower() for text in texts)
    assert any("thanks" in text.lower() for text in texts)
    assert all("info" not in text.lower() for text in texts)
    assert len(texts) <= 100


def test_stage_03_source_binding_survives_overlay_and_backtracks_generic_surface():
    """Prompt: keep the source binding alive when contact info chrome is visible."""
    goal = _forward_goal()
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="static", bounds=(900, 20, 180, 34), actions=[]),
            _entity(10, label="Your message, Link, https://www.zarooratwala.com/abc", etype="link", bounds=(920, 420, 300, 60)),
            _entity(11, label="Media, links and docs", etype="button", bounds=(920, 220, 180, 40)),
            _entity(12, label="Info", etype="button", bounds=(1120, 220, 100, 40)),
            _entity(13, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    prior = {
        "bindings": {
            "source_object": {
                "name": "source_object",
                "constraints": {"content_tokens": ["zarooratwala"], "types": ["link", "message"]},
                "candidate_entity_ids": [10],
                "resolved_entity_id": 10,
                "confidence": 0.9,
                "status": "confirmed",
                "evidence": ["selected entity_id=10"],
            }
        },
        "predicates": {
            "source_conversation_open": True,
            "source_object_visible": True,
            "source_object_selected": True,
            "forward_surface_open": False,
            "destination_picker_visible": False,
            "destination_selected": False,
            "forward_completed": False,
        },
        "derived_phase": "OPEN_FORWARD",
    }
    view = WhatsAppWorldView.from_world_model(wm)
    ft = build_forward_task_state(goal, wm, view, leftover=False, prior=prior)
    feats = WhatsAppOverlay().features(wm, goal)
    feats.extras["forward_task"] = ft.to_dict()
    feats.extras["forward_phase"] = ft.derived_phase

    assert ft.binding("source_object").resolved_entity_id == 10
    assert ft.binding("source_object").status == "confirmed"
    assert ft.predicates.source_object_selected is True
    assert ft.derived_phase in {"OPEN_FORWARD", "PICK_DEST"}
    assert _infer_forward_phase(goal, wm, view, leftover=False) in {"OPEN_FORWARD", "PICK_DEST"}


def test_stage_04_destination_picker_only_on_picker_surface():
    """Prompt: only enter destination selection when the picker is visible."""
    goal = _forward_goal()
    picker_world = _seed(
        [
            _entity(1, label="Send to", etype="static", bounds=(600, 100, 200, 30), actions=[]),
            _entity(2, label="Select chats", etype="static", bounds=(600, 140, 200, 30), actions=[]),
            _entity(3, label="Search", etype="textfield", bounds=(600, 200, 300, 40)),
        ]
    )
    non_picker_world = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="static", bounds=(900, 20, 180, 34), actions=[]),
            _entity(2, label="Forward", etype="button", bounds=(500, 500, 80, 36)),
            _entity(3, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    picker_view = WhatsAppWorldView.from_world_model(picker_world)
    non_picker_view = WhatsAppWorldView.from_world_model(non_picker_world)

    picker_state = build_forward_task_state(goal, picker_world, picker_view, leftover=False)
    non_picker_state = build_forward_task_state(goal, non_picker_world, non_picker_view, leftover=False)

    assert picker_state.predicates.destination_picker_visible is True
    assert picker_state.derived_phase == "PICK_DEST"
    assert non_picker_state.predicates.destination_picker_visible is False
    assert non_picker_state.derived_phase != "PICK_DEST"


def test_stage_05_irreversible_threshold_is_configurable(monkeypatch):
    """Prompt: do not hardcode the confidence gate for irreversible actuators."""
    engine = DecisionEngine()
    import hermes_cli.config as config_mod

    monkeypatch.setattr(
        config_mod,
        "load_config_readonly",
        lambda: {"agent": {"irreversible_action_confidence_threshold": 0.83}},
        raising=True,
    )
    assert engine.irreversible_action_confidence_threshold() == pytest.approx(0.83)


def test_stage_06_high_risk_selector_uses_dedicated_task_and_risk_gate_for_forward_picker():
    """Prompt: high-risk forward choices must carry the risk gate into the selector."""
    goal = _forward_goal()
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="static", bounds=(900, 20, 180, 34), actions=[]),
            _entity(2, label="Your message, Link, https://www.zarooratwala.com/abc", etype="link", bounds=(920, 420, 300, 60)),
            _entity(3, label="Forward", etype="button", bounds=(900, 140, 100, 36)),
            _entity(4, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    wm_graph = reconstruct_world_graph(list(wm.entities.values()), app="WhatsApp")
    wm.last_scene_graph = wm_graph.to_dict()
    wm.last_capability_graph = build_capability_graph(
        wm_graph,
        list(wm.entities.values()),
        goal=goal,
        capability_hints=WhatsAppOverlay().capability_hints(goal),
    ).to_dict()

    captured: Dict[str, object] = {}

    def fake_selector(**kwargs):
        captured.update(kwargs)
        return _llm_response('{"choice": "Forward", "confidence": 0.94, "reason": "forward chrome visible"}')

    engine = DecisionEngine(selector_enabled=True, selector_caller=fake_selector)
    decision = engine.define_action_step(goal, wm, ExecutionState())

    assert decision is not None
    assert decision.action_family in {"forward_message", "select_content", "type_query"}
    assert decision.capability_type in {"ForwardMessage", "SelectContent", "SearchConversation"}
    assert engine.last_trace is not None
    assert engine.last_trace.selector_confidence == pytest.approx(0.94)
    assert captured["task"] == "decision_high_risk"
    assert captured["reasoning_config"]["enabled"] is True
    assert captured["reasoning_config"]["effort"] == "high"
    prompt = captured["messages"][1]["content"]
    assert '"risk_gate"' in prompt
    assert '"irreversible_threshold": 0.7' in prompt
    assert '"ForwardMessage"' in prompt or '"forward_message"' in prompt
    assert "zarooratwala" in prompt.lower()


def test_stage_07_high_risk_selector_surfaces_forward_risk_and_goal_context():
    """Prompt: forwarding paths must expose irreversible context to the selector."""
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
    )
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="static", bounds=(900, 20, 180, 34), actions=[]),
            _entity(2, label="Your message, Link, https://www.zarooratwala.com/abc", etype="link", bounds=(920, 420, 300, 60)),
            _entity(3, label="Forward", etype="button", bounds=(900, 140, 100, 36)),
            _entity(4, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    wm_graph = reconstruct_world_graph(list(wm.entities.values()), app="WhatsApp")
    wm.last_scene_graph = wm_graph.to_dict()
    wm.last_capability_graph = build_capability_graph(
        wm_graph,
        list(wm.entities.values()),
        goal=goal,
        capability_hints=WhatsAppOverlay().capability_hints(goal),
    ).to_dict()

    captured: Dict[str, object] = {}

    def fake_selector(**kwargs):
        captured.update(kwargs)
        return _llm_response('{"choice": "Forward", "confidence": 0.91, "reason": "forward chrome visible"}')

    engine = DecisionEngine(selector_enabled=True, selector_caller=fake_selector)
    decision = engine.define_action_step(goal, wm, ExecutionState())

    assert decision is not None
    assert decision.action_family in {"forward_message", "select_content", "type_query"}
    assert decision.capability_type in {"ForwardMessage", "SelectContent", "SearchConversation"}
    assert engine.last_trace is not None
    assert engine.last_trace.selector_confidence == pytest.approx(0.91)
    assert captured["task"] == "decision_high_risk"
    assert captured["reasoning_config"]["effort"] == "high"
    prompt = captured["messages"][1]["content"]
    assert '"risk_gate"' in prompt
    assert '"irreversible_threshold": 0.7' in prompt
    assert '"ForwardMessage"' in prompt or '"forward_message"' in prompt
    assert "zarooratwala" in prompt.lower()


def test_stage_08_google_maps_share_link_prompt_prefers_timeline_link_over_profile_chrome():
    """Prompt: find the Google Maps share link in the source chat, then forward it."""
    goal = _maps_forward_goal()
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="static", bounds=(900, 20, 180, 34), actions=[]),
            _entity(
                10,
                label="Google Maps share link: India Coffee House HSR Layout",
                etype="link",
                bounds=(920, 420, 360, 60),
                description="Maps share link for India Coffee House HSR Layout",
            ),
            _entity(11, label="Media, links and docs", etype="button", bounds=(920, 220, 180, 40)),
            _entity(12, label="Info", etype="button", bounds=(1120, 220, 100, 40)),
            _entity(13, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    ft = build_forward_task_state(goal, wm, view, leftover=False)
    overlay = WhatsAppOverlay()
    feats = overlay.features(wm, goal)
    cands = enumerate_candidates(goal, wm, feats, overlay)

    assert ft.binding("source_object").resolved_entity_id == 10
    assert ft.binding("source_object").status in {"provisional", "confirmed"}
    assert ft.predicates.source_object_visible is True
    assert any(a.action_family == "select_content" and a.target_entity_id == 10 for a in cands)


def test_stage_09_google_maps_location_share_prompt_prefers_timeline_link_over_profile_chrome():
    """Prompt: find the Google share location in the source chat, then forward it."""
    goal = _godrej_maps_forward_goal()
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="static", bounds=(900, 20, 180, 34), actions=[]),
            _entity(
                10,
                label="Google Maps share location: Godrej Nurture Electronic City Phase 1",
                etype="link",
                bounds=(920, 420, 360, 60),
                description="Maps share location for Godrej Nurture Electronic City Phase 1",
            ),
            _entity(11, label="Media, links and docs", etype="button", bounds=(920, 220, 180, 40)),
            _entity(12, label="Info", etype="button", bounds=(1120, 220, 100, 40)),
            _entity(13, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    ft = build_forward_task_state(goal, wm, view, leftover=False)
    overlay = WhatsAppOverlay()
    feats = overlay.features(wm, goal)
    cands = enumerate_candidates(goal, wm, feats, overlay)

    assert ft.binding("source_object").resolved_entity_id == 10
    assert ft.binding("source_object").status in {"provisional", "confirmed"}
    assert ft.predicates.source_object_visible is True
    assert any(a.action_family == "select_content" and a.target_entity_id == 10 for a in cands)


def test_whatsapp_view_ignores_storage_warning_as_contact():
    wm = _seed(
        [
            _entity(1, label="Storage is too full", etype="button", bounds=(10, 10, 220, 32), actions=["click"]),
            _entity(2, label="Kulvinder Ji", etype="static", bounds=(900, 20, 180, 34), actions=[]),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    assert "Storage is too full" not in view.visible_contacts


def test_whatsapp_view_ignores_menu_chrome_as_contact():
    wm = _seed(
        [
            _entity(1, label="Format", etype="menu", bounds=(10, 10, 120, 32), actions=["click"]),
            _entity(2, label="Kulvinder Ji", etype="static", bounds=(900, 20, 180, 34), actions=[]),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    assert "Format" not in view.visible_contacts


def test_whatsapp_view_uses_scene_layout_fallback_for_list():
    wm = _seed(
        [
            _entity(1, label="Format", etype="menu", bounds=(10, 10, 120, 32), actions=["click"]),
            _entity(2, label="Storage is too full", etype="button", bounds=(10, 50, 220, 32), actions=["click"]),
        ]
    )
    wm.last_scene_graph = {
        "regions": [
            {"kind": "sidebar", "entity_ids": [1]},
            {"kind": "timeline", "entity_ids": [2]},
        ]
    }
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.screen == "LIST"
