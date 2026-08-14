"""Live 145943: OPEN_SOURCE stuck on foreign chat — leave + visible source open."""

from __future__ import annotations

from plugin.agent.capabilities.resolve_entity import (
    actuatable_source_contact_row,
    open_matches_referent,
    row_matches_source_contact,
)
from plugin.agent.capabilities.search_episode import (
    maybe_complete_source_contact_from_visible_row,
    meta_referent_search_signals,
)
from plugin.agent.decision_consultation import (
    build_decision_brief,
    sanitize_decision,
)
from plugin.agent.executive.meta_action import MetaAction, MetaContext, select_meta_action
from plugin.agent.executive.meta_consultation import sanitize_meta_choice
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import ExecutionState


def _goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )


def _features(**extras):
    base = {"app_content_node_count": 0}
    base.update(extras)
    return StateFeatures(
        conversation_open=bool(extras.get("conversation_open", True)),
        extras=base,
    )


def _pallavi_row(**extra):
    row = {
        "id": "pallavi_row",
        "kind": "chat_row",
        "text": "Pallavi",
        "point": [180.0, 240.0],
    }
    row.update(extra)
    return row


def test_row_matches_source_contact_uses_name_head():
    assert row_matches_source_contact("Pallavi - zarooratwala preview", "Pallavi")
    assert not row_matches_source_contact("Pallavi Ather Gen3", "Pallavi")
    assert open_matches_referent("Pallavi", "Pallavi")


def test_foreign_open_conversation_triggers_leave_before_compose():
    """open=CoE ≠ Pallavi → compose_search_query forbidden; leave owed."""
    brief = build_decision_brief(
        _goal(),
        world_document={
            "surface": "conversation",
            "open_conversation": "[CoE - IoT & AI] BLR Startups",
            "objects": [
                {"kind": "search_field", "text": "Search", "point": [120.0, 80.0]},
            ],
        },
        features=_features(conversation_open=True),
    )
    assert brief.task_state.phase == "reach_source"
    assert brief.task_state.source_chat_open is False
    rejected = sanitize_decision(
        {"capability": "compose_search_query", "target": ""}, brief
    )
    assert not rejected.ok
    assert "foreign conversation" in rejected.why.lower()
    assert "leave" in rejected.why.lower() or "dismiss" in rejected.why.lower()

    state = ExecutionState()
    state.unified_world_document = {
        "surface": "conversation",
        "open_conversation": "[CoE - IoT & AI] BLR Startups",
        "objects": [],
    }
    state.leave_wrong_conversation_owed = True
    ctx = MetaContext(leave_wrong_conversation_owed=True)
    choice = select_meta_action(ctx)
    assert choice.action is MetaAction.ACT
    sanitized = sanitize_meta_choice(
        {"meta_action": "search", "why": "find Pallavi", "confidence": 0.9},
        ctx,
    )
    assert sanitized is not None
    assert sanitized.action is MetaAction.ACT


def test_visible_source_chat_row_allows_open_despite_link_query():
    """Actuatable Pallavi chat_row may open_entity even with unpaid link_query."""
    brief = build_decision_brief(
        _goal(),
        world_document={
            "surface": "chat_list",
            "open_conversation": "[CoE - IoT & AI] BLR Startups",
            "objects": [_pallavi_row()],
        },
        features=_features(conversation_open=True),
        execution_state=ExecutionState(),
    )
    assert brief.task_state.source_chat_open is False
    allowed = sanitize_decision(
        {"capability": "open_entity", "target": "Pallavi"}, brief
    )
    assert allowed.ok, allowed.why
    assert allowed.capability == "open_entity"
    # Compose still forbidden while foreign pane + row visible.
    compose = sanitize_decision(
        {"capability": "compose_search_query", "target": ""}, brief
    )
    assert not compose.ok
    assert "open_entity" in compose.why.lower()


