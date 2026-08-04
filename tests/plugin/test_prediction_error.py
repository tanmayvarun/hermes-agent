"""Prediction error is computed, named, and acted on.

The agent predicts what an action will produce, and that prediction is what makes
the result informative: without it a screen is just a screen, and with it even an
unchanged screen is evidence that the agent's model of what a control does is
wrong. That is the signal it learns from during a task.

Both halves of the mechanism existed. The model emitted expected_transition, the
runtime stored it and handed it back as you_predicted, and the prompt told the
model to compare. Nothing ever put the two side by side, so the comparison was
left for the model to make on its own while also perceiving the screen, updating
its world model and choosing a move. It did not make it: on a live run it
predicted a context menu three times, got the unchanged conversation three times,
and reissued the same right-click each time.

The comparison is structural rather than task-shaped — a predicted surface and a
set of expected controls describe a step in any application — so these tests use
the live chat failure as one instance, not as the definition.
"""

from __future__ import annotations

from plugin.agent.action import PlanStep
from plugin.agent.controller import _last_action_surprised, _prediction_was_contradicted
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.unified_cognition import (
    UnifiedProposal,
    build_decision_packet,
    note_prediction_error,
    prediction_error,
    proposal_to_action,
)
from plugin.worldmodel.model import WorldModel


def _menu_expected() -> dict:
    return {"surface": "context_menu", "likely_controls": ["Forward", "Reply", "Delete"]}


def _conversation_seen() -> dict:
    return {
        "surface": "conversation",
        "objects": [
            {"id": "msg_1", "kind": "message_bubble", "text": "ZarooratWala - Fresh Groceries"},
            {"id": "composer", "kind": "input_field", "text": "Type a message"},
        ],
    }


def _menu_seen() -> dict:
    return {
        "surface": "context_menu",
        "objects": [
            {"id": "mi_forward", "kind": "menu_item", "text": "Forward"},
            {"id": "mi_reply", "kind": "menu_item", "text": "Reply"},
            {"id": "mi_delete", "kind": "menu_item", "text": "Delete"},
        ],
    }


# --- the comparison itself ----------------------------------------------------


def test_the_live_failure_is_named_as_an_error():
    error = prediction_error(_menu_expected(), _conversation_seen())
    assert error["matched"] is False
    assert error["predicted_surface"] == "context_menu"
    assert error["observed_surface"] == "conversation"
    assert "context_menu" in error["verdict"]
    assert "conversation" in error["verdict"]


def test_the_absent_controls_are_named():
    error = prediction_error(_menu_expected(), _conversation_seen())
    assert error["controls_absent"] == ["forward", "reply", "delete"]
    assert error["controls_present"] == []


def test_a_prediction_that_held_is_recognised():
    error = prediction_error(_menu_expected(), _menu_seen())
    assert error["matched"] is True
    assert "held" in error["verdict"]


def test_a_surface_renamed_but_present_is_not_an_error():
    """Surface vocabularies drift between frames; synonyms must not manufacture errors."""
    seen = dict(_menu_seen())
    seen["surface"] = "message_actions"
    error = prediction_error(_menu_expected(), seen)
    assert error["matched"] is True, error["verdict"]


def test_a_partially_containing_surface_name_counts_as_a_match():
    seen = {"surface": "search_results", "objects": []}
    error = prediction_error({"surface": "search"}, seen)
    assert error["matched"] is True


def test_controls_matched_by_kind_not_only_text():
    """A composer is recognised as a kind; a menu item by its label."""
    error = prediction_error(
        {"surface": "conversation", "likely_controls": ["input_field"]}, _conversation_seen()
    )
    assert error["matched"] is True


def test_no_prediction_means_nothing_to_score():
    assert prediction_error({}, _conversation_seen()) == {}
    assert prediction_error(None, _conversation_seen()) == {}


def test_a_prediction_without_a_surface_is_not_scored():
    assert prediction_error({"likely_controls": ["Forward"]}, _conversation_seen()) == {}


def test_an_unreadable_frame_is_reported_as_uncheckable_not_as_failure():
    """Absence of a reading is not evidence the prediction was wrong."""
    error = prediction_error(_menu_expected(), {"surface": "", "objects": []})
    assert error["matched"] is False
    assert "could not be checked" in error["verdict"]


# --- scoring happens before the prediction is replaced ------------------------


