"""ReflectDiagnosis contract — fault localization + repair (145239 Forward miss)."""

from __future__ import annotations

from types import SimpleNamespace

from plugin.agent.brain import apply_surprise_explanation
from plugin.agent.decision_consultation import DecisionOutcome
from plugin.agent.reflect_diagnosis import (
    enrich_reflect_packet,
    merge_diagnoses,
    normalize_reflect_diagnosis,
    seed_reflect_diagnosis_from_measured,
)
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.unified_cognition import (
    finalize_surprise_explanation,
    normalize_surprise_explanation,
)


def _forward_picker_miss_packet() -> dict:
    """Measured facts from zarooratwala 145239 step 34→37."""
    return {
        "action": {
            "family": "invoke_affordance",
            "target": "Forward",
            "text": "Forward",
            "executor_ok": True,
            "executor_message": "AXPress 'Forward' in background (no foreground)",
            "intended_point": [1400.0, 400.0],
        },
        "expected": {"surface": "forward_picker", "likely_controls": ["Search", "Tanmay"]},
        "actual": {
            "predicted_surface": "forward_picker",
            "observed_surface": "conversation",
            "matched": False,
            "verdict": "miss",
        },
        "measured": {"effect": "promising_unresolved", "executor_ok": True},
        "post_world": {
            "surface": "conversation",
            "open_conversation": "Pallavi",
            "objects": [
                {
                    "id": "hdr",
                    "kind": "header",
                    "text": "Pallavi",
                    "point": [900, 40],
                },
                {
                    "id": "sel",
                    "kind": "status_text",
                    "text": "1 Selected",
                    "point": [900, 60],
                },
                {
                    "id": "fwd",
                    "kind": "button",
                    "text": "Forward",
                    "point": [520, 920],
                    "bounds": [480, 900, 80, 40],
                    "matches_goal": True,
                },
                {
                    "id": "msg",
                    "kind": "message_bubble",
                    "text": "ZarooratWala - Fresh Groceries",
                    "point": [1385, 186],
                    "matches_goal": True,
                },
            ],
        },
    }


def test_normalize_accepts_repair_schema():
    d = normalize_reflect_diagnosis(
        {
            "cause": "motor_path",
            "locus": "actor",
            "transition_class": "wrong_transition",
            "confidence": 0.9,
            "recommended_next": "act",
            "repair": {
                "kind": "retry_same_affordance_different_motor",
                "capability": "invoke_affordance",
                "target": "Forward",
                "motor_constraint": "foreground_click",
            },
        }
    )
    assert d.cause == "motor_path"
    assert d.locus == "actor"
    assert d.repair.kind == "retry_same_affordance_different_motor"
    assert d.recommended_next == "act"
    wire = d.to_surprise_explanation()
    assert wire["repair"]["motor_constraint"] == "foreground_click"


def test_seed_diagnoses_145239_background_forward_as_partial_transition():
    packet = _forward_picker_miss_packet()
    seed = seed_reflect_diagnosis_from_measured(packet)
    assert seed.cause == "partial_effect"
    assert seed.locus == "world_semantics"
    assert seed.transition_class == "partial_transition"
    assert seed.repair.kind == "follow_observed_transition"
    assert seed.repair.target == "Forward"
    assert seed.repair.capability == "invoke_affordance"
    assert seed.repair.motor_constraint == "foreground_click"
    assert seed.repair.geometry == [520.0, 920.0]
    assert seed.recommended_next == "act"
    assert "observe_while_forward_visible" in seed.do_not_repeat


def test_seed_background_ax_without_selection_chrome_is_motor_path():
    packet = _forward_picker_miss_packet()
    packet["post_world"]["objects"] = [
        {"id": "m", "kind": "message", "text": "hi", "point": [100, 100]}
    ]
    seed = seed_reflect_diagnosis_from_measured(packet)
    assert seed.cause == "motor_path"
    assert seed.locus == "actor"
    assert seed.repair.kind == "retry_same_affordance_different_motor"
    assert seed.repair.motor_constraint == "foreground_click"


def test_weak_model_loses_to_strong_seed():
    packet = _forward_picker_miss_packet()
    seed = seed_reflect_diagnosis_from_measured(packet)
    model = normalize_reflect_diagnosis(
        {
            "cause": "unknown",
            "confidence": 0.4,
            "recommended_next": "reperceive",
            "detail": "unclear",
        }
    )
    merged = merge_diagnoses(model, seed)
    assert merged.repair.kind == "follow_observed_transition"
    assert merged.source == "merged_seed"


