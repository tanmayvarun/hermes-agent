"""Session-scoped runtime continuation (suspended ASK / intentions).

MIGRATION DEBT: this is a temporary module-global continuation store beside
TUI SessionDB and per-session RuntimeState. Longer-term, a single AgentSession
should own active intention, pending ASK, declined method scope, RuntimeState,
and memory/session handles. Wire cleanup when the Hermes session ends.
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
    permission_granted: bool = False
    interpretation_notes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionRuntimeState:
    session_id: str
    runtime_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    suspended_ask: Optional[SuspendedAsk] = None
    declined_method_ids: Set[str] = field(default_factory=set)
    declined_preconditions: Set[str] = field(default_factory=set)
    # Verified precondition facts (session-scoped) — not AgentRuntime instance fields.
    precondition_facts: Dict[str, bool] = field(default_factory=dict)
    active_intention_id: str = ""
    last_trace: Dict[str, Any] = field(default_factory=dict)
    original_user_turn: str = ""


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
    """Call when the underlying Hermes/TUI session ends."""
    with _LOCK:
        _SESSIONS.pop(str(session_id or "").strip(), None)


def reset_session_store() -> None:
    with _LOCK:
        _SESSIONS.clear()
