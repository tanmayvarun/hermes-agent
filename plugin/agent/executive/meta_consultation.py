"""LLM chooses the executive meta-action — always, no flag, no ladder fallback.

Live path: one short text consultation over the shaped meta packet returns
``{meta_action, why, confidence}``. The only hard sanitize rewrite is unpaid
look debt (post-act / surprise) → PERCEIVE. Budgets and hard_block are packet
signals for the model, not post-hoc overrides.

Offline tests inject a ``MetaChooser`` stub. Goldens may still score labels via
``decision_ladder`` as a frozen policy oracle — that is eval-only, not runtime.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, Tuple, runtime_checkable

from plugin.agent.executive.meta_action import (
    CORE_META_ACTION_VALUES,
    MetaAction,
    MetaChoice,
    MetaContext,
)
from plugin.agent.executive.meta_situation import (
    META_PACKET_REQUIRED_SECTIONS,
    MetaSituation,
)

logger = logging.getLogger(__name__)

META_ACTIONS = CORE_META_ACTION_VALUES

META_SYSTEM = """You are the executive of a general-purpose agent.
Choose the single next meta-action — the *kind* of step (purpose, not mechanism).
Screenshot / click / type / shell are capability motors underneath — never meta names.

v1 core vocabulary (docs/design/agent-design.md):
- think: derive something from information already available (no new external evidence)
- perceive: acquire a current description of a *known* scope ("what is here?")
- search: find entities matching *known criteria* in a search space (location unknown).
  Does NOT open/commit — that is act. Requires criteria; else choose explore.
- explore: discover possibilities when target/route/search space is insufficiently known
  (reveal/probe motors only — not compose/rank)
- act: intentionally change external state toward the goal (target/method known enough)
- ask: request info/judgment/permission from another actor (user, peer, service)
- delegate: assign a bounded objective to another agent/skill; you remain goal owner
- wait: allow time or an external process to change state before reconsidering

Packet sections: look_debt, evidence, search (incl. referent_search intent/result),
decision_problem (known/unknown/blocking_uncertainty + selection semantics),
budgets, options, blockers, situation.

Return JSON only:
{"meta_action":"<one of the allowed actions>","capability":"<optional catalog verb>","why":"<short>","confidence":0.0-1.0}

Hard contract (runtime-enforced if you violate it):
- If look_debt.look_owed_now, you MUST choose perceive. Never act while that debt is unpaid.
- If search.referent_search.retreat_owed or search.referent_search.failed
  (empty / zero-progress find), you MUST NOT choose search again until explore or think
  has cleared the dead branch — prefer explore (revert/reveal) or think (replan).
- If search.referent_search.needed or search.referent_search.incomplete with criteria,
  prefer search over act (act is for commit after SearchResult.chosen) — unless
  retreat_owed/failed as above.
- If search.referent_search.retrieve_ready and NOT route_discovery_owed,
  choose act — not search (commit/open known address).
- If search.referent_search.source_contact_open_ready, choose act open_entity —
  not search/compose (visible source contact row already grounded).
- If leave_wrong_conversation_owed and NOT source_contact_open_ready, choose act
  leave/list (dismiss / Chats) — not search/compose into the foreign pane.
- If wrong_locus_recovery_owed, choose act/perceive recovery for the required
  locus (dismiss composer / leave foreign / reground patient) — never search
  or compose into the forbidden locus.
- If route_discovery_owed (content known, goal affordance latent) or
  incomplete_reveal / expected_overlay_missing after the look is paid,
  choose explore — not act on the same content. Route discovery is EXPLORE.
- Search without criteria → explore, not search or act.

