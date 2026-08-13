"""Decision consultation: the brain chooses the next capability.

Pipeline:

    perceptor → world proposal + affordance frontier (visible / latent / probe)
    critic    → accept / reject / edit the world delta
    brain     → this module: pick one capability over accepted world + frontier

The perceptor makes choices *available*; it does not rank or commit them. This
module returns **one capability plus its argument**. Coordinates come from
grounding against accepted ``objects`` / frontier targets. Irreversible commits
stay gated.

Choice is text-LLM consultation only. There is no heuristic fallback that
invents a capability when the model is unavailable or returns an invalid choice
— the brain declines to ``observe`` so meta can look or retry.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

logger = logging.getLogger(__name__)

# Capabilities the decision-maker may name. Motor primitives are deliberately
# absent: choosing "click" is a mechanism decision the runtime already owns.
_CHOOSABLE_EXTRA = ("observe",)

_DECISION_SYSTEM = (
    "You choose the next capability for a macOS UI agent.\n"
    "You are given the ACCEPTED world document (critic-vetted), the closed "
    "affordance_frontier for the *current UI node* (observed + same-node "
    "latent/probe options, each tagged node_scope current|transition), "
    "optional perceptor_suggestions (visual ranking with why — advice only), "
    "task state, navigation, and the goal. You make the final choice.\n"
    "Return ONLY JSON: "
    '{"capability": "...", "target": "...", "why": "...", "confidence": 0-1}.\n'
    "Rules:\n"
    "- capability MUST be one of allowed_capabilities.\n"
    "- Prefer perceptor_suggestions when their why fits the accepted world and "
    "frontier; you may override when the suggestion conflicts with task state "
    "or node_scope.\n"
    "- If affordance_qc.expected_found is false, or the frontier lacks the "
    "critical same-node control for this surface (Forward on conversation, "
    "Send on forward_picker), choose observe and say that expected affordances "
    "seem unavailable so perception can close the node again.\n"
    "- Prefer affordance_frontier entries with node_scope=current that advance "
    "the goal; choosing node_scope=transition leaves this UI node.\n"
    "- Use latent/probe (same-node) only to reveal in-place controls before a "
    "transition when needed.\n"
    "- Never invent click scripts, coordinates, or menu paths.\n"
    "- Never choose anything in forbidden_capabilities.\n"
    "- commit_irreversible is only for Send/Delete/Confirm and only when the "
    "task state says the commit step is reached.\n"
    "- When the executive meta is search: only compose_search_query / "
    "resolve_entity / locate_content / observe. Never open_entity or commit — "
    "act meta opens after SearchResult.chosen.\n"
    "- resolve_entity is the ranking stage of find-among-many — choose among "
    "visible candidates when several rows could match a referent.\n"
    "- compose_search_query is only the query-authorship stage "
    "(leave target empty for the query arg); it does not finish search. "
    "The runtime still binds Search-field geometry from the perceived world.\n"
    "- On chat_list / search in phase reach_source with a non-empty source_query: "
    "prefer compose_search_query / search before open_entity. A chat snippet "
    "that echoes the typed query is not the intended hit — continue ranking. "
    "Never choose invoke_affordance, reveal_actions, locate_content, or "
    "commit_irreversible before the source conversation is open.\n"
    "- Once the source chat is open and source_query looks like a link hunt: "
    "prefer locate_content / reveal_actions on a URL-bearing message. Do not "
    "invoke_affordance (left-click) a plain text bubble that merely contains "
    "the query tokens. Motor alias right_click means reveal_actions.\n"
    "- locate_content makes content reachable inside the open surface; only "
    "use it when the open conversation is the intended source.\n"
    "- Skip any step whose result the world document already shows.\n"
    "- If prior_rejection is present, your previous choice was invalid — pick a "
    "different allowed capability that fixes that rejection.\n"
    "- capability_disclosure ranks the capabilities relevant to this situation "
    "(cheapest, most reliable, precondition-satisfied first) and groups the rest "
    "by family; prefer a relevant capability over one whose preconditions are "
    "not yet met.\n"
    "- target is the capability argument (a label, a query, or empty)."
)


def decision_consultation_enabled() -> bool:
    return os.getenv("HERMES_DECISION_CONSULTATION", "1").strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }


def decision_llm_enabled() -> bool:
    return os.getenv("HERMES_DECISION_LLM", "1").strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }


@runtime_checkable
class DecisionChooser(Protocol):
    def choose(self, system: str, packet: Dict[str, Any]) -> Dict[str, Any]:
        """Return ``{"capability": str, "target": str, "why": str, ...}``."""


@dataclass
class TaskState:
    """Where the task stands — not a UI reading."""

    phase: str = "reach_source"
    open_conversation: str = ""
    source_chat_open: bool = False
    content_located: bool = False
    content_visible: bool = False
    # Bound content patient is selected with corroborating chrome (not merely visible).
    referent_selected: bool = False
    # BindingStatus of the content object: unresolved|ambiguous|provisional|confirmed|…
    referent_binding_status: str = ""
    # Last selection_consistency verdict; False blocks object-scoped invoke.
    selection_consistent: bool = True
    search_query: str = ""
    search_empty: bool = False
    attempts: List[Dict[str, Any]] = field(default_factory=list)
    exhausted: List[Any] = field(default_factory=list)
    last_action: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "open_conversation": self.open_conversation,
            "source_chat_open": self.source_chat_open,
            "content_located": self.content_located,
            "content_visible": self.content_visible,
            "referent_selected": self.referent_selected,
            "referent_binding_status": self.referent_binding_status,
            "selection_consistent": self.selection_consistent,
            "search_query": self.search_query,
            "search_empty": self.search_empty,
            "attempts": self.attempts[-6:],
            "exhausted": list(self.exhausted)[:6],
            "last_action": self.last_action,
        }


@dataclass
class NavigationInfo:
    """Where the agent can go from here, and by which capability."""

    surface: str = ""
    focused_field_role: str = "none"
    reachable: Dict[str, List[str]] = field(default_factory=dict)
    forbidden: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "surface": self.surface,
            "focused_field_role": self.focused_field_role,
            "reachable_surfaces": self.reachable,
            "forbidden_capabilities": self.forbidden,
        }


@dataclass
class DecisionBrief:
    goal: Dict[str, Any] = field(default_factory=dict)
    world: Dict[str, Any] = field(default_factory=dict)
    task_state: TaskState = field(default_factory=TaskState)
    navigation: NavigationInfo = field(default_factory=NavigationInfo)
    capabilities: List[str] = field(default_factory=list)
    candidates: List[str] = field(default_factory=list)
    # Snapshot of ExecutionState.search_episode for sanitize / chooser packet.
    search_episode: Optional[Dict[str, Any]] = None
    # Executive meta kind for this decision (search ⇒ find-stage allowlist).
    meta_action: str = "act"
    # Closed current-node frontier (observed / latent / probe + node_scope).
    affordance_frontier: Dict[str, Any] = field(default_factory=dict)
    # Stage1 visual ranking with why — advisory only.
    perceptor_suggestions: List[Dict[str, Any]] = field(default_factory=list)
    # Stage1 QC: whether critical same-node affordances were figured out.
    affordance_qc: Dict[str, Any] = field(default_factory=dict)
    # Progressive-disclosure view of the capability registry: the relevant
    # shortlist for this situation, the family taxonomy, and how much of the
    # catalog that shortlist is — so the model sees "N of M relevant" rather
    # than a flat verb dump.
    capability_disclosure: Dict[str, Any] = field(default_factory=dict)
    # Deprecated alias of the top suggestion.
    perceptor_suggestion: Dict[str, Any] = field(default_factory=dict)
    # Effect-closure + route-discovery signals from the last post-act look.
    effect_closure: Dict[str, Any] = field(default_factory=dict)
    # Honest perceptor stance: act_clear requires actuatable geometry.
    affordance_stance: str = ""
    act_clear: bool = False
    # Terminal empty reveal → ACT must escalate route, not Observe (live 181059).
    reveal_episode_failed: bool = False

    def to_packet(self) -> Dict[str, Any]:
        packet = {
            "goal": self.goal,
            "world_model": self.world,
            "task_state": self.task_state.to_dict(),
            "navigation": self.navigation.to_dict(),
            "allowed_capabilities": self.capabilities,
            "forbidden_capabilities": self.navigation.forbidden,
            "capability_disclosure": self.capability_disclosure,
            "visible_candidates": self.candidates[:24],
            "affordance_frontier": self.affordance_frontier,
            "perceptor_suggestions": self.perceptor_suggestions[:3],
            "affordance_qc": self.affordance_qc,
            "affordance_stance": self.affordance_stance,
            "act_clear": bool(self.act_clear),
            "reveal_episode_failed": bool(self.reveal_episode_failed),
        }
        if self.effect_closure:
            packet["effect_closure"] = dict(self.effect_closure)
        if isinstance(self.search_episode, dict) and self.search_episode:
            try:
                from plugin.agent.capabilities.search_episode import (
                    search_selection_trace,
                )

                trace = search_selection_trace(self.search_episode)
            except Exception:
                trace = {}
            ledger = list(
                (trace.get("hypothesis_ledger") if trace else None)
                or self.search_episode.get("hypothesis_ledger")
                or []
            )[:4]
            packet["search_episode"] = {
                "status": self.search_episode.get("status"),
                "role": self.search_episode.get("role"),
                "referent": self.search_episode.get("referent"),
                "query": self.search_episode.get("query"),
                "candidate_count": self.search_episode.get("candidate_count"),
                "chosen_label": self.search_episode.get("chosen_label"),
                "explore_label": self.search_episode.get("explore_label"),
                "choice_confidence": self.search_episode.get("choice_confidence"),
                "role_resolved": self.search_episode.get("role_resolved"),
                "space": self.search_episode.get("space"),
                "hypothesis_ledger": ledger,
                "path": str(
                    (trace or {}).get("selection_path")
                    or self.search_episode.get("selection_path")
                    or ""
                ),
                "selection_trace": {
                    k: (trace or {}).get(k)
                    for k in (
                        "selection_path",
                        "selected_hypothesis",
                        "act_target",
                        "candidate_count",
                        "choice_confidence",
                    )
                    if (trace or {}).get(k) not in (None, "", [])
                },
            }
        return packet


@dataclass
class DecisionOutcome:
    ok: bool = False
    capability: str = ""
    target: str = ""
    why: str = ""
    confidence: float = 0.0
    realization: str = ""
    # Survive sanitize → next_action → Action/PlanStep → controller.
    target_kind: str = ""
    establishes_roles: List[str] = field(default_factory=list)
    action_is_navigation: bool = False
    legacy_semantics: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "capability": self.capability,
            "target": self.target,
            "why": self.why[:200],
            "confidence": round(float(self.confidence or 0.0), 3),
            "realization": self.realization,
            "target_kind": self.target_kind,
            "establishes_roles": list(self.establishes_roles or []),
            "action_is_navigation": bool(self.action_is_navigation),
            "legacy_semantics": bool(self.legacy_semantics),
        }


def choosable_capabilities() -> List[str]:
    from plugin.agent.capabilities.catalog import realized_verbs

    return list(realized_verbs()) + list(_CHOOSABLE_EXTRA)


def ranked_capabilities(
    *,
    surface: str = "",
    forbidden: Optional[Iterable[str]] = None,
    facts: Optional[Iterable[str]] = None,
    meta_action: str = "act",
) -> List[str]:
    """Consultation shortlist, ranked by the executive's capability registry.

    Same choosable set as before, minus forbidden verbs, but ordered by the
    registry's value score (cheap, reliable, reversible first) and filtered to
    what fits the meta-action. This is hierarchical retrieval replacing the flat
    catalog dump the model used to receive.
    """
    from plugin.agent.executive.capabilities import default_registry
    from plugin.agent.executive.meta_action import (
        EXPLORE_FORBIDDEN_CAPABILITIES,
        EXPLORE_STAGE_CAPABILITIES,
        SEARCH_FORBIDDEN_CAPABILITIES,
        SEARCH_STAGE_CAPABILITIES,
    )

    banned = {str(f).strip().lower() for f in (forbidden or [])}
    meta = str(meta_action or "act").strip().lower()
    if meta == "probe":
        meta = "explore"
    if meta == "search":
        banned |= set(SEARCH_FORBIDDEN_CAPABILITIES)
        # Compound catalog ``search`` is meta-level now — stages only.
        banned.add("search")
    elif meta == "explore":
        banned |= set(EXPLORE_FORBIDDEN_CAPABILITIES)
        banned.add("search")
        # Failed context-click/hover must escalate to select_content (live 213125:
        # explore forbade select → only observe/reveal → thrash).
        fact_set = {str(f).strip().lower() for f in (facts or [])}
        if (
            "reveal_episode_failed" in fact_set
            or "failed_reveal" in fact_set
            or "prefer_select_content" in fact_set
        ):
            banned.discard("select_content")
    choosable = [c for c in choosable_capabilities() if c not in banned]
    if meta == "search":
        stages = set(SEARCH_STAGE_CAPABILITIES) | {"observe"}
        choosable = [c for c in choosable if c in stages] or ["observe"]
    elif meta == "explore":
        stages = set(EXPLORE_STAGE_CAPABILITIES) | {"observe"}
        fact_set = {str(f).strip().lower() for f in (facts or [])}
        if (
            "reveal_episode_failed" in fact_set
            or "failed_reveal" in fact_set
            or "prefer_select_content" in fact_set
        ):
            stages = set(stages) | {"select_content"}
        choosable = [c for c in choosable if c in stages] or ["observe"]
    registry = default_registry()
    ordered = registry.shortlist_for(
        meta_action=meta,
        facts=list(facts or []),
        limit=len(choosable) or 1,
    )
    ranked = [d.verb for d in ordered if d.verb in choosable]
    # Anything the registry does not know about (e.g. _CHOOSABLE_EXTRA) keeps
    # its place at the end rather than being dropped.
    ranked += [c for c in choosable if c not in set(ranked)]
    return ranked


def situation_facts(
    task_state: "TaskState",
    *,
    candidates: Iterable[str] = (),
    goal: Optional[Dict[str, Any]] = None,
    execution_state: Any = None,
    affordance_frontier: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """The facts the registry gates capability preconditions against.

    These are the situation's answer to "what is true right now" in the same
    vocabulary the capability descriptors declare their preconditions in
    (``task_evidence``, ``candidate_set``, ``affordance_set`` ...). Passing them
    to the registry lets retrieval rank precondition-satisfied capabilities
    ahead of ones that cannot run yet, instead of a static value ordering.
    Precondition-failing verbs are never dropped from the final list — the
    registry only reorders — so an incomplete fact set degrades gracefully.
    """
    goal = goal or {}
    facts: List[str] = []
    cand = [c for c in candidates if str(c or "").strip()]

    # There is always some goal evidence to author a query from.
    if goal.get("source_conversation") or goal.get("source_query"):
        facts.append("task_evidence")
    # A surface that hosts a search field is searchable.
    if task_state.phase in {"reach_source", "hunt_content", "choose_destination"}:
        facts.append("searchable_surface")
    # An open source chat is a surface content can be located within.
    if task_state.source_chat_open or task_state.open_conversation:
        facts.append("open_surface")
    # Visible rows/objects are addressable entities, and a set of them to pick from.
    if cand:
        facts.append("candidate_set")
    if cand or task_state.open_conversation:
        facts.append("addressable_entity")
    # A revealed action set exists once grounded controls are on the substrate
    # (or the phase machine already entered invoke_forward).
    if task_state.phase == "invoke_forward" or _affordance_set_present(
        execution_state, affordance_frontier
    ):
        facts.append("affordance_set")
    # Object-scoped invoke needs a selected patient matching the binding.
    if bool(getattr(task_state, "referent_selected", False)) and bool(
        getattr(task_state, "selection_consistent", True)
    ):
        facts.append("selection")
    # A commit target is gated open only at the phases where committing is due.
    if task_state.phase in {"choose_destination", "act_on_content"}:
        facts.append("gated_target")
    return facts


def _affordance_set_present(
    execution_state: Any, affordance_frontier: Optional[Dict[str, Any]]
) -> bool:
    if execution_state is not None:
        try:
            from plugin.agent.affordance_frontier import grounded_affordance_set_of

            if grounded_affordance_set_of(execution_state):
                return True
        except Exception:
            pass
    frontier = affordance_frontier
    if not isinstance(frontier, dict) and execution_state is not None:
        frontier = getattr(execution_state, "last_affordance_frontier", None)
    if not isinstance(frontier, dict):
        return False
    for aff in frontier.get("observed_actions") or []:
        if not isinstance(aff, dict):
            continue
        if str(aff.get("family") or "") not in {
            "invoke_affordance",
            "commit_irreversible",
        }:
            continue
        if aff.get("actuators"):
            return True
    return False


def _pressure_facts_from_features(features: Any = None) -> List[str]:
    """Housekeeping substrate facts from overlay extras (storage / chrome)."""
    extras: Dict[str, Any] = {}
    if features is None:
        return []
    if hasattr(features, "extras") and isinstance(features.extras, dict):
        extras = features.extras
    elif isinstance(features, dict):
        extras = dict(features.get("extras") or features)
    facts: List[str] = []
    if extras.get("storage_pressure") or extras.get("system_warnings"):
        facts.append("host_resource_pressure")
        facts.append("transient_chrome")
    elif extras.get("blocking_overlay") or extras.get("has_dialog") or getattr(
        features, "has_dialog", False
    ):
        facts.append("transient_chrome")
    return facts


def navigation_options(surface: str, field_role: str = "") -> NavigationInfo:
    """Surfaces reachable from here and the capability that opens each."""
    from plugin.agent.world_critic import (
        ACTION_OPENS_SURFACE,
        SURFACE_PARENTS,
        sidebar_search_forbidden,
    )

    surf = str(surface or "").strip().lower()
    role = str(field_role or "").strip().lower()
    reachable: Dict[str, List[str]] = {}
    for child, parents in SURFACE_PARENTS.items():
        if child == surf or surf not in parents:
            continue
        openers = sorted(ACTION_OPENS_SURFACE.get(child, set()))
        reachable[child] = [o for o in openers if o in set(choosable_capabilities())]

    forbidden: List[str] = []
    if sidebar_search_forbidden(surface=surf, role=role):
        # Sidebar search from a picker/dialog is the drift class that opened the
        # wrong chat; the decision-maker must not be able to name it.
        forbidden = ["compose_search_query", "open_search"]
    return NavigationInfo(
        surface=surf,
        focused_field_role=role or "none",
        reachable=reachable,
        forbidden=forbidden,
    )


def task_state_from_context(
    goal: Any,
    *,
    world_document: Optional[Dict[str, Any]] = None,
    features: Any = None,
    execution_state: Any = None,
) -> TaskState:
    """Derive the task phase from accepted world plus runtime bookkeeping."""
    from plugin.agent.capabilities.resolve_entity import open_matches_referent
    from plugin.agent.executive.sync import bind_goal, commit_reading

    bind_goal(execution_state, goal)

    doc = world_document if isinstance(world_document, dict) else {}
    extras = {}
    if features is not None and isinstance(getattr(features, "extras", None), dict):
        extras = features.extras

    source = str(getattr(goal, "contact", "") or "").strip()
    link_q = str(getattr(goal, "link_query", "") or "").strip()
    surface = str(doc.get("surface") or extras.get("wa_screen") or "").strip().lower()
    open_conversation = str(
        doc.get("open_conversation") or extras.get("open_conversation") or ""
    ).strip()
    conv_open = bool(getattr(features, "conversation_open", False)) or surface == "conversation"
    source_open = bool(
        conv_open and source and open_matches_referent(open_conversation, source)
    )
    # Locate execution_ok alone is not content_located (185549 AX-blind).
    located = bool(
        link_q
        and str(extras.get("last_locate_query") or "").strip().lower() == link_q.lower()
        and (
            bool(extras.get("last_locate_found"))
            or str(extras.get("last_locate_effect_status") or "").lower() == "achieved"
        )
    )
    # Close EffectStatus UNKNOWN only on ACHIEVED here. Failed verify (still
    # blind / no patient) is resolved after a paid look in the controller —
    # never on the immediate post-locate frame before visual verify runs.
    if (
        execution_state is not None
        and link_q
        and bool(getattr(execution_state, "locate_effect_verify_owed", False))
        and isinstance(doc, dict)
    ):
        try:
            from plugin.agent.capabilities.locate_content import (
                resolve_locate_effect_verification,
            )
            from plugin.agent.source_query_binding import (
                document_locates_source_query,
                evaluate_source_object_match,
            )

            query_visible = bool(document_locates_source_query(doc, link_q))
            content_located = False
            if query_visible:
                open_c = str(doc.get("open_conversation") or "")
                source = str(
                    getattr(goal, "contact", None)
                    or getattr(goal, "source_conversation", None)
                    or (goal.get("source_conversation") if isinstance(goal, dict) else "")
                    or (goal.get("contact") if isinstance(goal, dict) else "")
                    or ""
                ).strip()
                # Originator only from typed goal relation — never alias to container.
                want_origin = str(
                    getattr(goal, "originator", None)
                    or (goal.get("originator") if isinstance(goal, dict) else "")
                    or ""
                ).strip()
                for obj in doc.get("objects") or []:
                    if not isinstance(obj, dict):
                        continue
                    gm = evaluate_source_object_match(
                        text=str(obj.get("text") or obj.get("label") or ""),
                        kind=str(obj.get("kind") or ""),
                        query=link_q,
                        container_open=open_c,
                        expected_container=source,
                        expected_originator=want_origin,
                        sender=obj.get("sender") or obj.get("originator"),
                        perception_matches_goal=bool(obj.get("matches_goal")),
                        role=str(obj.get("role") or obj.get("field_role") or ""),
                    )
                    if gm.binding_eligible:
                        content_located = True
                        break
            if content_located or query_visible:
                resolve_locate_effect_verification(
                    execution_state,
                    content_located=content_located,
                    query_visible=query_visible and not content_located,
                )
                if content_located or (
                    str(getattr(execution_state, "last_locate_effect_status", "") or "")
                    == "achieved"
                ):
                    located = True
        except Exception:
            pass
    visible = bool(
        extras.get("source_content_visible")
        or extras.get("timeline_query_hit")
        or extras.get("query_in_timeline")
    )
    # Soft extras can latch from distractor URLs — downgrade only (do not
    # promote preview text into content_located; that skips hunt_content).
    if link_q and visible:
        try:
            from plugin.agent.source_query_binding import document_locates_source_query

            if isinstance(doc, dict) and doc.get("objects") is not None:
                if not document_locates_source_query(doc, link_q):
                    visible = False
        except Exception:
            pass

    last_action: Dict[str, Any] = {}
    step = getattr(execution_state, "last_plan_step", None) if execution_state else None
    if step is not None:
        last_action = {
            "family": str(getattr(step, "action_family", "") or ""),
            "target": str(getattr(step, "semantic_target", "") or ""),
            "text": str(getattr(step, "text", "") or ""),
        }

    attempts = list(getattr(execution_state, "search_attempt_log", None) or [])
    if not attempts and isinstance(doc.get("attempts"), list):
        attempts = [a for a in doc["attempts"] if isinstance(a, dict)]

    if surface == "forward_picker":
        phase = "choose_destination"
    elif surface in {"context_menu", "action_menu", "selection_mode"}:
        phase = "invoke_forward"
    elif not source_open:
        phase = "reach_source"
    elif link_q and not (located or visible):
        phase = "hunt_content"
    else:
        phase = "act_on_content"

    # The derivation above is a proposal, not the answer. The workspace holds
    # the phase and the open conversation, so a reading that contradicts what
    # the executive already accepted has to justify itself there.
    workspace = commit_reading(
        execution_state,
        source="task_state",
        surface=surface,
        open_conversation=open_conversation,
        phase=phase,
        confidence=0.6,
        evidence=f"derived from surface {surface!r}",
    )
    if workspace is not None:
        phase = workspace.phase or phase
        open_conversation = workspace.open_conversation or open_conversation
        source_open = bool(
            conv_open and source and open_matches_referent(open_conversation, source)
        )

    # Phase-gate Search stash: clear once we leave reach_source, or once a true
    # overlay owns the scene. Do NOT clear merely because AX mislabels search
    # results as conversation (live 131221) — that wiped Search geometry while
    # the agent was still hunting the source chat.
    if execution_state is not None:
        overlay_surfaces = {
            "context_menu",
            "forward_picker",
            "action_menu",
            "selection_mode",
            "dialog",
        }
        if phase != "reach_source" or surface in overlay_surfaces:
            try:
                if getattr(execution_state, "last_filter_geometry", None):
                    execution_state.last_filter_geometry = None
            except Exception:
                pass

    # Referent selection / binding honesty (forward_task predicates + consistency).
    ft: Dict[str, Any] = {}
    if isinstance(extras.get("forward_task"), dict):
        ft = dict(extras.get("forward_task") or {})
    if not ft and isinstance(doc.get("forward_task"), dict):
        ft = dict(doc.get("forward_task") or {})
    if not ft and execution_state is not None:
        try:
            hints = getattr(execution_state, "overlay_hints", None)
            if not isinstance(hints, dict):
                wm = getattr(execution_state, "world_model", None)
                hints = getattr(wm, "overlay_hints", None) if wm is not None else None
            if isinstance(hints, dict) and isinstance(hints.get("forward_task"), dict):
                ft = dict(hints.get("forward_task") or {})
        except Exception:
            ft = ft
    predicates = ft.get("predicates") if isinstance(ft.get("predicates"), dict) else {}
    bindings = ft.get("bindings") if isinstance(ft.get("bindings"), dict) else {}
    source_obj = (
        bindings.get("source_object")
        if isinstance(bindings.get("source_object"), dict)
        else {}
    )
    referent_selected = bool(predicates.get("source_object_selected"))
    referent_status = str(source_obj.get("status") or "").strip().lower()
    selection_consistent = True
    if execution_state is not None:
        sel = getattr(execution_state, "last_selection_consistency", None)
        if isinstance(sel, dict) and sel.get("applicable") and sel.get("consistent") is False:
            selection_consistent = False
            referent_selected = False

    return TaskState(
        phase=phase,
        open_conversation=open_conversation,
        source_chat_open=source_open,
        content_located=located,
        content_visible=visible,
        referent_selected=referent_selected,
        referent_binding_status=referent_status,
        selection_consistent=selection_consistent,
        search_query=str(extras.get("search_query") or extras.get("search_query_hint") or ""),
        search_empty=bool(extras.get("search_empty")),
        attempts=[a for a in attempts if isinstance(a, dict)],
        exhausted=list(doc.get("exhausted") or []),
        last_action=last_action,
    )


def build_decision_brief(
    goal: Any,
    *,
    world_document: Optional[Dict[str, Any]] = None,
    features: Any = None,
    execution_state: Any = None,
    affordance_frontier: Optional[Dict[str, Any]] = None,
    perceptor_suggestions: Optional[List[Dict[str, Any]]] = None,
    affordance_qc: Optional[Dict[str, Any]] = None,
    perceptor_action: Optional[Dict[str, Any]] = None,
) -> DecisionBrief:
    from plugin.agent.capabilities.resolve_entity import candidates_from_context

    doc = world_document if isinstance(world_document, dict) else {}
    task_state = task_state_from_context(
        goal,
        world_document=doc,
        features=features,
        execution_state=execution_state,
    )
    navigation = navigation_options(
        str(doc.get("surface") or ""),
        str(doc.get("focused_field_role") or getattr(execution_state, "focused_field_role", "") or ""),
    )
    rows = candidates_from_context(features=features, world_document=doc)
    frontier: Dict[str, Any] = {}
    if isinstance(affordance_frontier, dict) and affordance_frontier:
        frontier = dict(affordance_frontier)
    elif execution_state is not None:
        stored = getattr(execution_state, "last_affordance_frontier", None)
        if isinstance(stored, dict):
            frontier = dict(stored)
    # Compact for the chooser: families + labels + node_scope.
    frontier_view = {
        "surface": str(frontier.get("surface") or ""),
        "node_closure": dict(frontier.get("node_closure") or {}),
        "observed_actions": [
            {
                "family": str(a.get("family") or ""),
                "label": str(
                    a.get("target_label") or a.get("label") or a.get("text") or ""
                )[:80],
                "target_id": a.get("target_id"),
                "node_scope": str(a.get("node_scope") or "current"),
                "why": str(a.get("why") or "")[:120],
            }
            for a in (frontier.get("observed_actions") or [])[:12]
            if isinstance(a, dict)
        ],
        "latent_actions": [
            {
                "family": str(a.get("family") or ""),
                "label": str(a.get("target_label") or a.get("label") or "")[:80],
                "available_after": str(a.get("available_after") or ""),
                "node_scope": str(a.get("node_scope") or "current"),
            }
            for a in (frontier.get("latent_actions") or [])[:8]
            if isinstance(a, dict)
        ],
        "probe_actions": [
            {
                "family": str(a.get("family") or ""),
                "label": str(a.get("target_label") or a.get("label") or "")[:80],
                "may_reveal": [
                    (m.get("label") if isinstance(m, dict) else str(m))
                    for m in (a.get("may_reveal") or [])[:4]
                ],
                "node_scope": str(a.get("node_scope") or "current"),
            }
            for a in (frontier.get("probe_actions") or [])[:4]
            if isinstance(a, dict)
        ],
    }
    del perceptor_action
    suggestions = [
        {
            "rank": int(s.get("rank") or i + 1),
            "family": str(s.get("family") or ""),
            "target": str(s.get("text") or s.get("target_label") or ""),
            "target_id": s.get("target_id"),
            "confidence": s.get("confidence"),
            "why": str(s.get("why") or s.get("reason") or "")[:160],
        }
        for i, s in enumerate(perceptor_suggestions or [])
        if isinstance(s, dict) and str(s.get("family") or "").strip()
    ][:3]
    goal_dict = {
        "operation": str(getattr(goal, "kind", "") or ""),
        # Goal.contact is the source/container referent in this procedure path.
        "source_conversation": str(getattr(goal, "contact", "") or ""),
        "source_query": str(getattr(goal, "link_query", "") or ""),
        "destination": str(getattr(goal, "target_contact", "") or ""),
        # Typed authorship / addressee — never alias from contact.
        "originator": str(getattr(goal, "originator", "") or ""),
        "recipient": str(getattr(goal, "recipient", "") or ""),
    }
    candidate_labels = [str(r.get("label") or "") for r in rows if r.get("label")]

    # The registry now retrieves against the situation, not in the abstract:
    # what is true right now (facts) plus what the executive last decided to do
    # (meta_action) drive both the ranked shortlist and its disclosure view.
    facts = situation_facts(
        task_state,
        candidates=candidate_labels,
        goal=goal_dict,
        execution_state=execution_state,
        affordance_frontier=frontier if isinstance(frontier, dict) else None,
    )
    for fact in _pressure_facts_from_features(features):
        if fact not in facts:
            facts.append(fact)
    meta_action = str(getattr(execution_state, "last_meta_action", "") or "act")

    from plugin.agent.executive.capabilities import default_registry
    from plugin.agent.capabilities.search_episode import (
        ensure_search_episode_from_brief,
        maybe_complete_source_contact_from_visible_row,
        search_episode_of,
    )

    # Grounded source contact row completes the source find before compose-first
    # ranking arms (live 145943).
    if execution_state is not None and not task_state.source_chat_open:
        maybe_complete_source_contact_from_visible_row(
            execution_state,
            document=doc,
            contact=str(goal_dict.get("source_conversation") or ""),
            source_chat_open=bool(task_state.source_chat_open),
        )

    closure = getattr(execution_state, "last_effect_closure", None) if execution_state else None
    if not isinstance(closure, dict):
        closure = {}
    handoff = getattr(execution_state, "reveal_handoff", None) if execution_state else None
    if isinstance(handoff, dict) and handoff.get("incomplete_reveal"):
        closure = {
            **closure,
            "incomplete_reveal": True,
            "fingerprint": str(
                closure.get("fingerprint")
                or getattr(execution_state, "last_failed_motor_key", "")
                or ""
            ),
        }
    reveal_episode_failed = False
    if isinstance(handoff, dict):
        reveal_episode_failed = bool(handoff.get("failed_reveal")) or str(
            handoff.get("status") or ""
        ).strip().lower() in {"failed_reveal", "failed"}
    if not reveal_episode_failed and isinstance(closure, dict):
        reveal_episode_failed = bool(closure.get("reveal_episode_failed"))
    if execution_state is not None and not reveal_episode_failed:
        reveal_episode_failed = bool(
            getattr(execution_state, "reveal_episode_failed", False)
        )
    # Unban select_content for explore shortlists when reveal already failed.
    if reveal_episode_failed:
        for tok in ("reveal_episode_failed", "prefer_select_content"):
            if tok not in facts:
                facts.append(tok)

    disclosure = default_registry().disclosure(
        meta_action=meta_action,
        facts=facts,
        limit=6,
    )
    if reveal_episode_failed:
        prefer_cap = ""
        if execution_state is not None:
            prefer_cap = str(
                getattr(execution_state, "reveal_prefer_capability", "") or ""
            ).strip().lower()
        closure = {
            **closure,
            "reveal_episode_failed": True,
            "reveal_prefer_capability": prefer_cap or "select_content",
        }
    sel_cons = (
        getattr(execution_state, "last_selection_consistency", None)
        if execution_state
        else None
    )
    if isinstance(sel_cons, dict) and sel_cons.get("applicable") and sel_cons.get(
        "consistent"
    ) is False:
        closure = {
            **closure,
            "referent_repair_owed": True,
            "fingerprint": str(
                closure.get("fingerprint")
                or getattr(execution_state, "last_failed_motor_key", "")
                or ""
            ),
        }
    world_surface = str(doc.get("surface") or "").strip().lower()
    try:
        from plugin.agent.capabilities.branch_fitness import selection_chrome_present

        if selection_chrome_present(doc) and world_surface in {
            "",
            "conversation",
            "context_menu",
            "action_menu",
        }:
            world_surface = "selection_mode"
    except Exception:
        pass
    stance = ""
    act_clear = False
    if execution_state is not None:
        stance = str(
            getattr(execution_state, "last_affordance_stance", "") or ""
        ).strip().lower()
        act_clear = stance == "act_clear"
        if not act_clear:
            uni = getattr(execution_state, "last_unified_proposal", None)
            if isinstance(uni, dict):
                stance = str(uni.get("affordance_stance") or stance or "").strip().lower()
                act_clear = stance == "act_clear"
        if not act_clear:
            try:
                from plugin.agent.affordance_frontier import grounded_affordance_set_of

                act_clear = len(grounded_affordance_set_of(execution_state) or []) > 0
            except Exception:
                act_clear = bool(
                    getattr(execution_state, "last_grounded_affordance_set", None)
                )
    if not stance and affordance_qc and bool(
        (affordance_qc or {}).get("expected_found")
    ):
        # QC alone is not act_clear (geometry honesty); leave stance empty.
        pass
    caps = ranked_capabilities(
        surface=str(doc.get("surface") or ""),
        forbidden=navigation.forbidden,
        facts=facts,
        meta_action=meta_action,
    )
    # Under honest act_clear + ACT: prefer invoke/commit at the head; demote observe.
    # On forward_picker without a selected destination, prefer type_query / resolve
    # over Forward invoke (live 184742: '1 Selected' ≠ destination chosen).
    surface_now = str(doc.get("surface") or "").strip().lower()
    dest_name = str(getattr(goal, "target_contact", "") or "").strip().lower()
    dest_selected = False
    dest_visible = False
    if surface_now == "forward_picker" and dest_name:
        for o in (doc.get("objects") or [])[:24]:
            if not isinstance(o, dict):
                continue
            label = str(o.get("text") or o.get("label") or "").strip().lower()
            if not label or dest_name not in label and label not in dest_name:
                continue
            dest_visible = True
            if bool(o.get("selected")) or bool(o.get("matches_goal")):
                dest_selected = True
                break
    if (
        surface_now == "forward_picker"
        and not dest_selected
        and str(meta_action or "act").strip().lower() in {"act", "explore", "search"}
    ):
        prefer = (
            ["invoke_affordance", "type_query", "resolve_entity"]
            if dest_visible
            else ["type_query", "resolve_entity", "invoke_affordance"]
        )
        head = [c for c in prefer if c in caps]
        rest = [
            c
            for c in caps
            if c not in head
            and c
            not in {"observe", "request_more_evidence", "commit_irreversible", "reveal_actions"}
        ]
        caps = head + rest + [c for c in caps if c in {"observe", "request_more_evidence"}]
    elif act_clear and str(meta_action or "act").strip().lower() == "act":
        prefer = (
            ["invoke_affordance", "commit_irreversible"]
            if surface_now == "forward_picker"
            else ["invoke_affordance", "commit_irreversible"]
        )
        head = [c for c in prefer if c in caps]
        rest = [c for c in caps if c not in head and c not in {"observe", "request_more_evidence"}]
        caps = head + rest + [c for c in caps if c in {"observe", "request_more_evidence"}]
    # Active EXPLORE intention / exhausted escalate: prefer next method — not Observe.
    intention_next_cap = ""
    try:
        from plugin.agent.executive.intention_frame import (
            active_intention_frame,
            ensure_prereq_child_or_next_method,
            resume_parent_after_child,
        )

        iframe = active_intention_frame(execution_state)
        if iframe is not None and str(iframe.status or "") == "active":
            # Child prereq may already be satisfied by world — resume + re-rank.
            selected = bool(getattr(task_state, "referent_selected", False))
            world_for_intention = {
                **(doc if isinstance(doc, dict) else {}),
                "source_object_selected": selected,
            }
            if iframe.parent_intention_id:
                resume_parent_after_child(
                    execution_state,
                    world=world_for_intention,
                    affordance_stance=stance,
                    grounded_forward=bool(act_clear),
                )
                iframe = active_intention_frame(execution_state)
            if iframe is not None and str(iframe.status or "") == "active":
                nxt = ensure_prereq_child_or_next_method(
                    execution_state,
                    iframe,
                    world=world_for_intention,
                    predicates={"source_object_selected": selected},
                )
                if nxt is not None:
                    top = active_intention_frame(execution_state) or iframe
                    intention_next_cap = str(nxt.capability or "")
                    closure = {
                        **closure,
                        "intention_id": top.intention.id,
                        "intention_next_method": nxt.id,
                        "intention_next_gesture": nxt.gesture,
                        "intention_active": True,
                        "intention_parent_id": top.parent_intention_id,
                    }
    except Exception:
        pass
    if (
        (intention_next_cap or reveal_episode_failed)
        and not act_clear
        and str(meta_action or "act").strip().lower() in {"act", "explore"}
    ):
        prefer_cap = intention_next_cap or str(
            closure.get("reveal_prefer_capability")
            or getattr(execution_state, "reveal_prefer_capability", "")
            or "select_content"
        )
        prefer = (
            ["select_content", "reveal_actions"]
            if prefer_cap == "select_content"
            else ["reveal_actions", "select_content"]
        )
        # Inject preferred verbs even when explore stage omitted them (213125).
        for verb in prefer:
            if verb not in caps:
                caps.insert(0, verb)
        head = [c for c in prefer if c in caps]
        rest = [
            c
            for c in caps
            if c not in head and c not in {"observe", "request_more_evidence"}
        ]
        caps = head + rest + [c for c in caps if c in {"observe", "request_more_evidence"}]
    brief = DecisionBrief(
        goal=goal_dict,
        world={
            "surface": world_surface or str(doc.get("surface") or ""),
            "open_conversation": str(doc.get("open_conversation") or ""),
            "focused_field_role": str(doc.get("focused_field_role") or ""),
            "objects": [
                {
                    **{
                        "id": o.get("id"),
                        "text": str(o.get("text") or ""),
                        "kind": str(o.get("kind") or ""),
                        "matches_goal": bool(o.get("matches_goal")),
                        "point": o.get("point"),
                    },
                    **{
                        k: o.get(k)
                        for k in (
                            "sender",
                            "originator",
                            "role",
                            "field_role",
                            "goal_match",
                            "interpretation",
                        )
                        if o.get(k) not in (None, "", [], {})
                    },
                }
                for o in (doc.get("objects") or [])[:16]
                if isinstance(o, dict)
            ],
            "beliefs": list(doc.get("beliefs") or [])[:8],
        },
        task_state=task_state,
        navigation=navigation,
        capabilities=caps,
        candidates=candidate_labels,
        meta_action=meta_action,
        affordance_frontier=frontier_view,
        perceptor_suggestions=suggestions,
        affordance_qc=dict(affordance_qc or {}),
        perceptor_suggestion=dict(suggestions[0]) if suggestions else {},
        capability_disclosure=disclosure,
        effect_closure=dict(closure),
        affordance_stance=stance,
        act_clear=bool(act_clear),
        reveal_episode_failed=bool(reveal_episode_failed),
    )
    ep = ensure_search_episode_from_brief(execution_state, brief)
    brief.search_episode = ep or search_episode_of(execution_state)
    return brief


def _llm_required_observe(why: str, *, realization: str) -> DecisionOutcome:
    """Decline actuation when text-LLM consultation cannot define a step."""
    return DecisionOutcome(
        ok=True,
        capability="observe",
        target="",
        why=why[:200],
        confidence=0.0,
        realization=realization,
    )


@dataclass
class LlmDecisionChooser:
    """Default realization: one short bounded text call."""

    timeout_s: float = 60.0

    def choose(self, system: str, packet: Dict[str, Any]) -> Dict[str, Any]:
        from plugin.agent.perception_synthesis import _call_llm_hard_timeout
        from plugin.agent.reasoning_consultation import consult_reasoning

        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    "Choose the next capability.\n"
                    + json.dumps(packet, ensure_ascii=False, default=str)[:7000]
                ),
            },
        ]
        try:
            consultation = consult_reasoning(
                "decision",
                messages,
                usecase="decision_choice",
                caller=lambda **kwargs: _call_llm_hard_timeout(self.timeout_s, **kwargs),
                call_kwargs={"timeout": self.timeout_s},
                temperature=0.1,
                max_tokens=256,
            )
        except Exception as exc:
            logger.warning("decision consultation LLM failed: %s", exc)
            return {}
        parsed = getattr(consultation, "parsed", None) or {}
        if isinstance(parsed, dict) and parsed.get("capability"):
            return parsed
        raw = str(getattr(consultation, "raw_response", "") or "")
        try:
            return json.loads(raw)
        except Exception:
            return {}


def _affordance_label(target: str) -> str:
    """Collapse click-script prose into the control label AX/geometry can ground.

    Models often emit ``Click 'Links' tab in sidebar``; actuators need ``Links``.
    """
    import re

    raw = str(target or "").strip()
    if not raw:
        return ""
    quoted = re.match(
        r"^(?:click|tap|press|select|open)\s+['\"]([^'\"]+)['\"]",
        raw,
        flags=re.IGNORECASE,
    )
    if quoted:
        return quoted.group(1).strip()
    prefixed = re.match(
        r"^(?:click|tap|press|select|open)\s+(.+?)(?:\s+tab|\s+button|\s+in\s+|\s+to\s+|$)",
        raw,
        flags=re.IGNORECASE,
    )
    if prefixed:
        return prefixed.group(1).strip(" '\"")
    return raw


def sanitize_decision(payload: Dict[str, Any], brief: DecisionBrief) -> DecisionOutcome:
    """Keep only choices the catalog, navigation and safety gates allow."""
    # Composition root (not role_binding): ensure domain evidence providers exist.
    try:
        from plugin.agent.composition import compose_domain_adapters

        compose_domain_adapters()
    except Exception:
        pass
    if not isinstance(payload, dict):
        return DecisionOutcome(ok=False, why="non-dict decision payload")
    # Motor aliases (right_click) → catalog verbs before the choosable gate.
    capability = _canonical_capability(payload.get("capability") or "")
    if not capability:
        return DecisionOutcome(ok=False, why="no capability named")
    if capability in set(brief.navigation.forbidden):
        return DecisionOutcome(ok=False, why=f"{capability} forbidden on this surface")
    if capability not in set(brief.capabilities):
        return DecisionOutcome(ok=False, why=f"unknown capability {capability!r}")

    target = str(payload.get("target") or payload.get("text") or "").strip()
    if capability in {"invoke_affordance", "commit_irreversible", "reveal_actions"}:
        target = _affordance_label(target)
    if capability == "resolve_entity" and not brief.candidates:
        return DecisionOutcome(ok=False, why="resolve_entity chosen with an empty candidate_set")
    # RoleBinder owns identity. resolve_* may propose a binding; open/act
    # consumes a valid binding (or bind-then-act via RoleBinder — not a second
    # copy of identity rules inline here).
    if capability in {"resolve_entity", "open_entity", "open_contact"} and target:
        from plugin.agent.procedures.forward_message import (
            action_open_semantics,
            looks_like_container_open_target,
            looks_like_content_open_target,
        )
        from plugin.agent.role_binding import (
            BindingRecord,
            RoleBinder,
        )

        cand = {
            "label": target,
            "text": target,
            "title": target,
            "domain": "whatsapp",
        }
        payload_target_id = str(
            payload.get("target_id") or payload.get("id") or ""
        ).strip()
        target_n = target.strip().lower()
        for row in brief.candidates or []:
            if isinstance(row, dict):
                lab = str(row.get("label") or row.get("text") or "")
                lab_n = lab.strip().lower()
                row_id = str(row.get("id") or row.get("target_id") or "").strip()
                # Exact match only — substring (`target in lab`) is not authority.
                if payload_target_id and row_id and payload_target_id == row_id:
                    cand = dict(row)
                    cand.setdefault("label", lab or target)
                    cand.setdefault("domain", "whatsapp")
                    break
                if lab_n and lab_n == target_n:
                    cand = dict(row)
                    cand.setdefault("label", lab)
                    cand.setdefault("domain", "whatsapp")
                    break
            elif str(row or "").strip().lower() == target_n:
                cand["label"] = str(row)
                break
        # Unknown stays unknown — never flatten “not content” → conversation.
        if not str(cand.get("entity_kind") or cand.get("kind") or "").strip():
            if looks_like_content_open_target(candidate=cand, target=target):
                cand["kind"] = "message"
                cand["entity_kind"] = "message"
            elif looks_like_container_open_target(candidate=cand, target=target):
                cand["kind"] = "conversation"
                cand["entity_kind"] = "conversation"
        sem = action_open_semantics(
            capability,
            phase=str(brief.task_state.phase or ""),
            candidate=cand,
            target=target,
        )
        role = str(sem.get("target_role") or "")
        # Navigation via content: click target is not a container identity claim.
        # Allow open; RoleBinder will verify established roles after settle.
        # Must NOT auto-bind source_object from this click.
        if sem.get("is_navigation") and capability in {"open_entity", "open_contact"}:
            closure = (
                brief.effect_closure if isinstance(brief.effect_closure, dict) else {}
            )
            bad_label = str(closure.get("referent_mismatch_label") or "").strip()
            # Only block re-open of a settled *wrong container*, not content labels.
            if (
                bad_label
                and str(closure.get("referent_mismatch_role") or "")
                in {"source_container", "destination"}
                and bad_label.lower() == target.strip().lower()
                and not looks_like_content_open_target(target=bad_label)
            ):
                return DecisionOutcome(
                    ok=False,
                    why=(
                        f"container candidate {target!r} negatively evidenced "
                        f"({closure.get('modes')}) — resume SEARCH"
                    ),
                )
            # Fail closed: typed navigation must carry establishes_roles from sem.
            est = [str(r) for r in (sem.get("establishes_roles") or []) if str(r).strip()]
            if not est:
                return DecisionOutcome(
                    ok=False,
                    why=(
                        "incomplete typed navigation — missing establishes_roles "
                        "(no invented source_container contract)"
                    ),
                )
            # Stamp on payload; final DecisionOutcome copies these fields.
            try:
                payload["target_kind"] = str(sem.get("target_kind") or "")
                payload["establishes_roles"] = est
                payload["action_is_navigation"] = True
            except Exception:
                pass
        elif role:
            closure = (
                brief.effect_closure if isinstance(brief.effect_closure, dict) else {}
            )
            bad_label = str(closure.get("referent_mismatch_label") or "").strip()
            bad_role = str(closure.get("referent_mismatch_role") or "").strip()
            if (
                bad_label
                and bad_role == role
                and bad_label.lower() == target.strip().lower()
            ):
                return DecisionOutcome(
                    ok=False,
                    why=(
                        f"{role} candidate {target!r} negatively evidenced "
                        f"({closure.get('modes')}) — resume SEARCH"
                    ),
                )
            existing: Optional[BindingRecord] = None
            # Prefer an authoritative workspace binding when present.
            try:
                ft = (
                    (brief.world or {}).get("forward_task")
                    if isinstance(brief.world, dict)
                    else None
                )
                if isinstance(ft, dict):
                    slot = {
                        "source_container": "source_conversation",
                        "source_object": "source_object",
                        "destination": "destination",
                    }.get(role, role)
                    raw_b = (ft.get("bindings") or {}).get(slot) or {}
                    if isinstance(raw_b, dict) and raw_b.get("status") in {
                        "provisional",
                        "confirmed",
                    }:
                        existing = BindingRecord(
                            role=role,
                            entity_id=str(raw_b.get("resolved_entity_id") or ""),
                            label=str(
                                raw_b.get("resolved_label")
                                or raw_b.get("label")
                                or ""
                            ),
                            status=str(raw_b.get("status") or ""),
                            confidence=float(raw_b.get("confidence") or 0.0),
                        )
            except Exception:
                existing = None
            # resolve_entity establishes bindings; open consumes them but may
            # bind-then-act through RoleBinder when none exists yet.
            allow_propose = capability == "resolve_entity" or existing is None
            ok, why, proposal = RoleBinder().action_allowed(
                role=role,
                target=target,
                binding=existing,
                candidate=cand if allow_propose else None,
                goal=brief.goal if allow_propose else None,
                allow_propose=allow_propose,
                task_relevance=0.9,
            )
            if not ok:
                return DecisionOutcome(
                    ok=False,
                    why=(
                        f"{role} not actionable for {target!r} ({why})"
                        + (
                            "; continue SEARCH"
                            if why
                            in {
                                "identity_contract_unsatisfied",
                                "no_valid_binding",
                            }
                            else ""
                        )
                    ),
                )
            del proposal  # binder owns proposal; sanitize does not re-score it
    # Meta SEARCH: commit-class verbs are illegal (ACT opens after chosen).
    # Meta EXPLORE: compose/rank forbidden (affordance reveal only).
    from plugin.agent.executive.meta_action import (
        EXPLORE_FORBIDDEN_CAPABILITIES,
        SEARCH_FORBIDDEN_CAPABILITIES,
    )

    meta_now = str(getattr(brief, "meta_action", "") or "").strip().lower()
    if meta_now == "probe":
        meta_now = "explore"
    if meta_now == "search" and capability in SEARCH_FORBIDDEN_CAPABILITIES:
        # Exception (live 145943): grounded source contact row may open under
        # search meta — container open is ACT-commit of the source find.
        if capability in {"open_entity", "open_contact"} and _actuatable_source_contact_ready(
            brief, target=target
        ):
            pass
        else:
            return DecisionOutcome(
                ok=False,
                why="search meta forbids commit verbs; use compose/resolve or wait for act",
            )
    if meta_now == "explore" and capability in EXPLORE_FORBIDDEN_CAPABILITIES:
        return DecisionOutcome(
            ok=False,
            why="explore meta forbids compose/rank; use reveal_actions or observe",
        )
    # Honest act_clear + ACT: commit the inventoried control — do not observe,
    # re-reveal, or dismiss the overlay (live 171627 Observe/Escape thrash).
    act_clear = bool(getattr(brief, "act_clear", False)) or str(
        getattr(brief, "affordance_stance", "") or ""
    ).strip().lower() == "act_clear"
    closure_early = (
        brief.effect_closure if isinstance(brief.effect_closure, dict) else {}
    )
    referent_repair_early = bool(closure_early.get("referent_repair_owed"))
    reveal_failed_early = bool(getattr(brief, "reveal_episode_failed", False)) or bool(
        closure_early.get("reveal_episode_failed")
    )
    if act_clear and meta_now == "act" and not referent_repair_early:
        if capability in {"observe", "request_more_evidence", "reveal_actions"}:
            return DecisionOutcome(
                ok=False,
                why=(
                    "act_clear forbids observe/reveal — invoke/commit the "
                    "actuatable goal control"
                ),
            )
        if capability in {"dismiss_transient", "dismiss"}:
            return DecisionOutcome(
                ok=False,
                why="act_clear forbids dismiss — do not throw away the open overlay",
            )
        world_surf = str(
            (brief.world or {}).get("surface")
            or brief.navigation.surface
            or ""
        ).strip().lower()
        if capability == "select_content" and world_surf in {
            "context_menu",
            "action_menu",
            "selection_mode",
            "forward_picker",
        }:
            return DecisionOutcome(
                ok=False,
                why=(
                    "act_clear on overlay — invoke/commit the goal control, "
                    "do not re-select content"
                ),
            )
    # Active explore intention or exhausted escalate: forbid *unmotivated* Observe.
    # Targeted PERCEIVE with a named purpose remains allowed upstream as meta.
    intention_active_early = bool(closure_early.get("intention_active"))
    if (
        (reveal_failed_early or intention_active_early)
        and meta_now in {"act", "explore"}
        and not act_clear
        and not referent_repair_early
    ):
        if capability in {"observe", "request_more_evidence"}:
            return DecisionOutcome(
                ok=False,
                why=(
                    "active explore intention forbids unmotivated observe — "
                    "continue method frontier (reveal/select) or motivated perceive"
                ),
            )
    # Effect closure: under ACT, refuse re-select/reveal on the same failed
    # content fingerprint — route discovery must escalate under EXPLORE.
    # Referent-repair debt also forbids re-invoke of the same verb fingerprint.
    closure = brief.effect_closure if isinstance(brief.effect_closure, dict) else {}
    forbid_fp = str(closure.get("fingerprint") or "").strip().lower()
    referent_repair = bool(closure.get("referent_repair_owed"))
    if (
        meta_now == "act"
        and capability in {"select_content", "reveal_actions", "open_entity"}
        and forbid_fp
        and (
            bool(closure.get("incomplete_reveal"))
            or bool(closure.get("expected_overlay_missing"))
            or bool(closure.get("geometry_mismatch"))
        )
    ):
        tgt_l = target.lower()
        if tgt_l and (
            tgt_l in forbid_fp
            or any(tok and tok in forbid_fp for tok in tgt_l.split()[:4] if len(tok) >= 4)
        ):
            return DecisionOutcome(
                ok=False,
                why=(
                    "effect unclosed — refuse same-content ACT; "
                    "explore/escalate reveal or perceive"
                ),
            )
    if (
        capability == "invoke_affordance"
        and forbid_fp
        and referent_repair
    ):
        tgt_l = target.lower()
        if tgt_l and (
            tgt_l in forbid_fp
            or any(tok and tok in forbid_fp for tok in tgt_l.split()[:4] if len(tok) >= 3)
        ):
            return DecisionOutcome(
                ok=False,
                why=(
                    "referent repair owed — refuse re-invoke same fingerprint; "
                    "select/cancel matching patient first"
                ),
            )
    # Content ACT before SearchResult.chosen is pretend-commit.
    ep_check = brief.search_episode if isinstance(brief.search_episode, dict) else {}
    if (
        capability in {"select_content", "reveal_actions", "invoke_affordance"}
        and str(brief.goal.get("source_query") or "").strip()
        and not str(ep_check.get("chosen_label") or "").strip()
        and str(ep_check.get("status") or "") not in {"complete", ""}
    ):
        # ranking/querying/retrieving without chosen — block content commit
        if str(ep_check.get("status") or "") in {
            "querying",
            "retrieving",
            "ranking",
        }:
            return DecisionOutcome(
                ok=False,
                why="search episode has no chosen binding — resolve/search before content act",
            )
    # Search ranking incomplete ⇒ try unique/clear-winner completion, else block.
    ep = brief.search_episode if isinstance(brief.search_episode, dict) else None
    ep_status = str((ep or {}).get("status") or "")
    ep_cands = int((ep or {}).get("candidate_count") or 0)
    if (
        capability in {"open_entity", "open_contact"}
        and ep_status == "ranking"
        and ep_cands >= 1
    ):
        from plugin.agent.capabilities.search_episode import search_continue_capability

        cont_cap, cont_tgt, _cont_why = search_continue_capability(
            None, brief, meta_action=meta_now
        )
        ep = brief.search_episode if isinstance(brief.search_episode, dict) else ep
        if (
            cont_cap == "open_entity"
            and cont_tgt
            and str((ep or {}).get("status") or "") == "complete"
            and meta_now != "search"
        ):
            target = cont_tgt
        else:
            return DecisionOutcome(
                ok=False,
                why="search_incomplete_rank_before_commit; use resolve_entity",
            )
    if capability == "commit_irreversible" and brief.task_state.phase not in {
        "choose_destination",
        "act_on_content",
    }:
        return DecisionOutcome(
            ok=False, why="commit_irreversible before the task reached a commit step"
        )
    if capability in {"locate_content", "type_query"} and not target:
        return DecisionOutcome(ok=False, why=f"{capability} needs an argument")
    if capability == "locate_content" and not brief.task_state.source_chat_open:
        return DecisionOutcome(
            ok=False, why="locate_content before the intended source chat is open"
        )
    surface = str((brief.world or {}).get("surface") or "").strip().lower()
    link_q = str((brief.goal or {}).get("source_query") or "").strip()
    search_q = str(brief.task_state.search_query or "").strip()
    had_search_attempt = bool(brief.task_state.attempts)
    # Never search/locate a distractor URL when source_query is known
    # (live 225807: locate_content(YouTube) typed into sidebar Search).
    if (
        capability in {"locate_content", "type_query", "compose_search_query"}
        and link_q
        and target
    ):
        from plugin.agent.source_query_binding import (
            host_contradicts_query,
            query_supported_by_text,
        )

        distractor = host_contradicts_query(target, link_q) or (
            ("http://" in target.lower() or "https://" in target.lower() or "youtu" in target.lower())
            and not query_supported_by_text(target, link_q)
        )
        if capability == "locate_content" and (
            distractor or not query_supported_by_text(target, link_q)
        ):
            target = link_q
        elif distractor:
            return DecisionOutcome(
                ok=False,
                why=(
                    f"{capability} target contradicts source_query={link_q!r}; "
                    "use the goal query, not a distractor URL"
                ),
            )
    # locate_content hunts inside an open chat; the destination picker needs
    # type_query / resolve_entity against its own filter field.
    if capability == "locate_content" and surface == "forward_picker":
        return DecisionOutcome(
            ok=False,
            why="locate_content is not for the destination picker; type/resolve there",
        )
    # Live 184742: do not invoke Forward/Send on Send-to until a destination row
    # is inventory-selected. 'N Selected' is source-message chrome.
    if capability in {"invoke_affordance", "commit_irreversible"} and surface in {
        "forward_picker",
        "destination_picker",
    }:
        dest = str(
            (brief.goal or {}).get("destination")
            or (brief.goal or {}).get("target_contact")
            or ""
        ).strip()
        tgt_l = target.strip().lower()
        dest_l = dest.lower()
        looks_like_dest = bool(dest_l) and (dest_l in tgt_l or tgt_l in dest_l)
        is_forward_verb = (not looks_like_dest) and (
            tgt_l
            in {
                "forward",
                "forward message",
                "forward messages",
                "share",
                "send",
            }
            or tgt_l.startswith("forward")
        )
        if is_forward_verb and dest:
            selected = False
            for o in (brief.world or {}).get("objects") or []:
                if not isinstance(o, dict):
                    continue
                label = str(o.get("text") or o.get("label") or "").strip().lower()
                if not label:
                    continue
                if dest_l in label or label in dest_l:
                    if bool(o.get("selected")) or bool(o.get("matches_goal")):
                        selected = True
                        break
            if not selected:
                return DecisionOutcome(
                    ok=False,
                    why=(
                        "destination not selected on forward_picker — "
                        "type_query/invoke the destination contact first "
                        "(background selection chrome is not destination_selected)"
                    ),
                )
    # Once the source chat is open, sidebar compose+Cmd+F is the drift class
    # that filters the chat list while the conversation stays open.
    if (
        capability == "compose_search_query"
        and brief.task_state.source_chat_open
        and brief.task_state.phase in {"hunt_content", "act_on_content", "choose_destination"}
    ):
        return DecisionOutcome(
            ok=False,
            why="source chat already open; do not compose a sidebar search query",
        )
    if capability == "compose_search_query" and surface in {
        "forward_picker",
        "context_menu",
        "action_menu",
        "selection_mode",
        "dialog",
    }:
        return DecisionOutcome(
            ok=False,
            why=f"compose_search_query forbidden on {surface}; use type_query on the local filter",
        )
    # Link hunt: do not short-circuit to a preview/chat row before search
    # (live 024851/030941). Gate on phase+source_open, not surface label —
    # WhatsApp split view often reports surface=conversation with empty open
    # while the clickable target is still a chat-list preview row.
    # Exception (live 131221): when search/results already show a matches_goal
    # row, AX may have dropped search_query — still allow open_entity.
    # Exception (live 145943): actuatable source *contact* chat_row may open
    # even with unpaid link_query — container open is parent of link hunt.
    if (
        capability == "open_entity"
        and brief.task_state.phase == "reach_source"
        and not brief.task_state.source_chat_open
        and link_q
        and not search_q
        and not had_search_attempt
        and not _search_results_ready_for_open(brief)
        and not _actuatable_source_contact_ready(brief, target=target)
    ):
        return DecisionOutcome(
            ok=False,
            why="link query unresolved; compose_search_query before opening a preview row",
        )
    # Wrong-locus forbid (field | container | patient): locally executable
    # methods whose actuation locus is forbidden for the active desired effect.
    # Absorbs foreign-compose (145943) and composer-focused type/locate (181132).
    try:
        from plugin.agent.capabilities.locus_contract import wrong_locus_forbidden

        field_role = str(
            (brief.world or {}).get("focused_field_role")
            or brief.navigation.focused_field_role
            or ""
        ).strip()
        target_kind = str(
            payload.get("target_kind")
            or payload.get("kind")
            or ""
        ).strip()
        locus_bad, locus_why, locus_req = wrong_locus_forbidden(
            capability,
            brief=brief,
            field_role=field_role,
            label=str(target or ""),
            target_kind=target_kind,
        )
        if locus_bad:
            # Preserve legacy why substrings used by remap / goldens.
            if "foreign_open" in locus_why:
                if _actuatable_source_contact_ready(brief):
                    return DecisionOutcome(
                        ok=False,
                        why=(
                            f"{locus_why}; foreign conversation open with source "
                            "contact row visible; open_entity before compose_search_query"
                        ),
                    )
                return DecisionOutcome(
                    ok=False,
                    why=(
                        f"{locus_why}; foreign conversation open; leave/dismiss "
                        "toward chat list before compose_search_query"
                    ),
                )
            if "composer" in locus_why:
                return DecisionOutcome(
                    ok=False,
                    why=(
                        f"{locus_why}; wrong field locus — locate_content / dismiss "
                        "draft, do not type or context-click composer"
                    ),
                )
            detail = (
                locus_req.kind.value if locus_req is not None else "locus"
            )
            return DecisionOutcome(
                ok=False,
                why=f"{locus_why}; wrong_locus:{detail}",
            )
    except Exception:
        pass
    # Compatibility gate (live 131030): when the forward task is hunting
    # content inside an already-open source chat, prefer locate/reveal over
    # open_entity. Temporary — not the final desired-effect architecture
    # (same object may legitimately need OPEN_CONTENT for other goals).
    if (
        capability == "open_entity"
        and brief.task_state.source_chat_open
        and link_q
        and not bool(brief.task_state.content_located)
        and brief.task_state.phase in {"hunt_content", "act_on_content"}
    ):
        return DecisionOutcome(
            ok=False,
            why=(
                "compat: source chat open while hunting link_query — "
                "locate_content / reveal_actions instead of open_entity "
                "(desired-effect selection pending)"
            ),
        )
    # Message actions need an open conversation; on chat_list/search the same
    # URL often appears as a preview row — revealing there is a dead end.
    if capability in {"reveal_actions", "select_content", "invoke_affordance"} and surface in {
        "chat_list",
        "search",
        "search_results",
    }:
        if not brief.task_state.source_chat_open:
            return DecisionOutcome(
                ok=False,
                why=f"{capability} before the source chat is open; open_entity first",
            )
    # Reveal of a concrete URL/message requires query identity. Opaque labels
    # (e.g. content_item geometry re-ground) are not distractor evidence.
    # Container open + generic URL is not identity (live 214025 YouTube).
    if capability == "reveal_actions" and link_q and surface == "conversation":
        from plugin.agent.capabilities.action_area import label_looks_like_composer
        from plugin.agent.source_query_binding import text_locates_source_query

        target_blob = str(target or "")
        field_role = str(
            (brief.world or {}).get("focused_field_role")
            or brief.navigation.focused_field_role
            or ""
        ).strip().lower()
        # Live 181132: typed query echo in the chat composer is not a message.
        # Right-click yields spellcheck, not Forward.
        if field_role in {
            "composer",
            "message_composer",
            "chat_composer",
            "message_input",
        } or label_looks_like_composer(target_blob):
            return DecisionOutcome(
                ok=False,
                why=(
                    "reveal_actions on message composer — "
                    "locate_content / dismiss draft, do not context-click typed text"
                ),
            )
        target_ok = text_locates_source_query(target_blob, link_q)
        concrete = _looks_like_url_blob(target_blob) or (
            len(target_blob) >= 12 and " " in target_blob and "/" in target_blob
        ) or (
            "http://" in target_blob.lower()
            or "https://" in target_blob.lower()
            or "youtu" in target_blob.lower()
        )
        # Query-token echo without URL/path is almost always composer draft text.
        q_low = link_q.lower()
        t_low = target_blob.lower().strip()
        query_echo = bool(
            q_low
            and t_low
            and (q_low in t_low or t_low in q_low or t_low.startswith(q_low[:8]))
            and not concrete
            and "http" not in t_low
            and "/" not in t_low
        )
        if query_echo:
            return DecisionOutcome(
                ok=False,
                why=(
                    "reveal_actions on source_query echo (likely composer draft) — "
                    "locate_content for the timeline URL first"
                ),
            )
        if concrete and not target_ok:
            return DecisionOutcome(
                ok=False,
                why=(
                    "reveal target fails source_query identity — "
                    "continue SEARCH for matching message"
                ),
            )
        if (
            concrete
            and not bool(brief.task_state.content_located)
            and not target_ok
        ):
            return DecisionOutcome(
                ok=False,
                why=(
                    "source_object unresolved for source_query — "
                    "SEARCH/locate matching content before reveal"
                ),
            )
    if capability == "invoke_affordance" and surface in {
        "chat_list",
        "search",
        "search_results",
    }:
        return DecisionOutcome(
            ok=False,
            why="invoke_affordance on a list/search surface; open the chat first",
        )
    # Left-click on plain text that merely contains the link_query never opens
    # Forward; prefer reveal_actions / locate_content on a URL (live 024851).
    if (
        capability == "invoke_affordance"
        and surface == "conversation"
        and link_q
        and target
        and link_q.lower() in target.lower()
        and not _looks_like_url_blob(target)
        and target.strip().lower()
        not in {"forward", "share", "reply", "copy", "delete", "info", "star"}
    ):
        return DecisionOutcome(
            ok=False,
            why=(
                "invoke_affordance on non-URL text matching link_query; "
                "locate_content or reveal_actions on the link"
            ),
        )
    # Object-scoped affordance (Forward/Share/…) needs a matching selected patient.
    # Grounding the verb is not binding the patient (live 235148).
    # Exception: honest act_clear on an open action overlay — the reveal that
    # opened the menu already scoped the patient; sticky source_object=ambiguous
    # plus forbidding select_content under act_clear deadlocks invoke (live 173658).
    _object_scoped = {
        "forward",
        "share",
        "delete",
        "copy",
        "reply",
        "star",
        "info",
        "pin",
    }
    _overlay_surfaces = {
        "context_menu",
        "action_menu",
        "selection_mode",
    }
    overlay_act_clear = (
        act_clear
        and surface in _overlay_surfaces
        and not referent_repair
    )
    if (
        capability == "invoke_affordance"
        and link_q
        and target.strip().lower() in _object_scoped
        and surface not in {"forward_picker", "destination_picker"}
        and not overlay_act_clear
    ):
        status = str(brief.task_state.referent_binding_status or "").strip().lower()
        if status in {"ambiguous", "unresolved"}:
            return DecisionOutcome(
                ok=False,
                why=(
                    "source object binding ambiguous/unresolved — "
                    "select_content among candidates before invoke"
                ),
            )
        if not bool(brief.task_state.selection_consistent):
            return DecisionOutcome(
                ok=False,
                why=(
                    "selection inconsistent with goal referent — "
                    "cancel/reselect matching patient before invoke"
                ),
            )
        if referent_repair and not bool(brief.task_state.referent_selected):
            return DecisionOutcome(
                ok=False,
                why=(
                    "referent repair owed — select matching patient before re-invoke"
                ),
            )
        if not bool(brief.task_state.referent_selected):
            return DecisionOutcome(
                ok=False,
                why=(
                    "object-scoped invoke without selected referent — "
                    "select_content (or corroborating selection chrome) first"
                ),
            )

    try:
        confidence = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    est_roles = payload.get("establishes_roles") or []
    if not isinstance(est_roles, list):
        est_roles = []
    return DecisionOutcome(
        ok=True,
        capability=capability,
        target=target,
        why=str(payload.get("why") or "")[:200],
        confidence=max(0.0, min(1.0, confidence)) or 0.6,
        realization="llm_decision",
        target_kind=str(payload.get("target_kind") or ""),
        establishes_roles=[str(r) for r in est_roles if str(r).strip()],
        action_is_navigation=bool(payload.get("action_is_navigation")),
        legacy_semantics=bool(payload.get("legacy_semantics")),
    )


def consult_decision(
    brief: DecisionBrief,
    chooser: Optional[DecisionChooser] = None,
    *,
    use_llm: Optional[bool] = None,
) -> DecisionOutcome:
    """Choose the next capability via text-LLM consultation only.

    No heuristic invents a capability. On disable / failure / invalid choice the
    outcome is ``observe`` so the brain can schedule another look.
    """
    want_llm = decision_llm_enabled() if use_llm is None else bool(use_llm)
    if not want_llm and chooser is None:
        return _llm_required_observe(
            "decision LLM required; no chooser provided",
            realization="llm_required",
        )

    author = chooser or LlmDecisionChooser()
    packet = dict(brief.to_packet())
    last_reject = ""
    # One repair turn: feed sanitize rejection back to the model. Still LLM-only
    # — never invent a capability when both attempts miss.
    for attempt in range(2):
        if last_reject:
            packet = dict(brief.to_packet())
            packet["prior_rejection"] = {
                "why": last_reject,
                "attempt": attempt,
            }
        try:
            payload = author.choose(_DECISION_SYSTEM, packet) or {}
        except Exception as exc:
            logger.warning("decision chooser failed: %s", exc)
            return _llm_required_observe(
                f"decision chooser failed: {exc}",
                realization="llm_required_miss",
            )
        decided = sanitize_decision(payload, brief)
        if decided.ok:
            if attempt > 0:
                decided.why = f"{decided.why}; after_rejection_retry".strip("; ")
                decided.realization = "llm_decision_retry"
            return decided
        last_reject = str(decided.why or "invalid capability")
        logger.info("decision choice rejected (attempt %s): %s", attempt + 1, last_reject)
    # Live 131221: repeated reveal/right_click on search is rejected with
    # "open_entity first" — do not collapse that into observe thrash.
    if "open_entity first" in last_reject.lower() and "open_entity" in set(
        brief.capabilities or []
    ):
        target = _open_entity_target_from_brief(brief)
        if target:
            return DecisionOutcome(
                ok=True,
                capability="open_entity",
                target=target,
                why=last_reject,
                confidence=0.7,
                realization="llm_required_open_first",
            )
    # Active explore intention: promote next frontier method after observe reject.
    closure_promote = (
        brief.effect_closure if isinstance(brief.effect_closure, dict) else {}
    )
    if bool(closure_promote.get("intention_active")) and str(
        getattr(brief, "meta_action", "") or ""
    ).strip().lower() in {"act", "explore"}:
        mid = str(closure_promote.get("intention_next_method") or "")
        cap = "select_content" if "select" in mid else "reveal_actions"
        if cap in set(brief.capabilities or []):
            tgt = ""
            for sug in brief.perceptor_suggestions or []:
                if isinstance(sug, dict):
                    tgt = str(
                        sug.get("text") or sug.get("target") or sug.get("label") or ""
                    ).strip()
                    if tgt:
                        break
            if not tgt:
                tgt = str((brief.goal or {}).get("source_query") or "").strip()
            promoted = sanitize_decision(
                {
                    "capability": cap,
                    "target": tgt,
                    "why": "intention frame promote next method",
                    "confidence": 0.72,
                    "gesture": str(closure_promote.get("intention_next_gesture") or ""),
                },
                brief,
            )
            if promoted.ok:
                promoted.realization = "intention_promote_next_method"
                return promoted
    # Honest act_clear: do not collapse rejected observe/reveal into Observe thrash
    # — promote the inventoried invoke/commit suggestion when geometry exists.
    if bool(getattr(brief, "act_clear", False)) and str(
        getattr(brief, "meta_action", "") or ""
    ).strip().lower() == "act":
        for sug in brief.perceptor_suggestions or []:
            if not isinstance(sug, dict):
                continue
            fam = _canonical_capability(sug.get("family") or sug.get("capability"))
            if fam not in {"invoke_affordance", "commit_irreversible"}:
                continue
            tgt = str(sug.get("text") or sug.get("target") or sug.get("label") or "").strip()
            has_geo = bool(
                sug.get("target_point") or sug.get("point") or sug.get("bounds")
            )
            if not has_geo and not tgt:
                continue
            payload = {
                "capability": fam,
                "target": tgt,
                "why": "act_clear promote after observe/reveal rejected",
                "confidence": float(sug.get("confidence") or 0.75),
            }
            if isinstance(sug.get("target_point"), (list, tuple)):
                payload["target_point"] = list(sug.get("target_point") or [])
            elif isinstance(sug.get("point"), (list, tuple)):
                payload["target_point"] = list(sug.get("point") or [])
            if sug.get("coordinate_space"):
                payload["coordinate_space"] = sug.get("coordinate_space")
            promoted = sanitize_decision(payload, brief)
            if promoted.ok:
                promoted.realization = "act_clear_promote_invoke"
                return promoted
        # Prefer the real reject reason — live 173658 mislabeled referent-gate
        # misses as geometry_incomplete and hid the deadlock.
        reject_l = str(last_reject or "").lower()
        if any(
            tok in reject_l
            for tok in (
                "binding ambiguous",
                "selected referent",
                "referent repair",
                "selection inconsistent",
            )
        ):
            realization = "act_clear_referent_gate"
        elif "geometry" in reject_l or "point" in reject_l or "bounds" in reject_l:
            realization = "act_clear_geometry_incomplete"
        else:
            realization = "act_clear_commit_blocked"
        return DecisionOutcome(
            ok=False,
            capability="",
            target="",
            why=(
                f"act_clear but no actuatable invoke after rejection: {last_reject}"
            ),
            confidence=0.0,
            realization=realization,
        )
    return _llm_required_observe(
        f"llm choice rejected: {last_reject}",
        realization="llm_required_miss",
    )


# Capabilities that need a screen target. Derived from CapabilitySpec.requires_geometry
# (GroundedUiTarget family) plus motor aliases like type_query.
def _pointer_capabilities() -> frozenset:
    from plugin.agent.capabilities.catalog import geometry_required_capabilities

    return geometry_required_capabilities()


# Families that share a filter-input rectangle even when the brain renames the
# capability (compose_search_query vs type_query vs open_search).
# Source of truth: action_area contracts (app-agnostic).
def _search_field_families() -> frozenset:
    from plugin.agent.capabilities.action_area import filter_field_families

    return filter_field_families()


# Back-compat alias used across this module.
_SEARCH_FIELD_FAMILIES = frozenset(
    {"compose_search_query", "type_query", "locate_content", "open_search"}
)

# Motor aliases the perceptor may emit; brain/catalog verb is reveal_actions.
# Geometry handoff and sanitize must treat these as the same family (live 024851:
# right_click suggestion + reveal_actions choice dropped CTA geometry).
_CAPABILITY_ALIASES = {
    "right_click": "reveal_actions",
    "rightclick": "reveal_actions",
    "context_click": "reveal_actions",
    "contextclick": "reveal_actions",
}
_REVEAL_FAMILY_ALIASES = frozenset({"reveal_actions", *_CAPABILITY_ALIASES.keys()})


def _norm_family(raw: Any) -> str:
    return str(raw or "").strip().lower().replace("-", "_")


def _canonical_capability(raw: Any) -> str:
    fam = _norm_family(raw)
    return _CAPABILITY_ALIASES.get(fam, fam)


def _open_entity_target_from_brief(brief: "DecisionBrief") -> str:
    """Resolve open target — SEARCH owns hypothesis choice; ACT executes it.

    Contract: consume ``chosen_label`` / ``explore_label`` only. Do not invoke
    hypothesis ranking. No SEARCH choice ⇒ empty string (return to SEARCH),
    except a goal-grounded contact address when there is no content query.
    """
    goal = brief.goal if isinstance(brief.goal, dict) else {}
    contact = str(goal.get("source_conversation") or "").strip()
    ep = brief.search_episode if isinstance(brief.search_episode, dict) else {}
    chosen = str(
        ep.get("chosen_label") or ep.get("explore_label") or ""
    ).strip()
    if chosen:
        return chosen
    link_q = str(goal.get("source_query") or goal.get("link_query") or "").strip()
    # Grounded source address from the decision itself — not inventory re-rank.
    if not link_q:
        return contact
    return ""


def _search_results_ready_for_open(brief: "DecisionBrief") -> bool:
    """True when search episode is complete (or unique fit) and may commit.

    Legacy name kept for call sites that gated link-hunt open. Raw
    ``matches_goal`` alone is not enough — ranking must have finished.
    """
    ep = brief.search_episode if isinstance(brief.search_episode, dict) else None
    if ep and str(ep.get("status") or "") == "complete" and ep.get("chosen_label"):
        return True
    doc = brief.world if isinstance(brief.world, dict) else {}
    surface = str(doc.get("surface") or "").strip().lower()
    if surface not in {"search", "search_results", "chat_list"}:
        return False
    if brief.task_state.source_chat_open:
        return False
    if brief.task_state.phase != "reach_source":
        return False
    # Sync episode from brief world when snapshot missing (tests / early path).
    from plugin.agent.capabilities.search_episode import ensure_search_episode_from_brief

    ep = ensure_search_episode_from_brief(None, brief)
    brief.search_episode = ep or brief.search_episode
    return bool(
        ep
        and str(ep.get("status") or "") == "complete"
        and ep.get("chosen_label")
    )


def _actuatable_source_contact_ready(
    brief: "DecisionBrief",
    *,
    target: str = "",
) -> bool:
    """True when an actuatable source-contact chat_row is grounded for open.

    Optional ``target`` must match that row (or the source name) when provided.
    """
    if brief.task_state.source_chat_open:
        return False
    if brief.task_state.phase not in {"reach_source", "open_source", "preclear", ""}:
        return False
    source = str(
        (brief.goal or {}).get("source_conversation")
        or (brief.goal or {}).get("contact")
        or ""
    ).strip()
    if not source:
        return False
    from plugin.agent.capabilities.resolve_entity import (
        actuatable_source_contact_row,
        open_matches_referent,
        row_matches_source_contact,
    )

    doc = brief.world if isinstance(brief.world, dict) else {}
    row = actuatable_source_contact_row(doc, source)
    if not isinstance(row, dict):
        return False
    if not target:
        return True
    tgt = str(target or "").strip()
    label = str(row.get("text") or row.get("label") or "").strip()
    if not tgt:
        return True
    if row_matches_source_contact(tgt, source) or open_matches_referent(tgt, source):
        return True
    if label and (
        tgt.lower() == label.lower()
        or tgt.lower() in label.lower()
        or label.lower() in tgt.lower()
    ):
        return True
    return False


def _looks_like_url_blob(text: Any) -> bool:
    blob = str(text or "").strip().lower()
    if not blob:
        return False
    return (
        "http://" in blob
        or "https://" in blob
        or ".goo." in blob
        or ".com/" in blob
        or ".com?" in blob
        or blob.endswith(".com")
    )


def _valid_xy(raw: Any) -> Optional[List[float]]:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    try:
        return [float(raw[0]), float(raw[1])]
    except (TypeError, ValueError):
        return None


def _token_set(text: Any) -> set:
    return {
        t
        for t in re.split(r"\W+", str(text or "").lower())
        if len(t) >= 4
    }


def _point_in_bounds(point: Any, bounds: Any, *, pad: float = 24.0) -> bool:
    pt = _valid_xy(point)
    if pt is None or not isinstance(bounds, (list, tuple)) or len(bounds) < 4:
        return False
    try:
        x, y, w, h = (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
    except (TypeError, ValueError):
        return False
    return (x - pad) <= pt[0] <= (x + w + pad) and (y - pad) <= pt[1] <= (y + h + pad)


def _reconcile_perceptor_with_inventory(
    world_geo: Dict[str, Any],
    perc_geo: Dict[str, Any],
    document: Dict[str, Any],
) -> Dict[str, Any]:
    """Prefer inventory geometry when perceptor CTA disagrees with the named object.

    Live failure: prose described a message near x≈1356 while next_action kept
    the chat-list row point [305,240]. Inventory object for the brain target is
    the single source of truth; CTA may only refine when it lands on that object.
    """
    out = dict(perc_geo)
    world_pt = _valid_xy(world_geo.get("target_point"))
    perc_pt = _valid_xy(perc_geo.get("target_point"))
    world_bounds = world_geo.get("bounds")
    if world_pt is None and world_bounds is None:
        out["geometry_source"] = "perceptor"
        return out

    # Resolve named inventory object for a stronger check.
    objects = [o for o in (document.get("objects") or []) if isinstance(o, dict)]
    named = None
    tid = str(world_geo.get("target_id") or perc_geo.get("target_id") or "").strip()
    label = str(world_geo.get("target_label") or "").strip().lower()
    if tid:
        for obj in objects:
            if str(obj.get("id") or "").strip() == tid:
                named = obj
                break
    if named is None and label:
        # Prefer overlay/toolbar controls (menu_item/button) over content rows
        # that merely share a verb substring — avoids list-band Forward ghosts.
        overlay_kinds = {
            "menu_item",
            "menuitem",
            "button",
            "toolbar_button",
            "action",
            "control",
        }
        overlay_hits = []
        content_hits = []
        for obj in objects:
            blob = " ".join(
                str(obj.get(k) or "") for k in ("text", "label", "id")
            ).lower()
            if not (label and label in blob):
                continue
            kind = str(obj.get("kind") or "").strip().lower()
            if kind in overlay_kinds:
                overlay_hits.append(obj)
            else:
                content_hits.append(obj)
        named = (overlay_hits[0] if overlay_hits else None) or (
            content_hits[0] if content_hits else None
        )
    if named is not None:
        n_pt = _valid_xy(named.get("point"))
        n_bounds = named.get("bounds")
        if n_pt is not None:
            world_pt = n_pt
        if isinstance(n_bounds, (list, tuple)) and len(n_bounds) >= 4:
            world_bounds = n_bounds
        if tid or named.get("id"):
            out["target_id"] = tid or named.get("id")
        n_label = str(named.get("text") or named.get("label") or "").strip()
        if n_label:
            out["target_label"] = n_label
        space = str(named.get("coordinate_space") or "").strip().lower()
        if space in {"image", "screen"}:
            out["coordinate_space"] = space

    agrees = False
    if perc_pt is not None and world_bounds is not None and _point_in_bounds(perc_pt, world_bounds):
        agrees = True
    elif perc_pt is not None and world_pt is not None:
        agrees = abs(perc_pt[0] - world_pt[0]) <= 40.0 and abs(perc_pt[1] - world_pt[1]) <= 40.0

    # Multi-pane layouts: a CTA that is hundreds of px away in x is a different
    # surface (list vs content), not a refinement — never accept it.
    cross_pane = False
    if perc_pt is not None and world_pt is not None:
        cross_pane = abs(perc_pt[0] - world_pt[0]) >= 200.0
    if cross_pane:
        agrees = False

    if agrees and perc_pt is not None and not cross_pane:
        out["target_point"] = perc_pt
        out["geometry_source"] = "perceptor"
        return out

    # Conflict or missing CTA agreement → inventory wins.
    if world_pt is not None:
        out["target_point"] = world_pt
    if isinstance(world_bounds, (list, tuple)) and len(world_bounds) >= 4:
        try:
            out["bounds"] = [float(x) for x in world_bounds[:4]]
        except (TypeError, ValueError):
            pass
    if str(world_geo.get("coordinate_space") or "").strip().lower() in {"image", "screen"}:
        out["coordinate_space"] = world_geo["coordinate_space"]
    out["geometry_source"] = "inventory"
    if cross_pane:
        out["geometry_rejected_cross_pane"] = True
    return out


def _perceptor_geometry_for_choice(
    perceptor_action: Optional[Dict[str, Any]],
    capability: str,
    brain_target: str,
) -> Dict[str, Any]:
    """Carry CTA geometry the perceptor already bound for this capability.

    Contract: screenshot+AX fusion lives in the perceptor; the brain chooses
    *which* capability; the actor lands the perceptor's point. Re-grounding from
    a stale accepted document is what opened the wrong chat row live.

    Search-field families are interchangeable for geometry: compose_search_query
    may reuse a perceptor type_query / open_search CTA on the same field.

    Motor aliases (right_click) share geometry with reveal_actions.
    """
    if not isinstance(perceptor_action, dict) or not perceptor_action:
        return {}
    perc_fam = _norm_family(
        perceptor_action.get("family") or perceptor_action.get("capability")
    )
    brain_fam = _norm_family(capability)
    perc_canon = _canonical_capability(perc_fam)
    brain_canon = _canonical_capability(brain_fam)
    same_family = perc_canon == brain_canon or (
        perc_fam in _REVEAL_FAMILY_ALIASES and brain_fam in _REVEAL_FAMILY_ALIASES
    )
    shared_search_field = (
        perc_fam in _SEARCH_FIELD_FAMILIES and brain_fam in _SEARCH_FIELD_FAMILIES
    )
    if not same_family and not shared_search_field:
        return {}
    perc_blob = " ".join(
        str(perceptor_action.get(k) or "")
        for k in ("target_label", "label", "text", "target")
    )
    brain_tokens = _token_set(brain_target)
    perc_tokens = _token_set(perc_blob)
    # Same family but clearly different referent (e.g. Tanmay vs Pallavi) →
    # do not carry the wrong CTA; fall through to world grounding.
    # Search-field swaps skip this: the field label ("Search") ≠ the query arg.
    # Reveal aliases often carry prose targets ("right of the bubble") without
    # overlapping brain tokens — still carry geometry when family matches.
    if (
        same_family
        and not shared_search_field
        and brain_tokens
        and perc_tokens
        and not (brain_tokens & perc_tokens)
        and perc_canon not in {"reveal_actions"}
    ):
        return {}
    out: Dict[str, Any] = {}
    pt = _valid_xy(perceptor_action.get("target_point") or perceptor_action.get("point"))
    if pt is not None:
        out["target_point"] = pt
    tid = perceptor_action.get("target_id")
    if tid is not None and str(tid).strip() != "":
        out["target_id"] = tid
    label = str(
        perceptor_action.get("target_label") or perceptor_action.get("label") or ""
    ).strip()
    if label:
        out["target_label"] = label
    bounds = perceptor_action.get("bounds")
    if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
        try:
            out["bounds"] = [float(x) for x in bounds[:4]]
        except (TypeError, ValueError):
            pass
    space = str(perceptor_action.get("coordinate_space") or "").strip().lower()
    if space in {"image", "screen"}:
        out["coordinate_space"] = space
    return out


def _geometry_grounding_document(
    execution_state: Any,
    proposal: Any,
) -> Dict[str, Any]:
    """Object inventory used to bind a brain choice to a screen point.

    Prefer the perceptor's ``world_model.objects`` from this look — the accepted
    ``unified_world_document`` can still hold pre-search row geometry after the
    list has been filtered.
    """
    document = getattr(execution_state, "unified_world_document", None)
    if not isinstance(document, dict):
        document = {}
    wm = getattr(proposal, "world_model", None) if proposal is not None else None
    if not isinstance(wm, dict):
        wm = {}
    if wm.get("objects"):
        merged = dict(document)
        merged["objects"] = [o for o in (wm.get("objects") or []) if isinstance(o, dict)]
        if wm.get("surface"):
            merged["surface"] = wm.get("surface")
        if "open_conversation" in wm:
            merged["open_conversation"] = wm.get("open_conversation")
        if wm.get("layers"):
            merged["layers"] = wm.get("layers")
        return merged
    if document:
        return document
    return dict(wm)


def _point_from_bounds(bounds: Any) -> Optional[List[float]]:
    try:
        x, y, w, h = (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
    except (TypeError, ValueError, IndexError):
        return None
    if w <= 0 or h <= 0:
        return None
    return [x + w / 2.0, y + h / 2.0]


def _filter_site_from_frontier(frontier: Any) -> Dict[str, Any]:
    """AX-built frontier actuators for exclusive filter_input families.

    Live 123746: VLM objects were only chat rows while AX ``Q Search`` already
    sat on ``last_affordance_frontier`` with a coordinate_click actuator. The
    chooser brief strips actuators; grounding must read the full stored packet.
    """
    if not isinstance(frontier, dict):
        return {}
    from plugin.agent.capabilities.action_area import (
        filter_field_families,
        label_looks_like_filter,
    )

    families = filter_field_families()
    for bucket in ("observed_actions", "latent_actions"):
        for aff in frontier.get(bucket) or []:
            if not isinstance(aff, dict):
                continue
            if str(aff.get("family") or "") not in families:
                continue
            label = str(
                aff.get("target_label") or aff.get("label") or aff.get("text") or ""
            ).strip()
            if label and not label_looks_like_filter(label) and "search" not in label.lower():
                continue
            point = None
            for act in aff.get("actuators") or []:
                if not isinstance(act, dict):
                    continue
                raw = act.get("point") or act.get("target_point")
                if isinstance(raw, (list, tuple)) and len(raw) >= 2:
                    try:
                        point = [float(raw[0]), float(raw[1])]
                    except (TypeError, ValueError):
                        point = None
                    if point is not None:
                        break
            raw_pt = aff.get("target_point") or aff.get("point")
            if point is None and isinstance(raw_pt, (list, tuple)) and len(raw_pt) >= 2:
                try:
                    point = [float(raw_pt[0]), float(raw_pt[1])]
                except (TypeError, ValueError):
                    point = None
            bounds = aff.get("bounds")
            if (
                point is None
                and isinstance(bounds, (list, tuple))
                and len(bounds) >= 4
            ):
                point = _point_from_bounds(bounds)
            if point is None and not (
                isinstance(bounds, (list, tuple)) and len(bounds) >= 4
            ):
                continue
            site: Dict[str, Any] = {
                "target_label": "Search",
                "coordinate_space": "screen",
                "geometry_source": "ax_frontier",
                "kind": "search_field",
            }
            if point is not None:
                site["target_point"] = point
            if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
                try:
                    site["bounds"] = [float(x) for x in bounds[:4]]
                except (TypeError, ValueError):
                    pass
            tid = aff.get("target_id")
            if tid is not None:
                site["target_id"] = tid
            return site
    return {}


def _filter_site_from_world_entities(execution_state: Any) -> Dict[str, Any]:
    """Bind Search chrome from WorldModel entities when VLM omitted the field."""
    if execution_state is None:
        return {}
    world = getattr(execution_state, "world_model", None)
    entities = getattr(world, "entities", None) if world is not None else None
    if not isinstance(entities, dict) or not entities:
        return {}
    from plugin.agent.capabilities.action_area import label_looks_like_filter

    for entity in entities.values():
        label = str(getattr(entity, "label", "") or "").strip()
        etype = str(getattr(entity, "entity_type", "") or getattr(entity, "type", "") or "")
        attrs = getattr(entity, "attributes", None) or {}
        blob = f"{label} {etype} {attrs.get('role', '')} {attrs.get('description', '')}".lower()
        if not label_looks_like_filter(label) and "search" not in blob:
            continue
        if any(tok in blob for tok in ("composer", "message", "type a message")):
            continue
        bounds = getattr(entity, "bounds", None)
        point = _point_from_bounds(bounds)
        if point is None:
            continue
        site: Dict[str, Any] = {
            "target_label": "Search",
            "target_point": point,
            "coordinate_space": "screen",
            "geometry_source": "ax_entity",
            "kind": "search_field",
        }
        try:
            site["bounds"] = [float(x) for x in bounds[:4]]
        except (TypeError, ValueError, IndexError):
            pass
        eid = getattr(entity, "id", None)
        if eid is not None:
            site["target_id"] = eid
        return site
    return {}


def _filter_site_from_ocr(execution_state: Any, features: Any = None) -> Dict[str, Any]:
    """Last-resort Search geometry from OCR lines (screen/image bounds)."""
    from plugin.agent.capabilities.action_area import label_looks_like_filter

    lines: List[Any] = []
    world = getattr(execution_state, "world_model", None) if execution_state else None
    if world is not None:
        lines.extend(
            ln for ln in (getattr(world, "last_ocr_lines", None) or []) if isinstance(ln, dict)
        )
    extras = None
    if features is not None and isinstance(getattr(features, "extras", None), dict):
        extras = features.extras
    if isinstance(extras, dict):
        for key in ("ocr_lines", "ocr"):
            raw = extras.get(key)
            if isinstance(raw, list):
                lines.extend(ln for ln in raw if isinstance(ln, dict))
            elif isinstance(raw, dict) and isinstance(raw.get("lines"), list):
                lines.extend(ln for ln in raw["lines"] if isinstance(ln, dict))
    for line in lines:
        text = str(line.get("text") or line.get("label") or "").strip()
        if not label_looks_like_filter(text) and not _is_search_chrome_label(text):
            continue
        bounds = line.get("bounds") or line.get("bbox")
        point = _point_from_bounds(bounds)
        if point is None:
            continue
        site: Dict[str, Any] = {
            "target_label": "Search",
            "target_point": point,
            "coordinate_space": "screen",
            "geometry_source": "ocr_search",
            "kind": "search_field",
        }
        try:
            site["bounds"] = [float(x) for x in bounds[:4]]
        except (TypeError, ValueError, IndexError):
            pass
        return site
    return {}


def _is_search_chrome_label(text: Any) -> bool:
    low = str(text or "").strip().lower()
    if not low:
        return False
    if re.match(r"^(q\s+|•\s+|·\s+)?search\|?$", low):
        return True
    return "search" in low and len(low) < 48 and "result" not in low


def _resolve_filter_geometry_site(
    *,
    execution_state: Any = None,
    features: Any = None,
) -> Dict[str, Any]:
    # Perception stashes a Search site on the look that built the frontier —
    # preferred over re-deriving (live 123746: RuntimeState.world_model is not
    # on execution_state, so entity/OCR fallbacks were empty).
    if execution_state is not None:
        stashed = getattr(execution_state, "last_filter_geometry", None)
        if isinstance(stashed, dict) and (
            stashed.get("target_point") is not None or stashed.get("bounds")
        ):
            return dict(stashed)
    extras = getattr(features, "extras", None) if features is not None else None
    if isinstance(extras, dict):
        stashed = extras.get("filter_geometry")
        if isinstance(stashed, dict) and (
            stashed.get("target_point") is not None or stashed.get("bounds")
        ):
            return dict(stashed)
    site = _filter_site_from_frontier(
        getattr(execution_state, "last_affordance_frontier", None)
        if execution_state is not None
        else None
    )
    if site:
        return site
    site = _filter_site_from_world_entities(execution_state)
    if site:
        return site
    return _filter_site_from_ocr(execution_state, features)


def _document_has_filter_geometry(document: Dict[str, Any]) -> bool:
    from plugin.agent.capabilities.action_area import (
        ActionArea,
        contract_for,
        object_matches_area,
    )

    contract = contract_for("compose_search_query")
    if contract is None or contract.area != ActionArea.FILTER_INPUT:
        return False
    for obj in document.get("objects") or []:
        if not isinstance(obj, dict) or not object_matches_area(obj, contract):
            continue
        if obj.get("point") or obj.get("target_point") or obj.get("bounds"):
            return True
    return False


def _augment_document_with_filter_site(
    document: Dict[str, Any],
    *,
    execution_state: Any = None,
    features: Any = None,
) -> Dict[str, Any]:
    """Inject a grounded search_field object when VLM omitted filter chrome.

    Preserves exclusive filter_input binding: chat/contact rows stay in the
    inventory but cannot win prefer_filter matching (live 095344).
    """
    doc = dict(document or {})
    if _document_has_filter_geometry(doc):
        return doc
    site = _resolve_filter_geometry_site(
        execution_state=execution_state, features=features
    )
    if not site.get("target_point") and not site.get("bounds"):
        return doc
    objects = [o for o in (doc.get("objects") or []) if isinstance(o, dict)]
    injected = {
        "id": site.get("target_id") if site.get("target_id") is not None else "ax_search_field",
        "kind": "search_field",
        "text": str(site.get("target_label") or "Search"),
        "label": str(site.get("target_label") or "Search"),
        "coordinate_space": str(site.get("coordinate_space") or "screen"),
        "geometry_source": str(site.get("geometry_source") or "ax_frontier"),
    }
    if site.get("target_point") is not None:
        injected["point"] = list(site["target_point"][:2])
    if site.get("bounds") is not None:
        injected["bounds"] = list(site["bounds"][:4])
    doc["objects"] = [injected] + objects
    return doc


def _ground_choice_on_world(
    document: Dict[str, Any],
    capability: str,
    target: str,
    *,
    goal_referents: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Resolve a brain choice onto perceived objects (ids / points / labels).

    When ``goal_referents`` is non-empty and capability is a content probe
    (reveal/select on conversation), an explicit model target that does not
    overlap those referents is not admissible — rebind to the unique
    referent-matching content object instead (154356 class).
    """
    grounded: Dict[str, Any] = {}
    if capability not in _pointer_capabilities():
        return grounded
    from plugin.agent.capabilities.action_area import (
        ActionArea,
        contract_for,
        label_looks_like_filter,
        object_matches_area,
    )
    from plugin.agent.capabilities.revert_effects import (
        content_target_fits_referents,
        pick_unique_referent_content,
    )

    area_contract = contract_for(capability)
    referents = [str(t).strip() for t in (goal_referents or []) if str(t).strip()]
    # Exclusive filter_input: bind only the filter control — never a
    # matches_goal chat/contact row (live 095344 typed a query into chat).
    prefer_filter = bool(
        area_contract
        and area_contract.area == ActionArea.FILTER_INPUT
        and area_contract.exclusive
    )
    objects = [o for o in (document.get("objects") or []) if isinstance(o, dict)]
    if not objects:
        if prefer_filter:
            grounded["target_label"] = (
                (area_contract.canonical_label if area_contract else "") or "Search"
            )
        elif target:
            grounded["target_label"] = target
        return grounded

    target_norm = str(target or "").strip().lower()
    surface = str(document.get("surface") or "").strip().lower()
    # Destination picking must not latch onto a prior-phase content object that
    # still carries matches_goal (live: Zarooratwala message stole Tanmay's click).
    picker_kinds = {"contact_row", "contact", "entity", "chat_row", "row"}
    prefer_picker = capability in {"resolve_entity", "select_content"} and surface in {
        "forward_picker",
        "search",
        "search_results",
    }
    prefer_content = capability in {"reveal_actions", "select_content"} and surface == "conversation"

    def _blob(obj: Dict[str, Any]) -> str:
        return " ".join(
            str(obj.get(k) or "") for k in ("text", "label", "id", "kind")
        ).lower()

    def _kind_ok(obj: Dict[str, Any]) -> bool:
        if prefer_filter and area_contract is not None:
            return object_matches_area(obj, area_contract)
        kind = str(obj.get("kind") or "").strip().lower()
        if prefer_content and area_contract is not None:
            return object_matches_area(obj, area_contract)
        if prefer_picker:
            return kind in picker_kinds
        return True

    chosen: Optional[Dict[str, Any]] = None
    # Exclusive action areas: bind in-area only. Never fall through to a
    # name/matches_goal latch outside the area (high error-cost writes).
    if prefer_filter:
        for obj in objects:
            if _kind_ok(obj):
                chosen = obj
                break
        if chosen is None:
            grounded["target_label"] = (
                (area_contract.canonical_label if area_contract else "") or "Search"
            )
            return grounded
    # Explicit target wins over matches_goal — unless content-probe referents
    # veto a non-overlapping entity (model named the wrong link/message).
    if chosen is None and target_norm:
        ordered = (
            [o for o in objects if _kind_ok(o)] + [o for o in objects if not _kind_ok(o)]
            if (prefer_picker or prefer_content)
            else list(objects)
        )
        for obj in ordered:
            if target_norm not in _blob(obj):
                continue
            if prefer_content and referents and not content_target_fits_referents(
                target_label=str(obj.get("text") or obj.get("label") or ""),
                object_blob=_blob(obj),
                goal_referents=referents,
            ):
                continue
            chosen = obj
            break
    if chosen is None and prefer_content and referents:
        alt = pick_unique_referent_content(document, referents)
        if alt is not None and _kind_ok(alt):
            chosen = alt
    if chosen is None:
        for obj in objects:
            if not obj.get("matches_goal"):
                continue
            if (prefer_picker or prefer_content) and not _kind_ok(obj):
                continue
            if prefer_content and referents and not content_target_fits_referents(
                target_label=str(obj.get("text") or obj.get("label") or ""),
                object_blob=_blob(obj),
                goal_referents=referents,
            ):
                continue
            chosen = obj
            break
    if chosen is None and target_norm:
        for obj in objects:
            if target_norm not in _blob(obj):
                continue
            if prefer_content and referents and not content_target_fits_referents(
                target_label=str(obj.get("text") or obj.get("label") or ""),
                object_blob=_blob(obj),
                goal_referents=referents,
            ):
                continue
            chosen = obj
            break
    if chosen is None and len(objects) == 1:
        if not (
            prefer_content
            and referents
            and not content_target_fits_referents(
                target_label=str(objects[0].get("text") or objects[0].get("label") or ""),
                object_blob=_blob(objects[0]),
                goal_referents=referents,
            )
        ):
            chosen = objects[0]
    if chosen is None:
        if target and not prefer_filter:
            grounded["target_label"] = target
        elif prefer_filter:
            grounded["target_label"] = (
                (area_contract.canonical_label if area_contract else "") or "Search"
            )
        return grounded

    if chosen.get("id") is not None:
        grounded["target_id"] = chosen.get("id")
    # Filter area: control name (Search), never the query/contact token.
    if prefer_filter:
        canon = (area_contract.canonical_label if area_contract else "") or "Search"
        label = str(chosen.get("text") or chosen.get("label") or canon).strip()
        if not label_looks_like_filter(label):
            label = canon
    else:
        label = str(chosen.get("text") or chosen.get("label") or target or "").strip()
    if label:
        grounded["target_label"] = label
    point = chosen.get("point")
    if isinstance(point, (list, tuple)) and len(point) >= 2:
        grounded["target_point"] = [point[0], point[1]]
    space = str(chosen.get("coordinate_space") or "").strip().lower()
    if space in {"image", "screen"}:
        grounded["coordinate_space"] = space
    bounds = chosen.get("bounds")
    if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
        try:
            grounded["bounds"] = [float(x) for x in bounds[:4]]
        except (TypeError, ValueError):
            pass
    geo_src = str(chosen.get("geometry_source") or "").strip()
    if geo_src:
        grounded["geometry_source"] = geo_src
    return grounded


