"""Warning / Precondition / BlockingCondition — prerequisite interruption substrate.

Authority boundary:
  Precondition = what an intention needs to be true
  BlockingCondition = scoped evidence that a precondition is currently false
  Warning = observed info that must not interrupt by itself

Capability executes and returns evidence; IntentionFrame judges success_predicate.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple
import uuid


class BlockerLifecycle(str, Enum):
    DETECTED = "detected"
    CONFIRMED = "confirmed"
    RESOLVING = "resolving"
    RESOLVED = "resolved"
    STALE = "stale"


class ResolutionAttemptOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EFFECT_UNMET = "effect_unmet"
    INCONCLUSIVE = "inconclusive"


class ExecutabilityStatus(str, Enum):
    EXECUTABLE = "executable"
    BLOCKED_RESOLVABLE = "blocked_resolvable"
    BLOCKED_UNRESOLVABLE = "blocked_unresolvable"
    UNKNOWN = "unknown"


class Reclaimability(str, Enum):
    GUARANTEED = "guaranteed"
    LIKELY = "likely"
    UNKNOWN = "unknown"


@dataclass
class IntentionRef:
    """Reference to an intention that a blocker may scope to."""

    intention_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"intention_id": self.intention_id}


@dataclass
class HostResource:
    kind: str = ""  # storage | network | auth | permission | dependency

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind}

    def __str__(self) -> str:
        return self.kind


@dataclass
class EffectPredicate:
    """Semantic center for resolution — not a free-text kind switch."""

    subject: str = ""  # e.g. storage | app_operational
    relation: str = ""  # available_bytes_at_least | is_true | ...
    value: Any = None

    def semantic_key(self) -> str:
        """Stable identity for child dedupe (not blocker observation id)."""
        subj = str(self.subject or "").strip().lower()
        rel = str(self.relation or "").strip().lower()
        val = self.value
        if isinstance(val, (int, float)):
            # Bucket large byte thresholds so dialog+df map to one child.
            return f"{subj}:{rel}:{int(val)}"
        return f"{subj}:{rel}:{str(val).strip().lower()}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject": self.subject,
            "relation": self.relation,
            "value": self.value,
            "semantic_key": self.semantic_key(),
        }


@dataclass
class Warning:
    """Observed information — must not interrupt a task by itself."""

    kind: str = ""
    severity: str = "info"
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Precondition:
    """Belongs to an intention: what must be true for it to proceed."""

    predicate: EffectPredicate = field(default_factory=EffectPredicate)
    required: bool = True

    def semantic_key(self) -> str:
        return self.predicate.semantic_key()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "predicate": self.predicate.to_dict(),
            "required": self.required,
        }


@dataclass
class BlockingCondition:
    """Scoped evidence that a precondition is currently false."""

    id: str = ""
    required_effect: EffectPredicate = field(default_factory=EffectPredicate)
    blocks: List[IntentionRef] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)
    suggested_method_from_environment: str = ""
    lifecycle: str = BlockerLifecycle.DETECTED.value
    kind: str = ""  # label only — not a behavior switch

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"bc_{uuid.uuid4().hex[:10]}"

    def semantic_key(self) -> str:
        return self.required_effect.semantic_key()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "required_effect": self.required_effect.to_dict(),
            "blocks": [b.to_dict() for b in self.blocks],
            "evidence": list(self.evidence)[:8],
            "provenance": dict(self.provenance),
            "suggested_method_from_environment": self.suggested_method_from_environment,
            "lifecycle": self.lifecycle,
        }


@dataclass
class Suspension:
    """Why a parent is suspended_by_child (not IntentionStatus.BLOCKED)."""

    reason: str = "unsatisfied_prerequisite"
    child_intention_id: str = ""
    blocking_condition_id: str = ""
    precondition_key: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutabilityAssessment:
    status: str = ExecutabilityStatus.EXECUTABLE.value
    unmet_preconditions: List[Precondition] = field(default_factory=list)
    blocking_conditions: List[BlockingCondition] = field(default_factory=list)
    resolvable_conditions: List[BlockingCondition] = field(default_factory=list)
    reason: str = ""

    @property
    def executable(self) -> bool:
        return self.status == ExecutabilityStatus.EXECUTABLE.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "unmet_preconditions": [p.to_dict() for p in self.unmet_preconditions],
            "blocking_conditions": [b.to_dict() for b in self.blocking_conditions],
            "resolvable_conditions": [b.to_dict() for b in self.resolvable_conditions],
            "reason": self.reason,
        }


@dataclass
class ResolvedMethod:
    capability: str
    applicable_if: str = ""
    effect_key: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ResourceCandidate:
    path: str = ""
    owner: str = "unknown"  # agent | system | user
    persistence: str = "unknown"  # ephemeral | cache | durable
    regenerable: bool = False
    deletion_risk: str = "unknown"
    reclaimability: str = Reclaimability.UNKNOWN.value

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --- Effect → methods (applicability-aware; not a hard switchboard) ----------


_EFFECT_METHODS: Dict[str, List[ResolvedMethod]] = {
    "storage:available_bytes_at_least": [
        ResolvedMethod(
            capability="relieve_host_storage",
            applicable_if="agent_owned_reclaimable_bytes > 0",
            effect_key="storage:available_bytes_at_least",
        )
    ],
    "app_operational:is_true": [
        ResolvedMethod(
            capability="recover_blocked_app",
            applicable_if="blocked_app_recoverable",
            effect_key="app_operational:is_true",
        )
    ],
    # Golden stubs — not wired to live actuators yet.
    "authenticated:is_true": [
        ResolvedMethod(capability="authenticate", applicable_if="auth_flow_available")
    ],
    "permission_granted:is_true": [
        ResolvedMethod(capability="obtain_permission", applicable_if="permission_prompt_available")
    ],
    "dependency_present:is_true": [
        ResolvedMethod(capability="install_dependency", applicable_if="dependency_installable")
    ],
}


def resolve_methods_for_effect(
    effect: EffectPredicate,
    *,
    facts: Optional[Dict[str, Any]] = None,
) -> List[ResolvedMethod]:
    """Return applicable candidate methods for a required effect."""
    facts = facts if isinstance(facts, dict) else {}
    prefix = f"{str(effect.subject or '').strip().lower()}:{str(effect.relation or '').strip().lower()}"
    candidates = list(_EFFECT_METHODS.get(prefix) or [])
    out: List[ResolvedMethod] = []
    for m in candidates:
        if _applicable(m.applicable_if, facts):
            out.append(m)
    return out


def _applicable(clause: str, facts: Dict[str, Any]) -> bool:
    c = str(clause or "").strip()
    if not c:
        return True
    if c == "agent_owned_reclaimable_bytes > 0":
        return float(facts.get("agent_owned_reclaimable_bytes") or 0) > 0
    if c == "blocked_app_recoverable":
        return bool(facts.get("blocked_app_recoverable", True))
    if c.endswith("_available") or c.endswith("_installable"):
        # Stubs default True in tests when fact absent.
        return bool(facts.get(c, True))
    return True


# Methods that must never auto-run from an effect resolver (user/system danger).
_FORBIDDEN_AUTO_CAPABILITIES = frozenset(
    {
        "delete_user_documents",
        "delete_user_files",
        "wipe_user_data",
        "navigate_system_settings_blind",
        "open_system_settings_storage_blind",
    }
)


def rank_resolution_plan(
    effect: EffectPredicate,
    *,
    resources: Sequence[ResourceCandidate] = (),
    facts: Optional[Dict[str, Any]] = None,
    offered_capabilities: Sequence[str] = (),
) -> Dict[str, Any]:
    """General effect→method policy: prefer safe agent-owned reclaim.

    Returns ranked applicable methods plus explicit forbidden auto-methods.
    Does not invent WhatsApp-specific switchboards — ownership/reclaimability
    of ResourceCandidate drives ranking.
    """
    facts = dict(facts or {})
    # Derive reclaimable bytes from resource inventory when not stamped.
    if "agent_owned_reclaimable_bytes" not in facts:
        agent_bytes = 0
        for r in resources or []:
            if str(getattr(r, "owner", "") or "").lower() == "agent":
                if str(getattr(r, "reclaimability", "") or "") in {
                    Reclaimability.GUARANTEED.value,
                    Reclaimability.LIKELY.value,
                }:
                    agent_bytes += 1  # presence signal; magnitude from facts if known
        if agent_bytes and float(facts.get("agent_owned_reclaimable_bytes") or 0) <= 0:
            facts["agent_owned_reclaimable_bytes"] = float(
                facts.get("agent_owned_ephemeral_bytes") or agent_bytes
            )

    applicable = resolve_methods_for_effect(effect, facts=facts)
    ranked = [m.capability for m in applicable]

    forbidden: List[str] = []
    for cap in offered_capabilities or []:
        name = str(cap or "").strip()
        if name in _FORBIDDEN_AUTO_CAPABILITIES:
            forbidden.append(name)
    # User-document reclaim is never auto-ranked above agent ephemeral.
    has_agent = any(
        str(getattr(r, "owner", "") or "").lower() == "agent"
        and str(getattr(r, "reclaimability", "") or "")
        in {Reclaimability.GUARANTEED.value, Reclaimability.LIKELY.value}
        for r in (resources or [])
    )
    has_user_only = any(
        str(getattr(r, "owner", "") or "").lower() == "user" for r in (resources or [])
    )
    if has_user_only and not has_agent:
        # No safe auto method — leave ranked empty / ASK path.
        forbidden.append("delete_user_documents")

    return {
        "ranked_capabilities": ranked,
        "forbidden_auto": sorted(set(forbidden)),
        "has_safe_agent_reclaim": bool(has_agent and ranked),
        "effect_key": effect.semantic_key(),
    }


# --- Detection: progress blocker vs mere warning ------------------------------


_STORAGE_CANNOT_CONTINUE = re.compile(
    r"(storage is too full|free up at least|to keep using .{0,40}free up|"
    r"insufficient storage|not enough storage|disk (is )?full)",
    re.I,
)
_STORAGE_MB_ASK = re.compile(
    r"free up at least\s+([0-9]+(?:\.[0-9]+)?)\s*(mb|gb|mib|gib)",
    re.I,
)
_STORAGE_WEAK_WARNING = re.compile(
    r"(storage almost full|low (on )?storage|running out of space|"
    r"disk space is low|storage getting full)",
    re.I,
)


def _bytes_from_ask(amount: float, unit: str) -> int:
    u = unit.lower()
    if u in {"gb", "gib"}:
        return int(amount * (1024**3))
    return int(amount * (1024**2))


def detect_warnings_and_blockers(
    *,
    observation_texts: Sequence[str] = (),
    view: Optional[Dict[str, Any]] = None,
    features: Optional[Dict[str, Any]] = None,
    intention_id: str = "",
    app: str = "",
) -> Tuple[List[Warning], List[BlockingCondition]]:
    """Split mere warnings from intention-scoped progress blockers.

    High-confidence storage blocker requires inability-to-continue language
    and/or a quantified reclaim ask on a blocking dialog surface — not keyword
    "storage" alone.
    """
    view = view if isinstance(view, dict) else {}
    extras: Dict[str, Any] = {}
    if features is not None:
        if hasattr(features, "extras") and isinstance(features.extras, dict):
            extras = dict(features.extras)
        elif isinstance(features, dict):
            extras = dict(features.get("extras") or features)

    texts: List[str] = []
    for t in observation_texts or []:
        if str(t).strip():
            texts.append(str(t).strip())
    for w in extras.get("system_warnings") or view.get("system_warnings") or []:
        if str(w).strip():
            texts.append(str(w).strip())
    for d in extras.get("dialogs") or view.get("dialogs") or []:
        if str(d).strip():
            texts.append(str(d).strip())
    blob = "\n".join(texts)

    warnings: List[Warning] = []
    blockers: List[BlockingCondition] = []

    screen = str(
        extras.get("screen_kind") or view.get("screen") or extras.get("wa_screen") or ""
    ).strip().lower()
    dialog_like = screen in {"dialog", "modal"} or bool(extras.get("has_dialog"))
    storage_pressure_flag = bool(extras.get("storage_pressure") or view.get("storage_pressure"))

    strong = bool(_STORAGE_CANNOT_CONTINUE.search(blob))
    weak = bool(_STORAGE_WEAK_WARNING.search(blob)) and not strong
    mb = _STORAGE_MB_ASK.search(blob)
    required_bytes: Optional[int] = None
    if mb:
        try:
            required_bytes = _bytes_from_ask(float(mb.group(1)), mb.group(2))
        except (TypeError, ValueError):
            required_bytes = None

    # Progress blocker: strong language + (dialog surface or quantified ask).
    is_progress_blocker = strong and (dialog_like or required_bytes is not None or storage_pressure_flag)
    # Counterexample: weak toast / operational app → warning only.
    if weak and not is_progress_blocker:
        warnings.append(
            Warning(
                kind="low_storage",
                severity="warn",
                evidence=[t for t in texts if _STORAGE_WEAK_WARNING.search(t)][:4]
                or texts[:2],
            )
        )

    if is_progress_blocker:
        effect = EffectPredicate(
            subject="storage",
            relation="available_bytes_at_least",
            value=int(required_bytes or 0),
        )
        conf = 0.55
        if dialog_like:
            conf += 0.2
        if required_bytes:
            conf += 0.15
        if strong:
            conf += 0.1
        suggested = ""
        if "system settings" in blob.lower() or "storage" in blob.lower():
            if "system settings" in blob.lower():
                suggested = "system_settings_storage"
        blocks = [IntentionRef(intention_id=intention_id)] if intention_id else []
        blockers.append(
            BlockingCondition(
                kind="insufficient_storage",
                required_effect=effect,
                blocks=blocks,
                evidence=texts[:6],
                provenance={
                    "surface_ownership": str(app or extras.get("app") or view.get("app") or ""),
                    "modality": "blocking_dialog" if dialog_like else "warning_text",
                    "confidence": min(1.0, conf),
                    "language_cannot_continue": strong,
                    "quantified_ask_bytes": required_bytes,
                },
                suggested_method_from_environment=suggested,
                lifecycle=BlockerLifecycle.CONFIRMED.value
                if conf >= 0.75
                else BlockerLifecycle.DETECTED.value,
            )
        )
        # Distinct second precondition: app may remain non-operational after
        # free-space is met (dismiss/recover dialog). Child B only after parent
        # recheck — assess orders unmet preds; storage first, then this.
        blockers.append(
            BlockingCondition(
                kind="app_not_operational",
                required_effect=EffectPredicate(
                    subject="app_operational",
                    relation="is_true",
                    value=True,
                ),
                blocks=list(blocks),
                evidence=texts[:4],
                provenance={
                    "modality": "blocking_dialog" if dialog_like else "warning_text",
                    "confidence": min(1.0, conf),
                    "paired_with": "insufficient_storage",
                },
                lifecycle=BlockerLifecycle.DETECTED.value,
            )
        )
    elif strong and not dialog_like and required_bytes is None:
        # Ambiguous strong-ish text without dialog — warning, not interrupt.
        warnings.append(
            Warning(kind="low_storage", severity="warn", evidence=texts[:3])
        )

    return warnings, blockers


def assess_executability(
    *,
    intention_id: str = "",
    preconditions: Sequence[Precondition] = (),
    blockers: Sequence[BlockingCondition] = (),
    world: Optional[Dict[str, Any]] = None,
    facts: Optional[Dict[str, Any]] = None,
) -> ExecutabilityAssessment:
    """Decide whether the current intention can progress."""
    world = world if isinstance(world, dict) else {}
    facts = dict(facts or {})
    unmet: List[Precondition] = []
    relevant_blockers: List[BlockingCondition] = []

    # If caller passed no explicit preconditions, derive from blockers scoped
    # to this intention (or unscoped).
    derived_preconditions = list(preconditions)
    if not derived_preconditions and blockers:
        for b in blockers:
            if b.blocks and intention_id:
                if not any(x.intention_id == intention_id for x in b.blocks):
                    continue
            derived_preconditions.append(Precondition(predicate=b.required_effect))

    if not derived_preconditions and not blockers:
        # No evidence of unmet prereqs.
        if facts.get("executability_unknown"):
            return ExecutabilityAssessment(
                status=ExecutabilityStatus.UNKNOWN.value,
                reason="insufficient_evidence_for_preconditions",
            )
        return ExecutabilityAssessment(
            status=ExecutabilityStatus.EXECUTABLE.value,
            reason="no_unmet_preconditions",
        )

    for pre in derived_preconditions:
        if _predicate_satisfied(pre.predicate, world=world, facts=facts):
            continue
        # Missing evidence about this predicate → UNKNOWN rather than blocked.
        if _predicate_unknown(pre.predicate, world=world, facts=facts):
            return ExecutabilityAssessment(
                status=ExecutabilityStatus.UNKNOWN.value,
                unmet_preconditions=[pre],
                reason=f"unknown:{pre.semantic_key()}",
            )
        unmet.append(pre)
        for b in blockers:
            if b.semantic_key() == pre.semantic_key() or (
                b.required_effect.subject == pre.predicate.subject
                and b.required_effect.relation == pre.predicate.relation
            ):
                if intention_id and b.blocks:
                    if not any(x.intention_id == intention_id for x in b.blocks):
                        continue
                relevant_blockers.append(b)

    if not unmet:
        return ExecutabilityAssessment(
            status=ExecutabilityStatus.EXECUTABLE.value,
            reason="preconditions_satisfied",
        )

    resolvable: List[BlockingCondition] = []
    for pre in unmet:
        methods = resolve_methods_for_effect(pre.predicate, facts=facts)
        # Pair with blocker evidence when present; else synthetic resolvable.
        matched = [b for b in relevant_blockers if b.semantic_key() == pre.semantic_key()]
        if methods:
            if matched:
                resolvable.extend(matched)
            else:
                resolvable.append(
                    BlockingCondition(
                        kind="derived",
                        required_effect=pre.predicate,
                        blocks=[IntentionRef(intention_id=intention_id)]
                        if intention_id
                        else [],
                        evidence=["precondition_unmet"],
                        lifecycle=BlockerLifecycle.CONFIRMED.value,
                    )
                )

    if resolvable:
        return ExecutabilityAssessment(
            status=ExecutabilityStatus.BLOCKED_RESOLVABLE.value,
            unmet_preconditions=unmet,
            blocking_conditions=relevant_blockers or list(resolvable),
            resolvable_conditions=resolvable,
            reason="unmet_resolvable_preconditions",
        )
    return ExecutabilityAssessment(
        status=ExecutabilityStatus.BLOCKED_UNRESOLVABLE.value,
        unmet_preconditions=unmet,
        blocking_conditions=relevant_blockers,
        reason="unmet_unresolvable_preconditions",
    )


def _predicate_satisfied(
    pred: EffectPredicate,
    *,
    world: Dict[str, Any],
    facts: Dict[str, Any],
) -> bool:
    subj = str(pred.subject or "").strip().lower()
    rel = str(pred.relation or "").strip().lower()
    if subj == "storage" and rel == "available_bytes_at_least":
        need = int(pred.value or 0)
        if bool(world.get("free_storage_satisfied") or facts.get("free_storage_satisfied")):
            return True
        free = facts.get("available_storage_bytes")
        if free is None:
            free = world.get("available_storage_bytes")
        if free is None:
            return False
        # Unquantified dialog (need==0): free bytes alone do not prove relief;
        # require an explicit satisfied stamp (handled above) or positive reclaim.
        if need <= 0:
            return bool(facts.get("bytes_reclaimed") or world.get("bytes_reclaimed"))
        return int(free) >= need
    if subj == "app_operational" and rel == "is_true":
        if "app_operational" in facts:
            return bool(facts.get("app_operational"))
        if "app_operational" in world:
            return bool(world.get("app_operational"))
        # Dialog storage pressure implies not operational.
        if bool(world.get("storage_pressure") or facts.get("storage_pressure")):
            screen = str(world.get("surface") or world.get("screen") or "").lower()
            if screen in {"dialog", "modal"}:
                return False
        return bool(world.get("app_operational", True))
    if rel == "is_true":
        key = subj
        if key in facts:
            return bool(facts.get(key))
        if key in world:
            return bool(world.get(key))
        return False
    # Named world flags matching semantic key.
    key = pred.semantic_key()
    if key in world:
        return bool(world.get(key))
    return False


def _predicate_unknown(
    pred: EffectPredicate,
    *,
    world: Dict[str, Any],
    facts: Dict[str, Any],
) -> bool:
    """True when we lack evidence to decide the predicate (force UNKNOWN path)."""
    if facts.get("force_unknown_preconditions"):
        return True
    subj = str(pred.subject or "").strip().lower()
    rel = str(pred.relation or "").strip().lower()
    if subj == "storage" and rel == "available_bytes_at_least":
        # If we have a confirmed blocker with this effect, we know it's unmet.
        return False
    if subj in {"authenticated", "permission_granted", "dependency_present"}:
        if subj not in facts and subj not in world and not facts.get(f"{subj}_evidence"):
            return True
    return False


def evaluate_effect_predicate(
    pred: EffectPredicate,
    *,
    world: Optional[Dict[str, Any]] = None,
    facts: Optional[Dict[str, Any]] = None,
) -> bool:
    """Intention-side judgment of whether a required effect holds in the world."""
    return _predicate_satisfied(
        pred,
        world=world if isinstance(world, dict) else {},
        facts=facts if isinstance(facts, dict) else {},
    )


def agent_owned_temp_candidates(
    *,
    live_run_root: str = "/tmp/hermes-runs",
    keep_active: bool = True,
) -> List[ResourceCandidate]:
    """Bootstrap ownership metadata for agent ephemeral roots."""
    return [
        ResourceCandidate(
            path=live_run_root,
            owner="agent",
            persistence="ephemeral",
            regenerable=True,
            deletion_risk="low",
            reclaimability=(
                Reclaimability.LIKELY.value
                if keep_active
                else Reclaimability.GUARANTEED.value
            ),
        )
    ]
