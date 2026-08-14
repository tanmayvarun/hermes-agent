# Hermes MemorySystem design

**Status:** Architecture approved for implementation (post design-review + research + final contract tightenings).  
**Related:** [personal-agent-brain-and-substrates.md](personal-agent-brain-and-substrates.md),
[executive-runtime.md](executive-runtime.md),
[agent-design.md](agent-design.md).  
**Code seam today:** [`plugin/agent/memory/`](../../plugin/agent/memory/) — `MemorySystem` Protocol + `NoopMemorySystem` only.

**Research alignment:** Hermes is closer to **Graphiti/Zep + Memori** than to classic “vector = memory” systems. Borrow selectively from Mem0, Supermemory, Graphiti/Zep, Letta/MemGPT, Cognee, Memori, memU — do **not** copy any one architecture wholesale.

**Do not reopen architecture.** Implement Slices 1–4 with the contracts below. Vectors, semantic compaction, wiki views, graph DBs, and cloud sync stay deferred.

---

## Stance

> **Preserve raw evidence, derive structured memory, retrieve with multiple independent signals, keep temporal/provenance information, and assemble only a small context packet for the main brain.**

> **Memory is an append-only evidence system with intelligent derived views.
> Raw history is preserved; intelligence decides what higher-order memories to
> derive, strengthen, supersede, contextualize, and retrieve.**

Terminology:

- **Physical compaction** = LSM / WAL / index merge (storage). No intelligence required.
- **Semantic compaction** = consolidation / summarization into higher-order memories. Model-driven + evidence accounting. Distinct subsystem.
- **MemoryProjection** = rebuildable retrieval/materialization accelerator — **not** memory truth.
- **MemoryDerivation** = inspectable transform that produced derived memory (pipeline/model/schema version + inputs).

Never collapse:

```text
Evidence  ≠  Memory  ≠  Projection  ≠  Retrieval  ≠  Context  ≠  Belief  ≠  Action
```

### Hard authority invariant

```text
MemorySystem     = evidence authority   (retrieve / store / consolidate evidence)
EntityResolver   = interpretation authority  (who does this EntityRef mean?)
RoleBinder       = commit authority
ActionRiskPolicy = whether ambiguity is tolerable for this effect
Substrate        = environment grounding after canonical entity is committed
```

**`resolve_entity` is NOT a MemorySystem method.** Specialized retrieval via
`MemoryQuery(purpose=ENTITY_RESOLUTION)` is fine; final identity resolution
stays outside the store so MemorySystem never owns semantic commitments.

| Layer | Question | Authority |
|---|---|---|
| Evidence (events / episodes) | What happened / was observed? | Append-only EventStore |
| Canonical memory | What is worth remembering now? | Entity / Relationship / InteractionAggregate / Episode? / MemoryStore |
| Projections | How do we retrieve efficiently? | MemoryProjectionManager (rebuildable; freshness-tracked) |
| Retrieval / context | What matters for *this* prompt? | Retriever + ContextAssembler |
| Belief / binding | What does the task commit? | EntityResolver → RoleBinder |
| Action | How / whether to act? | Executive + ActionRiskPolicy → Substrate |

**Single most important principle:** never throw away evidence merely because a better abstraction was derived over it.

**Rebuildability test:** Can we rebuild every derived MemoryRecord **and every MemoryProjection** from the append log plus explicitly supplied assertion/import facts? If not, the source-of-truth boundary is already leaking.

---

## Canonical layered architecture (locked)

```text
                    SOURCE LAYER
Contacts / WhatsApp / Email / Calendar /
User assertions / Tool results / Agent actions /
Verified action effects / User corrections
                          ↓
                    EVENT STORE
immutable provenance-bearing observations
                          ↓
                  COGNITIVE PIPELINES
(versioned, composable, watermarked tasks)
identity extraction / linking /
optional episode formation /
relationships / interaction aggregates /
facts / preferences / procedures
                          ↓
                 CANONICAL MEMORY MODEL
 Entities
 Relationships          (semantic predicates)
 InteractionAggregates  (behavioral metrics)
 Episodes               (optional derivation layer)
 Semantic facts
 Preferences
 Procedures
 Environment mappings
                          ↓
                  MEMORY PROJECTIONS
 (rebuildable; ProjectionState watermark/freshness)
 exact / alias indexes
 FTS / BM25
 temporal indexes
 recent-entity / profile / active-context views
 vectors (later)
 graph adjacency
 human-readable wiki exports (optional)
                          ↓
                  RETRIEVAL PLANNER
 parallel recall → UNION → fusion → hydration
                          ↓
                 MEMORY EVIDENCE PACKET
                          ↓
                  CONTEXT ASSEMBLER
                          ↓
              ENTITY RESOLVER / BRAIN
                          ↓
                     ROLE BINDER
                          ↓
              CHANNEL / ENVIRONMENT GROUNDING
                          ↓
                   EXECUTION SUBSTRATE
```

