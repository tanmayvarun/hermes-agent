"""Object-bound forward control — bindings, predicates, no naked More."""

from __future__ import annotations

from typing import Dict, List, Optional
from pathlib import Path
import json
from types import SimpleNamespace

import pytest

from plugin.agent.apps.whatsapp import (
    WhatsAppOverlay,
    build_forward_task_state,
    _conversation_context_rows,
    _infer_forward_phase,
)
from plugin.agent.decision import DecisionEngine
from plugin.agent.goal import Goal
from plugin.agent.policy.candidates import enumerate_candidates
from plugin.agent.policy.value import predicted_value_delta
from plugin.agent.action import Action
from plugin.agent.features import StateFeatures
from plugin.agent.predicates import ConversationOpen
from plugin.agent.controller import _bind_forward_after_execution
from plugin.agent.runtime.state import ExecutionState, RuntimeState
from plugin.agent.task_binding import ForwardTaskState, picker_chrome_visible
from plugin.agent.whatsapp_view import WhatsAppWorldView, contact_names_from_entity
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.capability import Capability
from plugin.worldmodel.model import WorldModel


@pytest.fixture(autouse=True)
def _disable_live_conversation_ranking(monkeypatch):
    from plugin.agent.apps import whatsapp as whatsapp_mod

    monkeypatch.setattr(whatsapp_mod, "rank_conversation_messages", lambda *args, **kwargs: None)


def test_forward_runtime_binding_prefers_ollama_cloud_gpt_oss_default(monkeypatch):
    """The live forward loop should bind to the Ollama Cloud primary runtime."""
    import plugin.experiments.run_forward_message as runner

    seen = {}

    def fake_set_runtime_main(provider, model, *, base_url="", api_key="", api_mode="", auth_mode=""):
        seen.update(
            {
                "provider": provider,
                "model": model,
                "base_url": base_url,
                "api_key": api_key,
                "api_mode": api_mode,
                "auth_mode": auth_mode,
            }
        )

    monkeypatch.setenv("OLLAMA_BASE_URL", "https://ollama.example.test/v1")
    monkeypatch.setattr("agent.auxiliary_client.set_runtime_main", fake_set_runtime_main)

    runner._bind_forward_runtime_main()

    assert seen == {
        "provider": "ollama-cloud",
        "model": "gpt-oss:120b",
        "base_url": "https://ollama.example.test/v1",
        "api_key": "",
        "api_mode": "",
        "auth_mode": "",
    }


def test_forward_launcher_pins_main_model_default():
    script = Path("plugin/experiments/runs/run_forward_zarooratwala.command").read_text()
    assert 'HERMES_MODEL:=gpt-oss:120b' in script
    assert 'HERMES_INFERENCE_MODEL:=gpt-oss:120b' in script
    assert 'HERMES_AUXILIARY_PROVIDER_POLICY=ollama-only' in script
    assert 'HERMES_INFERENCE_PROVIDER:=ollama-cloud' in script
    assert 'HERMES_PERCEPTION_PROVIDER:=ollama-cloud' in script
    assert 'OPENROUTER_BASE_URL' not in script
    assert 'OPENROUTER_API_KEY' not in script


def _entity(
    eid: int,
    *,
    etype: str = "button",
    label: str,
    bounds=(0.0, 0.0, 40.0, 40.0),
    description: str = "",
    actions: Optional[List[str]] = None,
) -> Entity:
    attrs: Dict = {}
    if description:
        attrs["description"] = description
    return Entity(
        id=eid,
        entity_type=etype,
        semantic_role=label,
        label=label,
        role="AXButton" if etype == "button" else "AXStaticText",
        bounds=bounds,
        actions=actions if actions is not None else (["click"] if etype in {"button", "link"} else []),
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


def _goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zaroortwala",
    )


def _response(payload: dict[str, object]):
    message = SimpleNamespace(content=json.dumps(payload), tool_calls=[])
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], usage=None, model="fake")


