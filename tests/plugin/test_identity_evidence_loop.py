"""Goldens: identity evidence-acquisition before ASK.

ASK is terminal information gathering after a bounded Brain budget —
not the first response to a narrow numeric margin.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from plugin.agent.brain.identity_evidence import (
    classify_name_match,
    gather_identity_evidence,
    hypotheses_from_ranked,
    reinterpret_identity_hypotheses,
    resolve_identity_with_evidence_loop,
)
from plugin.agent.goal import Goal
from plugin.agent.memory.bootstrap import open_local_memory
from plugin.agent.memory.pipeline import ContactObservation
from plugin.agent.memory.recipient_binding import resolve_recipient_before_methods
from plugin.agent.memory.sources import FixtureSourceAdapter
from plugin.agent.memory.types import RankedCandidate


def _rc(
    eid: str,
    name: str,
    *,
    score: float,
    recency: float = 0.0,
    frequency: float = 0.0,
    alias_exact: float = 0.0,
    aliases: list[str] | None = None,
) -> RankedCandidate:
    return RankedCandidate(
        ref=eid,
        ref_kind="entity",
        payload={"canonical_name": name, "aliases": aliases or [name]},
        feature_scores={
            "alias_exact": alias_exact,
            "interaction_recency": recency,
            "interaction_frequency": frequency,
        },
        final_score=score,
        explanation=name,
    )


def test_classify_name_match_kinds():
    assert classify_name_match("Pallavi", "Pallavi") == "exact"
    assert classify_name_match("Pallavi", "Pallavi Joshi") == "extended"
    assert classify_name_match("Pallavi", "Pallavi PhonePe") == "qualified_partial"
    assert classify_name_match("Pallavi", "Ravi") == "none"


def test_ambiguous_person_triggers_evidence_gathering_before_ask(tmp_path):
    """Close numeric margin must gather probes before asking the user."""
    now = time.time()
    # Joshi must NOT carry bare alias "Pallavi" or alias_exact ties defeat the
    # close-margin ASK path (recency_dominant clear_personal_margin).
    obs = [
        ContactObservation(
            provider="whatsapp",
            external_id="W_J",
            display_name="Pallavi Joshi",
            aliases=["Pallavi Joshi"],
            last_interaction_at=now - 3600,
            frequency_known=False,
        ),
        ContactObservation(
            provider="whatsapp",
            external_id="W_P",
            display_name="Pallavi",
            aliases=["Pallavi"],
            last_interaction_at=None,
            frequency_known=False,
        ),
        ContactObservation(
            provider="whatsapp",
            external_id="W_PP",
            display_name="Pallavi PhonePe",
            aliases=["Pallavi PhonePe"],
            last_interaction_at=now - 400 * 86400,
            frequency_known=False,
        ),
    ]
    store, _ = open_local_memory(
        root=tmp_path / "mem_ask",
        start_bootstrap=True,
        blocking_bootstrap=True,
        adapters=[FixtureSourceAdapter(source_name="wa", observations=obs)],
    )
    try:
        goal = Goal(
            kind="whatsapp_forward_message",
            contact="Pallavi",
            message_body="hi",
            app="WhatsApp",
        )
        rr = resolve_recipient_before_methods(
            store,
            goal=goal,
            desired_effects=["send_message"],
            channel="whatsapp",
            world_probes=False,
            evidence_budget=4,
        )
        assert rr.evidence_probes, "expected evidence probes before commit/ASK"
        assert "working_context_recheck" in rr.evidence_probes
        assert any("memory_" in p or "working_" in p for p in rr.evidence_probes)
        # After gathering: exact alias prior without contextual rival → proceed
        assert rr.status == "proceed"
        assert rr.channel_external_id == "W_P"
        assert rr.reason == "exact_alias_prior_without_contextual_rival"
    finally:
        store.close()


def test_additional_world_evidence_can_resolve_without_user_interrupt(monkeypatch):
    """World substrate enrichment can establish a winner without interrupting."""
    ranked = [
        _rc("e:joshi", "Pallavi Joshi", score=0.32, recency=0.0, aliases=["Pallavi Joshi"]),
        _rc(
            "e:phonepe",
            "Pallavi PhonePe",
            score=0.30,
            recency=0.0,
            aliases=["Pallavi PhonePe"],
        ),
    ]
    memory = SimpleNamespace()  # no aggregate / reference APIs

    def fake_wa(hyps, **_kwargs):
        for h in hyps:
            if "Joshi" in h.display_name:
                h.salience.frequency_known = True
                h.salience.frequency = 0.85
                h.gather_notes.append("wa_contacts:freq=0.85")
            else:
                h.salience.frequency_known = True
                h.salience.frequency = 0.05
                h.gather_notes.append("wa_contacts:freq=0.05")
        return "whatsapp_contacts_enrichment"

    monkeypatch.setattr(
        "plugin.agent.brain.identity_evidence._probe_whatsapp_contact_enrichment",
        fake_wa,
    )
    outcome = resolve_identity_with_evidence_loop(
        memory,
        ranked,
        surface="Pallavi",
        world_probes=True,
        budget=4,
    )
    assert outcome.action == "proceed"
    assert outcome.entity_id == "e:joshi"
    assert outcome.reason == "frequency_dominance"
    assert "whatsapp_contacts_enrichment" in outcome.probes_used


def test_exact_name_does_not_always_override_context():
    ranked = [
        _rc("e:exact", "Pallavi", score=0.30, alias_exact=1.0, aliases=["Pallavi"]),
        _rc(
            "e:joshi",
            "Pallavi Joshi",
            score=0.32,
            recency=0.95,
            aliases=["Pallavi Joshi"],
        ),
    ]
    hyps = hypotheses_from_ranked(
        ranked,
        surface="Pallavi",
        memory=SimpleNamespace(),
        working_context={
            "recent_entity_id": "e:joshi",
            "recent_entity_name": "Pallavi Joshi",
        },
    )
    outcome = reinterpret_identity_hypotheses(hyps, surface="Pallavi")
    assert outcome.action == "proceed"
    assert outcome.entity_id == "e:joshi"
    assert "working_context" in outcome.reason


def test_recent_partial_match_does_not_automatically_override_exact_alias():
    ranked = [
        _rc(
            "e:joshi",
            "Pallavi Joshi",
            score=0.32,
            recency=0.99,
            aliases=["Pallavi Joshi"],
        ),
        _rc("e:exact", "Pallavi", score=0.30, alias_exact=1.0, aliases=["Pallavi"]),
        _rc(
            "e:phonepe",
            "Pallavi PhonePe",
            score=0.07,
            aliases=["Pallavi PhonePe"],
        ),
    ]
    hyps = hypotheses_from_ranked(
        ranked,
        surface="Pallavi",
        memory=SimpleNamespace(),
        working_context={},
    )
    outcome = reinterpret_identity_hypotheses(hyps, surface="Pallavi")
    assert outcome.action == "proceed"
    assert outcome.entity_id == "e:exact"
    assert outcome.reason == "exact_alias_prior_without_contextual_rival"


def test_working_context_can_flip_person_resolution(tmp_path):
    now = time.time()
    obs = [
        ContactObservation(
            provider="whatsapp",
            external_id="W_P",
            display_name="Pallavi",
            aliases=["Pallavi"],
            last_interaction_at=now - 86400,
            interaction_count_30d=20,
            frequency_known=True,
        ),
        ContactObservation(
            provider="whatsapp",
            external_id="W_J",
            display_name="Pallavi Joshi",
            aliases=["Pallavi Joshi", "Pallavi"],
            last_interaction_at=now - 7200,
            interaction_count_30d=5,
            frequency_known=True,
        ),
    ]
    store, _ = open_local_memory(
        root=tmp_path / "mem_wc",
        start_bootstrap=True,
        blocking_bootstrap=True,
        adapters=[FixtureSourceAdapter(source_name="wa", observations=obs)],
    )
    try:
        ents = store.find_entities_by_name("Pallavi")
        joshi = next(e for e in ents if "Joshi" in e.canonical_name)
        goal = Goal(
            kind="whatsapp_forward_message",
            contact="Pallavi",
            message_body="hi",
            app="WhatsApp",
        )
        rr = resolve_recipient_before_methods(
            store,
            goal=goal,
            desired_effects=["send_message"],
            channel="whatsapp",
            working_context={
                "recent_entity_id": joshi.entity_id,
                "recent_entity_name": "Pallavi Joshi",
            },
            world_probes=False,
        )
        assert rr.status == "proceed"
        assert rr.channel_external_id == "W_J"
        assert "working_context" in (rr.reason or "") or rr.entity_id == joshi.entity_id
    finally:
        store.close()


def test_ask_only_after_identity_evidence_budget_exhausted():
    """Two exact peers with no discriminator → gather then ASK."""
    ranked = [
        _rc("e:a", "Pallavi", score=0.40, alias_exact=1.0, recency=0.5, aliases=["Pallavi"]),
        _rc("e:b", "Pallavi", score=0.39, alias_exact=1.0, recency=0.48, aliases=["Pallavi"]),
    ]
    memory = SimpleNamespace(
        get_aggregate=lambda *a, **k: None,
        recent_reference_support=lambda *a, **k: 0.0,
    )
    outcome = resolve_identity_with_evidence_loop(
        memory,
        ranked,
        surface="Pallavi",
        world_probes=False,
        budget=2,
    )
    assert outcome.action == "gather_exhausted_ask"
    assert outcome.probes_used
    assert len(outcome.probes_used) <= 2
    assert outcome.reason == "ambiguity_survived_evidence_budget"


def test_gather_respects_budget_cap():
    ranked = [
        _rc("e:a", "Pallavi", score=0.3, aliases=["Pallavi"]),
        _rc("e:b", "Pallavi Joshi", score=0.3, aliases=["Pallavi Joshi"]),
    ]
    hyps = hypotheses_from_ranked(
        ranked, surface="Pallavi", memory=SimpleNamespace()
    )
    _, probes = gather_identity_evidence(
        SimpleNamespace(),
        hyps,
        surface="Pallavi",
        budget=1,
        world_probes=True,
    )
    assert len(probes) == 1
