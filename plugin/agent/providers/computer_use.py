"""Production ComputerUse method provider — READY only when substrate is runnable."""

from __future__ import annotations

from typing import Optional, Sequence

from plugin.agent.executive.intention_frame import MethodSpec
from plugin.agent.executive.method_availability import MethodReadiness
from plugin.agent.executive.method_providers import TaskInterpretation
from plugin.agent.ingress import ExecutionConstraints


class ComputerUseMethodProvider:
    """Advertises computer_use methods only when a runnable substrate is composed."""

    provider_id = "computer_use_native"

    def __init__(self, *, runnable: bool = False, reason: str = "") -> None:
        self.runnable = bool(runnable)
        self.reason = str(reason or "")

    def discover(
        self,
        interpretation: TaskInterpretation,
        *,
        constraints: Optional[ExecutionConstraints] = None,
    ) -> Sequence[MethodSpec]:
        if not self.runnable:
            return []
        effects = set(interpretation.desired_effects or [])
        kind = str(interpretation.goal_kind or "")
        if "forward_message" not in effects and "forward" not in kind:
            return []
        return [
            MethodSpec(
                id="native_computer_use_forward",
                capability="forward_message",
                substrate="computer_use",
                provider=self.provider_id,
                preconditions=[],
                readiness=MethodReadiness.READY.value,
                reliability=0.55,  # I3: below WhatsApp gateway (0.88)
                latency=0.7,
                risk=0.55,
                cost=0.6,
                user_interference=0.85,
                semantic_precision=0.55,
            )
        ]


def ensure_computer_use_provider_registered(
    *,
    force_runnable: Optional[bool] = None,
    observe_builder=None,
    execute_builder=None,
    wait_builder=None,
) -> dict:
    """Compose substrate + register provider/executor when runnable.

    Returns a structured composition diagnostic (never silently empty).
    """
    from plugin.agent.executive.method_providers import register_method_provider
    from plugin.agent.runtime.computer_use_substrate import compose_computer_use_substrate
    from plugin.agent.runtime.method_executors import (
        ComputerUseClosedLoopExecutor,
        register_method_executor,
    )

    substrate = compose_computer_use_substrate(
        force_runnable=force_runnable,
        observe_builder=observe_builder,
        execute_builder=execute_builder,
        wait_builder=wait_builder,
    )
    diagnostic = {
        "event": "computer_use_composition",
        "ok": bool(substrate.runnable),
        "runnable": bool(substrate.runnable),
        "substrate_composed": bool(substrate.runnable),
        "reason": substrate.reason,
        "provider_registered": False,
        "executor_registered": False,
    }
    if not substrate.runnable:
        return diagnostic

    register_method_provider(
        ComputerUseMethodProvider(runnable=True, reason=substrate.reason)
    )
    register_method_executor(ComputerUseClosedLoopExecutor())
    try:
        from plugin.agent.runtime.desktop_app_ready import (
            ensure_desktop_app_ready_resolver_registered,
        )

        ensure_desktop_app_ready_resolver_registered()
        diagnostic["desktop_app_ready_resolver"] = True
    except Exception as exc:
        diagnostic["desktop_app_ready_resolver"] = False
        diagnostic["desktop_app_ready_resolver_error"] = f"{type(exc).__name__}:{exc}"
    diagnostic["provider_registered"] = True
    diagnostic["executor_registered"] = True
    diagnostic["ok"] = True
    return diagnostic
