"""DecisionSufficiency — the executive's judgement of whether it can act yet.

The old loop answered "should I observe again?" with a streak counter: two
identical observes in a row and it stopped. That is a proxy. The real question
is whether the evidence in hand is enough to choose an action, and if not,
whether *observing* is the thing that would close the gap.

``assess_sufficiency`` answers that from three inputs the executive already has:
what the perceptor said it could not establish (evidence gaps), what the domain
knows is still unresolved (blocking uncertainties), and whether observation is
still yielding anything (did the last observe change the world). It is
domain-agnostic: WhatsApp supplies "source object unresolved" as a blocking
uncertainty, the filesystem domain supplies its own, and the judgement is the
same.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence


@dataclass
class SufficiencyInputs:
    """Everything the judgement reads. All optional so any caller can use it."""

    # Uncertainties the domain says must be resolved before acting, each of
    # which continued observation/exploration is expected to resolve.
    blocking_uncertainties: Sequence[str] = ()
    # Evidence the perceptor itself declared it could not establish this frame.
    declared_evidence_gaps: Sequence[str] = ()
    # A grounded, admissible non-observe action exists right now.
    has_grounded_action: bool = False
    # Did the most recent observe change the world at all?
    last_observe_changed_world: bool = True
    # How many times in a row observe returned the same state.
    identical_observe_streak: int = 0
    # Fraction of the surface the perceptor reported it covered, if known.
    coverage: Optional[float] = None
    # A prior suppression that has not yet been cleared by real change.
    previously_suppressed: bool = False
    # The most recent action did not produce the world we predicted (no
    # transition, a regression, or an unexpected surface). A surprise means the
    # executive's model of "what just happened" is wrong, so a look has value
    # even if the evidence otherwise looked sufficient to act.
    last_action_surprised: bool = False


@dataclass
class DecisionSufficiency:
    """The verdict, plus why."""

    sufficient_to_act: bool = False
    observe_has_value: bool = False
    suppress_observe: bool = False
    needs_exploration: bool = False
    blocking_uncertainties: List[str] = field(default_factory=list)
    useful_information_actions: List[str] = field(default_factory=list)
    # Which action families the current evidence is enough to commit to. Empty
    # when the executive is not yet sure of any (it should gather first).
    sufficient_for_which_actions: List[str] = field(default_factory=list)
    # How strongly the executive holds this verdict, 0..1. Driven by coverage
    # and by whether anything is still blocking or under-seen.
    confidence: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "sufficient_to_act": self.sufficient_to_act,
            "observe_has_value": self.observe_has_value,
            "suppress_observe": self.suppress_observe,
            "needs_exploration": self.needs_exploration,
            "blocking_uncertainties": list(self.blocking_uncertainties),
            "useful_information_actions": list(self.useful_information_actions),
            "sufficient_for_which_actions": list(self.sufficient_for_which_actions),
            "confidence": round(float(self.confidence or 0.0), 3),
            "reason": self.reason,
        }


# Observing yields nothing new once the world has repeated this many times.
STALE_OBSERVE_STREAK = 2
# Below this, the perceptor is telling us it barely saw the surface.
THIN_COVERAGE = 0.34


def assess_sufficiency(inputs: SufficiencyInputs) -> DecisionSufficiency:
    """Decide whether the executive can act, and whether observing would help.

    The shape mirrors the judgement the forward-observe heuristics used to make
    implicitly:

    - a blocking uncertainty means keep gathering evidence (observe/explore),
      never suppress, because that is the thing the agent is still hunting for;
    - with nothing blocking but observation gone stale, stop re-observing and
      repair instead;
    - otherwise the evidence is enough to act on.
    """
    blocking = [str(item).strip() for item in inputs.blocking_uncertainties if str(item).strip()]
    gaps = [str(item).strip() for item in inputs.declared_evidence_gaps if str(item).strip()]
    thin_coverage = inputs.coverage is not None and inputs.coverage < THIN_COVERAGE
    stale = (
        inputs.previously_suppressed
        or int(inputs.identical_observe_streak or 0) >= STALE_OBSERVE_STREAK
    )
    # Coverage is the executive's best single read on how much it saw; absent a
    # reported value, assume a middling view rather than perfect knowledge.
    cov = float(inputs.coverage) if inputs.coverage is not None else 0.7
    grounded = ["grounded_action"] if inputs.has_grounded_action else []
    surprised = bool(inputs.last_action_surprised)

    if blocking:
        # Still hunting for something the domain named. Observation is how the
        # agent finds it, so it always has value here, even across a stale
        # streak: the object may simply be off-screen, not absent.
        return DecisionSufficiency(
            sufficient_to_act=False,
            observe_has_value=True,
            suppress_observe=False,
            needs_exploration=True,
            blocking_uncertainties=blocking,
            useful_information_actions=["observe", "explore"],
            sufficient_for_which_actions=[],
            confidence=round(min(cov, 0.6), 3),
            reason="blocking uncertainty: " + ", ".join(blocking[:3]),
        )

    if surprised:
        # The last action did not produce the world we predicted. Before acting
        # again, look: re-perceiving is how the executive re-understands what
        # actually happened (an unexpected surface, a click that landed on the
        # wrong region) instead of blindly repeating a move that already failed.
        return DecisionSufficiency(
            sufficient_to_act=False,
            observe_has_value=True,
            suppress_observe=False,
            needs_exploration=True,
            useful_information_actions=["observe"],
            sufficient_for_which_actions=[],
            confidence=round(min(cov, 0.4), 3),
            reason="last action surprised us; re-perceive before re-acting",
        )

    if gaps and not stale:
        # The perceptor named a gap and observing is still moving the world, so
        # another look is the cheapest way to close it before acting.
        return DecisionSufficiency(
            sufficient_to_act=inputs.has_grounded_action,
            observe_has_value=True,
            suppress_observe=False,
            needs_exploration=True,
            blocking_uncertainties=[],
            useful_information_actions=["observe"],
            sufficient_for_which_actions=grounded if inputs.has_grounded_action else [],
            confidence=round(min(cov, 0.55), 3),
            reason="declared evidence gap: " + ", ".join(gaps[:3]),
        )

    if thin_coverage and not stale:
        return DecisionSufficiency(
            sufficient_to_act=inputs.has_grounded_action,
            observe_has_value=True,
            suppress_observe=False,
            needs_exploration=True,
            useful_information_actions=["observe"],
            sufficient_for_which_actions=grounded if inputs.has_grounded_action else [],
            confidence=round(cov, 3),
            reason=f"thin coverage {inputs.coverage:.2f}",
        )

    if stale:
        # Nothing blocking and observing has stopped telling us anything. Stop
        # looking and repair the branch instead.
        return DecisionSufficiency(
            sufficient_to_act=inputs.has_grounded_action,
            observe_has_value=False,
            suppress_observe=True,
            needs_exploration=True,
            useful_information_actions=[],
            sufficient_for_which_actions=grounded,
            confidence=round(0.5 * cov, 3),
            reason="observation stale, no new evidence",
        )

    # "Sufficient" without a grounded UI move is a lie — it drove THINK thrash
    # with act=0 while the ladder skipped ACT. Evidence readiness is not actuation.
    return DecisionSufficiency(
        sufficient_to_act=bool(inputs.has_grounded_action),
        observe_has_value=not inputs.has_grounded_action,
        suppress_observe=False,
        needs_exploration=not inputs.has_grounded_action,
        useful_information_actions=[] if inputs.has_grounded_action else ["observe"],
        sufficient_for_which_actions=grounded,
        confidence=round(max(0.6, cov), 3),
        reason=(
            "evidence sufficient to act"
            if inputs.has_grounded_action
            else "evidence ready but no grounded action geometry yet"
        ),
    )
