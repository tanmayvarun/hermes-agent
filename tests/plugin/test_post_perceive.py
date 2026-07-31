"""Post-action perception gate + premature hyp-advance guards."""

from __future__ import annotations

import pytest

from plugin.agent.action import Action
from plugin.agent.controller import _maybe_advance_search_hypothesis
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import RuntimeState
from plugin.agent.perception_cycle import PerceptionSnapshot
from plugin.agent.transition.post_perceive import (
    assess_post_action_perception,
    feature_get,
    settled_empty_search_results,
)


def test_feature_get_reads_nested_extras():
    feats = StateFeatures(
        query_matches_goal=True,
        screen_bucket="search",
        extras={
            "resolution_policy": "ask",
            "resolution_confidence": 0.0,
            "result_surface_visible": True,
            "search_result_rows": ["Now…"],
            "contact_candidates": [{"name": "Now…", "confidence": 0.91}],
        },
    ).to_dict()
    assert feature_get(feats, "result_surface_visible") is True
    assert feature_get(feats, "resolution_policy") == "ask"
    assert feature_get(feats, "contact_candidates")[0]["name"] == "Now…"
    assert feature_get(feats, "query_matches_goal") is True


def test_nested_extras_shape_blocks_empty_advance():
    runtime = RuntimeState()
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    after_features = StateFeatures(
        query_matches_goal=True,
        screen_bucket="search",
        extras={
            "resolution_policy": "ask",
            "resolution_confidence": 0.0,
            "result_surface_visible": True,
            "search_result_rows": ["Now…"],
            "contact_candidates": [{"name": "Now…", "confidence": 0.91}],
            "search_query": "Now",
        },
    ).to_dict()
    # Even with perception_settled, results present → no advance
    ok, reason = settled_empty_search_results(
        view={"search_query": "Now", "screen": "SEARCH_RESULTS"},
        features=after_features,
        perception_settled=True,
    )
    assert ok is False
    assert reason == "results_present"

    advanced = _maybe_advance_search_hypothesis(
        runtime,
        goal,
        decision=Action(action="Type", semantic_target="Search", text="Now", action_family="type_query"),
        after_view={"search_query": "Now"},
        after_features=after_features,
        log=None,
        iteration=1,
        perception_settled=True,
    )
    assert advanced is False
    assert runtime.execution_state.search_hypothesis_index == 0


def test_null_resolution_is_perception_incomplete_not_empty():
    feats = {
        "query_matches_goal": True,
        "screen_bucket": "search",
        "extras": {
            "resolution_policy": None,
            "resolution_confidence": None,
            "search_query": "Now",
        },
    }
    ok, reason = settled_empty_search_results(
        view={"search_query": "Now"},
        features=feats,
        perception_settled=True,
    )
    assert ok is False
    assert reason == "perception_incomplete"

    assessment = assess_post_action_perception(
        action_family="type_query",
        view={"search_query": "Now"},
        features=feats,
        patch=None,
    )
    assert assessment.settled is False
    assert "resolution_unset" in assessment.failure_modes


def test_type_query_never_advances_on_same_transition():
    runtime = RuntimeState()
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    feats = {
        "query_matches_goal": True,
        "extras": {
            "resolution_policy": "ask",
            "resolution_confidence": 0.0,
            "contact_candidates": [],
            "search_result_rows": [],
            "search_query": "Now",
        },
    }
    advanced = _maybe_advance_search_hypothesis(
        runtime,
        goal,
        decision=Action(action="Type", semantic_target="Search", text="Now", action_family="type_query"),
        after_view={"search_query": "Now"},
        after_features=feats,
        log=None,
        iteration=1,
        perception_settled=True,
    )
    assert advanced is False


def test_settled_empty_allows_advance_via_observe():
    runtime = RuntimeState()
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    feats = {
        "query_matches_goal": True,
        "extras": {
            "resolution_policy": "ask",
            "resolution_confidence": 0.0,
            "contact_candidates": [],
            "search_result_rows": [],
            "result_surface_visible": False,
            "search_query": "Now",
        },
    }
    advanced = _maybe_advance_search_hypothesis(
        runtime,
        goal,
        decision=Action(action="Observe", action_family="observe"),
        after_view={"search_query": "Now"},
        after_features=feats,
        log=None,
        iteration=2,
        perception_settled=True,
    )
    assert advanced is True
    assert runtime.execution_state.search_hypothesis_index == 1


def test_auto_candidate_beats_next_hyp_type():
    from plugin.agent.decision import DecisionEngine
    from plugin.worldmodel.entities.entity import Entity
    from plugin.worldmodel.model import WorldModel

    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    wm = WorldModel()
    wm.active_app = "WhatsApp"
    ents = [
        Entity(
            id=1,
            entity_type="textfield",
            semantic_role="Search",
            label="Search",
            role="AXTextField",
            actions=["type"],
            attributes={"value": "Now", "focused": True},
            visible=True,
        ),
        Entity(
            id=2,
            entity_type="button",
            semantic_role="Now…",
            label="Now…",
            role="AXButton",
            actions=["click"],
            attributes={"description": "Now…", "semantic_type": "group"},
            visible=True,
        ),
    ]
    wm.entities = {e.id: e for e in ents}
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = 3
    wm.overlay_hints["search_query"] = "Now"

    ex = RuntimeState().execution_state
    ex.search_hypothesis_index = 1  # wrongly advanced already
    decision = DecisionEngine().decide(goal, wm, ex)
    assert decision is not None
    assert decision.action_family == "open_contact"
    assert "now" in (decision.semantic_target or "").lower()


