from __future__ import annotations

import json
from types import SimpleNamespace

from plugin.agent.apps.whatsapp import WhatsAppOverlay, build_forward_task_state
from plugin.agent.conversation_reasoning import ConversationMessageRelevance, rank_conversation_messages
from plugin.agent.goal import Goal
from plugin.agent.whatsapp_view import WhatsAppWorldView
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel


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


def _world() -> WorldModel:
    wm = WorldModel()
    wm.active_app = "WhatsApp"
    wm.entities = {
        1: Entity(
            id=1,
            entity_type="static",
            semantic_role="Kulvinder Ji",
            label="Kulvinder Ji",
            role="AXStaticText",
            visible=True,
            bounds=(900, 20, 180, 34),
        ),
        10: Entity(
            id=10,
            entity_type="static",
            semantic_role="Shared link",
            label="Shared link",
            role="AXStaticText",
            visible=True,
            bounds=(920, 420, 340, 56),
            attributes={"description": "ZarooratWala – Fresh Groceries Delivered"},
        ),
        11: Entity(
            id=11,
            entity_type="static",
            semantic_role="Thanks",
            label="Thanks",
            role="AXStaticText",
            visible=True,
            bounds=(920, 500, 220, 44),
        ),
    }
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = 12
    wm.overlay_hints = {}
    return wm


def test_rank_conversation_messages_ranks_without_consulting_a_second_model(monkeypatch):
    """Relevance belongs to unified cognition, which reads the same rows.

    Ranking here is evidence for that judgement, not a rival to it, so this
    path must reach its answer without spending another model call.
    """
    from agent import auxiliary_client

    calls = {"count": 0}

    def fail_call_llm(**kwargs):  # noqa: ARG001
        calls["count"] += 1
        raise AssertionError("conversation ranking must not consult a second model")

    monkeypatch.setattr(auxiliary_client, "call_llm", fail_call_llm)

    wm = _world()
    view = {
        "screen": "CONVERSATION",
        "open_conversation": "Kulvinder Ji",
        "search_query": "",
        "conversation_context_window": 100,
    }
    rows = [
        {
            "entity_id": 10,
            "text": "Shared link",
            "label": "Shared link",
            "description": "ZarooratWala – Fresh Groceries Delivered",
            "role": "AXStaticText",
            "entity_type": "static",
        },
        {
            "entity_id": 11,
            "text": "Thanks",
            "label": "Thanks",
            "description": "",
            "role": "AXStaticText",
            "entity_type": "static",
        },
    ]

    result = rank_conversation_messages(_goal(), view, rows, world=wm, force=True)
    assert result is not None
    assert result.likely_source_message_ids == [10]
    assert result.ranked_messages[0]["entity_id"] == 10
    assert calls["count"] == 0

    cached = rank_conversation_messages(_goal(), view, rows, world=wm, force=True)
    assert cached is not None
    assert cached.likely_source_message_ids == [10]
    assert calls["count"] == 0


def test_rank_conversation_messages_skips_when_conversation_not_open(monkeypatch):
    from agent import auxiliary_client

    def fail_call_llm(**kwargs):  # noqa: ARG001
        raise AssertionError("LLM should not run when the conversation pane is not observed")

    monkeypatch.setattr(auxiliary_client, "call_llm", fail_call_llm)

    wm = _world()
    view = {
        "screen": "LIST",
        "open_conversation": "",
        "search_query": "",
        "conversation_context_window": 100,
    }
    rows = [
        {
            "entity_id": 10,
            "text": "Shared link",
            "label": "Shared link",
            "description": "ZarooratWala – Fresh Groceries Delivered",
            "role": "AXStaticText",
            "entity_type": "static",
        }
    ]

    assert rank_conversation_messages(_goal(), view, rows, world=wm, force=True) is None


def test_rank_conversation_messages_accepts_search_results_when_conversation_is_open(monkeypatch):
    from agent import auxiliary_client

    calls = {"count": 0}

    def fail_call_llm(**kwargs):  # noqa: ARG001
        calls["count"] += 1
        raise AssertionError("conversation ranking must not consult a second model")

    monkeypatch.setattr(auxiliary_client, "call_llm", fail_call_llm)

    wm = _world()
    view = {
        "screen": "SEARCH_RESULTS",
        "open_conversation": "Kulvinder Ji",
        "search_query": "Kulvinder",
        "conversation_context_window": 100,
        "conversation_timeline": [
            {
                "entity_id": 10,
                "text": "Shared link",
                "label": "Shared link",
                "description": "ZarooratWala – Fresh Groceries Delivered",
                "role": "AXStaticText",
                "entity_type": "static",
            }
        ],
    }
    rows = [
        {
            "entity_id": 10,
            "text": "Shared link",
            "label": "Shared link",
            "description": "ZarooratWala – Fresh Groceries Delivered",
            "role": "AXStaticText",
            "entity_type": "static",
        }
    ]

    result = rank_conversation_messages(_goal(), view, rows, world=wm, force=True)
    assert result is not None
    assert result.likely_source_message_ids == [10]
    assert calls["count"] == 0


def test_forward_binding_uses_llm_ranked_message_when_deterministic_match_is_absent(monkeypatch):
    from plugin.agent import task_binding
    from plugin.agent.apps import whatsapp as whatsapp_mod

    monkeypatch.setattr(task_binding, "find_query_entities", lambda *args, **kwargs: [])

    def fake_rank_conversation_messages(*args, **kwargs):
        return ConversationMessageRelevance(
            summary="Relevant source message located.",
            confidence=0.94,
            ranked_messages=[
                {
                    "entity_id": 10,
                    "score": 0.97,
                    "reason": "the share link preview is the item to forward",
                    "text": "Shared link",
                    "label": "Shared link",
                    "description": "ZarooratWala – Fresh Groceries Delivered",
                }
            ],
            likely_source_message_ids=[10],
            likely_source_message_text="Shared link",
            supporting_evidence=["row 10 is the source link"],
            contradictions=[],
            needs_followup_observe=False,
            raw={},
        )

    monkeypatch.setattr(whatsapp_mod, "rank_conversation_messages", fake_rank_conversation_messages)

    wm = _world()
    goal = _goal()
    overlay = WhatsAppOverlay()
    feats = overlay.features(wm, goal)
    ft = build_forward_task_state(goal, wm, WhatsAppWorldView.from_world_model(wm), leftover=False)

    assert feats.extras["conversation_message_relevance"]["likely_source_message_ids"] == [10]
    assert ft.binding("source_object").resolved_entity_id == 10
    assert ft.binding("source_object").status in {"provisional", "confirmed"}
    assert ft.binding("source_object").evidence[0].startswith("llm_ranked entity_id=10")
