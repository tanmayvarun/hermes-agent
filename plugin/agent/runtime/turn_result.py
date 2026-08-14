"""Structured result of AgentRuntime.handle_turn."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from plugin.agent.runtime.task_facts import (
    TURN_COMPLETED,
    TURN_CONTINUED,
    TURN_FAILED,
    TURN_LEGACY_DELEGATED,
    TURN_WAITING_FOR_USER,
)


class TurnStatus:
    COMPLETED = TURN_COMPLETED
    WAITING_FOR_USER = TURN_WAITING_FOR_USER
    CONTINUED = TURN_CONTINUED
    FAILED = TURN_FAILED
    LEGACY_DELEGATED = TURN_LEGACY_DELEGATED


@dataclass
class RuntimeTurnResult:
    status: str
    message: str = ""
    question: str = ""
    intention_id: str = ""
    selected_method: str = ""
    selected_substrate: str = ""
    task_request_id: str = ""
    session_id: str = ""
    runtime_id: str = ""
    acceptance_trace: Dict[str, Any] = field(default_factory=dict)
    legacy_result: Any = None
    interpretation: Any = None
    # Client-facing rich UI (e.g. WhatsApp link-device QR). Domain-agnostic bag.
    ui_hints: Dict[str, Any] = field(default_factory=dict)
