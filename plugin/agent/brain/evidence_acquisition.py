"""Generic MetaActor evidence-acquisition episode — domain-neutral.

Knows only InformationNeed, EvidenceResult, budgets, and an EvidenceStrategy.
Providers return evidence; strategies incorporate + assess.
Attempts are tracked by (evidence_kind, provider_id).
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from plugin.agent.brain.information_need import (
    EVIDENCE_FOUND,
    ERROR,
    NO_CAPABILITY,
    EvidenceAcquisitionEpisode,
    EvidenceNeedAssessment,
    EvidenceResult,
    InformationNeed,
    ProbeAttempt,
)
from plugin.agent.information import InformationCapabilityRegistry


class EvidenceStrategy(Protocol):
    """Domain-supplied incorporate + reassessment for one InformationNeed type."""

    def incorporate(
        self,
        result: EvidenceResult,
        hypotheses: list[Any],
        *,
        need: InformationNeed,
    ) -> list[Any]:
        """Apply raw EvidenceResult onto hypotheses; return updated list."""
        ...

    def assess(
        self,
        need: InformationNeed,
        hypotheses: list[Any],
        *,
        last_result: Optional[EvidenceResult] = None,
        attempted_pairs: Optional[set[tuple[str, str]]] = None,
    ) -> EvidenceNeedAssessment: ...


def run_evidence_acquisition(
    need: InformationNeed,
    *,
    registry: InformationCapabilityRegistry,
    strategy: EvidenceStrategy,
    hypotheses: Optional[list[Any]] = None,
) -> EvidenceAcquisitionEpisode:
    """Bounded adaptive gathering driven by strategy reassessment.

    Loop:
      assess → preferred kinds → next untried provider for kind
      → EvidenceResult → strategy.incorporate → reassess

    Budgets:
      - information budget: EVIDENCE_FOUND / NO_EVIDENCE only
      - attempt budget: every registry/provider interaction
    """
    hyps = list(hypotheses if hypotheses is not None else need.competing_hypotheses)
    episode = EvidenceAcquisitionEpisode(
        information_need=need,
        hypotheses=hyps,
        budget_remaining=max(0, int(need.budget)),
        attempt_budget_remaining=max(0, int(need.attempt_budget)),
    )
    last: Optional[EvidenceResult] = None
    blacklisted: set[str] = set()

    while episode.budget_remaining > 0 and episode.attempt_budget_remaining > 0:
        pairs = episode.attempted_pairs()
        assessment = strategy.assess(
            need,
            hyps,
            last_result=last,
            attempted_pairs=pairs,
        )
        episode.assessments.append(assessment)
        if assessment.resolved:
            episode.resolved = True
            episode.resolution_ref = assessment.resolution_ref
            episode.resolution_reason = assessment.resolution_reason
            break

        # Find next (kind, provider) — do not exhaust a kind after one provider.
        choice = registry.select_provider(
            need,
            preferred_kinds=list(assessment.preferred_evidence_kinds),
            attempted_pairs=pairs,
            blacklisted=blacklisted,
        )
        if choice is None:
            episode.uncertainty_notes.extend(assessment.remaining_ambiguities)
            break

        kind, provider = choice
        result = provider.probe(need, evidence_kind=kind, hypotheses=hyps)
        episode.probes_attempted.append(result)
        episode.probe_attempts.append(
            ProbeAttempt(
                evidence_kind=kind,
                provider_id=str(getattr(provider, "provider_id", "")),
                status=result.status,
            )
        )
        last = result
        episode.attempt_budget_remaining -= 1

        # Interpretation belongs to the strategy, not the provider.
        hyps = strategy.incorporate(result, hyps, need=need)
        episode.hypotheses = hyps

        if result.status == EVIDENCE_FOUND:
            episode.evidence_found.append(result)
            need.evidence_already_known.append(
                {
                    "kind": kind,
                    "provider_id": result.provider_id,
                    "payload": dict(result.payload),
                }
            )
        if result.status in {NO_CAPABILITY, ERROR}:
            blacklisted.add(result.provider_id)
            continue
        episode.budget_remaining -= 1

    pairs = episode.attempted_pairs()
    final = strategy.assess(
        need,
        hyps,
        last_result=last,
        attempted_pairs=pairs,
    )
    episode.assessments.append(final)
    if final.resolved:
        episode.resolved = True
        episode.resolution_ref = final.resolution_ref
        episode.resolution_reason = final.resolution_reason
    else:
        episode.uncertainty_notes.extend(final.remaining_ambiguities)

    episode.hypotheses = hyps
    return episode
