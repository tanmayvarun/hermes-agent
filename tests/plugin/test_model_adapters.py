from __future__ import annotations

from plugin.agent.action import Action
from plugin.agent.action_models.base import ActionModelRun, ActionProposal
from plugin.agent.action_models.integration import action_prior_bonus, collect_action_prior_runs
from plugin.agent.action_models.registry import clear_action_models, register_action_model
from plugin.agent.decision_selector import build_selector_messages
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.perception.models.base import ScreenElement, ScreenModelRun
from plugin.perception.models.recovery import recover_observation_with_screen_models
from plugin.perception.models.registry import clear_screen_models, register_screen_model
from plugin.perception.observation import Observation
from plugin.worldmodel.model import WorldModel


class _FakeScreenModel:
    model_id = "omniparser_v2"

    def parse(self, screenshot_path: str, *, use_case: str = "") -> ScreenModelRun:
        return ScreenModelRun(
            model_id=self.model_id,
            use_case=use_case,
            elements=[
                ScreenElement(
                    element_id="voice",
                    label="Voice",
                    bbox=(10.0, 20.0, 120.0, 36.0),
                    interactive=True,
                    confidence=0.92,
                    source=self.model_id,
                ),
            ],
        )


class _FakeActionModel:
    model_id = "ui-tars"

    def propose(self, *, goal, world, features, candidates=(), use_case: str = "") -> ActionModelRun:
        return ActionModelRun(
            model_id=self.model_id,
            use_case=use_case,
            proposals=[
                ActionProposal(
                    action_family="start_call",
                    semantic_target="Voice",
                    action="Click",
                    confidence=0.91,
                    risk=0.2,
                    reversible=False,
                    reason="model prior prefers call surface",
                )
            ],
        )


def test_screen_model_recovery_merges_registered_model_output():
    clear_screen_models()
    register_screen_model(_FakeScreenModel())
    obs = Observation(
        timestamp=0.0,
        app_name="WhatsApp",
        window_name="Chat",
        nodes=[],
        screenshot_path="/tmp/fake.png",
        source="fixture",
        coverage=0.0,
    )

    recovered = recover_observation_with_screen_models(obs, use_case="WhatsApp", force=True)

    assert recovered.source == "screen_model:omniparser_v2"
    assert any(node.name == "Voice" for node in recovered.nodes)
    assert recovered.meta["screen_models"]["status"] == "applied"
    clear_screen_models()


def test_action_prior_collection_uses_registry_and_scores_candidates():
    clear_action_models()
    register_action_model(_FakeActionModel())
    goal = Goal(kind="whatsapp_voice_call", contact="Now Group")
    world = WorldModel()
    features = StateFeatures(app="WhatsApp")
    candidates = [Action(action="Click", action_family="start_call", semantic_target="Voice")]

    runs = collect_action_prior_runs(goal, world, features, candidates)

    assert runs and runs[0].model_id == "ui-tars"
    assert runs[0].proposals[0].semantic_target == "Voice"
    assert action_prior_bonus(candidates[0], runs) > 0.0
    clear_action_models()


def test_selector_prompt_includes_action_prior_runs():
    goal = Goal(kind="whatsapp_voice_call", contact="Now Group")
    features = StateFeatures(extras={"goal_hypotheses": goal.intent_hypotheses()})
    messages = build_selector_messages(
        goal,
        WorldModel(),
        features,
        candidates=[],
        action_prior_runs=[{"model_id": "ui-tars", "score": 0.9, "proposals": []}],
    )

    payload = messages[1]["content"]
    assert "action_prior_runs" in payload
    assert "ui-tars" in payload
