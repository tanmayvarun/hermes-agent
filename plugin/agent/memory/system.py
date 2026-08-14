"""MemorySystem Protocol + NoopMemorySystem.

Authority: evidence only. resolve_entity is NOT on this Protocol.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol, Sequence, Union, runtime_checkable

from plugin.agent.memory.types import (
    MemoryCandidate,
    MemoryEvidence,
    MemoryEvent,
    MemoryInvalidationResult,
    MemoryQuery,
    MemoryWriteResult,
)

MemoryQueryLike = Union[str, MemoryQuery, Mapping[str, Any]]


@runtime_checkable
class MemorySystem(Protocol):
    def retrieve(
        self,
        query: MemoryQueryLike,
        *,
        context: Optional[Mapping[str, Any]] = None,
        limit: int = 8,
    ) -> Sequence[MemoryEvidence]:
        """Return evidence-bearing memories. Never auto-called by TaskIngress."""
        ...

    def submit_candidate(self, candidate: MemoryCandidate) -> MemoryWriteResult:
        """Offer a candidate for write policy. May ignore, accept, or persist."""
        ...

    def invalidate(
        self,
        memory_id: str,
        *,
        reason: str = "",
    ) -> MemoryInvalidationResult:
        """Invalidate / forget by id (structured outcome)."""
        ...


class NoopMemorySystem:
    """In-memory seam placeholder — does not persist.

    Writes report disposition=ignored so callers cannot confuse submit with persist.
    Optional append_event is a no-op for LocalMemorySystem parity in tests.
    """

    def retrieve(
        self,
        query: MemoryQueryLike,
        *,
        context: Optional[Mapping[str, Any]] = None,
        limit: int = 8,
    ) -> list[MemoryEvidence]:
        return []

    def submit_candidate(self, candidate: MemoryCandidate) -> MemoryWriteResult:
        return MemoryWriteResult(
            disposition="ignored",
            reason="noop_memory_system",
            memory_id=None,
        )

    def invalidate(
        self,
        memory_id: str,
        *,
        reason: str = "",
    ) -> MemoryInvalidationResult:
        return MemoryInvalidationResult(
            disposition="ignored",
            reason=reason or "noop_memory_system",
            memory_id=memory_id or None,
        )

    def append_event(self, event: MemoryEvent) -> str:
        return event.event_id or ""
