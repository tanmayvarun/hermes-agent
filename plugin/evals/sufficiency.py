"""Component-correctness eval for the DecisionSufficiency computation.

This is the bottom of the pyramid for the executive brain. Everything the agent
does downstream — which meta-action it picks, whether it perceives again or
commits — is a function of the sufficiency verdict. If `assess_sufficiency`
mislabels a situation, no amount of good policy above it can recover: a false
"sufficient_to_act" makes the agent commit blind; a false "observe_has_value"
makes it loop looking at a settled world.

Unlike `plugin/evals/executive.py` (which correlates verdicts with *outcomes*
over live run logs, a closed-loop latitude), this eval checks the *computation
itself* against a labelled set of situations with a known-correct verdict. It is
deterministic, needs no run logs, and is meant to be gated hard: a labelled case
that flips is a regression in the agent's judgement, full stop.

The two metrics that matter most are asymmetric:

- false_act_rate : of situations where acting is NOT yet warranted, how many did
                   the verdict call sufficient_to_act? This is the dangerous one
                   and must stay at zero.
- missed_act_rate: of situations where acting IS warranted, how many did the
                   verdict withhold? Wasteful, not dangerous.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from plugin.agent.executive.sufficiency import (
    DecisionSufficiency,
    SufficiencyInputs,
    assess_sufficiency,
)


@dataclass(frozen=True)
class SufficiencyCase:
    """One situation with the verdict a correct executive must reach.

    Any expectation left as ``None`` is not asserted for that case, so a case can
    pin only the dimension it is about (e.g. a safety case pins ``sufficient``
    without over-constraining ``observe``).
    """

    id: str
    situation: str
    inputs: SufficiencyInputs
    sufficient: Optional[bool] = None
    observe: Optional[bool] = None
    suppress: Optional[bool] = None


# The labelled corpus. Each case is a decision the executive must get right;
# several are drawn directly from the ZarooratWala forward journey, where the
# wrong verdict produced the loops we actually saw.
SUFFICIENCY_CASES: Sequence[SufficiencyCase] = (
    SufficiencyCase(
        id="clean_frame_with_action",
        situation="Well-covered frame with a grounded action available.",
        inputs=SufficiencyInputs(has_grounded_action=True, coverage=0.9),
        sufficient=True,
        observe=False,
        suppress=False,
    ),
    SufficiencyCase(
        id="blocking_uncertainty_keeps_looking",
        situation="Source object not yet resolved; must keep gathering evidence.",
        inputs=SufficiencyInputs(blocking_uncertainties=["source object unresolved"]),
        sufficient=False,
        observe=True,
        suppress=False,
    ),
    SufficiencyCase(
        id="blocking_beats_stale_streak",
        situation="Still hunting a named object across a stale streak; it may be off-screen.",
        inputs=SufficiencyInputs(
            blocking_uncertainties=["source object unresolved"], identical_observe_streak=5
        ),
        sufficient=False,
        observe=True,
        suppress=False,
    ),
    SufficiencyCase(
        id="destination_ambiguous_never_acts",
        situation="Forward picker with an ambiguous destination — acting blind could send to the wrong chat.",
        inputs=SufficiencyInputs(blocking_uncertainties=["destination ambiguous"], coverage=0.9),
        sufficient=False,
        observe=True,
    ),
    SufficiencyCase(
        id="stale_nothing_blocking_suppresses",
        situation="Nothing blocking and observing stopped changing the world.",
        inputs=SufficiencyInputs(identical_observe_streak=2),
        observe=False,
        suppress=True,
    ),
    SufficiencyCase(
        id="stale_with_action_commits",
        situation="Observing is stale, nothing blocking, and a grounded action exists — stop looking, act.",
        inputs=SufficiencyInputs(identical_observe_streak=2, has_grounded_action=True),
        sufficient=True,
        observe=False,
        suppress=True,
    ),
    SufficiencyCase(
        id="prior_suppression_sticks",
        situation="A suppression that has not been cleared by real change stays in force.",
        inputs=SufficiencyInputs(previously_suppressed=True),
        observe=False,
        suppress=True,
    ),
    SufficiencyCase(
        id="declared_gap_earns_a_look",
        situation="Perceptor named a gap and the world is still moving.",
        inputs=SufficiencyInputs(declared_evidence_gaps=["is the target below the fold?"]),
        observe=True,
        suppress=False,
    ),
    SufficiencyCase(
        id="declared_gap_does_not_override_stale",
        situation="A named gap does not justify re-looking once observation has gone stale.",
        inputs=SufficiencyInputs(
            declared_evidence_gaps=["is the target below the fold?"], identical_observe_streak=2
        ),
        observe=False,
        suppress=True,
    ),
    SufficiencyCase(
        id="thin_coverage_worth_a_look",
        situation="Perceptor reported it barely saw the surface.",
        inputs=SufficiencyInputs(coverage=0.2, has_grounded_action=True),
        observe=True,
        suppress=False,
    ),
    SufficiencyCase(
        id="full_coverage_commits",
        situation="Full coverage with a grounded action — no reason to re-observe.",
        inputs=SufficiencyInputs(coverage=1.0, has_grounded_action=True),
        sufficient=True,
        observe=False,
        suppress=False,
    ),
    SufficiencyCase(
        id="forward_ready_commits",
        situation="ZarooratWala: source open, target picked, action grounded, surface well seen.",
        inputs=SufficiencyInputs(has_grounded_action=True, coverage=0.95),
        sufficient=True,
        observe=False,
        suppress=False,
    ),
)


@dataclass
class SufficiencyScore:
    total: int = 0
    verdict_correct: int = 0
    # Asymmetric error accounting.
    act_warranted: int = 0
    missed_acts: int = 0
    act_unwarranted: int = 0
    false_acts: int = 0
    # Confidence separation: sufficient verdicts should out-confidence blocked ones.
    sufficient_confidence: List[float] = field(default_factory=list)
    blocked_confidence: List[float] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)

    @property
    def verdict_accuracy(self) -> float:
        return round(self.verdict_correct / self.total, 4) if self.total else 1.0

    @property
    def false_act_rate(self) -> float:
        """The dangerous error: called sufficient when acting was not warranted."""
        return round(self.false_acts / self.act_unwarranted, 4) if self.act_unwarranted else 0.0

    @property
    def missed_act_rate(self) -> float:
        """The wasteful error: withheld action when it was warranted."""
        return round(self.missed_acts / self.act_warranted, 4) if self.act_warranted else 0.0

    @property
    def confidence_separation(self) -> float:
        """Mean confidence on sufficient cases minus mean on blocked cases.

        Should be >= 0: a verdict that says "act" ought to be held at least as
        firmly as one that says "I cannot yet".
        """
        if not self.sufficient_confidence or not self.blocked_confidence:
            return 0.0
        suff = sum(self.sufficient_confidence) / len(self.sufficient_confidence)
        blocked = sum(self.blocked_confidence) / len(self.blocked_confidence)
        return round(suff - blocked, 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cases": self.total,
            "verdict_accuracy": self.verdict_accuracy,
            "false_act_rate": self.false_act_rate,
            "missed_act_rate": self.missed_act_rate,
            "confidence_separation": self.confidence_separation,
            "failures": self.failures[:8],
        }


def _mismatch(expected: Optional[bool], actual: bool) -> bool:
    return expected is not None and expected != actual


def score_sufficiency_cases(
    cases: Sequence[SufficiencyCase] = SUFFICIENCY_CASES,
) -> SufficiencyScore:
    """Run every labelled case through the real computation and grade it."""
    score = SufficiencyScore()
    for case in cases:
        verdict: DecisionSufficiency = assess_sufficiency(case.inputs)
        score.total += 1

        mismatches = []
        if _mismatch(case.sufficient, verdict.sufficient_to_act):
            mismatches.append(f"sufficient={verdict.sufficient_to_act} (want {case.sufficient})")
        if _mismatch(case.observe, verdict.observe_has_value):
            mismatches.append(f"observe={verdict.observe_has_value} (want {case.observe})")
        if _mismatch(case.suppress, verdict.suppress_observe):
            mismatches.append(f"suppress={verdict.suppress_observe} (want {case.suppress})")

        if mismatches:
            score.failures.append(f"{case.id}: " + ", ".join(mismatches))
        else:
            score.verdict_correct += 1

        # Asymmetric act accounting, only for cases that pinned `sufficient`.
        if case.sufficient is True:
            score.act_warranted += 1
            if not verdict.sufficient_to_act:
                score.missed_acts += 1
        elif case.sufficient is False:
            score.act_unwarranted += 1
            if verdict.sufficient_to_act:
                score.false_acts += 1

        if case.sufficient is True:
            score.sufficient_confidence.append(float(verdict.confidence or 0.0))
        elif case.sufficient is False:
            score.blocked_confidence.append(float(verdict.confidence or 0.0))

    return score


def summarize_sufficiency(score: Optional[SufficiencyScore] = None) -> Dict[str, Any]:
    return (score or score_sufficiency_cases()).to_dict()
