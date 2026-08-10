"""Overloaded revert_effects + start-anywhere branch fitness recoverability."""

from __future__ import annotations

from types import SimpleNamespace

from plugin.agent.brain import apply_surprise_explanation
from plugin.agent.capabilities.branch_fitness import compute_branch_fitness
from plugin.agent.capabilities.catalog import spec_by_name
from plugin.agent.capabilities.dispatch import can_dispatch
from plugin.agent.capabilities.revert_effects import (
    PRESS_ESCAPE,
    analyze_revert_plan,
    approve_revert_plan,
    revert_effects,
    selection_consistency_error,
)
from plugin.agent.decision_consultation import DecisionOutcome
from plugin.agent.reflect_diagnosis import (
    merge_diagnoses,
    normalize_reflect_diagnosis,
    seed_reflect_diagnosis_from_measured,
)
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.unified_cognition import finalize_surprise_explanation


def _bad_two_selected_doc() -> dict:
    return {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "objects": [
            {"id": "sel", "kind": "status_text", "text": "2 Selected", "point": [900, 60]},
            {"id": "fwd", "kind": "button", "text": "Forward", "point": [981, 990]},
            {
                "id": "z",
                "kind": "message_bubble",
                "text": "https://www.zarooratwala.com/",
                "matches_goal": True,
                "point": [1191, 201],
            },
            {
                "id": "c",
                "kind": "message_bubble",
                "text": "Chunni ko bhi Prabal se baat karna hai...",
                "matches_goal": False,
                "point": [1124, 227],
            },
        ],
    }


def test_catalog_lists_revert_effects():
    assert spec_by_name("revert_effects") is not None
    assert can_dispatch("revert_effects")
    assert can_dispatch("backtrack")
    assert can_dispatch("rollback")


def test_wrong_selection_is_inconsistent():
    sel = selection_consistency_error(
        _bad_two_selected_doc(),
        goal_referents=["zarooratwala", "https://www.zarooratwala.com"],
    )
    assert sel["consistent"] is False
    assert sel.get("selection_count") == 2


def test_wrong_selection_plan_press_escape():
    doc = _bad_two_selected_doc()
    plan = analyze_revert_plan(document=doc, goal_referents=["zarooratwala"])
    plan = approve_revert_plan(plan, auto=True)
    assert plan.approved
    assert plan.steps[0].realization == PRESS_ESCAPE


def test_filter_chip_cold_start_press_escape():
    doc = {
        "surface": "search",
        "objects": [
            {"text": "MediaFilter", "kind": "filter_chip", "restricts": "media"},
            {"text": "thumb", "kind": "media"},
        ],
    }
    fit = compute_branch_fitness(
        doc,
        needed_kinds=["message", "link", "message_bubble"],
        goal_referents=["example-link"],
    )
    assert fit["admissible"] is False
    plan = analyze_revert_plan(
        document=doc,
        goal_referents=["example-link"],
        effect_trace=[],
        branch_fitness=fit,
    )
    plan = approve_revert_plan(plan, auto=True)
    assert plan.approved
    assert plan.steps[0].realization == PRESS_ESCAPE


def test_whatsapp_overlay_tags_media_filter_chip():
    from plugin.agent.apps.whatsapp import WhatsAppOverlay

    doc = WhatsAppOverlay().enrich_world_document(
        {
            "surface": "search",
            "open_conversation": "• Videos",
            "objects": [{"text": "Videos", "kind": "chip"}],
        }
    )
    assert any(o.get("kind") == "filter_chip" for o in doc["objects"])


def test_filter_chip_seeds_backtrack_repair():
    doc = {
        "surface": "search",
        "objects": [
            {"text": "MediaFilter", "kind": "filter_chip", "restricts": "media"},
            {"text": "thumb", "kind": "media"},
        ],
    }
    packet = {
        "action": {"family": "compose_search_query", "target": "example-link"},
        "expected": {"surface": "search"},
        "actual": {"matched": True, "observed_surface": "search"},
        "goal": {"link_query": "example-link"},
        "post_world": doc,
    }
    seed = seed_reflect_diagnosis_from_measured(packet)
    assert seed.repair.kind == "invoke_revert_effects"
    assert seed.recommended_next == "explore"


