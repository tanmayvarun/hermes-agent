"""Tests for PerceptionQuery — a look with an information objective."""

from plugin.agent.executive.perception_query import (
    PerceptionQuery,
    from_sufficiency,
)
from plugin.agent.executive.sufficiency import DecisionSufficiency


def test_a_query_without_questions_is_generic():
    assert PerceptionQuery().is_generic is True
    assert PerceptionQuery(objective="find the target row").is_generic is False
    assert PerceptionQuery(questions=["is it below the fold?"]).is_generic is False


def test_from_sufficiency_carries_the_blocking_uncertainties():
    suff = DecisionSufficiency(
        blocking_uncertainties=["source object unresolved"],
        reason="blocking uncertainty: source object unresolved",
    )
    query = from_sufficiency(suff, focus="chat_list")
    assert query.questions == ["source object unresolved"]
    assert query.focus == "chat_list"
    assert query.depth == "deep"  # a blocking uncertainty warrants a deep look
    assert query.completion_condition


def test_from_sufficiency_without_blockers_is_shallow():
    suff = DecisionSufficiency(blocking_uncertainties=[], reason="thin coverage 0.20")
    query = from_sufficiency(suff)
    assert query.depth == "shallow"


def test_settled_query_is_redundant_when_evidence_unchanged():
    query = PerceptionQuery(questions=["source object unresolved"])
    assert query.is_settled_by(["source object unresolved"], evidence_changed=False) is True


def test_settled_query_is_worth_re_asking_when_evidence_changed():
    query = PerceptionQuery(questions=["source object unresolved"])
    assert query.is_settled_by(["source object unresolved"], evidence_changed=True) is False


def test_unsettled_question_is_not_redundant():
    query = PerceptionQuery(questions=["target row visible?"])
    assert query.is_settled_by(["source object unresolved"], evidence_changed=False) is False
