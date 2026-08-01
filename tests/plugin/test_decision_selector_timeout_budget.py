from __future__ import annotations

from plugin.agent.action import Action
from plugin.agent.decision_selector import select_action_with_llm
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.worldmodel.model import WorldModel


def test_select_action_with_llm_reports_selector_timeout_from_config(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.config.load_config_readonly",
        lambda: {
            "agent": {
                "decision_selector_timeout_seconds": 11,
            }
        },
    )

    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi")
    world = WorldModel()
    features = StateFeatures(app="WhatsApp", screen_bucket="conversation", conversation_open=True)
    candidates = [
        Action(
            action="Click",
            action_family="open_contact",
            semantic_target="Kulvinder",
            score=0.8,
            target_entity_id=11,
            grounding_confidence=0.9,
        ),
        Action(
            action="Type",
            action_family="type_query",
            semantic_target="Search",
            text="Kulvinder",
            score=0.7,
            target_entity_id=42,
            grounding_confidence=0.8,
        ),
    ]

    def fake_caller(**kwargs):
        assert kwargs["timeout"] == 11
        return '{"choice_id":"c1","confidence":0.91}'

    chosen, trace = select_action_with_llm(
        goal,
        world,
        features,
        candidates,
        caller=fake_caller,
    )

    assert chosen is candidates[0]
    assert trace["timeout_s"] == 11.0
    assert trace["timeout_source"] == "config:decision_selector_timeout_seconds"


def test_select_action_with_llm_returns_grounding_recovery_when_no_grounded_candidates(monkeypatch):
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi")
    world = WorldModel()
    features = StateFeatures(app="WhatsApp", screen_bucket="conversation", conversation_open=True)
    candidates = [
        Action(action="Click", action_family="open_contact", semantic_target="Kulvinder", score=0.8),
        Action(action="Type", action_family="type_query", semantic_target="Search", text="Kulvinder", score=0.7),
    ]

    def fake_caller(**kwargs):
        raise AssertionError("selector LLM should not be called when nothing is grounded")

    chosen, trace = select_action_with_llm(
        goal,
        world,
        features,
        candidates,
        caller=fake_caller,
        grounding_threshold=0.7,
    )

    assert chosen is None
    assert trace["reason"] == "grounding_recovery"
    assert trace["grounded_candidates"] == 0
