"""Single MethodFrontier authority for runtime method selection.

AgentRuntime must not implement parallel ranking — it calls ``decide_methods``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from plugin.agent.executive.intention_frame import (
    Intention,
    IntentionFrame,
    MethodFrontier,
    MethodSpec,
    ScoringPolicy,
    rank_eligible,
    score_method,
)
from plugin.agent.executive.method_availability import (
    MethodAvailability,
    evaluate_method_availability,
    should_ask_for_precondition,
)
from plugin.agent.ingress import ExecutionConstraints


@dataclass
class MethodDecision:
    frontier: MethodFrontier
    ranked_executable: List[Tuple[str, float]] = field(default_factory=list)
    availability_by_id: Dict[str, str] = field(default_factory=dict)
    reason_by_id: Dict[str, str] = field(default_factory=dict)
    selected_method_id: str = ""
    ask_method_id: str = ""
    ask_precondition: str = ""
    should_ask: bool = False


def build_frontier_from_specs(
    specs: Sequence[MethodSpec],
    *,
    intention_id: str = "",
    desired_effect: str = "",
) -> IntentionFrame:
    catalog = {str(s.id): s for s in specs if str(getattr(s, "id", "") or "")}
    frontier = MethodFrontier(
        known_untried=list(catalog.keys()),
        catalog=catalog,
    )
    intention = Intention(
        id=intention_id or "runtime_intention",
        objective=desired_effect or "task_effect",
        success_predicate=desired_effect or "task_effect",
    )
    return IntentionFrame(
        intention=intention,
        method_frontier=frontier,
        scoring_policy=ScoringPolicy.for_meta("act"),
    )


def decide_methods(
    specs: Sequence[MethodSpec],
    *,
    constraints: Optional[ExecutionConstraints] = None,
    precondition_facts: Optional[Mapping[str, bool]] = None,
    declined_method_ids: Optional[Set[str]] = None,
    declined_preconditions: Optional[Set[str]] = None,
    blocked_method_ids: Optional[Set[str]] = None,
    failed_preconditions: Optional[Set[str]] = None,
    intention_id: str = "",
    desired_effect: str = "",
) -> MethodDecision:
    """Evaluate availability, reuse MethodFrontier.rank_eligible for executables."""
    frame = build_frontier_from_specs(
        specs, intention_id=intention_id, desired_effect=desired_effect
    )
    frontier = frame.method_frontier
    avail_map: Dict[str, str] = {}
    reason_map: Dict[str, str] = {}
    missing_ready: List[Tuple[MethodSpec, float, str]] = []

    for mid, spec in list(frontier.catalog.items()):
        avail, reason = evaluate_method_availability(
            spec,
            constraints=constraints,
            precondition_facts=precondition_facts,
            declined_method_ids=declined_method_ids,
            declined_preconditions=declined_preconditions,
            blocked_method_ids=blocked_method_ids,
            failed_preconditions=failed_preconditions,
        )
        avail_map[mid] = avail
        reason_map[mid] = reason
        if avail != MethodAvailability.AVAILABLE.value:
            if mid not in frontier.currently_ineligible:
                frontier.currently_ineligible.append(mid)
        if (
            avail == MethodAvailability.MISSING_PRECONDITION.value
            and str(getattr(spec, "readiness", "") or "").strip().lower() == "ready"
        ):
            q = score_method(spec, frame.scoring_policy)
            missing_ready.append((spec, q, reason))

    ranked = rank_eligible(frame)
    decision = MethodDecision(
        frontier=frontier,
        ranked_executable=list(ranked),
        availability_by_id=avail_map,
        reason_by_id=reason_map,
    )
    if ranked:
        decision.selected_method_id = str(ranked[0][0])

    best_available_q = float(ranked[0][1]) if ranked else None
    if missing_ready:
        missing_ready.sort(key=lambda t: t[1], reverse=True)
        ask_spec, ask_q, ask_reason = missing_ready[0]
        if should_ask_for_precondition(
            preferred_spec=ask_spec,
            preferred_availability=MethodAvailability.MISSING_PRECONDITION.value,
            preferred_quality=ask_q,
            best_available_quality=best_available_q,
        ):
            decision.should_ask = True
            decision.ask_method_id = str(ask_spec.id)
            if "missing:" in ask_reason:
                decision.ask_precondition = ask_reason.split("missing:", 1)[-1].split(",")[0]
            # Prefer asking over immediately executing a worse available method.
            decision.selected_method_id = ""
    return decision
