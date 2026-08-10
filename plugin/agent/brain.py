"""Brain: choose the next capability over the accepted world + closed frontier.

Pipeline ownership:

    stage0 assemble → stage1 perceptor (world + suggested_actions/why + affordance_qc)
    critic          → accept / reject / edit Δworld
    node closure    → same-node affordance enrichment (reversible probes)
    brain           → this module: one capability / transition
    runtime         → ground + execute

Resilience: when the closed frontier lacks task-critical same-node affordances
for the current surface, the brain asks to reperceive with an explicit gap
message rather than forcing a bad transition.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Surface → labels that must appear as latent/observed/may_reveal for the node
# to look promising (from the surface contract, not a single task fixture).
_CRITICAL_NODE_LABELS: Dict[str, Tuple[str, ...]] = {
    "conversation": ("forward",),
    "forward_picker": ("send",),
}


def _frontier_labels(frontier: Dict[str, Any]) -> List[str]:
    labels: List[str] = []
    for key in ("observed_actions", "latent_actions", "probe_actions"):
        for entry in frontier.get(key) or []:
            if not isinstance(entry, dict):
                continue
            for raw in (
                entry.get("target_label"),
                entry.get("label"),
                entry.get("text"),
            ):
                if raw:
                    labels.append(str(raw).strip().lower())
            for m in entry.get("may_reveal") or []:
                if isinstance(m, dict) and m.get("label"):
                    labels.append(str(m.get("label")).strip().lower())
                elif m:
                    labels.append(str(m).strip().lower())
    return labels


def barren_frontier_reperceive(brief: Any) -> Tuple[bool, str]:
    """True when the closed frontier lacks critical same-node affordances.

    Hint for the LLM chooser / barren override. Callers should prefer
    ``observe`` + a reperceive query over inventing a transition.
    """
    world = getattr(brief, "world", None) or {}
    if not isinstance(world, dict):
        world = {}
    surface = str(world.get("surface") or "").strip().lower()
    needed = _CRITICAL_NODE_LABELS.get(surface)
    if not needed:
        return False, ""
    objects = [o for o in (world.get("objects") or []) if isinstance(o, dict)]
    task = getattr(brief, "task_state", None)
    phase = str(getattr(task, "phase", "") or "")
    # Conversation: demand Forward only when goal-matched *content* is present.
    # A chat_row / header that matches the source contact is not content — treating
    # it as such starved locate_content (hunt phase) with barren→observe loops.
    if surface == "conversation":
        content_kinds = {
            "message",
            "link",
            "content",
            "attachment",
            "media",
            "image",
            "video",
            "audio",
            "document",
        }
        if not any(
            o.get("matches_goal")
            and str(o.get("kind") or "").strip().lower() in content_kinds
            for o in objects
        ):
            return False, ""
    # Forward picker: Send stays latent until commit. Never treat a missing
    # Send as barren while the destination is still being chosen — that would
    # starve resolve_entity / type_query. Only QC can flag picker barren.
    if surface == "forward_picker":
        qc = getattr(brief, "affordance_qc", None) or {}
        if not (
            isinstance(qc, dict)
            and qc.get("expected_found") is False
            and any("send" in str(x).lower() for x in (qc.get("missing") or []))
            and phase in {"choose_destination", "act_on_content"}
        ):
            return False, ""
        return True, (
            "expected same-node affordances not available on forward_picker: "
            "missing=['send']; reperceive / close the current node"
        )

    frontier = getattr(brief, "affordance_frontier", None) or {}
    if not isinstance(frontier, dict):
        frontier = {}
    labels = set(_frontier_labels(frontier))
    missing = [lab for lab in needed if lab not in labels]
    qc = getattr(brief, "affordance_qc", None) or {}
    qc_miss = (
        isinstance(qc, dict)
        and qc.get("expected_found") is False
        and bool(qc.get("missing") or needed)
    )
    if not missing and not qc_miss:
        return False, ""
    if not missing and qc_miss:
        missing = [str(x).lower() for x in (qc.get("missing") or list(needed))[:4]]
    return True, (
        f"expected same-node affordances not available on {surface}: "
        f"missing={missing}; reperceive / close the current node"
    )


def request_reperceive(
    execution_state: Any,
    features: Any,
    *,
    reason: str,
    missing: Optional[List[str]] = None,
) -> None:
    """Tell the executive the next look must hunt for missing affordances."""
    query = {
        "objective": "expected affordances unavailable on current node",
        "questions": [
            reason[:200],
            "Which reversible probe (hover / reveal_actions / dropdown) would expose them?",
        ],
        "focus": "task-relevant object and its latent menu",
        "depth": "affordance_closure",
        "completion_condition": "critical same-node affordances present on the frontier",
        "missing_affordances": list(missing or [])[:8],
    }
    if execution_state is not None:
        try:
            execution_state.last_perception_query = query
            execution_state.force_deliberation = True
            execution_state.reperceive_affordance_gap = reason[:200]
        except Exception:
            pass
    if features is not None and isinstance(getattr(features, "extras", None), dict):
        features.extras["reperceive_affordance_gap"] = {
            "reason": reason[:200],
            "missing": list(missing or [])[:8],
            "query": query,
        }


def motor_fingerprint(
    family: str,
    target: str = "",
    point: Any = None,
) -> str:
    """Stable key for 'do not re-issue this failed motor unchanged'."""
    fam = str(family or "").strip().lower()
    tgt = str(target or "").strip().lower()
    pt = ""
    if isinstance(point, (list, tuple)) and len(point) >= 2:
        try:
            pt = f"{float(point[0]):.0f},{float(point[1]):.0f}"
        except (TypeError, ValueError):
            pt = ""
    return f"{fam}|{tgt}|{pt}"


def apply_surprise_explanation(
    outcome: Any,
    execution_state: Any,
    *,
    features: Any = None,
) -> Any:
    """Steer the brain after a REFLECT look using ReflectDiagnosis.

    Authoritative repairs override the chooser (including Observe). Weak
    diagnoses still only reperceive. Never re-issues an identical failed motor.
    """
    from plugin.agent.decision_consultation import DecisionOutcome
    from plugin.agent.reflect_diagnosis import normalize_reflect_diagnosis
    from plugin.agent.unified_cognition import explanation_is_authoritative

    if outcome is None or execution_state is None:
        return outcome
    expl = getattr(execution_state, "last_surprise_explanation", None)
    if not isinstance(expl, dict) or not expl:
        return outcome

    diagnosis = normalize_reflect_diagnosis(expl)
    authoritative = explanation_is_authoritative(expl)
    recommended = str(diagnosis.recommended_next or "reperceive").strip().lower()
    cause = str(diagnosis.cause or "unknown")
    detail = str(diagnosis.detail or "")[:200]
    repair = diagnosis.repair
    conf = float(diagnosis.confidence or 0.0)

    # Record the failed motor + diagnosis do_not_repeat keys.
    step = getattr(execution_state, "last_plan_step", None)
    failed_key = motor_fingerprint(
        str(getattr(step, "action_family", "") or getattr(execution_state, "last_action", "") or ""),
        str(getattr(step, "semantic_target", "") or ""),
        getattr(step, "target_point", None) if step is not None else None,
    )
    if failed_key and failed_key != "||":
        try:
            execution_state.last_failed_motor_key = failed_key
            keys = list(getattr(execution_state, "avoid_motor_keys", None) or [])
            if failed_key not in keys:
                keys.append(failed_key)
            for item in diagnosis.do_not_repeat:
                if item and item not in keys:
                    keys.append(item)
            execution_state.avoid_motor_keys = keys[-16:]
        except Exception:
            pass

    # Stash motor constraint for the actor/executor path.
    if repair.motor_constraint:
        try:
            execution_state.reflect_motor_constraint = repair.motor_constraint
        except Exception:
            pass

    if not authoritative or recommended == "reperceive" or repair.kind == "reperceive":
        request_reperceive(
            execution_state,
            features,
            reason=detail or f"reflect:{cause}: need another look",
            missing=[],
        )
        return DecisionOutcome(
            ok=True,
            capability="observe",
            target="",
            why=f"reflect ({cause}, conf={conf}): {detail or 'reperceive'}",
            confidence=conf,
            realization="reflect_reperceive",
        )

    # Exploration-controller retreat → revert_effects capability (not a meta).
    if (
        recommended in {"backtrack", "explore"}
        or repair.kind in {"backtrack_dismiss", "invoke_revert_effects"}
    ):
        return DecisionOutcome(
            ok=True,
            capability="revert_effects",
            target=str(repair.target or "").strip(),
            why=(
                f"reflect backtrack/revert ({cause}/{diagnosis.locus}): "
                f"{repair.detail or detail}"
            ),
            confidence=conf,
            realization=(
                "reflect_repair:invoke_revert_effects"
                if repair.kind == "invoke_revert_effects"
                else "reflect_backtrack"
            ),
        )

    if repair.kind == "re_ground_then_act":
        # Consume post-revert stash once the reselect repair is issued.
        try:
            pending = getattr(execution_state, "pending_repair_after_revert", None)
            if isinstance(pending, dict) and pending.get("reason") == "post_revert_reselect":
                execution_state.pending_repair_after_revert = None
        except Exception:
            pass

    # Authoritative act repairs: override Observe / wrong chooser with the repair.
    # Motor landing on the *same* semantic target must NOT become object geometry
    # (inconclusive_grounding → re-perceive). Geometry on a *different* control
    # (e.g. toolbar Forward after a miss) is a new grounded affordance — allowed.
    act_repairs = {
        "follow_observed_transition",
        "retry_same_affordance_different_motor",
        "retry_with_corrected_geometry",
        "re_ground_then_act",
        "invoke_revert_effects",
    }
    same_target_geometry_retry = repair.kind in {
        "retry_with_corrected_geometry",
        "re_ground_then_act",
    } and cause in {
        "stale_geometry",
        "motor_miss",
        "motor_path",
        "wrong_target",
        "no_effect",
        "unknown",
        "",
    }
    if same_target_geometry_retry:
        try:
            execution_state.reflect_corrected_point = None
            execution_state.attempt_validity = "inconclusive_grounding"
        except Exception:
            pass
        request_reperceive(
            execution_state,
            features,
            reason=(
                f"inconclusive_grounding ({cause}): motor landing is not object "
                f"geometry — re-perceive then re-ground"
            ),
        )
        return DecisionOutcome(
            ok=False,
            capability="observe",
            target="",
            why=(
                f"inconclusive_grounding ({cause}/{diagnosis.locus}): "
                f"do not adopt motor landing as semantic geometry; "
                f"{repair.detail or detail}"
            ),
            confidence=conf,
            realization="inconclusive_grounding_reperceive",
        )
    if repair.kind in act_repairs and repair.capability:
        geo = repair.geometry or diagnosis.corrected_point
        if isinstance(geo, (list, tuple)) and len(geo) >= 2:
            try:
                # New control geometry (toolbar etc.) — not object-identity rewrite.
                execution_state.reflect_corrected_point = [float(geo[0]), float(geo[1])]
            except (TypeError, ValueError):
                execution_state.reflect_corrected_point = None
        return DecisionOutcome(
            ok=True,
            capability=str(repair.capability).strip().lower().replace("-", "_"),
            target=str(repair.target or "").strip(),
            why=(
                f"reflect repair {repair.kind} ({cause}/{diagnosis.locus}): "
                f"{repair.detail or detail}"
            ),
            confidence=conf,
            realization=f"reflect_repair:{repair.kind}",
        )

    # recommended == act without structured repair: legacy corrected_point path.
    if not isinstance(outcome, DecisionOutcome):
        return outcome
    chosen_point = None
    corrected = diagnosis.corrected_point or expl.get("corrected_point")
    has_corrected = isinstance(corrected, (list, tuple)) and len(corrected) >= 2
    if has_corrected:
        chosen_point = corrected
    chosen_key = motor_fingerprint(
        outcome.capability,
        outcome.target,
        chosen_point,
    )
    failed_parts = failed_key.split("|") if failed_key else []
    chosen_parts = chosen_key.split("|") if chosen_key else []
    failed_fam_tgt = "|".join(failed_parts[:2]) if failed_parts else ""
    chosen_fam_tgt = "|".join(chosen_parts[:2]) if chosen_parts else ""
    same_point = (
        len(failed_parts) >= 3
        and len(chosen_parts) >= 3
        and failed_parts[2]
        and failed_parts[2] == chosen_parts[2]
    )
    block_causes = {
        "wrong_target",
        "stale_geometry",
        "motor_miss",
        "motor_path",
        "no_effect",
        "partial_effect",
        "unknown",
        "",
    }
    if (
        failed_fam_tgt
        and chosen_fam_tgt
        and failed_fam_tgt == chosen_fam_tgt
        and (
            same_point
            or not failed_parts[2:]
            or cause in block_causes
        )
        and cause in block_causes
    ):
        # Never promote motor-corrected XY into the next act as object truth.
        try:
            execution_state.reflect_corrected_point = None
            if cause in {"stale_geometry", "motor_miss", "motor_path", "wrong_target"}:
                execution_state.attempt_validity = "inconclusive_grounding"
        except Exception:
            pass
        request_reperceive(
            execution_state,
            features,
            reason=f"reflect blocked repeat of failed {failed_fam_tgt}: {detail}",
            missing=[],
        )
        return DecisionOutcome(
            ok=True,
            capability="observe",
            target="",
            why=f"reflect blocked repeat ({cause}): {detail}",
            confidence=conf,
            realization="reflect_block_repeat",
        )
    return outcome


def choose_next_capability(
    proposal: Any,
    goal: Any,
    features: Any = None,
    execution_state: Any = None,
    *,
    chooser: Any = None,
) -> Dict[str, Any]:
    """Fill ``proposal.next_action`` from accepted world + closed frontier.

    Stage1 ``suggested_actions`` (with why) are advice in the decision brief —
    never auto-executed. Returns the consultation trace.
    """
    if proposal is None:
        return {}
    # Prefer proposal's explanation onto state before consultation.
    expl = getattr(proposal, "surprise_explanation", None)
    if isinstance(expl, dict) and expl and execution_state is not None:
        try:
            from plugin.agent.unified_cognition import normalize_surprise_explanation

            execution_state.last_surprise_explanation = normalize_surprise_explanation(expl)
        except Exception:
            pass
    try:
        from plugin.agent.decision_consultation import apply_decision_consultation

        return apply_decision_consultation(
            proposal,
            goal,
            features=features,
            execution_state=execution_state,
            chooser=chooser,
        )
    except Exception as exc:
        logger.warning("Brain choice skipped: %s", exc)
        return {}


def publish_brain_choice(features: Any, proposal: Any, trace: Optional[Dict[str, Any]] = None) -> None:
    """Record the brain's choice for traces — never as a perception nudge."""
    if features is None or not isinstance(getattr(features, "extras", None), dict):
        return
    action = dict(getattr(proposal, "next_action", None) or {})
    features.extras["brain_choice"] = {
        "family": str(action.get("family") or ""),
        "target": str(action.get("target_label") or action.get("text") or ""),
        "confidence": action.get("confidence"),
        "trace": dict(trace or {}) if isinstance(trace, dict) else {},
    }
