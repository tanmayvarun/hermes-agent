"""In-memory prompt-as-task status tracker.

Every user prompt that enters AgentRuntime becomes a TaskRecord keyed by
``task_request_id``. Status/phase updates are progressive; settle stamps
``duration_ms`` for the frozen UI footer.
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Optional

from plugin.agent.runtime.task_facts import (
    PHASE_AWAITING_USER,
    PHASE_COMPUTER_USE,
    PHASE_EXECUTING,
    PHASE_FINISHING,
    PHASE_INTERPRETING,
    PHASE_SELECTING_METHOD,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
    STATUS_RUNNING,
    STATUS_WAITING_FOR_USER,
    TERMINAL_TASK_STATUSES,
    TaskOutcomeFacts,
    final_status_from_turn as _final_status_from_turn,
)

TaskUpdateCallback = Callable[[Dict[str, Any]], None]

# Re-export canonical facts (single vocabulary).
__all__ = [
    "PHASE_AWAITING_USER",
    "PHASE_COMPUTER_USE",
    "PHASE_EXECUTING",
    "PHASE_FINISHING",
    "PHASE_INTERPRETING",
    "PHASE_SELECTING_METHOD",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_INTERRUPTED",
    "STATUS_RUNNING",
    "STATUS_WAITING_FOR_USER",
    "TaskRecord",
    "TaskTracker",
    "final_status_from_turn",
    "get_task_tracker",
    "reset_task_tracker_for_tests",
]

_TERMINAL = TERMINAL_TASK_STATUSES


@dataclass
class TaskRecord:
    task_request_id: str
    session_id: str
    prompt_excerpt: str = ""
    status: str = STATUS_RUNNING
    phase: str = PHASE_INTERPRETING
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    duration_ms: Optional[int] = None
    summary: str = ""
    error: str = ""
    error_code: str = ""
    selected_method: str = ""

    def to_payload(self) -> Dict[str, Any]:
        from plugin.agent.runtime.error_codes import resolve_user_message

        out = {
            "task_request_id": self.task_request_id,
            "session_id": self.session_id,
            "prompt_excerpt": self.prompt_excerpt,
            "status": self.status,
            "phase": self.phase,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "summary": self.summary,
            "error": self.error,
            "selected_method": self.selected_method,
        }
        if self.error_code:
            out["error_code"] = self.error_code
            out["message"] = resolve_user_message(
                self.error_code, override=self.summary or self.error
            )
        return out


class TaskTracker:
    """Process-local tracker. Not durable across restarts."""

    def __init__(self, *, throttle_s: float = 0.5) -> None:
        self._lock = threading.RLock()
        self._by_id: Dict[str, TaskRecord] = {}
        self._by_session: Dict[str, str] = {}  # session_id -> active task_request_id
        self._throttle_s = max(0.0, float(throttle_s))
        self._last_emit_at: Dict[str, float] = {}

    def start(
        self,
        *,
        task_request_id: str,
        session_id: str,
        prompt: str = "",
        on_update: Optional[TaskUpdateCallback] = None,
    ) -> TaskRecord:
        excerpt = " ".join(str(prompt or "").split())
        if len(excerpt) > 120:
            excerpt = excerpt[:117] + "..."
        now = time.time()
        rec = TaskRecord(
            task_request_id=str(task_request_id),
            session_id=str(session_id or "anonymous"),
            prompt_excerpt=excerpt,
            status=STATUS_RUNNING,
            phase=PHASE_INTERPRETING,
            started_at=now,
            updated_at=now,
        )
        with self._lock:
            self._by_id[rec.task_request_id] = rec
            self._by_session[rec.session_id] = rec.task_request_id
        self._emit(rec, on_update, force=True)
        return rec

    def note_phase(
        self,
        task_request_id: str,
        phase: str,
        *,
        status: Optional[str] = None,
        summary: str = "",
        selected_method: str = "",
        on_update: Optional[TaskUpdateCallback] = None,
        force: bool = False,
    ) -> Optional[TaskRecord]:
        with self._lock:
            rec = self._by_id.get(str(task_request_id))
            if rec is None:
                return None
            if rec.status in _TERMINAL and not force:
                return rec
            changed = False
            phase_s = str(phase or "").strip()
            if phase_s and phase_s != rec.phase:
                rec.phase = phase_s
                changed = True
            if status and status != rec.status:
                rec.status = str(status)
                changed = True
            if summary:
                rec.summary = str(summary)[:240]
                changed = True
            if selected_method:
                rec.selected_method = str(selected_method)
                changed = True
            if not changed and not force:
                return rec
            rec.updated_at = time.time()
            snapshot = TaskRecord(**asdict(rec))
        self._emit(snapshot, on_update, force=force)
        return snapshot

    def settle(
        self,
        task_request_id: str,
        *,
        status: str,
        summary: str = "",
        error: str = "",
        error_code: str = "",
        phase: Optional[str] = None,
        on_update: Optional[TaskUpdateCallback] = None,
    ) -> Optional[TaskRecord]:
        final = str(status or STATUS_COMPLETED).strip() or STATUS_COMPLETED
        with self._lock:
            rec = self._by_id.get(str(task_request_id))
            if rec is None:
                return None
            now = time.time()
            rec.status = final
            rec.phase = str(phase or PHASE_FINISHING)
            rec.updated_at = now
            rec.ended_at = now
            rec.duration_ms = max(0, int(round((now - rec.started_at) * 1000)))
            if summary:
                rec.summary = str(summary)[:240]
            if error:
                rec.error = str(error)[:400]
            if error_code:
                rec.error_code = str(error_code).strip().lower()
            active = self._by_session.get(rec.session_id)
            if active == rec.task_request_id:
                self._by_session.pop(rec.session_id, None)
            snapshot = TaskRecord(**asdict(rec))
        self._emit(snapshot, on_update, force=True)
        return snapshot

    def get(self, task_request_id: str) -> Optional[TaskRecord]:
        with self._lock:
            rec = self._by_id.get(str(task_request_id))
            return TaskRecord(**asdict(rec)) if rec else None

    def active_for_session(self, session_id: str) -> Optional[TaskRecord]:
        with self._lock:
            tid = self._by_session.get(str(session_id))
            if not tid:
                return None
            rec = self._by_id.get(tid)
            return TaskRecord(**asdict(rec)) if rec else None

    def complete_payload(self, task_request_id: str) -> Dict[str, Any]:
        """Fields to merge onto message.complete (TaskOutcomeFacts)."""
        from plugin.agent.runtime.error_codes import resolve_user_message

        rec = self.get(task_request_id)
        if rec is None:
            return {}
        message = ""
        if rec.error_code:
            message = resolve_user_message(
                rec.error_code, override=rec.summary or rec.error
            )
        return TaskOutcomeFacts(
            task_request_id=rec.task_request_id,
            final_status=rec.status,
            duration_ms=rec.duration_ms,
            phase=rec.phase,
            summary=rec.summary or "",
            error_code=rec.error_code or "",
            message=message,
        ).to_complete_payload()

    def _emit(
        self,
        rec: TaskRecord,
        on_update: Optional[TaskUpdateCallback],
        *,
        force: bool,
    ) -> None:
        if on_update is None:
            return
        now = time.time()
        with self._lock:
            last = self._last_emit_at.get(rec.task_request_id, 0.0)
            if not force and (now - last) < self._throttle_s:
                return
            self._last_emit_at[rec.task_request_id] = now
        try:
            on_update(rec.to_payload())
        except Exception:
            pass


_GLOBAL = TaskTracker()


def get_task_tracker() -> TaskTracker:
    return _GLOBAL


def reset_task_tracker_for_tests() -> None:
    global _GLOBAL
    _GLOBAL = TaskTracker()


def final_status_from_turn(turn_status: str, *, interrupted: bool = False) -> str:
    """Map TurnStatus / gateway flags → tracker final_status."""
    return _final_status_from_turn(turn_status, interrupted=interrupted)
