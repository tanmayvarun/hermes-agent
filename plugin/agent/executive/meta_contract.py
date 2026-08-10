"""Universal executive meta-action contracts (v1).

See ``docs/design/agent-design.md``. Meta-actions name *why* effort is spent,
not the motor used. Host/platform details stay behind capability adapters.

This module is the typed envelope + DecisionProblem + ScopeRef/EntityRef.
Kind-specific SEARCH episode types also live in ``search_episode`` and are
mapped into SearchRequest/SearchResult shapes here for the shared envelope.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Union

from plugin.agent.executive.meta_action import MetaAction


class MetaActionCategory(str, Enum):
    EPISTEMIC = "epistemic"
    INSTRUMENTAL = "instrumental"
    CONTROL = "control"


# Frozen v1 core — purpose vocabulary (not mechanisms).
CORE_META_KINDS = frozenset(
    {
        MetaAction.THINK,
        MetaAction.PERCEIVE,
        MetaAction.SEARCH,
        MetaAction.EXPLORE,
        MetaAction.ACT,
        MetaAction.ASK,
        MetaAction.DELEGATE,
        MetaAction.WAIT,
    }
)

META_ACTION_CATEGORY: Dict[MetaAction, MetaActionCategory] = {
    MetaAction.THINK: MetaActionCategory.EPISTEMIC,
    MetaAction.PERCEIVE: MetaActionCategory.EPISTEMIC,
    MetaAction.SEARCH: MetaActionCategory.EPISTEMIC,
    MetaAction.EXPLORE: MetaActionCategory.EPISTEMIC,
    MetaAction.ASK: MetaActionCategory.EPISTEMIC,
    MetaAction.ACT: MetaActionCategory.INSTRUMENTAL,
    MetaAction.DELEGATE: MetaActionCategory.CONTROL,
    MetaAction.WAIT: MetaActionCategory.CONTROL,
}


class MetaResultStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    NOT_FOUND = "not_found"
    BLOCKED = "blocked"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


@dataclass
class ScopeRef:
    """Domain-neutral scope — never bake WhatsAppRegion / FinderFolder into exec."""

    domain: str = ""
    locator: Union[str, Dict[str, Any]] = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"domain": self.domain, "locator": self.locator}

    @classmethod
    def from_dict(cls, raw: Any) -> "ScopeRef":
        if not isinstance(raw, dict):
            if raw is None:
                return cls()
            return cls(domain="unknown", locator=str(raw))
        return cls(
            domain=str(raw.get("domain") or "")[:64],
            locator=raw.get("locator")
            if isinstance(raw.get("locator"), (str, dict))
            else str(raw.get("locator") or ""),
        )


@dataclass
class EntityRef:
    entity_type: str = ""
    domain: str = ""
    identity: Any = None
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    provenance: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Any) -> "EntityRef":
        if not isinstance(raw, dict):
            return cls()
        return cls(
            entity_type=str(raw.get("entity_type") or "")[:64],
            domain=str(raw.get("domain") or "")[:64],
            identity=raw.get("identity"),
            properties=dict(raw.get("properties") or {})
            if isinstance(raw.get("properties"), dict)
            else {},
            confidence=float(raw.get("confidence") or 0.0),
            provenance=str(raw.get("provenance") or "")[:120],
        )


@dataclass
class EpistemicExpectation:
    questions_addressed: List[str] = field(default_factory=list)
    expected_information_gain: float = 0.0
    expected_coverage: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InstrumentalExpectation:
    expected_goal_progress: float = 0.0
    expected_transition: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MetaActionBudget:
    time_s: Optional[float] = None
    steps: Optional[int] = None
    risk: Optional[str] = None
    cost: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class MetaActionRequest:
    """Universal request envelope — every meta-action declares why / expect / stop."""

    kind: MetaAction = MetaAction.THINK
    objective: str = ""
    intention_id: str = ""
    belief_context: Dict[str, Any] = field(default_factory=dict)
    motivation: str = ""
    scope: Optional[ScopeRef] = None
    constraints: List[str] = field(default_factory=list)
    success_condition: str = ""
    expected_result: str = ""
    budget: Optional[MetaActionBudget] = None
    task_id: str = ""
    parent_action_id: str = ""
    # Kind-specific payload (ThinkRequest dict, SearchRequest dict, …).
    payload: Dict[str, Any] = field(default_factory=dict)
    epistemic: Optional[EpistemicExpectation] = None
    instrumental: Optional[InstrumentalExpectation] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value if isinstance(self.kind, MetaAction) else str(self.kind),
            "category": category_of(self.kind).value,
            "objective": self.objective,
            "intention_id": self.intention_id,
            "belief_context": dict(self.belief_context or {}),
            "motivation": self.motivation,
            "scope": self.scope.to_dict() if self.scope else None,
            "constraints": list(self.constraints or [])[:12],
            "success_condition": self.success_condition,
            "expected_result": self.expected_result,
            "budget": self.budget.to_dict() if self.budget else None,
            "task_id": self.task_id,
            "parent_action_id": self.parent_action_id,
            "payload": dict(self.payload or {}),
            "epistemic": self.epistemic.to_dict() if self.epistemic else None,
            "instrumental": self.instrumental.to_dict() if self.instrumental else None,
        }


@dataclass
class MetaActionResult:
    status: MetaResultStatus = MetaResultStatus.UNCERTAIN
    observations: List[Any] = field(default_factory=list)
    artifacts: List[Any] = field(default_factory=list)
    proposed_belief_updates: List[Dict[str, Any]] = field(default_factory=list)
    discovered_capabilities: List[str] = field(default_factory=list)
    unresolved_questions: List[str] = field(default_factory=list)
    suggested_next_moves: List[str] = field(default_factory=list)
    side_effects: List[Any] = field(default_factory=list)
    confidence: float = 0.0
    provenance: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value
            if isinstance(self.status, MetaResultStatus)
            else str(self.status),
            "observations": list(self.observations or [])[:24],
            "artifacts": list(self.artifacts or [])[:24],
            "proposed_belief_updates": list(self.proposed_belief_updates or [])[:12],
            "discovered_capabilities": list(self.discovered_capabilities or [])[:12],
            "unresolved_questions": list(self.unresolved_questions or [])[:12],
            "suggested_next_moves": list(self.suggested_next_moves or [])[:12],
            "side_effects": list(self.side_effects or [])[:12],
            "confidence": float(self.confidence),
            "provenance": str(self.provenance or "")[:160],
            "payload": dict(self.payload or {}),
        }


# ---------------------------------------------------------------------------
# Kind-specific request / result shapes (payload contracts)
# ---------------------------------------------------------------------------


@dataclass
class ThinkRequest:
    objective: str = ""
    available_evidence: List[Any] = field(default_factory=list)
    current_beliefs: Dict[str, Any] = field(default_factory=dict)
    unresolved_questions: List[str] = field(default_factory=list)
    candidate_hypotheses: Optional[List[str]] = None
    available_capability_summaries: Optional[List[str]] = None
    reasoning_budget: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ThinkResult:
    conclusions: List[str] = field(default_factory=list)
    hypotheses: List[str] = field(default_factory=list)
    proposed_intentions: List[str] = field(default_factory=list)
    recommended_meta_actions: List[str] = field(default_factory=list)
    unresolved_questions: List[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PerceiveRequest:
    scope: Optional[ScopeRef] = None
    questions: List[str] = field(default_factory=list)
    focus: Optional[str] = None
    desired_granularity: str = "adaptive"
    modalities: Optional[List[str]] = None
    prior_state: Optional[Any] = None
    budget: Optional[MetaActionBudget] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope.to_dict() if self.scope else None,
            "questions": list(self.questions or [])[:12],
            "focus": self.focus,
            "desired_granularity": self.desired_granularity,
            "modalities": list(self.modalities or []) if self.modalities else None,
            "prior_state": self.prior_state,
            "budget": self.budget.to_dict() if self.budget else None,
        }


@dataclass
class PerceiveResult:
    observed_state: List[Any] = field(default_factory=list)
    observed_entities: List[Any] = field(default_factory=list)
    observed_relationships: List[Any] = field(default_factory=list)
    grounded_affordances: List[Any] = field(default_factory=list)
    latent_affordance_hypotheses: List[Any] = field(default_factory=list)
    evidence_gaps: List[str] = field(default_factory=list)
    unknown_frontiers: List[str] = field(default_factory=list)
    coverage: Optional[Any] = None
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SearchRequest:
    sought: str = ""
    criteria: str = ""
    scopes: List[ScopeRef] = field(default_factory=list)
    preferred_sources: List[str] = field(default_factory=list)
    ranking_objective: Optional[str] = None
    stopping_condition: Optional[str] = None
    max_results: Optional[int] = None
    budget: Optional[MetaActionBudget] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sought": self.sought,
            "criteria": self.criteria,
            "scopes": [s.to_dict() for s in self.scopes],
            "preferred_sources": list(self.preferred_sources or []),
            "ranking_objective": self.ranking_objective,
            "stopping_condition": self.stopping_condition,
            "max_results": self.max_results,
            "budget": self.budget.to_dict() if self.budget else None,
        }


@dataclass
class ContractSearchResult:
    """Envelope SearchResult (distinct name from search_episode.SearchResult)."""

    matches: List[Any] = field(default_factory=list)
    ranked_candidates: List[Any] = field(default_factory=list)
    searched_scopes: List[str] = field(default_factory=list)
    unexplored_scopes: List[str] = field(default_factory=list)
    coverage: Optional[Dict[str, Any]] = None
    exhausted: bool = False
    refinements: List[str] = field(default_factory=list)
    confidence: float = 0.0
    chosen: Optional[Dict[str, Any]] = None
    fail_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExploreRequest:
    objective: str = ""
    current_hypotheses: List[str] = field(default_factory=list)
    known_boundaries: List[str] = field(default_factory=list)
    promising_frontiers: List[str] = field(default_factory=list)
    allowed_probe_types: List[str] = field(default_factory=list)
    information_budget: Optional[Any] = None
    risk_budget: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExploreResult:
    discoveries: List[Any] = field(default_factory=list)
    newly_discovered_scopes: List[str] = field(default_factory=list)
    newly_discovered_affordances: List[str] = field(default_factory=list)
    tested_hypotheses: List[str] = field(default_factory=list)
    rejected_hypotheses: List[str] = field(default_factory=list)
    new_search_criteria: List[str] = field(default_factory=list)
    new_candidate_routes: List[str] = field(default_factory=list)
    unresolved_frontiers: List[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ActRequest:
    desired_change: str = ""
    target: Optional[Any] = None
    grounded_method: Optional[str] = None
    acceptable_methods: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    expected_transition: Optional[Any] = None
    reversibility: Optional[str] = None
    risk: Optional[str] = None
    confirmation_policy: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ActResult:
    execution_status: str = ""
    attempted_method: str = ""
    immediate_observations: List[Any] = field(default_factory=list)
    side_effects: List[Any] = field(default_factory=list)
    expected_transition: Optional[Any] = None
    observed_transition: Optional[Any] = None
    verification_needed: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AskRequest:
    recipient: str = "user"
    question_or_request: str = ""
    information_needed: Optional[str] = None
    reason: Optional[str] = None
    urgency: Optional[str] = None
    expected_response_type: Optional[str] = None
    timeout: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AskResult:
    response: Optional[Any] = None
    status: str = "pending"
    observations: List[Any] = field(default_factory=list)
    new_constraints: List[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DelegateRequest:
    objective: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    constraints: List[str] = field(default_factory=list)
    expected_deliverables: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    budget: Optional[MetaActionBudget] = None
    deadline: Optional[str] = None
    completion_condition: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.budget:
            d["budget"] = self.budget.to_dict()
        return d


@dataclass
class DelegateResult:
    status: str = ""
    deliverables: List[Any] = field(default_factory=list)
    observations: List[Any] = field(default_factory=list)
    side_effects: List[Any] = field(default_factory=list)
    unresolved_questions: List[str] = field(default_factory=list)
    evidence: List[Any] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WaitRequest:
    waiting_for: str = ""
    condition: Optional[str] = None
    timeout: Optional[float] = None
    polling_policy: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WaitResult:
    condition_met: bool = False
    elapsed: float = 0.0
    observations: List[Any] = field(default_factory=list)
    timeout: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionProblem:
    """Executive choice framing — semantic guide, not a rigid ladder."""

    goal: Any = None
    current_intention: str = ""
    known: List[str] = field(default_factory=list)
    unknown: List[str] = field(default_factory=list)
    blocking_uncertainty: List[str] = field(default_factory=list)
    available_meta_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal if isinstance(self.goal, (str, dict, type(None))) else str(self.goal),
            "current_intention": self.current_intention,
            "known": list(self.known or [])[:12],
            "unknown": list(self.unknown or [])[:12],
            "blocking_uncertainty": list(self.blocking_uncertainty or [])[:12],
            "available_meta_actions": list(self.available_meta_actions or [])[:16],
            "selection_semantics": SELECTION_SEMANTICS,
        }


SELECTION_SEMANTICS = [
    "reliable_goal_action → ACT",
    "criteria_known_location_unknown → SEARCH",
    "scope_known_need_state → PERCEIVE",
    "target_or_route_unknown → EXPLORE",
    "existing_info_suffices → THINK",
    "need_other_actor → ASK",
    "bounded_specialist_objective → DELEGATE",
    "time_or_external_process → WAIT",
]


@dataclass
class TaskRecord:
    """Durable task checkpoint for long-running / interrupted work."""

    task_id: str = ""
    original_goal: Any = None
    status: str = "active"
    current_intention: str = ""
    beliefs: Dict[str, Any] = field(default_factory=dict)
    bindings: Dict[str, Any] = field(default_factory=dict)
    open_questions: List[str] = field(default_factory=list)
    hypotheses: List[str] = field(default_factory=list)
    exploration_state: Dict[str, Any] = field(default_factory=dict)
    important_events: List[Any] = field(default_factory=list)
    artifacts: List[Any] = field(default_factory=list)
    unfinished_commitments: List[str] = field(default_factory=list)
    last_active_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def category_of(kind: Union[MetaAction, str]) -> MetaActionCategory:
    if isinstance(kind, str):
        try:
            kind = MetaAction(kind)
        except ValueError:
            return MetaActionCategory.EPISTEMIC
    return META_ACTION_CATEGORY.get(kind, MetaActionCategory.EPISTEMIC)


def is_core_meta(kind: Union[MetaAction, str]) -> bool:
    if isinstance(kind, str):
        try:
            kind = MetaAction(kind)
        except ValueError:
            return False
    return kind in CORE_META_KINDS


def canonicalize_meta_kind(token: str) -> Optional[MetaAction]:
    """Parse a meta-action token; reject unknown and legacy tokens."""
    raw = str(token or "").strip().lower().replace("-", "_")
    if not raw:
        return None
    try:
        kind = MetaAction(raw)
    except ValueError:
        return None
    return kind if kind in CORE_META_KINDS else None


def core_meta_action_values() -> List[str]:
    return [a.value for a in (
        MetaAction.THINK,
        MetaAction.PERCEIVE,
        MetaAction.SEARCH,
        MetaAction.EXPLORE,
        MetaAction.ACT,
        MetaAction.ASK,
        MetaAction.DELEGATE,
        MetaAction.WAIT,
    )]


def search_request_from_episode(ep: Optional[Dict[str, Any]]) -> SearchRequest:
    from plugin.agent.capabilities.search_episode import search_intent_from_episode

    intent = search_intent_from_episode(ep)
    scope = ScopeRef(
        domain=str(intent.search_space or "ui_filter"),
        locator=str(intent.scope or intent.search_space or ""),
    )
    return SearchRequest(
        sought=intent.sought,
        criteria=intent.criteria,
        scopes=[scope] if scope.domain or scope.locator else [],
        preferred_sources=list(intent.sources or []),
        stopping_condition=intent.stopping_rule,
        max_results=intent.result_limit,
    )


def contract_search_result_from_episode(
    ep: Optional[Dict[str, Any]],
    *,
    exhausted: bool = False,
) -> ContractSearchResult:
    from plugin.agent.capabilities.search_episode import search_result_from_episode

    r = search_result_from_episode(ep, exhausted=exhausted)
    coverage = dict(r.coverage or {})
    searched = list(coverage.get("explored_scopes") or [])
    return ContractSearchResult(
        matches=list(r.candidates or []),
        ranked_candidates=list(r.candidates or []),
        searched_scopes=searched,
        unexplored_scopes=list(r.unexplored_scopes or []),
        coverage=coverage,
        exhausted=bool(r.exhausted or exhausted),
        refinements=[],
        confidence=float(r.confidence or 0.0),
        chosen=r.chosen if isinstance(r.chosen, dict) else None,
        fail_reason=str(r.fail_reason or ""),
    )


def decision_problem_from_meta_context(
    ctx: Any,
    *,
    goal: Any = None,
    phase: str = "",
) -> DecisionProblem:
    """Build DecisionProblem signals for the meta packet / consultant."""
    blocking: List[str] = []
    known: List[str] = []
    unknown: List[str] = []
    suff = getattr(ctx, "sufficiency", None)
    if suff is not None:
        blocking = [
            str(b)
            for b in (getattr(suff, "blocking_uncertainties", None) or [])
            if str(b).strip()
        ][:8]
        if getattr(suff, "sufficient_to_act", False):
            known.append("sufficient_to_act")
        if getattr(suff, "observe_has_value", False):
            unknown.append("observe_may_close_gap")
    if getattr(ctx, "referent_search_needed", False):
        unknown.append("referent_location")
        known.append("search_criteria") if getattr(ctx, "search_has_criteria", True) else unknown.append(
            "search_criteria"
        )
    # Entity-resolution gap → SEARCH is the admissible epistemic meta-action.
    if getattr(ctx, "destination_search_needed", False):
        known.append("search_criteria")
        known.append("searchable_scope_available")
        unknown.append("entity_location_in_scope")
        gap_text = (
            "Where is the destination entity inside the searchable picker scope?"
        )
        if gap_text not in blocking:
            blocking.insert(0, gap_text)
    if getattr(ctx, "address_known", False) or getattr(ctx, "retrieve_ready", False):
        known.append("address_known")
    if getattr(ctx, "hard_block", False):
        blocking.append("hard_block")
    if getattr(ctx, "branch_stale", False):
        unknown.append("viable_branch")
    intention = str(phase or getattr(ctx, "current_intention", "") or "")
    if getattr(ctx, "destination_search_needed", False):
        intention = intention or "select destination"
    elif getattr(ctx, "referent_search_needed", False):
        intention = intention or "resolve_referent_by_search"
    elif getattr(ctx, "post_action_look_owed", False):
        intention = intention or "reperceive_after_act"
    return DecisionProblem(
        goal=goal,
        current_intention=intention[:120],
        known=known,
        unknown=unknown,
        blocking_uncertainty=blocking,
        available_meta_actions=core_meta_action_values(),
    )


def envelope_for_choice(
    kind: MetaAction,
    *,
    motivation: str = "",
    expected_result: str = "",
    success_condition: str = "",
    objective: str = "",
    scope: Optional[ScopeRef] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> MetaActionRequest:
    """Build a minimal envelope so every chosen meta declares why/expect/stop."""
    return MetaActionRequest(
        kind=kind,
        objective=objective or motivation[:160],
        motivation=motivation[:200],
        expected_result=expected_result[:200],
        success_condition=success_condition[:200],
        scope=scope,
        payload=dict(payload or {}),
    )
