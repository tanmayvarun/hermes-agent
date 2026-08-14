"""Generic MetaActor evidence-acquisition episode — domain-neutral.

Knows only InformationNeed, EvidenceResult, budgets, and an EvidenceStrategy.
Domain logic (identity, documents, effects, …) lives in strategy callbacks.
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
)
from plugin.agent.information import InformationCapabilityRegistry


class EvidenceStrategy(Protocol):
    """Domain-supplied reassessment + coverage for one InformationNeed type."""

    def assess(
        self,
        need: InformationNeed,
        hypotheses: list[Any],
        *,
        last_result: Optional[EvidenceResult] = None,
        attempted_kinds: Optional[set[str]] = None,
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
      assess remaining uncertainty → preferred evidence kinds → provider
      → EvidenceResult → update hypotheses → reassess

    Budgets:
      - information budget: EVIDENCE_FOUND / NO_EVIDENCE only
      - attempt budget: every registry/provider interaction (incl. skips/errors)
    """
    hyps = list(hypotheses if hypotheses is not None else need.competing_hypotheses)
    episode = EvidenceAcquisitionEpisode(
        information_need=need,
        hypotheses=hyps,
        budget_remaining=max(0, int(need.budget)),
        attempt_budget_remaining=max(0, int(need.attempt_budget)),
    )
    attempted_kinds: set[str] = set()
    last: Optional[EvidenceResult] = None
    blacklisted: set[str] = set()

    while episode.budget_remaining > 0 and episode.attempt_budget_remaining > 0:
        assessment = strategy.assess(
            need,
            hyps,
            last_result=last,
            attempted_kinds=attempted_kinds,
        )
        episode.assessments.append(assessment)
        if assessment.resolved:
            episode.resolved = True
            episode.resolution_ref = assessment.resolution_ref
            episode.resolution_reason = assessment.resolution_reason
            break

        kind = assessment.next_kind(attempted_kinds)
        if not kind:
            episode.uncertainty_notes.extend(assessment.remaining_ambiguities)
            break

        attempted_kinds.add(kind)
        providers = [
            p
            for p in registry.providers_for(need, kind)
            if getattr(p, "provider_id", "") not in blacklisted
        ]
        if not providers:
            skip = EvidenceResult(
                status=NO_CAPABILITY,
                provider_id="registry",
                evidence_kind=kind,
                notes="no_provider",
            )
            episode.probes_attempted.append(skip)
            last = skip
            episode.attempt_budget_remaining -= 1
            continue

        # V1: first capable provider. Later: rank by latency/cost/gain.
        result = providers[0].probe(need, evidence_kind=kind, hypotheses=hyps)
        episode.probes_attempted.append(result)
        last = result
        episode.attempt_budget_remaining -= 1

        if result.status == EVIDENCE_FOUND:
            episode.evidence_found.append(result)
            need.evidence_already_known.append(
                {"kind": kind, "provider_id": result.provider_id}
            )
        if result.status in {NO_CAPABILITY, ERROR}:
            blacklisted.add(result.provider_id)
            continue
        episode.budget_remaining -= 1

    # Final assessment after budget/exhaustion
    final = strategy.assess(
        need,
        hyps,
        last_result=last,
        attempted_kinds=attempted_kinds,
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
