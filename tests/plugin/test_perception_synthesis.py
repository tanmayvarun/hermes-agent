from __future__ import annotations

import logging
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from plugin.agent.action import Action
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.apps.whatsapp import WhatsAppOverlay
from plugin.agent.perception_synthesis import (
    build_perception_prompt_payload,
    synthesize_perception,
    _perception_task_targets,
    _perception_timeout_seconds,
)
from plugin.agent.reasoning_consultation import ReasoningConsultationResult
from plugin.agent.policy.value import perception_synthesis_bonus
from plugin.agent.decision_selector import build_selector_messages
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel


def _response(payload: dict[str, object]):
    message = SimpleNamespace(content=json.dumps(payload), tool_calls=[])
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], usage=None, model="fake")


def _consultation_result(task: str, messages, payload: dict[str, object], call_kwargs=None):
    call_kwargs = call_kwargs or {}
    return ReasoningConsultationResult(
        task=task,
        messages=[dict(msg) for msg in messages],
        raw_response=json.dumps(payload),
        parsed=dict(payload),
        confidence=float(payload.get("confidence") or 0.0),
        abstained=bool(payload.get("needs_followup_observe") or payload.get("abstained")),
        reason=str(payload.get("reason") or ""),
        timeout_s=float(call_kwargs.get("timeout") or 0.0),
        max_tokens=int(call_kwargs.get("max_tokens") or 0),
        provider=str(call_kwargs.get("provider") or ""),
        model=str(call_kwargs.get("model") or ""),
        base_url=str(call_kwargs.get("base_url") or ""),
    )


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
    calls = {"count": 0, "main_runtime": None}

    def fake_consult_reasoning(task, messages, **kwargs):
        calls["count"] += 1
        calls["main_runtime"] = (kwargs.get("call_kwargs") or {}).get("main_runtime")
        payload = {
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
        return _consultation_result(task, messages, payload, kwargs.get("call_kwargs"))

    monkeypatch.setattr("plugin.agent.perception_synthesis.consult_reasoning", fake_consult_reasoning)
    from agent import auxiliary_client
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
    seen = {}

    def fake_consult_reasoning(task, messages, **kwargs):
        call_kwargs = kwargs.get("call_kwargs") or {}
        seen.update(
            provider=call_kwargs.get("provider"),
            model=call_kwargs.get("model"),
            base_url=call_kwargs.get("base_url"),
            api_key=call_kwargs.get("api_key"),
            reasoning_config=call_kwargs.get("reasoning_config"),
        )
        payload = {
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
        return _consultation_result(task, messages, payload, call_kwargs)

    monkeypatch.setattr("plugin.agent.perception_synthesis.consult_reasoning", fake_consult_reasoning)
    monkeypatch.setattr(
        "plugin.agent.perception_synthesis.rank_task_models",
        lambda *args, **kwargs: [
            SimpleNamespace(provider="ollama-cloud", model="qwen3.5:cloud", base_url="https://ollama.com/v1", source="cloud"),
            SimpleNamespace(provider="ollama-cloud", model="kimi-k3:cloud", base_url="https://ollama.com/v1", source="cloud"),
            SimpleNamespace(provider="ollama-cloud", model="gemma4:cloud", base_url="https://ollama.com/v1", source="cloud"),
        ],
    )
    from agent import auxiliary_client
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
        assert seen["provider"] == "ollama-cloud"
        assert seen["model"] == "qwen3.5:cloud"
        assert seen["reasoning_config"] == {"enabled": True, "effort": "low"}
    finally:
        auxiliary_client.reset_runtime_main(token)


def test_perception_prompt_drops_menu_chrome_for_message_tasks():
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zaroortwala")
    wm = _world()
    wm.entities[3] = Entity(
        id=3,
        entity_type="menu",
        semantic_role="Help",
        label="Help",
        role="AXMenuItem",
        visible=True,
    )
    wm.tracker._entities = dict(wm.entities)
    view = {
        "screen": "CONVERSATION",
        "search_query": "",
        "open_conversation": "Kulvinder Ji",
        "visible_contacts": ["Kulvinder Ji"],
        "search_visible": True,
        "search_focused": False,
    }
    features = StateFeatures(
        screen_bucket="conversation",
        worldview_score=0.91,
        mean_belief=0.95,
        extras={"resolution_policy": "observe", "observation_node_count": 12},
    )

    payload = build_perception_prompt_payload(goal, wm, view, features, prompt_shape="balanced")
    visible_labels = [str(ent.get("label") or "") for ent in payload["evidence"]["visible_entities"]]

    assert "Help" not in visible_labels
    assert any("Kulvinder" in label for label in visible_labels)


def test_synthesize_perception_switches_to_screen_understanding_with_screenshot(monkeypatch, tmp_path):
    from agent import auxiliary_client

    seen = {}

    def fake_call_llm(**kwargs):
        seen.update(
            task=kwargs.get("task"),
            provider=kwargs.get("provider"),
            model=kwargs.get("model"),
            messages=kwargs.get("messages"),
        )
        return _response(
            {
                "screen_type": "conversation",
                "active_surface": "conversation",
                "likely_next_family": "open_contact",
                "likely_next_target": "Kulvinder Ji",
                "likely_next_text": "",
                "confidence": 0.88,
                "avoid_families": ["type_query"],
                "supporting_evidence": ["screenshot and AX both show the source conversation"],
                "contradictions": [],
                "needs_followup_observe": False,
            }
        )

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)
    monkeypatch.setattr(
        "plugin.agent.perception_synthesis.rank_task_models",
        lambda *args, **kwargs: [
            SimpleNamespace(provider="ollama-cloud", model="qwen3.5:cloud", base_url="https://ollama.com/v1", source="cloud"),
            SimpleNamespace(provider="ollama-cloud", model="kimi-k3:cloud", base_url="https://ollama.com/v1", source="cloud"),
            SimpleNamespace(provider="ollama-cloud", model="gemma4:cloud", base_url="https://ollama.com/v1", source="cloud"),
        ],
    )
    token = auxiliary_client.set_runtime_main(
        "ollama-remote",
        "qwen2.5:32b",
        base_url="http://ollama.test/v1",
    )

    try:
        goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zaroortwala")
        wm = _world()
        screenshot = tmp_path / "vision-screen.png"
        screenshot.write_bytes(
            bytes.fromhex(
                "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                "1f15c4890000000a49444154789c6360000002000154012a0d0a00000000"
                "49454e44ae426082"
            )
        )
        view = {
            "screen": "DIALOG",
            "search_query": "",
            "open_conversation": "Kulvinder Ji",
            "visible_contacts": ["Kulvinder Ji"],
            "search_visible": True,
            "search_focused": False,
            "screenshot_path": str(screenshot),
        }
        features = StateFeatures(
            screen_bucket="dialog",
            worldview_score=0.62,
            mean_belief=0.84,
            extras={
                "resolution_policy": "observe",
                "observation_node_count": 12,
                "screenshot_path": str(screenshot),
                "scene_layout_confidence": 0.42,
                "scene_region_coverage": 0.61,
            },
        )

        summary = synthesize_perception(goal, wm, view, features, worldview=0.62)
        assert summary is not None
        assert seen["task"] == "screen_understanding"
        assert seen["provider"] == "ollama-cloud"
        assert seen["model"] == "qwen3.5:cloud"
        assert isinstance(seen["messages"][1]["content"], list)
        assert any(
            isinstance(part, dict) and part.get("type") == "image_url"
            for part in seen["messages"][1]["content"]
        )
        assert features.extras["perception_task"] == "screen_understanding"
    finally:
        auxiliary_client.reset_runtime_main(token)


def test_screen_understanding_ignores_legacy_non_cloud_override(monkeypatch):
    from agent import auxiliary_client

    monkeypatch.setattr(
        "plugin.agent.perception_synthesis.rank_task_models",
        lambda *args, **kwargs: [
            SimpleNamespace(provider="ollama-cloud", model="qwen3.5:cloud", base_url="https://ollama.com/v1", source="cloud"),
            SimpleNamespace(provider="ollama-cloud", model="kimi-k3:cloud", base_url="https://ollama.com/v1", source="cloud"),
            SimpleNamespace(provider="ollama-cloud", model="gemma4:cloud", base_url="https://ollama.com/v1", source="cloud"),
        ],
    )
    monkeypatch.setattr(
        auxiliary_client,
        "_get_auxiliary_task_config",
        lambda task: {
            "provider": "ollama-remote",
            "model": "qwen2.5:32b",
            "base_url": "http://ollama.test/v1",
            "api_key": "",
        }
        if task in {"screen_understanding", "perception"}
        else {},
    )

    targets = _perception_task_targets({"provider": "ollama-remote", "model": "qwen2.5:32b", "base_url": "http://ollama.test/v1"}, task_name="screen_understanding")
    assert [(t["provider"], t["model"]) for t in targets[:3]] == [
        ("ollama-cloud", "qwen3.5:cloud"),
        ("ollama-cloud", "kimi-k3:cloud"),
        ("ollama-cloud", "gemma4:cloud"),
    ]
    assert all(t["provider"] == "ollama-cloud" for t in targets[:3])


def test_synthesize_perception_fails_hard_without_llm(monkeypatch):
    def fake_consult_reasoning(task, messages, **kwargs):
        raise RuntimeError("no provider available")

    monkeypatch.setattr("plugin.agent.perception_synthesis.consult_reasoning", fake_consult_reasoning)

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
    calls = {"count": 0, "messages": None}

    def fake_consult_reasoning(task, messages, **kwargs):
        calls["count"] += 1
        calls["messages"] = messages
        payload = {
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
        return _consultation_result(task, messages, payload, kwargs.get("call_kwargs"))

    monkeypatch.setattr("plugin.agent.perception_synthesis.consult_reasoning", fake_consult_reasoning)

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
    content = calls["messages"][1]["content"]
    if isinstance(content, list):
        text_parts = [part.get("text") for part in content if isinstance(part, dict) and part.get("type") == "text"]
        payload = json.loads(text_parts[0])
    else:
        payload = json.loads(content)
    assert payload["screen"]["observation_node_count"] == 1
    assert payload["screen"]["held_last_good_world"] is True
    assert payload["screen"]["world_exploration_needed"] is True
    assert summary.likely_next_family == "open_contact"


def test_synthesize_perception_prompt_includes_conversation_context(monkeypatch):
    seen = {}

    def fake_consult_reasoning(task, messages, **kwargs):
        seen["messages"] = messages
        payload = {
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
        return _consultation_result(task, messages, payload, kwargs.get("call_kwargs"))

    monkeypatch.setattr("plugin.agent.perception_synthesis.consult_reasoning", fake_consult_reasoning)

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
    content = seen["messages"][1]["content"]
    if isinstance(content, list):
        text_parts = [part.get("text") for part in content if isinstance(part, dict) and part.get("type") == "text"]
        payload = json.loads(text_parts[0])
    else:
        payload = json.loads(content)
    assert "conversation_context" in payload["evidence"]
    assert any("zarooratwala" in str(msg).lower() for msg in payload["evidence"]["conversation_context"])


def test_synthesize_perception_emits_human_readable_log(monkeypatch, caplog):
    seen = {}

    def fake_consult_reasoning(task, messages, **kwargs):
        seen["messages"] = messages
        payload = {
            "screen_type": "conversation",
            "active_surface": "conversation",
            "likely_next_family": "open_contact",
            "likely_next_target": "Kulvinder Ji",
            "likely_next_text": "",
            "confidence": 0.86,
            "avoid_families": ["type_query"],
            "supporting_evidence": ["header and timeline rows align with the source conversation"],
            "contradictions": [],
            "needs_followup_observe": False,
        }
        return _consultation_result(task, messages, payload, kwargs.get("call_kwargs"))

    monkeypatch.setattr("plugin.agent.perception_synthesis.consult_reasoning", fake_consult_reasoning)
    monkeypatch.setattr(
        "plugin.agent.perception_synthesis.rank_task_models",
        lambda *args, **kwargs: [
            SimpleNamespace(provider="ollama-cloud", model="qwen3.5:cloud", base_url="https://ollama.com/v1", source="cloud"),
        ],
    )

    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zarooratwala")
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
        worldview_score=0.61,
        mean_belief=0.84,
        extras={
            "resolution_policy": "observe",
            "observation_node_count": 12,
            "conversation_context_text": ["Kulvinder Ji", "Zarooratwala – Fresh Groceries Delivered"],
            "screenshot_path": "",
            "app_content_node_count": 3,
        },
    )

    caplog.set_level(logging.INFO)
    summary = synthesize_perception(goal, wm, view, features, worldview=0.61)

    assert summary is not None
    assert "Perception LLM human summary:" in caplog.text
    assert "screen=conversation" in caplog.text
    assert "next=open_contact" in caplog.text
    assert features.extras["perception_human_readable"].startswith("Perception summary[screen_understanding]")


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

    assert len(compact["evidence"]["conversation_timeline"]) <= len(balanced["evidence"]["conversation_timeline"])
    assert len(balanced["evidence"]["conversation_timeline"]) <= len(rich["evidence"]["conversation_timeline"])
    assert "affordance_entropy" not in compact["evidence"]["scene_report"]
    assert "affordance_entropy" in balanced["evidence"]["scene_report"]
    assert "affordance_entropy" in rich["evidence"]["scene_report"]
    assert len(compact["evidence"]["conversation_context"]) < len(balanced["evidence"]["conversation_context"])
    assert len(balanced["evidence"]["conversation_context"]) < len(rich["evidence"]["conversation_context"])


def test_perception_prompt_projects_whatsapp_timeline_and_filters_noise():
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zarooratwala")
    wm = _world()
    wm.entities[3] = Entity(
        id=3,
        entity_type="static",
        semantic_role="Messages in chat with Kulvinder Ji",
        label="Messages in chat with Kulvinder Ji",
        role="AXStaticText",
        visible=True,
        bounds=(620, 40, 420, 28),
    )
    wm.entities[4] = Entity(
        id=4,
        entity_type="link",
        semantic_role="Zarooratwala – Fresh Groceries Delivered",
        label="Zarooratwala – Fresh Groceries Delivered",
        role="AXLink",
        visible=True,
        bounds=(920, 380, 360, 54),
        attributes={"description": "https://www.zarooratwala.com/?utm_source=ig"},
    )
    wm.entities[5] = Entity(
        id=5,
        entity_type="menu",
        semantic_role="Format",
        label="Format",
        role="AXMenuItem",
        visible=True,
        bounds=(20, 20, 120, 28),
    )
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = 6
    view = {
        "screen": "CONVERSATION",
        "search_query": "",
        "open_conversation": "Kulvinder Ji",
        "visible_contacts": ["Kulvinder Ji"],
        "search_visible": False,
        "search_focused": False,
    }
    features = StateFeatures(
        screen_bucket="conversation",
        worldview_score=0.79,
        mean_belief=0.93,
        extras={
            "conversation_context_text": ["Messages in chat with Kulvinder Ji", "Zarooratwala – Fresh Groceries Delivered"],
            "conversation_timeline": [
                {
                    "message_ids": [4],
                    "entity_ids": [4],
                    "text": "Zarooratwala – Fresh Groceries Delivered",
                    "urls": ["https://www.zarooratwala.com/?utm_source=ig"],
                    "row_count": 1,
                }
            ],
            "active_cognitive_subgraph": {
                "active_entity_ids": [3, 4],
                "focus_region_ids": ["timeline"],
                "phase": "conversation",
            },
        },
    )

    payload = build_perception_prompt_payload(goal, wm, view, features, prompt_shape="balanced")
    visible_texts = " ".join(
        str(item.get("text") or item.get("label") or item.get("description") or "")
        for item in payload["evidence"]["visible_entities"]
    ).lower()
    timeline = payload["evidence"]["conversation_timeline"]

    assert timeline and "zarooratwala" in json.dumps(timeline).lower()
    assert "format" not in visible_texts
    assert "zarooratwala" in visible_texts or "kulvinder" in visible_texts


def test_perception_timeout_is_capped():
    # The budget must fit a large cloud vision model (qwen3.5:397b peaked ~58s),
    # but stay bounded so a hung call cannot stall the loop indefinitely.
    from plugin.agent.perception_synthesis import _MAX_PERCEPTION_TIMEOUT_SECONDS

    timeout = _perception_timeout_seconds()
    assert 15.0 <= timeout <= _MAX_PERCEPTION_TIMEOUT_SECONDS


def test_perception_timeout_env_override_is_bounded(monkeypatch):
    from plugin.agent.perception_synthesis import _MAX_PERCEPTION_TIMEOUT_SECONDS

    monkeypatch.setenv("HERMES_PERCEPTION_LLM_TIMEOUT_SECONDS", "500")
    assert _perception_timeout_seconds() == _MAX_PERCEPTION_TIMEOUT_SECONDS
    monkeypatch.setenv("HERMES_PERCEPTION_LLM_TIMEOUT_SECONDS", "1")
    assert _perception_timeout_seconds() == 5.0


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
