"""Deterministic ReferenceInterpreter — typed refs without LLM."""

from __future__ import annotations

from plugin.agent.goal import Goal
from plugin.agent.reference import interpret_reference


def test_now_group_interprets_as_group_named_now():
    ref = interpret_reference("now group")
    assert ref.kind == "group"
    assert ref.name == "Now"
    assert ref.confidence >= 0.8
    assert "Now" in ref.search_hypotheses
    assert any(h.lower() == "now group" for h in ref.search_hypotheses)


def test_plugin_support_is_contact_full_name():
    ref = interpret_reference("plugin support")
    assert ref.kind == "contact"
    assert ref.name.lower() == "plugin support"
    assert "plugin support" in [h.lower() for h in ref.search_hypotheses]


def test_explicit_kind_name_override():
    ref = interpret_reference("now group", kind="group", name="Now")
    assert ref.kind == "group"
    assert ref.name == "Now"
    assert ref.confidence >= 0.9


def test_goal_auto_interprets_contact():
    g = Goal(kind="whatsapp_voice_call", contact="now group")
    assert g.reference is not None
    assert g.reference.kind == "group"
    assert g.search_text(0) == "Now"
    assert "Group" in g.search_text(1) or g.search_text(1).lower() == "now group"


def test_community_pattern():
    ref = interpret_reference("acme community")
    assert ref.kind == "community"
    assert "Acme" in ref.name
