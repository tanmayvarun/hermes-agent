"""Session-scoped runtime continuation (suspended ASK / intentions).

Sessions belong to the runtime, not the client. TaskRequest holds SessionRef only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set
import threading
import uuid


@dataclass
class SuspendedAsk:
    intention_id: str
    method_id: str
    precondition: str
    question: str
    parent_effect: str = ""
    interpretation_notes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionRuntimeState:
    session_id: str
    runtime_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    suspended_ask: Optional[SuspendedAsk] = None
    declined_method_ids: Set[str] = field(default_factory=set)
    declined_preconditions: Set[str] = field(default_factory=set)
    active_intention_id: str = ""
    last_trace: Dict[str, Any] = field(default_factory=dict)


_LOCK = threading.RLock()
_SESSIONS: Dict[str, SessionRuntimeState] = {}


def get_or_create_session(session_id: str) -> SessionRuntimeState:
    sid = str(session_id or "").strip() or "anonymous"
    with _LOCK:
        st = _SESSIONS.get(sid)
        if st is None:
            st = SessionRuntimeState(session_id=sid)
            _SESSIONS[sid] = st
        return st


def clear_session(session_id: str) -> None:
    with _LOCK:
        _SESSIONS.pop(str(session_id or "").strip(), None)


def reset_session_store() -> None:
    with _LOCK:
        _SESSIONS.clear()
