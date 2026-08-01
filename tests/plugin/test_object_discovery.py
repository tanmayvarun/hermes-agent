from __future__ import annotations

import json
from types import SimpleNamespace

from plugin.agent.goal import Goal
from plugin.agent.object_discovery import (
    DiscoveryContext,
    build_content_query,
    resolve_content_objects,
    resolve_content_rows,
)
from plugin.worldmodel.content import content_objects_from_rows


def _response(payload: dict[str, object]):
    message = SimpleNamespace(content=json.dumps(payload), tool_calls=[])
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], usage=None, model="fake")


def _goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
    )


def test_content_object_discovery_prefers_exact_url_match_without_llm(monkeypatch):
    from agent import auxiliary_client

    def fail_call_llm(**kwargs):  # noqa: ARG001
        raise AssertionError("LLM should not be needed for a decisive URL match")

    monkeypatch.setattr(auxiliary_client, "call_llm", fail_call_llm)

    rows = [
        {
            "entity_id": 10,
            "text": "Shared link",
            "label": "Shared link",
            "description": "ZarooratWala – Fresh Groceries Delivered",
            "url": "https://www.zarooratwala.com/?utm_source=chat",
            "role": "AXStaticText",
            "entity_type": "static",
            "visible": True,
        },
        {
            "entity_id": 11,
            "text": "Thanks",
            "label": "Thanks",
            "description": "",
            "role": "AXStaticText",
            "entity_type": "static",
            "visible": True,
        },
    ]
    query = build_content_query(_goal())
    objects = content_objects_from_rows(rows, source_app="WhatsApp", container_id="Kulvinder Ji")
    resolution = resolve_content_objects(
        query,
        objects,
        context=DiscoveryContext(source_app="WhatsApp", container_id="Kulvinder Ji", container_type="conversation"),
        world=None,
        force_llm=False,
    )

    assert resolution.status == "resolved"
    assert resolution.selected_object_id == "10"
    assert resolution.selected_source_entity_ids == [10]
    assert resolution.candidates[0].object_id == "10"
    assert resolution.candidates[0].score > resolution.candidates[1].score


def test_content_object_discovery_llm_reranks_ambiguous_content(monkeypatch):
    from agent import auxiliary_client

    def fake_call_llm(**kwargs):
        return _response(
            {
                "summary": "The row containing the link preview is the intended object.",
                "confidence": 0.94,
                "selected_object_id": "10",
                "ranked_objects": [
                    {"object_id": "10", "score": 0.98, "reason": "contains the share link preview"},
                    {"object_id": "11", "score": 0.12, "reason": "reply noise"},
                ],
                "selected_source_entity_ids": [10],
                "selected_object_text": "Shared link",
                "supporting_evidence": ["domain token matches the goal"],
                "contradictions": [],
                "next_information_actions": [],
                "needs_followup_observe": False,
            }
        )

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)

    rows = [
        {
            "entity_id": 10,
            "text": "Shared link",
            "label": "Shared link",
            "description": "ZarooratWala – Fresh Groceries Delivered",
            "role": "AXStaticText",
            "entity_type": "static",
            "visible": True,
        },
        {
            "entity_id": 11,
            "text": "Other note",
            "label": "Other note",
            "description": "",
            "role": "AXStaticText",
            "entity_type": "static",
            "visible": True,
        },
    ]

    query = build_content_query(_goal())
    objects = content_objects_from_rows(rows, source_app="WhatsApp", container_id="Kulvinder Ji")
    resolution = resolve_content_objects(
        query,
        objects,
        context=DiscoveryContext(
            source_app="WhatsApp",
            container_id="Kulvinder Ji",
            container_type="conversation",
            use_llm=True,
        ),
        world=None,
        force_llm=True,
    )

    assert resolution.status == "resolved"
    assert resolution.selected_object_id == "10"
    assert resolution.selected_source_entity_ids == [10]
    assert resolution.candidates[0].object_id == "10"


def test_resolve_content_rows_keeps_adapter_boundary_thin(monkeypatch):
    from agent import auxiliary_client

    monkeypatch.setattr(
        auxiliary_client,
        "call_llm",
        lambda **kwargs: _response(
            {
                "summary": "Selected the relevant object.",
                "confidence": 0.92,
                "selected_object_id": "10",
                "ranked_objects": [{"object_id": "10", "score": 0.99, "reason": "matches the goal"}],
                "selected_source_entity_ids": [10],
                "selected_object_text": "Shared link",
                "supporting_evidence": ["adapter exposed the visible row"],
                "contradictions": [],
                "next_information_actions": [],
                "needs_followup_observe": False,
            }
        ),
    )

    rows = [
        {
            "entity_id": 10,
            "text": "Shared link",
            "label": "Shared link",
            "description": "ZarooratWala – Fresh Groceries Delivered",
            "role": "AXStaticText",
            "entity_type": "static",
            "visible": True,
        }
    ]

    result = resolve_content_rows(
        _goal(),
        rows,
        source_app="WhatsApp",
        container_id="Kulvinder Ji",
        container_type="conversation",
        context=DiscoveryContext(source_app="WhatsApp", container_id="Kulvinder Ji", container_type="conversation"),
        world=None,
        force_llm=True,
    )

    assert result.selected_object_id == "10"
    assert result.evidence
    assert result.next_information_actions == []


def test_resolve_content_objects_includes_active_subgraph_in_prompt(monkeypatch):
    from agent import auxiliary_client

    seen = {}

    def fake_call_llm(**kwargs):
        seen["messages"] = kwargs.get("messages")
        return _response(
            {
                "summary": "Selected the relevant object.",
                "confidence": 0.92,
                "selected_object_id": "10",
                "ranked_objects": [{"object_id": "10", "score": 0.99, "reason": "matches the goal"}],
                "selected_source_entity_ids": [10],
                "selected_object_text": "Shared link",
                "supporting_evidence": ["adapter exposed the visible row"],
                "contradictions": [],
                "next_information_actions": [],
                "needs_followup_observe": False,
            }
        )

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)

    rows = [
        {
            "entity_id": 10,
            "text": "Shared link",
            "label": "Shared link",
            "description": "ZarooratWala – Fresh Groceries Delivered",
            "role": "AXStaticText",
            "entity_type": "static",
            "visible": True,
        }
    ]

    result = resolve_content_rows(
        _goal(),
        rows,
        source_app="WhatsApp",
        container_id="Kulvinder Ji",
        container_type="conversation",
        context=DiscoveryContext(
            source_app="WhatsApp",
            container_id="Kulvinder Ji",
            container_type="conversation",
            active_subgraph={
                "phase": "conversation",
                "focus_region_ids": ["timeline"],
                "active_entity_ids": [10],
                "grounded_capability_ids": ["select_content"],
            },
        ),
        world=None,
        force_llm=True,
    )

    assert result.selected_object_id == "10"
    payload = json.loads(seen["messages"][1]["content"])
    assert payload["context"]["active_subgraph"]["active_entity_ids"] == [10]
    assert payload["context"]["active_subgraph"]["focus_region_ids"] == ["timeline"]