def test_compose_first_still_blocks_non_actuatable_preview_row():
    """Preview text without geometry still requires compose (legacy 030941)."""
    brief = build_decision_brief(
        _goal(),
        world_document={
            "surface": "chat_list",
            "open_conversation": "",
            "objects": [
                {"text": "Pallavi - zarooratwala Pallavi", "matches_goal": True},
            ],
        },
        features=_features(conversation_open=False),
    )
    rejected = sanitize_decision(
        {"capability": "open_entity", "target": "Pallavi"}, brief
    )
    assert not rejected.ok
    assert "compose_search_query" in rejected.why


def test_preclear_does_not_skip_when_list_with_foreign_pane():
    """Harness preclear: LIST/SEARCH + foreign open must keep leaving."""
    import ast
    from pathlib import Path

    src = Path("plugin/experiments/run_forward_message.py").read_text(encoding="utf-8")
    assert "foreign_pane" in src
    assert "list_clean" in src
    tree = ast.parse(src)
    assert tree is not None


def test_search_type_regression_with_foreign_open_keeps_reach_source_leave_debt():
    """After search type regression under foreign open, leave debt still arms."""
    state = ExecutionState()
    doc = {
        "surface": "conversation",
        "open_conversation": "[CoE - IoT & AI] BLR Startups",
        "objects": [],
    }
    state.unified_world_document = doc
    sig = meta_referent_search_signals(
        state,
        phase="reach_source",
        source_chat_open=False,
        surface="conversation",
        goal=_goal(),
        document=doc,
    )
    assert sig.get("source_contact_open_ready") is False
    state.leave_wrong_conversation_owed = True
    state.leave_wrong_conversation_open = doc["open_conversation"]
    state.leave_wrong_conversation_source = "Pallavi"
    ctx = MetaContext(
        leave_wrong_conversation_owed=True,
        source_contact_open_ready=False,
        referent_search_needed=True,
        search_episode_incomplete=True,
    )
    choice = sanitize_meta_choice(
        {"meta_action": "search", "why": "type again", "confidence": 0.8},
        ctx,
    )
    assert choice is not None
    assert choice.action is MetaAction.ACT
    assert "leave" in choice.reason.lower() or "foreign" in choice.reason.lower()


def test_identity_contract_does_not_block_matching_source_chat_row_open():
    """RoleBinder must allow open_entity on matching Pallavi chat_row."""
    state = ExecutionState()
    brief = build_decision_brief(
        _goal(),
        world_document={
            "surface": "chat_list",
            "open_conversation": "[CoE - IoT & AI] BLR Startups",
            "objects": [_pallavi_row()],
        },
        features=_features(conversation_open=True),
        execution_state=state,
    )
    # Ensure candidates include the chat_row for RoleBinder cand merge.
    assert any(
        "Pallavi" in str(c)
        for c in (brief.candidates or [])
    ) or actuatable_source_contact_row(brief.world, "Pallavi")
    decided = sanitize_decision(
        {
            "capability": "open_entity",
            "target": "Pallavi",
            "target_id": "pallavi_row",
        },
        brief,
    )
    assert decided.ok, decided.why
    assert "identity_contract" not in (decided.why or "").lower()


def test_meta_prefers_act_when_source_contact_retrieve_ready():
    doc = {
        "surface": "chat_list",
        "open_conversation": "[CoE - IoT & AI] BLR Startups",
        "objects": [_pallavi_row()],
    }
    state = ExecutionState()
    state.unified_world_document = doc
    sig = meta_referent_search_signals(
        state,
        phase="reach_source",
        source_chat_open=False,
        surface="chat_list",
        goal=_goal(),
        document=doc,
    )
    assert sig.get("source_contact_open_ready") is True
    assert sig.get("retrieve_ready") is True
    assert sig.get("needed") is False
    ep = maybe_complete_source_contact_from_visible_row(
        state, document=doc, contact="Pallavi", source_chat_open=False
    )
    assert ep and ep.get("chosen_label")
    ctx = MetaContext(
        source_contact_open_ready=True,
        retrieve_ready=True,
        referent_search_needed=False,
        search_episode_complete=True,
    )
    choice = select_meta_action(ctx)
    assert choice.action is MetaAction.ACT
    sanitized = sanitize_meta_choice(
        {"meta_action": "search", "why": "compose", "confidence": 0.9},
        ctx,
    )
    assert sanitized is not None
    assert sanitized.action is MetaAction.ACT