def test_undo_hint_lifo_preferred():
    plan = analyze_revert_plan(
        document={"surface": "conversation", "objects": []},
        effect_trace=[
            {
                "capability": "commit_irreversible",
                "target": "Send",
                "effect_class": "message_sent",
                "undo_hint": "delete_committed_message",
            }
        ],
    )
    assert plan.steps
    assert plan.steps[0].realization == "delete_committed_message"
    gated = approve_revert_plan(plan, auto=True)
    assert gated.approved is False


def test_classify_effect_send_is_message_sent():
    from plugin.agent.capabilities.revert_effects import classify_effect

    assert (
        classify_effect(capability="commit_irreversible", target="Send")
        == "message_sent"
    )


def test_wrong_selection_seed_invokes_revert():
    packet = {
        "action": {
            "family": "select_content",
            "target": "zarooratwala",
            "executor_ok": True,
            "intended_point": [1191, 201],
            "motor_landed_point": [1124, 227],
        },
        "expected": {"surface": "conversation"},
        "actual": {
            "matched": True,
            "predicted_surface": "conversation",
            "observed_surface": "conversation",
        },
        "measured": {"geometry_mismatch": True},
        "goal": {"link_query": "zarooratwala"},
        "post_world": _bad_two_selected_doc(),
    }
    seed = seed_reflect_diagnosis_from_measured(packet)
    assert seed.repair.kind == "invoke_revert_effects"
    assert seed.repair.capability == "revert_effects"


def test_brain_consumes_revert_repair():
    packet = {
        "action": {
            "family": "select_content",
            "target": "zarooratwala",
            "executor_ok": True,
        },
        "expected": {"surface": "conversation"},
        "actual": {"matched": True, "observed_surface": "conversation"},
        "goal": {"link_query": "zarooratwala"},
        "post_world": _bad_two_selected_doc(),
    }
    expl = finalize_surprise_explanation(
        {"cause": "unknown", "confidence": 0.2, "recommended_next": "reperceive"},
        reflect_packet=packet,
    )
    state = ExecutionState()
    state.perception_mode = "reflect"
    state.last_surprise_explanation = expl
    state.last_plan_step = SimpleNamespace(
        action_family="select_content",
        semantic_target="zarooratwala",
        target_point=[1124, 227],
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
    assert out.capability == "revert_effects"


def test_post_revert_seed_reselects_goal():
    packet = {
        "action": {"family": "revert_effects", "executor_ok": True},
        "expected": {"surface": "conversation"},
        "actual": {"matched": True, "observed_surface": "conversation"},
        "pending_repair_after_revert": {
            "capability": "select_content",
            "target_hint": "zarooratwala",
            "reason": "post_revert_reselect",
            "repair_kind": "re_ground_then_act",
        },
        "goal": {"link_query": "zarooratwala"},
        "post_world": {
            "surface": "conversation",
            "open_conversation": "Pallavi",
            "objects": [
                {
                    "id": "z",
                    "kind": "message_bubble",
                    "text": "https://www.zarooratwala.com/",
                    "matches_goal": True,
                    "point": [1191, 201],
                }
            ],
        },
    }
    seed = seed_reflect_diagnosis_from_measured(packet)
    assert seed.repair.kind == "re_ground_then_act"
    assert seed.repair.capability == "select_content"
    assert seed.repair.geometry == [1191.0, 201.0]


def test_dry_run_revert_ok():
    outcome = revert_effects(
        app="WhatsApp",
        document=_bad_two_selected_doc(),
        goal_referents=["zarooratwala"],
        dry_run=True,
        force_approve=True,
    )
    assert outcome.ok
    assert outcome.capability == "revert_effects"
