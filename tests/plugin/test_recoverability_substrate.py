"""Structural/behavioral contracts so recoverability goldens remain actionable.

Goldens assert outcomes; these tests assert the agent still has the wiring
(catalog, fitness, meta, undo stack, brain/reflect, BACKTRACK→revert) those
goldens depend on.
"""

from __future__ import annotations

from plugin.agent.apps.whatsapp import WhatsAppOverlay
from plugin.agent.capabilities.branch_fitness import compute_branch_fitness
from plugin.agent.capabilities.catalog import model_allowed_actions, spec_by_name
from plugin.agent.capabilities.dispatch import can_dispatch
from plugin.agent.capabilities.revert_effects import (
    PRESS_ESCAPE,
    analyze_revert_plan,
    approve_revert_plan,
    normalize_realization,
    record_act_on_effect_trace,
)
from plugin.agent.executive.meta_action import MetaAction, MetaContext, select_meta_action
from plugin.agent.executive.meta_consultation import meta_context_packet
from plugin.agent.executive.sufficiency import DecisionSufficiency
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import ExecutionState
from plugin.evals.gates import _recoverability_substrate_wired_for_goldens
from plugin.evals.golden.schema import load_module_cases
from plugin.evals.golden.score import score_meta_action_case, score_ui_case


def test_recoverability_substrate_gate_passes():
    ok, detail = _recoverability_substrate_wired_for_goldens()
    assert ok, detail


def test_backtrack_aliases_dispatch_to_revert_effects():
    assert spec_by_name("revert_effects") is not None
    assert "revert_effects" in model_allowed_actions()
    for alias in ("backtrack", "rollback", "revert", "revert_effects"):
        assert can_dispatch(alias), alias


def test_escape_aliases_normalize_to_press_escape():
    for name in (
        "clear_search_filter",
        "clear_selection_escape",
        "dismiss_transient_chrome",
        "leave_picker_escape",
        PRESS_ESCAPE,
    ):
        assert normalize_realization(name) == PRESS_ESCAPE


def test_meta_packet_carries_branch_fitness_for_judgement():
    pkt = meta_context_packet(
        MetaContext(
            branch_unfit=True,
            branch_fitness={
                "admissible": False,
                "reasons": ["filter_chip_blocks_needed_evidence"],
                "blockers": [{"type": "filter_chip"}],
            },
        )
    )
    search = pkt["search"]
    assert search["branch_unfit"] is True
    assert search["branch_fitness"]["admissible"] is False
    assert "filter_chip" in (search["branch_fitness"].get("blockers") or [])


def test_branch_unfit_scorer_prefers_backtrack_over_perceive():
    """140713 class: observe_has_value alone must not bury BACKTRACK when unfit."""
    choice = select_meta_action(
        MetaContext(
            sufficiency=DecisionSufficiency(
                sufficient_to_act=False,
                observe_has_value=True,
                needs_exploration=True,
                confidence=0.8,
                reason="evidence ready but no grounded action geometry yet",
            ),
            has_grounded_action=False,
            branch_stale=True,
            branch_unfit=True,
            post_action_look_owed=False,
            information_gathering_exhausted=False,
            backtrack_exhausted=False,
        )
    )
    assert choice.action is MetaAction.EXPLORE


def test_effect_trace_records_undo_hint_for_lifo_analyze():
    state = ExecutionState()
    record_act_on_effect_trace(
        state,
        capability="select_content",
        target="msg",
        intention={"surface": "conversation"},
    )
    assert state.effect_trace[-1]["undo_hint"] == PRESS_ESCAPE
    plan = approve_revert_plan(
        analyze_revert_plan(
            document={"surface": "conversation", "objects": []},
            effect_trace=state.effect_trace,
        ),
        auto=True,
    )
    assert plan.approved
    assert plan.steps[0].realization == PRESS_ESCAPE


def test_goal_needed_kinds_drive_fitness_not_task_strings():
    goal = Goal(kind="whatsapp_forward_message", link_query="example-link")
    kinds = goal.needed_evidence_kinds()
    doc = {
        "surface": "search",
        "objects": [
            {"kind": "filter_chip", "text": "AnyChip", "restricts": "media"},
            {"kind": "media", "text": "0:05"},
        ],
    }
    fit = compute_branch_fitness(doc, needed_kinds=kinds, goal=goal)
    assert fit["admissible"] is False
    assert any(b.get("type") == "filter_chip" for b in fit["blockers"])


def test_overlay_enrich_is_observation_not_core_recovery_rule():
    doc = WhatsAppOverlay().enrich_world_document(
        {
            "surface": "search",
            "open_conversation": "• Videos",
            "objects": [{"kind": "chip", "text": "Videos"}],
        }
    )
    assert any(o.get("kind") == "filter_chip" for o in doc["objects"])
    # Core fitness only needs the typed kind — label may vary.
    fit = compute_branch_fitness(
        doc,
        needed_kinds=["message", "link"],
        goal_referents=["example"],
    )
    assert fit["admissible"] is False


def test_live_mined_recoverability_goldens_still_score():
    ui = {c.id: c for c in load_module_cases("ui")}
    for cid in (
        "ui/live_140713_ocr_videos_grid_reverts_press_escape",
        "ui/live_140713_ocr_videos_seeds_backtrack",
        "ui/live_132831_ocr_two_selected_reverts",
        "ui/cold_start_filter_chip_reverts_without_trace",
    ):
        assert cid in ui, cid
        scored = score_ui_case(ui[cid])
        assert scored.passed, (cid, scored.checks)
    meta = next(
        c
        for c in load_module_cases("meta_action")
        if c.id == "meta/live_140713_videos_unfit_backtracks_not_ig"
    )
    scored_m = score_meta_action_case(meta)
    assert scored_m.passed, scored_m.checks
