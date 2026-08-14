"""Memory types — evidence ≠ truth; MemoryCandidate ≠ durable MemoryRecord.

Canonical shapes follow docs/design/memorydesign.md. resolve_entity is NOT here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence, Union


# ---------------------------------------------------------------------------
# Seam types (existing — keep stable)
# ---------------------------------------------------------------------------


@dataclass
class MemoryCandidate:
    """May be worth remembering. Not yet durable persistence."""

    kind: str
    content: Any
    provenance: str = ""
    scope: str = "task"
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


# ---------------------------------------------------------------------------
# Scope / IDs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemoryScope:
    namespace: str = "personal"
    principal: str = "user:local"
    visibility: str = "private"

    def as_str(self) -> str:
        return f"{self.namespace}:{self.principal}:{self.visibility}"


# ---------------------------------------------------------------------------
# Evidence layer
# ---------------------------------------------------------------------------


@dataclass
class MemoryEvent:
    """Immutable-ish observation. ADD-only foundation."""

    event_id: str
    event_type: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_time: Optional[float] = None  # world validity / when it happened
    ingestion_time: Optional[float] = None  # when Hermes learned it
    scope: str = "personal:user:local:private"
    actor: str = ""
    entity_ids: list[str] = field(default_factory=list)
    source_identity_ids: list[str] = field(default_factory=list)
    payload_ref: str = ""
    provenance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Episode:
    """Optional derivation layer — not mandatory Event→Memory path."""

    episode_id: str
    event_refs: list[str] = field(default_factory=list)
    entity_ids: list[str] = field(default_factory=list)
    summary: str = ""
    scope: str = "personal:user:local:private"
    event_time_start: Optional[float] = None
    event_time_end: Optional[float] = None
    ingestion_time: Optional[float] = None
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Identity / relationship / aggregates
# ---------------------------------------------------------------------------


@dataclass
class SourceIdentity:
    """Channel- or source-specific identity (whatsapp:W17, contacts:C81)."""

    source_identity_id: str
    provider: str
    external_id: str
    display_name: str = ""
    aliases: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    scope: str = "personal:user:local:private"
    ingestion_time: Optional[float] = None


@dataclass
class CanonicalEntity:
    entity_id: str
    entity_type: str = "person"
    canonical_name: str = ""
    aliases: list[str] = field(default_factory=list)
    scope: str = "personal:user:local:private"
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[float] = None
    updated_at: Optional[float] = None


@dataclass
class IdentityLink:
    """SourceIdentity → CanonicalEntity (conservative merges only)."""

    link_id: str
    source_identity_id: str
    entity_id: str
    confidence: float = 1.0
    evidence_refs: list[str] = field(default_factory=list)
    status: str = "linked"  # linked | unresolved_cluster | superseded
    created_at: Optional[float] = None


@dataclass
class RelationshipRecord:
    """Semantic relationship predicate — not behavioral analytics."""

    relationship_id: str
    subject_id: str
    predicate: str
    object_id: str
    confidence: float = 1.0
    valid_from: Optional[float] = None
    valid_until: Optional[float] = None
    observed_at: Optional[float] = None
    last_supported_at: Optional[float] = None
    ingestion_time: Optional[float] = None
    evidence_refs: list[str] = field(default_factory=list)
    scope: str = "personal:user:local:private"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InteractionAggregate:
    """Behavioral metrics between two entities — separate from Relationship."""

    aggregate_id: str
    subject_id: str
    object_id: str
    count_7d: int = 0
    count_30d: int = 0
    count_180d: int = 0
    last_interaction_at: Optional[float] = None
    active_days_30d: int = 0
    continuity: float = 0.0
    scope: str = "personal:user:local:private"
    evidence_refs: list[str] = field(default_factory=list)
    updated_at: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryRecord:
    """Durable derived or asserted memory — always has provenance."""

    memory_id: str
    kind: str
    content: Any
    subject_entities: list[str] = field(default_factory=list)
    object_entities: list[str] = field(default_factory=list)
    predicate: str = ""
    confidence: float = 0.0
    valid_from: Optional[float] = None
    valid_until: Optional[float] = None
    observed_at: Optional[float] = None
    updated_at: Optional[float] = None
    ingestion_time: Optional[float] = None
    scope: str = "personal:user:local:private"
    evidence_refs: list[str] = field(default_factory=list)
    assertion_refs: list[str] = field(default_factory=list)
    derived_by: str = ""
    derivation_version: str = ""
    supersedes: list[str] = field(default_factory=list)
    contradicted_by: list[str] = field(default_factory=list)
    sensitivity: str = "normal"
    structured_payload: dict[str, Any] = field(default_factory=dict)
    readable: str = ""
    status: str = "active"  # active | superseded | invalidated


@dataclass
class MemoryDerivation:
    """Inspectable transform that produced derived memory."""

    derivation_id: str
    output_memory_ids: list[str] = field(default_factory=list)
    input_event_ids: list[str] = field(default_factory=list)
    input_memory_ids: list[str] = field(default_factory=list)
    pipeline_name: str = ""
    pipeline_version: str = ""
    model: str = ""
    prompt_or_schema_version: str = ""
    created_at: Optional[float] = None


# ---------------------------------------------------------------------------
# Projections
# ---------------------------------------------------------------------------


@dataclass
class ProjectionState:
    """Freshness contract — stale hot views must not masquerade as truth."""

    projection_name: str
    schema_version: str = "1"
    source_watermark: str = ""
    built_at: Optional[float] = None
    status: str = "ready"  # ready | rebuilding | stale | failed
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_fresh(self) -> bool:
        return self.status == "ready"


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


@dataclass
class MemoryQuery:
    """Structured retrieval query — not bare string search alone."""

    purpose: str = "factual_recall"
    # entity_resolution | factual_recall | episodic_recall |
    # procedural_recall | preference_lookup
    text: str = ""
    entities: list[str] = field(default_factory=list)
    predicates: list[str] = field(default_factory=list)
    time_range: Optional[tuple[Optional[float], Optional[float]]] = None
    scopes: list[str] = field(default_factory=list)
    current_context: dict[str, Any] = field(default_factory=dict)
    recall_budget: int = 50
    latency_budget_ms: int = 100
    requester: str = ""
    accessible_scopes: list[str] = field(default_factory=list)
    limit: int = 8


@dataclass
class RetrievalPlan:
    exact_entity_lookup: bool = True
    alias_lookup: bool = True
    fts_lookup: bool = True
    relationship_lookup: bool = True
    recency_lookup: bool = True
    hot_projection_lookup: bool = True
    vector_lookup: bool = False
    per_source_budget: int = 20
    total_latency_budget_ms: int = 100


@dataclass
class RecallCandidate:
    """Admitted by at least one recall arm — not yet ranked/selected."""

    ref: str
    ref_kind: str = "entity"  # entity | memory | relationship | aggregate
    recall_sources: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RankedCandidate:
    """Post-fusion ranked candidate with explanation."""

    ref: str
    ref_kind: str = "entity"
    feature_scores: dict[str, float] = field(default_factory=dict)
    final_score: float = 0.0
    explanation: str = ""
    recall_sources: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryEvidencePacket:
    """Small evidence packet for ContextAssembler / EntityResolver."""

    query_purpose: str = ""
    recall: list[RecallCandidate] = field(default_factory=list)
    ranked: list[RankedCandidate] = field(default_factory=list)
    evidence: list[MemoryEvidence] = field(default_factory=list)
    projection_states: list[ProjectionState] = field(default_factory=list)
    provenance_summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Binding uncertainty (EntityResolver / ActionRiskPolicy)
# ---------------------------------------------------------------------------


@dataclass
class BindingUncertainty:
    """Structured ambiguity for ActionRiskPolicy — not just margin floats."""

    top_candidate: str = ""
    alternatives: list[str] = field(default_factory=list)
    confidence: float = 0.0
    margin: float = 0.0
    ambiguity_reasons: list[str] = field(default_factory=list)
    evidence_quality: float = 0.0
    feature_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class EntityBindingProposal:
    """Interpretation output — RoleBinder remains commit authority."""

    role: str
    entity_id: str = ""
    surface_form: str = ""
    alternatives: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    uncertainty: BindingUncertainty = field(default_factory=BindingUncertainty)
    ranked: list[RankedCandidate] = field(default_factory=list)


MemoryQueryLike = Union[str, MemoryQuery, Mapping[str, Any]]
