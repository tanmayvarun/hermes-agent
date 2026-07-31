from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from plugin.agent.action import Action
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.apps.whatsapp import WhatsAppOverlay
from plugin.agent.perception_synthesis import build_perception_prompt_payload, synthesize_perception
from plugin.agent.policy.value import perception_synthesis_bonus
from plugin.agent.decision_selector import build_selector_messages
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel


def _response(payload: dict[str, object]):
    message = SimpleNamespace(content=json.dumps(payload), tool_calls=[])
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], usage=None, model="fake")


def _world() -> WorldModel:
    wm = WorldModel()
    wm.active_app = "WhatsApp"
    wm.entities = {
        1: Entity(
            id=1,
            entity_type="button",
            semantic_role="Search",
            label="Search",
            role="AXButton",
            actions=["click"],
            visible=True,
        ),
        2: Entity(
            id=2,
            entity_type="static",
            semantic_role="Kulvinder Ji",
            label="Kulvinder Ji",
            role="AXStaticText",
            actions=[],
            visible=True,
        ),
    }
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = 3
    wm.last_scene_graph = {
        "report": {"layout_confidence": 0.52, "affordance_entropy": 0.71},
        "attention": {"region_ids": ["sidebar"], "entity_ids": [1, 2]},
        "regions": [{"kind": "sidebar"}],
    }
    return wm


def test_synthesize_perception_calls_llm_once_on_ambiguous_screen(monkeypatch):
    from agent import auxiliary_client

    calls = {"count": 0, "main_runtime": None}

    def fake_call_llm(**kwargs):
        calls["count"] += 1
        calls["main_runtime"] = kwargs.get("main_runtime")
        return _response(
            {
                "screen_type": "conversation",
                "active_surface": "conversation",
                "likely_next_family": "open_contact",
                "likely_next_target": "Kulvinder Ji",
                "likely_next_text": "",
                "confidence": 0.82,
                "avoid_families": ["type_query"],
                "supporting_evidence": ["header and sidebar row match the goal contact"],
                "contradictions": [],
                "needs_followup_observe": False,
            }
        )

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)
    token = auxiliary_client.set_runtime_main(
        "ollama-remote",
        "qwen2.5:32b",
        base_url="http://ollama.test/v1",
    )

    try:
        goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zaroortwala")
        wm = _world()
        view = {
            "screen": "DIALOG",
            "search_query": "",
            "open_conversation": "Kulvinder Ji",
            "visible_contacts": ["Kulvinder Ji"],
            "search_visible": True,
            "search_focused": False,
        }
        features = StateFeatures(
            screen_bucket="dialog",
            worldview_score=0.82,
            mean_belief=0.91,
            extras={"resolution_policy": "observe", "observation_node_count": 12},
        )

        summary = synthesize_perception(goal, wm, view, features, worldview=0.82)
        assert summary is not None
        assert summary.likely_next_family == "open_contact"
        assert calls["count"] == 1
        assert calls["main_runtime"] == {
            "provider": "ollama-remote",
            "model": "qwen2.5:32b",
            "base_url": "http://ollama.test/v1",
            "api_key": "",
            "api_mode": "",
            "auth_mode": "",
        }
        assert features.extras["perception_summary"]["likely_next_family"] == "open_contact"

        again = synthesize_perception(goal, wm, view, features, worldview=0.82)
        assert again is not None
        assert calls["count"] == 1
    finally:
        auxiliary_client.reset_runtime_main(token)


def test_synthesize_perception_prefers_live_runtime_main(monkeypatch):
    from agent import auxiliary_client

    seen = {}

    def fake_call_llm(**kwargs):
        seen.update(
            provider=kwargs.get("provider"),
            model=kwargs.get("model"),
            base_url=kwargs.get("base_url"),
            api_key=kwargs.get("api_key"),
            reasoning_config=kwargs.get("reasoning_config"),
        )
        return _response(
            {
                "screen_type": "conversation",
                "active_surface": "conversation",
                "likely_next_family": "open_contact",
                "likely_next_target": "Kulvinder Ji",
                "likely_next_text": "",
                "confidence": 0.82,
                "avoid_families": ["type_query"],
                "supporting_evidence": ["perception should bind to its own route"],
                "contradictions": [],
                "needs_followup_observe": False,
            }
        )

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)
    token = auxiliary_client.set_runtime_main(
        "openrouter",
        "openai/gpt-oss-120b",
        base_url="https://openrouter.ai/api/v1",
    )

    try:
        goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zaroortwala")
        wm = _world()
        view = {
            "screen": "DIALOG",
            "search_query": "",
            "open_conversation": "Kulvinder Ji",
            "visible_contacts": ["Kulvinder Ji"],
            "search_visible": True,
            "search_focused": False,
        }
        features = StateFeatures(
            screen_bucket="dialog",
            worldview_score=0.82,
            mean_belief=0.91,
            extras={"resolution_policy": "observe", "observation_node_count": 12},
        )

        summary = synthesize_perception(goal, wm, view, features, worldview=0.82)
        assert summary is not None
        assert seen["provider"] == "openrouter"
        assert seen["model"] == "openai/gpt-oss-120b"
        assert seen["reasoning_config"] == {"enabled": True, "effort": "low"}
    finally:
        auxiliary_client.reset_runtime_main(token)