def test_the_standing_prediction_is_scored_against_the_new_reading():
    state = ExecutionState()
    state.unified_last_expectation = _menu_expected()
    proposal = UnifiedProposal()
    proposal.world_model = _conversation_seen()

    error = note_prediction_error(state, proposal)

    assert error["matched"] is False
    assert state.last_prediction_error["predicted_surface"] == "context_menu"


def test_scoring_a_frame_with_no_standing_prediction_is_harmless():
    state = ExecutionState()
    proposal = UnifiedProposal()
    proposal.world_model = _conversation_seen()
    assert note_prediction_error(state, proposal) == {}


# --- the error reaches the model ---------------------------------------------


def test_the_packet_carries_the_scored_error_beside_the_prediction():
    state = ExecutionState()
    state.last_plan_step = PlanStep(
        action="ContextClick", action_family="reveal_actions", semantic_target="msg"
    )
    state.unified_last_expectation = _menu_expected()
    state.last_prediction_error = prediction_error(_menu_expected(), _conversation_seen())

    packet = build_decision_packet(
        Goal(kind="whatsapp_forward_message"), WorldModel(), StateFeatures(app="WhatsApp"), state
    )

    last = packet["last_action"]
    assert last["you_predicted"]["surface"] == "context_menu"
    assert last["prediction_error"]["matched"] is False


def test_the_protocol_tells_the_model_what_a_prediction_error_means():
    from plugin.agent.unified_cognition import _SYSTEM_PROMPT

    assert "prediction_error" in _SYSTEM_PROMPT
    assert "you_predicted" in _SYSTEM_PROMPT


# --- a contradicted prediction is a surprise ---------------------------------


def test_a_contradicted_prediction_is_a_surprise():
    state = ExecutionState()
    state.last_prediction_error = prediction_error(_menu_expected(), _conversation_seen())
    assert _prediction_was_contradicted(state) is True
    assert _last_action_surprised(state) is True


def test_a_prediction_that_held_is_not_a_surprise():
    state = ExecutionState()
    state.last_prediction_error = prediction_error(_menu_expected(), _menu_seen())
    assert _prediction_was_contradicted(state) is False
    assert _last_action_surprised(state) is False


def test_surprise_from_the_prediction_needs_no_attribution():
    """The effect-based signals are proxies; the prediction speaks for itself.

    A move that lands somewhere plausible and entirely wrong reads as ordinary
    progress to them.
    """
    state = ExecutionState()
    state.last_attribution = {"effect_kind": "progress", "outcome": "progress"}
    state.last_prediction_error = prediction_error(_menu_expected(), _conversation_seen())
    assert _last_action_surprised(state) is True


# --- the learning layer stops receiving blanks -------------------------------


def _proposal_with_prediction() -> UnifiedProposal:
    proposal = UnifiedProposal()
    proposal.confidence = 0.9
    proposal.point_scale = 1.0
    proposal.point_origin = (0.0, 0.0)
    proposal.world_model = {"surface": "conversation", "objects": []}
    proposal.observed_state = {"surface": "conversation"}
    proposal.expected_transition = _menu_expected()
    proposal.next_action = {"family": "reveal_actions", "text": "ZarooratWala"}
    return proposal


def test_a_model_chosen_action_carries_its_prediction():
    """It was {} for every one, so record_outcome compared results to nothing."""
    proposal = _proposal_with_prediction()
    action, reason = proposal_to_action(proposal, Goal(kind="whatsapp_forward_message"), WorldModel())
    assert action is not None, reason
    assert action.prediction, "the model predicted; the action must carry it"
    assert action.prediction["predicted_outcome"] == "context_menu"
    assert action.prediction["expected_affordances"] == ["Forward", "Reply", "Delete"]


def test_the_prediction_is_in_the_shape_the_experience_layer_reads():
    proposal = _proposal_with_prediction()
    action, _ = proposal_to_action(proposal, Goal(kind="whatsapp_forward_message"), WorldModel())
    pred = action.prediction
    assert isinstance(pred.get("expected_progress"), float)
    assert isinstance(pred.get("expected_affordances"), list)
    assert pred.get("predicted_outcome")


def test_an_action_the_model_made_no_prediction_for_carries_none():
    proposal = _proposal_with_prediction()
    proposal.expected_transition = {}
    action, _ = proposal_to_action(proposal, Goal(kind="whatsapp_forward_message"), WorldModel())
    assert action is not None
    assert not action.prediction
