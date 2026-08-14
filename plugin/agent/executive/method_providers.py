"""Capability/method providers — domain catalogs live here, not in AgentRuntime.

AgentRuntime only calls ``discover_methods(interpretation, constraints)``.
Providers advertise MethodSpecs for effects they understand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

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
) -> Tuple[List[MethodSpec], List[Dict[str, Any]]]:
    """Return (specs, provider_errors). Fail-open across providers; never silent."""
    out: List[MethodSpec] = []
    errors: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for provider in _PROVIDERS:
        provider_id = str(
            getattr(provider, "provider_id", None)
            or getattr(provider, "__class__", type(provider)).__name__
        )
        try:
            specs = provider.discover(interpretation, constraints=constraints) or []
        except Exception as exc:
            errors.append(
                {
                    "event": "method_provider_error",
                    "provider_id": provider_id,
                    "exception": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        for spec in specs:
            mid = str(getattr(spec, "id", "") or "")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            out.append(spec)
    return out, errors


def interpret_task_request(
    request: Any,
    *,
    brain_workspace: Any = None,
    activated_context: Optional[dict] = None,
) -> TaskInterpretation:
    """Generic Goal.infer interpretation — domain-agnostic routing input.

    Slice 1B: when ``brain_workspace`` / ``activated_context`` is supplied, attach
    it under ``notes['activated_context']`` so interpretation *consumes* activation
    rather than ignoring a sidecar. Does not treat activation as Goal commitment.
    """
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
        effects.append(str(kind))
        if "forward" in kind:
            effects.append("forward_message")
        if "call" in kind or "voice" in kind:
            effects.append("place_call")

    notes: dict = {}
    ctx = dict(activated_context or {})
    if not ctx and brain_workspace is not None:
        try:
            from plugin.agent.brain.context_activation import (
                consultation_context_from_workspace,
            )

            ctx = consultation_context_from_workspace(brain_workspace)
        except Exception:
            ctx = {}
    if ctx:
        notes["activated_context"] = ctx
        # Temporary Slice 1 adapter: surface L1-preferred hypothesis for downstream
        # inspection without committing RoleBinder / goal.committed_*.
        hyps = list(ctx.get("hypotheses") or [])
        if hyps:
            notes["top_hypothesis"] = dict(hyps[0])
            notes["hypothesis_salience"] = hyps[0].get("salience")
        wc = dict(ctx.get("working_context") or {})
        if wc.get("recent_entity_name") or wc.get("recent_entity"):
            notes["l1_preferred_entity"] = wc.get("recent_entity_name") or wc.get(
                "recent_entity"
            )

    return TaskInterpretation(
        user_turn=user_turn,
        goal_kind=kind,
        goal=goal,
        desired_effects=effects,
        notes=notes,
    )
