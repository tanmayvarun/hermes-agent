"""SQLite schema for LocalMemorySystem (logical store separation)."""

from __future__ import annotations

SCHEMA_VERSION = 1

DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    event_time REAL,
    ingestion_time REAL NOT NULL,
    scope TEXT NOT NULL,
    actor TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    payload_ref TEXT,
    provenance TEXT,
    entity_ids_json TEXT NOT NULL DEFAULT '[]',
    source_identity_ids_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS episodes (
    episode_id TEXT PRIMARY KEY,
    event_refs_json TEXT NOT NULL DEFAULT '[]',
    entity_ids_json TEXT NOT NULL DEFAULT '[]',
    summary TEXT,
    scope TEXT NOT NULL,
    event_time_start REAL,
    event_time_end REAL,
    ingestion_time REAL,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS source_identities (
    source_identity_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    display_name TEXT,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    scope TEXT NOT NULL,
    ingestion_time REAL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(provider, external_id, scope)
);

CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    scope TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    created_at REAL,
    updated_at REAL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS identity_links (
    link_id TEXT PRIMARY KEY,
    source_identity_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'linked',
    created_at REAL,
    FOREIGN KEY(source_identity_id) REFERENCES source_identities(source_identity_id),
    FOREIGN KEY(entity_id) REFERENCES entities(entity_id)
);

CREATE TABLE IF NOT EXISTS relationships (
    relationship_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_id TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    valid_from REAL,
    valid_until REAL,
    observed_at REAL,
    last_supported_at REAL,
    ingestion_time REAL,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    scope TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS interaction_aggregates (
    aggregate_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    object_id TEXT NOT NULL,
    count_7d INTEGER NOT NULL DEFAULT 0,
    count_30d INTEGER NOT NULL DEFAULT 0,
    count_180d INTEGER NOT NULL DEFAULT 0,
    last_interaction_at REAL,
    active_days_30d INTEGER NOT NULL DEFAULT 0,
    continuity REAL NOT NULL DEFAULT 0.0,
    scope TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    updated_at REAL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(subject_id, object_id, scope)
);

CREATE TABLE IF NOT EXISTS memories (
    memory_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    content_json TEXT NOT NULL,
    subject_entities_json TEXT NOT NULL DEFAULT '[]',
    object_entities_json TEXT NOT NULL DEFAULT '[]',
    predicate TEXT,
    confidence REAL NOT NULL DEFAULT 0.0,
    valid_from REAL,
    valid_until REAL,
    observed_at REAL,
    updated_at REAL,
    ingestion_time REAL,
    scope TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    assertion_refs_json TEXT NOT NULL DEFAULT '[]',
    derived_by TEXT,
    derivation_version TEXT,
    supersedes_json TEXT NOT NULL DEFAULT '[]',
    contradicted_by_json TEXT NOT NULL DEFAULT '[]',
    sensitivity TEXT NOT NULL DEFAULT 'normal',
    structured_payload_json TEXT NOT NULL DEFAULT '{}',
    readable TEXT,
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS memory_derivations (
    derivation_id TEXT PRIMARY KEY,
    output_memory_ids_json TEXT NOT NULL DEFAULT '[]',
    input_event_ids_json TEXT NOT NULL DEFAULT '[]',
    input_memory_ids_json TEXT NOT NULL DEFAULT '[]',
    pipeline_name TEXT,
    pipeline_version TEXT,
    model TEXT,
    prompt_or_schema_version TEXT,
    created_at REAL
);

CREATE TABLE IF NOT EXISTS projection_state (
    projection_name TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    source_watermark TEXT,
    built_at REAL,
    status TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS source_cursors (
    source_name TEXT PRIMARY KEY,
    cursor_value TEXT NOT NULL,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS recent_entities_projection (
    entity_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    display_name TEXT,
    salience REAL NOT NULL DEFAULT 0.0,
    last_interaction_at REAL,
    rank INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(entity_id, scope)
);

CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(canonical_name);
CREATE INDEX IF NOT EXISTS idx_events_type_time ON events(event_type, event_time);
CREATE INDEX IF NOT EXISTS idx_relationships_pred ON relationships(predicate, subject_id);
CREATE INDEX IF NOT EXISTS idx_aggregates_object ON interaction_aggregates(object_id, last_interaction_at);
CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind, status);
"""
