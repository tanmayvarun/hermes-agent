"""Compatibility adapter: ComputerUse MethodSpec → legacy closed-loop.

Bindings come from the composed ComputerUseSubstrate — not from TUI/client
injection. Context may still override for tests.
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
    wait_fn = ctx.get("wait_fn")
    log = ctx.get("log")

    if observe is None or execute is None:
        from plugin.agent.runtime.computer_use_substrate import get_computer_use_substrate

        substrate = get_computer_use_substrate()
        if substrate is None or not substrate.runnable:
            return {
                "ok": False,
                "detail": "computer_use_substrate_not_composed",
                "substrate": "computer_use",
                "method_id": str(getattr(spec, "id", "") or ""),
                "dispatched": True,
            }
        try:
            bindings = substrate.bind(ctx)
        except Exception as exc:
            return {
                "ok": False,
                "detail": f"computer_use_bind_failed:{type(exc).__name__}:{exc}",
                "substrate": "computer_use",
                "method_id": str(getattr(spec, "id", "") or ""),
                "dispatched": True,
            }
        observe = bindings.get("observe")
        execute = bindings.get("execute")
        wait_fn = wait_fn or bindings.get("wait_fn")
        log = log or bindings.get("log")

    if observe is None or execute is None:
        return {
            "ok": False,
            "detail": "computer_use_observe_execute_not_provided",
            "substrate": "computer_use",
            "method_id": str(getattr(spec, "id", "") or ""),
            "dispatched": True,
        }

    if closed_loop is None:
        from plugin.agent.controller import run_goal_closed_loop

        closed_loop = run_goal_closed_loop

    result = closed_loop(
        runtime,
        goal,
        observe=observe,
        execute=execute,
        log=log,
        max_iterations=int(ctx.get("max_iterations") or 15),
        settle_s=float(ctx.get("settle_s") or 0.5),
        wait_fn=wait_fn,
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
        "bindings_source": "composed_substrate",
        "result": result,
    }
