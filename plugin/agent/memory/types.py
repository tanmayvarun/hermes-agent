"""Memory types — MemoryCandidate ≠ MemoryRecord; structured write outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class MemoryCandidate:
    """May be worth remembering. Not yet a durable MemoryRecord."""

    kind: str
    content: Any
    provenance: str = ""
    scope: str = "task"
    confidence: float = 0.0
    subject: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryRecord:
    """Durable memory shape (stub for the seam — no store in this slice).

    Distinct from MemoryCandidate: records exist only after write policy accepts.
    """

    memory_id: str
    kind: str
    content: Any
    provenance: str = ""
    scope: str = "session"
    confidence: float = 0.0
    subject: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryEvidence:
    """Retrieved memory as evidence — never automatic world/task truth."""

    memory_id: str
    kind: str
    content: Any
    provenance: str = ""
    scope: str = "session"
    confidence: float = 0.0
    subject: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryWriteResult:
    """Structured outcome of submit_candidate.

    runtime submitted memory ≠ memory was persisted.
    """

    disposition: str  # ignored | accepted | persisted | rejected
    reason: str = ""
    memory_id: Optional[str] = None


@dataclass(frozen=True)
class MemoryInvalidationResult:
    """Structured outcome of invalidate / forget."""

    disposition: str  # ignored | invalidated | not_found | rejected
    reason: str = ""
    memory_id: Optional[str] = None
