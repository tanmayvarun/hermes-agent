"""Precondition / integrity gates before mutating method execution.

Fail closed with typed reasons that AgentRuntime / executors can map to
WAITING_FOR_USER or next_method without inlining domain branches in the core.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from plugin.agent.executive.setup_blockers import DESKTOP_APP_READY_PRECONDITION
from plugin.agent.runtime.error_codes import client_error_payload
from plugin.agent.runtime.task_facts import (
    ERROR_AUTH_REQUIRED,
    ERROR_EXECUTION_FAILED,
    ERROR_PROVIDER_UNAVAILABLE,
    ERROR_SETUP_BLOCKED,
)

WHATSAPP_LINKED_PRECONDITION = "whatsapp_linked"


@dataclass(frozen=True)
class GateDecision:
    ok: bool
    reason: str = ""
    error_code: str = ""
    ask_precondition: str = ""
    fallback: str = ""  # ask_prerequisite | next_method | ""

    def to_payload(self) -> dict[str, Any]:
        base = {
            "ok": self.ok,
            "reason": self.reason,
            "error_code": self.error_code,
            "ask_precondition": self.ask_precondition,
            "fallback": self.fallback,
        }
        if self.error_code:
            base.update(
                client_error_payload(
                    self.error_code,
                    override=self.reason,
                    context={"ask_precondition": self.ask_precondition} if self.ask_precondition else None,
                )
            )
        return base


class ComputerUseReadyGate:
    """Block CU act when desktop app setup is known-not-ready."""

    @staticmethod
    def require_ready(
        *,
        precondition_facts: Optional[Mapping[str, Any]] = None,
        setup_blocker_id: str = "",
    ) -> GateDecision:
        facts = dict(precondition_facts or {})
        if setup_blocker_id:
            return GateDecision(
                ok=False,
                reason=f"setup_blocker:{setup_blocker_id}",
                error_code=ERROR_SETUP_BLOCKED,
                ask_precondition=DESKTOP_APP_READY_PRECONDITION,
                fallback="ask_prerequisite",
            )
        # Explicit false means probed-not-ready this session.
        if facts.get(DESKTOP_APP_READY_PRECONDITION) is False:
            return GateDecision(
                ok=False,
                reason="desktop_app_not_ready",
                error_code=ERROR_SETUP_BLOCKED,
                ask_precondition=DESKTOP_APP_READY_PRECONDITION,
                fallback="ask_prerequisite",
            )
        return GateDecision(ok=True)


class WhatsAppIdentityResolvedGate:
    """Require whatsapp_linked (or explicit session fact) before gateway send."""

    @staticmethod
    def require_linked(
        *,
        precondition_facts: Optional[Mapping[str, Any]] = None,
        linked: Optional[bool] = None,
    ) -> GateDecision:
        facts = dict(precondition_facts or {})
        if linked is True or facts.get(WHATSAPP_LINKED_PRECONDITION) is True:
            return GateDecision(ok=True)
        if linked is False or facts.get(WHATSAPP_LINKED_PRECONDITION) is False:
            return GateDecision(
                ok=False,
                reason="whatsapp_not_linked",
                error_code=ERROR_AUTH_REQUIRED,
                ask_precondition=WHATSAPP_LINKED_PRECONDITION,
                fallback="ask_prerequisite",
            )
        # Unknown — allow executor to probe live bridge.
        return GateDecision(ok=True)


class GatewaySessionWritableGate:
    """Session must be writable (has session_id) before side-effecting sends."""

    @staticmethod
    def require_writable(*, session_id: str = "", task_request_id: str = "") -> GateDecision:
        sid = str(session_id or "").strip()
        tid = str(task_request_id or "").strip()
        if not sid:
            return GateDecision(
                ok=False,
                reason="missing_session_id",
                error_code=ERROR_EXECUTION_FAILED,
                fallback="next_method",
            )
        if not tid:
            return GateDecision(
                ok=False,
                reason="missing_task_request_id",
                error_code=ERROR_PROVIDER_UNAVAILABLE,
                fallback="next_method",
            )
        return GateDecision(ok=True)