def test_refresh_perception_is_reusable_observe_fuse_update():
    from plugin.agent.perception_cycle import ensure_settled_perception, refresh_perception
    from plugin.perception.observation import AxNode, Observation

    runtime = RuntimeState()
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    calls = {"n": 0}

    def observe():
        calls["n"] += 1
        return Observation(
            timestamp=0.0,
            app_name="WhatsApp",
            window_name="WhatsApp",
            nodes=[
                AxNode(role="AXTextField", name="Search", value="Now", attributes={"focused": True}),
                AxNode(role="AXButton", name="Now…", description="Now…"),
            ],
            source="test",
        )

    snap = refresh_perception(runtime, goal, observe=observe, action_label="unit_refresh")
    assert calls["n"] == 1
    assert snap.patch is not None
    extras = snap.features.get("extras") or {}
    assert snap.view.get("search_query") or extras.get("search_query")
    assert len(runtime.patches) >= 1

    settled = ensure_settled_perception(
        runtime,
        goal,
        observe=observe,
        action_family="type_query",
        settle_s=0.0,
        wait_fn=lambda *_a, **_k: None,
        initial=snap,
    )
    assert settled.assessment is not None
    assert calls["n"] >= 1


def test_refresh_perception_propagates_provider_exhaustion(monkeypatch):
    from agent.auxiliary_client import LLMProviderExhaustedError
    from plugin.agent.perception_cycle import refresh_perception

    runtime = RuntimeState()
    goal = Goal(kind="whatsapp_voice_call", contact="now group")

    def fake_synthesize_perception(*args, **kwargs):
        raise LLMProviderExhaustedError("Auxiliary perception: exhausted")

    monkeypatch.setattr("plugin.agent.perception_cycle.synthesize_perception", fake_synthesize_perception)

    def observe():
        from plugin.perception.observation import Observation

        return Observation(timestamp=0.0, app_name="WhatsApp", window_name="WhatsApp", nodes=[], source="test")

    with pytest.raises(LLMProviderExhaustedError, match="exhausted"):
        refresh_perception(runtime, goal, observe=observe, action_label="unit_refresh")


def test_settled_perception_can_switch_to_fallback_observer_on_retry():
    from plugin.agent.perception_cycle import ensure_settled_perception
    from plugin.perception.observation import AxNode, Observation

    runtime = RuntimeState()
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    primary_calls = {"n": 0}
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("plugin.agent.perception_cycle.synthesize_perception", lambda *args, **kwargs: None)

    def observe():
        primary_calls["n"] += 1
        return Observation(
            timestamp=0.0,
            app_name="WhatsApp",
            window_name="WhatsApp",
            nodes=[
                AxNode(role="AXTextField", name="Search", value="Now", attributes={"focused": True}),
                AxNode(role="AXButton", name="Now…", description="Now…"),
            ],
            source="primary",
        )

    initial = PerceptionSnapshot(
        observation=None,
        patch=None,
        view={"search_query": ""},
        features={"needs_reobserve": True, "extras": {"needs_reobserve": True}},
        worldview=0.2,
        action_label="unit_retry",
    )

    settled = ensure_settled_perception(
        runtime,
        goal,
        observe=observe,
        action_family="type_query",
        settle_s=0.0,
        wait_fn=lambda *_a, **_k: None,
        initial=initial,
    )
    assert settled.settled is True
    assert primary_calls["n"] == 1
    monkeypatch.undo()


def test_repeated_identical_perception_stall_is_latched_and_blocks_observe():
    import plugin.agent.perception_cycle as perception_cycle

    from plugin.agent.perception_cycle import ensure_settled_perception
    from plugin.agent.action import Action
    from plugin.perception.observation import AxNode, Observation

    runtime = RuntimeState()
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    calls = {"n": 0}
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(perception_cycle, "synthesize_perception", lambda *args, **kwargs: None)

    def observe():
        calls["n"] += 1
        return Observation(
            timestamp=0.0,
            app_name="WhatsApp",
            window_name="WhatsApp",
            nodes=[
                AxNode(role="AXTextField", name="Search", value="", attributes={"focused": True}),
            ],
            source="test",
        )

    initial = ensure_settled_perception(
        runtime,
        goal,
        observe=observe,
        action_family="type_query",
        settle_s=0.0,
        wait_fn=lambda *_a, **_k: None,
        initial=None,
    )
    assert initial.settled is False
    assert runtime.execution_state.perception_cycle_stalled is True
    assert runtime.execution_state.perception_stall_count >= 2
    assert runtime.execution_state.world_exploration_needed is False
    assert runtime.execution_state.is_prohibited(
        Action(action="Observe", action_family="observe", rationale="stall guard")
    )
    assert calls["n"] >= 2
    monkeypatch.undo()
