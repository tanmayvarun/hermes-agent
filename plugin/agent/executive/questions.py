"""Open questions, hypotheses and information gaps as first-class state.

The re-search-the-same-thing failure is what happens when exploration is keyed
by the *action*. The watchdog sees "typed the same query again" and can only
count repetitions; it cannot tell a second search that tests a new spelling
from one that re-asks a question already answered.

Keying exploration by the *question* fixes that at the root. An action is a way
of testing a question ("where is the target message?"); once a question is
answered or abandoned, re-issuing an action that only tests it is visibly
pointless, no counter required. Hypotheses are candidate answers a branch is
built to confirm or refute, and information gaps are the questions the executive
knows it must close before it can act.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


def _norm(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _key(text: str) -> str:
    return _norm(text).lower()


@dataclass
class OpenQuestion:
    """Something the executive needs to know to make progress."""

    text: str = ""
    kind: str = "unknown"  # where_is | which_one | is_available | is_reachable | ...
    raised_frame: int = 0
    status: str = "open"  # open | answered | abandoned
    answer: str = ""
    tested_by: List[str] = field(default_factory=list)  # action families that test it
    evidence: List[str] = field(default_factory=list)
    attempts: int = 0

    @property
    def id(self) -> str:
        return _key(self.text)

    @property
    def is_open(self) -> bool:
        return self.status == "open"

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "text": self.text,
            "kind": self.kind,
            "raised_frame": self.raised_frame,
            "status": self.status,
            "answer": self.answer,
            "tested_by": list(self.tested_by),
            "evidence": self.evidence[-4:],
            "attempts": self.attempts,
        }


@dataclass
class Hypothesis:
    """A candidate answer a branch is built to confirm or refute."""

    statement: str = ""
    question_id: str = ""
    confidence: float = 0.5
    status: str = "proposed"  # proposed | supported | refuted
    supporting: List[str] = field(default_factory=list)
    contradicting: List[str] = field(default_factory=list)
    raised_frame: int = 0

    @property
    def id(self) -> str:
        return _key(self.statement)

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "statement": self.statement,
            "question_id": self.question_id,
            "confidence": round(float(self.confidence or 0.0), 3),
            "status": self.status,
            "supporting": self.supporting[-4:],
            "contradicting": self.contradicting[-4:],
            "raised_frame": self.raised_frame,
        }


@dataclass
class InformationGap:
    """A question the executive must close before it can act."""

    description: str = ""
    question_id: str = ""
    blocking: bool = True
    raised_frame: int = 0

    @property
    def id(self) -> str:
        return _key(self.description)

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "description": self.description,
            "question_id": self.question_id,
            "blocking": self.blocking,
            "raised_frame": self.raised_frame,
        }


@dataclass
class QuestionLedger:
    """The executive's questions, hypotheses and gaps, keyed by question."""

    questions: Dict[str, OpenQuestion] = field(default_factory=dict)
    hypotheses: Dict[str, Hypothesis] = field(default_factory=dict)
    gaps: Dict[str, InformationGap] = field(default_factory=dict)
    # question id -> the exploration key (hypothesis / branch) testing it
    exploration: Dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------- questions

    def ask(
        self,
        text: str,
        *,
        kind: str = "unknown",
        frame: int = 0,
        tested_by: Optional[str] = None,
    ) -> Optional[OpenQuestion]:
        """Raise a question, or return the existing one with the same text.

        A re-ask of an already-answered question does not reopen it; it just
        records another test attempt, which is exactly the signal the old
        watchdog was reconstructing from action repetition.
        """
        text = _norm(text)
        if not text:
            return None
        qid = _key(text)
        question = self.questions.get(qid)
        if question is None:
            question = OpenQuestion(text=text, kind=kind, raised_frame=frame)
            self.questions[qid] = question
        question.attempts += 1
        if tested_by and tested_by not in question.tested_by:
            question.tested_by.append(tested_by)
        return question

    def answer(self, text_or_id: str, answer: str = "", *, evidence: str = "") -> Optional[OpenQuestion]:
        question = self._resolve(text_or_id)
        if question is None:
            return None
        question.status = "answered"
        question.answer = _norm(answer)
        if evidence:
            question.evidence.append(_norm(evidence))
        return question

    def abandon(self, text_or_id: str, *, reason: str = "") -> Optional[OpenQuestion]:
        question = self._resolve(text_or_id)
        if question is None:
            return None
        question.status = "abandoned"
        if reason:
            question.evidence.append(_norm(reason))
        # An abandoned question closes any gap that waited on it.
        for gap in self.gaps.values():
            if gap.question_id == question.id:
                gap.blocking = False
        return question

    def is_answered(self, text_or_id: str) -> bool:
        question = self._resolve(text_or_id)
        return question is not None and question.status == "answered"

    def is_settled(self, text_or_id: str) -> bool:
        question = self._resolve(text_or_id)
        return question is not None and question.status in {"answered", "abandoned"}

    def open_questions(self) -> List[OpenQuestion]:
        return [q for q in self.questions.values() if q.is_open]

    def _resolve(self, text_or_id: str) -> Optional[OpenQuestion]:
        return self.questions.get(_key(text_or_id))

    # ----------------------------------------------------------- hypotheses

    def propose(
        self,
        statement: str,
        *,
        question_id: str = "",
        confidence: float = 0.5,
        frame: int = 0,
    ) -> Optional[Hypothesis]:
        statement = _norm(statement)
        if not statement:
            return None
        hid = _key(statement)
        hyp = self.hypotheses.get(hid)
        if hyp is None:
            hyp = Hypothesis(
                statement=statement,
                question_id=_key(question_id),
                confidence=confidence,
                raised_frame=frame,
            )
            self.hypotheses[hid] = hyp
            if hyp.question_id:
                self.exploration[hyp.question_id] = hid
        return hyp

    def support(self, statement_or_id: str, evidence: str = "") -> Optional[Hypothesis]:
        hyp = self.hypotheses.get(_key(statement_or_id))
        if hyp is None:
            return None
        hyp.status = "supported"
        hyp.confidence = min(1.0, hyp.confidence + 0.2)
        if evidence:
            hyp.supporting.append(_norm(evidence))
        return hyp

    def refute(self, statement_or_id: str, evidence: str = "") -> Optional[Hypothesis]:
        hyp = self.hypotheses.get(_key(statement_or_id))
        if hyp is None:
            return None
        hyp.status = "refuted"
        hyp.confidence = max(0.0, hyp.confidence - 0.3)
        if evidence:
            hyp.contradicting.append(_norm(evidence))
        return hyp

    def hypothesis_for(self, question_id: str) -> Optional[Hypothesis]:
        hid = self.exploration.get(_key(question_id))
        return self.hypotheses.get(hid) if hid else None

    # ----------------------------------------------------------------- gaps

    def declare_gap(
        self,
        description: str,
        *,
        question_id: str = "",
        blocking: bool = True,
        frame: int = 0,
    ) -> Optional[InformationGap]:
        description = _norm(description)
        if not description:
            return None
        gid = _key(description)
        gap = self.gaps.get(gid)
        if gap is None:
            gap = InformationGap(
                description=description,
                question_id=_key(question_id),
                blocking=blocking,
                raised_frame=frame,
            )
            self.gaps[gid] = gap
        else:
            gap.blocking = blocking
        return gap

    def blocking_gaps(self) -> List[InformationGap]:
        return [g for g in self.gaps.values() if g.blocking]

    def blocking_uncertainties(self) -> List[str]:
        """The gaps whose question is still open, phrased for sufficiency."""
        out: List[str] = []
        for gap in self.gaps.values():
            if not gap.blocking:
                continue
            if gap.question_id and self.is_settled(gap.question_id):
                continue
            out.append(gap.description)
        return out

    # -------------------------------------------------------------- exports

    def to_dict(self) -> Dict[str, object]:
        return {
            "questions": [q.to_dict() for q in self.questions.values()],
            "hypotheses": [h.to_dict() for h in self.hypotheses.values()],
            "gaps": [g.to_dict() for g in self.gaps.values()],
            "open_count": len(self.open_questions()),
            "blocking_count": len(self.blocking_gaps()),
        }
