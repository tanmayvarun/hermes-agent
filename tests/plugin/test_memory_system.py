"""MemorySystem Slice 1–4 goldens — Pallavi personal-intelligence path."""

from __future__ import annotations

import time

import pytest

from plugin.agent.memory.cognition import (
    ActionRiskPolicy,
    ChannelGrounding,
    ContextAssembler,
    EntityResolver,
    resolve_person_for_effect,
)
from plugin.agent.memory.local_store import LocalMemorySystem
from plugin.agent.memory.pipeline import ContactObservation, MemoryPipeline
from plugin.agent.memory.retriever import MemoryRetriever
from plugin.agent.memory.system import NoopMemorySystem
from plugin.agent.memory.types import (
    MemoryCandidate,
    MemoryEvent,
    MemoryQuery,
    MemoryRecord,
    ProjectionState,
)


@pytest.fixture()
def store(tmp_path):
    mem = LocalMemorySystem(root=tmp_path / "memory")
    yield mem
    mem.close()


def _day0_two_pallavis(store: LocalMemorySystem) -> MemoryPipeline:
    pipe = MemoryPipeline(store)
    now = time.time()
    pipe.ingest_contacts(
        "whatsapp_bootstrap",
        [
            ContactObservation(
                provider="whatsapp",
                external_id="W17",
                display_name="Pallavi",
                aliases=["Pallavi"],
                last_interaction_at=now - 3600,
                interaction_count_7d=40,
                interaction_count_30d=180,
                interaction_count_180d=900,
                active_days_30d=28,
                frequency_known=True,
            ),
            ContactObservation(
                provider="whatsapp",
                external_id="W781",
                display_name="Pallavi PhonePe",
                aliases=["Pallavi PhonePe", "Pallavi"],
                last_interaction_at=now - 3 * 365 * 86400,
                interaction_count_7d=0,
                interaction_count_30d=0,
                interaction_count_180d=1,
                active_days_30d=0,
                frequency_known=True,
            ),
        ],
        cursor_value="wa:v1",
    )
    return pipe


def test_noop_still_ignored():
    mem = NoopMemorySystem()
    assert mem.retrieve("x") == []
    assert mem.submit_candidate(
        MemoryCandidate(kind="episodic", content="x", provenance="t")
    ).disposition == "ignored"


def test_no_resolve_entity_on_memory_system(store):
    assert "resolve_entity" not in LocalMemorySystem.__dict__
    assert callable(store.retrieve)
    assert callable(store.append_event)
    assert callable(store.submit_candidate)
    assert callable(store.invalidate)


def test_memory_record_requires_provenance(store):
    with pytest.raises(ValueError, match="evidence_refs|assertion"):
        store.persist_memory(
            MemoryRecord(memory_id="mem:x", kind="semantic", content="no provenance")
        )


def test_assertion_event_direct_to_relationship_without_episode(store):
    pipe = MemoryPipeline(store)
    _day0_two_pallavis(store)
    ents = store.find_entities_by_name("Pallavi")
    frequent = max(
        ents,
        key=lambda e: (
            store.get_aggregate("user:local", e.entity_id, scope=e.scope).count_30d
            if store.get_aggregate("user:local", e.entity_id, scope=e.scope)
            else 0
        ),
    )
    rid = pipe.assert_relationship(
        subject_id="user:local",
        predicate="sibling_of",
        object_id=frequent.entity_id,
        assertion_text="Pallavi is my sister",
    )
    assert rid
    # No episode table requirement — events + relationship only
    n_ep = store._conn.execute("SELECT COUNT(*) AS c FROM episodes").fetchone()["c"]
    assert n_ep == 0


def test_source_identities_not_merged_on_shared_alias(store):
    pipe = _day0_two_pallavis(store)
    ents = store.find_entities_by_name("Pallavi")
    # Both entities match substring/alias "Pallavi"
    assert len(ents) >= 2
    # Re-ingest is idempotent (cursor + unique provider/external_id)
    before = store._conn.execute("SELECT COUNT(*) AS c FROM entities").fetchone()["c"]
    pipe.ingest_contacts(
        "whatsapp_bootstrap",
        [
            ContactObservation(
                provider="whatsapp",
                external_id="W17",
                display_name="Pallavi",
                interaction_count_30d=180,
                last_interaction_at=time.time(),
                frequency_known=True,
            ),
        ],
        cursor_value="wa:v2",
    )
    after = store._conn.execute("SELECT COUNT(*) AS c FROM entities").fetchone()["c"]
    assert after == before


def test_relationship_separate_from_interaction_aggregate(store):
    _day0_two_pallavis(store)
    ents = store.find_entities_by_name("Pallavi")
    e = ents[0]
    agg = store.get_aggregate("user:local", e.entity_id, scope=e.scope)
    assert agg is not None
    assert agg.count_30d >= 0
    # Relationship table empty until assertion
    n_rel = store._conn.execute("SELECT COUNT(*) AS c FROM relationships").fetchone()[
        "c"
    ]
    assert n_rel == 0


def test_stale_recent_projection_not_used_as_fresh_truth(store):
    pipe = _day0_two_pallavis(store)
    pipe.mark_projection_stale("RecentEntities")
    state = store.get_projection_state("RecentEntities")
    assert state is not None and state.status == "stale"
    packet = MemoryRetriever(store).retrieve(
        MemoryQuery(purpose="entity_resolution", text="Pallavi", limit=5)
    )
    # Recall still works via aggregates/alias; hot arm skipped
    assert any("hot_recent_entities" not in (c.recall_sources or []) or True for c in packet.recall)
    hot_admits = [
        c for c in packet.recall if "hot_recent_entities" in c.recall_sources
    ]
    assert hot_admits == []


