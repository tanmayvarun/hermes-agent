"""MemorySystem Protocol + NoopMemorySystem (thin C seam).

Design-neutral about async: methods are sync callables so existing closed-loop
code can call them without an event loop; future backends may wrap async IO
behind this façade. Do not assume retrieval is always an instantaneous
in-process lookup.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol, Sequence, runtime_checkable

from plugin.agent.memory.types import (
    MemoryCandidate,
    MemoryEvidence,
    MemoryInvalidationResult,
    MemoryWriteResult,
)


@runtime_checkable
class MemorySystem(Protocol):
    def retrieve(
        self,
        query: str,
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
    """

    def retrieve(
        self,
        query: str,
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
