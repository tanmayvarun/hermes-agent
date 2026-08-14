"""MemorySystem package — durable knowledge beside Executive (not a substrate).

Hard invariant: MemorySystem = evidence authority.
EntityResolver / RoleBinder / ActionRiskPolicy live outside this package surface
for interpretation, commit, and risk (see cognition.py).
"""

from plugin.agent.memory.system import MemorySystem, NoopMemorySystem
from plugin.agent.memory.types import (
    BindingUncertainty,
    CanonicalEntity,
    EntityBindingProposal,
    InteractionAggregate,
    MemoryCandidate,
    MemoryEvidence,
    MemoryEvidencePacket,
    MemoryEvent,
    MemoryInvalidationResult,
    MemoryQuery,
    MemoryRecord,
    MemoryWriteResult,
    ProjectionState,
    RankedCandidate,
    RecallCandidate,
    RelationshipRecord,
    SourceIdentity,
)

__all__ = [
    "BindingUncertainty",
    "CanonicalEntity",
    "EntityBindingProposal",
    "InteractionAggregate",
    "MemoryCandidate",
    "MemoryEvidence",
    "MemoryEvidencePacket",
    "MemoryEvent",
    "MemoryInvalidationResult",
    "MemoryQuery",
    "MemoryRecord",
    "MemorySystem",
    "MemoryWriteResult",
    "NoopMemorySystem",
    "ProjectionState",
    "RankedCandidate",
    "RecallCandidate",
    "RelationshipRecord",
    "SourceIdentity",
]
