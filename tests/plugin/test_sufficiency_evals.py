"""Component-correctness eval for the DecisionSufficiency computation."""

from __future__ import annotations

from plugin.agent.executive.sufficiency import SufficiencyInputs
from plugin.evals.sufficiency import (
    SUFFICIENCY_CASES,
    SufficiencyCase,
    score_sufficiency_cases,
    summarize_sufficiency,
)


def test_the_labelled_corpus_classifies_perfectly():
    # The corpus is the spec: the real computation must match every label.
    score = score_sufficiency_cases()
    assert score.total == len(SUFFICIENCY_CASES)
    assert score.verdict_accuracy == 1.0, score.failures
    assert score.false_act_rate == 0.0, score.failures


def test_sufficient_verdicts_are_held_at_least_as_firmly_as_blocked_ones():
    score = score_sufficiency_cases()
    assert score.confidence_separation >= 0.0


def test_a_mislabelled_case_is_caught():
    # Claim a clearly-blocked situation should be sufficient; the eval must flag it.
    wrong = SufficiencyCase(
        id="wrong",
        situation="blocked but labelled sufficient",
        inputs=SufficiencyInputs(blocking_uncertainties=["where?"]),
        sufficient=True,
    )
    score = score_sufficiency_cases([wrong])
    assert score.verdict_accuracy == 0.0
    assert score.failures


def test_false_act_is_the_dangerous_error_and_is_counted():
    # Inputs that really are sufficient, but labelled not-sufficient -> a case
    # where the computation would (correctly) act while the label says it must
    # not; this is exactly the false-act the gate guards against.
    case = SufficiencyCase(
        id="false_act",
        situation="a grounded, well-covered frame the label pretends is unsafe",
        inputs=SufficiencyInputs(has_grounded_action=True, coverage=0.9),
        sufficient=False,
    )
    score = score_sufficiency_cases([case])
    assert score.act_unwarranted == 1
    assert score.false_acts == 1
    assert score.false_act_rate == 1.0


def test_missed_act_is_counted_separately():
    case = SufficiencyCase(
        id="missed_act",
        situation="a blocked frame the label pretends is ready",
        inputs=SufficiencyInputs(blocking_uncertainties=["where?"]),
        sufficient=True,
    )
    score = score_sufficiency_cases([case])
    assert score.act_warranted == 1
    assert score.missed_acts == 1
    assert score.missed_act_rate == 1.0
    assert score.false_act_rate == 0.0  # not a dangerous error


def test_unpinned_expectations_are_not_asserted():
    # A case that pins nothing can never fail.
    case = SufficiencyCase(id="loose", situation="anything", inputs=SufficiencyInputs())
    score = score_sufficiency_cases([case])
    assert score.verdict_accuracy == 1.0


def test_summary_exposes_the_key_metrics():
    summary = summarize_sufficiency()
    for key in ("cases", "verdict_accuracy", "false_act_rate", "missed_act_rate", "confidence_separation"):
        assert key in summary


def test_the_hard_gates_pass_on_current_code():
    from plugin.evals.gates import run_gates, blocking_failures

    results = {r.name: r for r in run_gates()}
    assert results["sufficiency_never_acts_when_unwarranted"].passed
    assert results["sufficiency_classifies_every_labelled_case"].passed
    # And they are real blocking gates, not declared known-gaps.
    names = {r.name for r in blocking_failures(list(run_gates()))}
    assert "sufficiency_never_acts_when_unwarranted" not in names
