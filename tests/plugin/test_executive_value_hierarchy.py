"""Tests for the info-value function, cognitive modes, and decision ladder."""

from plugin.agent.executive.hierarchy import (
    DELIBERATIVE,
    REACTIVE,
    ModeContext,
    cognitive_mode,
    decision_ladder,
    mode_triggers,
)
from plugin.agent.executive.meta_action import MetaAction, MetaContext
from plugin.agent.executive.sufficiency import DecisionSufficiency
from plugin.agent.executive.value import ValueInputs, action_value, value_breakdown


# --- information value ---------------------------------------------------


def test_progress_beats_a_pure_look_when_probable():
    act = action_value(ValueInputs(progress_probability=0.9, progress_value=1.0))
    look = action_value(ValueInputs(progress_probability=0.0, information_gain=0.5))
    assert act > look


def test_repeat_penalty_sinks_a_redundant_move():
    fresh = action_value(ValueInputs(progress_probability=0.0, information_gain=0.6))
    repeated = action_value(
        ValueInputs(progress_probability=0.0, information_gain=0.6, repeated=True)
    )
    assert repeated < fresh
    assert repeated < 0


def test_risk_and_irreversibility_are_penalised():
    safe = action_value(ValueInputs(progress_probability=0.7, reversibility=1.0, risk=0.0))
    risky = action_value(ValueInputs(progress_probability=0.7, reversibility=0.0, risk=0.8))
    assert risky < safe


def test_breakdown_sums_to_total():
    inp = ValueInputs(progress_probability=0.5, information_gain=0.4, risk=0.2, cost="medium")
    bd = value_breakdown(inp)
    parts = bd["progress"] + bd["information"] + bd["reversibility"] + bd["risk"] + bd["cost"] + bd["repeat"]
    assert abs(parts - bd["total"]) < 1e-6


# --- cognitive modes -----------------------------------------------------


def test_clear_situation_is_reactive():
    assert cognitive_mode(ModeContext()) == REACTIVE


def test_any_trigger_makes_it_deliberative():
    assert cognitive_mode(ModeContext(contradiction=True)) == DELIBERATIVE
    assert cognitive_mode(ModeContext(new_goal=True)) == DELIBERATIVE
    assert cognitive_mode(ModeContext(high_consequence=True)) == DELIBERATIVE


def test_mode_triggers_are_reported():
    triggers = mode_triggers(ModeContext(ambiguous=True, branch_exhausted=True))
    assert "ambiguous" in triggers
    assert "branch_exhausted" in triggers


# --- decision ladder -----------------------------------------------------


def test_ladder_acts_when_grounded_and_sufficient():
    suff = DecisionSufficiency(sufficient_to_act=True)
    choice = decision_ladder(MetaContext(sufficiency=suff, has_grounded_action=True))
    assert choice.action == MetaAction.ACT


def test_ladder_perceives_on_a_blocking_uncertainty():
    suff = DecisionSufficiency(
        sufficient_to_act=False, observe_has_value=True, blocking_uncertainties=["source unresolved"]
    )
    choice = decision_ladder(MetaContext(sufficiency=suff))
    assert choice.action == MetaAction.PERCEIVE


def test_ladder_does_not_reperceive_a_settled_question():
    suff = DecisionSufficiency(
        sufficient_to_act=False, observe_has_value=True, blocking_uncertainties=["source unresolved"]
    )
    choice = decision_ladder(
        MetaContext(sufficiency=suff, question_settled=True, has_grounded_action=True)
    )
    # With the question settled, it must not loop on PERCEIVE.
    assert choice.action != MetaAction.PERCEIVE


def test_ladder_asks_user_on_a_hard_block():
    choice = decision_ladder(MetaContext(hard_block=True))
    assert choice.action == MetaAction.ASK


def test_ladder_plans_a_new_branch_on_a_stale_branch():
    """A stale branch asks *where* to go next, not merely that it should retreat.

    Retreating without a direction is what let the agent fall back on whichever
    untried family sat nearest on the frontier; rung 4 now gathers information
    about the action space (strategic search) and the retreat follows its plan.
    """
    suff = DecisionSufficiency(sufficient_to_act=False, observe_has_value=False)
    choice = decision_ladder(MetaContext(sufficiency=suff, branch_stale=True))
    assert choice.action == MetaAction.THINK