def test_synthesize_perception_fails_hard_without_llm(monkeypatch):
    from agent import auxiliary_client

    def fake_call_llm(**kwargs):
        raise RuntimeError("no provider available")

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)

    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zaroortwala")
    wm = _world()
    view = {
        "screen": "DIALOG",
        "search_query": "",
        "open_conversation": "Kulvinder Ji",
        "visible_contacts": ["Kulvinder Ji"],
        "search_visible": True,
        "search_focused": False,
    }
    features = StateFeatures(
        screen_bucket="dialog",
        worldview_score=0.82,
        mean_belief=0.91,
        extras={"resolution_policy": "observe", "observation_node_count": 12},
    )

    with pytest.raises(RuntimeError):
        synthesize_perception(goal, wm, view, features, worldview=0.82)


def test_synthesize_perception_still_calls_llm_on_degenerate_recovery_view(monkeypatch):
    from agent import auxiliary_client

    calls = {"count": 0, "messages": None}

    def fake_call_llm(**kwargs):
        calls["count"] += 1
        calls["messages"] = kwargs["messages"]
        return _response(
            {
                "screen_type": "conversation",
                "active_surface": "conversation",
                "likely_next_family": "open_contact",
                "likely_next_target": "Kulvinder Ji",
                "likely_next_text": "",
                "confidence": 0.74,
                "avoid_families": ["type_query"],
                "supporting_evidence": ["retained world still contains the source conversation"],
                "contradictions": [],
                "needs_followup_observe": False,
            }
        )

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)

    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zaroortwala")
    wm = WorldModel()
    wm.active_app = "WhatsApp"
    wm.entities = {
        1: Entity(
            id=1,
            entity_type="unknown",
            semantic_role="AXUnknown",
            label="AXUnknown",
            role="AXUnknown",
            actions=[],
            visible=True,
        )
    }
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = 2
    view = {
        "screen": "LIST",
        "search_query": "",
        "open_conversation": "",
        "visible_contacts": [],
        "search_visible": True,
        "search_focused": False,
    }
    features = StateFeatures(
        screen_bucket="list",
        worldview_score=0.2,
        mean_belief=0.9,
        extras={
            "resolution_policy": "observe",
            "observation_node_count": 1,
            "observation_degenerate": True,
            "held_last_good_world": True,
            "world_exploration_needed": True,
        },
    )

    summary = synthesize_perception(goal, wm, view, features, worldview=0.2)
    assert summary is not None
    assert calls["count"] == 1
    payload = json.loads(calls["messages"][1]["content"])
    assert payload["screen"]["observation_node_count"] == 1
    assert payload["screen"]["held_last_good_world"] is True
    assert payload["screen"]["world_exploration_needed"] is True
    assert summary.likely_next_family == "open_contact"


def test_synthesize_perception_prompt_includes_conversation_context(monkeypatch):
    from agent import auxiliary_client

    seen = {}

    def fake_call_llm(**kwargs):
        seen["messages"] = kwargs["messages"]
        return _response(
            {
                "screen_type": "conversation",
                "active_surface": "conversation",
                "likely_next_family": "observe",
                "likely_next_target": "",
                "likely_next_text": "",
                "confidence": 0.5,
                "avoid_families": [],
                "supporting_evidence": ["context included"],
                "contradictions": [],
                "needs_followup_observe": False,
            }
        )

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)

    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zaroortwala")
    wm = _world()
    wm.entities[3] = Entity(
        id=3,
        entity_type="link",
        semantic_role="Your message, Link, https://www.zarooratwala.com/abc",
        label="Your message, Link, https://www.zarooratwala.com/abc",
        role="AXStaticText",
        actions=[],
        visible=True,
        bounds=(900, 420, 300, 60),
    )
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = 4
    overlay = WhatsAppOverlay()
    feats = overlay.features(wm, goal, worldview_score=0.82)
    feats.worldview_score = 0.82
    feats.extras["resolution_policy"] = "observe"
    feats.extras["observation_node_count"] = 12

    summary = synthesize_perception(goal, wm, overlay.view_dict(wm), feats, worldview=0.82)
    assert summary is not None
    assert seen["messages"]
    payload = json.loads(seen["messages"][1]["content"])
    assert "conversation_context" in payload["evidence"]
    assert any("zarooratwala" in str(msg).lower() for msg in payload["evidence"]["conversation_context"])


