from __future__ import annotations

from plugin.agent.action import Action
from plugin.agent.decision import DecisionEngine
from plugin.agent.decision_selector import build_branch_strategy_messages
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.transition.types import BranchStrategy, ExplorationBranch
from plugin.worldmodel.model import WorldModel


class _Overlay:
    def features(self, world, goal, worldview_score=1.0):
        return StateFeatures(
            app="WhatsApp",
            screen_kind="list",
            screen_bucket="LIST",
            worldview_score=worldview_score,
            mean_belief=0.95,
            extras={},
        )


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
    text = messages[1]["content"]
    assert "branch strategy planner" in text.lower()
    assert "preferred_family" in text
    assert "open source conversation" in text
    assert "do not include the preferred_family or backtrack_family" in text


def test_decision_engine_uses_branch_strategy_selector_on_active_branch(monkeypatch):
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zarooratwala")
    wm = WorldModel()
    wm.active_app = "WhatsApp"
    ex = ExecutionState()
    ex.exploration_branch = ExplorationBranch(active=True, active_surface="search_results", depth=1)

    def fake_get_overlay(app, world):
        return _Overlay()

    def fake_enumerate_candidates(goal, world, features, overlay):
        return [
            Action(action="Click", action_family="open_contact", semantic_target="Kulvinder", score=0.9),
            Action(action="Type", action_family="type_query", semantic_target="Search", text="Kulvinder", score=0.1),
            Action(action="Observe", action_family="observe", score=0.05),
        ]

    captured = {}

    def fake_select_branch_strategy_with_llm(*args, **kwargs):
        captured["task"] = kwargs.get("task")
        return (
            BranchStrategy(
                strategy_id="s1",
                preferred_family="type_query",
                backtrack_family="open_contact",
                avoid_families=["observe"],
                branch_hypothesis="refine search query",
                expected_surface="search_results",
                confidence=0.92,
                reason="move deeper into the source search lane",
            ),
            {
                "task": kwargs.get("task"),
                "confidence": 0.92,
                "strategy": {
                    "preferred_family": "type_query",
                    "backtrack_family": "open_contact",
                },
            },
        )

    monkeypatch.setattr("plugin.agent.decision.get_overlay", fake_get_overlay)
    monkeypatch.setattr("plugin.agent.decision.enumerate_candidates", fake_enumerate_candidates)
    monkeypatch.setattr("plugin.agent.decision.select_branch_strategy_with_llm", fake_select_branch_strategy_with_llm)

    engine = DecisionEngine(selector_enabled=False)
    decision = engine.decide(goal, wm, ex)

    assert captured["task"] == "branch_strategy"
    assert decision is not None
    assert decision.action_family == "type_query"
    assert engine.last_trace is not None
    assert engine.last_trace.branch_strategy is not None
    assert engine.last_trace.branch_strategy["strategy"]["preferred_family"] == "type_query"
    assert engine.last_trace.features["extras"]["branch_edge_commit"]["family"] == "type_query"
