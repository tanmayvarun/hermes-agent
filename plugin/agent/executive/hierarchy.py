"""Cognitive modes and the offline meta decision ladder (eval oracle only).

Live meta-action selection is always LLM-based
(``meta_consultation.resolve_meta_choice``) — no runtime flag, no ladder
fallback. ``decision_ladder`` remains as a frozen policy oracle for goldens /
hermetic test stubs that *simulate* an LLM chooser:

    0. goal already complete?           -> PERCEIVE (verify via look)
    1. hard block?                      -> ASK
    2. look owed (post-act / surprise)?   -> PERCEIVE
    3. grounded advancing move?           -> ACT
    4. blocking uncertainty?              -> PERCEIVE / EXPLORE
    5. branch stale?                    -> THINK (or ACT / ASK when budgets spent)
    6. no strategy clear?               -> THINK
    7. look for action geometry?        -> PERCEIVE
    8. fallbacks                        -> ACT / PERCEIVE / ASK

Cognitive modes:

    - deliberative: new goal, ambiguity, exhausted branch, high-consequence
      action, contradicted beliefs, or no matching procedure -> strong model;
    - reactive: clear intention, grounded action, known transition, low risk.
"""

from __future__ import annotations

from dataclasses import dataclass
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

    Eval-only / hermetic-stub oracle. Live runtime never calls this — meta is
    always LLM-inferred via ``meta_consultation.resolve_meta_choice``.
    """
    if goal_complete:
        return MetaChoice(
            MetaAction.PERCEIVE,
            "rung 0: goal appears complete; verify via look",
            {"perceive": 1.0},
        )

    if ctx.hard_block:
        return MetaChoice(MetaAction.ASK, "rung 1: no self-serve route; ask", {"ask": 1.0})

    # Rung 1.5: entity-resolution SEARCH — known criteria + unresolved target +
    # searchable scope. Beats unpaid look debt when surprise is absent: the
    # prior look already answered visibility / search-availability (live 203259).
    entity_search = (
        bool(getattr(ctx, "destination_search_needed", False))
        and not bool(getattr(ctx, "act_clear", False))
        and not bool(getattr(ctx, "referent_repair_owed", False))
        and not bool(getattr(ctx, "search_exhausted", False))
        and not bool(getattr(ctx, "last_action_surprised", False))
    )
    if entity_search:
        return MetaChoice(
            MetaAction.SEARCH,
            "rung 1.5: entity unresolved with searchable scope — SEARCH",
            {"search": 1.0, "destination_search": 1.0, "entity_resolution": 1.0},
        )

    # Rung 2: executive owes a look (post-act re-perceive and/or surprise).
    # Post-act debt is hard — surprise-relook exhaustion must not skip this
    # while the act→reperceive→decide cycle is unfinished (live 033711).
    if ctx.post_action_look_owed or (
        ctx.awaiting_verification and not ctx.reperception_exhausted
    ):
        scores = {"perceive": 1.0}
        if ctx.last_action_surprised:
            scores["surprise"] = 1.0
        else:
            scores["must_reperceive"] = 1.0
        return MetaChoice(
            MetaAction.PERCEIVE,
            "rung 2: relook owed — perceive before re-acting",
            scores,
        )

    suff = ctx.sufficiency

    # Rung 3: a grounded, sufficiently-evidenced move that advances the goal.
    if ctx.has_grounded_action and (suff is None or suff.sufficient_to_act):
        return MetaChoice(MetaAction.ACT, "rung 3: grounded action with sufficient evidence", {"act": 1.0})

    # Rung 4: a blocking uncertainty a look/explore could resolve — unless that
    # question is already settled (then this rung is skipped, not re-asked).
    # Entity-resolution gaps are SEARCH (rung 1.5), not another generic look.
    if suff is not None and suff.blocking_uncertainties and not ctx.question_settled:
        if suff.observe_has_value and not (
            ctx.perceive_streak_exhausted and not ctx.post_action_look_owed
        ):
            return MetaChoice(MetaAction.PERCEIVE, "rung 4: blocking uncertainty a look can close", {"perceive": 1.0})
        if ctx.probe_available and not ctx.probe_exhausted:
            return MetaChoice(MetaAction.EXPLORE, "rung 4: blocking uncertainty explore can reveal", {"explore": 1.0})

    # Rung 5: branch stale — strategic replan from known info, or ACT/ASK when
    # retreat budgets are spent (loop must not rewrite after meta).
    if ctx.branch_stale:
        if ctx.information_gathering_exhausted:
            return MetaChoice(
                MetaAction.ACT,
                "rung 5: replan budget exhausted; decide next capability",
                {"act": 1.0, "retreat_exhausted": 1.0},
            )
        if ctx.backtrack_exhausted:
            if ctx.has_grounded_action:
                return MetaChoice(
                    MetaAction.ACT,
                    "rung 5: explore retreat exhausted; commit the grounded action",
                    {"act": 1.0, "retreat_exhausted": 1.0},
                )
            return MetaChoice(
                MetaAction.ASK,
                "rung 5: explore retreat exhausted; nothing can be grounded",
                {"ask": 1.0, "retreat_exhausted": 1.0},
            )
        return MetaChoice(
            MetaAction.THINK,
            "rung 5: branch stale; replan from known info",
            {"think": 1.0},
        )

    # Rung 6: no clear strategy -> consult reasoning, but only when a look
    # would not help.
    if (
        ctx.ambiguous
        and not ctx.think_exhausted
        and (suff is None or not suff.observe_has_value)
    ):
        return MetaChoice(MetaAction.THINK, "rung 6: no clear strategy; consult", {"think": 1.0})

    # Rung 7: evidence is ready but geometry is still missing (live 134822).
    if (
        suff is not None
        and suff.observe_has_value
        and not ctx.has_grounded_action
        and not (ctx.perceive_streak_exhausted and not ctx.post_action_look_owed)
    ):
        return MetaChoice(
            MetaAction.PERCEIVE,
            "rung 7: look for grounded action geometry",
            {"perceive": 1.0},
        )

    # Rung 8: fallbacks — act if we can, else look, else ask.
    # Perceive streak spent (and no post-act debt): decide a capability.
    if ctx.perceive_streak_exhausted and not ctx.post_action_look_owed:
        return MetaChoice(
            MetaAction.ACT,
            "fallback: perceive streak exhausted; decide next capability",
            {"act": 1.0, "perceive_streak_exhausted": 1.0},
        )
    if ctx.has_grounded_action:
        return MetaChoice(MetaAction.ACT, "fallback: commit to the grounded action", {"act": 0.5})
    if suff is None or suff.observe_has_value:
        return MetaChoice(MetaAction.PERCEIVE, "fallback: look again", {"perceive": 0.5})
    return MetaChoice(MetaAction.ASK, "fallback: nothing resolves the block", {"ask": 0.5})