def test_finalize_surprise_explanation_merges_seed():
    packet = enrich_reflect_packet(_forward_picker_miss_packet())
    expl = finalize_surprise_explanation(
        {"cause": "unknown", "confidence": 0.3, "recommended_next": "reperceive"},
        reflect_packet=packet,
    )
    assert expl["repair"]["kind"] == "follow_observed_transition"
    assert expl["recommended_next"] == "act"


def test_apply_repair_overrides_observe_chooser():
    """The irrecoverable 145239 failure: chooser said Observe while Forward visible."""
    state = ExecutionState()
    state.perception_mode = "reflect"
    packet = _forward_picker_miss_packet()
    state.last_surprise_explanation = finalize_surprise_explanation(
        {"cause": "unknown", "confidence": 0.2},
        reflect_packet=packet,
    )
    state.last_plan_step = SimpleNamespace(
        action_family="invoke_affordance",
        semantic_target="Forward",
        target_point=[1400, 400],
    )
    out = apply_surprise_explanation(
        DecisionOutcome(
            ok=True,
            capability="observe",
            target="",
            why="model_requested_observe",
            confidence=0.3,
            realization="llm_decision",
        ),
        state,
    )
    assert out.capability == "invoke_affordance"
    assert out.target == "Forward"
    assert out.realization == "reflect_repair:follow_observed_transition"
    assert state.reflect_corrected_point == [520.0, 920.0]
    assert state.reflect_motor_constraint == "foreground_click"


def test_legacy_normalize_still_works():
    expl = normalize_surprise_explanation(
        {
            "cause": "stale_geometry",
            "confidence": 0.9,
            "recommended_next": "act",
            "corrected_point": [1, 2],
        }
    )
    assert expl["cause"] == "stale_geometry"
    assert expl["corrected_point"] == [1.0, 2.0]
    assert expl["repair"]["kind"] == "retry_with_corrected_geometry"


def test_seed_geometry_mismatch_prefers_landed_object_not_intended():
    """Live 125715: motor landing is Attempt evidence — re-perceive, no object rewrite."""
    packet = {
        "action": {
            "family": "reveal_actions",
            "target": "zarooratwala",
            "executor_ok": True,
            "intended_point": [1191.0, 201.0],
            "motor_landed_point": [878.0, 260.0],
        },
        "expected": {"surface": "context_menu"},
        "actual": {
            "predicted_surface": "context_menu",
            "observed_surface": "conversation",
            "matched": False,
        },
        "measured": {
            "geometry_mismatch": True,
            "executor_ok": True,
            "motor_landed_point": [878.0, 260.0],
        },
        "post_world": {
            "surface": "conversation",
            "objects": [
                {
                    "text": "https://www.zarooratwala.com/",
                    "kind": "message_bubble",
                    "point": [900, 255],
                    "matches_goal": True,
                },
                {
                    "text": "other",
                    "kind": "message_bubble",
                    "point": [1191, 201],
                    "matches_goal": False,
                },
            ],
        },
    }
    seed = seed_reflect_diagnosis_from_measured(packet)
    assert seed.repair.kind == "reperceive"
    assert seed.recommended_next == "reperceive"
    assert seed.corrected_point is None
    assert seed.repair.geometry is None
    dnr = ",".join(seed.do_not_repeat)
    assert "1191" in dnr
    assert "878" in dnr
    assert "inconclusive_grounding" in " ".join(seed.evidence)


def test_seed_follows_forward_even_when_matched_true_after_reveal():
    """controls_present can make matched=true while surface stayed conversation."""
    packet = {
        "action": {
            "family": "reveal_actions",
            "target": "msg",
            "executor_ok": True,
            "intended_point": [100.0, 100.0],
        },
        "expected": {"surface": "context_menu", "likely_controls": ["Forward"]},
        "actual": {
            "predicted_surface": "context_menu",
            "observed_surface": "conversation",
            "matched": True,
            "controls_present": ["forward"],
        },
        "measured": {"executor_ok": True},
        "post_world": {
            "surface": "conversation",
            "objects": [
                {
                    "text": "Forward",
                    "kind": "menu_item",
                    "point": [520, 300],
                    "matches_goal": True,
                }
            ],
        },
    }
    seed = seed_reflect_diagnosis_from_measured(packet)
    assert seed.repair.kind == "follow_observed_transition"
    assert seed.repair.target == "Forward"
    assert seed.recommended_next == "act"
