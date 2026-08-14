"""Method execution dispatch — below MethodSpec selection.

AgentRuntime selects a MethodSpec; this registry runs the substrate executor.
ComputerUse may adapt to legacy ``run_goal_closed_loop``; conversation is only
for turns with no executable method (not a substitute for selected computer_use).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol


@dataclass
class MethodExecutionResult:
    ok: bool
    status: str = ""
    detail: str = ""
    payload: Any = None
    executor_id: str = ""


class MethodExecutor(Protocol):
    executor_id: str
    substrates: tuple[str, ...]

    def execute(self, spec: Any, *, context: Dict[str, Any]) -> MethodExecutionResult:
        ...


_EXECUTORS: List[MethodExecutor] = []


def register_method_executor(executor: MethodExecutor) -> None:
    if executor not in _EXECUTORS:
        _EXECUTORS.append(executor)


def clear_method_executors() -> None:
    _EXECUTORS.clear()


def iter_method_executors() -> List[MethodExecutor]:
    return list(_EXECUTORS)


def execute_method(spec: Any, *, context: Optional[Dict[str, Any]] = None) -> MethodExecutionResult:
    ctx = dict(context or {})
    substrate = str(getattr(spec, "substrate", "") or "").strip().lower()
    for ex in _EXECUTORS:
        subs = {str(s).strip().lower() for s in getattr(ex, "substrates", ()) or ()}
        if substrate and substrate in subs:
            return ex.execute(spec, context=ctx)
    return MethodExecutionResult(
        ok=False,
        status="no_executor",
        detail=f"no executor registered for substrate={substrate!r}",
        executor_id="",
    )


@dataclass
class ComputerUseClosedLoopExecutor:
    """Legacy ComputerUse substrate → closed-loop adapter."""

    executor_id: str = "computer_use_closed_loop"
    substrates: tuple[str, ...] = ("computer_use",)
    adapter: Optional[Callable[..., Any]] = None

    def execute(self, spec: Any, *, context: Dict[str, Any]) -> MethodExecutionResult:
        from plugin.agent.runtime.executor_idempotency import (
            get_executor_idempotency_guard,
            make_effect_key,
        )
        from plugin.agent.runtime.integrity_gates import ComputerUseReadyGate

        ctx = dict(context or {})
        facts = {}
        session_state = ctx.get("session_state")
        if session_state is not None and hasattr(session_state, "precondition_facts"):
            facts = dict(getattr(session_state, "precondition_facts") or {})
        elif isinstance(ctx.get("precondition_facts"), dict):
            facts = dict(ctx.get("precondition_facts") or {})

        setup_blocker_id = str(ctx.get("setup_blocker_id") or "").strip()
        gate = ComputerUseReadyGate.require_ready(
            precondition_facts=facts,
            setup_blocker_id=setup_blocker_id,
        )
        if not gate.ok:
            return MethodExecutionResult(
                ok=False,
                status="setup_blocked",
                detail=gate.reason or "Computer Use blocked by setup integrity gate",
                payload={
                    "fallback": gate.fallback or "ask_prerequisite",
                    "ask_precondition": gate.ask_precondition,
                    "error_code": gate.error_code,
                    "gate": gate.to_payload(),
                },
                executor_id=self.executor_id,
            )

        task_request_id = str(ctx.get("task_request_id") or "").strip()
        goal = ctx.get("goal")
        goal_fp = (
            getattr(goal, "raw", None)
            or getattr(goal, "text", None)
            or getattr(goal, "user_turn", None)
            or str(goal or "")
        )
        guard = get_executor_idempotency_guard()
        idem_key = make_effect_key(
            task_request_id=task_request_id or str(getattr(spec, "id", "") or "cu"),
            effect="computer_use_act",
            parts=(getattr(spec, "id", ""), goal_fp),
        )
        prior = guard.lookup(idem_key)
        if prior is not None:
            return guard.mark_replay(prior)

        adapter = self.adapter
        if adapter is None:
            from plugin.agent.runtime.closed_loop_adapter import (
                run_legacy_closed_loop_for_goal,
            )

            adapter = run_legacy_closed_loop_for_goal
        try:
            payload = adapter(spec=spec, context=ctx)
        except Exception as exc:
            return MethodExecutionResult(
                ok=False,
                status="executor_error",
                detail=str(exc),
                executor_id=self.executor_id,
            )
        ok = True
        detail = ""
        if isinstance(payload, dict):
            ok = bool(payload.get("ok", True))
            detail = str(payload.get("detail") or payload.get("reason") or "")
        result = MethodExecutionResult(
            ok=ok,
            status="executed" if ok else "failed",
            detail=detail,
            payload=payload,
            executor_id=self.executor_id,
        )
        if ok:
            guard.remember_success(idem_key, result)
        return result
