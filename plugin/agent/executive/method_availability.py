"""MethodAvailability vs MethodReadiness — quality ranking stays separate.

Implementation readiness ≠ runtime prerequisite:

    readiness UNAVAILABLE → overall UNSUPPORTED (never ASK to link)
    readiness READY + auth missing → MISSING_PRECONDITION (may ASK)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping, Optional, Sequence, Set

from plugin.agent.ingress import ExecutionConstraints


class MethodAvailability(str, Enum):
    AVAILABLE = "available"
    MISSING_PRECONDITION = "missing_precondition"
    USER_DECLINED = "user_declined"
    UNSUPPORTED = "unsupported"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    FORBIDDEN_BY_CONSTRAINT = "forbidden_by_constraint"


class MethodReadiness(str, Enum):
    """Whether an executable implementation exists (not whether prereqs hold)."""

    READY = "ready"
    UNAVAILABLE = "unavailable"


def overall_availability(
    *,
    readiness: str,
    runtime_availability: str,
) -> str:
    """Combine implementation readiness with runtime prerequisite state."""
    if str(readiness or "").strip().lower() != MethodReadiness.READY.value:
        return MethodAvailability.UNSUPPORTED.value
    return str(runtime_availability or MethodAvailability.UNSUPPORTED.value)


def substrate_forbidden(
    substrate: str,
    constraints: Optional[ExecutionConstraints],
) -> bool:
    if constraints is None:
        return False
    forced = str(getattr(constraints, "forced_substrate", "") or "").strip().lower()
    sub = str(substrate or "").strip().lower()
    if forced and sub and sub != forced:
        return True
    allowed = tuple(getattr(constraints, "allowed_substrates", ()) or ())
    if allowed:
        allowed_l = {str(a).strip().lower() for a in allowed if str(a).strip()}
        if sub and sub not in allowed_l:
            return True
    return False


def evaluate_method_availability(
    spec: Any,
    *,
    constraints: Optional[ExecutionConstraints] = None,
    precondition_facts: Optional[Mapping[str, bool]] = None,
    declined_method_ids: Optional[Set[str]] = None,
    declined_preconditions: Optional[Set[str]] = None,
) -> tuple[str, str]:
    """Return (overall_availability, detail_reason).

    Quality/ranking must not be computed here — availability only.
    """
    readiness = str(
        getattr(spec, "readiness", None) or MethodReadiness.UNAVAILABLE.value
    ).strip().lower()
    mid = str(getattr(spec, "id", "") or "")
    substrate = str(getattr(spec, "substrate", "") or "")
    if mid in (declined_method_ids or set()):
        return MethodAvailability.USER_DECLINED.value, "method_declined"
    if substrate_forbidden(substrate, constraints):
        return MethodAvailability.FORBIDDEN_BY_CONSTRAINT.value, "substrate_constraint"

    if readiness != MethodReadiness.READY.value:
        return MethodAvailability.UNSUPPORTED.value, "implementation_unavailable"

    facts = dict(precondition_facts or {})
    missing: list[str] = []
    for pre in list(getattr(spec, "preconditions", None) or []):
        key = str(pre or "").strip()
        if not key:
            continue
        if key in (declined_preconditions or set()):
            return MethodAvailability.USER_DECLINED.value, f"precondition_declined:{key}"
        if facts.get(key, False) is True:
            continue
        # Absent fact → missing (fail closed for named preconditions).
        missing.append(key)
    if missing:
        return (
            MethodAvailability.MISSING_PRECONDITION.value,
            f"missing:{','.join(missing)}",
        )
    return MethodAvailability.AVAILABLE.value, "ready"


def method_quality_score(spec: Any) -> float:
    """Quality-only score (orthogonal to availability). Higher is better."""
    reliability = float(getattr(spec, "reliability", 0.5) or 0.5)
    latency = float(getattr(spec, "latency", 0.5) or 0.5)
    risk = float(getattr(spec, "risk", 0.5) or 0.5)
    cost = float(getattr(spec, "cost", 0.5) or 0.5)
    interference = float(getattr(spec, "user_interference", 0.5) or 0.5)
    semantic = float(getattr(spec, "semantic_precision", 0.5) or 0.5)
    return (
        1.2 * reliability
        + 1.0 * semantic
        - 0.8 * latency
        - 0.9 * risk
        - 0.6 * cost
        - 1.1 * interference
    )


def rank_by_quality(specs: Sequence[Any]) -> list[tuple[Any, float]]:
    ranked = [(s, method_quality_score(s)) for s in specs]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked


def should_ask_for_precondition(
    *,
    preferred_spec: Any,
    preferred_availability: str,
    best_available_quality: Optional[float],
    ask_quality_margin: float = 0.15,
) -> bool:
    """Whether to interrupt the user for a READY method's missing precondition.

    Does not auto-ASK merely because the top-ranked method is missing a prereq.
    Asks when no AVAILABLE alternative exists, or preferred quality beats the
    best AVAILABLE alternative by ``ask_quality_margin``.
    """
    if preferred_availability != MethodAvailability.MISSING_PRECONDITION.value:
        return False
    readiness = str(getattr(preferred_spec, "readiness", "") or "").lower()
    if readiness != MethodReadiness.READY.value:
        return False
    pref_q = method_quality_score(preferred_spec)
    if best_available_quality is None:
        return True
    return pref_q >= (float(best_available_quality) + float(ask_quality_margin))
