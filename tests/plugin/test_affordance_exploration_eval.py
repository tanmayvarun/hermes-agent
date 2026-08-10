"""Zarooratwala affordance exploration evals + brain reperceive resilience."""

from __future__ import annotations

from plugin.agent.brain import barren_frontier_reperceive, request_reperceive
from plugin.agent.decision_consultation import (
    DecisionBrief,
    NavigationInfo,
    TaskState,
)
from plugin.agent.features import StateFeatures
from plugin.evals.affordance_exploration import (
    score_brain_reperceive_resilience,
    summarize_affordance_exploration,
)
from plugin.evals.annotations import annotate, load_overrides
from plugin.evals.corpus import load_fixtures, DEFAULT_CORPUS_DIR


def test_brain_reperceive_metric_passes():
    metric = score_brain_reperceive_resilience()
    assert metric.value == 1.0, metric.examples


def test_barren_conversation_forces_observe_and_reperceive_query():
    brief = DecisionBrief(
        goal={
            "source_conversation": "Pallavi",
            "source_query": "zarooratwala",
            "destination": "Tanmay",
        },
        world={
            "surface": "conversation",
            "open_conversation": "Pallavi",
            "objects": [
                {
                    "id": "m1",
                    "kind": "link",
                    "text": "https://zarooratwala.com/x",
                    "matches_goal": True,
                }
            ],
        },
        task_state=TaskState(
            phase="act_on_content",
            source_chat_open=True,
            content_visible=True,
            open_conversation="Pallavi",
        ),
        navigation=NavigationInfo(surface="conversation"),
        capabilities=["reveal_actions", "observe"],
        affordance_frontier={
            "observed_actions": [{"family": "scroll", "label": "timeline"}],
            "latent_actions": [],
            "probe_actions": [],
        },
    )
    barren, why = barren_frontier_reperceive(brief)
    assert barren
    assert "forward" in why.lower()

    class _State:
        pass

    state = _State()
    features = StateFeatures(app="WhatsApp", extras={})
    request_reperceive(state, features, reason=why, missing=["forward"])
    assert state.last_perception_query["objective"].startswith("expected affordances")
    assert features.extras["reperceive_affordance_gap"]["missing"] == ["forward"]


def test_summarize_over_corpus_smoke():
    fixtures = annotate(load_fixtures(DEFAULT_CORPUS_DIR), overrides=load_overrides())
    report = summarize_affordance_exploration(fixtures)
    assert report["fixtures_scored"] >= 1
    names = {m["name"] for m in report["metrics"]}
    assert "zarooratwala_critical_latent_recall" in names
    assert "brain_reperceive_when_frontier_barren" in names
    # Brain resilience metric is synthetic and should be perfect.
    brain = next(m for m in report["metrics"] if m["name"] == "brain_reperceive_when_frontier_barren")
    assert brain["value"] == 1.0
