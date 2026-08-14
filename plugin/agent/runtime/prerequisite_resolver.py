"""Prerequisite resolution — ASK grants permission; verification marks achievement.

User acceptance ≠ precondition satisfied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class PrerequisiteResolveResult:
    status: str  # achieved | failed | pending | unsupported
    precondition: str
    detail: str = ""
    evidence: Dict[str, Any] = None  # type: ignore[assignment]
    # Domain-owned policy for AgentRuntime (no substrate names in the core):
    #   fallback_next_method — block this method/precondition and re-rank
    #   keep_ask — remain WAITING (retryable setup, e.g. fresh QR)
    failure_policy: str = ""
    # Optional user-facing copy while pending / retrying (owned by the resolver).
    user_message: str = ""

    def __post_init__(self) -> None:
        if self.evidence is None:
            self.evidence = {}


class PrerequisiteResolver(Protocol):
    def resolve(
        self,
        precondition: str,
        *,
        permission_granted: bool,
        context: Optional[Dict[str, Any]] = None,
    ) -> PrerequisiteResolveResult:
        ...


_RESOLVERS: List[PrerequisiteResolver] = []


def register_prerequisite_resolver(resolver: PrerequisiteResolver) -> None:
    if resolver not in _RESOLVERS:
        _RESOLVERS.append(resolver)


def clear_prerequisite_resolvers() -> None:
    _RESOLVERS.clear()


def ask_prompt_for_precondition(precondition: str) -> str:
    """Consent text from the owning resolver, else a domain-neutral default."""
    key = str(precondition or "").strip()
    if key:
        for resolver in _RESOLVERS:
            prompt_fn = getattr(resolver, "ask_prompt", None)
            if not callable(prompt_fn):
                continue
            try:
                text = prompt_fn(key)
            except Exception:
                continue
            if text and str(text).strip():
                return str(text).strip()
    return (
        f"A preferred method needs prerequisite '{key or 'access'}' first. "
        "Allow me to set that up so I can continue without a more disruptive approach?"
    )


def resolve_prerequisite(
    precondition: str,
    *,
    permission_granted: bool,
    context: Optional[Dict[str, Any]] = None,
) -> PrerequisiteResolveResult:
    key = str(precondition or "").strip()
    if not key:
        return PrerequisiteResolveResult(
            status="unsupported", precondition="", detail="empty_precondition"
        )
    if not permission_granted:
        return PrerequisiteResolveResult(
            status="failed",
            precondition=key,
            detail="permission_not_granted",
        )
    for resolver in _RESOLVERS:
        try:
            result = resolver.resolve(
                key, permission_granted=permission_granted, context=context
            )
        except Exception as exc:
            return PrerequisiteResolveResult(
                status="failed",
                precondition=key,
                detail=f"resolver_error:{exc}",
            )
        if result is not None and str(result.status) != "unsupported":
            return result
    return PrerequisiteResolveResult(
        status="unsupported",
        precondition=key,
        detail="no_resolver",
    )


@dataclass
class InjectedPrerequisiteResolver:
    """Test/prod injection: map precondition → achieved/failed after permission."""

    outcomes: Dict[str, str]

    def resolve(
        self,
        precondition: str,
        *,
        permission_granted: bool,
        context: Optional[Dict[str, Any]] = None,
    ) -> PrerequisiteResolveResult:
        key = str(precondition or "").strip()
        if key not in self.outcomes:
            return PrerequisiteResolveResult(
                status="unsupported", precondition=key, detail="not_owned"
            )
        if not permission_granted:
            return PrerequisiteResolveResult(
                status="failed", precondition=key, detail="permission_not_granted"
            )
        status = str(self.outcomes[key] or "failed")
        return PrerequisiteResolveResult(status=status, precondition=key, detail="injected")
