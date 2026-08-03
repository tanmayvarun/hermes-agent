"""The executive's decision hierarchy and its two cognitive modes.

The design specifies an ordered ladder the runtime walks every step:

    1. goal already complete?           -> stop
    2. grounded low-risk advancing move? -> ACT
    3. a blocking uncertainty?           -> the info action that resolves it
    4. local exploration exhausted?      -> BACKTRACK / broaden
    5. no strategy clear?                -> THINK (consult the model)
    6. no safe route at all?             -> ASK_USER

and two cognitive modes:

    - deliberative: new goal, ambiguity, exhausted branch, high-consequence
      action, contradicted beliefs, or no matching procedure -> use the strong
      reasoning model;
    - reactive: clear intention, grounded action, known transition, low risk ->
      deterministic / fast path.

``select_meta_action`` scores moves by value; this module expresses the *order*
and the *mode* explicitly, so the runtime walks one ladder instead of leaving
the precedence implicit across scattered flags.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from plugin.agent.executive.meta_action import MetaAction, MetaChoice, MetaContext


@dataclass
class ModeContext:
    """Signals that push the executive toward deliberation."""

    new_goal: bool = False
    ambiguous: bool = False
    branch_exhausted: bool = False
    high_consequence: bool = False  # an irreversible action is approaching
    contradiction: bool = False  # beliefs disagree
    no_matching_procedure: bool = False
    last_action_surprised: bool = False


DELIBERATIVE = "deliberative"
REACTIVE = "reactive"


def cognitive_mode(ctx: ModeContext) -> str:
    """Deliberative when any trigger fires; reactive otherwise."""
    triggers = (
        ctx.new_goal,
        ctx.ambiguous,
        ctx.branch_exhausted,
        ctx.high_consequence,
        ctx.contradiction,
        ctx.no_matching_procedure,
        ctx.last_action_surprised,
    )
    return DELIBERATIVE if any(triggers) else REACTIVE


def mode_triggers(ctx: ModeContext) -> List[str]:
    """Which triggers fired, for logging why a mode was chosen."""
    names = []
    for name in (
        "new_goal",
        "ambiguous",
        "branch_exhausted",
        "high_consequence",
        "contradiction",
        "no_matching_procedure",
        "last_action_surprised",
    ):
        if getattr(ctx, name):
            names.append(name)
    return names


def decision_ladder(ctx: MetaContext, *, goal_complete: bool = False) -> MetaChoice:
    """Walk the ordered hierarchy and return the first rung that applies.

    This is the explicit-precedence sibling of ``select_meta_action``: where the
    scorer weighs moves, this states the order plainly. They agree on the clear
    cases; the ladder is what the runtime reads when it wants the *reason* to be
    the rung, not a score.
    """
    if goal_complete:
        return MetaChoice(MetaAction.VERIFY, "rung 0: goal appears complete; verify", {"verify": 1.0})

    if ctx.hard_block:
        return MetaChoice(MetaAction.ASK_USER, "rung 6: no self-serve route; ask user", {"ask_user": 1.0})

    if ctx.awaiting_verification and ctx.last_action_surprised:
        return MetaChoice(MetaAction.VERIFY, "rung 1: last action surprised us; verify first", {"verify": 1.0})

    suff = ctx.sufficiency

    # Rung 2: a grounded, sufficiently-evidenced move that advances the goal.
    if ctx.has_grounded_action and (suff is None or suff.sufficient_to_act):
        return MetaChoice(MetaAction.ACT, "rung 2: grounded action with sufficient evidence", {"act": 1.0})

    # Rung 3: a blocking uncertainty a look/probe could resolve — unless that
    # question is already settled (then this rung is skipped, not re-asked).
    if suff is not None and suff.blocking_uncertainties and not ctx.question_settled:
        if suff.observe_has_value:
            return MetaChoice(MetaAction.PERCEIVE, "rung 3: blocking uncertainty a look can close", {"perceive": 1.0})
        if ctx.probe_available:
            return MetaChoice(MetaAction.PROBE, "rung 3: blocking uncertainty a probe can reveal", {"probe": 1.0})

    # Rung 4: local exploration exhausted -> retreat / broaden.
    if ctx.branch_stale:
        return MetaChoice(MetaAction.BACKTRACK, "rung 4: branch exhausted; retreat and broaden", {"backtrack": 1.0})

    # Rung 5: no clear strategy -> consult the reasoning model.
    if ctx.ambiguous:
        return MetaChoice(MetaAction.THINK, "rung 5: no clear strategy; consult", {"think": 1.0})

    # Fallbacks: act if we can, else look, else ask.
    if ctx.has_grounded_action:
        return MetaChoice(MetaAction.ACT, "fallback: commit to the grounded action", {"act": 0.5})
    if suff is None or suff.observe_has_value:
        return MetaChoice(MetaAction.PERCEIVE, "fallback: look again", {"perceive": 0.5})
    return MetaChoice(MetaAction.ASK_USER, "fallback: nothing resolves the block", {"ask_user": 0.5})
