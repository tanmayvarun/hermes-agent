"""PerceptionQuery — a look with an information objective, not a blank refresh.

The design's rule is "no generic Observe": every perception carries the
questions it is meant to answer, where to focus, how deep to look, and a
completion condition that says when the look has done its job. Before this,
perception was a full-screen refresh invoked every loop with no objective, so
the executive could not tell a *useful* look from a reflexive one, nor reject a
re-look whose question was already settled.

``PerceptionQuery`` carries that objective. ``from_sufficiency`` derives one
from the executive's current judgement (its blocking uncertainties and declared
gaps become the questions), and ``is_settled_by`` answers whether a query is
redundant given what the executive already believes with unchanged evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence


@dataclass
class PerceptionQuery:
    """What a look is for."""

    # The concrete questions this look must answer (from blocking uncertainties
    # and declared evidence gaps). A look with no questions is a generic refresh
    # and should be treated as low-value.
    questions: List[str] = field(default_factory=list)
    # Where to look: an entity/region hint, or "" for the whole surface.
    focus: str = ""
    # "shallow" (chrome/frontier only) or "deep" (full re-read).
    depth: str = "shallow"
    # A one-line statement of the information objective, for logging.
    objective: str = ""
    # The condition under which the look is complete (e.g. "target row visible").
    completion_condition: str = ""

    @property
    def is_generic(self) -> bool:
        """A query with no objective is the generic Observe the design forbids."""
        return not self.questions and not self.objective

    def to_dict(self) -> dict:
        return {
            "questions": list(self.questions),
            "focus": self.focus,
            "depth": self.depth,
            "objective": self.objective,
            "completion_condition": self.completion_condition,
            "is_generic": self.is_generic,
        }

    def is_settled_by(
        self, settled_questions: Sequence[str], *, evidence_changed: bool
    ) -> bool:
        """True when re-asking is redundant: every question already settled and
        nothing about the evidence has changed since it was settled."""
        if evidence_changed:
            return False
        if not self.questions:
            return False
        settled = {_norm(q) for q in settled_questions if _norm(q)}
        return all(_norm(q) in settled for q in self.questions)


def _norm(text: object) -> str:
    return " ".join(str(text or "").strip().lower().split())


def from_sufficiency(
    sufficiency,
    *,
    focus: str = "",
    depth: Optional[str] = None,
) -> PerceptionQuery:
    """Build the look's objective from the executive's current judgement."""
    questions = list(getattr(sufficiency, "blocking_uncertainties", None) or [])
    # A blocking uncertainty warrants a deeper look; a mere coverage gap does not.
    resolved_depth = depth or ("deep" if questions else "shallow")
    objective = getattr(sufficiency, "reason", "") or ""
    completion = ""
    if questions:
        completion = f"resolved: {questions[0]}"
    return PerceptionQuery(
        questions=[str(q).strip() for q in questions if str(q).strip()],
        focus=focus,
        depth=resolved_depth,
        objective=objective,
        completion_condition=completion,
    )
