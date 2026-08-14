"""Entity-resolution EvidenceStrategy + BindingAssessment (identity domain).

Providers return EvidenceResult; this strategy incorporates + assesses.
BindingAssessment uses qualitative evidence_strength — not fabricated
calibrated confidence/margin.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from plugin.agent.brain.evidence_acquisition import run_evidence_acquisition
from plugin.agent.brain.identity_hypothesis import IdentityHypothesis, hypotheses_from_ranked
from plugin.agent.brain.information_need import (
    EVIDENCE_FOUND,
    STRENGTH_DECISIVE,
    STRENGTH_MODERATE,
    STRENGTH_STRONG,
    STRENGTH_WEAK,
    EvidenceAcquisitionEpisode,
    EvidenceNeedAssessment,
    EvidenceResult,
    InformationNeed,
)
from plugin.agent.information import (
    InformationCapabilityRegistry,
    default_registry_for_entity_resolution,
)


@dataclass
class BindingAssessment:
    """Qualitative binding judgment for ActionRiskPolicy.

    evidence_strength is a policy-facing strength class, not a calibrated
    probability. raw_candidate_scores preserve opaque retrieval scores when
    present — they are not invented margins.
    """

    action: str  # proceed | ask
    entity_id: str = ""
    reason: str = ""
    evidence_strength: str = STRENGTH_WEAK  # weak|moderate|strong|decisive
    evidence_classes: list[str] = field(default_factory=list)
    ambiguity_reasons: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    raw_candidate_scores: dict[str, float] = field(default_factory=dict)
    hypotheses: list[IdentityHypothesis] = field(default_factory=list)
    rationale: str = ""

    def meets(self, minimum: str) -> bool:
        from plugin.agent.brain.information_need import STRENGTH_ORDER

        return STRENGTH_ORDER.get(self.evidence_strength, -1) >= STRENGTH_ORDER.get(
            minimum, 99
        )


# Back-compat alias
IdentityConsultation = BindingAssessment


def _raw_scores(hyps: list[IdentityHypothesis]) -> dict[str, float]:
    return {h.entity_id: float(h.opaque_score) for h in hyps}


def _assessment_for_choice(
    chosen: IdentityHypothesis,
    hyps: list[IdentityHypothesis],
    *,
    reason: str,
    strength: str,
    evidence_classes: list[str],
) -> BindingAssessment:
    return BindingAssessment(
        action="proceed",
        entity_id=chosen.entity_id,
        reason=reason,
        evidence_strength=strength,
        evidence_classes=list(evidence_classes),
        ambiguity_reasons=[],
        alternatives=[h.entity_id for h in hyps if h.entity_id != chosen.entity_id][:4],
        raw_candidate_scores=_raw_scores(hyps),
        hypotheses=hyps,
        rationale=reason,
    )


def consult_identity_hypotheses(
    hypotheses: list[IdentityHypothesis],
    *,
    surface: str,
) -> BindingAssessment:
    """Deterministic identity consultant → qualitative BindingAssessment."""
    if not hypotheses:
        return BindingAssessment(
            action="ask",
            reason="no_hypotheses",
            evidence_strength=STRENGTH_WEAK,
            ambiguity_reasons=["no_candidates"],
        )

    l1 = [h for h in hypotheses if h.context.l1_preferred or h.context.working_context_hit]
    if len(l1) == 1:
        return _assessment_for_choice(
            l1[0],
            hypotheses,
            reason="working_context_preference",
            strength=STRENGTH_STRONG,
            evidence_classes=["working_context"],
        )
    if len(l1) > 1:
        exact_l1 = [h for h in l1 if h.name.match_kind == "exact"]
        if len(exact_l1) == 1:
            return _assessment_for_choice(
                exact_l1[0],
                hypotheses,
                reason="working_context_exact",
                strength=STRENGTH_DECISIVE,
                evidence_classes=["working_context", "exact_alias"],
            )

    refs = [h for h in hypotheses if h.context.reference_support >= 1.0]
    if len(refs) == 1:
        return _assessment_for_choice(
            refs[0],
            hypotheses,
            reason="prior_reference_resolution",
            strength=STRENGTH_STRONG,
            evidence_classes=["prior_reference"],
        )

    exact = [h for h in hypotheses if h.name.match_kind == "exact"]
    qualified = [h for h in hypotheses if h.name.match_kind == "qualified_partial"]

    surface_tokens = (surface or "").strip().split()
    casual_unqualified = len(surface_tokens) == 1
    if casual_unqualified and len(exact) == 1:
        rival_context = [
            h
            for h in hypotheses
            if h.entity_id != exact[0].entity_id
            and (
                h.context.l1_preferred
                or h.context.working_context_hit
                or h.context.reference_support >= 1.0
                or h.context.active_project_hit
            )
        ]
        if not rival_context:
            return _assessment_for_choice(
                exact[0],
                hypotheses,
                reason="exact_alias_prior_without_contextual_rival",
                strength=STRENGTH_MODERATE,
                evidence_classes=["exact_alias"],
            )

    if qualified:
        wc_proj = [
            h
            for h in qualified
            if h.context.active_project_hit or h.context.working_context_hit
        ]
        if len(wc_proj) == 1:
            return _assessment_for_choice(
                wc_proj[0],
                hypotheses,
                reason="qualified_match_with_project_context",
                strength=STRENGTH_STRONG,
                evidence_classes=["project_context", "qualified_name"],
            )

    if len(hypotheses) == 1:
        return _assessment_for_choice(
            hypotheses[0],
            hypotheses,
            reason="single_candidate",
            strength=STRENGTH_MODERATE,
            evidence_classes=["single_candidate"],
        )

    freq_known = [
        h
        for h in hypotheses
        if h.salience.frequency_known and h.salience.frequency > 0
    ]
    if len(freq_known) >= 2:
        ranked_f = sorted(freq_known, key=lambda h: h.salience.frequency, reverse=True)
        if ranked_f[0].salience.frequency >= ranked_f[1].salience.frequency + 0.35:
            classes = ["interaction_frequency"]
            if ranked_f[0].name.match_kind == "exact":
                classes.append("exact_alias")
            return _assessment_for_choice(
                ranked_f[0],
                hypotheses,
                reason="frequency_dominance",
                strength=STRENGTH_STRONG,
                evidence_classes=classes,
            )

    ranked = sorted(hypotheses, key=lambda h: h.opaque_score, reverse=True)
    top = ranked[0]
    return BindingAssessment(
        action="ask",
        entity_id=top.entity_id,
        reason="ambiguity_survived_evidence_budget",
        evidence_strength=STRENGTH_WEAK,
        evidence_classes=[],
        ambiguity_reasons=["competing_identity_hypotheses"],
        alternatives=[h.entity_id for h in ranked[1:5]],
        raw_candidate_scores=_raw_scores(hypotheses),
        hypotheses=hypotheses,
        rationale="ambiguity_survived_evidence_budget",
    )


class EntityResolutionEvidenceStrategy:
    """Identity-domain: incorporate raw evidence, then reassess."""

    def __init__(self, *, surface: str = "") -> None:
        self.surface = surface

    def incorporate(
        self,
        result: EvidenceResult,
        hypotheses: list[Any],
        *,
        need: InformationNeed,
    ) -> list[Any]:
        hyps = [h for h in hypotheses if isinstance(h, IdentityHypothesis)]
        if result.status != EVIDENCE_FOUND:
            return list(hypotheses)

        payload = dict(result.payload or {})
        kind = result.evidence_kind

        if kind == "working_context":
            preferred = set(payload.get("preferred_entity_ids") or [])
            for h in hyps:
                if h.entity_id in preferred:
                    h.context.l1_preferred = True
                    h.context.working_context_hit = True
                    h.gather_notes.append("working_context_prefer")

        elif kind == "memory_aggregates":
            by_entity = dict(payload.get("by_entity") or {})
            now = time.time()
            for h in hyps:
                row = by_entity.get(h.entity_id) or {}
                if "error" in row:
                    h.gather_notes.append(f"aggregate_error:{row['error']}")
                    continue
                h.salience.frequency_known = bool(row.get("frequency_known"))
                if h.salience.frequency_known:
                    h.salience.frequency = min(
                        1.0, float(row.get("count_30d") or 0) / 50.0
                    )
                last_at = row.get("last_interaction_at")
                if last_at is not None:
                    h.salience.last_interaction_at = float(last_at)
                    days = max(0.0, (now - float(last_at)) / 86400.0)
                    h.salience.recency = max(0.0, 1.0 - days / 180.0)
                h.gather_notes.append(
                    f"aggregate freq_known={h.salience.frequency_known} "
                    f"recency={h.salience.recency:.2f}"
                )

        elif kind == "reference_history":
            by_entity = dict(payload.get("reference_support_by_entity") or {})
            for h in hyps:
                h.context.reference_support = float(by_entity.get(h.entity_id) or 0.0)
                h.gather_notes.append(
                    f"reference_support={h.context.reference_support:.2f}"
                )

        elif kind == "channel_activity":
            by_entity = dict(payload.get("by_entity") or {})
            now = time.time()
            for h in hyps:
                row = by_entity.get(h.entity_id) or {}
                if row.get("frequency_known") and row.get("interaction_count_30d") is not None:
                    h.salience.frequency_known = True
                    h.salience.frequency = min(
                        1.0, float(row["interaction_count_30d"]) / 50.0
                    )
                    h.gather_notes.append(f"wa_contacts:freq={h.salience.frequency:.2f}")
                last_at = row.get("last_interaction_at")
                if last_at is not None:
                    h.salience.last_interaction_at = float(last_at)
                    days = max(0.0, (now - float(last_at)) / 86400.0)
                    h.salience.recency = max(0.0, 1.0 - days / 180.0)
                    h.gather_notes.append(f"wa_contacts:recency={h.salience.recency:.3f}")

        return list(hypotheses)

    def assess(
        self,
        need: InformationNeed,
        hypotheses: list[Any],
        *,
        last_result: Optional[EvidenceResult] = None,
        attempted_pairs: Optional[set[tuple[str, str]]] = None,
    ) -> EvidenceNeedAssessment:
        hyps = [h for h in hypotheses if isinstance(h, IdentityHypothesis)]
        pairs = set(attempted_pairs or ())

        consultation = consult_identity_hypotheses(
            hyps, surface=self.surface or need.subject
        )
        if consultation.action == "proceed" and consultation.entity_id:
            strong = consultation.evidence_strength in {
                STRENGTH_STRONG,
                STRENGTH_DECISIVE,
            }
            if strong:
                return EvidenceNeedAssessment(
                    resolved=True,
                    resolution_ref=consultation.entity_id,
                    resolution_reason=consultation.reason,
                )

        ambiguities: list[str] = []
        preferred: list[str] = []

        l1_hits = [
            h for h in hyps if h.context.l1_preferred or h.context.working_context_hit
        ]
        if len(l1_hits) != 1:
            ambiguities.append("no_unique_working_context")
            preferred.append("working_context")

        freq_unknown = [h for h in hyps if not h.salience.frequency_known]
        if len(hyps) >= 2 and freq_unknown:
            ambiguities.append("frequency_unknown_for_candidates")
            preferred.append("memory_aggregates")

        refs = [h for h in hyps if h.context.reference_support >= 1.0]
        if len(refs) != 1:
            ambiguities.append("no_unique_prior_reference")
            preferred.append("reference_history")

        sparse_salience = [
            h
            for h in hyps
            if (not h.salience.frequency_known) and h.salience.recency < 0.2
        ]
        if len(hyps) >= 2 and (sparse_salience or freq_unknown or len(refs) != 1):
            ambiguities.append("sparse_channel_salience")
            preferred.append("channel_activity")

        seen: set[str] = set()
        ordered: list[str] = []
        for k in preferred:
            if k not in seen:
                seen.add(k)
                ordered.append(k)

        return EvidenceNeedAssessment(
            remaining_ambiguities=ambiguities or ["competing_identity_hypotheses"],
            discriminating_features=list(ordered),
            preferred_evidence_kinds=ordered,
            resolved=False,
            notes=f"last={getattr(last_result, 'evidence_kind', None)} pairs={len(pairs)}",
        )


def acquire_for_entity_resolution(
    memory: Any,
    ranked: list[Any],
    *,
    surface: str,
    channel: str = "whatsapp",
    working_context: Optional[dict[str, Any]] = None,
    budget: int = 4,
    attempt_budget: int = 8,
    world_probes: bool = True,
    registry: Optional[InformationCapabilityRegistry] = None,
) -> EvidenceAcquisitionEpisode:
    hyps = hypotheses_from_ranked(
        ranked,
        surface=surface,
        memory=memory,
        channel=channel,
        working_context=working_context,
    )
    need = InformationNeed(
        need_type="entity_resolution",
        subject=surface,
        competing_hypotheses=hyps,
        budget=budget,
        attempt_budget=attempt_budget,
        context={
            "channel": channel,
            "working_context": dict(working_context or {}),
        },
    )
    reg = registry or default_registry_for_entity_resolution(
        memory, world_probes=world_probes
    )
    strategy = EntityResolutionEvidenceStrategy(surface=surface)
    return run_evidence_acquisition(
        need, registry=reg, strategy=strategy, hypotheses=hyps
    )


def consult_after_episode(
    episode: EvidenceAcquisitionEpisode, *, surface: str
) -> BindingAssessment:
    hyps = [h for h in episode.hypotheses if isinstance(h, IdentityHypothesis)]
    consultation = consult_identity_hypotheses(hyps, surface=surface)
    if consultation.action == "ask":
        if episode.budget_remaining <= 0 or not episode.evidence_found:
            consultation.reason = (
                consultation.reason or "ambiguity_survived_evidence_budget"
            )
    return consultation
