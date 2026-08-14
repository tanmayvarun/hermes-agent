"""Local SQLite MemorySystem — EventStore ≠ rebuildable derived stores."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Union

from plugin.agent.memory import ids
from plugin.agent.memory.schema import DDL, SCHEMA_VERSION
from plugin.agent.memory.types import (
    CanonicalEntity,
    IdentityLink,
    InteractionAggregate,
    MemoryCandidate,
    MemoryDerivation,
    MemoryEvidence,
    MemoryEvidencePacket,
    MemoryEvent,
    MemoryInvalidationResult,
    MemoryQuery,
    MemoryRecord,
    MemoryWriteResult,
    ProjectionState,
    RelationshipRecord,
    SourceIdentity,
)


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _loads(s: Optional[str], default: Any) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return default


def default_memory_root() -> Path:
    """macOS Application Support path; falls back to ~/.hermes/memory."""
    home = Path.home()
    app_support = home / "Library" / "Application Support" / "Hermes" / "memory"
    if (home / "Library" / "Application Support").is_dir():
        return app_support
    return home / ".hermes" / "memory"


class LocalMemorySystem:
    """Evidence authority: append_event / retrieve / submit / invalidate.

    Does NOT expose resolve_entity — that is EntityResolver cognition.
    """

    def __init__(self, root: Optional[Union[str, Path]] = None) -> None:
        self.root = Path(root) if root is not None else default_memory_root()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "blobs").mkdir(exist_ok=True)
        (self.root / "vectors").mkdir(exist_ok=True)
        self.db_path = self.root / "memory.db"
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def _init_schema(self) -> None:
        self._conn.executescript(DDL)
        cur = self._conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        )
        row = cur.fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO schema_meta(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Events (immutable evidence)
    # ------------------------------------------------------------------

    def append_event(self, event: MemoryEvent) -> str:
        now = time.time()
        eid = event.event_id or ids.event_id()
        self._conn.execute(
            """
            INSERT INTO events(
                event_id, event_type, source, event_time, ingestion_time, scope,
                actor, payload_json, payload_ref, provenance,
                entity_ids_json, source_identity_ids_json, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eid,
                event.event_type,
                event.source,
                event.event_time,
                event.ingestion_time if event.ingestion_time is not None else now,
                event.scope,
                event.actor,
                _json(event.payload),
                event.payload_ref,
                event.provenance,
                _json(event.entity_ids),
                _json(event.source_identity_ids),
                _json(event.metadata),
            ),
        )
        self._conn.commit()
        return eid

    def get_event(self, event_id: str) -> Optional[MemoryEvent]:
        row = self._conn.execute(
            "SELECT * FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if row is None:
            return None
        return MemoryEvent(
            event_id=row["event_id"],
            event_type=row["event_type"],
            source=row["source"],
            payload=_loads(row["payload_json"], {}),
            event_time=row["event_time"],
            ingestion_time=row["ingestion_time"],
            scope=row["scope"],
            actor=row["actor"] or "",
            entity_ids=_loads(row["entity_ids_json"], []),
            source_identity_ids=_loads(row["source_identity_ids_json"], []),
            payload_ref=row["payload_ref"] or "",
            provenance=row["provenance"] or "",
            metadata=_loads(row["metadata_json"], {}),
        )

    def scan_events(
        self,
        *,
        event_type: Optional[str] = None,
        after_ingestion: Optional[float] = None,
        limit: int = 1000,
    ) -> list[MemoryEvent]:
        clauses: list[str] = []
        args: list[Any] = []
        if event_type:
            clauses.append("event_type = ?")
            args.append(event_type)
        if after_ingestion is not None:
            clauses.append("ingestion_time > ?")
            args.append(after_ingestion)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        args.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM events{where} ORDER BY ingestion_time ASC LIMIT ?",
            args,
        ).fetchall()
        out: list[MemoryEvent] = []
        for row in rows:
            out.append(
                MemoryEvent(
                    event_id=row["event_id"],
                    event_type=row["event_type"],
                    source=row["source"],
                    payload=_loads(row["payload_json"], {}),
                    event_time=row["event_time"],
                    ingestion_time=row["ingestion_time"],
                    scope=row["scope"],
                    actor=row["actor"] or "",
                    entity_ids=_loads(row["entity_ids_json"], []),
                    source_identity_ids=_loads(row["source_identity_ids_json"], []),
                    payload_ref=row["payload_ref"] or "",
                    provenance=row["provenance"] or "",
                    metadata=_loads(row["metadata_json"], {}),
                )
            )
        return out

    # ------------------------------------------------------------------
    # Entities / source identities / links
    # ------------------------------------------------------------------

    def upsert_source_identity(self, sid: SourceIdentity) -> str:
        now = time.time()
        sid_id = sid.source_identity_id or ids.source_identity_id()
        existing = self._conn.execute(
            """
            SELECT source_identity_id FROM source_identities
            WHERE provider = ? AND external_id = ? AND scope = ?
            """,
            (sid.provider, sid.external_id, sid.scope),
        ).fetchone()
        if existing:
            sid_id = existing["source_identity_id"]
            self._conn.execute(
                """
                UPDATE source_identities SET display_name = ?, aliases_json = ?,
                metadata_json = ?, ingestion_time = ?
                WHERE source_identity_id = ?
                """,
                (
                    sid.display_name,
                    _json(sid.aliases),
                    _json(sid.metadata),
                    sid.ingestion_time if sid.ingestion_time is not None else now,
                    sid_id,
                ),
            )
        else:
            self._conn.execute(
                """
                INSERT INTO source_identities(
                    source_identity_id, provider, external_id, display_name,
                    aliases_json, scope, ingestion_time, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid_id,
                    sid.provider,
                    sid.external_id,
                    sid.display_name,
                    _json(sid.aliases),
                    sid.scope,
                    sid.ingestion_time if sid.ingestion_time is not None else now,
                    _json(sid.metadata),
                ),
            )
        self._conn.commit()
        return sid_id

    def upsert_entity(self, entity: CanonicalEntity) -> str:
        now = time.time()
        eid = entity.entity_id or ids.entity_id()
        row = self._conn.execute(
            "SELECT entity_id FROM entities WHERE entity_id = ?", (eid,)
        ).fetchone()
        if row:
            self._conn.execute(
                """
                UPDATE entities SET entity_type = ?, canonical_name = ?,
                aliases_json = ?, confidence = ?, updated_at = ?, metadata_json = ?
                WHERE entity_id = ?
                """,
                (
                    entity.entity_type,
                    entity.canonical_name,
                    _json(entity.aliases),
                    entity.confidence,
                    now,
                    _json(entity.metadata),
                    eid,
                ),
            )
        else:
            self._conn.execute(
                """
                INSERT INTO entities(
                    entity_id, entity_type, canonical_name, aliases_json,
                    scope, confidence, created_at, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eid,
                    entity.entity_type,
                    entity.canonical_name,
                    _json(entity.aliases),
                    entity.scope,
                    entity.confidence,
                    entity.created_at if entity.created_at is not None else now,
                    now,
                    _json(entity.metadata),
                ),
            )
        self._conn.commit()
        return eid

    def link_identity(self, link: IdentityLink) -> str:
        lid = link.link_id or ids.link_id()
        now = time.time()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO identity_links(
                link_id, source_identity_id, entity_id, confidence,
                evidence_refs_json, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lid,
                link.source_identity_id,
                link.entity_id,
                link.confidence,
                _json(link.evidence_refs),
                link.status,
                link.created_at if link.created_at is not None else now,
            ),
        )
        self._conn.commit()
        return lid

    def get_entity(self, entity_id: str) -> Optional[CanonicalEntity]:
        row = self._conn.execute(
            "SELECT * FROM entities WHERE entity_id = ?", (entity_id,)
        ).fetchone()
        if row is None:
            return None
        return CanonicalEntity(
            entity_id=row["entity_id"],
            entity_type=row["entity_type"],
            canonical_name=row["canonical_name"],
            aliases=_loads(row["aliases_json"], []),
            scope=row["scope"],
            confidence=row["confidence"],
            metadata=_loads(row["metadata_json"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def find_entities_by_name(self, name: str, *, scope: Optional[str] = None) -> list[CanonicalEntity]:
        needle = (name or "").strip().lower()
        if not needle:
            return []
        rows = self._conn.execute("SELECT * FROM entities").fetchall()
        out: list[CanonicalEntity] = []
        for row in rows:
            if scope and row["scope"] != scope:
                continue
            names = [row["canonical_name"], *_loads(row["aliases_json"], [])]
            if any(needle == (n or "").strip().lower() for n in names) or any(
                needle in (n or "").strip().lower() for n in names
            ):
                out.append(
                    CanonicalEntity(
                        entity_id=row["entity_id"],
                        entity_type=row["entity_type"],
                        canonical_name=row["canonical_name"],
                        aliases=_loads(row["aliases_json"], []),
                        scope=row["scope"],
                        confidence=row["confidence"],
                        metadata=_loads(row["metadata_json"], {}),
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                )
        return out

    def channel_identities_for_entity(
        self, entity_id: str, *, provider: Optional[str] = None
    ) -> list[SourceIdentity]:
        rows = self._conn.execute(
            """
            SELECT s.* FROM source_identities s
            JOIN identity_links l ON l.source_identity_id = s.source_identity_id
            WHERE l.entity_id = ? AND l.status = 'linked'
            """,
            (entity_id,),
        ).fetchall()
        out: list[SourceIdentity] = []
        for row in rows:
            if provider and row["provider"] != provider:
                continue
            out.append(
                SourceIdentity(
                    source_identity_id=row["source_identity_id"],
                    provider=row["provider"],
                    external_id=row["external_id"],
                    display_name=row["display_name"] or "",
                    aliases=_loads(row["aliases_json"], []),
                    metadata=_loads(row["metadata_json"], {}),
                    scope=row["scope"],
                    ingestion_time=row["ingestion_time"],
                )
            )
        return out

    # ------------------------------------------------------------------
    # Relationships vs InteractionAggregates
    # ------------------------------------------------------------------

    def upsert_relationship(self, rel: RelationshipRecord) -> str:
        rid = rel.relationship_id or ids.relationship_id()
        now = time.time()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO relationships(
                relationship_id, subject_id, predicate, object_id, confidence,
                valid_from, valid_until, observed_at, last_supported_at,
                ingestion_time, evidence_refs_json, scope, metadata_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                rid,
                rel.subject_id,
                rel.predicate,
                rel.object_id,
                rel.confidence,
                rel.valid_from,
                rel.valid_until,
                rel.observed_at,
                rel.last_supported_at,
                rel.ingestion_time if rel.ingestion_time is not None else now,
                _json(rel.evidence_refs),
                rel.scope,
                _json(rel.metadata),
            ),
        )
        self._conn.commit()
        return rid

    def upsert_interaction_aggregate(self, agg: InteractionAggregate) -> str:
        now = time.time()
        existing = self._conn.execute(
            """
            SELECT aggregate_id FROM interaction_aggregates
            WHERE subject_id = ? AND object_id = ? AND scope = ?
            """,
            (agg.subject_id, agg.object_id, agg.scope),
        ).fetchone()
        aid = (
            existing["aggregate_id"]
            if existing
            else (agg.aggregate_id or ids.aggregate_id())
        )
        self._conn.execute(
            """
            INSERT OR REPLACE INTO interaction_aggregates(
                aggregate_id, subject_id, object_id, count_7d, count_30d,
                count_180d, last_interaction_at, active_days_30d, continuity,
                scope, evidence_refs_json, updated_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                aid,
                agg.subject_id,
                agg.object_id,
                agg.count_7d,
                agg.count_30d,
                agg.count_180d,
                agg.last_interaction_at,
                agg.active_days_30d,
                agg.continuity,
                agg.scope,
                _json(agg.evidence_refs),
                agg.updated_at if agg.updated_at is not None else now,
                _json(agg.metadata),
            ),
        )
        self._conn.commit()
        return aid

    def get_aggregate(
        self, subject_id: str, object_id: str, *, scope: str
    ) -> Optional[InteractionAggregate]:
        row = self._conn.execute(
            """
            SELECT * FROM interaction_aggregates
            WHERE subject_id = ? AND object_id = ? AND scope = ?
            """,
            (subject_id, object_id, scope),
        ).fetchone()
        if row is None:
            return None
        return InteractionAggregate(
            aggregate_id=row["aggregate_id"],
            subject_id=row["subject_id"],
            object_id=row["object_id"],
            count_7d=row["count_7d"],
            count_30d=row["count_30d"],
            count_180d=row["count_180d"],
            last_interaction_at=row["last_interaction_at"],
            active_days_30d=row["active_days_30d"],
            continuity=row["continuity"],
            scope=row["scope"],
            evidence_refs=_loads(row["evidence_refs_json"], []),
            updated_at=row["updated_at"],
            metadata=_loads(row["metadata_json"], {}),
        )

    def list_aggregates_for_subject(
        self, subject_id: str, *, scope: Optional[str] = None
    ) -> list[InteractionAggregate]:
        rows = self._conn.execute(
            "SELECT * FROM interaction_aggregates WHERE subject_id = ?",
            (subject_id,),
        ).fetchall()
        out: list[InteractionAggregate] = []
        for row in rows:
            if scope and row["scope"] != scope:
                continue
            out.append(
                InteractionAggregate(
                    aggregate_id=row["aggregate_id"],
                    subject_id=row["subject_id"],
                    object_id=row["object_id"],
                    count_7d=row["count_7d"],
                    count_30d=row["count_30d"],
                    count_180d=row["count_180d"],
                    last_interaction_at=row["last_interaction_at"],
                    active_days_30d=row["active_days_30d"],
                    continuity=row["continuity"],
                    scope=row["scope"],
                    evidence_refs=_loads(row["evidence_refs_json"], []),
                    updated_at=row["updated_at"],
                    metadata=_loads(row["metadata_json"], {}),
                )
            )
        return out

    # ------------------------------------------------------------------
    # Memory records (rebuildable derived)
    # ------------------------------------------------------------------

    def persist_memory(self, record: MemoryRecord) -> str:
        if not record.evidence_refs and not record.assertion_refs:
            raise ValueError("MemoryRecord requires evidence_refs or assertion_refs")
        mid = record.memory_id or ids.memory_id()
        now = time.time()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO memories(
                memory_id, kind, content_json, subject_entities_json,
                object_entities_json, predicate, confidence, valid_from,
                valid_until, observed_at, updated_at, ingestion_time, scope,
                evidence_refs_json, assertion_refs_json, derived_by,
                derivation_version, supersedes_json, contradicted_by_json,
                sensitivity, structured_payload_json, readable, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mid,
                record.kind,
                _json(record.content),
                _json(record.subject_entities),
                _json(record.object_entities),
                record.predicate,
                record.confidence,
                record.valid_from,
                record.valid_until,
                record.observed_at,
                record.updated_at if record.updated_at is not None else now,
                record.ingestion_time if record.ingestion_time is not None else now,
                record.scope,
                _json(record.evidence_refs),
                _json(record.assertion_refs),
                record.derived_by,
                record.derivation_version,
                _json(record.supersedes),
                _json(record.contradicted_by),
                record.sensitivity,
                _json(record.structured_payload),
                record.readable,
                record.status,
            ),
        )
        self._conn.commit()
        return mid

    def record_derivation(self, derivation: MemoryDerivation) -> str:
        did = derivation.derivation_id or ids.derivation_id()
        now = time.time()
        self._conn.execute(
            """
            INSERT INTO memory_derivations(
                derivation_id, output_memory_ids_json, input_event_ids_json,
                input_memory_ids_json, pipeline_name, pipeline_version, model,
                prompt_or_schema_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                did,
                _json(derivation.output_memory_ids),
                _json(derivation.input_event_ids),
                _json(derivation.input_memory_ids),
                derivation.pipeline_name,
                derivation.pipeline_version,
                derivation.model,
                derivation.prompt_or_schema_version,
                derivation.created_at if derivation.created_at is not None else now,
            ),
        )
        self._conn.commit()
        return did

    # ------------------------------------------------------------------
    # Projections / cursors
    # ------------------------------------------------------------------

    def set_projection_state(self, state: ProjectionState) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO projection_state(
                projection_name, schema_version, source_watermark, built_at,
                status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                state.projection_name,
                state.schema_version,
                state.source_watermark,
                state.built_at if state.built_at is not None else time.time(),
                state.status,
                _json(state.metadata),
            ),
        )
        self._conn.commit()

    def get_projection_state(self, name: str) -> Optional[ProjectionState]:
        row = self._conn.execute(
            "SELECT * FROM projection_state WHERE projection_name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return ProjectionState(
            projection_name=row["projection_name"],
            schema_version=row["schema_version"],
            source_watermark=row["source_watermark"] or "",
            built_at=row["built_at"],
            status=row["status"],
            metadata=_loads(row["metadata_json"], {}),
        )

    def replace_recent_entities(
        self,
        rows: Sequence[tuple[str, str, str, float, Optional[float], int]],
        *,
        watermark: str,
    ) -> None:
        """rows: (entity_id, scope, display_name, salience, last_interaction_at, rank)"""
        self._conn.execute("DELETE FROM recent_entities_projection")
        self._conn.executemany(
            """
            INSERT INTO recent_entities_projection(
                entity_id, scope, display_name, salience, last_interaction_at, rank
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            list(rows),
        )
        self.set_projection_state(
            ProjectionState(
                projection_name="RecentEntities",
                schema_version="1",
                source_watermark=watermark,
                built_at=time.time(),
                status="ready",
            )
        )

    def list_recent_entities(
        self, *, scope: Optional[str] = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        if scope:
            rows = self._conn.execute(
                """
                SELECT * FROM recent_entities_projection
                WHERE scope = ? ORDER BY rank ASC LIMIT ?
                """,
                (scope, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM recent_entities_projection
                ORDER BY rank ASC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_source_cursor(self, source_name: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT cursor_value FROM source_cursors WHERE source_name = ?",
            (source_name,),
        ).fetchone()
        return row["cursor_value"] if row else None

    def set_source_cursor(self, source_name: str, cursor_value: str) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO source_cursors(source_name, cursor_value, updated_at)
            VALUES (?, ?, ?)
            """,
            (source_name, cursor_value, time.time()),
        )
        self._conn.commit()

    def get_bootstrap_state(self) -> str:
        row = self._conn.execute(
            "SELECT value FROM bootstrap_state WHERE key = 'state'"
        ).fetchone()
        return str(row["value"]) if row else "NOT_STARTED"

    def set_bootstrap_state(self, state: str) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO bootstrap_state(key, value, updated_at)
            VALUES ('state', ?, ?)
            """,
            (state, time.time()),
        )
        self._conn.commit()

    def record_reference_evidence(
        self,
        *,
        surface_form: str,
        chosen_entity_id: str,
        rejected_entity_ids: Sequence[str],
        context: Optional[Mapping[str, Any]] = None,
        event_id: str = "",
        scope: str = "personal:user:local:private",
    ) -> str:
        eid = ids.new_id("ref")
        self._conn.execute(
            """
            INSERT INTO entity_reference_evidence(
                evidence_id, surface_form, chosen_entity_id,
                rejected_entity_ids_json, context_json, event_id, created_at, scope
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eid,
                (surface_form or "").strip().lower(),
                chosen_entity_id,
                _json(list(rejected_entity_ids)),
                _json(dict(context or {})),
                event_id,
                time.time(),
                scope,
            ),
        )
        self._conn.commit()
        return eid

    def recent_reference_support(
        self, surface_form: str, entity_id: str, *, within_days: float = 90.0
    ) -> float:
        """1.0 if this entity was recently chosen for this surface form."""
        needle = (surface_form or "").strip().lower()
        if not needle or not entity_id:
            return 0.0
        cutoff = time.time() - within_days * 86400.0
        row = self._conn.execute(
            """
            SELECT chosen_entity_id FROM entity_reference_evidence
            WHERE surface_form = ? AND created_at >= ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (needle, cutoff),
        ).fetchone()
        if row is None:
            return 0.0
        return 1.0 if row["chosen_entity_id"] == entity_id else 0.0

    # ------------------------------------------------------------------
    # MemorySystem Protocol surface
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: Union[str, MemoryQuery, Mapping[str, Any]],
        *,
        context: Optional[Mapping[str, Any]] = None,
        limit: int = 8,
    ) -> Sequence[MemoryEvidence]:
        from plugin.agent.memory.retriever import MemoryRetriever

        packet = MemoryRetriever(self).retrieve(query, context=context, limit=limit)
        return packet.evidence

    def retrieve_packet(
        self,
        query: Union[str, MemoryQuery, Mapping[str, Any]],
        *,
        context: Optional[Mapping[str, Any]] = None,
        limit: int = 8,
    ) -> MemoryEvidencePacket:
        from plugin.agent.memory.retriever import MemoryRetriever

        return MemoryRetriever(self).retrieve(query, context=context, limit=limit)

    def submit_candidate(self, candidate: MemoryCandidate) -> MemoryWriteResult:
        refs = list(candidate.evidence_refs or [])
        if candidate.provenance and candidate.provenance not in refs:
            refs.append(candidate.provenance)
        if not refs:
            return MemoryWriteResult(
                disposition="rejected",
                reason="missing_provenance",
                memory_id=None,
            )
        mid = ids.memory_id()
        record = MemoryRecord(
            memory_id=mid,
            kind=candidate.kind,
            content=candidate.content,
            subject_entities=[candidate.subject] if candidate.subject else [],
            confidence=candidate.confidence,
            scope=candidate.scope or "personal:user:local:private",
            evidence_refs=refs if candidate.kind != "assertion" else [],
            assertion_refs=refs if candidate.kind == "assertion" else [],
            structured_payload=dict(candidate.metadata or {}),
            readable=str(candidate.content)[:500],
        )
        # assertions use assertion_refs; others evidence_refs — ensure one set
        if not record.evidence_refs and not record.assertion_refs:
            record.evidence_refs = refs
        self.persist_memory(record)
        return MemoryWriteResult(
            disposition="persisted", reason="local_sqlite", memory_id=mid
        )

    def invalidate(
        self,
        memory_id: str,
        *,
        reason: str = "",
    ) -> MemoryInvalidationResult:
        row = self._conn.execute(
            "SELECT memory_id FROM memories WHERE memory_id = ?", (memory_id,)
        ).fetchone()
        if row is None:
            return MemoryInvalidationResult(
                disposition="not_found", reason=reason or "missing", memory_id=memory_id
            )
        self._conn.execute(
            "UPDATE memories SET status = 'invalidated', updated_at = ? WHERE memory_id = ?",
            (time.time(), memory_id),
        )
        self._conn.commit()
        return MemoryInvalidationResult(
            disposition="invalidated", reason=reason or "invalidated", memory_id=memory_id
        )