Guidance (semantic DecisionProblem — not a rigid tree):
- reliable goal-advancing action → act
- criteria known, location unknown → search
- scope known, need current state → perceive
- target/route insufficiently known → explore
- content known + affordance latent → explore (reveal), then perceive, then act invoke
- existing information may resolve it → think
- another actor has info/authority → ask
- bounded specialist objective → delegate
- missing info expected through time → wait
- When search.hard_block is true, prefer ask.
- When blockers.storage_pressure, prefer act + housekeeping capability.
"""


@runtime_checkable
class MetaChooser(Protocol):
    def choose(self, system: str, packet: Dict[str, Any]) -> Dict[str, Any]:
        """Return ``{"meta_action": str, "why": str, "confidence": float}``."""


@dataclass
class LlmMetaChooser:
    """Default realization: one short bounded text call on the decision stack."""

    timeout_s: float = 45.0

    def choose(self, system: str, packet: Dict[str, Any]) -> Dict[str, Any]:
        from plugin.agent.perception_synthesis import _call_llm_hard_timeout
        from plugin.agent.reasoning_consultation import consult_reasoning

        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    "Choose the next meta-action.\n"
                    + json.dumps(packet, ensure_ascii=False, default=str)[:6000]
                ),
            },
        ]
        consultation = consult_reasoning(
            "decision",
            messages,
            usecase="meta_choice",
            caller=lambda **kwargs: _call_llm_hard_timeout(self.timeout_s, **kwargs),
            call_kwargs={"timeout": self.timeout_s},
            temperature=0.1,
            max_tokens=192,
        )
        parsed = getattr(consultation, "parsed", None) or {}
        if isinstance(parsed, dict) and (
            parsed.get("meta_action") or parsed.get("action")
        ):
            return parsed
        raw = str(getattr(consultation, "raw_response", "") or "")
        return json.loads(raw)


def meta_context_packet(
    ctx: MetaContext,
    *,
    goal_complete: bool = False,
    situation: Optional[MetaSituation] = None,
) -> Dict[str, Any]:
    """Shaped signal packet for the meta chooser (no screen pixels).

    Section layout is the eval contract: mined from unique ``executive_judgement``
    situations across zarooratwala live runs so the LLM sees the same
    discriminators the executive historically used.
    """
    suff = ctx.sufficiency
    blocking: list = []
    observe_has_value = False
    sufficient_to_act = False
    needs_exploration = False
    suff_reason = ""
    if suff is not None:
        blocking = [
            str(b)
            for b in (getattr(suff, "blocking_uncertainties", None) or [])
            if str(b).strip()
        ][:6]
        observe_has_value = bool(getattr(suff, "observe_has_value", False))
        sufficient_to_act = bool(getattr(suff, "sufficient_to_act", False))
        needs_exploration = bool(getattr(suff, "needs_exploration", False))
        suff_reason = str(getattr(suff, "reason", "") or "")[:160]

    sit = situation or MetaSituation()
    sit_view = sit.to_dict()
    if not blocking:
        blocking = list(sit_view.get("blocking_uncertainties") or [])[:6]

    look_owed = bool(
        ctx.post_action_look_owed
        or (ctx.awaiting_verification and not ctx.reperception_exhausted)
    )
    ep_view = (
        getattr(ctx, "search_episode", None)
        if isinstance(getattr(ctx, "search_episode", None), dict)
        else {}
    )
    result_view = (
        ep_view.get("result") if isinstance(ep_view.get("result"), dict) else {}
    )
    intent_view = (
        ep_view.get("intent") if isinstance(ep_view.get("intent"), dict) else {}
    )
    coverage_view = (
        result_view.get("coverage")
        if isinstance(result_view.get("coverage"), dict)
        else {}
    )
    unexplored_view = [
        str(s)[:64]
        for s in (result_view.get("unexplored_scopes") or [])
        if str(s).strip()
    ][:12]
    from plugin.agent.executive.meta_contract import (
        decision_problem_from_meta_context,
        envelope_for_choice,
    )

    decision_problem = decision_problem_from_meta_context(
        ctx,
        goal=(sit_view.get("goal") or {}).get("summary")
        or (sit_view.get("goal") or {}).get("phase")
        or None,
        phase=str((sit_view.get("goal") or {}).get("phase") or ""),
    )
    packet = {
        "goal_complete": bool(goal_complete)
        or bool((sit_view.get("goal") or {}).get("all_satisfied")),
        "allowed_meta_actions": list(META_ACTIONS),
        "core_meta_actions": list(CORE_META_ACTION_VALUES),
        "decision_problem": decision_problem.to_dict(),
        "look_debt": {
            "post_action_look_owed": bool(ctx.post_action_look_owed),
            "awaiting_verification": bool(ctx.awaiting_verification),
            "last_action_surprised": bool(ctx.last_action_surprised),
            "reperception_exhausted": bool(ctx.reperception_exhausted),
            "look_owed_now": look_owed,
        },
        "evidence": {
            "has_grounded_action": bool(ctx.has_grounded_action),
            "sufficient_to_act": sufficient_to_act,
            "observe_has_value": observe_has_value,
            "needs_exploration": needs_exploration,
            "question_settled": bool(ctx.question_settled),
            "blocking_uncertainties": blocking,
            "evidence_gaps": list(sit_view.get("evidence_gaps") or [])[:6],
            "coverage": sit_view.get("coverage"),
            "sufficiency_reason": suff_reason,
        },
        "search": {
            "branch_stale": bool(ctx.branch_stale),
            "branch_unfit": bool(getattr(ctx, "branch_unfit", False)),
            "branch_fitness": {
                "admissible": (getattr(ctx, "branch_fitness", None) or {}).get(
                    "admissible"
                ),
                "reasons": list(
                    (getattr(ctx, "branch_fitness", None) or {}).get("reasons") or []
                )[:6],
                "blockers": [
                    b.get("type")
                    for b in (
                        (getattr(ctx, "branch_fitness", None) or {}).get("blockers")
                        or []
                    )
                    if isinstance(b, dict)
                ][:6],
                "verdict": str(
                    (getattr(ctx, "branch_fitness", None) or {}).get("verdict") or ""
                )[:160],
            },
            "ambiguous": bool(ctx.ambiguous),
            "hard_block": bool(ctx.hard_block),
            "static_streak": int(sit_view.get("static_streak") or 0),
            "cognitive_mode": str(sit_view.get("cognitive_mode") or ""),
            "mode_triggers": list(sit_view.get("mode_triggers") or [])[:8],
            "referent_search": {
                "needed": bool(getattr(ctx, "referent_search_needed", False)),
                "incomplete": bool(getattr(ctx, "search_episode_incomplete", False)),
                "complete": bool(getattr(ctx, "search_episode_complete", False)),
                "failed": bool(getattr(ctx, "search_episode_failed", False)),
                "fail_reason": str(
                    (getattr(ctx, "search_episode", None) or {}).get("fail_reason") or ""
                )[:80],
                "retreat_owed": bool(getattr(ctx, "search_retreat_owed", False)),
                "exhausted": bool(getattr(ctx, "search_exhausted", False)),
                "status": str((getattr(ctx, "search_episode", None) or {}).get("status") or ""),
                "role": str((getattr(ctx, "search_episode", None) or {}).get("role") or ""),
                "referent": str(
                    (getattr(ctx, "search_episode", None) or {}).get("referent") or ""
                )[:80],
                "chosen_label": str(
                    (getattr(ctx, "search_episode", None) or {}).get("chosen_label") or ""
                )[:80],
                "candidate_count": int(
                    (getattr(ctx, "search_episode", None) or {}).get("candidate_count")
                    or 0
                ),
                "address_known": bool(getattr(ctx, "address_known", False)),
                "retrieve_ready": bool(getattr(ctx, "retrieve_ready", False)),
                "source_contact_open_ready": bool(
                    getattr(ctx, "source_contact_open_ready", False)
                ),
                "leave_wrong_conversation_owed": bool(
                    getattr(ctx, "leave_wrong_conversation_owed", False)
                ),
                "wrong_locus_recovery_owed": bool(
                    getattr(ctx, "wrong_locus_recovery_owed", False)
                ),
                "wrong_locus_kind": str(
                    getattr(ctx, "wrong_locus_kind", "") or ""
                ),
                "locate_effect_verify_owed": bool(
                    getattr(ctx, "locate_effect_verify_owed", False)
                ),
                "has_criteria": bool(getattr(ctx, "search_has_criteria", True)),
                "route_discovery_owed": bool(
                    getattr(ctx, "route_discovery_owed", False)
                ),
                "incomplete_reveal": bool(getattr(ctx, "incomplete_reveal", False)),
                "expected_overlay_missing": bool(
                    getattr(ctx, "expected_overlay_missing", False)
                ),
                "act_clear": bool(getattr(ctx, "act_clear", False)),
                "reveal_episode_failed": bool(
                    getattr(ctx, "reveal_episode_failed", False)
                ),
                "referent_repair_owed": bool(
                    getattr(ctx, "referent_repair_owed", False)
                ),
                "intent": dict(intent_view),
                "result": dict(result_view),
                "coverage": dict(coverage_view),
                "unexplored_scopes": list(unexplored_view),
                "progress": dict(getattr(ctx, "search_progress", None) or {})
                if isinstance(getattr(ctx, "search_progress", None), dict)
                else {},
            },
        },
        "budgets": {
            "steps_remaining": int(ctx.steps_remaining),
            "backtrack_exhausted": bool(ctx.backtrack_exhausted),
            "information_gathering_exhausted": bool(ctx.information_gathering_exhausted),
            "search_exhausted": bool(getattr(ctx, "search_exhausted", False)),
            "think_exhausted": bool(ctx.think_exhausted),
            "probe_exhausted": bool(ctx.probe_exhausted),
            "perceive_streak_exhausted": bool(ctx.perceive_streak_exhausted),
            "streaks": dict(sit_view.get("streaks") or {}),
        },
        "options": {
            "probe_available": bool(ctx.probe_available),
            "housekeeping_capabilities": list(
                sit_view.get("housekeeping_capabilities") or []
            )[:6],
        },
        "blockers": dict(sit_view.get("blockers") or {}),
        "situation": {
            "goal": dict(sit_view.get("goal") or {}),
            "recent": dict(sit_view.get("recent") or {}),
            "perception_query": dict(sit_view.get("perception_query") or {}),
        },
    }
    for key in META_PACKET_REQUIRED_SECTIONS:
        packet.setdefault(key, {})
    return packet


def _parse_action(raw: Dict[str, Any]) -> Optional[MetaAction]:
    if not isinstance(raw, dict):
        return None
    token = str(raw.get("meta_action") or raw.get("action") or "").strip().lower()
    if not token:
        return None
    from plugin.agent.executive.meta_contract import canonicalize_meta_kind

    return canonicalize_meta_kind(token)


def _look_owed(ctx: MetaContext) -> bool:
    return bool(
        ctx.post_action_look_owed
        or (ctx.awaiting_verification and not ctx.reperception_exhausted)
    )


def sanitize_meta_choice(
    raw: Dict[str, Any],
    ctx: MetaContext,
    *,
    goal_complete: bool = False,
    situation: Optional[MetaSituation] = None,
) -> Optional[MetaChoice]:
    """Map LLM JSON → MetaChoice, or None when the choice is unusable.

    Hard contracts: unpaid look debt; ACT while referent search incomplete.
    Budgets / hard_block stay advisory in the packet. Optional ``capability`` on
    ACT is kept when it names an offered housekeeping verb.
    """
    action = _parse_action(raw)
    if action is None:
        return None

    # Entity-resolution SEARCH owns the epistemic move when criteria are known,
    # the target is unresolved, and a scoped search facility exists. Generic
    # PERCEIVE for look debt must not starve SEARCH when the prior look already
    # answered visibility / search-availability (live 203259). Surprise still
    # forces PERCEIVE first.
    act_clear_early = bool(getattr(ctx, "act_clear", False))
    referent_repair_early = bool(getattr(ctx, "referent_repair_owed", False))
    destination_search_early = bool(getattr(ctx, "destination_search_needed", False))
    if (
        destination_search_early
        and not act_clear_early
        and not referent_repair_early
        and not bool(getattr(ctx, "search_exhausted", False))
        and not bool(getattr(ctx, "last_action_surprised", False))
    ):
        return MetaChoice(
            MetaAction.SEARCH,
            "contract: entity unresolved with searchable scope — SEARCH",
            {
                "search": 1.0,
                "destination_search": 1.0,
                "entity_resolution": 1.0,
                "llm_proposed": action.value,
                "source": "llm_contract",
            },
        )

    # Post-act / unpaid look is a contract, not a preference — always PERCEIVE.
    if _look_owed(ctx):
        scores: Dict[str, Any] = {
            "perceive": 1.0,
            "must_reperceive": 1.0,
            "llm_proposed": action.value,
            "source": "llm_contract",
        }
        if ctx.last_action_surprised:
            scores["surprise"] = 1.0
        return MetaChoice(
            MetaAction.PERCEIVE,
            "contract: look owed — perceive before re-acting",
            scores,
        )

    why = str(raw.get("why") or raw.get("reason") or "llm meta choice")
    conf = 0.0
    try:
        conf = float(raw.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0

    from plugin.agent.capabilities.housekeeping import is_meta_housekeeping_verb

    sit = situation or MetaSituation()
    offered_names = {
        str(c.get("name") or "").strip().lower().replace("-", "_")
        for c in (sit.housekeeping_capabilities or [])
        if isinstance(c, dict) and str(c.get("name") or "").strip()
    }
    storage_pressure = bool((sit.blockers or {}).get("storage_pressure"))
    capability = str(raw.get("capability") or "").strip().lower().replace("-", "_")
    if capability and not is_meta_housekeeping_verb(capability):
        # Non-housekeeping capability names are ignored at meta; decision owns those.
        capability = ""
    if capability and offered_names and capability not in offered_names:
        capability = ""
    last_housekeeping = str((sit.blockers or {}).get("last_housekeeping") or "").strip().lower()
    # Soft prefer under storage pressure when the model chose bare act:
    # after a relieve pass → recover/relaunch so perception can re-check;
    # otherwise → relieve once.
    if action is MetaAction.ACT and not capability and storage_pressure:
        if (
            last_housekeeping == "relieve_host_storage"
            and "recover_blocked_app" in offered_names
        ):
            capability = "recover_blocked_app"
            why = (why + "; prefer recover_blocked_app after relieve")[:200]
        elif "relieve_host_storage" in offered_names:
            capability = "relieve_host_storage"
            why = (why + "; prefer relieve_host_storage under storage_pressure")[:200]

    # Empty / zero-progress find ⇒ leave the branch before another SEARCH.
    retreat_owed = bool(getattr(ctx, "search_retreat_owed", False)) or (
        bool(getattr(ctx, "search_episode_failed", False))
        and not bool(getattr(ctx, "search_episode_complete", False))
    )
    if retreat_owed and action is MetaAction.SEARCH:
        explore_exhausted = bool(getattr(ctx, "backtrack_exhausted", False)) or bool(
            getattr(ctx, "probe_exhausted", False)
        )
        if not explore_exhausted:
            return MetaChoice(
                MetaAction.EXPLORE,
                "contract: find returned empty/zero progress — explore before re-search",
                {
                    "explore": 1.0,
                    "llm_proposed": action.value,
                    "source": "llm_contract",
                },
            )
        think_exhausted = bool(getattr(ctx, "think_exhausted", False)) or bool(
            getattr(ctx, "information_gathering_exhausted", False)
        )
        if not think_exhausted:
            return MetaChoice(
                MetaAction.THINK,
                "contract: find returned empty/zero progress — replan before re-search",
                {
                    "think": 1.0,
                    "llm_proposed": action.value,
                    "source": "llm_contract",
                },
            )
        if ctx.hard_block:
            return MetaChoice(
                MetaAction.ASK,
                "contract: search retreat exhausted — escalate",
                {
                    "ask": 1.0,
                    "llm_proposed": action.value,
                    "source": "llm_contract",
                },
            )

    # Wrong patient selected after invoke/select → ACT repair, not observe/explore.
    # Exception: REFERENT_MISMATCH on a container/destination role is identity
    # failure — resume SEARCH/resolve, do not re-ACT the same row.
    referent_repair = bool(getattr(ctx, "referent_repair_owed", False))
    role_identity_search = bool(getattr(ctx, "role_identity_search_owed", False))
    if (
        role_identity_search
        and not bool(getattr(ctx, "search_exhausted", False))
        and action
        in {MetaAction.ACT, MetaAction.EXPLORE, MetaAction.THINK, MetaAction.PERCEIVE}
    ):
        return MetaChoice(
            MetaAction.SEARCH,
            "contract: role identity mismatch — SEARCH/resolve, do not re-act same candidate",
            {
                "search": 1.0,
                "referent_mismatch": 1.0,
                "llm_proposed": action.value,
                "source": "llm_contract",
            },
        )
    if referent_repair and action in {
        MetaAction.EXPLORE,
        MetaAction.SEARCH,
        MetaAction.THINK,
    }:
        return MetaChoice(
            MetaAction.ACT,
            "contract: referent mismatch — select/cancel matching patient before re-invoke",
            {
                "act": 1.0,
                "referent_repair": 1.0,
                "llm_proposed": action.value,
                "source": "llm_contract",
            },
        )

    # Effect closure / route discovery: content known but affordance latent, or
    # a reveal probe still unpaid after look → EXPLORE, not instrumental re-ACT.
    # Skip when referent repair owns the next move (ACT select, not EXPLORE),
    # when the perceptor already reports the goal act is clear, or when the
    # reveal episode has already failed / probe budget is spent.
    act_clear = bool(getattr(ctx, "act_clear", False))
    reveal_failed = bool(getattr(ctx, "reveal_episode_failed", False))
    route_owed = bool(getattr(ctx, "route_discovery_owed", False))
    reveal_unclosed = bool(getattr(ctx, "incomplete_reveal", False)) or bool(
        getattr(ctx, "expected_overlay_missing", False)
    )
    explore_exhausted = bool(getattr(ctx, "probe_exhausted", False)) or bool(
        getattr(ctx, "backtrack_exhausted", False)
    )
    if act_clear and action is MetaAction.EXPLORE and not referent_repair:
        return MetaChoice(
            MetaAction.ACT,
            "contract: act clear — commit goal control, do not re-explore",
            {
                "act": 1.0,
                "act_clear": 1.0,
                "llm_proposed": action.value,
                "source": "llm_contract",
            },
        )
    # Destination unresolved in open picker → SEARCH within picker (live 184742).
    # Wins over sticky EXPLORE intention once the foreground surface is the picker.
    destination_search = bool(getattr(ctx, "destination_search_needed", False))
    if (
        destination_search
        and not act_clear
        and not referent_repair
        and not bool(getattr(ctx, "search_exhausted", False))
        and action
        in {MetaAction.ACT, MetaAction.EXPLORE, MetaAction.THINK, MetaAction.PERCEIVE}
    ):
        return MetaChoice(
            MetaAction.SEARCH,
            "contract: destination unresolved in picker — search within destination scope",
            {
                "search": 1.0,
                "destination_search": 1.0,
                "llm_proposed": action.value,
                "source": "llm_contract",
            },
        )
    # Source container already open but source_object query unpaid → SEARCH
    # (live 214025: do not EXPLORE/reveal YouTube distractors). Do not arm
    # this before the container is open — that would block open_entity.
    content_search_owed = (
        bool(getattr(ctx, "address_known", False))
        and bool(getattr(ctx, "referent_search_needed", False))
        and not bool(getattr(ctx, "retrieve_ready", False))
        and not bool(getattr(ctx, "search_exhausted", False))
        and not retreat_owed
        and not act_clear
        and not referent_repair
    )
    if (
        content_search_owed
        and action
        in {MetaAction.ACT, MetaAction.EXPLORE, MetaAction.THINK}
    ):
        return MetaChoice(
            MetaAction.SEARCH,
            "contract: source_object query unpaid — SEARCH until binding-eligible content",
            {
                "search": 1.0,
                "content_search": 1.0,
                "llm_proposed": action.value,
                "source": "llm_contract",
            },
        )
    # Patient already established (SEARCH debt cleared) + reveal/select failure:
    # repair interaction affordance on the same patient — do not re-enter SEARCH
    # (live 113806: context_menu miss → locate_content found=False).
    if (
        reveal_failed
        and bool(getattr(ctx, "address_known", False))
        and not content_search_owed
        and not bool(getattr(ctx, "role_identity_search_owed", False))
        and not destination_search
        and action is MetaAction.SEARCH
    ):
        prefer_select = str(
            getattr(ctx, "reveal_prefer_capability", "") or ""
        ).strip().lower() in {"select_content", "select"}
        if prefer_select:
            return MetaChoice(
                MetaAction.ACT,
                "contract: patient established — repair affordance via select, not re-search",
                {
                    "act": 1.0,
                    "affordance_repair": 1.0,
                    "reveal_episode_failed": 1.0,
                    "forbid_search": 1.0,
                    "llm_proposed": action.value,
                    "source": "llm_contract",
                },
            )
        return MetaChoice(
            MetaAction.EXPLORE,
            "contract: patient established — repair affordance, not re-search",
            {
                "explore": 1.0,
                "affordance_repair": 1.0,
                "reveal_episode_failed": 1.0,
                "forbid_search": 1.0,
                "llm_proposed": action.value,
                "source": "llm_contract",
            },
        )
    # Active EXPLORE intention with methods left → keep EXPLORE (intent retry).
    # Exception: reveal already failed with select recovery — that is ACT.
    intention_active = bool(getattr(ctx, "intention_explore_active", False))
    intention_exhausted = bool(getattr(ctx, "intention_locally_exhausted", False))
    prefer_select_now = str(
        getattr(ctx, "reveal_prefer_capability", "") or ""
    ).strip().lower() in {"select_content", "select"}
    if (
        intention_active
        and not intention_exhausted
        and not referent_repair
        and not act_clear
        and not destination_search
        and not content_search_owed
        and not (reveal_failed and prefer_select_now)
        and action in {MetaAction.ACT, MetaAction.THINK, MetaAction.SEARCH}
    ):
        return MetaChoice(
            MetaAction.EXPLORE,
            "contract: active explore intention — continue method frontier",
            {
                "explore": 1.0,
                "intention_active": 1.0,
                "llm_proposed": action.value,
                "source": "llm_contract",
            },
        )
    # Local route exhausted: do not sticky-force ACT. THINK if hard-blocked;
    # otherwise honor LLM / fall through (SEARCH/EXPLORE/THINK admissible).
    if (
        (reveal_failed or explore_exhausted or intention_exhausted)
        and action is MetaAction.EXPLORE
        and not referent_repair
        and not act_clear
        and not intention_active
    ):
        # Live 213125: reveal failed + prefer select_content → ACT select, not
        # another explore (explore forbids select → observe thrash).
        prefer_select = str(
            getattr(ctx, "reveal_prefer_capability", "") or ""
        ).strip().lower() in {"select_content", "select"}
        look_owed = bool(getattr(ctx, "post_action_look_owed", False)) or bool(
            getattr(ctx, "awaiting_verification", False)
        )
        if reveal_failed and prefer_select and not look_owed:
            return MetaChoice(
                MetaAction.ACT,
                "contract: reveal failed — act select_content recovery, not re-explore",
                {
                    "act": 1.0,
                    "reveal_episode_failed": 1.0,
                    "select_recovery": 1.0,
                    "llm_proposed": action.value,
                    "source": "llm_contract",
                },
            )
        if ctx.hard_block:
            return MetaChoice(
                MetaAction.THINK,
                "contract: local reveal route exhausted — replan",
                {
                    "think": 1.0,
                    "reveal_episode_failed": 1.0 if reveal_failed else 0.0,
                    "llm_proposed": action.value,
                    "source": "llm_contract",
                },
            )
        # Allow EXPLORE only if LLM chose it for a *new* strategy; do not
        # re-latch the same incomplete reveal debt (already cleared in sync).
        pass
    if (
        (route_owed or reveal_unclosed)
        and not act_clear
        and not reveal_failed
        and not referent_repair
        and action is MetaAction.ACT
        and not capability
        and not explore_exhausted
    ):
        return MetaChoice(
            MetaAction.EXPLORE,
            "contract: content known / reveal unclosed — explore route, not re-act",
            {
                "explore": 1.0,
                "route_discovery": 1.0 if route_owed else 0.0,
                "incomplete_reveal": 1.0 if reveal_unclosed else 0.0,
                "llm_proposed": action.value,
                "source": "llm_contract",
            },
        )
    if (
        (route_owed or reveal_unclosed)
        and not act_clear
        and not reveal_failed
        and not referent_repair
        and action is MetaAction.SEARCH
        and not explore_exhausted
    ):
        return MetaChoice(
            MetaAction.EXPLORE,
            "contract: route discovery owed — explore affordances, not re-search",
            {
                "explore": 1.0,
                "llm_proposed": action.value,
                "source": "llm_contract",
            },
        )

    # Address known → RETRIEVE/ACT, not SEARCH — unless route discovery still owed.
    retrieve_ready = bool(getattr(ctx, "retrieve_ready", False))
    source_contact_ready = bool(getattr(ctx, "source_contact_open_ready", False))
    leave_wrong = bool(getattr(ctx, "leave_wrong_conversation_owed", False))
    wrong_locus = bool(getattr(ctx, "wrong_locus_recovery_owed", False))
    wrong_locus_kind = str(getattr(ctx, "wrong_locus_kind", "") or "").strip().lower()
    if (
        (retrieve_ready or source_contact_ready)
        and action is MetaAction.SEARCH
        and not route_owed
    ):
        return MetaChoice(
            MetaAction.ACT,
            (
                "contract: source contact row grounded — open, not search"
                if source_contact_ready
                else "contract: address known — retrieve/act, not search"
            ),
            {
                "act": 1.0,
                "retrieve": 1.0,
                "source_contact_open_ready": 1.0 if source_contact_ready else 0.0,
                "llm_proposed": action.value,
                "source": "llm_contract",
            },
        )
    if (
        leave_wrong
        and not source_contact_ready
        and action is MetaAction.SEARCH
        and not route_owed
    ):
        return MetaChoice(
            MetaAction.ACT,
            "contract: foreign conversation open — leave/list, not search",
            {
                "act": 1.0,
                "leave_wrong_conversation": 1.0,
                "llm_proposed": action.value,
                "source": "llm_contract",
            },
        )
    locate_verify = bool(getattr(ctx, "locate_effect_verify_owed", False))
    if locate_verify and action is MetaAction.SEARCH and not route_owed:
        return MetaChoice(
            MetaAction.PERCEIVE,
            "contract: locate effect unknown — perceive verify, not same SEARCH",
            {
                "perceive": 1.0,
                "locate_effect_verify": 1.0,
                "llm_proposed": action.value,
                "source": "llm_contract",
            },
        )
    if wrong_locus and action is MetaAction.SEARCH and not route_owed:
        if wrong_locus_kind == "patient":
            return MetaChoice(
                MetaAction.PERCEIVE,
                "contract: wrong patient locus — perceive reground, not search",
                {
                    "perceive": 1.0,
                    "wrong_locus_recovery": 1.0,
                    "llm_proposed": action.value,
                    "source": "llm_contract",
                },
            )
        return MetaChoice(
            MetaAction.ACT,
            "contract: wrong locus — restore required locus, not search/compose",
            {
                "act": 1.0,
                "wrong_locus_recovery": 1.0,
                "llm_proposed": action.value,
                "source": "llm_contract",
            },
            capability=(
                "dismiss_transient" if wrong_locus_kind == "field" else ""
            ),
        )

    # SEARCH requires criteria; without criteria → EXPLORE (affordance discovery).
    if action is MetaAction.SEARCH and not bool(
        getattr(ctx, "search_has_criteria", True)
    ):
        return MetaChoice(
            MetaAction.EXPLORE,
            "contract: search needs criteria — explore affordances instead",
            {
                "explore": 1.0,
                "llm_proposed": action.value,
                "source": "llm_contract",
            },
        )

    # Find-among-many incomplete ⇒ SEARCH, not ACT commit (unless housekeeping).
    # Do not force SEARCH while retreat is owed — that re-enters a dead episode.
    # Do not force SEARCH when address is known (retrieve path).
    # Do not force SEARCH when source contact row is open-ready or leave is owed.
    search_owed = (
        bool(
            getattr(ctx, "referent_search_needed", False)
            or getattr(ctx, "search_episode_incomplete", False)
        )
        and not bool(getattr(ctx, "search_episode_complete", False))
        and not retreat_owed
        and not retrieve_ready
        and not source_contact_ready
        and not leave_wrong
        and not wrong_locus
    )
    if (
        search_owed
        and action is MetaAction.ACT
        and not capability
        and not bool(getattr(ctx, "search_exhausted", False))
    ):
        return MetaChoice(
            MetaAction.SEARCH,
            "contract: referent search incomplete — search before act/commit",
            {
                "search": 1.0,
                "llm_proposed": action.value,
                "source": "llm_contract",
            },
        )

    choice = MetaChoice(
        action,
        why[:200],
        {"source": "llm", "confidence": conf, action.value: max(conf, 0.5)},
    )
    if capability and action is MetaAction.ACT:
        choice.capability = capability
        choice.scores["capability"] = capability
    return choice


def _llm_failed(reason: str, **extra: Any) -> MetaChoice:
    scores = {"source": "llm_failed", "ask": 1.0}
    scores.update(extra)
    return MetaChoice(MetaAction.ASK, reason[:200], scores)


def _invoke_chooser(
    realization: MetaChooser, packet: Dict[str, Any]
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        raw = realization.choose(META_SYSTEM, packet)
    except Exception as exc:
        logger.warning("meta chooser raised: %s", exc)
        return None, f"meta llm failed: {exc}"
    if not isinstance(raw, dict) or not raw:
        return None, "meta llm returned no choice"
    if not (raw.get("meta_action") or raw.get("action")):
        return None, "meta llm returned no meta_action"
    return raw, None


def resolve_meta_choice(
    ctx: MetaContext,
    *,
    goal_complete: bool = False,
    chooser: Optional[MetaChooser] = None,
    situation: Optional[MetaSituation] = None,
) -> MetaChoice:
    """Always run LLM (or injected chooser) meta inference — never ladder fallback."""
    realization = chooser or LlmMetaChooser()
    packet = meta_context_packet(
        ctx, goal_complete=bool(goal_complete), situation=situation
    )

    raw, err = _invoke_chooser(realization, packet)
    if err:
        return _llm_failed(err)

    choice = sanitize_meta_choice(
        raw, ctx, goal_complete=bool(goal_complete), situation=situation
    )
    if choice is not None:
        return choice

    # Unparseable / unknown meta_action: one LLM repair turn, still no ladder.
    rejected = str(raw.get("meta_action") or raw.get("action") or "")
    repair = dict(packet)
    repair["rejected_choice"] = {
        "meta_action": rejected,
        "why": "unknown or unusable meta_action; choose one of allowed_meta_actions",
    }
    raw2, err2 = _invoke_chooser(realization, repair)
    if err2:
        return _llm_failed(err2, rejected=rejected)
    choice2 = sanitize_meta_choice(
        raw2, ctx, goal_complete=bool(goal_complete), situation=situation
    )
    if choice2 is not None:
        scores = dict(choice2.scores or {})
        scores["repaired"] = 1.0
        choice2.scores = scores
        return choice2
    return _llm_failed(
        f"meta llm unusable after repair (rejected {rejected})",
        rejected=rejected,
    )
