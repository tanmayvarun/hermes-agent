"""Act intention → post-act perceive → inferred surprise → REFLECT.

Surprise is not wired from AX settle / geometry heuristics. The act stamps what
it claimed; the next look scores that claim; mismatch arms multimodal surprise.
"""

from __future__ import annotations

from plugin.agent.action import Action
from plugin.agent.controller import _last_action_surprised, _prediction_was_contradicted
from plugin.agent.executive.meta_action import MetaAction, MetaContext, select_meta_action
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.unified_cognition import (
    UnifiedProposal,
    _expand_fast_parsed,
    _remember_reading,
    intention_expectation_from_decision,
    note_prediction_error,
    stamp_act_intention,
)


def _conversation_world() -> dict:
    return {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "objects": [
            {"id": "msg", "kind": "message_bubble", "text": "ZarooratWala link"},
            {"id": "composer", "kind": "input_field", "text": "Type a message"},
        ],
    }


def test_reveal_actions_stamps_context_menu_intention():
    decision = Action(
        action="ContextClick",
        action_family="reveal_actions",
        semantic_target="content_item",
    )
    exp = intention_expectation_from_decision(decision)
    assert exp["surface"] == "context_menu"
    assert "Forward" in exp["likely_controls"]


def test_stamp_sets_pending_and_expectation():
    state = ExecutionState()
    decision = Action(action="ContextClick", action_family="reveal_actions")
    stamped = stamp_act_intention(state, decision)
    assert stamped["surface"] == "context_menu"
    assert state.act_intention_pending is True
    assert state.unified_last_expectation["surface"] == "context_menu"


def test_fast_remember_does_not_wipe_pending_act_intention():
    state = ExecutionState()
    stamp_act_intention(
        state, Action(action="ContextClick", action_family="reveal_actions")
    )
    proposal = UnifiedProposal()
    proposal.world_model = _conversation_world()
    proposal.observed_state = {"surface": "conversation", "open_conversation": "Pallavi"}
    proposal.expected_transition = {}  # compact path omits this
    _remember_reading(state, proposal)
    assert state.act_intention_pending is True
    assert state.unified_last_expectation["surface"] == "context_menu"


def test_post_act_mismatch_infers_surprise_then_reflect():
    """Live class: reveal → still conversation; AX settle diagnostic; surprise via look."""
    state = ExecutionState()
    stamp_act_intention(
        state,
        Action(
            action="ContextClick",
            action_family="reveal_actions",
            semantic_target="zarooratwala",
            prediction={
                "expected_surface": "context_menu",
                "expected_affordances": ["Forward", "Reply"],
            },
        ),
    )
    # Post-act attribution stays diagnostic — must not be the surprise source.
    state.last_attribution = {
        "effect_kind": "no_transition",
        "outcome": "no_effect",
        "belief_authority": "ax_settle_diagnostic",
        "evidence": {"executor_ok": True},
    }
    assert not _last_action_surprised(state)

    proposal = UnifiedProposal()
    proposal.world_model = _conversation_world()
    proposal.observed_state = dict(_conversation_world())
    # Compact expand has no expected_transition — scoring must still use act stamp.
    expanded = _expand_fast_parsed(
        {
            "surface": "conversation",
            "objects": [{"id": "m1", "role": "message", "text": "ZarooratWala", "point": [10, 20]}],
            "actions": [{"family": "observe", "target": "m1", "score": 0.4}],
            "needs_more_evidence": False,
            "confidence": 0.7,
        },
        frame=1,
    )
    proposal.expected_transition = expanded.get("expected_transition") or {}
    proposal.world_model = expanded["world_model"]

    error = note_prediction_error(state, proposal)
    assert error.get("matched") is False
    assert error.get("predicted_surface") == "context_menu"
    assert state.act_intention_pending is False
    assert _prediction_was_contradicted(state) is True
    assert _last_action_surprised(state) is True

    _remember_reading(state, proposal)

    choice = select_meta_action(
        MetaContext(
            awaiting_verification=True,
            last_action_surprised=_last_action_surprised(state),
            has_grounded_action=True,
        )
    )
    assert choice.action is MetaAction.PERCEIVE


def test_ax_settle_alone_still_not_surprise():
    state = ExecutionState()
    state.last_attribution = {
        "effect_kind": "regression",
        "outcome": "regression",
        "belief_authority": "ax_settle_diagnostic",
        "evidence": {"executor_ok": True},
    }
    assert not _last_action_surprised(state)


def test_decision_prediction_surface_wins_over_family_default():
    decision = Action(
        action="Click",
        action_family="open_entity",
        prediction={"expected_surface": "search"},
    )
    assert intention_expectation_from_decision(decision)["surface"] == "search"
