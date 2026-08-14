"""Day-0 MemoryPipeline — identity bootstrap + interaction aggregates.

Incremental / idempotent via SourceCursor. Episode is optional.
Conservative SourceIdentity → CanonicalEntity linking.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from plugin.agent.memory import ids
from plugin.agent.memory.types import (
    CanonicalEntity,
    IdentityLink,
    InteractionAggregate,
    MemoryEvent,
    ProjectionState,
    RelationshipRecord,
    SourceIdentity,
)

PIPELINE_VERSION = "day0-v1"
USER_ENTITY_ID = "user:local"
DEFAULT_SCOPE = "personal:user:local:private"


@dataclass
class ContactObservation:
    """Normalized contact/channel observation from a source adapter.

    Frequency fields are 0 when unknown unless ``frequency_known`` is True.
    Never fabricate frequency from unread counts.
    """

    provider: str
    external_id: str
    display_name: str
    aliases: list[str] = field(default_factory=list)
    last_interaction_at: Optional[float] = None
    interaction_count_30d: int = 0
    interaction_count_7d: int = 0
    interaction_count_180d: int = 0
    active_days_30d: int = 0
    frequency_known: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    source_identities: int = 0
    entities: int = 0
    links: int = 0
    aggregates: int = 0
    events: int = 0
    unresolved_clusters: int = 0


class MemoryPipeline:
    """Composable Day-0 tasks: 2A identity then 2B aggregates + projections."""

    def __init__(self, store: Any, *, user_entity_id: str = USER_ENTITY_ID) -> None:
        self.store = store
        self.user_entity_id = user_entity_id
        # Ensure user entity exists
        self.store.upsert_entity(
            CanonicalEntity(
                entity_id=user_entity_id,
                entity_type="person",
                canonical_name="User",
                aliases=[],
                scope=DEFAULT_SCOPE,
            )
        )

    def ingest_contacts(
        self,
        source_name: str,
        observations: Sequence[ContactObservation],
        *,
        cursor_value: Optional[str] = None,
    ) -> PipelineResult:
        """Idempotent ingest. Does not false-merge ambiguous same-name contacts."""
        result = PipelineResult()
        now = time.time()
        name_buckets: dict[str, list[str]] = {}  # normalized name → entity_ids

        for obs in observations:
            evt_id = self.store.append_event(
                MemoryEvent(
                    event_id=ids.event_id(),
                    event_type="source_observation.contact",
                    source=source_name,
                    payload={
                        "provider": obs.provider,
                        "external_id": obs.external_id,
                        "display_name": obs.display_name,
                        "aliases": list(obs.aliases),
                        "interaction_count_30d": obs.interaction_count_30d,
                        "last_interaction_at": obs.last_interaction_at,
                    },
                    event_time=obs.last_interaction_at,
                    ingestion_time=now,
                    scope=DEFAULT_SCOPE,
                    provenance=f"{source_name}:{obs.provider}:{obs.external_id}",
                )
            )
            result.events += 1

            sid = SourceIdentity(
                source_identity_id="",
                provider=obs.provider,
                external_id=obs.external_id,
                display_name=obs.display_name,
                aliases=list(obs.aliases),
                metadata=dict(obs.metadata),
                scope=DEFAULT_SCOPE,
                ingestion_time=now,
            )
            sid_id = self.store.upsert_source_identity(sid)
            result.source_identities += 1

            # Conservative link: one SourceIdentity → one CanonicalEntity.
            # Same display name from different external_ids stays separate unless
            # external_id already linked (idempotent re-ingest).
            existing_links = self._links_for_source(sid_id)
            if existing_links:
                entity_id = existing_links[0]
            else:
                entity_id = ids.entity_id()
                aliases = list(
                    dict.fromkeys(
                        [obs.display_name, *obs.aliases]
                    )
                )
                self.store.upsert_entity(
                    CanonicalEntity(
                        entity_id=entity_id,
                        entity_type="person",
                        canonical_name=obs.display_name or obs.external_id,
                        aliases=aliases,
                        scope=DEFAULT_SCOPE,
                        confidence=1.0,
                        metadata={"bootstrap": True},
                    )
                )
                result.entities += 1
                self.store.link_identity(
                    IdentityLink(
                        link_id=ids.link_id(),
                        source_identity_id=sid_id,
                        entity_id=entity_id,
                        confidence=1.0,
                        evidence_refs=[evt_id],
                        status="linked",
                    )
                )
                result.links += 1

            # Track name buckets for diagnostics only — do NOT auto-merge.
            key = (obs.display_name or "").strip().lower()
            if key:
                name_buckets.setdefault(key, [])
                if entity_id not in name_buckets[key]:
                    name_buckets[key].append(entity_id)

            # 2B: interaction aggregates — frequency only when source says known
            continuity = 0.0
            if obs.frequency_known and obs.active_days_30d:
                continuity = min(1.0, obs.active_days_30d / 30.0)
            meta = dict(obs.metadata or {})
            meta["frequency_known"] = bool(obs.frequency_known)
            self.store.upsert_interaction_aggregate(
                InteractionAggregate(
                    aggregate_id="",
                    subject_id=self.user_entity_id,
                    object_id=entity_id,
                    count_7d=obs.interaction_count_7d if obs.frequency_known else 0,
                    count_30d=obs.interaction_count_30d if obs.frequency_known else 0,
                    count_180d=obs.interaction_count_180d if obs.frequency_known else 0,
                    last_interaction_at=obs.last_interaction_at,
                    active_days_30d=obs.active_days_30d if obs.frequency_known else 0,
                    continuity=continuity,
                    scope=DEFAULT_SCOPE,
                    evidence_refs=[evt_id],
                    updated_at=now,
                    metadata=meta,
                )
            )
            result.aggregates += 1

        for names, ents in name_buckets.items():
            if len(ents) > 1:
                result.unresolved_clusters += 1

        watermark = cursor_value or f"{source_name}:{now}"
        self.store.set_source_cursor(source_name, watermark)
        self.rebuild_recent_entities_projection(watermark=watermark)
        return result

    def assert_relationship(
        self,
        *,
        subject_id: str,
        predicate: str,
        object_id: str,
        assertion_text: str,
        confidence: float = 1.0,
    ) -> str:
        """Direct Event → Relationship (no Episode required)."""
        evt = ids.event_id()
        self.store.append_event(
            MemoryEvent(
                event_id=evt,
                event_type="user_assertion",
                source="user",
                payload={
                    "text": assertion_text,
                    "subject_id": subject_id,
                    "predicate": predicate,
                    "object_id": object_id,
                },
                event_time=time.time(),
                ingestion_time=time.time(),
                scope=DEFAULT_SCOPE,
                provenance="user_assertion",
                entity_ids=[subject_id, object_id],
            )
        )
        return self.store.upsert_relationship(
            RelationshipRecord(
                relationship_id=ids.relationship_id(),
                subject_id=subject_id,
                predicate=predicate,
                object_id=object_id,
                confidence=confidence,
                valid_from=time.time(),
                observed_at=time.time(),
                last_supported_at=time.time(),
                evidence_refs=[evt],
                scope=DEFAULT_SCOPE,
            )
        )

    def record_disambiguation(
        self,
        *,
        surface_form: str,
        chosen_entity_id: str,
        rejected_entity_ids: Sequence[str],
        context: Optional[dict[str, Any]] = None,
    ) -> str:
        """ASK correction → EntityReferenceEvidence (not interaction frequency).

        Choosing "Pallavi PhonePe" is reference-resolution evidence, not proof
        of more recent messaging. Retrieval uses ``recent_disambiguation_support``.
        """
        evt = ids.event_id()
        now = time.time()
        self.store.append_event(
            MemoryEvent(
                event_id=evt,
                event_type="entity_disambiguation",
                source="user_correction",
                payload={
                    "surface_form": surface_form,
                    "chosen_entity_id": chosen_entity_id,
                    "rejected_entity_ids": list(rejected_entity_ids),
                    "context": dict(context or {}),
                },
                event_time=now,
                ingestion_time=now,
                scope=DEFAULT_SCOPE,
                provenance="entity_disambiguation",
                entity_ids=[chosen_entity_id, *rejected_entity_ids],
            )
        )
        self.store.record_reference_evidence(
            surface_form=surface_form,
            chosen_entity_id=chosen_entity_id,
            rejected_entity_ids=list(rejected_entity_ids),
            context=dict(context or {}),
            event_id=evt,
            scope=DEFAULT_SCOPE,
        )
        self.rebuild_recent_entities_projection(
            watermark=f"disambiguation:{evt}"
        )
        return evt

    def rebuild_recent_entities_projection(self, *, watermark: str) -> None:
        self.store.set_projection_state(
            ProjectionState(
                projection_name="RecentEntities",
                schema_version="1",
                source_watermark=watermark,
                built_at=time.time(),
                status="rebuilding",
            )
        )
        aggs = self.store.list_aggregates_for_subject(self.user_entity_id)
        scored: list[tuple[str, str, str, float, Optional[float], int]] = []
        for agg in aggs:
            ent = self.store.get_entity(agg.object_id)
            if ent is None:
                continue
            salience = min(
                1.0,
                0.5 * min(1.0, agg.count_30d / 50.0)
                + 0.5 * (1.0 if agg.last_interaction_at else 0.0),
            )
            # Recency boost
            if agg.last_interaction_at:
                days = max(0.0, (time.time() - float(agg.last_interaction_at)) / 86400.0)
                salience = min(1.0, salience * (1.0 - min(0.9, days / 365.0)) + 0.1)
            scored.append(
                (
                    ent.entity_id,
                    ent.scope,
                    ent.canonical_name,
                    salience,
                    agg.last_interaction_at,
                    0,
                )
            )
        scored.sort(key=lambda r: (r[3], r[4] or 0.0), reverse=True)
        ranked = [
            (e, s, n, sal, li, i) for i, (e, s, n, sal, li, _) in enumerate(scored)
        ]
        self.store.replace_recent_entities(ranked, watermark=watermark)

    def mark_projection_stale(self, name: str = "RecentEntities") -> None:
        state = self.store.get_projection_state(name)
        if state is None:
            state = ProjectionState(projection_name=name, status="stale")
        else:
            state = ProjectionState(
                projection_name=state.projection_name,
                schema_version=state.schema_version,
                source_watermark=state.source_watermark,
                built_at=state.built_at,
                status="stale",
                metadata=dict(state.metadata),
            )
        self.store.set_projection_state(state)

    def _links_for_source(self, source_identity_id: str) -> list[str]:
        rows = self.store._conn.execute(
            """
            SELECT entity_id FROM identity_links
            WHERE source_identity_id = ? AND status = 'linked'
            """,
            (source_identity_id,),
        ).fetchall()
        return [r["entity_id"] for r in rows]
