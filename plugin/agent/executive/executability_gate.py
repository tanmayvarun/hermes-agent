"""Executability gate — the production path the controller uses before meta.

Extracted so L3 trajectory / controller-replay evals can drive the *same*
function as the live loop, instead of re-orchestrating detect→child→resume
inside the scorer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from plugin.agent.executive.blocking import (
    ExecutabilityStatus,
    assess_executability,
    detect_warnings_and_blockers,
    resolve_methods_for_effect,
)
from plugin.agent.executive.intention_frame import (
    Intention,
    IntentionFrame,
    IntentionOrigin,
    active_intention_frame,
    ensure_child_for_precondition,
    evaluate_intention_success,
    push_intention_frame,
    resume_parent_after_child,
)
from plugin.agent.executive.meta_action import MetaAction, MetaChoice


@dataclass
class ExecutabilityGateResult:
    """Outcome of one gate evaluation (one controller turn equivalent)."""

    skip_normal_meta: bool = False
    meta: Optional[MetaChoice] = None
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    blockers: List[Dict[str, Any]] = field(default_factory=list)
    assessment: Optional[Dict[str, Any]] = None
    resume: Optional[Dict[str, Any]] = None
    child_id: str = ""
    effect_key: str = ""
    phase: str = ""  # executability | prerequisite_child | prerequisite_child_act | prerequisite_resume | ...

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skip_normal_meta": self.skip_normal_meta,
            "meta": self.meta.to_dict() if self.meta is not None else None,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "assessment": self.assessment,
            "resume": self.resume,
            "child_id": self.child_id,
            "effect_key": self.effect_key,
            "phase": self.phase,
        }


def run_executability_gate(
    state: Any,
    *,
    observation_texts: Sequence[str] = (),
    view: Optional[Dict[str, Any]] = None,
    features: Optional[Any] = None,
    facts: Optional[Dict[str, Any]] = None,
    app: str = "",
    goal_kind: str = "goal",
    intention_id: str = "",
    seed_parent_if_missing: bool = True,
    iteration: int = 0,
) -> ExecutabilityGateResult:
    """Production executability interruption (same semantics as controller gate)."""
    view = view if isinstance(view, dict) else {}
    result = ExecutabilityGateResult()

    iframe = active_intention_frame(state)
    intent_id = (
        str(iframe.intention.id)
        if iframe is not None
        else (intention_id or f"i_goal_{iteration}" or goal_kind)
    )
    warns, blockers = detect_warnings_and_blockers(
        observation_texts=observation_texts,
        view=view,
        features=features,
        intention_id=intent_id,
        app=app,
    )
    result.warnings = [w.to_dict() for w in warns]
    result.blockers = [b.to_dict() for b in blockers]
    if state is not None:
        try:
            state.last_warnings = result.warnings
            state.last_blocking_conditions = result.blockers
        except Exception:
            pass

    extras: Dict[str, Any] = {}
    if features is not None:
        if hasattr(features, "extras") and isinstance(features.extras, dict):
            extras = dict(features.extras)
        elif isinstance(features, dict):
            extras = dict(features.get("extras") or features)

    exec_facts: Dict[str, Any] = {
        "agent_owned_reclaimable_bytes": 1,
        "blocked_app_recoverable": True,
        "storage_pressure": bool(extras.get("storage_pressure") or view.get("storage_pressure")),
    }
    if isinstance(facts, dict):
        exec_facts.update(facts)

    # Active prereq child path.
    if (
        iframe is not None
        and iframe.parent_intention_id
        and str(iframe.prerequisite_effect_key or "")
    ):
        child_world = dict(view)
        child_world.setdefault("surface", child_world.get("screen") or "")
        last_ev = getattr(state, "last_housekeeping_evidence", None)
        if isinstance(last_ev, dict):
            if last_ev.get("available_storage_bytes") is not None:
                child_world["available_storage_bytes"] = last_ev[
                    "available_storage_bytes"
                ]
            if last_ev.get("headroom_met"):
                child_world["free_storage_satisfied"] = True
            if last_ev.get("bytes_reclaimed"):
                child_world["bytes_reclaimed"] = last_ev["bytes_reclaimed"]
        if evaluate_intention_success(iframe, world=child_world):
            resume = resume_parent_after_child(
                state,
                world=child_world,
                parent_blockers=blockers,
                facts={
                    **exec_facts,
                    "available_storage_bytes": child_world.get(
                        "available_storage_bytes"
                    ),
                    "app_operational": not bool(exec_facts.get("storage_pressure")),
                },
            )
            result.resume = resume
            result.phase = "prerequisite_resume"
            result.skip_normal_meta = False
            return result

        cap = ""
        known = list(getattr(iframe.method_frontier, "known_untried", None) or [])
        if known:
            spec = (iframe.method_frontier.catalog or {}).get(known[0])
            if spec is not None:
                cap = str(spec.capability or known[0])
        if not cap:
            cap = "relieve_host_storage"
        result.meta = MetaChoice(
            action=MetaAction.ACT,
            reason="prerequisite_child_method",
            capability=cap,
        )
        result.skip_normal_meta = True
        result.child_id = iframe.intention.id
        result.effect_key = str(iframe.prerequisite_effect_key or "")
        result.phase = "prerequisite_child_act"
        return result

    # Parent (or no frame).
    if iframe is not None:
        intent_id = str(iframe.intention.id)
    assessment = assess_executability(
        intention_id=intent_id,
        blockers=blockers,
        world=view,
        facts=exec_facts,
    )
    result.assessment = assessment.to_dict()
    result.phase = "executability"

    if (
        assessment.status == ExecutabilityStatus.BLOCKED_RESOLVABLE.value
        and assessment.resolvable_conditions
    ):
        bc = assessment.resolvable_conditions[0]
        key = bc.semantic_key()
        methods = [
            (m.capability, m.capability)
            for m in resolve_methods_for_effect(bc.required_effect, facts=exec_facts)
        ]
        if iframe is None and seed_parent_if_missing:
            iframe = IntentionFrame(
                intention=Intention(
                    id=intent_id
                    if str(intent_id).startswith("i_")
                    else f"i_goal_{iteration}",
                    objective=str(goal_kind or "goal"),
                    success_predicate="goal_complete",
                    created_from=IntentionOrigin(kind="goal"),
                )
            )
            push_intention_frame(state, iframe)
        if iframe is not None:
            child = ensure_child_for_precondition(
                state,
                iframe,
                effect_key=key,
                success_predicate=key,
                objective=f"Resolve {key}",
                methods=methods,
                blocking_condition_id=bc.id,
            )
            if child is not None and methods:
                result.meta = MetaChoice(
                    action=MetaAction.ACT,
                    reason="blocked_resolvable_prerequisite",
                    capability=str(methods[0][0]),
                )
                result.skip_normal_meta = True
                result.child_id = child.intention.id
                result.effect_key = key
                result.phase = "prerequisite_child"
                return result
    elif assessment.status == ExecutabilityStatus.UNKNOWN.value:
        if state is not None:
            try:
                state.must_executive_reperceive = True
            except Exception:
                pass
        result.meta = MetaChoice(
            action=MetaAction.PERCEIVE,
            reason="executability_unknown",
            capability="",
        )
        result.skip_normal_meta = True
        return result
    elif assessment.status == ExecutabilityStatus.BLOCKED_UNRESOLVABLE.value:
        result.meta = MetaChoice(
            action=MetaAction.ASK,
            reason="blocked_unresolvable_prerequisite",
            capability="",
        )
        result.skip_normal_meta = True
        return result

    return result
