"""General contracts: effect judgment vs meta latch; content referent fitness."""

from __future__ import annotations

from types import SimpleNamespace

from plugin.agent.controller import (
    _consume_surprise,
    _effect_was_absent,
    _last_action_surprised,
    _prediction_was_contradicted,
)
from plugin.agent.capabilities.reveal_actions import escalate_failed_reveal
from plugin.agent.capabilities.revert_effects import (
    content_target_fits_referents,
    pick_unique_referent_content,
)
from plugin.agent.decision_consultation import _ground_choice_on_world
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.unified_cognition import note_prediction_error, UnifiedProposal


def test_consume_surprise_keeps_effect_absent_judgment():
    state = ExecutionState()
    state.last_prediction_error = {
        "matched": False,
        "predicted_surface": "context_menu",
        "observed_surface": "conversation",
        "controls_absent": ["forward", "reply"],
        "verdict": "you predicted 'context_menu' and the screen is 'conversation'.",
    }
    state.last_attribution = {
        "belief_authority": "motor",
        "effect_kind": "no_transition",
        "outcome": "no_effect",
    }
    assert _prediction_was_contradicted(state) is True
    _consume_surprise(state)
    # Meta: surprise disarmed.
    assert _last_action_surprised(state) is False
    assert _prediction_was_contradicted(state) is False
    # Judgment: effect still absent — mechanism may escalate.
    assert state.last_prediction_error.get("matched") is False
    assert state.last_prediction_error.get("effect_absent") is True
    assert state.last_prediction_error.get("suppressed_rearm") is True
    assert _effect_was_absent(state) is True


def test_suppressed_rearm_allows_motor_escalate():
    state = ExecutionState()
    state.last_prediction_error = {
        "matched": False,
        "effect_absent": True,
        "consumed_by_reflect": True,
        "suppressed_rearm": True,
        "surprise_armed": False,
        "predicted_surface": "context_menu",
    }
    state.reveal_probe_mode = "context_click"
    state.last_plan_step = SimpleNamespace(
        action_family="reveal_actions",
        semantic_target="content_alpha",
        target_point=(10.0, 20.0),
    )
    assert _prediction_was_contradicted(state) is False
    assert _effect_was_absent(state) is True
    esc = escalate_failed_reveal(
        state,
        target="content_alpha",
        point=(10.0, 20.0),
        last_gesture="context_click",
    )
    assert esc.get("next_mode") == "hover"
    assert state.reveal_probe_mode == "hover"


def test_note_prediction_error_preserves_matched_false_after_consume():
    state = ExecutionState()
    state.unified_last_expectation = {
        "surface": "context_menu",
        "likely_controls": ["Forward", "Reply"],
    }
    state.last_prediction_error = {
        "matched": False,
        "consumed_by_reflect": True,
        "surprise_armed": False,
        "predicted_surface": "context_menu",
    }
    err = note_prediction_error(
        state,
        UnifiedProposal(
            world_model={"surface": "conversation", "objects": []},
            confidence=0.5,
        ),
    )
    assert err.get("matched") is False
    assert err.get("suppressed_rearm") is True
    assert err.get("effect_absent") is True


def test_content_probe_rebinds_to_unique_referent_object():
    """Synthetic A vs B — no host names. Wrong model target must not stick."""
    doc = {
        "surface": "conversation",
        "objects": [
            {
                "id": "wrong",
                "kind": "message_bubble",
                "text": "content_other_host_link",
                "point": [100.0, 200.0],
            },
            {
                "id": "right",
                "kind": "message_bubble",
                "text": "https://example.com/goal_token_alpha",
                "point": [300.0, 400.0],
                "matches_goal": True,
            },
        ],
    }
    assert content_target_fits_referents(
        target_label="content_other_host_link",
        goal_referents=["goal_token_alpha"],
    ) is False
    alt = pick_unique_referent_content(doc, ["goal_token_alpha"])
    assert alt is not None
    assert alt.get("id") == "right"

    grounded = _ground_choice_on_world(
        doc,
        "reveal_actions",
        "content_other_host_link",
        goal_referents=["goal_token_alpha"],
    )
    assert grounded.get("target_id") == "right"
    assert "goal_token_alpha" in str(grounded.get("target_label") or "")


def test_content_probe_without_referents_keeps_explicit_target():
    doc = {
        "surface": "conversation",
        "objects": [
            {
                "id": "a",
                "kind": "message_bubble",
                "text": "content_other_host_link",
                "point": [100.0, 200.0],
            },
        ],
    }
    grounded = _ground_choice_on_world(
        doc, "reveal_actions", "content_other_host_link", goal_referents=None
    )
    assert grounded.get("target_id") == "a"
