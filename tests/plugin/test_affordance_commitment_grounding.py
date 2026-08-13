"""Goldens for thin AffordanceCommitment + grounding-recovery layer."""

from __future__ import annotations

from types import SimpleNamespace

from plugin.agent.action import Action
from plugin.agent.executive.affordance_commitment import (
    AVAIL_LATENT,
    AVAIL_OBSERVED,
    STRATEGY_AX,
    STRATEGY_RE_REVEAL,
    STRATEGY_ROI,
    active_commitment,
    arm_grounding_recovery,
    commitment_satisfied_by_label_patient,
    derive_availability,
    derive_executable,
    ensure_commitment_from_menu_observation,
    evidence_indicates_grounding_failure,
    forbids_patient_substitute,
    handle_failed_committed_action,
    invalidate_grounding_hypothesis,
    next_grounding_strategy,
    note_strategy_attempt,
    upsert_commitment,
)
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import ExecutionState, RuntimeState
from plugin.agent.unified_cognition import UnifiedProposal, proposal_to_action
from plugin.worldmodel.model import WorldModel


def _state_with_menu_forward(*, with_geometry: bool = False, surface: str = "context_menu"):
    state = ExecutionState()
    state.last_surface = surface
    obj = {
        "text": "Forward",
        "label": "Forward",
        "kind": "menu_item",
        "enabled": True,
    }
    if with_geometry:
        obj["point"] = [1259.0, 290.0]
        obj["bounds"] = [1200.0, 270.0, 1320.0, 310.0]
    state.unified_world_document = {
        "surface": surface,
        "open_conversation": "Pallavi",
        "source_object_label": "zarooratwala.com",
        "objects": [obj],
    }
    return state


def test_known_affordance_without_geometry_triggers_grounding_recovery():
    state = _state_with_menu_forward(with_geometry=False)
    c = ensure_commitment_from_menu_observation(
        state,
        label="Forward",
        patient_ref="zarooratwala.com",
        desired_effect="forward_picker",
        owner_surface="context_menu",
    )
    assert c is not None
    assert derive_availability(state, c) == AVAIL_OBSERVED
    assert derive_executable(state, c) is False
    arm_grounding_recovery(state, c, reason="label_only")
    assert state.grounding_reground_only is True
    assert state.grounding_reground_commitment_id == c.commitment_id
    assert state.grounding_reground_patient_ref == "zarooratwala.com"
    strat = next_grounding_strategy(state, c)
    assert strat in {STRATEGY_ROI, STRATEGY_AX}


def test_failed_grounding_does_not_invalidate_semantic_method():
    state = _state_with_menu_forward(with_geometry=True)
    c = upsert_commitment(
        state,
        family="invoke_affordance",
        label="Forward",
        desired_effect="forward_picker",
        patient_ref="msg-A",
        owner_surface_expected="context_menu",
    )
    result = handle_failed_committed_action(
        state,
        family="invoke_affordance",
        target="Forward",
        point=(560.0, 290.0),
        pred_error={
            "matched": False,
            "predicted": "forward_picker",
            "actual": "conversation",
            "expected_surface": "context_menu",
            "target": "Forward",
            "verdict": "expected forward_picker",
        },
        intended_point=(1259.0, 290.0),
        surface_before="context_menu",
        surface_after="conversation",
    )
    assert result.get("classified") == "grounding"
    assert result.get("preserve_semantic_method") == "invoke_affordance:Forward"
    c2 = active_commitment(state)
    assert c2 is not None
    assert c2.semantic_method_id == "invoke_affordance:Forward"
    assert any("pt:560.0,290.0" in k for k in c2.invalid_grounding_keys)


