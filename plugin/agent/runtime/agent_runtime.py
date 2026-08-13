"""Thin AgentRuntime façade — owns RuntimeState + MemorySystem one-way.

Ownership invariant:

    AgentRuntime
    ├── RuntimeState
    ├── MemorySystem
    └── TaskRequest / SessionRef

RuntimeState must not backreference AgentRuntime.
Construction has no MemorySystem side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from plugin.agent.ingress import SessionRef, TaskRequest
from plugin.agent.memory.system import MemorySystem, NoopMemorySystem
from plugin.agent.runtime.state import RuntimeState


@dataclass
class AgentRuntime:
    """HermesRuntime façade for the common ingress seam."""

    runtime_state: RuntimeState
    memory: MemorySystem = field(default_factory=NoopMemorySystem)
    task_request: Optional[TaskRequest] = None
    session: Optional[SessionRef] = None

    def __post_init__(self) -> None:
        if self.runtime_state is None:
            raise TypeError("AgentRuntime requires runtime_state")
        if self.memory is None:
            self.memory = NoopMemorySystem()
        if self.session is None and self.task_request is not None:
            self.session = self.task_request.session
        # Construction must not touch MemorySystem (no retrieve/submit/invalidate).