Separately (later slices):

```text
new events / episodes
  → MemoryCognition / MemoryDerivation
  → versioned MemoryRecords
  → evidence remains untouched
  → projections recomputed
```

---

## Cognitive path (memory before method selection)

Wrong path:

```text
prompt → Goal(contact="Pallavi") → WhatsApp → search → UI decides identity
```

Target path:

```text
TUI / TaskRequest
  → InitialInterpretation
       recipient=EntityRef(surface_form="Pallavi", entity_id=UNRESOLVED)
       channel=WhatsApp
  → ContextNeed(entity_resolution)
  → (optional) hot projections: RecentEntities / CurrentUserProfile
  → MemoryQuery(purpose=ENTITY_RESOLUTION) if needed
  → RetrievalPlanner → RetrievalPlan
  → parallel recall arms → UNION → fusion → hydrate
  → MemoryEvidencePacket (scored candidates + retrieval provenance)
  → ContextAssembler (budget / dedupe / format only)
  → EntityResolver → BindingProposal
  → ActionRiskPolicy → RoleBinder.commit | ASK
  → ChannelIdentity → environment referent → substrate
```

```text
name match  ≠  entity identity  ≠  role binding
UI order / shortest fuzzy = retrieval evidence only, never identity commit
```

Memory retrieval is a **sub-cognitive operation**, not a top-level Hermes meta-action (THINK / PERCEIVE / SEARCH / EXPLORE / ACT / ASK remain). Explicit recall when context is missing is fine; stuffing all history into every prompt is not (Letta lesson).

---

## Industry research — borrow / do not borrow

| Project | Best idea for Hermes |
|---|---|
| **Mem0** | ADD-only history; entity linking; multi-signal retrieval; agent-generated facts as evidence |
| **Supermemory** | stable profile + dynamic context views; fast context API ≠ generic search |
| **Graphiti/Zep** | episodes → entities/relationships; provenance; bi-temporal facts; hybrid retrieval |
| **Letta/MemGPT** | hot attended set vs archival memory; explicit recall; versionable views |
| **Cognee** | versioned/composable cognition pipeline + storage adapters |
| **Memori** | remember agent execution; structured taxonomy; entity/process/session scopes |
| **memU** | human-readable wiki projection + background memorization |

### Do not borrow

1. **Vector DB ≠ memory.** Strong modern systems moved beyond this.
2. **LLM deciding every retrieval query on the hot path.** Prefer deterministic/indexed recall; intelligence only where it adds value.
3. **Aggressive destructive deletion of contradictions.** Prefer preserve evidence → supersede/invalidate derived current beliefs → down-rank stale → physical delete only for privacy/retention.
4. **Neo4j (or any graph DB) as the architecture.** Graph **model** ≠ graph **database**. SQLite for V1; `RelationshipStore` can swap backends later.
5. **Markdown/wiki as canonical memory.** Optional projection for inspectability/trust only.
6. **Mem0-style “vector candidates then others only boost.”** Hermes requires **independent recall arms that UNION**, then fuse — critical for names (Pallavi), IDs, dates, phones, filenames, rare facts.

Mem0 OSS v3 moved away from exposed graph-memory toward ADD-only extraction + hybrid signals (often boosting semantic candidates). Hermes goes further on recall independence. Graphiti remains the closest structural validation of Event → Episode → Entity/Relationship.

---

## Hard authority reminder

```text
Memory = evidence authority
EntityResolver = interpretation authority
RoleBinder = commit authority
```

---

## 1. EventStore — ADD-only evidence foundation

Events accumulate; history is not destroyed. Retrieval decides which dated/current fact matters — not overwrite-in-place.

```text
Event {
    event_id
    event_time              # when it happened in the world (if known)
    ingestion_time          # when Hermes learned it
    source
    subject_scope
    actor
    entities / source_identities
    event_type
    payload_ref
    metadata
    provenance
}
```

