"""Generic intention execution: Intention (immutable) + IntentionFrame (mutable).

See docs/design/agent-design.md — meta-actions retry at intent level:

    intention → method → attempt → effect verification → recovery

Reveal probes seed an EXPLORE frame; ActRequest/ExploreRequest reference the
frame rather than owning retry architecture.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple
import time
import uuid


class RetrySafety(str, Enum):
    SAFE_TO_RETRY = "safe_to_retry"
    VERIFY_BEFORE_RETRY = "verify_before_retry"
    NEVER_AUTO_RETRY = "never_auto_retry"


class MethodOutcome(str, Enum):
    EFFECT_OBSERVED = "effect_observed"
    EFFECT_ABSENT = "effect_absent"
    EFFECT_UNCERTAIN = "effect_uncertain"
    UNEXPECTED_EFFECT = "unexpected_effect"


class IntentionOutcome(str, Enum):
    ACHIEVED = "achieved"
    ACTIVE = "active"
    BLOCKED = "blocked"
    EXHAUSTED = "exhausted"
    SUPERSEDED = "superseded"


class IntentionStatus(str, Enum):
    ACTIVE = "active"
    ACHIEVED = "achieved"
    BLOCKED = "blocked"
    EXHAUSTED = "exhausted"
    SUPERSEDED = "superseded"


class TerminationReason(str, Enum):
    SUCCESS = "success"
    LOCAL_ROUTE_EXHAUSTED = "local_route_exhausted"
    BUDGET_EXHAUSTED = "budget_exhausted"
    USER_CANCELLED = "user_cancelled"
    POLICY_BLOCKED = "policy_blocked"
    SUPERSEDED = "superseded"
    INVALIDATED_BY_WORLD_CHANGE = "invalidated_by_world_change"
    NO_LONGER_RELEVANT = "no_longer_relevant"


class FailureClass(str, Enum):
    TRANSIENT = "transient"
    GROUNDING = "grounding"
    EFFECT_UNCERTAIN = "effect_uncertain"
    METHOD_INEFFECTIVE = "method_ineffective"
    PRECONDITION_MISSING = "precondition_missing"
    UNEXPECTED_WORLD = "unexpected_world"
    LOCAL_ROUTE_EXHAUSTED = "local_route_exhausted"
    UNSAFE = "unsafe"


class MethodStatus(str, Enum):
    UNTRIED = "untried"
    SUCCEEDED = "succeeded"
    INEFFECTIVE = "ineffective"
    INVALID = "invalid"
    SUPERSEDED = "superseded"


class AttemptValidity(str, Enum):
    VALID = "valid"
    INCONCLUSIVE_GROUNDING = "inconclusive_grounding"
    ACTUATOR_ERROR = "actuator_error"
    EFFECT_UNCERTAIN = "effect_uncertain"


class RecoveryAction(str, Enum):
    CONTINUE_INTENTION = "continue_intention"
    SUSPEND_INTENTION = "suspend_intention"
    ABANDON_INTENTION = "abandon_intention"
    RETURN_TO_EXECUTIVE = "return_to_executive"
    SPAWN_CHILD_INTENTION = "spawn_child_intention"


class MethodProvenance(str, Enum):
    OBSERVED = "observed"
    APP_PRIOR = "app_prior"
    GENERIC_PRIOR = "generic_prior"
    MEMORY = "memory"
    LLM_INFERRED = "llm_inferred"
    PREVIOUS_SUCCESS = "previous_success"
    USER_INSTRUCTION = "user_instruction"


@dataclass(frozen=True)
class IntentionOrigin:
    kind: str = "executive_decision"
    parent_goal_id: str = ""
    triggering_uncertainty: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Intention:
    """Immutable local objective — do not mutate mid-execution."""

    id: str
    objective: str
    success_predicate: str
    scope: Optional[str] = None
    created_from: IntentionOrigin = field(default_factory=IntentionOrigin)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "objective": self.objective,
            "success_predicate": self.success_predicate,
            "scope": self.scope,
            "created_from": self.created_from.to_dict(),
        }


@dataclass
class EffectSpec:
    """Predicate-based expected effect + settle window (not affordance TTL)."""

    success_any: List[str] = field(default_factory=list)
    settle_window_ms: int = 1200

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success_any": list(self.success_any),
            "settle_window_ms": int(self.settle_window_ms),
        }


@dataclass
class RetryPolicy:
    same_method_max: int = 1
    try_alternatives: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IntentionBudget:
    max_methods: int = 5
    max_wall_time_s: float = 20.0
    max_perception_calls: int = 6
    max_cost: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScoringPolicy:
    """Meta-action-specific ranking weights for the method frontier."""

    progress_weight: float = 0.5
    information_weight: float = 0.5
    risk_weight: float = 0.3
    latency_weight: float = 0.2
    cost_weight: float = 0.1
    reversibility_weight: float = 0.3
    grounding_weight: float = 0.4
    repeat_penalty_weight: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def for_meta(cls, meta: str) -> "ScoringPolicy":
        m = str(meta or "").strip().lower()
        if m == "explore":
            return cls(
                progress_weight=0.25,
                information_weight=0.9,
                reversibility_weight=0.7,
                risk_weight=0.2,
            )
        if m == "act":
            return cls(
                progress_weight=0.95,
                information_weight=0.15,
                grounding_weight=0.9,
                risk_weight=0.8,
            )
        if m == "search":
            return cls(
                progress_weight=0.4,
                information_weight=0.85,
                grounding_weight=0.5,
            )
        return cls()


@dataclass
class MethodSpec:
    id: str
    capability: str
    target_binding: Optional[str] = None
    preconditions: List[str] = field(default_factory=list)
    expected_effect: EffectSpec = field(default_factory=EffectSpec)
    retry_safety: str = RetrySafety.SAFE_TO_RETRY.value
    provenance: str = MethodProvenance.GENERIC_PRIOR.value
    cost: float = 0.2
    latency: float = 0.2
    risk: float = 0.1
    reversibility: float = 0.9
    gesture: str = ""  # optional motor detail (context_click / hover)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "capability": self.capability,
            "target_binding": self.target_binding,
            "preconditions": list(self.preconditions),
            "expected_effect": self.expected_effect.to_dict(),
            "retry_safety": self.retry_safety,
            "provenance": self.provenance,
            "cost": self.cost,
            "latency": self.latency,
            "risk": self.risk,
            "reversibility": self.reversibility,
            "gesture": self.gesture,
        }


@dataclass
class AttemptRecord:
    method_id: str
    attempt_id: str = ""
    intention_id: str = ""
    world_before: str = ""
    grounding_snapshot: str = ""
    execution_status: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    observation_quality: float = 0.0
    method_outcome: str = ""
    failure_class: Optional[str] = None
    world_after: Optional[str] = None
    expected_effect: str = ""
    motor_point: Optional[List[float]] = None
    attempt_validity: str = AttemptValidity.VALID.value
    method_status: str = MethodStatus.UNTRIED.value

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def may_mark_method_ineffective(self) -> bool:
        """Only valid attempts provide strong evidence against a method."""
        return self.attempt_validity == AttemptValidity.VALID.value


@dataclass
class BindingRef:
    """Typed reference to a role binding (not a free string)."""

    role: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"role": self.role}

    def __str__(self) -> str:
        return self.role


@dataclass
class CapabilityRef:
    """Typed reference to a capability (not a free string)."""

    name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"capability": self.name}

    def __str__(self) -> str:
        return self.name


@dataclass
class ScopeRef:
    """Typed world-scope reference for intentions / methods."""

    kind: str = ""  # surface | app | binding | method_context
    value: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "value": self.value}


@dataclass
class MethodContext:
    """Method-relevant semantic world state for failure scope.

    Prefer this over opaque textual world hashes so irrelevant churn
    (e.g. message timestamps) does not resurrect every failed method.
    """

    surface: str = ""
    target_selected: bool = False
    action_surface_visible: bool = False
    overlay: str = ""

    def signature(self) -> str:
        return (
            f"surface={str(self.surface or '').strip().lower()}"
            f"|sel={int(bool(self.target_selected))}"
            f"|act={int(bool(self.action_surface_visible))}"
            f"|ov={str(self.overlay or '').strip().lower()}"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "surface": self.surface,
            "target_selected": bool(self.target_selected),
            "action_surface_visible": bool(self.action_surface_visible),
            "overlay": self.overlay,
            "signature": self.signature(),
        }

    @classmethod
    def from_any(cls, raw: Any) -> "MethodContext":
        if isinstance(raw, MethodContext):
            return raw
        if isinstance(raw, dict):
            return cls(
                surface=str(raw.get("surface") or ""),
                target_selected=bool(raw.get("target_selected")),
                action_surface_visible=bool(raw.get("action_surface_visible")),
                overlay=str(raw.get("overlay") or ""),
            )
        # Legacy: opaque string treated as overlay tag only (not a full hash).
        text = str(raw or "").strip()
        if not text:
            return cls()
        if text.startswith("surface="):
            parts = dict(
                p.split("=", 1) for p in text.split("|") if "=" in p
            )
            return cls(
                surface=str(parts.get("surface") or ""),
                target_selected=str(parts.get("sel") or "0") in {"1", "true"},
                action_surface_visible=str(parts.get("act") or "0") in {"1", "true"},
                overlay=str(parts.get("ov") or ""),
            )
        return cls(overlay=text)


@dataclass
class Predicate:
    """Structured success / precondition predicate (prefer over raw strings)."""

    subject: Any = ""  # BindingRef preferred; str accepted during migration
    relation: str = ""
    object: Any = ""  # CapabilityRef / BindingRef preferred
    value: Any = None

    def to_dict(self) -> Dict[str, Any]:
        subj = self.subject
        obj = self.object
        return {
            "subject": subj.to_dict() if hasattr(subj, "to_dict") else subj,
            "relation": self.relation,
            "object": obj.to_dict() if hasattr(obj, "to_dict") else obj,
            "value": self.value,
        }

    def as_legacy_string(self) -> str:
        subj = str(self.subject) if self.subject is not None else ""
        obj = str(self.object) if self.object is not None else ""
        if self.relation and obj:
            return f"{subj}.{self.relation}:{obj}".strip(".")
        return self.relation or subj


@dataclass
class MethodFrontier:
    """Decision state for methods. ``attempted`` is a ledger, not a blocker.

    Eligibility derives from ``method_status`` (and explicit ineligible /
    invalidated / superseded sets). An inconclusive-grounding attempt leaves
    status UNTRIED → method stays eligible.

    World-scoped ineffectiveness is coherent: when the method-relevant
    ``MethodContext`` changes, ``refresh_method_frontier`` reactivates
    ``INEFFECTIVE → UNTRIED`` rather than returning eligible while status
    remains INEFFECTIVE.
    """

    known_untried: List[str] = field(default_factory=list)
    attempted: List[str] = field(default_factory=list)  # ledger only
    currently_ineligible: List[str] = field(default_factory=list)
    invalidated: List[str] = field(default_factory=list)
    newly_discovered: List[str] = field(default_factory=list)
    superseded: List[str] = field(default_factory=list)
    # method_id → MethodStatus value (decision state)
    method_status: Dict[str, str] = field(default_factory=dict)
    # method_id → MethodContext.signature() under which INEFFECTIVE was recorded
    ineffective_in_world_signature: Dict[str, str] = field(default_factory=dict)
    # method_id → MethodSpec
    catalog: Dict[str, MethodSpec] = field(default_factory=dict)
    # Last method-relevant context applied via refresh_method_frontier
    active_context_signature: str = ""

    def status_of(self, method_id: str) -> str:
        return str(
            self.method_status.get(method_id) or MethodStatus.UNTRIED.value
        )

    def refresh_method_frontier(self, world: Any = "") -> List[str]:
        """Reactivate INEFFECTIVE methods when method-relevant context changes.

        ``INEFFECTIVE@contextA`` + ``contextB`` → ``UNTRIED@contextB``.
        Returns method ids that were reactivated.
        """
        ctx = MethodContext.from_any(world)
        sig = ctx.signature()
        reactivated: List[str] = []
        for mid, prior in list(self.ineffective_in_world_signature.items()):
            if self.status_of(mid) != MethodStatus.INEFFECTIVE.value:
                continue
            if prior and prior != sig:
                self.method_status[mid] = MethodStatus.UNTRIED.value
                self.ineffective_in_world_signature.pop(mid, None)
                if mid not in self.known_untried and mid not in self.newly_discovered:
                    self.known_untried.append(mid)
                reactivated.append(mid)
        self.active_context_signature = sig
        return reactivated

    def eligible_methods(self, *, world_signature: str = "") -> List[str]:
        if world_signature:
            self.refresh_method_frontier(world_signature)
        blocked = set(self.currently_ineligible)
        blocked |= set(self.invalidated) | set(self.superseded)
        out: List[str] = []
        pool = list(self.newly_discovered) + list(self.known_untried)
        # Also consider catalog methods still UNTRIED after inconclusive attempts.
        for mid in list(self.catalog.keys()):
            if mid not in pool:
                pool.append(mid)
        for mid in pool:
            if mid in blocked or mid in out:
                continue
            if mid not in self.catalog:
                continue
            st = self.status_of(mid)
            if st in {
                MethodStatus.INEFFECTIVE.value,
                MethodStatus.INVALID.value,
                MethodStatus.SUPERSEDED.value,
                MethodStatus.SUCCEEDED.value,
            }:
                continue
            out.append(mid)
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "known_untried": list(self.known_untried),
            "attempted": list(self.attempted),
            "currently_ineligible": list(self.currently_ineligible),
            "invalidated": list(self.invalidated),
            "newly_discovered": list(self.newly_discovered),
            "superseded": list(self.superseded),
            "method_status": dict(self.method_status),
            "ineffective_in_world_signature": dict(self.ineffective_in_world_signature),
            "active_context_signature": self.active_context_signature,
            "catalog": {k: v.to_dict() for k, v in self.catalog.items()},
            "eligible": self.eligible_methods(),
        }


@dataclass
class IntentionFrame:
    intention: Intention
    originating_meta_action: str = "explore"
    scoring_policy: ScoringPolicy = field(default_factory=ScoringPolicy)
    method_frontier: MethodFrontier = field(default_factory=MethodFrontier)
    attempts: List[AttemptRecord] = field(default_factory=list)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    budget: IntentionBudget = field(default_factory=IntentionBudget)
    parent_intention_id: Optional[str] = None
    child_intention_ids: List[str] = field(default_factory=list)
    suspended_by_child: bool = False
    # Explicit why suspended (not IntentionStatus.BLOCKED — that is budget).
    suspension: Optional[Dict[str, Any]] = None
    # Semantic key of the unmet required_effect this child is resolving.
    prerequisite_effect_key: str = ""
    status: str = IntentionStatus.ACTIVE.value
    termination_reason: Optional[str] = None
    opened_at: float = field(default_factory=time.time)
    perception_calls: int = 0
    methods_tried_count: int = 0
    pending_effect_verification: bool = False
    last_motivated_perceive: Dict[str, Any] = field(default_factory=dict)
    same_method_retries: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intention": self.intention.to_dict(),
            "originating_meta_action": self.originating_meta_action,
            "scoring_policy": self.scoring_policy.to_dict(),
            "method_frontier": self.method_frontier.to_dict(),
            "attempts": [a.to_dict() for a in self.attempts[-12:]],
            "retry_policy": self.retry_policy.to_dict(),
            "budget": self.budget.to_dict(),
            "parent_intention_id": self.parent_intention_id,
            "child_intention_ids": list(self.child_intention_ids),
            "suspended_by_child": self.suspended_by_child,
            "suspension": dict(self.suspension or {}) if self.suspension else None,
            "prerequisite_effect_key": self.prerequisite_effect_key,
            "status": self.status,
            "termination_reason": self.termination_reason,
            "opened_at": self.opened_at,
            "perception_calls": self.perception_calls,
            "methods_tried_count": self.methods_tried_count,
            "pending_effect_verification": self.pending_effect_verification,
            "last_motivated_perceive": dict(self.last_motivated_perceive or {}),
            "same_method_retries": dict(self.same_method_retries or {}),
        }


def new_intention_id() -> str:
    return f"i_{uuid.uuid4().hex[:10]}"


def new_attempt_id() -> str:
    return f"a_{uuid.uuid4().hex[:10]}"


def begin_attempt(
    *,
    method_id: str,
    intention_id: str = "",
    world_before: str = "",
    grounding_snapshot: str = "",
    expected_effect: str = "",
) -> AttemptRecord:
    return AttemptRecord(
        method_id=method_id,
        attempt_id=new_attempt_id(),
        intention_id=intention_id,
        world_before=world_before,
        grounding_snapshot=grounding_snapshot,
        expected_effect=expected_effect,
        attempt_validity=AttemptValidity.VALID.value,
        method_status=MethodStatus.UNTRIED.value,
    )


def close_attempt(
    attempt: AttemptRecord,
    *,
    execution_status: str = "",
    method_outcome: str = "",
    failure_class: Optional[str] = None,
    world_after: str = "",
    motor_point: Optional[Sequence[float]] = None,
    attempt_validity: Optional[str] = None,
    method_status: Optional[str] = None,
) -> AttemptRecord:
    attempt.execution_status = execution_status or attempt.execution_status
    attempt.method_outcome = method_outcome or attempt.method_outcome
    attempt.failure_class = failure_class
    attempt.world_after = world_after or attempt.world_after
    if motor_point is not None and len(motor_point) >= 2:
        attempt.motor_point = [float(motor_point[0]), float(motor_point[1])]
    if attempt_validity:
        attempt.attempt_validity = attempt_validity
    if method_status:
        attempt.method_status = method_status
    elif (
        attempt.may_mark_method_ineffective()
        and method_outcome == MethodOutcome.EFFECT_ABSENT.value
    ):
        attempt.method_status = MethodStatus.INEFFECTIVE.value
    elif attempt_validity == AttemptValidity.INCONCLUSIVE_GROUNDING.value:
        # Grounding failure must not exhaust the method.
        attempt.method_status = MethodStatus.UNTRIED.value
        attempt.failure_class = FailureClass.GROUNDING.value
    return attempt


def close_attempt_on_frame(
    frame: IntentionFrame,
    attempt: AttemptRecord,
    *,
    execution_status: str = "",
    method_outcome: str = "",
    failure_class: Optional[str] = None,
    world_after: str = "",
    motor_point: Optional[Sequence[float]] = None,
    attempt_validity: Optional[str] = None,
    world_signature: str = "",
) -> AttemptRecord:
    """Close attempt and sync MethodFrontier decision status (not just ledger)."""
    closed = close_attempt(
        attempt,
        execution_status=execution_status,
        method_outcome=method_outcome,
        failure_class=failure_class,
        world_after=world_after,
        motor_point=motor_point,
        attempt_validity=attempt_validity,
    )
    record_method_status(
        frame,
        closed.method_id,
        closed.method_status,
        world_signature=world_signature or str(closed.world_before or ""),
    )
    return closed


def score_method(
    spec: MethodSpec,
    policy: ScoringPolicy,
    *,
    attempted: bool = False,
    grounding_confidence: float = 0.7,
) -> float:
    info = 0.8 if "reveal" in spec.capability or spec.gesture else 0.4
    progress = 0.3 if "reveal" in spec.capability else 0.5
    if spec.provenance == MethodProvenance.OBSERVED.value:
        info += 0.45
        progress += 0.35
        grounding_confidence = max(grounding_confidence, 0.92)
    if spec.provenance == MethodProvenance.LLM_INFERRED.value:
        info -= 0.1
    repeat = 1.0 if attempted else 0.0
    return (
        policy.progress_weight * progress
        + policy.information_weight * info
        + policy.grounding_weight * grounding_confidence
        + policy.reversibility_weight * float(spec.reversibility)
        - policy.risk_weight * float(spec.risk)
        - policy.latency_weight * float(spec.latency)
        - policy.cost_weight * float(spec.cost)
        - policy.repeat_penalty_weight * repeat
    )


def rank_eligible(
    frame: IntentionFrame,
    *,
    demote_ids: Optional[Sequence[str]] = None,
) -> List[Tuple[str, float]]:
    frontier = frame.method_frontier
    demote = {str(x) for x in (demote_ids or ()) if str(x or "").strip()}
    ranked: List[Tuple[str, float]] = []
    for mid in frontier.eligible_methods():
        spec = frontier.catalog.get(mid)
        if spec is None:
            continue
        ranked.append(
            (
                mid,
                score_method(
                    spec,
                    frame.scoring_policy,
                    attempted=mid in frontier.attempted,
                ),
            )
        )
    # Demoted ids sort after others (architect: no blind replay after child).
    ranked.sort(key=lambda x: (x[0] in demote, -x[1]))
    return ranked


def actionable_prerequisites(frame: IntentionFrame) -> List[str]:
    """Preconditions on methods that are still decision-eligible (or waiting)."""
    out: List[str] = []
    pool = set(frame.method_frontier.eligible_methods())
    pool |= set(frame.method_frontier.currently_ineligible)
    for mid in pool:
        st = frame.method_frontier.status_of(mid)
        if st in {
            MethodStatus.INEFFECTIVE.value,
            MethodStatus.INVALID.value,
            MethodStatus.SUPERSEDED.value,
            MethodStatus.SUCCEEDED.value,
        }:
            continue
        spec = frame.method_frontier.catalog.get(mid)
        if spec is None:
            continue
        for p in spec.preconditions:
            t = str(p or "").strip()
            if t and t not in out:
                out.append(t)
    return out


def budget_exhausted(frame: IntentionFrame, *, now: Optional[float] = None) -> bool:
    t = float(now if now is not None else time.time())
    if frame.methods_tried_count >= int(frame.budget.max_methods):
        return True
    if frame.perception_calls >= int(frame.budget.max_perception_calls):
        return True
    if (t - float(frame.opened_at or t)) >= float(frame.budget.max_wall_time_s):
        return True
    return False


def is_local_route_exhausted(frame: IntentionFrame) -> bool:
    """Derived invariant — do not assign exhausted arbitrarily."""
    if frame.pending_effect_verification:
        return False
    if frame.method_frontier.eligible_methods():
        return False
    if actionable_prerequisites(frame):
        return False
    # Still have newly_discovered pending catalogization?
    for mid in frame.method_frontier.newly_discovered:
        if mid in frame.method_frontier.catalog and mid not in set(
            frame.method_frontier.attempted
        ) | set(frame.method_frontier.invalidated) | set(
            frame.method_frontier.superseded
        ):
            return False
    return True


def evaluate_intention_success(
    frame: IntentionFrame,
    *,
    world: Optional[Dict[str, Any]] = None,
    affordance_stance: str = "",
    grounded_forward: bool = False,
) -> bool:
    """Re-evaluate success_predicate after every world update (before next method)."""
    pred = str(frame.intention.success_predicate or "").strip().lower()
    stance = str(affordance_stance or "").strip().lower()
    doc = world if isinstance(world, dict) else {}
    surface = str(doc.get("surface") or "").strip().lower()
    if pred in {
        "forward_affordance_grounded",
        "usable_forwarding_route_discovered",
        "a grounded forwarding route is discovered",
    }:
        if grounded_forward or stance == "act_clear":
            return True
        if surface in {"context_menu", "action_menu", "selection_mode", "forward_picker"}:
            # Surface alone is not enough — need Forward-ish control when possible.
            objs = doc.get("objects") or []
            for o in objs if isinstance(objs, list) else []:
                if not isinstance(o, dict):
                    continue
                text = str(o.get("text") or o.get("label") or "").strip().lower()
                if text in {"forward", "share"} or "forward" in text:
                    return True
            # selection_mode / menu with act_clear handled above
            if stance == "act_clear":
                return True
        return False
    if pred == "message_action_surface_visible":
        return surface in {"context_menu", "action_menu", "selection_mode"}
    if pred == "source_object_selected":
        if bool(doc.get("source_object_selected")):
            return True
        if surface == "selection_mode":
            return True
        return False
    # Effect-keyed child success predicates (storage / operational / stubs).
    if pred.startswith("storage:available_bytes_at_least") or pred == "free_storage_satisfied":
        from plugin.agent.executive.blocking import (
            EffectPredicate,
            evaluate_effect_predicate,
        )

        # Prefer structured world facts over capability self-claim.
        if ":" in pred and pred != "free_storage_satisfied":
            # storage:available_bytes_at_least:N
            parts = pred.split(":")
            need = int(parts[2]) if len(parts) >= 3 and str(parts[2]).isdigit() else 0
            return evaluate_effect_predicate(
                EffectPredicate(
                    subject="storage",
                    relation="available_bytes_at_least",
                    value=need,
                ),
                world=doc,
            )
        return bool(doc.get("free_storage_satisfied")) or evaluate_effect_predicate(
            EffectPredicate(subject="storage", relation="available_bytes_at_least", value=0),
            world=doc,
        )
    if pred in {"app_operational:is_true", "app_operational"}:
        from plugin.agent.executive.blocking import (
            EffectPredicate,
            evaluate_effect_predicate,
        )

        return evaluate_effect_predicate(
            EffectPredicate(subject="app_operational", relation="is_true", value=True),
            world=doc,
        )
    return False


def method_preconditions_met(
    spec: MethodSpec,
    *,
    world: Optional[Dict[str, Any]] = None,
    predicates: Optional[Dict[str, Any]] = None,
) -> bool:
    """True when every named precondition holds in world/predicates."""
    preds = predicates if isinstance(predicates, dict) else {}
    doc = world if isinstance(world, dict) else {}
    for p in spec.preconditions or []:
        key = str(p or "").strip()
        if not key:
            continue
        if key == "source_object_selected":
            if bool(preds.get("source_object_selected")) or bool(
                doc.get("source_object_selected")
            ):
                continue
            if str(doc.get("surface") or "").strip().lower() == "selection_mode":
                continue
            return False
        if key in preds and not bool(preds.get(key)):
            return False
        if key in doc and not bool(doc.get(key)):
            return False
    return True


def mark_method_ineligible(frame: IntentionFrame, method_id: str) -> None:
    mid = str(method_id or "").strip()
    if not mid:
        return
    fr = frame.method_frontier
    if mid not in fr.currently_ineligible:
        fr.currently_ineligible.append(mid)
    fr.known_untried = [x for x in fr.known_untried if x != mid]
    fr.newly_discovered = [x for x in fr.newly_discovered if x != mid]


def clear_method_ineligible(frame: IntentionFrame, method_id: str) -> None:
    mid = str(method_id or "").strip()
    if not mid:
        return
    fr = frame.method_frontier
    fr.currently_ineligible = [x for x in fr.currently_ineligible if x != mid]
    if (
        mid in fr.catalog
        and mid not in fr.attempted
        and mid not in fr.known_untried
        and mid not in fr.newly_discovered
    ):
        fr.known_untried.append(mid)


def seed_select_referent_child(
    *,
    parent_intention_id: str,
    target_binding: str = "source_object",
) -> IntentionFrame:
    """Child EXPLORE/ACT frame: satisfy source_object_selected for a parent method."""
    intention = Intention(
        id=new_intention_id(),
        objective="Select the bound source message so parent methods can proceed",
        success_predicate="source_object_selected",
        scope=f"{target_binding} selection",
        created_from=IntentionOrigin(
            kind="prerequisite",
            parent_goal_id=str(parent_intention_id or "")[:64],
            triggering_uncertainty="source_object_not_selected",
        ),
    )
    mid = "select_then_toolbar"
    catalog = {
        mid: MethodSpec(
            id=mid,
            capability="select_content",
            target_binding=target_binding,
            expected_effect=EffectSpec(
                success_any=["source_object_selected"],
                settle_window_ms=800,
            ),
            retry_safety=RetrySafety.SAFE_TO_RETRY.value,
            provenance=MethodProvenance.GENERIC_PRIOR.value,
            reversibility=0.9,
            risk=0.05,
        )
    }
    frontier = MethodFrontier(known_untried=[mid], catalog=catalog)
    return IntentionFrame(
        intention=intention,
        originating_meta_action="act",
        scoring_policy=ScoringPolicy.for_meta("act"),
        method_frontier=frontier,
        retry_policy=RetryPolicy(same_method_max=1, try_alternatives=False),
        budget=IntentionBudget(
            max_methods=2, max_wall_time_s=20.0, max_perception_calls=4
        ),
        parent_intention_id=str(parent_intention_id or "") or None,
    )


def spawn_child_for_precondition(
    state: Any,
    parent: IntentionFrame,
    *,
    blocked_method_id: str,
    precondition: str = "source_object_selected",
) -> Optional[IntentionFrame]:
    """Suspend parent under child prereq; parent method stays ineligible, not attempted."""
    if state is None or parent is None:
        return None
    if parent.suspended_by_child:
        # Child already on stack.
        child = active_intention_frame(state)
        if child is not None and child.intention.id != parent.intention.id:
            return child
    mark_method_ineligible(parent, blocked_method_id)
    blocked_spec = parent.method_frontier.catalog.get(blocked_method_id)
    bind = "source_object"
    if blocked_spec is not None and blocked_spec.target_binding:
        bind = str(blocked_spec.target_binding)
    child = seed_select_referent_child(
        parent_intention_id=parent.intention.id,
        target_binding=bind,
    )
    child.prerequisite_effect_key = str(precondition or "source_object_selected")
    parent.suspended_by_child = True
    parent.suspension = {
        "reason": "unsatisfied_prerequisite",
        "child_intention_id": child.intention.id,
        "blocking_condition_id": "",
        "precondition_key": str(precondition or "source_object_selected"),
    }
    parent.child_intention_ids.append(child.intention.id)
    # Tag parent attempt ledger with the prereq miss (not a method attempt).
    parent.attempts.append(
        AttemptRecord(
            method_id=str(blocked_method_id),
            execution_status="not_executed",
            observation_quality=1.0,
            method_outcome=MethodOutcome.EFFECT_ABSENT.value,
            failure_class=FailureClass.PRECONDITION_MISSING.value,
            evidence_refs=[f"precondition_missing:{precondition}"],
        )
    )
    replace_active_frame(state, parent)
    push_intention_frame(state, child)
    return child


def seed_prerequisite_child(
    *,
    parent_intention_id: str,
    effect_key: str,
    success_predicate: str,
    objective: str,
    methods: Sequence[Tuple[str, str]],
    blocking_condition_id: str = "",
) -> IntentionFrame:
    """Generic child whose success_predicate is judged from world evidence."""
    intention = Intention(
        id=new_intention_id(),
        objective=str(objective or f"Satisfy prerequisite {effect_key}")[:200],
        success_predicate=str(success_predicate or effect_key),
        scope=str(effect_key or "")[:120],
        created_from=IntentionOrigin(
            kind="prerequisite",
            parent_goal_id=str(parent_intention_id or "")[:64],
            triggering_uncertainty=str(effect_key or "")[:80],
        ),
    )
    catalog: Dict[str, MethodSpec] = {}
    known: List[str] = []
    for i, (cap, mid) in enumerate(methods):
        method_id = str(mid or f"{cap}_{i}").strip() or f"m_{i}"
        catalog[method_id] = MethodSpec(
            id=method_id,
            capability=str(cap),
            expected_effect=EffectSpec(success_any=[str(success_predicate or effect_key)]),
            retry_safety=RetrySafety.SAFE_TO_RETRY.value,
            provenance=MethodProvenance.GENERIC_PRIOR.value,
            reversibility=0.85,
            risk=0.05,
        )
        known.append(method_id)
    frontier = MethodFrontier(known_untried=known, catalog=catalog)
    frame = IntentionFrame(
        intention=intention,
        originating_meta_action="act",
        scoring_policy=ScoringPolicy.for_meta("act"),
        method_frontier=frontier,
        retry_policy=RetryPolicy(same_method_max=1, try_alternatives=True),
        budget=IntentionBudget(
            max_methods=max(2, len(known)), max_wall_time_s=45.0, max_perception_calls=6
        ),
        parent_intention_id=str(parent_intention_id or "") or None,
        prerequisite_effect_key=str(effect_key or ""),
    )
    return frame


def ensure_child_for_precondition(
    state: Any,
    parent: IntentionFrame,
    *,
    effect_key: str,
    success_predicate: str = "",
    objective: str = "",
    methods: Optional[Sequence[Tuple[str, str]]] = None,
    blocking_condition_id: str = "",
) -> Optional[IntentionFrame]:
    """Ensure one child for a semantic prerequisite; dedupe by effect_key.

    Two observations of the same unmet predicate must not spawn two children.
    """
    if state is None or parent is None:
        return None
    key = str(effect_key or "").strip()
    if not key:
        return None
    # Dedupe: existing child on stack with same semantic key.
    for frame in intention_stack_of(state):
        if (
            frame.parent_intention_id == parent.intention.id
            and str(frame.prerequisite_effect_key or "") == key
            and frame.status == IntentionStatus.ACTIVE.value
        ):
            return frame
    if parent.suspended_by_child:
        child = active_intention_frame(state)
        if (
            child is not None
            and child.intention.id != parent.intention.id
            and str(child.prerequisite_effect_key or "") == key
        ):
            return child

    method_pairs = list(methods or [])
    if not method_pairs:
        from plugin.agent.executive.blocking import (
            EffectPredicate,
            resolve_methods_for_effect,
        )

        parts = key.split(":")
        pred = EffectPredicate(
            subject=parts[0] if parts else "",
            relation=parts[1] if len(parts) > 1 else "is_true",
            value=int(parts[2]) if len(parts) > 2 and str(parts[2]).isdigit() else True,
        )
        resolved = resolve_methods_for_effect(
            pred, facts={"agent_owned_reclaimable_bytes": 1, "blocked_app_recoverable": True}
        )
        method_pairs = [(m.capability, m.capability) for m in resolved]
    if not method_pairs:
        return None

    child = seed_prerequisite_child(
        parent_intention_id=parent.intention.id,
        effect_key=key,
        success_predicate=str(success_predicate or key),
        objective=objective or f"Resolve prerequisite {key}",
        methods=method_pairs,
        blocking_condition_id=blocking_condition_id,
    )
    parent.suspended_by_child = True
    parent.suspension = {
        "reason": "unsatisfied_prerequisite",
        "child_intention_id": child.intention.id,
        "blocking_condition_id": str(blocking_condition_id or ""),
        "precondition_key": key,
    }
    if child.intention.id not in parent.child_intention_ids:
        parent.child_intention_ids.append(child.intention.id)
    parent.attempts.append(
        AttemptRecord(
            method_id="",
            execution_status="not_executed",
            observation_quality=1.0,
            method_outcome=MethodOutcome.EFFECT_ABSENT.value,
            failure_class=FailureClass.PRECONDITION_MISSING.value,
            evidence_refs=[f"precondition_missing:{key}"],
        )
    )
    replace_active_frame(state, parent)
    push_intention_frame(state, child)
    return child


def resume_parent_after_child(
    state: Any,
    *,
    world: Optional[Dict[str, Any]] = None,
    affordance_stance: str = "",
    grounded_forward: bool = False,
    facts: Optional[Dict[str, Any]] = None,
    parent_blockers: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """On child ACHIEVED: recheck parent executability before resume.

    Child success triggers re-evaluation — not automatic resume. If the parent
    goal is already complete, do not resume obsolete work. If parent is still
    blocked on another resolvable prereq, leave that for the caller to spawn.
    """
    status: Dict[str, Any] = {"resumed": False}
    child = active_intention_frame(state)
    if child is None or not child.parent_intention_id:
        return status
    if not evaluate_intention_success(
        child, world=world, affordance_stance=affordance_stance
    ):
        status["child_still_active"] = child.intention.id
        status["child_effect_met"] = False
        return status
    status["child_effect_met"] = True
    child.status = IntentionStatus.ACHIEVED.value
    child.termination_reason = TerminationReason.SUCCESS.value
    status["child_achieved"] = child.intention.id
    pop_intention_frame(state)
    parent = active_intention_frame(state)
    if parent is None or parent.intention.id != child.parent_intention_id:
        # Recover parent from stack scan.
        for frame in reversed(intention_stack_of(state)):
            if frame.intention.id == child.parent_intention_id:
                parent = frame
                break
    if parent is None:
        status["parent_missing"] = True
        return status

    # Parent already done while child was running → do not resume obsolete work.
    if evaluate_intention_success(
        parent,
        world=world,
        affordance_stance=affordance_stance,
        grounded_forward=grounded_forward,
    ):
        parent.suspended_by_child = False
        parent.suspension = None
        parent.status = IntentionStatus.ACHIEVED.value
        parent.termination_reason = TerminationReason.SUCCESS.value
        status["parent_achieved"] = parent.intention.id
        status["resumed"] = False
        status["obsolete_parent"] = True
        pop_intention_frame(state)
        return status

    # Recheck parent executability before clearing suspension / resuming.
    from plugin.agent.executive.blocking import (
        ExecutabilityStatus,
        assess_executability,
    )

    assessment = assess_executability(
        intention_id=parent.intention.id,
        blockers=list(parent_blockers or []),
        world=world if isinstance(world, dict) else {},
        facts=facts if isinstance(facts, dict) else {},
    )
    status["parent_executability"] = assessment.to_dict()
    if assessment.status != ExecutabilityStatus.EXECUTABLE.value:
        # Keep parent suspended conceptually until caller handles next prereq,
        # but clear child link so a new child can be ensured.
        parent.suspended_by_child = False
        parent.suspension = None
        replace_active_frame(state, parent)
        status["resumed"] = False
        status["parent_still_blocked"] = True
        status["parent_id"] = parent.intention.id
        return status

    parent.suspended_by_child = False
    parent.suspension = None
    # Re-enable methods that were only blocked on this prereq.
    for mid in list(parent.method_frontier.currently_ineligible):
        spec = parent.method_frontier.catalog.get(mid)
        if spec is None:
            continue
        if method_preconditions_met(spec, world=world):
            clear_method_ineligible(parent, mid)
    apply_derived_status(parent)
    replace_active_frame(state, parent)
    demote = [
        str(a.method_id)
        for a in parent.attempts
        if str(a.failure_class or "") == FailureClass.PRECONDITION_MISSING.value
        and str(a.method_id or "").strip()
    ]
    ranked = rank_eligible(parent, demote_ids=demote)
    status["resumed"] = True
    status["parent_id"] = parent.intention.id
    status["rerank"] = [m for m, _ in ranked]
    status["next_method"] = ranked[0][0] if ranked else None
    status["demoted"] = list(demote)
    motivated_perceive_packet(
        parent,
        purpose="revalidate_after_child",
        question="After prerequisite, what methods are now viable?",
        focus="task_surface",
    )
    parent.pending_effect_verification = False
    return status


def ensure_prereq_child_or_next_method(
    state: Any,
    frame: IntentionFrame,
    *,
    world: Optional[Dict[str, Any]] = None,
    predicates: Optional[Dict[str, Any]] = None,
) -> Optional[MethodSpec]:
    """Pick next method; spawn child when top-ranked method lacks preconditions."""
    if frame.suspended_by_child:
        child = active_intention_frame(state)
        if child is not None and child.intention.id != frame.intention.id:
            return next_reveal_method(child)
    ranked = rank_eligible(frame)
    for mid, _score in ranked:
        spec = frame.method_frontier.catalog.get(mid)
        if spec is None:
            continue
        if method_preconditions_met(spec, world=world, predicates=predicates):
            return spec
        # First unmet → spawn child for that precondition (v1: select only).
        if "source_object_selected" in (spec.preconditions or []):
            child = spawn_child_for_precondition(
                state,
                frame,
                blocked_method_id=mid,
                precondition="source_object_selected",
            )
            if child is not None:
                return next_reveal_method(child)
        mark_method_ineligible(frame, mid)
    apply_derived_status(frame)
    return None


def classify_method_outcome(
    *,
    execution_ok: bool,
    observation_quality: float,
    effect_present: bool,
    unexpected: bool = False,
) -> Tuple[str, Optional[str]]:
    """Return (method_outcome, failure_class)."""
    if unexpected:
        return MethodOutcome.UNEXPECTED_EFFECT.value, FailureClass.UNEXPECTED_WORLD.value
    if not execution_ok:
        return MethodOutcome.EFFECT_ABSENT.value, FailureClass.TRANSIENT.value
    if float(observation_quality) < 0.55:
        return MethodOutcome.EFFECT_UNCERTAIN.value, FailureClass.EFFECT_UNCERTAIN.value
    if effect_present:
        return MethodOutcome.EFFECT_OBSERVED.value, None
    return MethodOutcome.EFFECT_ABSENT.value, FailureClass.METHOD_INEFFECTIVE.value


def mark_method_attempted(frame: IntentionFrame, method_id: str) -> None:
    """Record an attempt in the ledger. Does not change eligibility by itself."""
    mid = str(method_id or "").strip()
    if not mid:
        return
    fr = frame.method_frontier
    if mid not in fr.attempted:
        fr.attempted.append(mid)
    # Keep known_untried / newly_discovered so inconclusive attempts stay eligible.
    # Status updates happen in ``record_method_status`` / ``close_attempt``.
    frame.methods_tried_count = len(fr.attempted)


def record_method_status(
    frame: IntentionFrame,
    method_id: str,
    status: str,
    *,
    world_signature: str = "",
    method_context: Any = None,
) -> None:
    """Update decision-state MethodStatus (orthogonal to attempt ledger)."""
    mid = str(method_id or "").strip()
    if not mid:
        return
    fr = frame.method_frontier
    fr.method_status[mid] = str(status or MethodStatus.UNTRIED.value)
    if status == MethodStatus.INEFFECTIVE.value:
        ctx = MethodContext.from_any(method_context if method_context is not None else world_signature)
        sig = ctx.signature()
        if sig:
            fr.ineffective_in_world_signature[mid] = sig
            fr.active_context_signature = sig
    if status == MethodStatus.UNTRIED.value:
        if mid not in fr.known_untried and mid not in fr.newly_discovered:
            fr.known_untried.append(mid)


def recommend_recovery(
    frame: IntentionFrame,
    *,
    failure_class: Optional[str],
    method_outcome: str,
) -> str:
    if budget_exhausted(frame):
        return RecoveryAction.RETURN_TO_EXECUTIVE.value
    if failure_class == FailureClass.UNEXPECTED_WORLD.value:
        return RecoveryAction.RETURN_TO_EXECUTIVE.value
    if failure_class == FailureClass.PRECONDITION_MISSING.value:
        return RecoveryAction.SPAWN_CHILD_INTENTION.value
    if failure_class == FailureClass.EFFECT_UNCERTAIN.value:
        return RecoveryAction.CONTINUE_INTENTION.value  # motivated perceive
    if failure_class == FailureClass.GROUNDING.value:
        return RecoveryAction.CONTINUE_INTENTION.value
    if is_local_route_exhausted(frame):
        return RecoveryAction.RETURN_TO_EXECUTIVE.value
    if method_outcome == MethodOutcome.EFFECT_ABSENT.value:
        return RecoveryAction.CONTINUE_INTENTION.value
    return RecoveryAction.CONTINUE_INTENTION.value


def apply_derived_status(frame: IntentionFrame) -> IntentionFrame:
    """Update status/termination_reason from invariants (not arbitrary writes)."""
    if frame.status in {
        IntentionStatus.ACHIEVED.value,
        IntentionStatus.SUPERSEDED.value,
    }:
        return frame
    if budget_exhausted(frame):
        frame.status = IntentionStatus.BLOCKED.value
        frame.termination_reason = TerminationReason.BUDGET_EXHAUSTED.value
        return frame
    if is_local_route_exhausted(frame):
        frame.status = IntentionStatus.EXHAUSTED.value
        frame.termination_reason = TerminationReason.LOCAL_ROUTE_EXHAUSTED.value
        return frame
    frame.status = IntentionStatus.ACTIVE.value
    return frame


# --- stack helpers on ExecutionState-like objects ---------------------------------


def intention_stack_of(state: Any) -> List[IntentionFrame]:
    stack = getattr(state, "intention_stack", None)
    if not isinstance(stack, list):
        return []
    return [f for f in stack if isinstance(f, IntentionFrame)]


def active_intention_frame(state: Any) -> Optional[IntentionFrame]:
    stack = intention_stack_of(state)
    return stack[-1] if stack else None


def push_intention_frame(state: Any, frame: IntentionFrame) -> None:
    if state is None:
        return
    stack = list(intention_stack_of(state))
    stack.append(frame)
    state.intention_stack = stack


def pop_intention_frame(state: Any) -> Optional[IntentionFrame]:
    if state is None:
        return None
    stack = list(intention_stack_of(state))
    if not stack:
        return None
    top = stack.pop()
    state.intention_stack = stack
    return top


def replace_active_frame(state: Any, frame: IntentionFrame) -> None:
    if state is None:
        return
    stack = list(intention_stack_of(state))
    if not stack:
        state.intention_stack = [frame]
        return
    stack[-1] = frame
    state.intention_stack = stack


def seed_reveal_explore_frame(
    *,
    target_binding: str = "source_object",
    parent_goal_id: str = "",
    triggering_uncertainty: str = "forward_affordance_not_grounded",
) -> IntentionFrame:
    """Open an EXPLORE IntentionFrame for discovering a message forwarding route."""
    intention = Intention(
        id=new_intention_id(),
        objective="Find a usable way to forward the bound message",
        success_predicate="forward_affordance_grounded",
        scope=f"{target_binding} within current conversation",
        created_from=IntentionOrigin(
            kind="executive_decision",
            parent_goal_id=str(parent_goal_id or "")[:64],
            triggering_uncertainty=str(triggering_uncertainty or "")[:80],
        ),
    )
    catalog: Dict[str, MethodSpec] = {}
    order: List[str] = []
    for mid, capability, gesture, provenance in (
        (
            "reveal_context_click",
            "reveal_actions",
            "context_click",
            MethodProvenance.GENERIC_PRIOR.value,
        ),
        (
            "reveal_hover",
            "reveal_actions",
            "hover",
            MethodProvenance.GENERIC_PRIOR.value,
        ),
        (
            "select_then_toolbar",
            "select_content",
            "",
            MethodProvenance.GENERIC_PRIOR.value,
        ),
    ):
        catalog[mid] = MethodSpec(
            id=mid,
            capability=capability,
            target_binding=target_binding,
            preconditions=(
                ["source_object_selected"] if mid == "reveal_hover" else []
            ),
            expected_effect=EffectSpec(
                success_any=[
                    "message_action_surface_visible",
                    "forward_affordance_grounded",
                ],
                settle_window_ms=1200,
            ),
            retry_safety=RetrySafety.SAFE_TO_RETRY.value,
            provenance=provenance,
            gesture=gesture,
            reversibility=0.95,
            risk=0.05,
        )
        order.append(mid)
    frontier = MethodFrontier(known_untried=list(order), catalog=catalog)
    return IntentionFrame(
        intention=intention,
        originating_meta_action="explore",
        scoring_policy=ScoringPolicy.for_meta("explore"),
        method_frontier=frontier,
        retry_policy=RetryPolicy(same_method_max=1, try_alternatives=True),
        budget=IntentionBudget(
            max_methods=5, max_wall_time_s=45.0, max_perception_calls=8
        ),
    )


def next_reveal_method(frame: IntentionFrame) -> Optional[MethodSpec]:
    ranked = rank_eligible(frame)
    if not ranked:
        return None
    mid = ranked[0][0]
    return frame.method_frontier.catalog.get(mid)


def motivated_perceive_packet(
    frame: IntentionFrame,
    *,
    purpose: str,
    question: str,
    focus: str = "source_message_neighborhood",
) -> Dict[str, Any]:
    packet = {
        "purpose": str(purpose or "effect_verification")[:40],
        "question": str(question or "")[:200],
        "focus": str(focus or "")[:80],
        "intention_id": frame.intention.id,
    }
    frame.last_motivated_perceive = dict(packet)
    frame.perception_calls = int(frame.perception_calls or 0) + 1
    return packet
