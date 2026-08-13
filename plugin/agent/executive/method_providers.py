"""Capability/method providers — domain catalogs live here, not in AgentRuntime.

AgentRuntime only calls ``discover_methods(interpretation, constraints)``.
Providers advertise MethodSpecs for effects they understand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Protocol, Sequence

from plugin.agent.executive.intention_frame import MethodSpec
from plugin.agent.ingress import ExecutionConstraints


@dataclass
class TaskInterpretation:
    """Generic interpretation result — no substrate choice."""

    user_turn: str = ""
    goal_kind: str = "unknown"
    goal: Any = None
    desired_effects: List[str] = field(default_factory=list)
    notes: dict = field(default_factory=dict)


class MethodProvider(Protocol):
    def discover(
        self,
        interpretation: TaskInterpretation,
        *,
        constraints: Optional[ExecutionConstraints] = None,
    ) -> Sequence[MethodSpec]:
        ...


_PROVIDERS: List[MethodProvider] = []


def register_method_provider(provider: MethodProvider) -> None:
    if provider not in _PROVIDERS:
        _PROVIDERS.append(provider)


def clear_method_providers() -> None:
    _PROVIDERS.clear()


def iter_method_providers() -> List[MethodProvider]:
    return list(_PROVIDERS)


def discover_methods(
    interpretation: TaskInterpretation,
    *,
    constraints: Optional[ExecutionConstraints] = None,
) -> List[MethodSpec]:
    out: List[MethodSpec] = []
    seen: set[str] = set()
    for provider in _PROVIDERS:
        try:
            specs = provider.discover(interpretation, constraints=constraints) or []
        except Exception:
            continue
        for spec in specs:
            mid = str(getattr(spec, "id", "") or "")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            out.append(spec)
    return out


def interpret_task_request(request: Any) -> TaskInterpretation:
    """Generic Goal.infer interpretation — domain-agnostic routing input."""
    user_turn = str(getattr(request, "user_turn", "") or "")
    legacy = getattr(request, "legacy_goal", None)
    goal = legacy
    kind = "unknown"
    if goal is not None:
        kind = str(getattr(goal, "kind", "") or "unknown")
    else:
        try:
            from plugin.agent.goal import Goal

            goal = Goal.infer_from_text(user_turn)
            kind = str(getattr(goal, "kind", "") or "unknown")
        except Exception:
            goal = None
            kind = "unknown"
    effects: List[str] = []
    if kind and kind != "unknown":
        # Effect keys derived from goal kind; providers match on these.
        effects.append(str(kind))
        if "forward" in kind:
            effects.append("forward_message")
        if "call" in kind or "voice" in kind:
            effects.append("place_call")
    return TaskInterpretation(
        user_turn=user_turn,
        goal_kind=kind,
        goal=goal,
        desired_effects=effects,
    )