### First-class event sources (not conversation-only)

```text
user assertions
external-source observations (Contacts, WhatsApp metadata, Email, Calendar, …)
tool results
agent actions
verified action effects
user corrections / EntityDisambiguationEvent
```

Agent-execution memory is first-class (Memori/Mem0 lesson) but lives under **separate namespaces/policies** from personal memory (e.g. operational substrate failures vs people facts).

---

## 2. Episode — optional derivation layer (not mandatory)

Episodes are extremely useful for interaction history, conversations, meetings,
coding sessions, etc. They are **not** an obligatory normalization stage between
every Event and Memory.

```text
Event
 ├─→ Episode                    # optional (conversations, meetings, sessions)
 ├─→ Entity / Relationship update
 ├─→ InteractionAggregate update
 └─→ MemoryCandidate            # e.g. user assertion "Pallavi is my sister"

Episode
 └─→ higher-order memory
```

A durable relationship from an explicit assertion event may be written **directly**
from the event (+ provenance). Do not manufacture an Episode just because a
schema diagram once said Event→Episode→Memory.

When used, episodes are provenance-bearing coherent units:

```text
Episode {
    episode_id
    event_refs[]
    time_range (event_time)
    participants / entities
    summary?                 # optional derived; evidence_refs required if present
    scope
    ingestion_time
}
```

---

## 3. Logical stores (one SQLite physically OK)

| Store | Contents | Mutability |
|---|---|---|
| **EventStore** | immutable-ish historical observations | append; rare evidence deletion |
| **EpisodeStore** | optional coherent evidence units | append / light update; rebuildable summaries |
| **EntityStore** | CanonicalEntity, aliases, IdentityLinks, SourceIdentity | durable; conservative merges |
| **RelationshipStore** | semantic predicates (`sibling_of`, `works_with`, …) with temporal validity | durable / supersedable |
| **InteractionAggregateStore** | behavioral metrics (counts, recency, continuity) | rebuildable from events |
| **MemoryStore** | derived current interpretations / MemoryRecords | **fully rebuildable** |
| **ProjectionStore** | indexes & materialized views + ProjectionState | **fully rebuildable accelerators** |

```text
DROP / recompute derived MemoryRecords + projections
  without losing EventStore / raw episode evidence
```

**Graph model ≠ graph database.** Keep Entity / Relationship / Episode as concepts; implement in SQLite V1.

---

## 4. Bi-temporal semantics

Distinguish:

```text
event_time / validity time     — when a fact was true in the world
ingestion_time / knowledge time — when the memory system learned it
```

Example: “Pallavi worked at PhonePe until 2023” may be ingested in 2026. Both timestamps matter for personal and organizational memory.

Records carry (as applicable):

```text
valid_from / valid_until      # world validity
observed_at / last_supported_at
ingestion_time / learned_at   # knowledge time
```

Historical states remain queryable after invalidation (Graphiti lesson).

---

## 5. Provenance + MemoryDerivation

### Provenance invariant

```text
No MemoryRecord without provenance / evidence.

Derived memory:     evidence_refs required
Asserted memory:    assertion event required
Imported memory:    external-source observation required
```

### MemoryDerivation (inspectable transforms)

```text
MemoryDerivation {
    derivation_id
    output_memory_ids
    input_event_ids
    input_memory_ids
    pipeline_name
    pipeline_version
    model
    prompt_or_schema_version
    created_at
}
```

Answers: “Why does Hermes believe Pallavi is a frequent contact?”  
→ `relationship-aggregation-v4` from 183 interaction events, last recomputed ….  
Recompute with v5 without destroying evidence.

Other invariants: no overwriting history; contradiction → supersession; compaction replayable; model/version recorded.

---

## 6. Eight memory classes + WorkingContext

| Class | Purpose | Example |
|---|---|---|
| **Working Context** | current reasoning / session hypotheses | “two Pallavis are candidates” |
| **Episodic** | things that happened (via Episode) | “messaged Pallavi yesterday” |
| **Entity** | identity and aliases | `person:E123 = Pallavi Sharma` |
| **Relationship** | semantic predicates between entities | `sibling_of`, `works_with` |
| **Semantic / Factual** | durable declarative knowledge | “E123 works at …” |
| **Preference** | user conventions / desires | “user usually means E123 by ‘Pallavi’” |
| **Procedural** | reusable methods / skills | how this task class has been done |
| **Environment** | mappings to systems / channels | `E123 ↔ WhatsApp W17` |

