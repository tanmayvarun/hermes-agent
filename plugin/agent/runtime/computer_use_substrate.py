"""Production ComputerUse substrate wiring — below AgentRuntime / ClientAdapter.

Observe/execute bindings are composed here. TUI must not inject them.
READY is advertised only when this substrate is runnable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

ObserveFn = Callable[[], Any]
WaitFn = Callable[[float, str], None]


@dataclass
class ComputerUseSubstrate:
    """Composed ComputerUse dependencies."""

    runnable: bool
    reason: str = ""
    app_default: str = "WhatsApp"
    # Optional test/prod override factories (already-bound callables builders).
    _observe_builder: Optional[Callable[..., ObserveFn]] = None
    _execute_builder: Optional[Callable[..., Any]] = None
    _wait_builder: Optional[Callable[..., WaitFn]] = None

    def bind(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Return observe/execute/wait_fn/log for closed-loop dispatch."""
        if not self.runnable:
            raise RuntimeError(f"computer_use_substrate_not_runnable:{self.reason}")
        runtime = context.get("runtime_state")
        goal = context.get("goal")
        if runtime is None or goal is None:
            raise RuntimeError("computer_use_bind_missing_runtime_or_goal")
        log = context.get("log")
        if log is None:
            log = _NullEventLogger()
        app = str(getattr(goal, "app", "") or self.app_default or "WhatsApp")

        if self._observe_builder is not None:
            observe = self._observe_builder(runtime=runtime, goal=goal, log=log, app=app)
        else:
            observe = _default_observe(runtime=runtime, log=log, app=app)

        if self._execute_builder is not None:
            execute = self._execute_builder(runtime=runtime, goal=goal, log=log, app=app)
        else:
            execute = _LiveCapabilityExecutor(runtime=runtime, goal=goal, app=app)

        if self._wait_builder is not None:
            wait_fn = self._wait_builder(runtime=runtime, goal=goal, log=log, app=app)
        else:
            wait_fn = _default_wait(log=log, runtime=runtime)

        return {
            "observe": observe,
            "execute": execute,
            "wait_fn": wait_fn,
            "log": log,
        }


_ACTIVE: Optional[ComputerUseSubstrate] = None


def get_computer_use_substrate() -> Optional[ComputerUseSubstrate]:
    return _ACTIVE


def install_computer_use_substrate(substrate: Optional[ComputerUseSubstrate]) -> None:
    global _ACTIVE
    _ACTIVE = substrate


def probe_computer_use_environment() -> Tuple[bool, str]:
    """True when live observation backends needed for ComputerUse are present."""
    try:
        from plugin.perception.macos.accessibility.observer import (
            ax_available,
            macapptree_available,
        )
    except Exception as exc:
        return False, f"accessibility_import_failed:{type(exc).__name__}:{exc}"
    try:
        has_ax = bool(ax_available())
    except Exception as exc:
        return False, f"ax_probe_failed:{exc}"
    try:
        has_tree = bool(macapptree_available())
    except Exception:
        has_tree = False
    if not has_ax and not has_tree:
        return False, "no_ax_or_macapptree_backend"
    try:
        from plugin.experiments.live_observe import _live_observe  # noqa: F401
        from plugin.agent.capabilities.dispatch import dispatch_from_step  # noqa: F401
    except Exception as exc:
        return False, f"substrate_import_failed:{type(exc).__name__}:{exc}"
    return True, "ok"


def compose_computer_use_substrate(
    *,
    force_runnable: Optional[bool] = None,
    observe_builder: Optional[Callable[..., ObserveFn]] = None,
    execute_builder: Optional[Callable[..., Any]] = None,
    wait_builder: Optional[Callable[..., WaitFn]] = None,
) -> ComputerUseSubstrate:
    """Compose substrate. READY/runnable only when environment (or forced test) allows."""
    if force_runnable is True:
        ok, reason = True, "forced_runnable"
    elif force_runnable is False:
        ok, reason = False, "forced_not_runnable"
    else:
        ok, reason = probe_computer_use_environment()
    substrate = ComputerUseSubstrate(
        runnable=ok,
        reason=reason,
        _observe_builder=observe_builder,
        _execute_builder=execute_builder,
        _wait_builder=wait_builder,
    )
    install_computer_use_substrate(substrate if ok else None)
    return substrate


def _default_observe(*, runtime: Any, log: Any, app: str) -> ObserveFn:
    def observe():
        from plugin.agent.unified_cognition import expects_overlay_perception
        from plugin.experiments.live_observe import _live_observe

        return _live_observe(
            log,
            app=app,
            step=int(getattr(runtime.execution_state, "iteration", 0) or 0),
            with_screenshot=True,
            include_overlays=expects_overlay_perception(runtime.execution_state),
        )

    return observe


def _default_wait(*, log: Any, runtime: Any) -> WaitFn:
    def wait_fn(seconds: float, reason: str) -> None:
        import time

        try:
            log.step(
                "wait",
                step=int(getattr(runtime.execution_state, "iteration", 0) or 0),
                message=f"{seconds}s {reason}",
            )
        except Exception:
            pass
        time.sleep(max(0.0, float(seconds or 0.0)))

    return wait_fn


class _LiveCapabilityExecutor:
    """Generic live motor: capability dispatch + ghost scroll fallback."""

    def __init__(self, *, runtime: Any, goal: Any, app: str) -> None:
        self.runtime = runtime
        self.goal = goal
        self.app = app

    def execute(self, step: Any) -> Any:
        from plugin.agent.capabilities.dispatch import dispatch_from_step
        from plugin.executor.ghost import ExecResult, get_executor

        act = str(getattr(step, "action", "") or "").lower()
        fam = str(getattr(step, "action_family", "") or "")
        if act == "observe":
            return ExecResult(ok=True, backend="none", message="observe")
        if fam == "scroll_content" or act == "scroll":
            direction = getattr(step, "scroll_direction", "") or "down"
            amount = int(getattr(step, "scroll_amount", 0) or 3)
            return get_executor(dry_run=False, app=self.app).scroll(
                direction, amount=amount
            )
        try:
            from plugin.agent.apps.registry import get_overlay

            overlay = get_overlay(str(getattr(self.goal, "app", "") or self.app), self.runtime.world_model)
        except Exception:
            overlay = None
        outcome = dispatch_from_step(
            step,
            app=self.app,
            overlay=overlay,
            world=self.runtime.world_model,
            execution_state=self.runtime.execution_state,
            goal=self.goal,
        )
        return ExecResult(
            ok=bool(getattr(outcome, "ok", False)),
            backend="capability",
            message=str(
                getattr(outcome, "message", None)
                or getattr(outcome, "capability", None)
                or fam
                or act
            ),
        )


class _NullEventLogger:
    def step(self, *args: Any, **kwargs: Any) -> None:
        return None

    def log(self, *args: Any, **kwargs: Any) -> None:
        return None

    def check(self, *args: Any, **kwargs: Any) -> None:
        return None
