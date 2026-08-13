"""MemorySystem package — durable knowledge beside Executive (not a substrate)."""

from plugin.agent.memory.system import MemorySystem, NoopMemorySystem
from plugin.agent.memory.types import (
    MemoryCandidate,
    MemoryEvidence,
    MemoryInvalidationResult,
    MemoryWriteResult,
)

__all__ = [
    "MemoryCandidate",
    "MemoryEvidence",
    "MemoryInvalidationResult",
    "MemorySystem",
    "MemoryWriteResult",
    "NoopMemorySystem",
]