Working Context = runtime cognition (attended set), **not** long-term store.

```text
LongTermMemory  ≠  currently attended memory
MemorySystem    → millions of records
ContextAssembler → ~5–30 relevant items
WorkingContext  → what the executive reasons over now
```

### Relationship vs InteractionAggregate (do not overload)

**Canonical Relationship** = semantic fact:

```text
user --sibling_of--> E123
user --works_with--> E456
```

with temporal validity + provenance (assertion event, import, etc.).

**InteractionAggregate** = behavioral metrics (separate store/record):

```text
InteractionAggregate {
    subject = user
    object  = E123
    count_7d / count_30d / count_180d
    last_interaction_at
    active_days_30d
    continuity
    …
}
```

Then:

```text
semantic relationship
  + behavioral interaction metrics
  → contextual_salience / frequent_contact (derived, policy-dependent)
```

Do not stuff analytics features into Relationship records.

---

## 7. SourceIdentity → CanonicalEntity

```text
SourceIdentity (whatsapp:W17, contacts:C81, …)
  → IdentityLink (conservative)
  → CanonicalEntity (person:E123)
```

**Fail closed on uncertain merges.** Wrong merges > missing merges. Interaction frequency must not force identity merges.

---

## 8. MemoryProjection (first-class, async, freshness-tracked)

Projections are **rebuildable optimized representations** derived from canonical memory/evidence — not another source of truth. ProjectionManager is explicitly **asynchronous/rebuildable**.

```text
ProjectionState {
    projection_name
    schema_version
    source_watermark
    built_at
    status                  # ready | rebuilding | stale | failed
}
```

Retrieval **must** know whether a hot projection is current enough. A stale `RecentEntities` view must **not** quietly masquerade as fresh truth or outrank newer interaction evidence merely because it is fast (Pallavi benchmark risk).

```text
MemoryProjectionManager
  ├─ ProjectionState registry
  ├─ EntityAliasIndex
  ├─ ExactNameIndex
  ├─ FTS / BM25 index
  ├─ TemporalIndex
  ├─ RelationshipAdjacency
  ├─ RecentInteractionProjection / RecentEntitiesView
  ├─ PersonalSalienceProjection
  ├─ CurrentUserProfile          # stable/high-confidence facts
  ├─ CurrentPersonalContext      # recent people, projects, tasks, interactions
  ├─ ActiveProjectsView
  ├─ VectorIndex                 # later
  └─ HumanReadableWikiExport     # optional inspectability
```

Architecture:

```text
EventStore → Canonical entities/relationships/aggregates/episodes?/memories
  → MemoryProjectionManager (rebuild from watermark)
  → fast prompt-time retrieval (only if ProjectionState is fresh enough)
```

Separates **what Hermes remembers** from **how Hermes efficiently retrieves it**.

### Hot views (Supermemory lesson)

For “send hi to Pallavi”, prefer a **fresh** hot view:

```text
CurrentPersonalContext.recent_people:
  E123 Pallavi — very high salience
```

If ProjectionState is stale, fall through to structured recall over InteractionAggregates / indexes. Full MemoryRetriever remains available when hot views are insufficient or stale.

Human-readable exports (memU-inspired):

```text
People/Pallavi.md   # what / why / from where / last supported
Projects/Hermes.md
Preferences.md
```

Materialized for trust/inspectability — **never** canonical.

---

## 9. Cognitive pipeline (Cognee lesson)

Not a monolithic `MemoryInitializer.run()`:

```text
MemoryPipeline {
    tasks[]
    pipeline_version
    watermark / SourceCursor per source
}
```

Composable, separately rerunnable/versioned stages:

```text
SourceObservation
  → normalize
  → extract SourceIdentities
  → entity linking (conservative)
  → episode formation
  → interaction aggregation
  → memory classification
  → materialize indexes / projections
```

Replay from evidence when models/compactors improve.

Initializer remains **incremental, restartable, idempotent** via per-source cursors.

| Phase | Content |
|---|---|
| **2A Identity** | SourceIdentity → CanonicalEntity; aliases; channel mappings |
| **2B Aggregates** | interaction features on *already linked* entities |
| **Hot projections** | RecentEntities / CurrentUserProfile / ActiveContext |
| **Later** | episodic summaries, semantic/preference/procedural derivation |