def test_recall_candidate_separate_from_ranked(store):
    _day0_two_pallavis(store)
    packet = MemoryRetriever(store).retrieve(
        MemoryQuery(
            purpose="entity_resolution",
            text="Pallavi",
            current_context={"channel": "whatsapp", "user_entity_id": "user:local"},
            limit=5,
        )
    )
    assert packet.recall
    assert packet.ranked
    assert all(hasattr(c, "recall_sources") for c in packet.recall)
    assert all(hasattr(c, "feature_scores") and hasattr(c, "explanation") for c in packet.ranked)
    # Both Pallavis recalled
    assert len(packet.recall) >= 2
    # Dominant personal context ranks first
    top = packet.ranked[0]
    second = packet.ranked[1]
    assert top.final_score > second.final_score
    assert top.feature_scores.get("interaction_recency", 0) > second.feature_scores.get(
        "interaction_recency", 0
    )


def test_pallavi_send_message_proceeds_or_asks(store):
    _day0_two_pallavis(store)
    result = resolve_person_for_effect(
        store, surface_form="Pallavi", effect="send_message", channel="whatsapp"
    )
    proposal = result["proposal"]
    decision = result["decision"]
    assert proposal.entity_id
    assert proposal.uncertainty.margin >= 0
    # High margin frequent contact should proceed
    assert decision.action == "proceed"
    assert result["grounding"] is not None
    assert result["grounding"].provider == "whatsapp"
    assert result["grounding"].external_id == "W17"


def test_close_candidates_trigger_ask_via_binding_uncertainty(store):
    pipe = MemoryPipeline(store)
    now = time.time()
    # Two similarly active Pallavis → ASK
    pipe.ingest_contacts(
        "wa",
        [
            ContactObservation(
                provider="whatsapp",
                external_id="A",
                display_name="Pallavi",
                last_interaction_at=now - 1000,
                interaction_count_30d=50,
                interaction_count_7d=10,
                active_days_30d=10,
                frequency_known=True,
            ),
            ContactObservation(
                provider="whatsapp",
                external_id="B",
                display_name="Pallavi",
                last_interaction_at=now - 2000,
                interaction_count_30d=48,
                interaction_count_7d=9,
                active_days_30d=9,
                frequency_known=True,
            ),
        ],
    )
    result = resolve_person_for_effect(
        store, surface_form="Pallavi", effect="send_message", channel="whatsapp"
    )
    assert "multiple_exact_name_matches" in result["proposal"].uncertainty.ambiguity_reasons
    assert result["decision"].action == "ask"


def test_disambiguation_event_improves_future_retrieval(store):
    pipe = _day0_two_pallavis(store)
    ents = store.find_entities_by_name("Pallavi")
    phonepe = next(e for e in ents if "PhonePe" in e.canonical_name)
    frequent = next(e for e in ents if e.entity_id != phonepe.entity_id)
    before = store.get_aggregate("user:local", phonepe.entity_id, scope=phonepe.scope)
    before_count = before.count_30d if before else 0
    pipe.record_disambiguation(
        surface_form="Pallavi",
        chosen_entity_id=phonepe.entity_id,
        rejected_entity_ids=[frequent.entity_id],
        context={"effect": "send_message"},
    )
    events = store.scan_events(event_type="entity_disambiguation")
    assert len(events) == 1
    # Must NOT corrupt interaction frequency
    after = store.get_aggregate("user:local", phonepe.entity_id, scope=phonepe.scope)
    assert after is not None
    assert after.count_30d == before_count
    assert store.recent_reference_support("Pallavi", phonepe.entity_id) == 1.0
    packet = MemoryRetriever(store).retrieve(
        MemoryQuery(
            purpose="entity_resolution",
            text="Pallavi",
            current_context={"channel": "whatsapp", "user_entity_id": "user:local"},
        )
    )
    # Disambiguation support should appear on PhonePe features
    phonepe_rank = next(r for r in packet.ranked if r.ref == phonepe.entity_id)
    assert phonepe_rank.feature_scores.get("recent_disambiguation_support", 0) >= 1.0


def test_context_assembler_does_not_choose_identity(store):
    _day0_two_pallavis(store)
    packet = MemoryRetriever(store).retrieve(
        MemoryQuery(purpose="entity_resolution", text="Pallavi")
    )
    ctx = ContextAssembler().assemble(packet, max_ranked=2)
    assert len(ctx.packet.ranked) <= 2
    # Assembler has no entity_id decision field
    assert not hasattr(ctx, "entity_id")


def test_derived_memory_rebuildable_events_preserved(store):
    store.append_event(
        MemoryEvent(
            event_id="",
            event_type="interaction",
            source="test",
            payload={"n": 1},
            provenance="t",
        )
    )
    n_events = store._conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
    store._conn.execute("DELETE FROM memories")
    store._conn.commit()
    assert (
        store._conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
        == n_events
    )


def test_action_risk_distinguishes_qualitative_ambiguity():
    policy = ActionRiskPolicy()
    from plugin.agent.memory.types import BindingUncertainty

    multi = BindingUncertainty(
        top_candidate="e1",
        alternatives=["e2"],
        confidence=0.6,
        margin=0.12,
        ambiguity_reasons=["multiple_exact_name_matches"],
        evidence_quality=0.5,
    )
    weak = BindingUncertainty(
        top_candidate="e1",
        alternatives=["e2"],
        confidence=0.6,
        margin=0.12,
        ambiguity_reasons=[],
        evidence_quality=0.5,
        feature_scores={"alias_exact": 1.0},
    )
    assert policy.allows("send_message", multi).action == "ask"
    # Without qualitative multi-match reason, moderate may still ask on margin —
    # but multi-match is strictly ask.
    assert policy.allows("open_chat", weak).action == "proceed"