def _entity_resolution_type_query_outcome(
    brief: "DecisionBrief",
    execution_state: Any,
    *,
    prior: Optional["DecisionOutcome"] = None,
) -> Optional["DecisionOutcome"]:
    """When SEARCH meta owns an unresolved searchable entity, realize type_query.

    Observe / Forward invoke are inadmissible realizations of that gap.
    """
    meta_now = str(getattr(brief, "meta_action", "") or "").strip().lower()
    if meta_now != "search":
        return None
    try:
        from plugin.agent.executive.search_applicability import (
            evaluate_entity_resolution_search,
            type_query_for_gap,
        )
    except Exception:
        return None
    eval_result = evaluate_entity_resolution_search(execution_state)
    if not eval_result.applicable or eval_result.gap is None:
        return None
    query = type_query_for_gap(eval_result.gap)
    if not query:
        return None
    allowed = set(brief.capabilities or [])
    if "type_query" not in allowed and "locate_content" not in allowed:
        return None
    cap = "type_query" if "type_query" in allowed else "locate_content"
    prior_cap = str(getattr(prior, "capability", "") or "").strip().lower()
    # Already a legal SEARCH-stage realization — leave it.
    if prior_cap in {"type_query", "locate_content", "compose_search_query", "resolve_entity"}:
        if prior_cap in {"type_query", "locate_content"} and str(
            getattr(prior, "target", "") or ""
        ).strip():
            return None
    return DecisionOutcome(
        ok=True,
        capability=cap,
        target=query,
        why=(
            f"entity unresolved in {eval_result.gap.current_scope}; "
            f"SEARCH → {cap}({query!r})"
        ),
        confidence=max(0.85, float(getattr(prior, "confidence", 0.0) or 0.0)),
        realization=(
            f"{getattr(prior, 'realization', None) or 'decision'}"
            "+entity_resolution_search_type_query"
        ),
    )


