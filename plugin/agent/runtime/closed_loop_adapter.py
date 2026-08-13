"""Compatibility adapter: ComputerUse MethodSpec → legacy closed-loop.

Domain-agnostic entry. Live observe/execute wiring is loaded from the
experiment harness helpers when available; callers may inject overrides via
``context['observe']`` / ``context['execute']`` / ``context['closed_loop']``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def run_legacy_closed_loop_for_goal(
    *,
    spec: Any = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ctx = dict(context or {})
    goal = ctx.get("goal")
    runtime = ctx.get("runtime_state")
    if goal is None:
        return {"ok": False, "detail": "missing_goal", "substrate": "computer_use"}
    if runtime is None:
        return {"ok": False, "detail": "missing_runtime_state", "substrate": "computer_use"}

    closed_loop = ctx.get("closed_loop")
    observe = ctx.get("observe")
    execute = ctx.get("execute")
    if closed_loop is None:
        from plugin.agent.controller import run_goal_closed_loop

        closed_loop = run_goal_closed_loop
    if observe is None or execute is None:
        # Live wiring optional — unit tests inject observe/execute.
        return {
            "ok": False,
            "detail": "computer_use_observe_execute_not_provided",
            "substrate": "computer_use",
            "method_id": str(getattr(spec, "id", "") or ""),
            "dispatched": True,
        }

    result = closed_loop(
        runtime,
        goal,
        observe=observe,
        execute=execute,
        log=ctx.get("log"),
        max_iterations=int(ctx.get("max_iterations") or 15),
        settle_s=float(ctx.get("settle_s") or 0.5),
        wait_fn=ctx.get("wait_fn"),
        engine=ctx.get("engine"),
        memory=ctx.get("memory"),
    )
    return {
        "ok": bool(getattr(result, "ok", False)),
        "reason": str(getattr(result, "reason", "") or ""),
        "iterations": int(getattr(result, "iterations", 0) or 0),
        "substrate": "computer_use",
        "method_id": str(getattr(spec, "id", "") or ""),
        "dispatched": True,
        "result": result,
    }
