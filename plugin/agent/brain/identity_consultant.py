"""Deterministic identity-resolution consultant (fallback / goldens).

Not the architecture: LLM consultation over BrainWorkspace evidence is the
target. This module applies soft priors over structured IdentityHypothesis
bags so tests have a stable reinterpretation step.

Exact-name evidence is a **prior**, not resolution authority — working
context, reference history, and project alignment outrank it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from plugin.agent.brain.identity_hypothesis import IdentityHypothesis
from plugin.agent.brain.information_need import EvidenceAcquisitionEpisode


@dataclass
class IdentityConsultation:
    action: str  # proceed | ask
    entity_id: str = ""
    reason: str = ""
    hypotheses: list[IdentityHypothesis] = field(default_factory=list)


def consult_identity_hypotheses(
    hypotheses: list[IdentityHypothesis],
    *,
    surface: str,
) -> IdentityConsultation:
    """Reinterpret competing identity hypotheses after evidence acquisition."""
    if not hypotheses:
        return IdentityConsultation(action="ask", reason="no_hypotheses")

    # 1) Working / L1 context preference (strong personal signal)
    l1 = [h for h in hypotheses if h.context.l1_preferred or h.context.working_context_hit]
    if len(l1) == 1:
        return IdentityConsultation(
            action="proceed",
            entity_id=l1[0].entity_id,
            reason="working_context_preference",
            hypotheses=hypotheses,
        )
    if len(l1) > 1:
        exact_l1 = [h for h in l1 if h.name.match_kind == "exact"]
        if len(exact_l1) == 1:
            return IdentityConsultation(
                action="proceed",
                entity_id=exact_l1[0].entity_id,
                reason="working_context_exact",
                hypotheses=hypotheses,
            )

    # 2) Prior reference / disambiguation support
    refs = [h for h in hypotheses if h.context.reference_support >= 1.0]
    if len(refs) == 1:
        return IdentityConsultation(
            action="proceed",
            entity_id=refs[0].entity_id,
            reason="prior_reference_resolution",
            hypotheses=hypotheses,
        )

    exact = [h for h in hypotheses if h.name.match_kind == "exact"]
    qualified = [h for h in hypotheses if h.name.match_kind == "qualified_partial"]

    # 3) Soft exact-alias prior for casual unqualified surfaces — only when no
    #    contextual rival. Exact is never authoritative against L1/refs/project.
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
            # Recent partial alone does not automatically override exact prior.
            return IdentityConsultation(
                action="proceed",
                entity_id=exact[0].entity_id,
                reason="exact_alias_prior_without_contextual_rival",
                hypotheses=hypotheses,
            )

    # 4) Project / qualifier alignment
    if qualified:
        wc_proj = [
            h
            for h in qualified
            if h.context.active_project_hit or h.context.working_context_hit
        ]
        if len(wc_proj) == 1:
            return IdentityConsultation(
                action="proceed",
                entity_id=wc_proj[0].entity_id,
                reason="qualified_match_with_project_context",
                hypotheses=hypotheses,
            )

    if len(hypotheses) == 1:
        return IdentityConsultation(
            action="proceed",
            entity_id=hypotheses[0].entity_id,
            reason="single_candidate",
            hypotheses=hypotheses,
        )

    # 5) True frequency dominance (known counts only)
    freq_known = [
        h
        for h in hypotheses
        if h.salience.frequency_known and h.salience.frequency > 0
    ]
    if len(freq_known) >= 2:
        ranked_f = sorted(freq_known, key=lambda h: h.salience.frequency, reverse=True)
        if ranked_f[0].salience.frequency >= ranked_f[1].salience.frequency + 0.35:
            return IdentityConsultation(
                action="proceed",
                entity_id=ranked_f[0].entity_id,
                reason="frequency_dominance",
                hypotheses=hypotheses,
            )

    return IdentityConsultation(
        action="ask",
        reason="ambiguity_survived_evidence_budget",
        hypotheses=hypotheses,
    )


def consult_after_episode(
    episode: EvidenceAcquisitionEpisode, *, surface: str
) -> IdentityConsultation:
    hyps = [h for h in episode.hypotheses if isinstance(h, IdentityHypothesis)]
    consultation = consult_identity_hypotheses(hyps, surface=surface)
    if consultation.action == "ask":
        # Mark as post-budget ASK when budget exhausted and no resolution.
        if episode.budget_remaining <= 0 or not episode.evidence_found:
            consultation.reason = consultation.reason or "ambiguity_survived_evidence_budget"
    return consultation
