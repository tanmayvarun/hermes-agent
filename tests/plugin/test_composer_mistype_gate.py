"""Live 181132: do not context-click / type the link query into chat composer."""

from __future__ import annotations

from plugin.agent.capabilities.action_area import validate_actuation_grounding
from plugin.agent.decision_consultation import build_decision_brief, sanitize_decision
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal


def _goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )


def test_reveal_query_echo_in_composer_rejected():
    brief = build_decision_brief(
        _goal(),
        world_document={
            "surface": "conversation",
            "open_conversation": "Pallavi",
            "focused_field_role": "composer",
            "objects": [],
        },
        features=StateFeatures(conversation_open=True, extras={}),
    )
    rejected = sanitize_decision(
        {"capability": "reveal_actions", "target": "zarooratwala lasawel"},
        brief,
    )
    assert not rejected.ok
    assert "composer" in rejected.why.lower() or "locate_content" in rejected.why.lower()


def test_reveal_plain_query_echo_without_url_rejected():
    brief = build_decision_brief(
        _goal(),
        world_document={
            "surface": "conversation",
            "open_conversation": "Pallavi",
            "objects": [],
        },
        features=StateFeatures(conversation_open=True, extras={}),
    )
    rejected = sanitize_decision(
        {"capability": "reveal_actions", "target": "zarooratwala lasawel"},
        brief,
    )
    assert not rejected.ok
    assert "echo" in rejected.why.lower() or "locate_content" in rejected.why.lower()


def test_actuation_refuses_reveal_on_composer_role():
    ok, why = validate_actuation_grounding(
        capability="reveal_actions",
        field_role="composer",
        label="zarooratwala",
        target_kind="",
    )
    assert not ok
    assert "composer" in why
