"""Exploration is keyed by the question an action tests, not the action."""

from __future__ import annotations

from plugin.agent.executive.questions import (
    Hypothesis,
    InformationGap,
    OpenQuestion,
    QuestionLedger,
)
from plugin.agent.executive.workspace import ExecutiveWorkspace, WorkspaceProposal


def test_asking_the_same_question_twice_does_not_duplicate_it():
    ledger = QuestionLedger()
    a = ledger.ask("where is the pdf?", frame=1)
    b = ledger.ask("Where is the PDF?", frame=2)  # same question, different frame/case
    assert a is b
    assert len(ledger.questions) == 1
    assert a.attempts == 2


def test_an_answered_question_reads_as_settled():
    ledger = QuestionLedger()
    ledger.ask("is send enabled?", frame=1)
    ledger.answer("is send enabled?", "yes", evidence="button visible")
    assert ledger.is_answered("is send enabled?")
    assert ledger.is_settled("is send enabled?")
    assert not ledger.open_questions()


def test_re_asking_a_settled_question_records_a_test_but_stays_settled():
    ledger = QuestionLedger()
    ledger.ask("where is the target?", frame=1)
    ledger.answer("where is the target?", "row 3")
    again = ledger.ask("where is the target?", frame=5, tested_by="scroll")
    assert again.status == "answered"
    assert again.attempts == 2
    assert "scroll" in again.tested_by


def test_abandoning_a_question_clears_its_gap():
    ledger = QuestionLedger()
    ledger.declare_gap("target below the fold?", question_id="where is the target?")
    ledger.ask("where is the target?", frame=1)
    assert ledger.blocking_gaps()
    ledger.abandon("where is the target?", reason="not present")
    assert not ledger.blocking_gaps()


def test_blocking_uncertainties_drop_settled_questions():
    ledger = QuestionLedger()
    ledger.declare_gap("is destination reachable?", question_id="reach dest?")
    ledger.ask("reach dest?", frame=1)
    assert ledger.blocking_uncertainties() == ["is destination reachable?"]
    ledger.answer("reach dest?", "yes")
    assert ledger.blocking_uncertainties() == []


def test_a_hypothesis_can_be_supported_and_refuted():
    ledger = QuestionLedger()
    ledger.ask("which row is it?", frame=1)
    ledger.propose("it is row 3", question_id="which row is it?", confidence=0.5, frame=1)
    supported = ledger.support("it is row 3", evidence="matched")
    assert supported.status == "supported"
    assert supported.confidence > 0.5
    refuted = ledger.refute("it is row 3", evidence="mismatch")
    assert refuted.status == "refuted"


def test_hypothesis_is_reachable_by_its_question():
    ledger = QuestionLedger()
    ledger.propose("target is off-screen", question_id="where is target?", frame=1)
    hyp = ledger.hypothesis_for("where is target?")
    assert hyp is not None
    assert hyp.statement == "target is off-screen"


# ------------------------------------------------ workspace integration


def test_workspace_commit_raises_and_answers_questions():
    workspace = ExecutiveWorkspace()
    workspace.commit(
        WorkspaceProposal(
            source="exploration",
            frame=1,
            ask=[OpenQuestion(text="where is the file?", kind="where_is", raised_frame=1)],
            gaps=[InformationGap(description="where is the file?", question_id="where is the file?")],
            hypotheses=[Hypothesis(statement="file is in downloads", question_id="where is the file?")],
        )
    )
    assert workspace.questions.blocking_uncertainties() == ["where is the file?"]
    assert workspace.questions.hypothesis_for("where is the file?") is not None

    verdict = workspace.commit(
        WorkspaceProposal(
            source="exploration",
            frame=2,
            answers=[("where is the file?", "downloads", "listed there")],
        )
    )
    assert workspace.questions.is_answered("where is the file?")
    assert workspace.questions.blocking_uncertainties() == []
    kinds = {d.field for d in verdict.decisions}
    assert "answer" in kinds


def test_workspace_snapshot_includes_questions():
    workspace = ExecutiveWorkspace()
    workspace.commit(
        WorkspaceProposal(
            source="exploration",
            frame=1,
            ask=[OpenQuestion(text="q?", raised_frame=1)],
        )
    )
    snap = workspace.to_dict()
    assert snap["questions"]["open_count"] == 1
