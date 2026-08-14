"""Canonical task/turn status facts (presentation-agnostic).

Single vocabulary for TaskTracker, gateway ``task.status`` / ``message.complete``,
and desktop prompt-task UI. Presentation labels live in thin mappers — do not
redefine status strings in clients.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Mapping, Optional, Tuple

# --- Progressive + terminal tracker statuses ---------------------------------

STATUS_RUNNING = "running"
STATUS_WAITING_FOR_USER = "waiting_for_user"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_INTERRUPTED = "interrupted"

TASK_STATUSES: Tuple[str, ...] = (
    STATUS_RUNNING,
    STATUS_WAITING_FOR_USER,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
)

TERMINAL_TASK_STATUSES: FrozenSet[str] = frozenset(
    {
        STATUS_WAITING_FOR_USER,
        STATUS_COMPLETED,
        STATUS_FAILED,
        STATUS_INTERRUPTED,
    }
)

# --- Progressive phases (non-terminal progress labels) -----------------------

PHASE_INTERPRETING = "interpreting"
PHASE_SELECTING_METHOD = "selecting_method"
PHASE_EXECUTING = "executing"
PHASE_COMPUTER_USE = "computer_use"
PHASE_AWAITING_USER = "awaiting_user"
PHASE_FINISHING = "finishing"

TASK_PHASES: Tuple[str, ...] = (
    PHASE_INTERPRETING,
    PHASE_SELECTING_METHOD,
    PHASE_EXECUTING,
    PHASE_COMPUTER_USE,
    PHASE_AWAITING_USER,
    PHASE_FINISHING,
)

# --- Turn outcomes (AgentRuntime.handle_turn) --------------------------------

TURN_COMPLETED = "completed"
TURN_WAITING_FOR_USER = "waiting_for_user"
TURN_CONTINUED = "continued"
TURN_FAILED = "failed"
TURN_LEGACY_DELEGATED = "legacy_delegated"

TURN_STATUSES: Tuple[str, ...] = (
    TURN_COMPLETED,
    TURN_WAITING_FOR_USER,
    TURN_CONTINUED,
    TURN_FAILED,
    TURN_LEGACY_DELEGATED,
)

# --- Stable client-boundary error codes (closed set) -------------------------

ERROR_SETUP_BLOCKED = "setup_blocked"
ERROR_AUTH_REQUIRED = "auth_required"
ERROR_PROVIDER_UNAVAILABLE = "provider_unavailable"
ERROR_TIMEOUT = "timeout"
ERROR_INTERRUPTED = "interrupted"
ERROR_EXECUTION_FAILED = "execution_failed"
ERROR_UNKNOWN = "unknown"

HERMES_ERROR_CODES: Tuple[str, ...] = (
    ERROR_SETUP_BLOCKED,
    ERROR_AUTH_REQUIRED,
    ERROR_PROVIDER_UNAVAILABLE,
    ERROR_TIMEOUT,
    ERROR_INTERRUPTED,
    ERROR_EXECUTION_FAILED,
    ERROR_UNKNOWN,
)


def is_terminal_task_status(status: str) -> bool:
    return str(status or "").strip().lower() in TERMINAL_TASK_STATUSES


def normalize_task_status(raw: Any, *, default: str = STATUS_RUNNING) -> str:
    s = str(raw or "").strip().lower()
    if s in TASK_STATUSES:
        return s
    return default


def final_status_from_turn(turn_status: str, *, interrupted: bool = False) -> str:
    """Map TurnStatus / gateway flags → tracker final_status."""
    if interrupted:
        return STATUS_INTERRUPTED
    s = str(turn_status or "").strip().lower()
    if s in {STATUS_WAITING_FOR_USER, TURN_WAITING_FOR_USER}:
        return STATUS_WAITING_FOR_USER
    if s in {STATUS_FAILED, TURN_FAILED, "error"}:
        return STATUS_FAILED
    if s in {STATUS_INTERRUPTED, "interrupted"}:
        return STATUS_INTERRUPTED
    if s in {
        STATUS_COMPLETED,
        TURN_COMPLETED,
        "complete",
        TURN_CONTINUED,
        TURN_LEGACY_DELEGATED,
    }:
        return STATUS_COMPLETED
    return STATUS_COMPLETED


def phase_for_final_status(final_status: str) -> str:
    """Canonical settle phase from a terminal tracker status."""
    if str(final_status or "").strip().lower() == STATUS_WAITING_FOR_USER:
        return PHASE_AWAITING_USER
    return PHASE_FINISHING


@dataclass(frozen=True)
class TaskOutcomeFacts:
    """Presentation-agnostic settled outcome (gateway / transcript merge)."""

    task_request_id: str
    final_status: str
    duration_ms: Optional[int] = None
    phase: str = PHASE_FINISHING
    summary: str = ""
    error_code: str = ""
    message: str = ""

    def to_complete_payload(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "task_request_id": self.task_request_id,
            "final_status": self.final_status,
            "duration_ms": self.duration_ms,
            "phase": self.phase,
            "summary": self.summary or "",
        }
        if self.error_code:
            out["error_code"] = self.error_code
        if self.message:
            out["message"] = self.message
        return out


class TaskOutcomePresentation:
    """Thin UI labels — never recompute status vocabulary here."""

    _STATUS_LABELS: Mapping[str, str] = {
        STATUS_WAITING_FOR_USER: "Needs your input",
        STATUS_FAILED: "Failed",
        STATUS_INTERRUPTED: "Interrupted",
        STATUS_COMPLETED: "Completed",
        STATUS_RUNNING: "Running",
    }

    _PHASE_LABELS: Mapping[str, str] = {
        PHASE_COMPUTER_USE: "computer use",
        PHASE_SELECTING_METHOD: "selecting method",
        PHASE_AWAITING_USER: "needs input",
        PHASE_INTERPRETING: "interpreting",
        PHASE_EXECUTING: "executing",
        PHASE_FINISHING: "finishing",
    }

    @classmethod
    def status_label(cls, status: str) -> str:
        s = normalize_task_status(status)
        return cls._STATUS_LABELS.get(s, "Running")

    @classmethod
    def phase_label(cls, phase: str) -> str:
        p = str(phase or "").strip().lower()
        if not p:
            return ""
        if p in cls._PHASE_LABELS:
            return cls._PHASE_LABELS[p]
        return p.replace("_", " ")


def vocab_schema() -> Dict[str, Any]:
    """JSON-serializable schema shared with desktop contract tests."""
    from plugin.agent.runtime.error_codes import vocab_error_schema

    base = {
        "task_statuses": list(TASK_STATUSES),
        "terminal_task_statuses": sorted(TERMINAL_TASK_STATUSES),
        "task_phases": list(TASK_PHASES),
        "turn_statuses": list(TURN_STATUSES),
        "error_codes": list(HERMES_ERROR_CODES),
    }
    base.update(vocab_error_schema())
    return base
