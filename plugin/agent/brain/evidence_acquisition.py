"""Generic MetaActor evidence-acquisition episode.

Adaptive: after each EvidenceResult, choose the next useful evidence kind.
Budget counts only meaningful probe attempts (EVIDENCE_FOUND / NO_EVIDENCE).
NO_CAPABILITY / ERROR do not consume the information budget.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from plugin.agent.brain.identity_hypothesis import IdentityHypothesis, hypotheses_from_ranked
from plugin.agent.brain.information_need import (
    EVIDENCE_FOUND,
    ERROR,
    NO_CAPABILITY,
    EvidenceAcquisitionEpisode,
    EvidenceResult,
    InformationNeed,
)
from plugin.agent.information import (
    InformationCapabilityRegistry,
    default_registry_for_entity_resolution,
)


def _default_kind_priority(need: InformationNeed) -> list[str]:
    missing = list(need.missing_features())
    # Prefer cheap local context first; world channel activity last.
    order = [
        "working_context",
        "memory_aggregates",
        "reference_history",
        "channel_activity",
    ]
    prioritized = [k for k in order if k in missing]
    for k in missing:
        if k not in prioritized:
            prioritized.append(k)
    return prioritized


def choose_next_evidence_kind(
    need: InformationNeed,
    *,
    attempted_kinds: set[str],
    last_result: Optional[EvidenceResult],
    hypotheses: list[Any],
) -> Optional[str]:
    """Adaptive next kind — not a blind fixed pipeline.

    Early stop suggestion: if working context uniquely prefers one hypothesis,
    still allow caller to resolve; we stop proposing further kinds when
    discrimination is already established at the chooser level.
    """
    if isinstance(hypotheses, list) and hypotheses:
        l1 = [
            h
            for h in hypotheses
            if isinstance(h, IdentityHypothesis)
            and (h.context.l1_preferred or h.context.working_context_hit)
        ]
        if len(l1) == 1 and last_result and last_result.evidence_kind == "working_context":
            # Working context already discriminates — no further probes needed.
            return None

        refs = [
            h
            for h in hypotheses
            if isinstance(h, IdentityHypothesis) and h.context.reference_support >= 1.0
        ]
        if len(refs) == 1 and last_result and last_result.evidence_kind == "reference_history":
            return None

    for kind in _default_kind_priority(need):
        if kind not in attempted_kinds:
            return kind
    return None


def run_evidence_acquisition(
    need: InformationNeed,
    *,
    registry: InformationCapabilityRegistry,
    hypotheses: Optional[list[Any]] = None,
    choose_next: Optional[Callable[..., Optional[str]]] = None,
) -> EvidenceAcquisitionEpisode:
    """Run bounded adaptive gathering until resolved signal or budget exhausts.

    Does **not** commit bindings or apply ActionRiskPolicy.
    """
    hyps = list(hypotheses if hypotheses is not None else need.competing_hypotheses)
    episode = EvidenceAcquisitionEpisode(
        information_need=need,
        hypotheses=hyps,
        budget_remaining=max(0, int(need.budget)),
    )
    chooser = choose_next or choose_next_evidence_kind
    attempted_kinds: set[str] = set()
    last: Optional[EvidenceResult] = None
    blacklisted: set[str] = set()

    while episode.budget_remaining > 0:
        kind = chooser(
            need,
            attempted_kinds=attempted_kinds,
            last_result=last,
            hypotheses=hyps,
        )
        if not kind:
            break
        attempted_kinds.add(kind)
        providers = [
            p
            for p in registry.providers_for(need, kind)
            if getattr(p, "provider_id", "") not in blacklisted
        ]
        if not providers:
            # No capable provider — do not spend budget.
            skip = EvidenceResult(
                status=NO_CAPABILITY,
                provider_id="registry",
                evidence_kind=kind,
                notes="no_provider",
            )
            episode.probes_attempted.append(skip)
            last = skip
            continue

        result = providers[0].probe(need, evidence_kind=kind, hypotheses=hyps)
        episode.probes_attempted.append(result)
        last = result
        if result.status == EVIDENCE_FOUND:
            episode.evidence_found.append(result)
            need.evidence_already_known.append(
                {"kind": kind, "provider_id": result.provider_id}
            )
        if result.status in {NO_CAPABILITY, ERROR}:
            blacklisted.add(result.provider_id)
            # Unavailable / error: do not consume information budget.
            continue
        # Meaningful attempt
        episode.budget_remaining -= 1

    episode.hypotheses = hyps
    return episode


def acquire_for_entity_resolution(
    memory: Any,
    ranked: list[Any],
    *,
    surface: str,
    channel: str = "whatsapp",
    working_context: Optional[dict[str, Any]] = None,
    budget: int = 4,
    world_probes: bool = True,
    registry: Optional[InformationCapabilityRegistry] = None,
) -> EvidenceAcquisitionEpisode:
    """Identity use-case entry: build need + hypotheses, run generic episode."""
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
        desired_discrimination=(
            "working_context,memory_aggregates,reference_history,channel_activity"
        ),
        budget=budget,
        context={
            "channel": channel,
            "working_context": dict(working_context or {}),
        },
    )
    reg = registry or default_registry_for_entity_resolution(
        memory, world_probes=world_probes
    )
    return run_evidence_acquisition(need, registry=reg, hypotheses=hyps)
