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
        adapter = self.adapter
        if adapter is None:
            from plugin.agent.runtime.closed_loop_adapter import (
                run_legacy_closed_loop_for_goal,
            )

            adapter = run_legacy_closed_loop_for_goal
        try:
            payload = adapter(spec=spec, context=context)
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
        return MethodExecutionResult(
            ok=ok,
            status="executed" if ok else "failed",
            detail=detail,
            payload=payload,
            executor_id=self.executor_id,
        )