---

## 10. Retrieval — multi-source UNION then fusion

```text
MemoryQuery
  → RetrievalPlanner
  → RetrievalPlan {
        exact_entity_lookup
        alias_lookup
        FTS / BM25
        relationship_lookup
        recency / temporal
        vector?              # later
        procedural_index?
        hot_projection_lookup
        per_source_budget
        total_latency_budget
    }
  → PARALLEL RECALL (each arm may ADD candidates)
  → UNION → RecallCandidate[]
  → feature enrichment + fusion / ranking → RankedCandidate[]
  → hydration
  → MemoryEvidencePacket
```

**Recall and ranking stay separate typed stages** (do not conflate retrieved with selected — same bug Hermes has hit elsewhere):

```text
RecallCandidate {
    memory_or_entity_ref
    recall_sources[]          # which arms admitted this candidate
}

RankedCandidate {
    ref
    feature_scores            # alias, recency, frequency, channel, …
    final_score
    explanation               # why this rank
}
```

Pallavi example:

```text
Recall:
  E123 from exact alias + recent projection
  E847 from exact alias

Ranking:
  E123 high recency/frequency
  E847 stale
```

```text
Recall:  Did every relevant candidate have a chance to enter?
Ranking: Which recalled candidates matter most?
```

Initial planner deterministic; later MemoryCognition may smarten planning. Hot path does **not** require an LLM per query. Hot-projection arm must respect ProjectionState freshness.

---

## 11. ContextAssembler stays boring

Gather, dedupe, budget, format DecisionContext. **Does not** resolve identity.

---

## 12. EntityResolver, RoleBinder, ActionRiskPolicy, grounding, correction

```text
EntityResolver.resolve(EntityRef, MemoryEvidencePacket, WorkingContext)
  → BindingProposal {
        candidate
        alternatives
        evidence
        uncertainty: BindingUncertainty
    }

BindingUncertainty {
    top_candidate
    alternatives
    confidence
    margin
    ambiguity_reasons       # e.g. two equal names vs one exact + weak distractor
    evidence_quality
}

ActionRiskPolicy.allows(effect, BindingUncertainty) → proceed | ASK | refuse
RoleBinder.commit(...)
ChannelGrounding(entity_id, channel) → environment referent → substrate
```

Ambiguity tolerance is **effect-risk policy**, not fixed global score thresholds.
Similar numeric margins can have qualitatively different risk:

```text
two equally named contacts          → higher ambiguity risk
one exact identity + weak distractor → lower ambiguity risk
```

### Slice 4 normative correction loop (acceptance)

```text
ambiguous binding
  → ASK
  → user selects entity
  → execute task
  → append EntityDisambiguationEvent
  → update retrieval evidence / projections (even before semantic compaction)
```

Memory must improve from user corrections **immediately**. Do not instantly freeze the choice as immutable Preference.

Substrate never chooses among semantic person candidates; it maps committed entity → channel identity → UI/API surface.

---

## 13. Forgetting

| Mode | Default |
|---|---|
| Evidence deletion | Rare (privacy / legal / explicit user) |
| Derived supersession / invalidation | Normal |
| Retrieval down-ranking | Common |

ADD-only history preferred over destructive UPDATE/DELETE of evidence (Mem0 direction).

---

## 14. Scopes and MemoryPolicy

```text
scope / principal / task-session / workspace / agent / organization
```

Not merely `user_id → memories`. Same engine; Personal / Family / Organization policies differ on retention, salience weights, sources, privacy, ranking.

Personal vs agent-operational memory: **different namespaces/policies**.

---

## 15. Local storage (V1)

```text
~/Library/Application Support/Hermes/memory/
    events/
    memory.db       # events, episodes, entities, relationships, memories,
                    # derivations, projections metadata, source_cursors
    vectors/        # later
    blobs/
    exports/wiki/   # optional human-readable projections
```

Stable globally unique IDs: `event_id`, `episode_id`, `entity_id`, `source_identity_id`, `memory_id`, `derivation_id`, `projection_id`.

---

## 16. Component interfaces

