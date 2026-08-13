"""Meta-action vocabulary and the offline value scorer.

Live selection is LLM-based (``meta_consultation``). This module names the moves
and provides ``select_meta_action`` — a pure value scorer used for traces and as
part of the offline fallback stack — not the live chooser.

**v1 core contract** — see ``docs/design/agent-design.md`` and ``meta_contract.py``.
A meta-action is the executive's *reason* for spending the next unit of effort,
not the motor used underneath (screenshot, type, click, shell, …).

    THINK · PERCEIVE · SEARCH · EXPLORE · ACT · ASK · DELEGATE · WAIT

The selection is a pure function of what the executive already knows, so it is
testable in isolation and reusable across domains.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from plugin.agent.executive.sufficiency import DecisionSufficiency


# How many consecutive diagnostic re-looks a run of unmoving worlds may spend
# before the executive stops looking and broadens the search instead.
REPERCEPTION_RELOOK_CAP = 2

# Meta streak budgets (execution_state counters). The loop reports these into
# MetaContext; it must not rewrite the resulting MetaChoice to ACT.
BACKTRACK_STREAK_CAP = 5
INFORMATION_GATHERING_STREAK_CAP = 2
SEARCH_STREAK_CAP = 8
THINK_STREAK_CAP = 2
PROBE_STREAK_CAP = 3
EXPLORE_STREAK_CAP = PROBE_STREAK_CAP
PERCEIVE_STREAK_CAP = 2

# Catalog stages meta SEARCH (information_search) may actuate.
# Commit verbs stay ACT-only; reveal/probe stays EXPLORE-only.
SEARCH_STAGE_CAPABILITIES = frozenset(
    {
        "compose_search_query",
        "resolve_entity",
        "locate_content",
        "observe",
        "type_query",
        "request_more_evidence",
    }
)
SEARCH_FORBIDDEN_CAPABILITIES = frozenset(
    {
        "open_entity",
        "open_contact",
        "select_content",
        "reveal_actions",
        "invoke_affordance",
        "commit_irreversible",
    }
)

# EXPLORE = affordance discovery; may reveal/hover, never compose/rank/commit.
# select_content is allowed only as *failed-reveal recovery* (see ranked_capabilities
# / decision_consultation) — not as a general explore verb.
EXPLORE_STAGE_CAPABILITIES = frozenset(
    {
        "reveal_actions",
        "observe",
        "request_more_evidence",
    }
)
EXPLORE_FORBIDDEN_CAPABILITIES = frozenset(
    {
        "compose_search_query",
        "resolve_entity",
        "type_query",
        "locate_content",
        "open_entity",
        "open_contact",
        "select_content",
        "invoke_affordance",
        "commit_irreversible",
    }
)


def reperception_exhausted(execution_state) -> bool:
    """Has the run of unmoving worlds used up its diagnostic re-looks?

    A surprise earns a look that carries the failed attempt, which is how the
    model works out why its move did nothing. Looking again at a world that keeps
    not moving stops paying, so past the cap the executive broadens the search
    rather than re-reading the same screen forever. The runtime keeps the count
    and resets it the moment the world moves.
    """
    return (
        int(getattr(execution_state, "consecutive_surprise_relooks", 0) or 0)
        >= REPERCEPTION_RELOOK_CAP
    )


class MetaAction(str, Enum):
    THINK = "think"
    PERCEIVE = "perceive"
    SEARCH = "search"
    EXPLORE = "explore"
    ACT = "act"
    ASK = "ask"
    DELEGATE = "delegate"
    WAIT = "wait"


CORE_META_ACTION_VALUES = (
    "think",
    "perceive",
    "search",
    "explore",
    "act",
    "ask",
    "delegate",
    "wait",
)


# Minimum confidence for a surprise_explanation to authorise act/explore retreat.
REFLECT_EXPLANATION_CONFIDENCE = 0.85


@dataclass
class MetaContext:
    """The signals the selector reads. All optional; each domain fills what it has."""

    sufficiency: Optional[DecisionSufficiency] = None
    has_grounded_action: bool = False
    # Look is owed before the next act: surprise, dead motor, or surface change.
    awaiting_verification: bool = False
    last_action_surprised: bool = False
    # Post-act debt: motor write returned; executive has not finished re-perceive
    # before the next decide. Harder than surprise relooks — exhaustion must
    # never waive this (live 033711: ACT skipped re-perceive→decide).
    post_action_look_owed: bool = False
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
    # The diagnostic re-looks bought by recent surprises are spent and the world
    # still has not moved. Verifying again would re-read an unchanged screen, so
    # PERCEIVE stops out-ranking the retreat that broadens the search.
    # Does NOT apply while ``post_action_look_owed`` — that debt is hard.
    reperception_exhausted: bool = False
    # Streak / retreat budgets spent — the executive re-chooses with these set;
    # the loop must not rewrite the choice to ACT after the fact.
    backtrack_exhausted: bool = False
    information_gathering_exhausted: bool = False
    think_exhausted: bool = False
    probe_exhausted: bool = False
    perceive_streak_exhausted: bool = False
    # Goal × world branch fitness: inadmissible → evidence for EXPLORE retreat.
    branch_unfit: bool = False
    branch_fitness: Optional[Dict[str, Any]] = None
    # Referent find-among-many: criteria known, target not yet chosen.
    referent_search_needed: bool = False
    search_episode_incomplete: bool = False
    search_episode_complete: bool = False
    search_episode_failed: bool = False
    search_exhausted: bool = False
    # Empty / zero-progress find: must EXPLORE or THINK before another SEARCH.
    search_retreat_owed: bool = False
    search_progress: Optional[Dict[str, Any]] = None
    search_episode: Optional[Dict[str, Any]] = None
    # Identity open for referent (container address known).
    address_known: bool = False
    # Address known + unpaid content cleared → ACT/RETRIEVE, not SEARCH.
    retrieve_ready: bool = False
    # Actuatable source contact row grounded → ACT open_entity, not compose SEARCH.
    source_contact_open_ready: bool = False
    # Foreign open conversation ≠ source → ACT leave/list before compose.
    leave_wrong_conversation_owed: bool = False
    # Wrong-locus recovery (field|container|patient) — ACT/PERCEIVE, not SEARCH.
    wrong_locus_recovery_owed: bool = False
    wrong_locus_kind: str = ""
    # locate_content EffectStatus UNKNOWN — PERCEIVE verify before SEARCH replay.
    locate_effect_verify_owed: bool = False
    # SEARCH admissibility: criteria known (sought/query). False → EXPLORE.
    search_has_criteria: bool = True
    # Content/referent known but goal affordance still latent → EXPLORE (route),
    # not another instrumental ACT on the same content fingerprint.
    route_discovery_owed: bool = False
    # Reveal probe ran; affordance_set / expected overlay not yet grounded.
    incomplete_reveal: bool = False
    expected_overlay_missing: bool = False
    # Last content-act motor fingerprint (family|target|point) to forbid re-ACT.
    forbid_content_act_fingerprint: str = ""
    # Invoke/select left the wrong patient selected — ACT select/cancel, not re-invoke.
    referent_repair_owed: bool = False
    # Bound role failed its identity contract after motor-ok act → SEARCH/resolve.
    # Distinct from referent_repair_owed (wrong selection) and from GROUNDING.
    role_identity_search_owed: bool = False
    # Perceptor/world: goal act already clear on screen — do not force EXPLORE.
    act_clear: bool = False
    # Reveal episode ended without grounded overlay — free meta (ACT/THINK).
    reveal_episode_failed: bool = False
    # After failed reveal: next recovery capability (usually select_content).
    reveal_prefer_capability: str = ""
    # IntentionFrame: EXPLORE objective still has eligible methods.
    intention_explore_active: bool = False
    # IntentionFrame derived local-route / budget exhaustion.
    intention_locally_exhausted: bool = False
    # Destination picker open; goal recipient not selected → SEARCH in picker.
    destination_search_needed: bool = False
    # Semantic target valid; only coordinate grounding is stale → PERCEIVE only.
    grounding_reground_only: bool = False


@dataclass
class MetaChoice:
    action: MetaAction = MetaAction.ACT
    reason: str = ""
    scores: Dict[str, float] = field(default_factory=dict)
    # Optional catalog verb when meta_action is ACT (housekeeping short-circuit).
    capability: str = ""

    @property
    def observe_wanted(self) -> bool:
        # THINK may want a fresh world before reasoning; SEARCH actuates find-stages.
        return self.action in {
            MetaAction.PERCEIVE,
            MetaAction.EXPLORE,
            MetaAction.THINK,
        }

    @property
    def may_actuate(self) -> bool:
        """ACT commits; SEARCH find-stages; EXPLORE reveal/probe only."""
        return self.action in {
            MetaAction.ACT,
            MetaAction.SEARCH,
            MetaAction.EXPLORE,
        }

    @property
    def suppress_observe(self) -> bool:
        return not self.observe_wanted

    def to_dict(self) -> Dict[str, object]:
        # Scores mix numeric value weights with string provenance tags
        # (e.g. source="llm" from meta consultation). Only round numbers.
        scores: Dict[str, object] = {}
        for k, v in self.scores.items():
            if isinstance(v, bool):
                scores[k] = v
            elif isinstance(v, (int, float)):
                scores[k] = round(float(v), 3)
            else:
                scores[k] = v
        out: Dict[str, object] = {
            "action": self.action.value,
            "reason": self.reason,
            "scores": scores,
        }
        if self.capability:
            out["capability"] = str(self.capability)
        return out


def select_meta_action(ctx: MetaContext) -> MetaChoice:
    """Score each admissible move with the one canonical value function.

    Every move's number now comes from ``action_value(ValueInputs(...))`` -- the
    same progress/information/reversibility/risk/cost/repeat trade-off the rest
    of the executive uses to rank concrete actions -- rather than a bespoke
    constant per branch. PERCEIVE/EXPLORE/THINK are information moves (they buy
    a reduction in blocking uncertainty), EXPLORE retreat scores when a branch is
    stale or unfit, and ACT is a progress move whose probability is the
    sufficiency verdict. Admissibility gates below decide *whether* a move is a
    candidate at all; the value function decides which candidate wins.

    Order still encodes hard precedence: a hard block can only be answered by
    asking. A just-executed action that surprised us schedules PERCEIVE (look,
    then brain acts). Below those, value decides.
    """
    from plugin.agent.executive.value import ValueInputs, action_value

    scores: Dict[str, float] = {}

    if ctx.hard_block:
        return MetaChoice(MetaAction.ASK, "hard block: no self-serve move resolves it", {"ask": 1.0})

    # Typed grounding failure: keep semantic binding; reground geometry only.
    # Must beat destination SEARCH / no-progress replan (live 171216 Forward).
    if bool(getattr(ctx, "grounding_reground_only", False)):
        return MetaChoice(
            MetaAction.PERCEIVE,
            "grounding stale — perceive(reground) only; preserve semantic binding",
            {
                "perceive": 1.0,
                "grounding_reground_only": 1.0,
                "forbid_search": 1.0,
            },
        )

    # Visible source contact / leave-wrong-conversation: ACT before SEARCH compose
    # (live 145943: foreign CoE open + Pallavi row → open, not compose_search).
    if bool(getattr(ctx, "source_contact_open_ready", False)) and not bool(
        getattr(ctx, "post_action_look_owed", False)
    ):
        return MetaChoice(
            MetaAction.ACT,
            "source contact row grounded — open_entity, not compose search",
            {
                "act": 1.0,
                "source_contact_open_ready": 1.0,
                "forbid_search": 1.0,
            },
        )
    if (
        bool(getattr(ctx, "leave_wrong_conversation_owed", False))
        and not bool(getattr(ctx, "source_contact_open_ready", False))
        and not bool(getattr(ctx, "post_action_look_owed", False))
        and not bool(getattr(ctx, "last_action_surprised", False))
    ):
        return MetaChoice(
            MetaAction.ACT,
            "foreign conversation open — leave/list before compose search",
            {
                "act": 1.0,
                "leave_wrong_conversation": 1.0,
                "forbid_search": 1.0,
            },
        )
    # Wrong-locus recovery (generalize leave-wrong): restore required locus
    # before SEARCH/compose into the forbidden field/container/patient.
    if (
        bool(getattr(ctx, "wrong_locus_recovery_owed", False))
        and not bool(getattr(ctx, "post_action_look_owed", False))
        and not bool(getattr(ctx, "last_action_surprised", False))
    ):
        kind = str(getattr(ctx, "wrong_locus_kind", "") or "").strip().lower()
        if kind == "field":
            return MetaChoice(
                MetaAction.ACT,
                "wrong field locus — dismiss composer / open find, not compose",
                {
                    "act": 1.0,
                    "wrong_locus_recovery": 1.0,
                    "forbid_search": 1.0,
                    "capability_hint": "dismiss_transient",
                },
                capability="dismiss_transient",
            )
        if kind == "patient":
            return MetaChoice(
                MetaAction.PERCEIVE,
                "wrong patient locus — reground committed affordance",
                {
                    "perceive": 1.0,
                    "wrong_locus_recovery": 1.0,
                    "forbid_search": 1.0,
                },
            )
        return MetaChoice(
            MetaAction.ACT,
            "wrong locus — restore required container/field before search",
            {
                "act": 1.0,
                "wrong_locus_recovery": 1.0,
                "forbid_search": 1.0,
            },
        )

    # locate EffectStatus UNKNOWN: visually verify before SEARCH reseals locate.
    if bool(getattr(ctx, "locate_effect_verify_owed", False)) and not bool(
        getattr(ctx, "post_action_look_owed", False)
    ):
        return MetaChoice(
            MetaAction.PERCEIVE,
            "locate effect unknown — perceive verify before same-method SEARCH",
            {
                "perceive": 1.0,
                "locate_effect_verify": 1.0,
                "forbid_search": 1.0,
            },
        )

    # Entity-resolution SEARCH beats unpaid look debt when the prior look
    # already answered "is the target visible / is search available?" — another
    # generic Observe answers nothing new (live 203259). Surprise still owns
    # PERCEIVE first (prediction error must be explained).
    act_clear = bool(getattr(ctx, "act_clear", False))
    referent_repair = bool(getattr(ctx, "referent_repair_owed", False))
    entity_search = (
        bool(getattr(ctx, "destination_search_needed", False))
        and not act_clear
        and not referent_repair
        and not ctx.search_exhausted
    )
    if entity_search and not ctx.last_action_surprised:
        return MetaChoice(
            MetaAction.SEARCH,
            "entity unresolved with searchable scope — SEARCH before re-perceive",
            {"search": 1.0, "destination_search": 1.0, "entity_resolution": 1.0},
        )

    # One executive: act → result → re-perceive → decide. An unpaid post-act
    # look always schedules PERCEIVE. Surprise alone does the same until the
    # relook budget is spent; exhaustion may then broaden — but never while
    # post-act debt is still unpaid (live 033711).
    if ctx.post_action_look_owed or (
        ctx.awaiting_verification and not ctx.reperception_exhausted
    ):
        if ctx.last_action_surprised:
            return MetaChoice(
                MetaAction.PERCEIVE,
                "prediction error — perceive before re-acting",
                {"perceive": 1.0, "surprise": 1.0},
            )
        return MetaChoice(
            MetaAction.PERCEIVE,
            "relook owed — perceive before re-acting",
            {"perceive": 1.0, "must_reperceive": 1.0},
        )

    suff = ctx.sufficiency

    # A look/probe that only re-tests an already-settled question is the
    # re-search failure class; the value function's repeat penalty
    # (EPSILON_REPEAT) drives it below acting/exploring.
    reask = bool(ctx.question_settled)

    # PERCEIVE is worth it only when a look could close a gap that matters. It is
    # a pure information move: no direct progress, fully reversible, cheap.
    if suff is not None and suff.observe_has_value:
        scores["perceive"] = action_value(
            ValueInputs(
                progress_probability=0.0,
                information_gain=0.9 if suff.blocking_uncertainties else 0.7,
                reversibility=1.0,
                cost="low",
                repeated=reask,
            )
        )
    else:
        scores["perceive"] = 0.0

    # EXPLORE when we cannot see what we need but looking again would not help —
    # a reversible reveal may expose affordances, or the branch is stale/unfit.
    # Also when content is known but the goal route/affordance is still latent.
    explore_score = 0.0
    reveal_failed = bool(getattr(ctx, "reveal_episode_failed", False))
    route_owed = (
        not act_clear
        and not reveal_failed
        and not ctx.probe_exhausted
        and not entity_search
        and (
            bool(getattr(ctx, "route_discovery_owed", False))
            or bool(getattr(ctx, "incomplete_reveal", False))
            or bool(getattr(ctx, "expected_overlay_missing", False))
        )
    )
    # Wrong selected patient → ACT select/cancel, not EXPLORE observe thrash.
    if referent_repair and not ctx.post_action_look_owed:
        return MetaChoice(
            MetaAction.ACT,
            "referent repair owed — select/cancel matching patient before re-invoke",
            {"act": 1.0, "referent_repair": 1.0},
        )
    # Goal act already clear (e.g. Forward on open menu) → ACT, not explore latch.
    if act_clear and not ctx.post_action_look_owed and not referent_repair:
        if ctx.has_grounded_action or not ctx.hard_block:
            return MetaChoice(
                MetaAction.ACT,
                "act clear — commit goal control, do not re-explore affordances",
                {"act": 1.0, "act_clear": 1.0},
            )
    # Active EXPLORE intention with remaining methods → keep exploring
    # (intent-level retry). Only when the intention frame is locally exhausted
    # does control return to the executive — not sticky ACT→Observe (181059).
    intention_active = bool(getattr(ctx, "intention_explore_active", False))
    intention_exhausted = bool(getattr(ctx, "intention_locally_exhausted", False))
    if (
        intention_active
        and not intention_exhausted
        and not act_clear
        and not referent_repair
        and not entity_search
        and not ctx.post_action_look_owed
    ):
        return MetaChoice(
            MetaAction.EXPLORE,
            "active explore intention — try next method for same objective",
            {"explore": 1.0, "intention_active": 1.0},
        )
    if (
        (reveal_failed or ctx.probe_exhausted or intention_exhausted)
        and not act_clear
        and not referent_repair
        and not ctx.post_action_look_owed
        and not intention_active
    ):
        # Local route exhausted: return authority to executive scoring
        # (SEARCH/EXPLORE/THINK/ASK) — do not force sticky ACT.
        explore_score = max(explore_score, 0.35)
        # Fall through to normal scoring with a think bias when hard-blocked.
        if ctx.hard_block:
            return MetaChoice(
                MetaAction.THINK,
                "local reveal route exhausted — replan",
                {"think": 1.0, "local_route_exhausted": 1.0},
            )
    if route_owed and not ctx.probe_exhausted and not ctx.post_action_look_owed:
        explore_score = action_value(
            ValueInputs(
                progress_probability=0.45,
                information_gain=0.9,
                reversibility=1.0,
                cost="low",
                repeated=False,
            )
        )
    elif (
        ctx.probe_available
        and not ctx.probe_exhausted
        and suff is not None
        and not suff.sufficient_to_act
        and not suff.observe_has_value
    ):
        explore_score = action_value(
            ValueInputs(
                progress_probability=0.3,
                information_gain=0.85,
                reversibility=1.0,
                cost="low",
                repeated=reask,
            )
        )
    elif (
        (ctx.branch_stale or ctx.branch_unfit)
        and not ctx.backtrack_exhausted
        and not ctx.information_gathering_exhausted
        and not ctx.probe_exhausted
        and (suff is None or not suff.observe_has_value or ctx.branch_unfit)
        and not ctx.post_action_look_owed
    ):
        explore_score = action_value(
            ValueInputs(
                progress_probability=0.7 if ctx.branch_unfit else 0.5,
                progress_value=1.0,
                information_gain=0.3,
                reversibility=1.0,
                cost="low",
            )
        )
    scores["explore"] = explore_score
    # Hard precedence when route discovery is the blocking unknown.
    # Skip when perceptor already sees the goal act (act_clear).
    if (
        route_owed
        and not act_clear
        and not ctx.post_action_look_owed
        and not ctx.probe_exhausted
        and explore_score > 0
    ):
        return MetaChoice(
            MetaAction.EXPLORE,
            "route discovery owed — explore affordances before act",
            {"explore": 1.0, "route_discovery": 1.0},
        )

    # Optional perceive (not post-act debt): streak exhausted → do not keep looking.
    if ctx.perceive_streak_exhausted and not ctx.post_action_look_owed:
        scores["perceive"] = 0.0

    # Retreat exhausted: executive decides ACT (or ask) — not a loop rewrite.
    if ctx.branch_stale and (
        ctx.information_gathering_exhausted or ctx.backtrack_exhausted
    ):
        if ctx.has_grounded_action or ctx.information_gathering_exhausted:
            return MetaChoice(
                MetaAction.ACT,
                "retreat budget spent — decide next capability",
                {"act": 1.0, "retreat_exhausted": 1.0},
            )
        return MetaChoice(
            MetaAction.ASK,
            "explore retreat exhausted; nothing can be grounded",
            {"ask": 1.0, "retreat_exhausted": 1.0},
        )

    # THINK when the situation is ambiguous and we are not merely short of a look.
    # Consulting the model buys information at a higher (medium) cost.
    if (
        ctx.ambiguous
        and not ctx.think_exhausted
        and (suff is None or not suff.observe_has_value)
    ):
        scores["think"] = action_value(
            ValueInputs(
                progress_probability=0.3,
                information_gain=0.6,
                reversibility=1.0,
                cost="medium",
            )
        )
    else:
        scores["think"] = 0.0

    # ACT when we have a grounded move. Its progress probability is exactly the
    # sufficiency verdict: high when the evidence is sufficient, thin otherwise.
    if ctx.has_grounded_action:
        sufficient = suff is None or suff.sufficient_to_act
        scores["act"] = action_value(
            ValueInputs(
                progress_probability=0.85 if sufficient else 0.5,
                progress_value=1.0,
                reversibility=1.0,
                cost="low",
            )
        )
    else:
        scores["act"] = 0.0

    # Running out of budget: prefer committing to the best action over more
    # looking. This is precedence, not value -- with the turn about to end, a
    # grounded action beats any further information gathering.
    if ctx.steps_remaining <= 1 and ctx.has_grounded_action:
        scores["act"] = max(scores["act"], 0.99)

    scores = {k: round(v, 4) for k, v in scores.items()}
    best_key = max(scores, key=lambda k: scores[k]) if scores else "act"
    best_val = scores.get(best_key, 0.0)
    if best_val <= 0.0:
        # Nothing scored: default to acting if we can, else looking — unless the
        # perceive streak is spent, in which case decide a capability.
        if ctx.has_grounded_action or (
            ctx.perceive_streak_exhausted and not ctx.post_action_look_owed
        ):
            return MetaChoice(MetaAction.ACT, "no signal; commit to grounded action", scores)
        return MetaChoice(MetaAction.PERCEIVE, "no signal and no action; look again", scores)

    chosen = MetaAction(best_key)
    reason = _reason_for(chosen, suff)
    return MetaChoice(chosen, reason, scores)


def _reason_for(action: MetaAction, suff: Optional[DecisionSufficiency]) -> str:
    if suff is not None and suff.reason and action in {
        MetaAction.PERCEIVE,
        MetaAction.EXPLORE,
        MetaAction.ACT,
    }:
        return f"{action.value}: {suff.reason}"
    return {
        MetaAction.PERCEIVE: "a look could close a real gap",
        MetaAction.EXPLORE: "reveal affordances or retreat from a stale branch",
        MetaAction.SEARCH: "criteria known; find among many",
        MetaAction.THINK: "ambiguous; consult reasoning",
        MetaAction.ACT: "evidence sufficient; commit",
        MetaAction.ASK: "escalate to user",
        MetaAction.DELEGATE: "assign bounded objective to specialist",
        MetaAction.WAIT: "allow external process to change state",
    }.get(action, action.value)
