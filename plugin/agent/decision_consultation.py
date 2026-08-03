"""Decision consultation: choose the next capability over the *accepted* world.

The perceptor proposes a world document and an action in the same breath. The
world critic then accepts or rejects the structural part of that proposal. Until
now the action rode along unchallenged, so control was really a pile of
imperative rewrites reacting to whatever the perceptor happened to name.

This module closes that gap. After the critic has settled what is true, a
decision-maker is consulted over:

    accepted world document  (surface, open conversation, objects, beliefs)
    task state               (phase, what has been tried, what is exhausted)
    navigation               (which surfaces are reachable, by which capability)
    goal                     (source, content query, destination)

and it returns **one capability plus its argument**. It never returns click
scripts or coordinates: grounding stays with the perceptor, mechanism stays with
the runtime, and irreversible commits stay gated.

A deterministic heuristic covers the same decision surface, so the loop still
runs (and stays testable) when no model is reachable.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Capabilities the decision-maker may name. Motor primitives are deliberately
# absent: choosing "click" is a mechanism decision the runtime already owns.
_CHOOSABLE_EXTRA = ("observe",)

_DECISION_SYSTEM = (
    "You choose the next capability for a macOS UI agent.\n"
    "You are given the ACCEPTED world document (already vetted by a critic), "
    "the task state, navigation options, and the goal.\n"
    "Return ONLY JSON: "
    '{"capability": "...", "target": "...", "why": "...", "confidence": 0-1}.\n'
    "Rules:\n"
    "- capability MUST be one of allowed_capabilities.\n"
    "- Never invent click scripts, coordinates, or menu paths.\n"
    "- Never choose anything in forbidden_capabilities.\n"
    "- commit_irreversible is only for Send/Delete/Confirm and only when the "
    "task state says the commit step is reached.\n"
    "- resolve_entity chooses among visible candidates when several rows could "
    "match a referent (aliases, self markers, group names sharing a name).\n"
    "- compose_search_query authors a fresh search string; use it when search "
    "is empty or a prior query failed.\n"
    "- locate_content makes content reachable inside the open surface; only "
    "use it when the open conversation is the intended source.\n"
    "- Skip any step whose result the world document already shows.\n"
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
    perceptor_suggestion: Dict[str, Any] = field(default_factory=dict)
    # Progressive-disclosure view of the capability registry: the relevant
    # shortlist for this situation, the family taxonomy, and how much of the
    # catalog that shortlist is — so the model sees "N of M relevant" rather
    # than a flat verb dump.
    capability_disclosure: Dict[str, Any] = field(default_factory=dict)

    def to_packet(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "world_model": self.world,
            "task_state": self.task_state.to_dict(),
            "navigation": self.navigation.to_dict(),
            "allowed_capabilities": self.capabilities,
            "forbidden_capabilities": self.navigation.forbidden,
            "capability_disclosure": self.capability_disclosure,
            "visible_candidates": self.candidates[:24],
            "perceptor_suggestion": self.perceptor_suggestion,
        }


@dataclass
class DecisionOutcome:
    ok: bool = False
    capability: str = ""
    target: str = ""
    why: str = ""
    confidence: float = 0.0
    realization: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "capability": self.capability,
            "target": self.target,
            "why": self.why[:200],
            "confidence": round(float(self.confidence or 0.0), 3),
            "realization": self.realization,
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

    banned = {str(f).strip().lower() for f in (forbidden or [])}
    choosable = [c for c in choosable_capabilities() if c not in banned]
    registry = default_registry()
    ordered = registry.shortlist_for(
        meta_action=meta_action,
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
    # A revealed action set exists once actions are exposed on the target.
    if task_state.phase == "invoke_forward":
        facts.append("affordance_set")
    # A commit target is gated open only at the phases where committing is due.
    if task_state.phase in {"choose_destination", "act_on_content"}:
        facts.append("gated_target")
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
    located = bool(
        link_q
        and str(extras.get("last_locate_query") or "").strip().lower() == link_q.lower()
    )
    visible = bool(
        extras.get("source_content_visible")
        or extras.get("timeline_query_hit")
        or extras.get("query_in_timeline")
    )

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
    elif surface == "context_menu":
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

    return TaskState(
        phase=phase,
        open_conversation=open_conversation,
        source_chat_open=source_open,
        content_located=located,
        content_visible=visible,
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
    suggestion = {}
    if isinstance(perceptor_action, dict):
        suggestion = {
            "family": str(perceptor_action.get("family") or ""),
            "text": str(perceptor_action.get("text") or ""),
            "target_label": str(perceptor_action.get("target_label") or ""),
        }
    goal_dict = {
        "operation": str(getattr(goal, "kind", "") or ""),
        "source_conversation": str(getattr(goal, "contact", "") or ""),
        "source_query": str(getattr(goal, "link_query", "") or ""),
        "destination": str(getattr(goal, "target_contact", "") or ""),
    }
    candidate_labels = [str(r.get("label") or "") for r in rows if r.get("label")]

    # The registry now retrieves against the situation, not in the abstract:
    # what is true right now (facts) plus what the executive last decided to do
    # (meta_action) drive both the ranked shortlist and its disclosure view.
    facts = situation_facts(task_state, candidates=candidate_labels, goal=goal_dict)
    meta_action = str(getattr(execution_state, "last_meta_action", "") or "act")

    from plugin.agent.executive.capabilities import default_registry

    disclosure = default_registry().disclosure(
        meta_action=meta_action,
        facts=facts,
        limit=6,
    )

    return DecisionBrief(
        goal=goal_dict,
        world={
            "surface": str(doc.get("surface") or ""),
            "open_conversation": str(doc.get("open_conversation") or ""),
            "focused_field_role": str(doc.get("focused_field_role") or ""),
            "objects": [
                {"text": str(o.get("text") or ""), "kind": str(o.get("kind") or "")}
                for o in (doc.get("objects") or [])[:16]
                if isinstance(o, dict)
            ],
            "beliefs": list(doc.get("beliefs") or [])[:8],
        },
        task_state=task_state,
        navigation=navigation,
        capabilities=ranked_capabilities(
            surface=str(doc.get("surface") or ""),
            forbidden=navigation.forbidden,
            facts=facts,
            meta_action=meta_action,
        ),
        candidates=candidate_labels,
        perceptor_suggestion=suggestion,
        capability_disclosure=disclosure,
    )


def heuristic_decision(brief: DecisionBrief) -> DecisionOutcome:
    """Deterministic choice over the same brief the model sees."""
    state = brief.task_state
    goal = brief.goal
    source = str(goal.get("source_conversation") or "")
    dest = str(goal.get("destination") or "")
    query = str(goal.get("source_query") or "")
    has_candidates = bool(brief.candidates)
    forbidden = set(brief.navigation.forbidden)

    def out(capability: str, target: str, why: str, confidence: float = 0.6) -> DecisionOutcome:
        return DecisionOutcome(
            ok=True,
            capability=capability,
            target=target,
            why=why,
            confidence=confidence,
            realization="heuristic",
        )

    if state.phase == "choose_destination":
        if has_candidates and dest:
            return out("resolve_entity", dest, "pick the destination row among visible candidates")
        return out("observe", "", "destination picker open but no candidate rows read yet", 0.3)

    if state.phase == "invoke_forward":
        return out("invoke_affordance", "Forward", "context menu is open; Forward is reversible")

    if state.phase == "reach_source":
        if has_candidates and source:
            return out("resolve_entity", source, "choose the source chat among visible rows")
        if "compose_search_query" in forbidden:
            return out("dismiss_transient", "", "leave the overlay before searching for the source", 0.4)
        return out("compose_search_query", "", "author a search string to reach the source chat")

    if state.phase == "hunt_content":
        return out("locate_content", query, "make the queried message reachable in the source chat")

    # act_on_content
    if state.content_located or state.content_visible:
        return out("reveal_actions", query or source, "expose Forward on the located message")
    return out("select_content", query or source, "focus the located message before revealing actions")


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
                "perception",
                messages,
                caller=lambda **kwargs: _call_llm_hard_timeout(self.timeout_s, **kwargs),
                call_kwargs={"task": "perception", "timeout": self.timeout_s},
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


def sanitize_decision(payload: Dict[str, Any], brief: DecisionBrief) -> DecisionOutcome:
    """Keep only choices the catalog, navigation and safety gates allow."""
    if not isinstance(payload, dict):
        return DecisionOutcome(ok=False, why="non-dict decision payload")
    capability = str(payload.get("capability") or "").strip().lower().replace("-", "_")
    if not capability:
        return DecisionOutcome(ok=False, why="no capability named")
    if capability in set(brief.navigation.forbidden):
        return DecisionOutcome(ok=False, why=f"{capability} forbidden on this surface")
    if capability not in set(brief.capabilities):
        return DecisionOutcome(ok=False, why=f"unknown capability {capability!r}")

    target = str(payload.get("target") or payload.get("text") or "").strip()
    if capability == "resolve_entity" and not brief.candidates:
        return DecisionOutcome(ok=False, why="resolve_entity chosen with an empty candidate_set")
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

    try:
        confidence = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return DecisionOutcome(
        ok=True,
        capability=capability,
        target=target,
        why=str(payload.get("why") or "")[:200],
        confidence=max(0.0, min(1.0, confidence)) or 0.6,
        realization="llm_decision",
    )


def consult_decision(
    brief: DecisionBrief,
    chooser: Optional[DecisionChooser] = None,
    *,
    use_llm: Optional[bool] = None,
) -> DecisionOutcome:
    """Choose the next capability; fall back to the heuristic on any miss."""
    fallback = heuristic_decision(brief)
    want_llm = decision_llm_enabled() if use_llm is None else bool(use_llm)
    if not want_llm and chooser is None:
        return fallback

    author = chooser or LlmDecisionChooser()
    packet = dict(brief.to_packet())
    packet["heuristic_suggestion"] = {
        "capability": fallback.capability,
        "target": fallback.target,
    }
    try:
        payload = author.choose(_DECISION_SYSTEM, packet) or {}
    except Exception as exc:
        logger.warning("decision chooser failed: %s", exc)
        return fallback
    decided = sanitize_decision(payload, brief)
    if not decided.ok:
        fallback.why = f"{fallback.why}; llm_rejected={decided.why}"
        fallback.realization = "heuristic_after_llm_miss"
        return fallback
    return decided


# Capabilities that need a screen target; keep the perceptor's grounding when
# the decision keeps the same family.
_POINTER_CAPABILITIES = frozenset(
    {"open_entity", "select_content", "reveal_actions", "invoke_affordance", "commit_irreversible"}
)


def apply_decision_consultation(
    proposal: Any,
    goal: Any,
    features: Any = None,
    execution_state: Any = None,
    *,
    chooser: Optional[DecisionChooser] = None,
) -> Dict[str, Any]:
    """Replace the perceptor's action with the consulted capability choice.

    The perceptor keeps ownership of *what is on screen*; this decides *what to
    do about it*. Returns a trace dict (also stored on features.extras).
    """
    if proposal is None or not decision_consultation_enabled():
        return {}
    document = getattr(execution_state, "unified_world_document", None)
    if not isinstance(document, dict) or not document:
        document = dict(getattr(proposal, "world_model", None) or {})

    perceptor_action = dict(getattr(proposal, "next_action", None) or {})
    brief = build_decision_brief(
        goal,
        world_document=document,
        features=features,
        execution_state=execution_state,
        perceptor_action=perceptor_action,
    )
    outcome = consult_decision(brief, chooser=chooser)
    trace = {
        "phase": brief.task_state.phase,
        "surface": brief.navigation.surface,
        "perceptor_family": str(perceptor_action.get("family") or ""),
        **outcome.to_dict(),
    }
    if not outcome.ok or not outcome.capability:
        trace["applied"] = False
    elif outcome.capability == "observe":
        # Judgment says look again; leave the perceptor's action alone rather
        # than burning a step on a no-op.
        trace["applied"] = False
    else:
        next_action: Dict[str, Any] = {
            "family": outcome.capability,
            "text": outcome.target,
            "confidence": outcome.confidence or float(getattr(proposal, "confidence", 0.0) or 0.0),
        }
        same_family = str(perceptor_action.get("family") or "") == outcome.capability
        if outcome.capability in _POINTER_CAPABILITIES:
            # Grounding belongs to the perceptor; carry it when it still applies.
            if same_family or not outcome.target:
                for key in ("target_id", "target_label", "target_point"):
                    if perceptor_action.get(key) is not None:
                        next_action[key] = perceptor_action[key]
            if not next_action.get("target_label") and outcome.target:
                next_action["target_label"] = outcome.target
        proposal.next_action = next_action
        trace["applied"] = True

    if features is not None and isinstance(getattr(features, "extras", None), dict):
        features.extras["decision_consultation"] = trace
    logger.info(
        "Decision consultation: phase=%s surface=%s perceptor=%s chosen=%s target=%r "
        "applied=%s via=%s why=%s",
        trace.get("phase"),
        trace.get("surface"),
        trace.get("perceptor_family"),
        outcome.capability,
        outcome.target,
        trace.get("applied"),
        outcome.realization,
        outcome.why[:120],
    )
    return trace
