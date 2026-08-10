"""Surprise → REFLECT → explain → brain."""

from __future__ import annotations

from types import SimpleNamespace

from plugin.agent.brain import apply_surprise_explanation, motor_fingerprint
from plugin.agent.decision_consultation import DecisionOutcome
from plugin.agent.executive.hierarchy import decision_ladder
from plugin.agent.executive.meta_action import (
    REFLECT_EXPLANATION_CONFIDENCE,
    MetaAction,
    MetaContext,
    select_meta_action,
)
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.transition.attribution import parse_motor_landed_point
from plugin.agent.unified_cognition import (
    _reflect_packet,
    build_decision_packet,
    discover_surprise_hypotheses,
    explanation_is_authoritative,
    normalize_surprise_explanation,
)


def test_select_and_ladder_surprise_is_reflect():
    ctx = MetaContext(
        awaiting_verification=True,
        last_action_surprised=True,
        has_grounded_action=True,
    )
    assert select_meta_action(ctx).action is MetaAction.PERCEIVE
    assert decision_ladder(ctx).action is MetaAction.PERCEIVE


def test_reflect_observe_wanted():
    choice = select_meta_action(
        MetaContext(awaiting_verification=True, last_action_surprised=True)
    )
    assert choice.observe_wanted is True
    assert choice.suppress_observe is False


def test_normalize_and_confidence_gate():
    weak = normalize_surprise_explanation(
        {"cause": "wrong_target", "confidence": 0.5, "recommended_next": "act"}
    )
    assert weak["cause"] == "wrong_target"
    assert not explanation_is_authoritative(weak)
    strong = normalize_surprise_explanation(
        {
            "cause": "stale_geometry",
            "confidence": REFLECT_EXPLANATION_CONFIDENCE,
            "recommended_next": "act",
            "detail": "point missed the link",
        }
    )
    assert explanation_is_authoritative(strong)


def test_parse_motor_landed_point():
    assert parse_motor_landed_point("AXPress center=(199.5, 242.35)") == [199.5, 242.35]
    assert parse_motor_landed_point("no center here") is None


def test_note_perception_ring_and_reflect_packet():
    state = ExecutionState()
    state.perception_mode = "reflect"
    state.last_action = "reveal_actions"
    state.last_plan_step = SimpleNamespace(
        action_family="reveal_actions",
        semantic_target="content_item",
        text="",
        target_point=[1360, 295],
    )
    state.last_result = {
        "ok": True,
        "message": "AXPress center=(199.5, 242.35) role=AXButton",
    }
    state.unified_last_expectation = {
        "surface": "context_menu",
        "likely_controls": ["Forward"],
    }
    state.last_prediction_error = {
        "predicted_surface": "context_menu",
        "observed_surface": "conversation",
        "matched": False,
        "verdict": "miss",
    }
    state.note_perception(
        {
            "surface": "conversation",
            "open_conversation": "Alice",
            "objects": [
                {
                    "id": "msg",
                    "kind": "message",
                    "text": "shared link",
                    "point": [1360, 295],
                    "matches_goal": True,
                }
            ],
        },
        iteration=3,
    )
    packet = _reflect_packet(state)
    assert packet.get("task")
    assert "LOCALIZE" in packet["task"]
    assert packet.get("discovery_questions")
    assert packet.get("runtime_seed_diagnosis")
    assert packet["action"]["family"] == "reveal_actions"
    assert packet["action"]["intended_point"] == [1360.0, 295.0]
    assert packet["action"]["motor_landed_point"] == [199.5, 242.35]
    assert packet["measured"]["geometry_mismatch"] is True
    assert packet["expected"]["surface"] == "context_menu"
    assert packet["actual"]["matched"] is False
    assert len(packet["prior_perceptions"]) == 1
    causes = {h["cause"] for h in packet.get("discovery_hypotheses") or []}
    assert "wrong_target" in causes
    # Same hypotheses from the pure discovery helper (eval substrate).
    assert "wrong_target" in {
        h["cause"] for h in discover_surprise_hypotheses(packet)
    }