def _patient_content_established(brief: "DecisionBrief") -> bool:
    """True when source-query patient is already on-screen / soft-located.

    Interaction-affordance failures must not erase this fact and restart
    retrieval (live 113806: reveal miss → locate_content found=False).
    """
    task = brief.task_state
    if bool(getattr(task, "content_located", False)):
        return True
    link_q = str(
        (brief.goal or {}).get("source_query")
        or (brief.goal or {}).get("link_query")
        or ""
    ).strip()
    if not link_q:
        return False
    doc = brief.world if isinstance(brief.world, dict) else {}
    try:
        from plugin.agent.source_query_binding import document_locates_source_query

        if document_locates_source_query(doc, link_q):
            return True
    except Exception:
        pass
    # Soft extras / phase already acknowledging patient presence.
    if str(getattr(task, "phase", "") or "").strip().lower() == "act_on_content":
        return True
    return False


def _content_search_locate_outcome(
    brief: "DecisionBrief",
    *,
    prior: Optional["DecisionOutcome"] = None,
    execution_state: Any = None,
) -> Optional["DecisionOutcome"]:
    """SEARCH with source open + unpaid source_query → locate_content, not Observe.

    Live 225807: binding correctly refused YouTube, meta kept SEARCH, but the
    planner realized Observe forever because content SEARCH had no seal.

    Live 185549: AX-blind locate left EffectStatus UNKNOWN; identical locate must
    not reseal while verification is pending / method still unresolved.

    Live 113806: do **not** reseal when the patient is already established —
    reveal/select failures repair affordances, they do not restart retrieval.
    """
    meta_now = str(getattr(brief, "meta_action", "") or "").strip().lower()
    if meta_now != "search":
        return None
    task = brief.task_state
    if not bool(getattr(task, "source_chat_open", False)):
        return None
    if bool(getattr(task, "content_located", False)):
        return None
    if _patient_content_established(brief):
        return None
    link_q = str(
        (brief.goal or {}).get("source_query")
        or (brief.goal or {}).get("link_query")
        or ""
    ).strip()
    if not link_q:
        return None
    surface = str((brief.world or {}).get("surface") or "").strip().lower()
    if surface and surface not in {"conversation", "search", "search_results"}:
        return None
    allowed = set(brief.capabilities or [])
    if "locate_content" not in allowed:
        return None
    prior_cap = str(getattr(prior, "capability", "") or "").strip().lower()
    if prior_cap == "locate_content" and str(getattr(prior, "target", "") or "").strip():
        return None
    # Affordance repair: never overwrite reveal/select with locate while patient known.
    if prior_cap in {"reveal_actions", "select_content"}:
        return None
    if prior_cap in {"type_query", "compose_search_query", "resolve_entity"}:
        # Prefer locate inside an open chat over sidebar compose.
        if prior_cap != "type_query" or surface == "conversation":
            pass
        else:
            return None
    # EffectStatus UNKNOWN / pending verify: forbid same-method SEARCH replay.
    if execution_state is not None:
        try:
            from plugin.agent.capabilities.locate_content import (
                prefer_next_locate_realization,
                same_locate_unresolved,
            )

            if same_locate_unresolved(execution_state, query=link_q):
                return None
            next_r = prefer_next_locate_realization(execution_state)
            if next_r:
                return DecisionOutcome(
                    ok=True,
                    capability="locate_content",
                    target=link_q,
                    why=(
                        f"source open; prior locate route uninformative — "
                        f"MethodFrontier next={next_r}({link_q!r})"
                    ),
                    confidence=max(
                        0.85, float(getattr(prior, "confidence", 0.0) or 0.0)
                    ),
                    realization=(
                        f"{getattr(prior, 'realization', None) or 'decision'}"
                        f"+content_search_locate_{next_r}"
                    ),
                )
        except Exception:
            pass
    return DecisionOutcome(
        ok=True,
        capability="locate_content",
        target=link_q,
        why=f"source open; SEARCH content unpaid — locate_content({link_q!r})",
        confidence=max(0.85, float(getattr(prior, "confidence", 0.0) or 0.0)),
        realization=(
            f"{getattr(prior, 'realization', None) or 'decision'}"
            "+content_search_locate"
        ),
    )


