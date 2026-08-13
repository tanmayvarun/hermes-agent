"""MethodAvailability vs MethodReadiness — orthogonal to MethodFrontier quality scores.

Implementation readiness ≠ runtime prerequisite:

    readiness UNAVAILABLE → overall UNSUPPORTED (never ASK to link)
    readiness unspecified/empty → legacy-compatible (not auto-UNSUPPORTED)
    readiness READY + auth missing → MISSING_PRECONDITION (may ASK)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping, Optional, Set

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
    UNSPECIFIED = ""  # legacy MethodSpec — preserve eligibility


def _num(value: Any, default: float) -> float:
    """None-aware float: keep legitimate 0.0 (do not coerce via truthiness)."""
    if value is None:
        return float(default)
    return float(value)


def overall_availability(
    *,
    readiness: str,
    runtime_availability: str,
) -> str:
    r = str(readiness or "").strip().lower()
    if r == MethodReadiness.UNAVAILABLE.value:
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
    """Return (overall_availability, detail_reason). Availability only — no ranking."""
    readiness = str(getattr(spec, "readiness", None) or "").strip().lower()
    mid = str(getattr(spec, "id", "") or "")
    substrate = str(getattr(spec, "substrate", "") or "")
    if mid in (declined_method_ids or set()):
        return MethodAvailability.USER_DECLINED.value, "method_declined"
    if substrate_forbidden(substrate, constraints):
        return MethodAvailability.FORBIDDEN_BY_CONSTRAINT.value, "substrate_constraint"

    if readiness == MethodReadiness.UNAVAILABLE.value:
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
        missing.append(key)
    if missing:
        # Legacy unspecified readiness with preconditions: still MISSING, but ASK
        # only when readiness is explicitly READY (see should_ask_for_precondition).
        return (
            MethodAvailability.MISSING_PRECONDITION.value,
            f"missing:{','.join(missing)}",
        )
    return MethodAvailability.AVAILABLE.value, "ready"


def should_ask_for_precondition(
    *,
    preferred_spec: Any,
    preferred_availability: str,
    preferred_quality: float,
    best_available_quality: Optional[float],
    ask_quality_margin: float = 0.15,
) -> bool:
    """Interrupt only for explicitly READY methods with missing user prereqs.

    Does not auto-ASK merely because the top-ranked method is missing a prereq.
    """
    if preferred_availability != MethodAvailability.MISSING_PRECONDITION.value:
        return False
    readiness = str(getattr(preferred_spec, "readiness", "") or "").strip().lower()
    if readiness != MethodReadiness.READY.value:
        return False
    if best_available_quality is None:
        return True
    return float(preferred_quality) >= (
        float(best_available_quality) + float(ask_quality_margin)
    )