def test_perception_prompt_shapes_restore_more_context_on_balanced():
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zaroortwala")
    wm = _world()
    for idx in range(3, 18):
        wm.entities[idx] = Entity(
            id=idx,
            entity_type="button" if idx % 2 else "static",
            semantic_role=f"extra-{idx}",
            label=f"Extra {idx}",
            role="AXButton" if idx % 2 else "AXStaticText",
            actions=["click"] if idx % 2 else [],
            visible=True,
            bounds=(20, 220 + idx * 20, 240, 40),
        )
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = 18
    view = {
        "screen": "LIST",
        "search_query": "",
        "open_conversation": "",
        "visible_contacts": ["Kulvinder Ji"],
        "search_visible": True,
        "search_focused": False,
    }
    features = StateFeatures(
        screen_bucket="list",
        worldview_score=0.82,
        mean_belief=0.91,
        extras={
            "resolution_policy": "observe",
            "observation_node_count": 12,
            "conversation_context_text": ["one", "two", "three", "four", "five", "six", "seven", "eight"],
            "ranked_conversation_messages": [
                {"entity_id": i, "score": 1.0 / (i + 1), "text": f"row {i}", "reason": "demo"}
                for i in range(6)
            ],
        },
    )

    compact = build_perception_prompt_payload(goal, wm, view, features, prompt_shape="compact")
    balanced = build_perception_prompt_payload(goal, wm, view, features, prompt_shape="balanced")
    rich = build_perception_prompt_payload(goal, wm, view, features, prompt_shape="rich")

    assert len(compact["evidence"]["visible_entities"]) < len(balanced["evidence"]["visible_entities"])
    assert len(balanced["evidence"]["visible_entities"]) < len(rich["evidence"]["visible_entities"])
    assert "affordance_entropy" not in compact["evidence"]["scene_report"]
    assert "affordance_entropy" in balanced["evidence"]["scene_report"]
    assert "affordance_entropy" in rich["evidence"]["scene_report"]
    assert len(compact["evidence"]["conversation_context"]) < len(balanced["evidence"]["conversation_context"])
    assert len(balanced["evidence"]["conversation_context"]) < len(rich["evidence"]["conversation_context"])


def test_perception_summary_bumps_matching_family():
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zaroortwala")
    features = StateFeatures(
        extras={
            "perception_llm": {
                "confidence": 0.8,
                "likely_next_family": "open_contact",
                "likely_next_target": "Kulvinder Ji",
                "avoid_families": ["type_query"],
                "needs_followup_observe": False,
            }
        }
    )
    open_contact = Action(action="Click", action_family="open_contact", semantic_target="Kulvinder Ji")
    observe = Action(action="Observe", action_family="observe")
    type_query = Action(action="Type", action_family="type_query", semantic_target="Search")

    assert perception_synthesis_bonus(open_contact, features, goal) > 0
    assert perception_synthesis_bonus(type_query, features, goal) < 0
    assert perception_synthesis_bonus(observe, features, goal) < 0


def test_whatsapp_view_does_not_promote_dismiss_target_to_open_conversation():
    from plugin.agent.whatsapp_view import WhatsAppWorldView

    wm = _world()
    wm.last_perception_synthesis = {
        "summary": {
            "screen_type": "dialog",
            "active_surface": "system_dialog",
            "likely_next_family": "dismiss",
            "likely_next_target": "Exit WhatsApp",
            "confidence": 0.73,
        }
    }

    view = WhatsAppWorldView.from_world_model(wm)
    assert view.open_conversation == "Kulvinder Ji"
    assert view.open_conversation != "Exit WhatsApp"


def test_whatsapp_view_does_not_promote_app_title_to_open_conversation():
    from plugin.agent.whatsapp_view import WhatsAppWorldView

    wm = WorldModel()
    wm.active_app = "WhatsApp"
    wm.entities = {
        1: Entity(
            id=1,
            entity_type="button",
            semantic_role="Chats",
            label="Chats",
            role="AXButton",
            actions=["click"],
            visible=True,
            bounds=(20, 20, 100, 32),
        ),
        2: Entity(
            id=2,
            entity_type="textfield",
            semantic_role="Search",
            label="Search",
            role="AXTextField",
            actions=["click", "type"],
            visible=True,
            bounds=(20, 80, 220, 32),
        ),
    }
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = 3
    wm.last_perception_synthesis = {
        "summary": {
            "screen_type": "list",
            "active_surface": "list",
            "likely_next_family": "open_contact",
            "likely_next_target": "WhatsApp for Mac",
            "confidence": 0.82,
        }
    }

    view = WhatsAppWorldView.from_world_model(wm)
    assert view.open_conversation in {None, ""}
    assert view.open_conversation != "WhatsApp for Mac"


def test_selector_messages_include_perception_summary():
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zaroortwala")
    wm = _world()
    features = StateFeatures(
        extras={
            "perception_summary": {
                "screen_type": "conversation",
                "active_surface": "conversation",
                "likely_next_family": "open_contact",
                "likely_next_target": "Kulvinder Ji",
                "confidence": 0.81,
            }
        }
    )
    messages = build_selector_messages(
        goal,
        wm,
        features,
        [("open_contact:1", Action(action="Click", action_family="open_contact", semantic_target="Kulvinder Ji"))],
    )
    payload = json.loads(messages[1]["content"])
    assert payload["perception_summary"]["likely_next_family"] == "open_contact"
