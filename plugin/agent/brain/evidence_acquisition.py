"""Generic MetaActor evidence-acquisition episode — domain-neutral.

Knows only InformationNeed, EvidenceResult, budgets, and an EvidenceStrategy.
Providers return evidence; strategies incorporate + assess.
Attempts are tracked by (evidence_kind, provider_id).
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


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


def _safe_probe(
    provider: Any,
    need: InformationNeed,
    *,
    evidence_kind: str,
    hypotheses: list[Any],
) -> EvidenceResult:
    """Exception boundary: provider failures become EvidenceResult(ERROR)."""
    pid = str(getattr(provider, "provider_id", "") or "unknown")
    try:
        return provider.probe(need, evidence_kind=evidence_kind, hypotheses=hypotheses)
    except Exception as exc:
        logger.warning(
            "evidence provider %s failed for kind=%s: %s", pid, evidence_kind, exc
        )
        return EvidenceResult(
            status=ERROR,
            provider_id=pid,
            evidence_kind=evidence_kind,
            notes=f"{type(exc).__name__}: {exc}",
            payload={"exception": True},
        )


def _is_global_unavailable(result: EvidenceResult) -> bool:
    """True only when the provider declares itself unavailable for all kinds."""
    if result.status not in {NO_CAPABILITY, ERROR}:
        return False
    payload = dict(result.payload or {})
    if payload.get("global_unavailable") is True:
        return True
    notes = (result.notes or "").lower()
    return notes in {"disabled", "provider_unavailable", "global_unavailable"}


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

    Failures are pair-scoped via attempted_pairs unless the provider reports
    global unavailability.
    """
    hyps = list(hypotheses if hypotheses is not None else need.competing_hypotheses)
    episode = EvidenceAcquisitionEpisode(
        information_need=need,
        hypotheses=hyps,
        budget_remaining=max(0, int(need.budget)),
        attempt_budget_remaining=max(0, int(need.attempt_budget)),
    )
    last: Optional[EvidenceResult] = None
    global_unavailable: set[str] = set()

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

        choice = registry.select_provider(
            need,
            preferred_kinds=list(assessment.preferred_evidence_kinds),
            attempted_pairs=pairs,
            blacklisted=global_unavailable,
        )
        if choice is None:
            episode.uncertainty_notes.extend(assessment.remaining_ambiguities)
            break

        kind, provider = choice
        result = _safe_probe(
            provider, need, evidence_kind=kind, hypotheses=hyps
        )
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
            if _is_global_unavailable(result):
                global_unavailable.add(result.provider_id)
            # Pair already recorded — do not consume information budget.
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