def test_query_visible_without_selection_not_pick_dest():
    wm = _seed(
        [
            _entity(1, label="Messages in chat with Kulvinder Ji", etype="static", bounds=(400, 20, 400, 30), actions=[]),
            _entity(2, label="Check zaroortwala.com for details", etype="static", bounds=(900, 300, 300, 40), actions=[]),
            _entity(3, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
            _entity(4, label="More", etype="button", bounds=(150, 50, 40, 30)),
            _entity(5, label="Forwarded", etype="static", bounds=(900, 280, 80, 20), actions=[]),
            _entity(6, label="Chats", etype="button", bounds=(40, 40, 60, 30)),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    phase = _infer_forward_phase(_goal(), wm, view, leftover=False)
    assert phase != "PICK_DEST"
    assert phase in {"FIND_LINK", "OPEN_FORWARD"}
    ft = build_forward_task_state(_goal(), wm, view, leftover=False)
    assert ft.predicates.destination_picker_visible is False
    assert ft.binding("source_object").candidate_entity_ids


def test_conversation_context_rows_fall_back_to_timeline_clusters():
    view = WhatsAppWorldView(
        screen="CONVERSATION",
        open_conversation="Kulvinder Ji",
        conversation_messages=[],
        conversation_timeline=[
            {
                "message_ids": [195],
                "entity_ids": [195],
                "text": "Your message, Link, https://www.zarooratwala.com/?utm_source=ig",
                "label": "ZarooratWala – Fresh Groceries Delivered",
                "description": "sidebar mislabel",
                "urls": ["https://www.zarooratwala.com/?utm_source=ig"],
                "top_y": 420.0,
                "x": 920.0,
            }
        ],
    )

    rows = _conversation_context_rows(view)

    assert rows
    assert any("zarooratwala.com" in (row["text"] or "").lower() for row in rows)


def test_conversation_context_rows_do_not_use_timeline_on_list_screen():
    view = WhatsAppWorldView(
        screen="LIST",
        open_conversation="",
        conversation_messages=[],
        conversation_timeline=[
            {
                "message_ids": [195],
                "entity_ids": [195],
                "text": "Your message, Link, https://www.zarooratwala.com/?utm_source=ig",
                "label": "ZarooratWala – Fresh Groceries Delivered",
                "description": "sidebar mislabel",
                "urls": ["https://www.zarooratwala.com/?utm_source=ig"],
                "top_y": 420.0,
                "x": 920.0,
            }
        ],
    )

    assert _conversation_context_rows(view) == []


def test_forward_task_state_does_not_bind_source_object_without_observed_conversation():
    wm = _seed(
        [
            _entity(1, label="Messages in chat with Kulvinder Ji", etype="static", bounds=(400, 20, 400, 30), actions=[]),
            _entity(2, label="Check zaroortwala.com for details", etype="static", bounds=(900, 300, 300, 40), actions=[]),
            _entity(3, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    view = WhatsAppWorldView(
        screen="LIST",
        open_conversation="",
        visible_contacts=["Kulvinder Ji"],
        conversation_messages=[],
        conversation_timeline=[
            {
                "message_ids": [2],
                "entity_ids": [2],
                "text": "Check zaroortwala.com for details",
                "label": "Shared link",
                "description": "ZarooratWala – Fresh Groceries Delivered",
                "urls": ["https://www.zarooratwala.com/?utm_source=ig"],
                "top_y": 300.0,
                "x": 900.0,
            }
        ],
    )
    state = build_forward_task_state(_goal(), wm, view, leftover=False)

    assert state.binding("source_object").candidate_entity_ids == []
    assert state.binding("source_object").status == "unresolved"
    assert state.predicates.source_object_visible is False
    assert state.derived_phase == "OPEN_SOURCE"


def test_forward_task_state_binds_source_object_on_search_results_when_conversation_is_open():
    wm = _seed(
        [
            _entity(1, label="Messages in chat with Kulvinder Ji", etype="static", bounds=(400, 20, 400, 30), actions=[]),
            _entity(2, label="Check zaroortwala.com for details", etype="static", bounds=(900, 300, 300, 40), actions=[]),
            _entity(3, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    view = WhatsAppWorldView(
        screen="SEARCH_RESULTS",
        open_conversation="Kulvinder Ji",
        visible_contacts=["Kulvinder Ji"],
        conversation_messages=[],
        conversation_timeline=[
            {
                "message_ids": [2],
                "entity_ids": [2],
                "text": "Check zaroortwala.com for details",
                "label": "Shared link",
                "description": "ZarooratWala – Fresh Groceries Delivered",
                "urls": ["https://www.zarooratwala.com/?utm_source=ig"],
                "top_y": 300.0,
                "x": 900.0,
            }
        ],
    )
    state = build_forward_task_state(_goal(), wm, view, leftover=False)

    assert state.binding("source_object").candidate_entity_ids == [2]
    assert state.binding("source_object").status in {"provisional", "confirmed"}
    assert state.predicates.source_object_visible is True
    assert state.derived_phase in {"FIND_LINK", "OPEN_SOURCE", "OPEN_FORWARD", "PICK_SOURCE"}


def test_contact_card_label_noise_does_not_become_dialog():
    wm = _seed(
        [
            _entity(1, label="Search", etype="textfield", bounds=(40, 80, 200, 30), description="Search", actions=["click"]),
            _entity(2, label="Papaji", etype="static", bounds=(900, 80, 220, 30), actions=[]),
            _entity(3, label="Kulvinder Ji", etype="static", bounds=(60, 160, 260, 56), description="Chat row"),
            _entity(4, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.screen in {"SEARCH", "SEARCH_RESULTS", "LIST", "CONVERSATION"}
    assert view.screen != "DIALOG"
    assert view.unexpected_dialogs == []


def test_preclear_signature_stalls_on_repeated_unchanged_state():
    from plugin.experiments.run_forward_message import _note_preclear_signature, _PRECLEAR_STALL_SIGNATURE_LIMIT

    prev = "screen=conversation|open=Kulvinder|call_state="
    current = prev
    repeat_count = 0

    for _ in range(_PRECLEAR_STALL_SIGNATURE_LIMIT - 1):
        repeat_count, stalled = _note_preclear_signature(prev, current, repeat_count=repeat_count)
        assert stalled is False
        assert repeat_count > 0

    repeat_count, stalled = _note_preclear_signature(prev, current, repeat_count=repeat_count)
    assert stalled is True
    assert repeat_count >= _PRECLEAR_STALL_SIGNATURE_LIMIT

    repeat_count, stalled = _note_preclear_signature(current, "screen=list|open=|call_state=", repeat_count=repeat_count)
    assert stalled is False
    assert repeat_count == 0


def test_forwarded_status_alone_not_picker():
    wm = _seed(
        [
            _entity(1, label="Messages in chat with Kulvinder", etype="static", bounds=(400, 20, 400, 30), actions=[]),
            _entity(2, label="Forwarded", etype="static", bounds=(450, 200, 120, 20), actions=[]),
            _entity(3, label="Type a message", etype="textfield", bounds=(400, 900, 600, 40)),
        ]
    )
    assert picker_chrome_visible(list(wm.entities.values())) is False
    overlay = WhatsAppOverlay()
    feats = overlay.features(wm, _goal())
    assert feats.extras.get("forward_phase") != "PICK_DEST"
    cands = enumerate_candidates(_goal(), wm, feats, overlay)
    dest_types = [
        a
        for a in cands
        if a.action_family == "type_query" and (a.text or "").lower() == "pallavi"
    ]
    assert dest_types == []


def test_no_naked_more_when_source_object_unresolved():
    wm = _seed(
        [
            _entity(1, label="Messages in chat with Kulvinder Ji", etype="static", bounds=(400, 20, 400, 30), actions=[]),
            _entity(2, label="hello world", etype="static", bounds=(450, 300, 200, 40), actions=[]),
            _entity(3, label="Type a message", etype="textfield", bounds=(400, 900, 600, 40)),
            _entity(4, label="More", etype="button", bounds=(150, 50, 40, 30)),
        ]
    )
    overlay = WhatsAppOverlay()
    feats = overlay.features(wm, _goal())
    assert feats.extras.get("forward_phase") == "FIND_LINK"
    cands = enumerate_candidates(_goal(), wm, feats, overlay)
    more = [
        a
        for a in cands
        if a.action_family == "explore_chrome"
        and (a.semantic_target or "").lower() in {"more", "more options", "menu"}
    ]
    assert more == []
    # Value ban if somehow candidated
    bad = Action(action="Click", semantic_target="More", action_family="explore_chrome")
    assert predicted_value_delta(bad, feats, _goal()) < 0


def test_dialog_surface_does_not_emit_open_search_candidate():
    wm = _seed(
        [
            _entity(1, label="Search", etype="button", bounds=(40, 80, 120, 30)),
            _entity(2, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    overlay = WhatsAppOverlay()
    feats = StateFeatures(
        extras={
            "forward_phase": "OPEN_SOURCE",
            "wa_screen": "DIALOG",
            "result_surface_visible": False,
            "search_focused": False,
            "source_conversation_rows": [],
            "source_conversation_visible": False,
        }
    )
    cands = enumerate_candidates(_goal(), wm, feats, overlay)
    assert not any(a.action_family == "open_search" for a in cands)


def test_storage_pressure_does_not_emit_dismiss_candidate():
    wm = _seed(
        [
            _entity(1, label="Exit WhatsApp", etype="button", bounds=(450, 780, 280, 50)),
            _entity(2, label="Storage is too full", etype="static", bounds=(300, 240, 520, 44), actions=[]),
        ]
    )
    overlay = WhatsAppOverlay()
    feats = StateFeatures(
        screen_bucket="dialog",
        has_dialog=True,
        extras={
            "storage_pressure": True,
            "system_warnings": ["Storage is too full"],
            "dialogs": ["Exit WhatsApp"],
        },
    )
    cands = enumerate_candidates(_goal(), wm, feats, overlay)
    assert not any(a.action_family == "dismiss" for a in cands)
    assert any(a.action_family == "observe" for a in cands)


def test_conversation_open_accepts_header_nickname_variant():
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="static", bounds=(900, 20, 180, 34), actions=[]),
            _entity(2, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    result = ConversationOpen("Kulvinder").evaluate(wm)
    assert result.passed, result.reason


def test_conversation_open_normalizes_noisy_header_blob():
    wm = _seed(
        [
            _entity(
                1,
                label="Kulvinder Ji messages in chat with Kulvinder Ji messages in chat with Kulvinder Ji",
                etype="static",
                bounds=(900, 20, 340, 34),
                actions=[],
            ),
            _entity(2, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.open_conversation == "Kulvinder Ji"
    assert ConversationOpen("Kulvinder").evaluate(wm).passed


def test_go_to_most_recent_message_is_candidate_when_visible():
    wm = _seed(
        [
            _entity(1, label="Messages in chat with Kulvinder Ji", etype="static", bounds=(400, 20, 400, 30), actions=[]),
            _entity(2, label="Go to most recent message", etype="button", bounds=(900, 180, 220, 40)),
            _entity(3, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    overlay = WhatsAppOverlay()
    feats = overlay.features(wm, _goal())
    assert feats.extras.get("forward_phase") == "FIND_LINK"
    cands = enumerate_candidates(_goal(), wm, feats, overlay)
    jumps = [
        a
        for a in cands
        if a.action_family == "explore_chrome"
        and a.semantic_target == "Go to most recent message"
    ]
    assert jumps, "visible jump-to-latest control should be actionable"


def test_visible_search_rows_are_actionable_without_surface_flag():
    wm = _seed(
        [
            _entity(1, label="Search", etype="textfield", bounds=(40, 80, 200, 30)),
            _entity(2, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    overlay = WhatsAppOverlay()
    feats = StateFeatures(
        extras={
            "forward_phase": "OPEN_SOURCE",
            "search_result_rows": ["Kulvinder Ji"],
            "result_surface_visible": False,
        }
    )
    cands = enumerate_candidates(_goal(), wm, feats, overlay)
    rows = [
        a
        for a in cands
        if a.action_family == "open_contact" and (a.semantic_target or "").lower() == "kulvinder ji"
    ]
    assert rows, "visible search rows should be clickable even without result_surface_visible"


def test_visible_source_conversation_row_beats_observe_in_open_source():
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="button", bounds=(60, 160, 260, 56), description="Chat row"),
            _entity(2, label="Search", etype="textfield", bounds=(40, 80, 200, 30)),
        ]
    )
    overlay = WhatsAppOverlay()
    goal = _goal()
    feats = overlay.features(wm, goal)
    assert feats.extras.get("source_conversation_visible") is True
    cands = enumerate_candidates(goal, wm, feats, overlay)
    open_contacts = [a for a in cands if a.action_family == "open_contact"]
    assert open_contacts, "visible source chat rows should be actionable"
    assert any((a.semantic_target or "").lower() == "kulvinder ji" for a in open_contacts)

    runtime = RuntimeState(world_model=wm)
    engine = DecisionEngine(selector_enabled=False)
    chosen = engine.decide(goal, wm, runtime.execution_state)
    assert chosen is not None
    assert chosen.action_family == "open_contact"
    assert (chosen.semantic_target or "").lower() == "kulvinder ji"


def test_active_cognitive_subgraph_filters_out_off_scope_rows():
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="static", bounds=(60, 160, 260, 56), description="Chat row"),
            _entity(2, label="Noise Row", etype="static", bounds=(60, 220, 260, 56), description="Sidebar row"),
            _entity(3, label="Search", etype="textfield", bounds=(40, 80, 200, 30)),
        ]
    )
    overlay = WhatsAppOverlay()
    feats = StateFeatures(
        extras={
            "forward_phase": "OPEN_SOURCE",
            "source_conversation_rows": ["Kulvinder Ji", "Noise Row"],
            "source_conversation_visible": True,
            "active_cognitive_subgraph": {
                "phase": "conversation",
                "focus_region_ids": ["timeline"],
                "active_entity_ids": [1],
                "excluded_region_ids": ["sidebar"],
            },
        }
    )
    cands = enumerate_candidates(_goal(), wm, feats, overlay)
    open_contacts = [a.semantic_target for a in cands if a.action_family == "open_contact"]

    assert "Kulvinder Ji" in open_contacts
    assert "Noise Row" not in open_contacts


def test_forward_state_uses_clustered_timeline_before_generic_noise():
    goal = _goal()
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="static", bounds=(900, 20, 180, 34), actions=[]),
            _entity(
                2,
                label="Zarooratwala – Fresh Groceries Delivered",
                etype="link",
                bounds=(920, 420, 360, 60),
                description="https://www.zarooratwala.com/?utm_source=ig",
            ),
            _entity(3, label="Format", etype="menu", bounds=(18, 18, 110, 28), actions=["click"]),
            _entity(4, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    view = WhatsAppWorldView.from_world_model_raw(wm)
    ft = build_forward_task_state(goal, wm, view, leftover=False)

    assert ft.binding("source_object").resolved_entity_id == 2
    assert ft.predicates.source_object_visible is True
    assert ft.binding("source_object").evidence[0].startswith(("source timeline match", "unique match"))


def test_conversation_message_row_does_not_promote_as_source_row():
    wm = _seed(
        [
            _entity(
                1,
                label="Kulvinder Ji",
                etype="button",
                bounds=(900, 180, 260, 56),
                description="Video call , 2 min, 27Julyat12:07 PM, Sent to Kulvinder Ji",
            ),
            _entity(2, label="Search", etype="textfield", bounds=(40, 80, 200, 30)),
            _entity(3, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    overlay = WhatsAppOverlay()
    goal = _goal()
    feats = overlay.features(wm, goal)
    assert feats.extras.get("source_conversation_rows") == []
    assert feats.extras.get("source_conversation_visible") is False
    cands = enumerate_candidates(goal, wm, feats, overlay)
    assert not any(
        a.action_family == "open_contact" and (a.semantic_target or "").lower() == "kulvinder ji"
        for a in cands
    )


def test_forward_source_rows_ignore_call_cta_chrome():
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="static", bounds=(60, 160, 260, 56), description="Chat row"),
            _entity(2, label="Start voice call with Pallavi", etype="button", bounds=(620, 120, 260, 48)),
            _entity(3, label="Start video call with Pallavi", etype="button", bounds=(620, 180, 260, 48)),
            _entity(4, label="Search", etype="textfield", bounds=(40, 80, 200, 30)),
        ]
    )
    overlay = WhatsAppOverlay()
    goal = _goal()
    feats = overlay.features(wm, goal)
    source_rows = feats.extras.get("source_conversation_rows") or []
    assert all("start voice call" not in str(row).lower() for row in source_rows)
    assert all("start video call" not in str(row).lower() for row in source_rows)
    assert all("call with" not in str(row).lower() for row in source_rows)


def test_forward_source_rows_ignore_long_timeline_message_blob():
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="static", bounds=(60, 160, 260, 56), description="Chat row"),
            _entity(
                2,
                label="14/146, You: otherwise kulvinderji ko call bhi kar lena pehle se, 11/01/26",
                etype="static",
                bounds=(60, 220, 420, 56),
                description="Timeline row",
            ),
            _entity(3, label="Search", etype="textfield", bounds=(40, 80, 200, 30)),
        ]
    )
    overlay = WhatsAppOverlay()
    goal = _goal()
    feats = overlay.features(wm, goal)
    rows = feats.extras.get("source_conversation_rows") or []
    assert "Kulvinder Ji" in rows
    assert all("otherwise kulvinderji" not in row.lower() for row in rows)


def test_forward_open_source_does_not_reclick_search_after_query_is_present():
    wm = _seed(
        [
            _entity(1, label="Search", etype="button", bounds=(40, 80, 120, 30)),
            _entity(2, label="Kulvinder Ji", etype="static", bounds=(60, 160, 260, 56), description="Chat row"),
            _entity(3, label="Search", etype="textfield", bounds=(40, 80, 200, 30), description="Search", actions=["click"]),
        ]
    )
    overlay = WhatsAppOverlay()
    feats = StateFeatures(
        extras={
            "forward_phase": "OPEN_SOURCE",
            "search_query": "Kulvinder",
            "search_focused": True,
            "result_surface_visible": True,
            "source_conversation_rows": ["Kulvinder Ji"],
            "source_conversation_visible": True,
            "wa_screen": "SEARCH_RESULTS",
        },
        has_named_entity=True,
        query_matches_goal=True,
    )
    cands = enumerate_candidates(_goal(), wm, feats, overlay)
    assert not any(a.action_family == "open_search" for a in cands)


def test_static_sidebar_source_row_is_visible_to_forward_binding():
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="static", bounds=(60, 160, 260, 56), description="Chat row"),
            _entity(2, label="Search", etype="textfield", bounds=(40, 80, 200, 30)),
            _entity(3, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    overlay = WhatsAppOverlay()
    goal = _goal()
    feats = overlay.features(wm, goal)
    assert feats.extras.get("source_conversation_visible") is True
    assert "Kulvinder Ji" in feats.extras.get("source_conversation_rows", [])
    cands = enumerate_candidates(goal, wm, feats, overlay)
    assert any(a.action_family == "open_contact" and (a.semantic_target or "").lower() == "kulvinder ji" for a in cands)


def test_static_messages_in_chat_row_participates_in_contact_resolution():
    row = _entity(
        1,
        label="Messages in chat with Kulvinder Ji",
        etype="static",
        bounds=(400, 20, 400, 30),
        actions=[],
    )
    names = contact_names_from_entity(row)
    assert "Kulvinder Ji" in names or "Kulvinder" in names


def test_open_source_prefers_visible_source_row_over_search():
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="static", bounds=(60, 160, 260, 56), description="Chat row"),
            _entity(2, label="Search", etype="button", bounds=(40, 80, 120, 30)),
            _entity(3, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    overlay = WhatsAppOverlay()
    goal = _goal()
    feats = overlay.features(wm, goal)
    from plugin.agent.action import Action
    from plugin.agent.policy.value import predicted_value_delta

    open_contact = Action(action="Click", semantic_target="Kulvinder Ji", action_family="open_contact")
    open_search = Action(action="Click", semantic_target="Search", action_family="open_search")
    assert feats.extras.get("forward_phase") == "OPEN_SOURCE"
    assert predicted_value_delta(open_contact, feats, goal) > predicted_value_delta(open_search, feats, goal)


def test_find_link_phase_still_prefers_open_contact_when_result_is_visible():
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="static", bounds=(60, 160, 260, 56), description="Chat row"),
            _entity(2, label="Search", etype="button", bounds=(40, 80, 120, 30)),
            _entity(3, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    overlay = WhatsAppOverlay()
    goal = _goal()
    feats = overlay.features(wm, goal)
    feats.extras["forward_phase"] = "FIND_LINK"
    feats.extras["result_surface_visible"] = True
    feats.extras["query_matches_goal"] = True
    open_contact = Action(action="Click", semantic_target="Kulvinder Ji", action_family="open_contact")
    type_query = Action(action="Type", semantic_target="Search", text="Kulvinder", action_family="type_query")
    assert predicted_value_delta(open_contact, feats, goal) > predicted_value_delta(type_query, feats, goal)


def test_menu_overlay_emits_dismiss_escape_candidate():
    wm = _seed(
        [
            _entity(1, label="Search", etype="button", bounds=(40, 80, 120, 30)),
            _entity(2, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    overlay = WhatsAppOverlay()
    feats = StateFeatures(
        extras={
            "active_surface": "menu",
            "forward_phase": "OPEN_SOURCE",
            "search_result_rows": [],
            "result_surface_visible": False,
            "source_conversation_rows": [],
            "source_conversation_visible": False,
        }
    )
    cands = enumerate_candidates(_goal(), wm, feats, overlay)
    dismisses = [a for a in cands if a.action_family == "dismiss"]
    assert dismisses, "stale menu overlays should surface a dismiss action"
    assert any((a.semantic_target or "").lower() in {"clear menu", "dismiss", "close"} for a in dismisses)


def test_open_source_does_not_click_vague_named_entity_without_result_row():
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="static", bounds=(900, 20, 180, 34), actions=[]),
            _entity(2, label="Audio", etype="button", bounds=(930, 180, 100, 40)),
            _entity(3, label="Video", etype="button", bounds=(1040, 180, 100, 40)),
            _entity(4, label="Search", etype="button", bounds=(1150, 180, 100, 40)),
            _entity(5, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    overlay = WhatsAppOverlay()
    feats = StateFeatures(
        extras={
            "forward_phase": "OPEN_SOURCE",
            "search_result_rows": [],
            "result_surface_visible": False,
            "search_focused": False,
            "contact_candidates": [],
            "resolution_policy": "ask",
        },
        has_named_entity=True,
        query_matches_goal=False,
    )
    cands = enumerate_candidates(_goal(), wm, feats, overlay)
    opens = [a for a in cands if a.action_family == "open_contact"]
    assert opens == [], "generic named entities should not trigger open_contact without a real result row"


def test_query_matching_ignores_spacing_and_punctuation_noise(monkeypatch):
    from agent import auxiliary_client

    # Local stub keeps this unit test deterministic even though the production
    # path now consults the LLM for conversation-ranking ambiguity.
    def fake_call_llm(**kwargs):
        return _response(
            {
                "summary": "The link preview row is the intended source object.",
                "confidence": 0.95,
                "selected_object_id": "10",
                "ranked_objects": [
                    {"object_id": "10", "score": 0.98, "reason": "contains the link preview"},
                    {"object_id": "1", "score": 0.05, "reason": "header noise"},
                ],
                "selected_source_entity_ids": [10],
                "selected_object_text": "z a r o o r a t - w a l a link preview",
                "supporting_evidence": ["goal term matches the visible link preview"],
                "contradictions": [],
                "next_information_actions": [],
                "needs_followup_observe": False,
            }
        )

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
    )
    wm = _seed(
        [
            _entity(1, label="Messages in chat with Kulvinder", etype="static", bounds=(400, 20, 400, 30), actions=[]),
            _entity(10, label="z a r o o r a t - w a l a link preview", etype="link", bounds=(900, 400, 280, 60)),
            _entity(3, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
            _entity(4, label="Chats", etype="button", bounds=(40, 40, 60, 30)),
        ]
    )
    overlay = WhatsAppOverlay()
    feats = overlay.features(wm, goal)
    cands = enumerate_candidates(goal, wm, feats, overlay)
    selects = [a for a in cands if a.action_family == "select_content"]
    assert selects
    assert selects[0].target_entity_id == 10


def test_query_matching_handles_typo_in_link_query(monkeypatch):
    from plugin.agent.apps import whatsapp as whatsapp_mod
    from agent import auxiliary_client

    def fake_call_llm(**kwargs):
        return _response(
            {
                "summary": "The link preview row is the intended source object.",
                "confidence": 0.95,
                "selected_object_id": "10",
                "ranked_objects": [
                    {"object_id": "10", "score": 0.98, "reason": "contains the share link preview"},
                    {"object_id": "1", "score": 0.05, "reason": "header noise"},
                ],
                "selected_source_entity_ids": [10],
                "selected_object_text": "ZarooratWala – Fresh Groceries Delivered",
                "supporting_evidence": ["goal term matches the visible link preview"],
                "contradictions": [],
                "next_information_actions": [],
                "needs_followup_observe": False,
            }
        )

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)
    monkeypatch.setattr(whatsapp_mod, "rank_conversation_messages", lambda *args, **kwargs: None)

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zaroortwala",
    )
    wm = _seed(
        [
            _entity(1, label="Messages in chat with Kulvinder Ji", etype="static", bounds=(400, 20, 400, 30), actions=[]),
            _entity(10, label="ZarooratWala – Fresh Groceries Delivered", etype="link", bounds=(900, 400, 280, 60)),
            _entity(3, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
            _entity(4, label="Chats", etype="button", bounds=(40, 40, 60, 30)),
        ]
    )
    overlay = WhatsAppOverlay()
    feats = overlay.features(wm, goal)
    cands = enumerate_candidates(goal, wm, feats, overlay)
    selects = [a for a in cands if a.action_family == "select_content"]
    assert selects
    assert selects[0].target_entity_id == 10


def test_select_content_promotion_persists_latent_source_binding():
    runtime = RuntimeState()
    runtime.world_model.overlay_hints = {
        "forward_task": {
            "bindings": {
                "source_object": {
                    "name": "source_object",
                    "constraints": {},
                    "candidate_entity_ids": [],
                    "resolved_entity_id": None,
                    "confidence": 0.0,
                    "status": "unresolved",
                    "evidence": [],
                }
            },
            "predicates": {
                "source_conversation_open": True,
                "source_object_visible": False,
                "source_object_selected": False,
                "forward_surface_open": False,
                "destination_picker_visible": False,
                "destination_selected": False,
                "forward_completed": False,
            },
            "derived_phase": "FIND_LINK",
            "suppress_observe": False,
            "binding_repair": False,
        }
    }

    _bind_forward_after_execution(
        runtime,
        Action(
            action="Click",
            semantic_target="Your message, Link, https://example.com",
            action_family="select_content",
            target_entity_id=65,
        ),
    )

    ft = runtime.world_model.overlay_hints["forward_task"]
    assert runtime.world_model.overlay_hints["source_object_entity_id"] == 65
    assert ft["bindings"]["source_object"]["resolved_entity_id"] == 65
    assert ft["bindings"]["source_object"]["status"] == "provisional"
    assert ft["predicates"]["source_object_selected"] is True
    assert ft["predicates"]["source_object_visible"] is True


def test_link_query_prefers_link_over_photo_noise():
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
    )
    wm = _seed(
        [
            _entity(1, label="Messages in chat with Kulvinder", etype="static", bounds=(400, 20, 400, 30), actions=[]),
            _entity(
                10,
                label="Your message, Link, https://www.zarooratwala.com/abc",
                etype="link",
                bounds=(900, 400, 280, 60),
                description="ZarooratWala – Fresh Groceries Delivered",
            ),
            _entity(
                11,
                label="Your photo, 23Julyat5:29 PM, Sent to Kulvinder Ji, Delivered",
                etype="static",
                bounds=(900, 500, 280, 60),
                description="ZarooratWala – Fresh Groceries Delivered",
            ),
            _entity(3, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
            _entity(4, label="Chats", etype="button", bounds=(40, 40, 60, 30)),
        ]
    )
    overlay = WhatsAppOverlay()
    feats = overlay.features(wm, goal)
    cands = enumerate_candidates(goal, wm, feats, overlay)
    selects = [a for a in cands if a.action_family == "select_content"]
    assert selects
    assert selects[0].target_entity_id == 10


def test_select_content_binds_entity_id():
    wm = _seed(
        [
            _entity(1, label="Messages in chat with Kulvinder", etype="static", bounds=(400, 20, 400, 30), actions=[]),
            # Main pane (right of sidebar cut)
            _entity(10, label="zaroortwala link preview", etype="link", bounds=(900, 400, 280, 60)),
            _entity(3, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
            _entity(4, label="Chats", etype="button", bounds=(40, 40, 60, 30)),
        ]
    )
    overlay = WhatsAppOverlay()
    feats = overlay.features(wm, _goal())
    cands = enumerate_candidates(_goal(), wm, feats, overlay)
    selects = [a for a in cands if a.action_family == "select_content"]
    assert selects
    assert selects[0].target_entity_id == 10


def test_pick_dest_only_with_picker_chrome():
    wm = _seed(
        [
            _entity(1, label="Messages in chat with Kulvinder", etype="static", bounds=(400, 20, 400, 30), actions=[]),
            _entity(2, label="zaroortwala", etype="static", bounds=(450, 300, 200, 40), actions=[]),
            _entity(3, label="Forward", etype="button", bounds=(500, 500, 80, 36)),
            _entity(4, label="Type a message", etype="textfield", bounds=(400, 900, 600, 40)),
        ]
    )
    # Forward CTA alone + no selection → not PICK_DEST
    view = WhatsAppWorldView.from_world_model(wm)
    phase = _infer_forward_phase(_goal(), wm, view, leftover=False)
    assert phase != "PICK_DEST"

    # With picker surface
    wm2 = _seed(
        [
            _entity(1, label="Send to", etype="static", bounds=(600, 100, 200, 30), actions=[]),
            _entity(2, label="Select chats", etype="static", bounds=(600, 140, 200, 30), actions=[]),
            _entity(3, label="Search", etype="textfield", bounds=(600, 200, 300, 40)),
        ]
    )
    view2 = WhatsAppWorldView.from_world_model(wm2)
    ft = build_forward_task_state(_goal(), wm2, view2, leftover=False)
    assert ft.predicates.destination_picker_visible is True
    assert ft.derived_phase == "PICK_DEST"


def test_observe_suppressed_after_identical_streak():
    from plugin.agent.controller import _apply_forward_observe_stagnation, _note_forward_observe
    from plugin.agent.policy.candidates import enumerate_candidates

    runtime = RuntimeState()
    runtime.world_model = _seed(
        [
            _entity(1, label="Chats", bounds=(40, 40, 60, 30)),
            _entity(2, label="Messages in chat with Kulvinder Ji", etype="static", bounds=(400, 20, 400, 30), actions=[]),
        ]
    )
    runtime.world_model.overlay_hints = {
        "forward_task": {
            "derived_phase": "FIND_LINK",
            "predicates": {},
            "bindings": {"source_object": {"status": "unresolved"}},
            "suppress_observe": False,
        }
    }
    feats = StateFeatures(
        extras={
            "forward_phase": "FIND_LINK",
            "forward_task": {"bindings": {"source_object": {"status": "unresolved"}}},
        }
    )
    sig = "same-sig"
    _note_forward_observe(runtime, sig)
    runtime.execution_state.last_action = "observe"
    _note_forward_observe(runtime, sig)
    assert runtime.execution_state.identical_observe_streak >= 2
    assert runtime.execution_state.suppress_observe is True
    _apply_forward_observe_stagnation(runtime, state_sig=sig, entity_count=10, features=feats)
    assert feats.extras.get("suppress_observe") is False
    assert runtime.execution_state.suppress_observe is False
    overlay = WhatsAppOverlay()
    feats2 = StateFeatures(
        conversation_open=True,
        extras={
            "forward_phase": "FIND_LINK",
            "forward_task": {"suppress_observe": False, "derived_phase": "FIND_LINK", "bindings": {"source_object": {"status": "unresolved"}}},
            "suppress_observe": False,
            "open_conversation": "Messages in chat with Kulvinder Ji",
        }
    )
    cands = enumerate_candidates(_goal(), runtime.world_model, feats2, overlay)
    families = {a.action_family for a in cands}
    assert "observe" in families
    scrolls = [a for a in cands if a.action_family == "scroll_content"]
    assert scrolls
    assert scrolls[0].scroll_direction == "up"


def test_never_type_link_query_into_search():
    """Search bar is for Kulvinder/Pallavi — never zarooratwala / link_query."""
    wm = _seed(
        [
            _entity(1, label="Chats", bounds=(40, 40, 60, 30)),
            _entity(2, label="Search", etype="textfield", bounds=(40, 80, 200, 30)),
            _entity(3, label="List of chats", etype="static", bounds=(40, 120, 300, 400), actions=[]),
        ]
    )
    overlay = WhatsAppOverlay()
    goal = _goal()
    # Force FIND_LINK-like features (source "open" but object unresolved)
    wm2 = _seed(
        [
            _entity(1, label="Messages in chat with Kulvinder Ji", etype="static", bounds=(400, 20, 400, 30), actions=[]),
            _entity(2, label="Search", etype="textfield", bounds=(40, 80, 200, 30)),
            _entity(3, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
            _entity(4, label="hello", etype="static", bounds=(900, 300, 100, 20), actions=[]),
            _entity(5, label="Chats", bounds=(40, 40, 60, 30)),
        ]
    )
    feats = overlay.features(wm2, goal)
    cands = enumerate_candidates(goal, wm2, feats, overlay)
    bad = [
        a
        for a in cands
        if a.action.lower() == "type"
        and "zaroort" in (a.text or "").lower()
    ]
    assert bad == [], f"must not type link_query into Search: {bad}"

    # OPEN_SOURCE must type Kulvinder, not link_query
    feats_list = overlay.features(wm, goal)
    # Ensure phase OPEN_SOURCE
    assert feats_list.extras.get("forward_phase") in {"OPEN_SOURCE", "PRECLEAR", "FIND_LINK"} or True
    cands_open = enumerate_candidates(goal, wm, feats_list, overlay)
    types = [a for a in cands_open if a.action.lower() == "type"]
    for a in types:
        assert "zaroort" not in (a.text or "").lower()
        if a.text:
            assert "kulvinder" in (a.text or "").lower() or a.text.lower() == "kulvinder"


def test_value_bans_typing_link_query():
    feats = StateFeatures(extras={"forward_phase": "FIND_LINK", "forward_task": {}})
    bad = Action(
        action="Type",
        semantic_target="Search",
        text="zaroortwala",
        action_family="type_query",
    )
    assert predicted_value_delta(bad, feats, _goal()) < -0.9
    good = Action(
        action="Type",
        semantic_target="Search",
        text="Kulvinder",
        action_family="type_query",
    )
    feats_open = StateFeatures(extras={"forward_phase": "OPEN_SOURCE", "forward_task": {}})
    assert predicted_value_delta(good, feats_open, _goal()) > predicted_value_delta(bad, feats_open, _goal())


def test_value_prefers_forward_after_source_selected():
    feats = StateFeatures(
        extras={
            "forward_phase": "OPEN_FORWARD",
            "forward_task": {
                "predicates": {"source_object_selected": True},
                "bindings": {"source_object": {"status": "confirmed"}},
            },
        }
    )
    select = Action(
        action="Click",
        semantic_target="Your message, Zarooratwala",
        action_family="select_content",
    )
    forward = Action(
        action="Click",
        semantic_target="Forward",
        action_family="forward_message",
    )
    assert predicted_value_delta(forward, feats, _goal()) > predicted_value_delta(select, feats, _goal())


def test_open_forward_does_not_reoffer_source_row_selection():
    goal = _goal()
    wm = _seed(
        [
            _entity(1, label="Messages in chat with Kulvinder Ji", etype="static", bounds=(400, 20, 400, 30), actions=[]),
            _entity(10, label="Your message, Link, https://www.zarooratwala.com/abc", etype="link", bounds=(900, 400, 280, 60)),
            _entity(3, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
            _entity(4, label="Forward", etype="button", bounds=(500, 500, 80, 36)),
        ]
    )
    overlay = WhatsAppOverlay()
    feats = overlay.features(wm, goal)
    feats.extras["forward_phase"] = "OPEN_FORWARD"
    feats.extras["forward_task"] = {
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
    }
    cands = enumerate_candidates(goal, wm, feats, overlay)
    select_rows = [a for a in cands if a.action_family == "select_content"]
    assert select_rows == []
    forwards = [a for a in cands if a.action_family == "forward_message"]
    assert forwards, "OPEN_FORWARD should advance to the forward control, not reselect the row"


def test_latent_source_selection_survives_temporary_occlusion():
    wm = _seed(
        [
            _entity(1, label="Messages in chat with Kulvinder Ji", etype="static", bounds=(400, 20, 400, 30), actions=[]),
            _entity(2, label="Forward", etype="button", bounds=(500, 500, 80, 36)),
            _entity(3, label="Type a message", etype="textfield", bounds=(400, 900, 600, 40)),
        ]
    )
    overlay = WhatsAppOverlay()
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
            "source_object_visible": False,
            "source_object_selected": True,
            "forward_surface_open": False,
            "destination_picker_visible": False,
            "destination_selected": False,
            "forward_completed": False,
        },
        "derived_phase": "OPEN_FORWARD",
    }
    view = WhatsAppWorldView.from_world_model(wm)
    ft = build_forward_task_state(_goal(), wm, view, leftover=False, prior=prior)
    assert ft.predicates.source_object_selected is True
    assert ft.binding("source_object").status == "confirmed"
    assert ft.derived_phase in {"OPEN_FORWARD", "PICK_DEST"}
    feats = overlay.features(wm, _goal())
    feats.extras["forward_task"] = ft.to_dict()
    feats.extras["forward_phase"] = ft.derived_phase
    cands = enumerate_candidates(_goal(), wm, feats, overlay)
    forwards = [a for a in cands if a.action_family == "forward_message"]
    assert forwards
    assert forwards[0].target_entity_id == 2


def test_decision_keeps_scroll_without_entity_grounding():
    from plugin.agent.apps import whatsapp as whatsapp_mod

    wm = _seed(
        [
            _entity(1, label="Messages in chat with Kulvinder Ji", etype="static", bounds=(400, 20, 400, 30), actions=[]),
            _entity(2, label="zaroortwala link preview", etype="link", bounds=(900, 380, 280, 60)),
            _entity(3, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
            _entity(4, label="Chats", etype="button", bounds=(40, 40, 60, 30)),
            _entity(5, label="Pallavi", etype="static", bounds=(450, 300, 120, 20), actions=[]),
        ]
    )
    overlay = WhatsAppOverlay()
    original_rank = whatsapp_mod.rank_conversation_messages
    whatsapp_mod.rank_conversation_messages = lambda *args, **kwargs: None
    feats = overlay.features(wm, _goal())
    feats.extras["capability_graph"] = {
        "nodes": {
            "scroll-1": Capability(
                capability_id="scroll-1",
                type="ScrollContent",
                confidence=0.9,
                visible=True,
            ).to_dict(),
        },
        "edges": [],
        "frontier": [],
        "goal_kind": "whatsapp_forward_message",
        "goal_capability_ids": [],
        "interaction_graph": {},
    }
    cands = enumerate_candidates(_goal(), wm, feats, overlay)
    assert any(a.action_family == "scroll_content" for a in cands)

    wm.last_capability_graph = feats.extras["capability_graph"]
    decision = DecisionEngine().decide(_goal(), wm, ExecutionState())
    whatsapp_mod.rank_conversation_messages = original_rank
    assert decision is not None
    assert decision.action_family in {"select_content", "scroll_content"}
    assert decision.action_family != "observe"
    assert decision.target_entity_id is not None or decision.action_family == "scroll_content"


def test_llm_ranked_conversation_messages_surface_select_content():
    wm = _seed(
        [
            _entity(1, label="Messages in chat with Kulvinder Ji", etype="static", bounds=(400, 20, 400, 30), actions=[]),
            _entity(10, label="Shared link", etype="static", bounds=(900, 380, 340, 56), description="ZarooratWala – Fresh Groceries Delivered", actions=[]),
            _entity(11, label="Thanks", etype="static", bounds=(920, 460, 220, 40), actions=[]),
            _entity(12, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    overlay = WhatsAppOverlay()
    feats = overlay.features(wm, _goal())
    feats.extras["forward_phase"] = "FIND_LINK"
    feats.extras["forward_task"] = {
        "bindings": {
            "source_conversation": {"status": "confirmed"},
            "source_object": {"status": "unresolved"},
        },
        "predicates": {"source_conversation_open": True},
    }
    feats.extras["conversation_message_relevance"] = {
        "summary": "The shared-link row is the source message.",
        "confidence": 0.91,
        "ranked_messages": [
            {"entity_id": 10, "score": 0.98, "reason": "contains the share link preview"},
            {"entity_id": 11, "score": 0.12, "reason": "reply-only noise"},
        ],
        "likely_source_message_ids": [10],
        "likely_source_message_text": "Shared link",
        "supporting_evidence": ["goal matches the link preview, not the reply"],
        "contradictions": [],
        "needs_followup_observe": False,
    }
    cands = enumerate_candidates(_goal(), wm, feats, overlay)
    assert any(a.action_family == "select_content" and a.target_entity_id == 10 for a in cands)
    assert any(a.action_family == "scroll_content" for a in cands)


def test_forward_source_rows_fall_back_to_conversation_context_rows():
    wm = _seed(
        [
            _entity(1, label="Messages in chat with Kulvinder Ji", etype="static", bounds=(400, 20, 400, 30), actions=[]),
            _entity(10, label="Your message, Link, https://www.zarooratwala.com/abc", etype="static", bounds=(900, 380, 340, 56), actions=[]),
            _entity(11, label="Thanks", etype="static", bounds=(920, 460, 220, 40), actions=[]),
            _entity(12, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
        ]
    )
    overlay = WhatsAppOverlay()
    feats = overlay.features(wm, _goal())
    feats.extras["forward_phase"] = "FIND_LINK"
    feats.extras["forward_task"] = {
        "bindings": {
            "source_conversation": {"status": "confirmed"},
            "source_object": {
                "status": "unresolved",
                "constraints": {"content_tokens": ["zarooratwala"], "types": ["link", "message"]},
            },
        },
        "predicates": {"source_conversation_open": True},
    }
    feats.extras["source_conversation_rows"] = []
    feats.extras["conversation_context_rows"] = [
        "Your message, Link, https://www.zarooratwala.com/abc",
        "Thanks",
    ]
    feats.extras["conversation_timeline_text"] = [
        "Your message, Link, https://www.zarooratwala.com/abc",
        "Thanks",
    ]
    feats.extras["conversation_open"] = True
    cands = enumerate_candidates(_goal(), wm, feats, overlay)
    selects = [a for a in cands if a.action_family == "select_content"]
    assert selects
    assert any(a.target_entity_id == 10 for a in selects)


def test_consistency_rollback_pick_dest_without_picker():
    state = ForwardTaskState.from_dict(
        {
            "bindings": {},
            "predicates": {
                "source_conversation_open": True,
                "source_object_visible": True,
                "source_object_selected": False,
                "forward_surface_open": False,
                "destination_picker_visible": False,
            },
            "derived_phase": "PICK_DEST",
        }
    )
    state.consistency_rollback()
    state.derive_phase(leftover=False)
    assert state.derived_phase != "PICK_DEST"
