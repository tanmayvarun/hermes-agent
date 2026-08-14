"""Goldens: generic evidence acquisition (identity + non-identity).

ASK is terminal after a bounded Brain/MetaActor evidence budget —
not the first response to a narrow numeric margin.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

from plugin.agent.brain.document_resolution import (
    DocumentHypothesis,
    acquire_for_document_resolution,
)
from plugin.agent.brain.evidence_acquisition import run_evidence_acquisition
from plugin.agent.brain.identity_consultant import (
    BindingAssessment,
    acquire_for_entity_resolution,
    consult_identity_hypotheses,
)
from plugin.agent.brain.identity_hypothesis import (
    classify_name_match,
    hypotheses_from_ranked,
)
from plugin.agent.brain.information_need import (
    EVIDENCE_FOUND,
    NO_CAPABILITY,
    STRENGTH_MODERATE,
    STRENGTH_STRONG,
    EvidenceNeedAssessment,
    EvidenceResult,
    InformationNeed,
)
from plugin.agent.goal import Goal
from plugin.agent.information import (
    InformationCapabilityRegistry,
    WhatsAppContactEvidenceProvider,
)
from plugin.agent.memory.bootstrap import open_local_memory
from plugin.agent.memory.cognition import ActionRiskPolicy
from plugin.agent.memory.pipeline import ContactObservation
from plugin.agent.memory.recipient_binding import resolve_recipient_before_methods
from plugin.agent.memory.sources import FixtureSourceAdapter
from plugin.agent.memory.types import BindingUncertainty, RankedCandidate


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
    now = time.time()
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
        assert rr.status == "proceed"
        assert rr.channel_external_id == "W_P"
        assert rr.reason == "exact_alias_prior_without_contextual_rival"
    finally:
        store.close()


def test_additional_world_evidence_can_resolve_without_user_interrupt(monkeypatch):
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
    memory = SimpleNamespace()

    def fake_probe(self, need, *, evidence_kind, hypotheses):
        return EvidenceResult(
            status=EVIDENCE_FOUND,
            provider_id="whatsapp_contacts",
            evidence_kind=evidence_kind,
            payload={
                "by_entity": {
                    "e:joshi": {
                        "frequency_known": True,
                        "interaction_count_30d": 42.5,
                    },
                    "e:phonepe": {
                        "frequency_known": True,
                        "interaction_count_30d": 2.5,
                    },
                }
            },
        )

    monkeypatch.setattr(WhatsAppContactEvidenceProvider, "probe", fake_probe)
    episode = acquire_for_entity_resolution(
        memory,
        ranked,
        surface="Pallavi",
        world_probes=True,
        budget=4,
    )
    consultation = consult_identity_hypotheses(
        [h for h in episode.hypotheses], surface="Pallavi"
    )
    assert consultation.action == "proceed"
    assert consultation.entity_id == "e:joshi"
    assert consultation.reason == "frequency_dominance"
    assert consultation.evidence_strength == STRENGTH_STRONG
    assert "interaction_frequency" in consultation.evidence_classes
    assert any("whatsapp_contacts" in p for p in episode.probe_labels())


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
    outcome = consult_identity_hypotheses(hyps, surface="Pallavi")
    assert outcome.action == "proceed"
    assert outcome.entity_id == "e:joshi"
    assert outcome.evidence_strength == STRENGTH_STRONG
    assert "working_context" in outcome.evidence_classes


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
    outcome = consult_identity_hypotheses(hyps, surface="Pallavi")
    assert outcome.action == "proceed"
    assert outcome.entity_id == "e:exact"
    assert outcome.evidence_strength == STRENGTH_MODERATE
    assert outcome.evidence_classes == ["exact_alias"]
    # Policy: moderate is enough for send_message
    assert ActionRiskPolicy().allows_binding("send_message", outcome).action == "proceed"


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
    finally:
        store.close()


def test_ask_only_after_identity_evidence_budget_exhausted():
    ranked = [
        _rc("e:a", "Pallavi", score=0.40, alias_exact=1.0, recency=0.5, aliases=["Pallavi"]),
        _rc("e:b", "Pallavi", score=0.39, alias_exact=1.0, recency=0.48, aliases=["Pallavi"]),
    ]
    memory = SimpleNamespace(
        get_aggregate=lambda *a, **k: None,
        recent_reference_support=lambda *a, **k: 0.0,
    )
    episode = acquire_for_entity_resolution(
        memory,
        ranked,
        surface="Pallavi",
        world_probes=False,
        budget=2,
    )
    consultation = consult_identity_hypotheses(
        [h for h in episode.hypotheses], surface="Pallavi"
    )
    assert consultation.action == "ask"
    assert episode.probes_attempted
    assert consultation.evidence_strength == "weak"


def test_budget_ignores_unavailable_providers_but_attempt_budget_bounds_them():
    need = InformationNeed(
        need_type="entity_resolution",
        subject="Pallavi",
        competing_hypotheses=[],
        budget=2,
        attempt_budget=3,
        context={"channel": "whatsapp", "working_context": {}},
    )

    class DeadProvider:
        provider_id = "dead"
        evidence_kinds = frozenset({"channel_activity"})

        def can_serve(self, need, evidence_kind):
            return True

        def probe(self, need, *, evidence_kind, hypotheses):
            return EvidenceResult(
                status=NO_CAPABILITY,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                notes="offline",
            )

    class AlwaysAmbiguousStrategy:
        def incorporate(self, result, hypotheses, *, need):
            return hypotheses

        def assess(self, need, hypotheses, *, last_result=None, attempted_pairs=None):
            return EvidenceNeedAssessment(
                remaining_ambiguities=["still_ambiguous"],
                preferred_evidence_kinds=["channel_activity", "working_context"],
            )

    reg = InformationCapabilityRegistry()
    reg.register(DeadProvider())
    reg.register(
        type(
            "WC",
            (),
            {
                "provider_id": "working_context",
                "evidence_kinds": frozenset({"working_context"}),
                "can_serve": lambda self, n, k: True,
                "probe": lambda self, n, *, evidence_kind, hypotheses: EvidenceResult(
                    status="NO_EVIDENCE",
                    provider_id="working_context",
                    evidence_kind=evidence_kind,
                ),
            },
        )()
    )
    episode = run_evidence_acquisition(
        need, registry=reg, strategy=AlwaysAmbiguousStrategy(), hypotheses=[]
    )
    assert episode.budget_remaining >= 1
    assert episode.attempt_budget_remaining >= 0
    assert any(r.status == NO_CAPABILITY for r in episode.probes_attempted)


def test_binding_assessment_is_qualitative_not_fabricated_margin():
    hyps = hypotheses_from_ranked(
        [
            _rc("e:exact", "Pallavi", score=0.30, alias_exact=1.0, aliases=["Pallavi"]),
            _rc("e:j", "Pallavi Joshi", score=0.32, recency=0.9, aliases=["Pallavi Joshi"]),
        ],
        surface="Pallavi",
        memory=SimpleNamespace(),
    )
    ba = consult_identity_hypotheses(hyps, surface="Pallavi")
    assert isinstance(ba, BindingAssessment)
    assert ba.evidence_strength == STRENGTH_MODERATE
    assert not hasattr(ba, "margin") or getattr(ba, "margin", None) is None
    assert "confidence" not in ba.__dataclass_fields__
    assert ba.raw_candidate_scores  # opaque scores preserved separately


def test_evidence_gathering_cannot_override_action_risk_refuse():
    policy = ActionRiskPolicy()
    ba = BindingAssessment(
        action="proceed",
        entity_id="e1",
        reason="working_context_preference",
        evidence_strength="decisive",
        evidence_classes=["working_context"],
    )
    assert policy.allows_binding("transfer_money", ba).action == "refuse"
    unc = BindingUncertainty(
        top_candidate="e1",
        alternatives=["e2"],
        confidence=0.9,
        margin=0.5,
        ambiguity_reasons=[],
        evidence_quality=0.9,
    )
    assert policy.allows("transfer_money", unc).action == "refuse"


def test_providers_do_not_mutate_hypotheses_directly():
    """Providers return payloads; strategy.incorporate applies interpretation."""
    from plugin.agent.information import WorkingContextEvidenceProvider
    from plugin.agent.brain.identity_consultant import EntityResolutionEvidenceStrategy

    hyp = hypotheses_from_ranked(
        [_rc("e:1", "Pallavi", score=0.3, aliases=["Pallavi"])],
        surface="Pallavi",
        memory=SimpleNamespace(),
        working_context={"recent_entity_id": "e:1", "recent_entity_name": "Pallavi"},
    )[0]
    assert hyp.context.l1_preferred is False or True  # may be set at construction
    # Reset flags to prove provider doesn't set them
    hyp.context.l1_preferred = False
    hyp.context.working_context_hit = False
    need = InformationNeed(
        need_type="entity_resolution",
        subject="Pallavi",
        context={"working_context": {"recent_entity_id": "e:1"}},
    )
    result = WorkingContextEvidenceProvider().probe(
        need, evidence_kind="working_context", hypotheses=[hyp]
    )
    assert result.status == EVIDENCE_FOUND
    assert hyp.context.l1_preferred is False  # provider must not mutate
    EntityResolutionEvidenceStrategy(surface="Pallavi").incorporate(
        result, [hyp], need=need
    )
    assert hyp.context.l1_preferred is True


def test_generic_episode_resolves_document_without_identity_hypothesis():
    import plugin.agent.brain.evidence_acquisition as ea_mod
    import plugin.agent.brain.document_resolution as doc_mod

    src = open(ea_mod.__file__, encoding="utf-8").read()
    assert "IdentityHypothesis" not in src
    assert "identity_hypothesis" not in src

    hyps = [
        DocumentHypothesis(doc_id="doc:old", title="Q1 Deck.pdf", path="/docs/Q1 Deck.pdf"),
        DocumentHypothesis(
            doc_id="doc:phonepe",
            title="PhonePe Deck.pptx",
            path="/docs/PhonePe Deck.pptx",
        ),
    ]
    episode = acquire_for_document_resolution(
        hyps,
        subject="the deck",
        working_context={},
        recent_files=["PhonePe Deck.pptx"],
        mtime_by_id={"doc:old": 0.2, "doc:phonepe": 0.9},
        budget=4,
    )
    assert episode.probes_attempted
    assert episode.resolved
    assert episode.resolution_ref == "doc:phonepe"
    doc_src = open(doc_mod.__file__, encoding="utf-8").read()
    assert "IdentityHypothesis" not in doc_src
    assert "identity_hypothesis" not in doc_src
    assert all(isinstance(h, DocumentHypothesis) for h in episode.hypotheses)


def test_document_adaptive_reassessment_after_first_provider_miss():
    """First recent-file provider returns NO_EVIDENCE; next provider / filesystem resolves."""
    hyps = [
        DocumentHypothesis(doc_id="doc:old", title="Q1 Deck.pdf"),
        DocumentHypothesis(doc_id="doc:phonepe", title="PhonePe Deck.pptx"),
    ]
    episode = acquire_for_document_resolution(
        hyps,
        subject="the deck",
        working_context={},
        recent_files=["PhonePe Deck.pptx"],
        mtime_by_id={"doc:old": 0.2, "doc:phonepe": 0.95},
        prefer_empty_recent_first=True,
        budget=5,
        attempt_budget=8,
    )
    labels = episode.probe_labels()
    assert any("recent_file_memory_empty" in p for p in labels)
    # Same evidence kind retried with a different provider, or filesystem used.
    assert episode.resolved
    assert episode.resolution_ref == "doc:phonepe"
    pairs = episode.attempted_pairs()
    assert ("recent_file_memory", "recent_file_memory_empty") in pairs


def test_incorporate_is_monotonic_missing_row_does_not_erase():
    from plugin.agent.brain.identity_consultant import EntityResolutionEvidenceStrategy
    from plugin.agent.brain.identity_hypothesis import (
        ContextEvidence,
        IdentityHypothesis,
        NameEvidence,
        SalienceEvidence,
    )

    h = IdentityHypothesis(
        entity_id="e:1",
        display_name="Pallavi",
        name=NameEvidence(match_kind="exact", surface_form="Pallavi", canonical_name="Pallavi"),
        salience=SalienceEvidence(
            frequency=0.8,
            frequency_known=True,
            frequency_status="known",
            recency=0.9,
            recency_status="known",
        ),
        context=ContextEvidence(
            reference_support=1.0,
            reference_status="known_positive",
        ),
    )
    strat = EntityResolutionEvidenceStrategy(surface="Pallavi")
    need = InformationNeed(need_type="entity_resolution", subject="Pallavi")
    # Provider found evidence for other entities only — e:1 absent
    result = EvidenceResult(
        status=EVIDENCE_FOUND,
        provider_id="memory_aggregates",
        evidence_kind="memory_aggregates",
        payload={"by_entity": {"e:other": {"frequency_known": False}}},
    )
    strat.incorporate(result, [h], need=need)
    assert h.salience.frequency_known is True
    assert h.salience.frequency_status == "known"
    assert h.salience.frequency == 0.8
    assert h.context.reference_status == "known_positive"


def test_reference_lookup_error_is_not_negative_evidence():
    from plugin.agent.brain.identity_consultant import EntityResolutionEvidenceStrategy
    from plugin.agent.brain.identity_hypothesis import (
        ContextEvidence,
        IdentityHypothesis,
        NameEvidence,
    )

    h = IdentityHypothesis(
        entity_id="e:1",
        display_name="Pallavi",
        name=NameEvidence(match_kind="exact", surface_form="Pallavi", canonical_name="Pallavi"),
        context=ContextEvidence(reference_status="unknown", reference_support=0.0),
    )
    strat = EntityResolutionEvidenceStrategy(surface="Pallavi")
    need = InformationNeed(need_type="entity_resolution", subject="Pallavi")
    result = EvidenceResult(
        status=EVIDENCE_FOUND,
        provider_id="reference_history",
        evidence_kind="reference_history",
        payload={"by_entity": {"e:1": {"status": "error", "error": "db down"}}},
    )
    strat.incorporate(result, [h], need=need)
    assert h.context.reference_status == "error"
    assert h.context.reference_support == 0.0  # unset value, not known_negative


def test_provider_exception_becomes_error_result_and_loop_continues():
    need = InformationNeed(
        need_type="entity_resolution",
        subject="Pallavi",
        competing_hypotheses=[],
        budget=2,
        attempt_budget=4,
    )

    class BoomProvider:
        provider_id = "boom"
        evidence_kinds = frozenset({"working_context"})

        def can_serve(self, need, evidence_kind):
            return True

        def probe(self, need, *, evidence_kind, hypotheses):
            raise RuntimeError("bridge down")

    class OkProvider:
        provider_id = "ok"
        evidence_kinds = frozenset({"memory_aggregates"})

        def can_serve(self, need, evidence_kind):
            return True

        def probe(self, need, *, evidence_kind, hypotheses):
            return EvidenceResult(
                status="NO_EVIDENCE",
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
            )

    class Strat:
        def incorporate(self, result, hypotheses, *, need):
            return hypotheses

        def assess(self, need, hypotheses, *, last_result=None, attempted_pairs=None):
            pairs = set(attempted_pairs or ())
            kinds = []
            if ("working_context", "boom") not in pairs:
                kinds.append("working_context")
            if ("memory_aggregates", "ok") not in pairs:
                kinds.append("memory_aggregates")
            return EvidenceNeedAssessment(
                remaining_ambiguities=["x"],
                preferred_evidence_kinds=kinds or [],
            )

    reg = InformationCapabilityRegistry()
    reg.register(BoomProvider())
    reg.register(OkProvider())
    episode = run_evidence_acquisition(need, registry=reg, strategy=Strat(), hypotheses=[])
    assert any(r.status == "ERROR" and r.provider_id == "boom" for r in episode.probes_attempted)
    assert any(r.provider_id == "ok" for r in episode.probes_attempted)


def test_error_on_one_kind_does_not_global_blacklist_provider():
    """Pair-scoped failure: provider usable for another evidence kind."""
    need = InformationNeed(
        need_type="entity_resolution",
        subject="Pallavi",
        budget=3,
        attempt_budget=6,
    )

    class MultiKindProvider:
        provider_id = "multi"
        evidence_kinds = frozenset({"working_context", "channel_activity"})
        calls: list[str] = []

        def can_serve(self, need, evidence_kind):
            return True

        def probe(self, need, *, evidence_kind, hypotheses):
            self.calls.append(evidence_kind)
            if evidence_kind == "working_context":
                raise RuntimeError("wc failed")
            return EvidenceResult(
                status=EVIDENCE_FOUND,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                payload={"by_entity": {}},
            )

    class Strat:
        def incorporate(self, result, hypotheses, *, need):
            return hypotheses

        def assess(self, need, hypotheses, *, last_result=None, attempted_pairs=None):
            pairs = set(attempted_pairs or ())
            kinds = []
            if ("working_context", "multi") not in pairs:
                kinds.append("working_context")
            elif ("channel_activity", "multi") not in pairs:
                kinds.append("channel_activity")
            if not kinds:
                return EvidenceNeedAssessment(resolved=True, resolution_ref="done")
            return EvidenceNeedAssessment(
                remaining_ambiguities=["x"],
                preferred_evidence_kinds=kinds,
            )

    prov = MultiKindProvider()
    MultiKindProvider.calls = []
    reg = InformationCapabilityRegistry()
    reg.register(prov)
    episode = run_evidence_acquisition(need, registry=reg, strategy=Strat(), hypotheses=[])
    assert "working_context" in MultiKindProvider.calls
    assert "channel_activity" in MultiKindProvider.calls
    assert episode.resolved


def test_brain_does_not_import_whatsapp_http():
    import pathlib

    brain = pathlib.Path(__file__).resolve().parents[2] / "plugin" / "agent" / "brain"
    banned = ("127.0.0.1:3000", "urllib.request", "/contacts")
    for path in brain.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{path.name} must not contain {token!r}"