def test_effect_absent_without_grounding_evidence_does_not_force_grounding_class():
    state = _state_with_menu_forward(with_geometry=True)
    upsert_commitment(
        state,
        family="invoke_affordance",
        label="Forward",
        desired_effect="forward_picker",
        patient_ref="msg-A",
    )
    # Point coincides with intended control — effect absent alone ≠ grounding.
    result = handle_failed_committed_action(
        state,
        family="invoke_affordance",
        target="Forward",
        point=(1259.0, 290.0),
        pred_error={
            "matched": False,
            "predicted": "forward_picker",
            "actual": "conversation",
            "target": "Forward",
        },
        intended_point=(1259.0, 290.0),
        surface_before="context_menu",
        surface_after="conversation",
    )
    assert result.get("classified") == "not_grounding"
    assert state.grounding_reground_only is False


def test_ungrounded_goal_relevant_affordance_beats_irrelevant_grounded_target():
    state = _state_with_menu_forward(with_geometry=False)
    ensure_commitment_from_menu_observation(
        state,
        label="Forward",
        patient_ref="zarooratwala.com",
        desired_effect="forward_picker",
    )
    arm_grounding_recovery(state, active_commitment(state), reason="test")
    assert forbids_patient_substitute(
        state, family="invoke_affordance", semantic_target="Forward"
    )
    assert forbids_patient_substitute(
        state, family="select_content", semantic_target="zarooratwala.com"
    )


def test_grounding_failure_does_not_collapse_to_source_object_click():
    state = _state_with_menu_forward(with_geometry=False)
    ensure_commitment_from_menu_observation(
        state,
        label="Forward",
        patient_ref="https://www.zarooratwala.com/",
        desired_effect="forward_picker",
    )
    arm_grounding_recovery(state, active_commitment(state), reason="bad_point")
    world = WorldModel(active_app="WhatsApp")
    proposal = UnifiedProposal(
        observed_state={"surface": "conversation"},
        world_model={"surface": "conversation"},
        next_action={
            "family": "invoke_affordance",
            "target_label": "Forward",
            "text": "Forward",
            "confidence": 0.8,
        },
    )
    action, reason = proposal_to_action(
        proposal,
        Goal(kind="whatsapp_forward_message"),
        world,
        execution_state=state,
    )
    assert action is None
    assert "no_patient_substitute" in reason or "ungrounded" in reason


def test_same_semantic_action_tries_alternate_grounding_source():
    state = _state_with_menu_forward(with_geometry=False)
    c = upsert_commitment(
        state,
        family="invoke_affordance",
        label="Forward",
        patient_ref="msg-A",
        owner_surface_expected="context_menu",
    )
    assert next_grounding_strategy(state, c) == STRATEGY_ROI
    note_strategy_attempt(state, c, strategy=STRATEGY_ROI, outcome="miss")
    c = active_commitment(state)
    assert next_grounding_strategy(state, c) == STRATEGY_AX


def test_owner_surface_gone_turns_visible_affordance_into_latent_reveal_recovery():
    state = _state_with_menu_forward(with_geometry=False, surface="context_menu")
    c = ensure_commitment_from_menu_observation(
        state,
        label="Forward",
        patient_ref="msg-A",
        owner_surface="context_menu",
    )
    assert derive_availability(state, c) == AVAIL_OBSERVED
    # Menu dismissed → conversation; commitment survives as latent.
    state.last_surface = "conversation"
    state.unified_world_document = {
        "surface": "conversation",
        "objects": [
            {
                "text": "ZarooratWala link",
                "kind": "message_bubble",
                "point": [1259.0, 218.0],
            }
        ],
    }
    assert derive_availability(state, c) == AVAIL_LATENT
    arm_grounding_recovery(state, c, reason="menu_gone")
    c2 = active_commitment(state)
    assert next_grounding_strategy(state, c2) == STRATEGY_RE_REVEAL
    # Explicit re-reveal on patient is allowed; invoke is not.
    assert forbids_patient_substitute(state, family="invoke_affordance")
    assert not forbids_patient_substitute(state, family="reveal_actions")