```text
MemorySystem
├── EventStore
├── EpisodeStore                 # optional derivation
├── EntityStore
├── RelationshipStore            # semantic predicates
├── InteractionAggregateStore    # behavioral metrics
├── MemoryStore
├── BlobStore
├── MemoryProjectionManager      # ProjectionState + rebuild
├── VectorIndex              # later projection backend
├── MemoryRetriever          # RetrievalPlanner inside
├── MemoryPipeline / MemoryInitializer
├── MemoryConsolidator       # later (emits MemoryDerivation)
└── MemoryPolicy
```

MemorySystem API:

```text
append_event(event)
retrieve(MemoryQuery) → MemoryEvidencePacket
submit_candidate(candidate) → MemoryWriteDisposition
invalidate(memory_id, evidence)
# consolidate later
```

**Forbidden on MemorySystem:** `resolve_entity(...)`.

Outside: EntityResolver, RoleBinder, ActionRiskPolicy, ChannelGrounding.

---

## 17. Acceptance benchmark

```text
Day-0 metadata (2A + 2B) + hot RecentEntities projection.

User: "send hi to Pallavi on WhatsApp"

Hermes:
  personal context before execution (hot view only if ProjectionState fresh)
  RecallCandidate UNION admits both Pallavis with recall_sources
  RankedCandidate explains why E123 outranks E847 (or close margin)
  ActionRiskPolicy uses BindingUncertainty → proceed OR ASK
  if ASK: user select → execute → EntityDisambiguationEvent → projection/evidence update
  substrate grounds committed E123 → channel → surface
```

If Day-0 metadata cannot distinguish a highly active Pallavi from a stale duplicate—or at least ASK—the memory architecture has not produced personal intelligence. That is the step from UI automation agent toward personal agent.

### Goldens policy

Land when owning slice is green. Fixtures ahead OK. **No knowingly red merge-gate stubs.**

Key names: rebuildable derived+projections with ProjectionState; Episode optional; Relationship ≠ InteractionAggregate; RecallCandidate ≠ RankedCandidate; BindingUncertainty; conservative SourceIdentity merge; bi-temporal; multi-source UNION; no resolve_entity on MemorySystem; channel grounding after commit; ASK→disambiguation→immediate evidence update.

---

## 18. Implementation order (approved — stop adding architecture)

```text
stores → identity bootstrap → interaction aggregates/projections
  → structured retrieval → context/entity binding
```

1. **Slice 1** — EventStore / optional Episode / Entity / Relationship / InteractionAggregate / Memory schemas; bi-temporal + provenance + MemoryDerivation stub; ProjectionManager + ProjectionState skeleton; MemoryQuery Protocol (**no** resolve_entity)
2. **Slice 2A** — SourceIdentity → conservative CanonicalEntity; channel mappings; SourceCursor pipeline tasks
3. **Slice 2B** — InteractionAggregate metrics (not Relationship overload); salience projections; seed RecentEntities / profile with ProjectionState
4. **Slice 3** — RetrievalPlanner; parallel UNION → RecallCandidate[]; ranking → RankedCandidate[]; hot arm respects freshness
5. **Slice 4** — ContextAssembler + EntityResolver + BindingUncertainty + ActionRiskPolicy + normative ASK correction loop + channel grounding
6. Vectors as projection
7. MemoryCognition / semantic consolidation (full MemoryDerivation)
8. Procedural / preference consolidation
9. Cloud replication + shared scopes; optional wiki export projection

Fastest path to personal intelligence: **1 → 4**. Deferred: vectors, semantic compaction, wiki, graph DBs, cloud sync.

---

## 19. Code map

| Today | Target |
|---|---|
| Noop `MemorySystem` | Local append/retrieve/submit/invalidate only |
| `memory/types.py` | Event, Episode?, SourceIdentity, CanonicalEntity, RelationshipRecord, InteractionAggregate, MemoryRecord, MemoryDerivation, ProjectionState, MemoryQuery, RetrievalPlan, RecallCandidate, RankedCandidate, BindingUncertainty, EvidencePacket |
| `ResolutionMemory` | Evidence/aggregate input — not identity authority |
| `resolve_entity` capability | UI label ranker; personal EntityResolver separate |
| `RoleBinder` | Commit-only |
| Missing | InteractionAggregate, ProjectionState, Pipeline/cursors, RetrievalPlanner UNION, ContextAssembler, EntityResolver, ActionRiskPolicy, ChannelGrounding |

Roof doc: Executive ∥ MemorySystem authorities. This file: MemorySystem internals + EntityResolver boundary + research-backed projections/episodes/bi-temporal/derivation.
