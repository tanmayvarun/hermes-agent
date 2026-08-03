"""The executive picks what *kind* of step to take, by value, not by position."""

from __future__ import annotations

from plugin.agent.executive.meta_action import (
    MetaAction,
    MetaContext,
    select_meta_action,
)
from plugin.agent.executive.sufficiency import SufficiencyInputs, assess_sufficiency


def _suff(**kwargs):
    return assess_sufficiency(SufficiencyInputs(**kwargs))


def test_a_hard_block_escalates_to_the_user():
    choice = select_meta_action(MetaContext(hard_block=True))
    assert choice.action is MetaAction.ASK_USER


def test_assess_threads_a_hard_block_to_ask_user():
    # A hard block computed by the controller (e.g. backtracks exhausted) must
    # reach the selector through assess_executive_judgement and win.
    from plugin.agent.executive.sync import assess_executive_judgement
    from plugin.agent.runtime.state import ExecutionState

    state = ExecutionState()
    _suff_verdict, meta = assess_executive_judgement(
        state, has_grounded_action=False, hard_block=True
    )
    assert meta.action is MetaAction.ASK_USER


def test_a_surprise_forces_verification_before_anything_else():
    choice = select_meta_action(
        MetaContext(awaiting_verification=True, last_action_surprised=True, has_grounded_action=True)
    )
    assert choice.action is MetaAction.VERIFY


def test_a_blocking_uncertainty_makes_the_agent_perceive():
    choice = select_meta_action(
        MetaContext(sufficiency=_suff(blocking_uncertainties=["where is target?"]))
    )
    assert choice.action is MetaAction.PERCEIVE
    assert choice.observe_wanted is True
    assert choice.suppress_observe is False


def test_sufficient_evidence_with_an_action_commits():
    choice = select_meta_action(
        MetaContext(sufficiency=_suff(has_grounded_action=True), has_grounded_action=True)
    )
    assert choice.action is MetaAction.ACT
    assert choice.suppress_observe is True


def test_stale_exploration_backtracks_rather_than_looking_again():
    choice = select_meta_action(
        MetaContext(sufficiency=_suff(identical_observe_streak=2), branch_stale=True)
    )
    assert choice.action is MetaAction.BACKTRACK
    assert choice.suppress_observe is True


def test_probe_when_looking_will_not_help_but_a_reversible_action_reveals():
    # Not sufficient to act, observing is stale, but a probe is available.
    suff = _suff(identical_observe_streak=2)
    choice = select_meta_action(
        MetaContext(sufficiency=suff, probe_available=True, has_grounded_action=False)
    )
    assert choice.action is MetaAction.PROBE
    assert choice.observe_wanted is True


def test_running_out_of_budget_commits_to_the_best_action():
    choice = select_meta_action(
        MetaContext(
            sufficiency=_suff(blocking_uncertainties=["x"]),
            has_grounded_action=True,
            steps_remaining=1,
        )
    )
    assert choice.action is MetaAction.ACT


def test_ambiguity_without_a_missing_look_consults_reasoning():
    choice = select_meta_action(
        MetaContext(sufficiency=_suff(identical_observe_streak=0), ambiguous=True)
    )
    assert choice.action is MetaAction.THINK


def test_no_signal_and_no_action_defaults_to_looking():
    choice = select_meta_action(MetaContext(sufficiency=_suff(has_grounded_action=False)))
    assert choice.action is MetaAction.PERCEIVE


def test_a_settled_question_is_not_re_perceived():
    # A blocking uncertainty would normally make the agent PERCEIVE, but if that
    # question is already settled with unchanged evidence, re-asking must lose to
    # committing the grounded action instead — the re-search failure class.
    choice = select_meta_action(
        MetaContext(
            sufficiency=_suff(blocking_uncertainties=["where is target?"], has_grounded_action=True),
            has_grounded_action=True,
            question_settled=True,
        )
    )
    assert choice.action is MetaAction.ACT
    # The look was penalised down from its unpenalised 0.8 to at most zero.
    assert choice.scores["perceive"] <= 0.0


def test_choice_serialises_with_scores():
    choice = select_meta_action(
        MetaContext(sufficiency=_suff(has_grounded_action=True), has_grounded_action=True)
    )
    payload = choice.to_dict()
    assert payload["action"] == "act"
    assert "scores" in payload and payload["reason"]
