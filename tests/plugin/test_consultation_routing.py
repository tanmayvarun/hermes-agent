"""Text vs multimodal consultation routing — live 032207 regression."""

from __future__ import annotations

import json
from types import SimpleNamespace

from plugin.agent.consultation_routing import (
    Modality,
    detect_modality,
    is_vision_task,
    model_looks_vision,
    resolve_reasoning_route,
)
from plugin.agent.reasoning_consultation import consult_reasoning


_TEXT_MSGS = [
    {"role": "system", "content": "Return JSON only."},
    {"role": "user", "content": "Author the next search-box query."},
]

_VISION_MSGS = [
    {
        "role": "user",
        "content": [
            {"type": "text", "text": "What surface is this?"},
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,AAAA"},
            },
        ],
    }
]


def test_detect_modality_text_vs_image():
    assert detect_modality(_TEXT_MSGS) is Modality.TEXT
    assert detect_modality(_VISION_MSGS) is Modality.MULTIMODAL


def test_text_only_perception_remaps_to_decision():
    route = resolve_reasoning_route("perception", _TEXT_MSGS, usecase="compose_search_query")
    assert route.remapped
    assert route.task == "decision"
    assert route.modality is Modality.TEXT
    assert "text_messages_must_not_use_vision_task" in route.constraints


def test_compose_usecase_never_stays_on_vision_task():
    route = resolve_reasoning_route(
        "perception",
        _TEXT_MSGS,
        usecase="compose_search_query",
    )
    assert not is_vision_task(route.task)
    assert route.task == "decision"


def test_decision_task_unchanged_for_text():
    route = resolve_reasoning_route("decision", _TEXT_MSGS, usecase="decision_choice")
    assert not route.remapped
    assert route.task == "decision"


def test_meta_choice_usecase_never_stays_on_vision_task():
    route = resolve_reasoning_route("perception", _TEXT_MSGS, usecase="meta_choice")
    assert not is_vision_task(route.task)
    assert route.task == "decision"


def test_multimodal_messages_upgrade_off_decision():
    route = resolve_reasoning_route("decision", _VISION_MSGS, usecase="unified_cognition")
    assert route.remapped
    assert route.task == "perception"
    assert "multimodal_messages_must_use_vision_task" in route.constraints


def test_multimodal_perception_unchanged():
    route = resolve_reasoning_route("perception", _VISION_MSGS)
    assert not route.remapped
    assert route.task == "perception"


def test_honor_requested_task_skips_remap():
    route = resolve_reasoning_route(
        "perception",
        _TEXT_MSGS,
        usecase="compose_search_query",
        honor_requested_task=True,
    )
    assert route.task == "perception"
    assert not route.remapped


def test_qwen_cloud_looks_vision_gpt_oss_does_not():
    assert model_looks_vision("qwen3.5:cloud")
    assert model_looks_vision("qwen3-vl:8b")
    assert not model_looks_vision("gpt-oss:120b")


def test_consult_reasoning_remaps_text_perception_to_decision(monkeypatch):
    from agent import auxiliary_client

    seen: dict[str, object] = {}

    def fake_call_llm(**kwargs):
        seen.update(kwargs)
        message = SimpleNamespace(
            content=json.dumps({"chosen": "zarooratwala Pallavi", "queries": []}),
            tool_calls=[],
        )
        choice = SimpleNamespace(message=message, finish_reason="stop")
        return SimpleNamespace(choices=[choice], usage=None, model="fake")

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)
    monkeypatch.setenv("HERMES_PERCEPTION_MODEL", "qwen3.5:cloud")
    monkeypatch.setenv("HERMES_DECISION_MODEL", "gpt-oss:120b")

    result = consult_reasoning(
        "perception",
        _TEXT_MSGS,
        usecase="compose_search_query",
        call_kwargs={"timeout": 7},
    )
    assert seen["task"] == "decision"
    assert result.task == "decision"
    assert result.parsed.get("chosen") == "zarooratwala Pallavi"


def test_consult_reasoning_keeps_perception_when_images_present(monkeypatch):
    from agent import auxiliary_client

    seen: dict[str, object] = {}

    def fake_call_llm(**kwargs):
        seen.update(kwargs)
        message = SimpleNamespace(
            content=json.dumps({"surface": "chat_list", "confidence": 0.9}),
            tool_calls=[],
        )
        choice = SimpleNamespace(message=message, finish_reason="stop")
        return SimpleNamespace(choices=[choice], usage=None, model="fake")

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)
    monkeypatch.setenv("HERMES_PERCEPTION_MODEL", "qwen3.5:cloud")

    result = consult_reasoning("perception", _VISION_MSGS, call_kwargs={"timeout": 7})
    assert seen["task"] == "perception"
    assert result.task == "perception"