def apply_decision_consultation(
    proposal: Any,
    goal: Any,
    features: Any = None,
    execution_state: Any = None,
    *,
    chooser: Optional[DecisionChooser] = None,
) -> Dict[str, Any]:
    """Brain chooses the next capability over the accepted world + frontier.

    Perception owns *what is on screen* and which choices are available; this
    decides *which choice to take*. Always fills ``proposal.next_action`` when
    a capability is chosen (including ``observe``). Returns a trace dict.
    """
    if proposal is None:
        return {}
    # Save perceptor CTA before wipe — brain chooses capability; geometry was
    # already bound from screenshot+AX in this look.
    # Fast-choice / stage1 leave executable next_action empty and put geometry
    # on suggested_actions; fall back so GroundedUiTarget can still bind.
    perceptor_action = (
        dict(proposal.next_action)
        if isinstance(getattr(proposal, "next_action", None), dict)
        else {}
    )
    suggestions = [
        dict(s)
        for s in (getattr(proposal, "suggested_actions", None) or getattr(proposal, "next_actions", None) or [])
        if isinstance(s, dict)
    ]
    if not (
        perceptor_action.get("target_point")
        or perceptor_action.get("point")
        or perceptor_action.get("bounds")
    ):
        for sug in suggestions:
            if sug.get("target_point") or sug.get("point") or sug.get("bounds"):
                perceptor_action = dict(sug)
                break
        if not perceptor_action and suggestions:
            perceptor_action = dict(suggestions[0])
    document = _geometry_grounding_document(execution_state, proposal)
    if not document:
        document = dict(getattr(proposal, "world_model", None) or {})
    # Live 123746: AX/OCR Search geometry is present even when VLM objects are
    # only chat rows — inject a search_field site before exclusive filter bind.
    document = _augment_document_with_filter_site(
        document, execution_state=execution_state, features=features
    )

    # Drop any legacy model-emitted action so it cannot leak into execution.
    # Geometry is restored below from perceptor_action / world grounding.
    proposal.next_action = {}

    brief = build_decision_brief(
        goal,
        world_document=document,
        features=features,
        execution_state=execution_state,
        perceptor_suggestions=suggestions,
        affordance_qc=dict(getattr(proposal, "affordance_qc", None) or {}),
    )
    # Proposal stance is authoritative for this look (geometry-honest).
    prop_stance = str(getattr(proposal, "affordance_stance", "") or "").strip().lower()
    if prop_stance:
        brief.affordance_stance = prop_stance
        brief.act_clear = prop_stance == "act_clear"
    if decision_consultation_enabled():
        outcome = consult_decision(brief, chooser=chooser)
    else:
        outcome = _llm_required_observe(
            "decision consultation disabled",
            realization="consultation_disabled",
        )

    from plugin.agent.brain import (
        apply_surprise_explanation,
        barren_frontier_reperceive,
        request_reperceive,
    )

    # REFLECT → explain → brain: steer only on the look that produced the
    # explanation (perception_mode/meta still reflect), then clear so it does
    # not sticky-override later turns.
    _mode = str(getattr(execution_state, "perception_mode", "") or "")
    _meta = str(getattr(execution_state, "last_meta_action", "") or "")
    if getattr(execution_state, "last_surprise_explanation", None) and (
        _mode == "reflect" or _meta == "reflect"
    ):
        outcome = apply_surprise_explanation(
            outcome, execution_state, features=features
        )
        try:
            execution_state.perception_mode = ""
        except Exception:
            pass

    barren, barren_why = barren_frontier_reperceive(brief)
    # Same-node gap closers (reveal_actions / select_content) are how the agent
    # finds missing latents on this UI node. Only force reperceive when the
    # chooser tries a transition/commit that assumes those latents exist.
    _gap_closers = {"observe", "reveal_actions", "select_content", ""}
    # Entity-resolution SEARCH must not be rewritten to Observe by barren
    # frontier logic — the blocking gap is location-in-scope, not missing
    # Forward chrome (live 203259).
    _forced_search = _entity_resolution_type_query_outcome(
        brief, execution_state, prior=outcome
    )
    if _forced_search is not None:
        outcome = _forced_search
    elif barren and outcome.capability not in _gap_closers:
        outcome = DecisionOutcome(
            ok=True,
            capability="observe",
            target="",
            why=barren_why,
            confidence=0.35,
            realization=f"{outcome.realization}+barren_frontier_override",
        )

    # Post-override gate: reflect_repair / barren can rewrite the capability
    # after consult_decision's sanitize. Re-check so compose-first / locate
    # gates still win (live 031818: reflect_repair forced open_entity).
    if outcome.ok and outcome.capability and outcome.capability not in {"observe", ""}:
        gated = sanitize_decision(
            {
                "capability": outcome.capability,
                "target": outcome.target,
                "why": outcome.why,
                "confidence": outcome.confidence,
            },
            brief,
        )
        if not gated.ok:
            allowed = set(brief.capabilities or [])
            why = str(gated.why or "")
            prior_r = str(outcome.realization or "decision")
            if (
                "open_entity before compose" in why.lower()
                or (
                    "foreign conversation open with source contact" in why.lower()
                    and "open_entity" in allowed
                )
            ):
                src_tgt = _open_entity_target_from_brief(brief)
                from plugin.agent.capabilities.resolve_entity import (
                    actuatable_source_contact_row,
                )

                row = actuatable_source_contact_row(
                    brief.world if isinstance(brief.world, dict) else {},
                    str(
                        (brief.goal or {}).get("source_conversation")
                        or (brief.goal or {}).get("contact")
                        or ""
                    ),
                )
                if isinstance(row, dict):
                    src_tgt = str(
                        row.get("text") or row.get("label") or src_tgt or ""
                    ).strip() or src_tgt
                outcome = DecisionOutcome(
                    ok=True,
                    capability="open_entity",
                    target=src_tgt,
                    why=why,
                    confidence=max(0.7, float(outcome.confidence or 0.0)),
                    realization=f"{prior_r}+sanitize_source_contact_open",
                )
            elif (
                "leave/dismiss" in why.lower()
                or "wrong_locus:container" in why.lower()
                or (
                    "foreign conversation open" in why.lower()
                    and "compose_search_query" in why.lower()
                )
            ) and "dismiss_transient" in allowed:
                outcome = DecisionOutcome(
                    ok=True,
                    capability="dismiss_transient",
                    target="",
                    why=why,
                    confidence=max(0.65, float(outcome.confidence or 0.0)),
                    realization=f"{prior_r}+sanitize_leave_wrong_conversation",
                )
                if execution_state is not None:
                    try:
                        from plugin.agent.capabilities.locus_contract import (
                            stamp_wrong_locus_debt,
                        )

                        stamp_wrong_locus_debt(
                            execution_state,
                            kind="container",
                            forbidden="foreign_container",
                            required="open_matches_referent(source)",
                            why=why,
                        )
                    except Exception:
                        pass
            elif "compose_search_query" in why and "compose_search_query" in allowed:
                outcome = DecisionOutcome(
                    ok=True,
                    capability="compose_search_query",
                    target="",
                    why=why,
                    confidence=max(0.55, float(outcome.confidence or 0.0)),
                    realization=f"{prior_r}+sanitize_compose_first",
                )
            elif (
                "locate_content" in why
                or "wrong_locus:field" in why.lower()
                or "composer draft" in why.lower()
                or "message composer" in why.lower()
                or "source_query echo" in why.lower()
            ) and "locate_content" in allowed:
                link_q = str((brief.goal or {}).get("source_query") or "").strip()
                outcome = DecisionOutcome(
                    ok=True,
                    capability="locate_content",
                    target=link_q or str(outcome.target or ""),
                    why=why,
                    confidence=max(0.55, float(outcome.confidence or 0.0)),
                    realization=f"{prior_r}+sanitize_locate",
                )
                if execution_state is not None and "wrong_locus:field" in why.lower():
                    try:
                        from plugin.agent.capabilities.locus_contract import (
                            stamp_wrong_locus_debt,
                        )

                        stamp_wrong_locus_debt(
                            execution_state,
                            kind="field",
                            forbidden="composer",
                            required="filter_field",
                            why=why,
                        )
                    except Exception:
                        pass
            elif "search_incomplete" in why.lower() and "resolve_entity" in allowed:
                from plugin.agent.capabilities.search_episode import (
                    search_continue_capability,
                )

                cont_cap, cont_tgt, cont_why = search_continue_capability(
                    execution_state,
                    brief,
                    meta_action=str(brief.meta_action or ""),
                )
                if (
                    cont_cap == "open_entity"
                    and cont_tgt
                    and str(brief.meta_action or "") != "search"
                ):
                    outcome = DecisionOutcome(
                        ok=True,
                        capability="open_entity",
                        target=cont_tgt,
                        why=cont_why or why,
                        confidence=max(0.7, float(outcome.confidence or 0.0)),
                        realization=f"{prior_r}+sanitize_search_commit_chosen",
                    )
                else:
                    ep = brief.search_episode if isinstance(brief.search_episode, dict) else {}
                    outcome = DecisionOutcome(
                        ok=True,
                        capability="resolve_entity",
                        target=str(
                            cont_tgt
                            or ep.get("chosen_label")
                            or ep.get("referent")
                            or ep.get("query")
                            or outcome.target
                            or ""
                        ),
                        why=cont_why or why,
                        confidence=max(0.7, float(outcome.confidence or 0.0)),
                        realization=f"{prior_r}+sanitize_resolve_before_commit",
                    )
            elif (
                "open_entity first" in why.lower()
                and "open_entity" in allowed
            ):
                # Prefer resolve when search still ranking; else open chosen/unique.
                from plugin.agent.capabilities.search_episode import (
                    search_continue_capability,
                )

                cont_cap, cont_tgt, cont_why = search_continue_capability(
                    execution_state,
                    brief,
                    meta_action=str(brief.meta_action or ""),
                )
                if cont_cap == "resolve_entity" or str(brief.meta_action or "") == "search":
                    outcome = DecisionOutcome(
                        ok=True,
                        capability=cont_cap or "resolve_entity",
                        target=cont_tgt
                        or _open_entity_target_from_brief(brief)
                        or str(outcome.target or ""),
                        why=cont_why or why,
                        confidence=max(0.7, float(outcome.confidence or 0.0)),
                        realization=f"{prior_r}+sanitize_resolve_first",
                    )
                else:
                    target = (
                        cont_tgt
                        or _open_entity_target_from_brief(brief)
                        or str(outcome.target or "")
                    )
                    outcome = DecisionOutcome(
                        ok=True,
                        capability="open_entity",
                        target=target,
                        why=why,
                        confidence=max(0.7, float(outcome.confidence or 0.0)),
                        realization=f"{prior_r}+sanitize_open_first",
                    )
            else:
                outcome = DecisionOutcome(
                    ok=True,
                    capability="observe",
                    target="",
                    why=why,
                    confidence=0.4,
                    realization=f"{prior_r}+sanitize_block",
                )

    # Mid-search: observe/reveal thrash → continue search (resolve) or commit
    # chosen after unique fit. Never open on raw matches_goal while ranking.
    if outcome.ok and outcome.capability in {
        "observe",
        "",
        "reveal_actions",
        "open_entity",
    }:
        from plugin.agent.capabilities.search_episode import search_continue_capability

        cont_cap, cont_tgt, cont_why = search_continue_capability(
            execution_state,
            brief,
            meta_action=str(brief.meta_action or ""),
        )
        ep = brief.search_episode if isinstance(brief.search_episode, dict) else {}
        ep_status = str(ep.get("status") or "")
        if cont_cap == "resolve_entity" and (
            outcome.capability in {"observe", "", "reveal_actions", "open_entity"}
            or ep_status in {"querying", "retrieving", "ranking"}
        ):
            outcome = DecisionOutcome(
                ok=True,
                capability="resolve_entity",
                target=cont_tgt,
                why=cont_why or "search incomplete; continue ranking before commit",
                confidence=max(0.7, float(outcome.confidence or 0.0)),
                realization=f"{outcome.realization or 'decision'}+search_continue_resolve",
            )
        elif (
            cont_cap == "open_entity"
            and cont_tgt
            and str(brief.meta_action or "") != "search"
            and outcome.capability in {"observe", "", "reveal_actions", "open_entity"}
        ):
            # ACT path: rewrite premature open onto the ranked choice.
            prior_tgt = " ".join(str(outcome.target or "").strip().lower().split())
            want_tgt = " ".join(str(cont_tgt or "").strip().lower().split())
            if outcome.capability != "open_entity" or prior_tgt != want_tgt:
                outcome = DecisionOutcome(
                    ok=True,
                    capability="open_entity",
                    target=cont_tgt,
                    why=cont_why or "search complete; open chosen candidate",
                    confidence=max(0.7, float(outcome.confidence or 0.0)),
                    realization=f"{outcome.realization or 'decision'}+search_commit_chosen",
                )

    # Final SEARCH→type_query seal: sanitize/barren/search_continue must not
    # leave Observe or Forward as the realization of an entity-resolution gap.
    _seal = _entity_resolution_type_query_outcome(
        brief, execution_state, prior=outcome
    )
    if _seal is not None and (
        not outcome.ok
        or str(outcome.capability or "").strip().lower()
        in {"", "observe", "request_more_evidence", "invoke_affordance", "commit_irreversible"}
    ):
        outcome = _seal

    # SEARCH with open source chat + unpaid link query → locate_content
    # (live 225807 Observe thrash after correct YouTube reject).
    # Live 113806: do not override reveal/select when the patient is already
    # established — that is affordance repair, not retrieval restart.
    _content_seal = _content_search_locate_outcome(
        brief, prior=outcome, execution_state=execution_state
    )
    _cap_now = str(outcome.capability or "").strip().lower()
    _patient_known = _patient_content_established(brief)
    _affordance_caps = {"reveal_actions", "select_content"}
    if _content_seal is not None and (
        not outcome.ok
        or (
            _cap_now
            in {
                "",
                "observe",
                "request_more_evidence",
                "invoke_affordance",
                "open_entity",
                "commit_irreversible",
            }
            or (_cap_now in _affordance_caps and not _patient_known)
        )
    ):
        outcome = _content_seal

    next_action: Dict[str, Any] = {
        "family": outcome.capability,
        "text": outcome.target if outcome.capability != "compose_search_query" else "",
        "confidence": outcome.confidence
        or float(getattr(proposal, "confidence", 0.0) or 0.0),
        "target_kind": str(getattr(outcome, "target_kind", "") or ""),
        "establishes_roles": list(getattr(outcome, "establishes_roles", None) or []),
        "action_is_navigation": bool(getattr(outcome, "action_is_navigation", False)),
        "legacy_semantics": bool(getattr(outcome, "legacy_semantics", False)),
    }
    if outcome.ok and outcome.capability:
        pointer_caps = _pointer_capabilities()
        if outcome.capability in pointer_caps:
            content_refs: List[str] = []
            if outcome.capability in {"reveal_actions", "select_content"}:
                content_refs = [
                    str(t).strip()
                    for t in (
                        [(brief.goal or {}).get("source_query") or ""]
                        + list((brief.goal or {}).get("goal_referents") or [])
                    )
                    if str(t).strip()
                ]
                if execution_state is not None:
                    try:
                        from plugin.agent.capabilities.revert_effects import (
                            goal_referents_from_context,
                        )

                        for t in goal_referents_from_context(
                            execution_state=execution_state,
                            extras={"link_query": (brief.goal or {}).get("source_query")},
                        ):
                            if t and t not in content_refs:
                                content_refs.append(t)
                    except Exception:
                        pass
            next_action.update(
                _ground_choice_on_world(
                    document,
                    outcome.capability,
                    outcome.target,
                    goal_referents=content_refs or None,
                )
            )
            # Content probe with referents but no admissible bind → locate/observe.
            if (
                outcome.capability in {"reveal_actions", "select_content"}
                and content_refs
                and next_action.get("target_point") is None
                and not next_action.get("bounds")
                and not next_action.get("target_id")
            ):
                from plugin.agent.capabilities.revert_effects import (
                    content_target_fits_referents,
                    pick_unique_referent_content,
                )

                alt = pick_unique_referent_content(document, content_refs)
                if alt is not None:
                    next_action["target_id"] = alt.get("id")
                    next_action["target_label"] = str(
                        alt.get("text") or alt.get("label") or ""
                    )
                    pt = alt.get("point")
                    if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                        next_action["target_point"] = [float(pt[0]), float(pt[1])]
                        next_action["coordinate_space"] = "screen"
                    outcome = DecisionOutcome(
                        ok=True,
                        capability=outcome.capability,
                        target=str(next_action.get("target_label") or outcome.target),
                        why=(
                            "rebound content probe to unique goal-referent object "
                            f"(rejected non-overlapping target {outcome.target!r})"
                        ),
                        confidence=max(0.65, float(outcome.confidence or 0.0)),
                        realization=f"{outcome.realization}+referent_rebind",
                    )
                    next_action["family"] = outcome.capability
                elif not content_target_fits_referents(
                    target_label=str(outcome.target or ""),
                    goal_referents=content_refs,
                ):
                    allowed = set(brief.capabilities or [])
                    if "locate_content" in allowed:
                        outcome = DecisionOutcome(
                            ok=True,
                            capability="locate_content",
                            target=content_refs[0],
                            why=(
                                "content probe target does not overlap goal referents; "
                                "locate_content before reveal/select"
                            ),
                            confidence=0.6,
                            realization=f"{outcome.realization}+referent_mismatch_locate",
                        )
                        next_action = {
                            "family": "locate_content",
                            "text": content_refs[0],
                            "target_label": content_refs[0],
                            "confidence": 0.6,
                        }
                    else:
                        outcome = DecisionOutcome(
                            ok=True,
                            capability="observe",
                            target="",
                            why=(
                                "content probe target does not overlap goal referents; "
                                "re-perceive for goal-matching content"
                            ),
                            confidence=0.4,
                            realization=f"{outcome.realization}+referent_mismatch_observe",
                        )
                        next_action = {
                            "family": "observe",
                            "text": "",
                            "confidence": 0.4,
                        }
            if not next_action.get("target_label") and outcome.target:
                # Query-arg caps: label is the field, not the authored string.
                if outcome.capability not in _SEARCH_FIELD_FAMILIES:
                    next_action["target_label"] = outcome.target
            # Handoff: perceptor CTA may refine id/label, but must not disagree
            # with the inventory object the brain named (prose≠point failure).
            world_geo = {
                k: next_action[k]
                for k in ("target_id", "target_label", "target_point", "bounds", "coordinate_space")
                if k in next_action
            }
            perc_geo = _perceptor_geometry_for_choice(
                perceptor_action, outcome.capability, outcome.target
            )
            if perc_geo.get("target_point") is not None or perc_geo.get("bounds"):
                reconciled = _reconcile_perceptor_with_inventory(
                    world_geo, perc_geo, document
                )
                next_action.update(reconciled)
            # Reflect recovery: prefer corrected geometry over the failed latch.
            corrected = getattr(execution_state, "reflect_corrected_point", None)
            if (
                isinstance(corrected, (list, tuple))
                and len(corrected) >= 2
                and (
                    str(getattr(outcome, "realization", "") or "")
                    == "reflect_corrected_geometry"
                    or str(getattr(outcome, "realization", "") or "").startswith(
                        "reflect_repair:"
                    )
                )
            ):
                next_action["target_point"] = [float(corrected[0]), float(corrected[1])]
                next_action["reflect_reground"] = True
                next_action["geometry_source"] = "reflect_corrected"
                # Prefer foreground click after background-AX surprises.
                constraint = getattr(execution_state, "reflect_motor_constraint", None)
                if constraint:
                    next_action["motor_constraint"] = str(constraint)
                try:
                    execution_state.reflect_corrected_point = None
                except Exception:
                    pass
            # Stamp coordinate space when still unknown: world/OCR bounds → screen.
            if next_action.get("target_point") is not None or next_action.get("bounds"):
                if str(next_action.get("coordinate_space") or "").strip().lower() not in {
                    "image",
                    "screen",
                }:
                    next_action["coordinate_space"] = (
                        "screen" if next_action.get("bounds") else "image"
                    )
            # Block identical failed motors (reveal @ same XY after no menu).
            # Live 153213: escalate reveal gesture (hover / select_content) instead
            # of observe-thrash when only context_click is latched.
            try:
                from plugin.agent.brain import motor_fingerprint
                from plugin.agent.capabilities.reveal_actions import (
                    current_reveal_probe_mode,
                    escalate_failed_reveal,
                    reveal_motor_fingerprint,
                )
                from plugin.agent.executive.effect_implications import (
                    avoid_key_blocks_method,
                    method_context_from_state,
                )
                from plugin.agent.executive.intention_frame import (
                    active_intention_frame,
                )

                avoid = set(
                    getattr(execution_state, "avoid_motor_keys", None) or []
                )
                tgt = str(next_action.get("target_label") or outcome.target or "")
                pt = next_action.get("target_point")
                key = motor_fingerprint(outcome.capability, tgt, pt)
                iframe = active_intention_frame(execution_state)
                intention_id = str(
                    getattr(getattr(iframe, "intention", None), "id", "") or ""
                )
                doc_world = document if isinstance(document, dict) else {}
                ctx = method_context_from_state(
                    execution_state,
                    world={
                        "surface": str(
                            doc_world.get("surface")
                            or getattr(execution_state, "last_surface", "")
                            or ""
                        ),
                        "open_conversation": str(
                            doc_world.get("open_conversation") or ""
                        ),
                        "semantic_container": str(
                            doc_world.get("semantic_container") or ""
                        ),
                    },
                )
                world_sig = ctx.signature() if ctx is not None else ""
                method_blocked = avoid_key_blocks_method(
                    list(avoid),
                    family=str(outcome.capability or ""),
                    target=tgt,
                    intention_id=intention_id,
                    world_signature=world_sig,
                    point_key=key,
                )
                reveal_caps = {
                    "reveal_actions",
                    "revealactions",
                    "right_click",
                    "context_click",
                }
                if outcome.capability in reveal_caps:
                    mode = current_reveal_probe_mode(execution_state)
                    gkey = reveal_motor_fingerprint(mode, tgt, pt)
                    prefer = str(
                        getattr(execution_state, "reveal_prefer_capability", "") or ""
                    ).strip().lower()
                    blocked = (gkey in avoid) or method_blocked
                    if blocked or prefer == "select_content":
                        if prefer != "select_content":
                            escalate_failed_reveal(
                                execution_state,
                                target=tgt,
                                point=pt,
                                last_gesture=mode,
                            )
                            prefer = str(
                                getattr(
                                    execution_state, "reveal_prefer_capability", ""
                                )
                                or ""
                            ).strip().lower()
                            mode = current_reveal_probe_mode(execution_state)
                        if prefer == "select_content":
                            outcome = DecisionOutcome(
                                ok=True,
                                capability="select_content",
                                target=tgt,
                                why=(
                                    "failed_reveal escalation: select message then "
                                    "toolbar Forward (context_click/hover exhausted)"
                                ),
                                confidence=0.7,
                                realization=f"{outcome.realization}+reveal_escalate_select",
                            )
                            next_action = {
                                "family": "select_content",
                                "target_label": tgt,
                                "target_point": pt,
                                "bounds": next_action.get("bounds"),
                                "coordinate_space": next_action.get(
                                    "coordinate_space"
                                )
                                or "screen",
                                "confidence": 0.7,
                            }
                        elif mode == "hover":
                            outcome = DecisionOutcome(
                                ok=True,
                                capability="reveal_actions",
                                target=tgt,
                                why="failed_reveal escalation: retry reveal via hover",
                                confidence=0.65,
                                realization=f"{outcome.realization}+reveal_escalate_hover",
                            )
                            next_action = {
                                **next_action,
                                "family": "reveal_actions",
                                "gesture": "hover",
                                "reveal_probe_mode": "hover",
                                "confidence": 0.65,
                            }
                        else:
                            outcome = DecisionOutcome(
                                ok=True,
                                capability="observe",
                                target="",
                                why=(
                                    f"blocked repeat of failed motor {gkey or key}; "
                                    "re-perceive for fresh geometry"
                                ),
                                confidence=0.3,
                                realization=f"{outcome.realization}+avoid_failed_motor",
                            )
                            next_action = {
                                "family": "observe",
                                "text": "",
                                "confidence": 0.3,
                            }
                    else:
                        # Stamp current probe gesture so actor does not hardcode
                        # context_click after a prior incomplete reveal.
                        next_action = {
                            **next_action,
                            "gesture": mode if mode in {"context_click", "hover"} else "context_click",
                            "reveal_probe_mode": mode,
                        }
                elif method_blocked and outcome.capability not in {"observe", ""}:
                    why = (
                        f"blocked repeat of failed motor {key}; "
                        "method ineffective under current intention/world"
                        if key not in avoid
                        else (
                            f"blocked repeat of failed motor {key}; "
                            "re-perceive for fresh geometry"
                        )
                    )
                    outcome = DecisionOutcome(
                        ok=True,
                        capability="observe",
                        target="",
                        why=why,
                        confidence=0.3,
                        realization=f"{outcome.realization}+avoid_failed_motor",
                    )
                    next_action = {
                        "family": "observe",
                        "text": "",
                        "confidence": 0.3,
                    }
                # Hierarchical gate: known-ungrounded commitment → grounding
                # recovery, not silent patient substitute.
                try:
                    from plugin.agent.executive.affordance_commitment import (
                        active_commitment,
                        arm_grounding_recovery,
                        derive_availability,
                        derive_executable,
                        forbids_wrong_locus,
                        next_grounding_strategy,
                        AVAIL_LATENT,
                        STRATEGY_RE_REVEAL,
                    )

                    c = active_commitment(execution_state)
                    if (
                        c is not None
                        and not derive_executable(execution_state, c)
                        and forbids_wrong_locus(
                            execution_state,
                            family=str(outcome.capability or ""),
                            semantic_target=tgt,
                            brief=brief,
                        )
                    ):
                        avail = derive_availability(execution_state, c)
                        strat = next_grounding_strategy(execution_state, c)
                        arm_grounding_recovery(
                            execution_state, c, reason="decision_gate_ungrounded"
                        )
                        if (
                            avail == AVAIL_LATENT
                            or strat == STRATEGY_RE_REVEAL
                        ) and str(outcome.capability or "") in {
                            "reveal_actions",
                            "select_content",
                        }:
                            # Explicit re-reveal for this commitment — allow.
                            pass
                        else:
                            outcome = DecisionOutcome(
                                ok=True,
                                capability="observe",
                                target=str(c.label or ""),
                                why=(
                                    f"grounding recovery for committed "
                                    f"{c.semantic_method_id} (availability={avail}, "
                                    f"strategy={strat}); do not substitute patient"
                                ),
                                confidence=0.55,
                                realization=(
                                    f"{outcome.realization}+commitment_grounding_recovery"
                                ),
                            )
                            next_action = {
                                "family": "observe",
                                "text": str(c.label or ""),
                                "confidence": 0.55,
                                "grounding_recovery": True,
                                "commitment_id": c.commitment_id,
                                "strategy": strat,
                            }
                except Exception:
                    pass
            except Exception:
                pass
            # Open-source repair: after repeated failed open_entity clicks, escalate
            # to compose_search_query only when retrieval is still owed. Content-
            # address misses prefer observe so explore/reveal can take over.
            try:
                repair = None
                extras = getattr(features, "extras", None) if features is not None else None
                if isinstance(extras, dict) and isinstance(extras.get("open_repair"), dict):
                    repair = extras.get("open_repair")
                if repair is None:
                    repair = getattr(execution_state, "open_repair", None)
                prefer_repair = (
                    str(repair.get("prefer") or "") if isinstance(repair, dict) else ""
                )
                if (
                    isinstance(repair, dict)
                    and prefer_repair == "compose_search_query"
                    and outcome.capability in {"open_entity", "open_contact"}
                    and not brief.task_state.source_chat_open
                    and brief.task_state.phase == "reach_source"
                ):
                    contact = str(
                        (brief.goal or {}).get("source_conversation")
                        or getattr(goal, "contact", "")
                        or ""
                    ).strip()
                    outcome = DecisionOutcome(
                        ok=True,
                        capability="compose_search_query",
                        target="",
                        why=(
                            f"open_repair after {repair.get('attempts')} failed opens; "
                            f"search for {contact or 'source'} then open the row"
                        ),
                        confidence=0.75,
                        realization=f"{outcome.realization}+open_repair_search",
                    )
                    next_action = {
                        "family": "compose_search_query",
                        "text": contact,
                        "target_label": "",
                        "confidence": 0.75,
                        "coordinate_space": "screen",
                    }
                    next_action.update(
                        _ground_choice_on_world(
                            document, "compose_search_query", contact
                        )
                    )
                elif (
                    isinstance(repair, dict)
                    and prefer_repair == "method_exhausted_reperceive"
                    and outcome.capability in {"open_entity", "open_contact"}
                ):
                    outcome = DecisionOutcome(
                        ok=True,
                        capability="observe",
                        target="",
                        why=(
                            f"open_repair: open_entity ineffective on "
                            f"{str(repair.get('last_target') or 'target')[:60]}; "
                            "re-perceive for alternate effect/method"
                        ),
                        confidence=0.35,
                        realization=f"{outcome.realization}+open_repair_method_exhausted",
                    )
                    next_action = {
                        "family": "observe",
                        "text": "",
                        "confidence": 0.35,
                    }
            except Exception:
                pass
            # Last chance: exclusive filter caps may still lack inventory geometry
            # after perceptor/world merge — bind AX frontier / entity / OCR Search.
            if (
                outcome.capability in _SEARCH_FIELD_FAMILIES
                and next_action.get("target_point") is None
                and not next_action.get("bounds")
            ):
                site = _resolve_filter_geometry_site(
                    execution_state=execution_state, features=features
                )
                if site.get("target_point") is not None or site.get("bounds"):
                    next_action.update(
                        {
                            k: site[k]
                            for k in (
                                "target_id",
                                "target_label",
                                "target_point",
                                "bounds",
                                "coordinate_space",
                                "geometry_source",
                            )
                            if k in site
                        }
                    )
            # GroundedUiTarget contract: geometry-required caps without a site
            # must not reach the actor. Under act_clear, do not silently force
            # observe (declines as model_requested_observe thrash) — ask for a
            # fresh look / demote honesty instead (live 171627).
            # Under entity-resolution SEARCH, Observe is also forbidden as a
            # geometry escape hatch — named question is "where is the search
            # field?", not a generic look (live 203259).
            if (
                outcome.capability in pointer_caps
                and next_action.get("target_point") is None
                and not next_action.get("bounds")
            ):
                # Only entity-resolution SEARCH (picker type_query) forbids
                # Observe as a geometry escape hatch. Source compose_search on
                # chat_list still demotes to observe when AX/OCR Search is
                # missing (live 123746).
                meta_search_gap = False
                if (
                    str(getattr(brief, "meta_action", "") or "").strip().lower()
                    == "search"
                    and outcome.capability in {"type_query", "locate_content"}
                ):
                    try:
                        from plugin.agent.executive.search_applicability import (
                            evaluate_entity_resolution_search,
                        )

                        meta_search_gap = bool(
                            evaluate_entity_resolution_search(execution_state).applicable
                        )
                    except Exception:
                        meta_search_gap = False
                if bool(getattr(brief, "act_clear", False)) or meta_search_gap:
                    try:
                        request_reperceive(
                            execution_state,
                            features,
                            reason=(
                                f"{outcome.capability} without control geometry — "
                                "re-look for search-field point/bounds"
                                if meta_search_gap
                                else (
                                    f"{outcome.capability} act_clear without control "
                                    "geometry — re-look for point/bounds"
                                )
                            ),
                            missing=[
                                "search_field"
                                if meta_search_gap
                                else str(outcome.target or "goal_control")[:40]
                            ],
                        )
                    except Exception:
                        pass
                    # Demote dishonest act_clear so meta can PERCEIVE/EXPLORE.
                    try:
                        if execution_state is not None and not meta_search_gap:
                            execution_state.last_affordance_stance = "explore_needed"
                    except Exception:
                        pass
                    outcome = DecisionOutcome(
                        ok=False,
                        capability=outcome.capability,
                        target=str(outcome.target or ""),
                        why=(
                            f"{outcome.capability} SEARCH without GroundedUiTarget "
                            "geometry — named re-look for search field, not Observe"
                            if meta_search_gap
                            else (
                                f"{outcome.capability} act_clear but no GroundedUiTarget "
                                "geometry — reperceive, do not observe-thrash"
                            )
                        ),
                        confidence=0.2,
                        realization=(
                            f"{outcome.realization}+search_geometry_incomplete"
                            if meta_search_gap
                            else f"{outcome.realization}+act_clear_geometry_incomplete"
                        ),
                    )
                    next_action = {}
                else:
                    outcome = DecisionOutcome(
                        ok=True,
                        capability="observe",
                        target="",
                        why=(
                            f"{outcome.capability} requires GroundedUiTarget geometry "
                            "(point/bounds) and none was bound from perceptor or world"
                        ),
                        confidence=0.3,
                        realization=f"{outcome.realization}+geometry_required_missing",
                    )
                    next_action = {
                        "family": "observe",
                        "text": "",
                        "confidence": 0.3,
                    }
        if outcome.capability in {"locate_content", "type_query"} and outcome.target:
            next_action["text"] = outcome.target
        # Preserve already-typed navigation semantics. Legacy untyped opens must
        # NOT acquire role-establishing navigation authority via re-inference.
        if outcome.capability in {"open_entity", "open_contact"}:
            try:
                typed = (
                    bool(getattr(outcome, "action_is_navigation", False))
                    or bool(getattr(outcome, "establishes_roles", None))
                    or bool(str(getattr(outcome, "target_kind", "") or "").strip())
                )
                if typed and not bool(getattr(outcome, "legacy_semantics", False)):
                    next_action["target_kind"] = str(
                        getattr(outcome, "target_kind", "") or ""
                    )
                    next_action["establishes_roles"] = list(
                        getattr(outcome, "establishes_roles", None) or []
                    )
                    next_action["action_is_navigation"] = bool(
                        getattr(outcome, "action_is_navigation", False)
                    )
                    next_action["legacy_semantics"] = False
                else:
                    import logging as _logging

                    _logging.getLogger(__name__).info(
                        "decision_consultation: legacy open without typed nav "
                        "contract — RoleBinder target-role path only "
                        "(no navigation establish authority)"
                    )
                    outcome.legacy_semantics = True
                    outcome.action_is_navigation = False
                    outcome.establishes_roles = []
                    # Keep any explicit target_kind; do not invent one.
                    next_action["target_kind"] = str(
                        getattr(outcome, "target_kind", "")
                        or next_action.get("target_kind")
                        or ""
                    )
                    next_action["establishes_roles"] = []
                    next_action["action_is_navigation"] = False
                    next_action["legacy_semantics"] = True
            except Exception:
                pass
        if outcome.ok and next_action.get("family"):
            proposal.next_action = next_action
            applied = True
        else:
            proposal.next_action = {}
            applied = False
    else:
        applied = False

    if barren and outcome.capability == "observe":
        request_reperceive(
            execution_state,
            features,
            reason=barren_why,
            missing=["forward"]
            if str(brief.world.get("surface") or "") == "conversation"
            else ["send"],
        )

    # Fold stage1 affordance QC into the brief packet for traces.
    qc = dict(getattr(proposal, "affordance_qc", None) or {})
    if qc and features is not None and isinstance(getattr(features, "extras", None), dict):
        features.extras["affordance_qc"] = qc

    # recommended_probe rides along for fast-path fallback only.
    probe = dict(getattr(proposal, "recommended_probe", None) or {})
    trace = {
        "phase": brief.task_state.phase,
        "surface": brief.navigation.surface,
        "frontier_observed": len(
            (brief.affordance_frontier or {}).get("observed_actions") or []
        ),
        "recommended_probe": str(probe.get("family") or ""),
        "barren_frontier": barren,
        "affordance_qc": qc,
        **outcome.to_dict(),
        "applied": applied,
    }

    if features is not None and isinstance(getattr(features, "extras", None), dict):
        features.extras["decision_consultation"] = trace
    logger.info(
        "Decision consultation: phase=%s surface=%s chosen=%s target=%r "
        "applied=%s via=%s why=%s",
        trace.get("phase"),
        trace.get("surface"),
        outcome.capability,
        outcome.target,
        applied,
        outcome.realization,
        (outcome.why or "")[:120],
    )
    return trace
