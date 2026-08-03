"""Meta-action selection: what *kind* of step is worth taking now.

The old loop had one shape per iteration: observe, then decide, then act. That
made perception unconditional -- the agent looked again every turn whether or
not another look could tell it anything, which is exactly the wasted-step and
re-search behaviour the executive is meant to end.

This module names the moves the executive can make and picks among them by
value rather than by position in a fixed sequence:

- THINK      consult the reasoning model; cheap-ish, resolves genuine ambiguity
- PERCEIVE   look again; only worth it when a look could close a real gap
- PROBE      take a cheap reversible action to *reveal* information
- ACT        commit to the best grounded action toward the goal
- VERIFY     confirm the last action produced the predicted world
- BACKTRACK  undo / retreat when the branch has gone stale
- ASK_USER   stop and ask, when nothing the agent can do resolves the block

The selection is a pure function of what the executive already knows, so it is
testable in isolation and reusable across domains.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from plugin.agent.executive.sufficiency import DecisionSufficiency


class MetaAction(str, Enum):
    THINK = "think"
    PERCEIVE = "perceive"
    PROBE = "probe"
    ACT = "act"
    VERIFY = "verify"
    BACKTRACK = "backtrack"
    ASK_USER = "ask_user"


@dataclass
class MetaContext:
    """The signals the selector reads. All optional; each domain fills what it has."""

    sufficiency: Optional[DecisionSufficiency] = None
    has_grounded_action: bool = False
    # An action was just executed and its predicted transition is unverified.
    awaiting_verification: bool = False
    last_action_surprised: bool = False
    # Exploration has gone stale / budget on the current branch is spent.
    branch_stale: bool = False
    # Nothing the agent can do resolves the block (e.g. login wall, permission).
    hard_block: bool = False
    # A reversible probing action is available that would reveal information.
    probe_available: bool = False
    # Steps remaining before the whole task budget is spent.
    steps_remaining: int = 99
    # The executive is confident enough that consulting the model is warranted.
    ambiguous: bool = False
    # The blocking question a look/probe would test is already settled with
    # unchanged evidence — re-asking it is redundant and must not win.
    question_settled: bool = False


@dataclass
class MetaChoice:
    action: MetaAction = MetaAction.ACT
    reason: str = ""
    scores: Dict[str, float] = field(default_factory=dict)

    @property
    def observe_wanted(self) -> bool:
        return self.action in {MetaAction.PERCEIVE, MetaAction.PROBE}

    @property
    def suppress_observe(self) -> bool:
        return not self.observe_wanted

    def to_dict(self) -> Dict[str, object]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "scores": {k: round(v, 3) for k, v in self.scores.items()},
        }


def select_meta_action(ctx: MetaContext) -> MetaChoice:
    """Score each move and take the best. Order encodes hard precedence.

    The precedence is deliberate rather than purely numeric: a hard block can
    only be answered by asking the user, and a just-executed action must be
    verified before the agent decides anything new. Below those, value decides.
    """
    scores: Dict[str, float] = {}

    if ctx.hard_block:
        return MetaChoice(MetaAction.ASK_USER, "hard block: no self-serve move resolves it", {"ask_user": 1.0})

    if ctx.awaiting_verification and ctx.last_action_surprised:
        return MetaChoice(MetaAction.VERIFY, "last action surprised us; confirm the world", {"verify": 1.0})

    suff = ctx.sufficiency

    # A look/probe that only re-tests an already-settled question is the
    # re-search failure class; apply the info-value repeat penalty so it cannot
    # win over acting or backtracking.
    from plugin.agent.executive.value import EPSILON_REPEAT

    reask_penalty = EPSILON_REPEAT if ctx.question_settled else 0.0

    # PERCEIVE is worth it only when a look could close a gap that matters.
    perceive = 0.0
    if suff is not None and suff.observe_has_value:
        perceive = 0.8 if suff.blocking_uncertainties else 0.6
    scores["perceive"] = round(perceive - reask_penalty, 4)

    # PROBE when we cannot see what we need but looking again would not help --
    # a reversible action that changes the surface may reveal it.
    probe = 0.0
    if (
        ctx.probe_available
        and suff is not None
        and not suff.sufficient_to_act
        and not suff.observe_has_value
    ):
        probe = 0.7
    scores["probe"] = round(probe - reask_penalty, 4)

    # BACKTRACK when exploration has gone stale and nothing blocks that a look
    # would resolve.
    backtrack = 0.0
    if ctx.branch_stale and (suff is None or not suff.observe_has_value):
        backtrack = 0.65
    scores["backtrack"] = backtrack

    # THINK when the situation is ambiguous and we are not merely short of a look.
    think = 0.0
    if ctx.ambiguous and (suff is None or not suff.observe_has_value):
        think = 0.55
    scores["think"] = think

    # ACT when we have a grounded move and enough evidence to trust it.
    act = 0.0
    if ctx.has_grounded_action and (suff is None or suff.sufficient_to_act):
        act = 0.75
    elif ctx.has_grounded_action:
        act = 0.4  # can act, but evidence is thin; other moves may beat it
    scores["act"] = act

    # Running out of budget: prefer committing to the best action over more looking.
    if ctx.steps_remaining <= 1 and ctx.has_grounded_action:
        scores["act"] = max(scores["act"], 0.95)

    best_key = max(scores, key=lambda k: scores[k]) if scores else "act"
    best_val = scores.get(best_key, 0.0)
    if best_val <= 0.0:
        # Nothing scored: default to acting if we can, else looking.
        if ctx.has_grounded_action:
            return MetaChoice(MetaAction.ACT, "no signal; commit to grounded action", scores)
        return MetaChoice(MetaAction.PERCEIVE, "no signal and no action; look again", scores)

    chosen = MetaAction(best_key)
    reason = _reason_for(chosen, suff)
    return MetaChoice(chosen, reason, scores)


def _reason_for(action: MetaAction, suff: Optional[DecisionSufficiency]) -> str:
    if suff is not None and suff.reason and action in {MetaAction.PERCEIVE, MetaAction.PROBE, MetaAction.ACT}:
        return f"{action.value}: {suff.reason}"
    return {
        MetaAction.PERCEIVE: "a look could close a real gap",
        MetaAction.PROBE: "reveal information a look cannot",
        MetaAction.BACKTRACK: "branch stale; retreat and repair",
        MetaAction.THINK: "ambiguous; consult reasoning",
        MetaAction.ACT: "evidence sufficient; commit",
        MetaAction.VERIFY: "confirm predicted world",
        MetaAction.ASK_USER: "escalate to user",
    }.get(action, action.value)
