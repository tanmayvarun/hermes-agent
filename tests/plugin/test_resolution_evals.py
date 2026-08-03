"""The self-contained resolution skill must transfer across domains, not just chats."""

from __future__ import annotations

from plugin.evals.resolution import (
    ResolutionCase,
    score_multi_resolution_cases,
    score_resolution_cases,
    summarize_resolution,
)


def test_every_labelled_case_is_graded_correctly():
    score = score_resolution_cases()
    assert not score.failures, "resolution skill mislabelled: " + "; ".join(score.failures)
    assert score.accuracy == 1.0


def test_skill_spans_multiple_domains():
    # The whole point is transfer: chats, files, and browser tabs at minimum.
    score = score_resolution_cases()
    assert score.domains >= 3


def test_false_fast_path_rate_is_zero():
    # The dangerous error — waving an ambiguous/risky pick through the fast path
    # without consulting the LLM — must never happen on the labelled set.
    score = score_resolution_cases()
    assert score.false_fast_path_rate == 0.0


def test_fast_path_recall_and_escalation_recall_are_perfect():
    score = score_resolution_cases()
    assert score.fast_path_true_positive_rate == 1.0
    assert score.escalation_recall == 1.0


def test_summary_shape():
    summary = summarize_resolution()
    for key in (
        "cases",
        "domains",
        "accuracy",
        "fast_path_true_positive_rate",
        "escalation_recall",
        "false_fast_path_rate",
        "multi",
    ):
        assert key in summary
    assert "mean_recall" in summary["multi"]


def test_multi_resolution_returns_the_whole_matching_set():
    score = score_multi_resolution_cases()
    assert not score.failures, "resolve_many mislabelled: " + "; ".join(score.failures)
    assert score.set_exact_match_rate == 1.0
    assert score.mean_recall == 1.0
    assert score.domains >= 3


def test_irreversible_send_needs_a_clear_leading_match():
    # Two namesakes as a send destination is not a true positive, in any domain.
    score = score_resolution_cases(
        [
            ResolutionCase(
                id="probe",
                domain="chat",
                referent="Sam",
                candidates=["Sam (work)", "Sam (home)"],
                consequence="irreversible",
                expect_fast_path=False,
            )
        ]
    )
    assert score.escalate_hits == 1
    assert score.false_fast_paths == 0
