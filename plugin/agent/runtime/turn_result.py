"""Structured result of AgentRuntime.handle_turn."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class TurnStatus:
    COMPLETED = "completed"
    WAITING_FOR_USER = "waiting_for_user"
    CONTINUED = "continued"
    FAILED = "failed"
    LEGACY_DELEGATED = "legacy_delegated"


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
