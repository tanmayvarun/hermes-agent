"""Entity-resolution EvidenceStrategy + BindingAssessment (identity domain).

Supplies identity-specific reassessment to the generic EvidenceAcquisitionEpisode.
Deterministic consultant is a fallback/golden — not the architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from plugin.agent.brain.evidence_acquisition import run_evidence_acquisition
from plugin.agent.brain.identity_hypothesis import IdentityHypothesis, hypotheses_from_ranked
from plugin.agent.brain.information_need import (
    EvidenceAcquisitionEpisode,
    EvidenceNeedAssessment,
    EvidenceResult,
    InformationNeed,
)
from plugin.agent.information import (
    InformationCapabilityRegistry,
    default_registry_for_entity_resolution,
)
from plugin.agent.memory.types import BindingUncertainty


@dataclass
class BindingAssessment:
    """Evidence-backed binding judgment for ActionRiskPolicy — not fabricated."""

    action: str  # proceed | ask
    entity_id: str = ""
    reason: str = ""
    confidence: float = 0.0
    margin: float = 0.0
    evidence_quality: float = 0.0
    ambiguity_reasons: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    feature_scores: dict[str, float] = field(default_factory=dict)
    hypotheses: list[IdentityHypothesis] = field(default_factory=list)
    rationale: str = ""

    def to_binding_uncertainty(self) -> BindingUncertainty:
        return BindingUncertainty(
            top_candidate=self.entity_id,
            alternatives=list(self.alternatives),
            confidence=float(self.confidence),
            margin=float(self.margin),
            ambiguity_reasons=list(self.ambiguity_reasons),
            evidence_quality=float(self.evidence_quality),
            feature_scores=dict(self.feature_scores),
        )


# Back-compat alias used by goldens
IdentityConsultation = BindingAssessment


def _evidence_diversity(h: IdentityHypothesis) -> float:
    bits = 0
    if h.context.l1_preferred or h.context.working_context_hit:
        bits += 1
    if h.context.reference_support >= 1.0:
        bits += 1
    if h.context.active_project_hit:
        bits += 1
    if h.name.match_kind == "exact":
        bits += 1
    if h.salience.frequency_known and h.salience.frequency > 0:
        bits += 1
    if h.salience.recency >= 0.5:
        bits += 1
    return min(1.0, bits / 4.0)


def _opaque_margin(chosen: IdentityHypothesis, hyps: list[IdentityHypothesis]) -> float:
    others = [h for h in hyps if h.entity_id != chosen.entity_id]
    if not others:
        return max(0.15, float(chosen.opaque_score))
    best_other = max(float(h.opaque_score) for h in others)
    return max(0.0, float(chosen.opaque_score) - best_other)


def _assessment_for_choice(
    chosen: IdentityHypothesis,
    hyps: list[IdentityHypothesis],
    *,
    reason: str,
    confidence_floor: float,
    quality_bonus: float,
) -> BindingAssessment:
    alts = [h.entity_id for h in hyps if h.entity_id != chosen.entity_id][:4]
    diversity = _evidence_diversity(chosen)
    opaque_m = _opaque_margin(chosen, hyps)
    # Conservative: confidence from opaque score + evidence class, not invented.
    conf = min(1.0, max(float(chosen.opaque_score), confidence_floor) + 0.05 * diversity)
    # Margin: prefer evidence-class separation over fixed 0.25 hack.
    class_sep = {
        "working_context_preference": 0.35,
        "working_context_exact": 0.40,
        "prior_reference_resolution": 0.30,
        "qualified_match_with_project_context": 0.28,
        "frequency_dominance": 0.22,
        # Unique exact surface + no contextual rival is a real evidence class,
        # not a fabricated 0.25 hack — floor at the unique_exact risk bar.
        "exact_alias_prior_without_contextual_rival": 0.16,
        "single_candidate": 0.20,
    }.get(reason, 0.10)
    margin = max(opaque_m, class_sep)
    if reason == "exact_alias_prior_without_contextual_rival":
        # Diversity is thin (name only); keep quality moderate, not inflated.
        margin = max(margin, 0.16)
    quality = min(1.0, quality_bonus + 0.5 * diversity)
    feats = {
        "name_exact": 1.0 if chosen.name.match_kind == "exact" else 0.0,
        "l1_preferred": 1.0 if chosen.context.l1_preferred else 0.0,
        "reference_support": float(chosen.context.reference_support),
        "frequency": float(chosen.salience.frequency) if chosen.salience.frequency_known else 0.0,
        "recency": float(chosen.salience.recency),
        "evidence_diversity": diversity,
    }
    if reason == "exact_alias_prior_without_contextual_rival":
        feats["unique_exact_alias"] = 1.0
        conf = max(conf, 0.45)
    return BindingAssessment(
        action="proceed",
        entity_id=chosen.entity_id,
        reason=reason,
        confidence=conf,
        margin=margin,
        evidence_quality=quality,
        ambiguity_reasons=[],
        alternatives=alts,
        feature_scores=feats,
        hypotheses=hyps,
        rationale=reason,
    )


def consult_identity_hypotheses(
    hypotheses: list[IdentityHypothesis],
    *,
    surface: str,
) -> BindingAssessment:
    """Deterministic identity consultant → evidence-backed BindingAssessment."""
    if not hypotheses:
        return BindingAssessment(
            action="ask",
            reason="no_hypotheses",
            ambiguity_reasons=["no_candidates"],
            confidence=0.0,
            margin=0.0,
            evidence_quality=0.0,
        )

    l1 = [h for h in hypotheses if h.context.l1_preferred or h.context.working_context_hit]
    if len(l1) == 1:
        return _assessment_for_choice(
            l1[0],
            hypotheses,
            reason="working_context_preference",
            confidence_floor=0.55,
            quality_bonus=0.55,
        )
    if len(l1) > 1:
        exact_l1 = [h for h in l1 if h.name.match_kind == "exact"]
        if len(exact_l1) == 1:
            return _assessment_for_choice(
                exact_l1[0],
                hypotheses,
                reason="working_context_exact",
                confidence_floor=0.58,
                quality_bonus=0.6,
            )

    refs = [h for h in hypotheses if h.context.reference_support >= 1.0]
    if len(refs) == 1:
        return _assessment_for_choice(
            refs[0],
            hypotheses,
            reason="prior_reference_resolution",
            confidence_floor=0.52,
            quality_bonus=0.5,
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
            # Exact prior only — moderate confidence, lower evidence diversity.
            return _assessment_for_choice(
                exact[0],
                hypotheses,
                reason="exact_alias_prior_without_contextual_rival",
                confidence_floor=0.40,
                quality_bonus=0.28,
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
                confidence_floor=0.50,
                quality_bonus=0.48,
            )

    if len(hypotheses) == 1:
        return _assessment_for_choice(
            hypotheses[0],
            hypotheses,
            reason="single_candidate",
            confidence_floor=0.35,
            quality_bonus=0.25,
        )

    freq_known = [
        h
        for h in hypotheses
        if h.salience.frequency_known and h.salience.frequency > 0
    ]
    if len(freq_known) >= 2:
        ranked_f = sorted(freq_known, key=lambda h: h.salience.frequency, reverse=True)
        if ranked_f[0].salience.frequency >= ranked_f[1].salience.frequency + 0.35:
            return _assessment_for_choice(
                ranked_f[0],
                hypotheses,
                reason="frequency_dominance",
                confidence_floor=0.48,
                quality_bonus=0.42,
            )

    # Still ambiguous — report honest low margin from opaque scores.
    ranked = sorted(hypotheses, key=lambda h: h.opaque_score, reverse=True)
    top, second = ranked[0], ranked[1] if len(ranked) > 1 else None
    margin = float(top.opaque_score) - (float(second.opaque_score) if second else 0.0)
    return BindingAssessment(
        action="ask",
        entity_id=top.entity_id,
        reason="ambiguity_survived_evidence_budget",
        confidence=float(top.opaque_score),
        margin=margin,
        evidence_quality=_evidence_diversity(top) * 0.5,
        ambiguity_reasons=["competing_identity_hypotheses"],
        alternatives=[h.entity_id for h in ranked[1:5]],
        hypotheses=hypotheses,
        rationale="ambiguity_survived_evidence_budget",
    )


class EntityResolutionEvidenceStrategy:
    """Identity-domain strategy: reassess after each result; pick discriminating kinds."""

    def __init__(self, *, surface: str = "") -> None:
        self.surface = surface

    def assess(
        self,
        need: InformationNeed,
        hypotheses: list[Any],
        *,
        last_result: Optional[EvidenceResult] = None,
        attempted_kinds: Optional[set[str]] = None,
    ) -> EvidenceNeedAssessment:
        hyps = [h for h in hypotheses if isinstance(h, IdentityHypothesis)]
        attempted = set(attempted_kinds or [])
        known = {
            str(e.get("kind") or "")
            for e in need.evidence_already_known
            if e
        }

        # Resolution check via same consultant (soft priors)
        consultation = consult_identity_hypotheses(hyps, surface=self.surface or need.subject)
        if consultation.action == "proceed" and consultation.entity_id:
            # Only early-stop when evidence class is strong enough that further
            # probes are unlikely to overturn (working context / refs / project).
            strong = consultation.reason in {
                "working_context_preference",
                "working_context_exact",
                "prior_reference_resolution",
                "qualified_match_with_project_context",
            }
            if strong or (
                last_result
                and last_result.evidence_kind
                in {"working_context", "reference_history"}
                and consultation.reason.startswith("working_context")
            ):
                return EvidenceNeedAssessment(
                    resolved=True,
                    resolution_ref=consultation.entity_id,
                    resolution_reason=consultation.reason,
                    remaining_ambiguities=[],
                    preferred_evidence_kinds=[],
                )

        ambiguities: list[str] = []
        preferred: list[str] = []

        # Infer what would discriminate given current evidence state.
        l1_hits = [
            h
            for h in hyps
            if h.context.l1_preferred or h.context.working_context_hit
        ]
        if len(l1_hits) != 1 and "working_context" not in attempted and "working_context" not in known:
            ambiguities.append("no_unique_working_context")
            preferred.append("working_context")

        freq_unknown = [h for h in hyps if not h.salience.frequency_known]
        if len(hyps) >= 2 and freq_unknown and "memory_aggregates" not in attempted:
            ambiguities.append("frequency_unknown_for_candidates")
            preferred.append("memory_aggregates")

        refs = [h for h in hyps if h.context.reference_support >= 1.0]
        if len(refs) != 1 and "reference_history" not in attempted:
            # Prefer refs when aggregates already ran and still ambiguous,
            # or when names look like casual aliases.
            if "memory_aggregates" in attempted or "memory_aggregates" in known:
                ambiguities.append("no_unique_prior_reference")
                preferred.append("reference_history")
            elif not preferred:
                preferred.append("reference_history")

        # Channel activity: useful when recency/frequency still sparse after memory.
        sparse_salience = [
            h
            for h in hyps
            if (not h.salience.frequency_known) and h.salience.recency < 0.2
        ]
        if (
            len(hyps) >= 2
            and sparse_salience
            and "channel_activity" not in attempted
            and ("memory_aggregates" in attempted or "memory_aggregates" in known)
        ):
            ambiguities.append("sparse_channel_salience")
            preferred.append("channel_activity")
        elif (
            len(hyps) >= 2
            and "channel_activity" not in attempted
            and not preferred
        ):
            preferred.append("channel_activity")

        # Dedupe while preserving order
        seen: set[str] = set()
        ordered: list[str] = []
        for k in preferred:
            if k not in seen:
                seen.add(k)
                ordered.append(k)

        if not ambiguities:
            ambiguities.append("competing_identity_hypotheses")

        return EvidenceNeedAssessment(
            remaining_ambiguities=ambiguities,
            discriminating_features=list(ordered),
            preferred_evidence_kinds=ordered,
            resolved=False,
            notes=f"last={getattr(last_result, 'evidence_kind', None)}",
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
    """Identity use-case: build need + strategy, run domain-neutral episode."""
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
