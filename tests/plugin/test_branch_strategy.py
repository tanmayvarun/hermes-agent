from __future__ import annotations

import pytest

from plugin.agent.action import Action
from plugin.agent.decision_selector import build_branch_strategy_messages
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.worldmodel.model import WorldModel


def test_branch_strategy_prompt_includes_branch_state():
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zarooratwala")
    world = WorldModel()
    world.active_app = "WhatsApp"
    messages = build_branch_strategy_messages(
        goal,
        world=world,
        features=StateFeatures(app="WhatsApp", screen_bucket="LIST", extras={}),
        candidates=[("c1", Action(action="Click", action_family="open_contact", semantic_target="Kulvinder"))],
        branch={"active": True, "active_surface": "search_results", "frontier_hypothesis": "open source conversation"},
    )
    # The framing and the output contract are the same on every call, so they
    # ride in the system message where a provider can cache the prefix; only the
    # live branch state belongs in the user message.
    system = messages[0]["content"]
    assert "branch strategy planner" in system.lower()
    assert "preferred_family" in system
    assert "do not include the preferred_family or backtrack_family" in system

    text = messages[1]["content"]
    assert "open source conversation" in text


@pytest.mark.skip(reason="legacy DecisionEngine fallthrough removed")
def test_decision_engine_uses_branch_strategy_selector_on_active_branch(monkeypatch):
    pass