def test_menu_disappeared_during_grounding_recovery_reveals_again():
    state = ExecutionState()
    state.last_surface = "conversation"
    state.unified_world_document = {"surface": "conversation", "objects": []}
    c = upsert_commitment(
        state,
        family="invoke_affordance",
        label="Forward",
        patient_ref="msg-A",
        owner_surface_expected="context_menu",
    )
    arm_grounding_recovery(state, c, reason="menu_absent")
    assert state.grounding_reground_only
    closure = state.last_effect_closure or {}
    assert closure.get("recovery") == "re_reveal_for_commitment"
    assert next_grounding_strategy(state, active_commitment(state)) == STRATEGY_RE_REVEAL


def test_same_label_different_patient_does_not_satisfy_grounding_commitment():
    state = ExecutionState()
    c = upsert_commitment(
        state,
        family="invoke_affordance",
        label="Forward",
        patient_ref="message-A",
        owner_surface_expected="context_menu",
    )
    arm_grounding_recovery(state, c, reason="test")
    assert commitment_satisfied_by_label_patient(
        c, label="Forward", patient_ref="message-A"
    )
    assert not commitment_satisfied_by_label_patient(
        c, label="Forward", patient_ref="message-B"
    )
    # Executable Forward for B must not clear A's debt.
    state.last_grounded_affordance_set = [
        {
            "target_label": "Forward",
            "label": "Forward",
            "patient_ref": "message-B",
            "actuators": [{"type": "coordinate_click", "point": [100.0, 200.0]}],
            "coordinate_space": "screen",
            "capture_id": "cap1",
        }
    ]
    state.unified_world_document = {
        "surface": "context_menu",
        "objects": [
            {
                "text": "Forward",
                "point": [100.0, 200.0],
                "patient_ref": "message-B",
            }
        ],
    }
    from plugin.agent.grounding_validity import grounding_repair_satisfied

    # Without graph freshness this may be False anyway; patient mismatch is the contract.
    assert not derive_executable(state, c)


def test_evidence_sidebar_point_is_grounding():
    ok, reason = evidence_indicates_grounding_failure(
        point=(560.0, 290.0),
        intended_point=(1259.0, 290.0),
        surface_before="context_menu",
        pred_error={"target": "Forward", "expected_surface": "context_menu"},
    )
    assert ok
    assert "sidebar" in reason or "far_from" in reason


def test_live_shaped_wrong_point_preserves_method_and_regrounds():
    """context_menu + Forward + bad point → invalidate point → preserve method."""
    state = _state_with_menu_forward(with_geometry=True)
    c = ensure_commitment_from_menu_observation(
        state,
        label="Forward",
        patient_ref="zarooratwala.com",
        desired_effect="forward_picker",
    )
    result = handle_failed_committed_action(
        state,
        family="invoke_affordance",
        target="Forward",
        point=(560.0, 290.0),
        pred_error={
            "matched": False,
            "predicted": "forward_picker",
            "actual": "conversation",
            "expected_surface": "context_menu",
            "target": "Forward",
        },
        intended_point=(1259.0, 290.0),
        surface_before="context_menu",
    )
    assert result["classified"] == "grounding"
    c = active_commitment(state)
    assert "pt:560.0,290.0" in c.invalid_grounding_keys
    assert c.semantic_method_id == "invoke_affordance:Forward"
    assert state.grounding_reground_commitment_id == c.commitment_id
    # Forbidden trajectory: invoke rebound to patient.
    action, reason = proposal_to_action(
        UnifiedProposal(
            observed_state={"surface": "conversation"},
            world_model={"surface": "conversation"},
            next_action={
                "family": "invoke_affordance",
                "target_label": "Forward",
                "text": "Forward",
            },
        ),
        Goal(kind="whatsapp_forward_message"),
        WorldModel(active_app="WhatsApp"),
        execution_state=state,
    )
    assert action is None