def test_low_confidence_forces_reperceive():
    state = ExecutionState()
    state.perception_mode = "reflect"
    state.last_surprise_explanation = {
        "cause": "unknown",
        "confidence": 0.4,
        "recommended_next": "act",
        "detail": "unclear",
    }
    state.last_plan_step = SimpleNamespace(
        action_family="reveal_actions",
        semantic_target="link",
        target_point=[10, 10],
    )
    out = apply_surprise_explanation(
        DecisionOutcome(
            ok=True,
            capability="reveal_actions",
            target="link",
            why="retry",
            confidence=0.9,
            realization="llm_decision",
        ),
        state,
    )
    assert out.capability == "observe"
    assert out.realization == "reflect_reperceive"


def test_high_confidence_backtrack():
    state = ExecutionState()
    state.perception_mode = "reflect"
    state.last_surprise_explanation = {
        "cause": "wrong_surface",
        "confidence": 0.9,
        "recommended_next": "explore",
        "detail": "opened wrong chat",
    }
    out = apply_surprise_explanation(
        DecisionOutcome(
            ok=True,
            capability="open_entity",
            target="X",
            why="go",
            confidence=0.8,
            realization="llm_decision",
        ),
        state,
    )
    # Graph nomenclature: backtrack ≡ revert_effects (not bare dismiss alone).
    assert out.capability == "revert_effects"
    assert out.realization == "reflect_backtrack"


def test_high_confidence_act_blocks_identical_failed_motor():
    state = ExecutionState()
    state.perception_mode = "reflect"
    state.last_plan_step = SimpleNamespace(
        action_family="reveal_actions",
        semantic_target="zarooratwala",
        target_point=[1360, 295],
    )
    state.last_surprise_explanation = {
        "cause": "wrong_target",
        "confidence": 0.92,
        "recommended_next": "act",
        "detail": "clicked sidebar row",
    }
    out = apply_surprise_explanation(
        DecisionOutcome(
            ok=True,
            capability="reveal_actions",
            target="zarooratwala",
            why="retry same",
            confidence=0.9,
            realization="llm_decision",
        ),
        state,
    )
    assert out.capability == "observe"
    assert out.realization == "inconclusive_grounding_reperceive"
    assert state.last_failed_motor_key == motor_fingerprint(
        "reveal_actions", "zarooratwala", [1360, 295]
    )


def test_wrong_region_with_corrected_point_regrounds():
    """Same-target corrected_point must not rewrite object geometry — re-perceive."""
    state = ExecutionState()
    state.perception_mode = "reflect"
    state.last_plan_step = SimpleNamespace(
        action_family="reveal_actions",
        semantic_target="https://www.zarooratwala.com/?...",
        target_point=[1360, 295],
    )
    state.last_surprise_explanation = {
        "cause": "wrong_target",
        "confidence": 0.93,
        "recommended_next": "act",
        "detail": "hit URL/sidebar; use card body",
        "corrected_point": [1487, 187],
    }
    out = apply_surprise_explanation(
        DecisionOutcome(
            ok=True,
            capability="reveal_actions",
            target="https://www.zarooratwala.com/?...",
            why="retry",
            confidence=0.9,
            realization="llm_decision",
        ),
        state,
    )
    assert out.capability == "observe"
    assert out.realization == "inconclusive_grounding_reperceive"
    assert state.reflect_corrected_point is None
    assert getattr(state, "attempt_validity", None) == "inconclusive_grounding"


def test_build_decision_packet_includes_reflect_when_mode_set():
    from plugin.agent.features import StateFeatures
    from plugin.agent.goal import Goal
    from plugin.worldmodel.model import WorldModel

    state = ExecutionState()
    state.perception_mode = "reflect"
    state.unified_world_document = {"surface": "conversation", "objects": []}
    state.unified_last_expectation = {"surface": "context_menu"}
    state.last_prediction_error = {
        "predicted_surface": "context_menu",
        "observed_surface": "conversation",
        "matched": False,
    }
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    feats = StateFeatures(app="WhatsApp", extras={})
    packet = build_decision_packet(goal, WorldModel(active_app="WhatsApp"), feats, state)
    assert packet.get("perception_mode") == "reflect"
    assert isinstance(packet.get("reflect"), dict)
