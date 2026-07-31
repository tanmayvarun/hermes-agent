"""Trajectory-aware progress assessment + transition outcome evaluation."""

from __future__ import annotations

from typing import Any, Dict, Optional

from plugin.agent.action import Action
from plugin.agent.goal import Goal, GoalStatus, evaluate_goal
from plugin.agent.transition.attribution import attribute_transition
from plugin.agent.transition.context import (
    affordance_delta,
    contradiction_evidence,
    detect_goal_affordances,
    latent_target_in_focus,
    update_interaction_context,
)
from plugin.agent.transition.types import (
    ContextualBelief,
    InteractionContext,
    ProgressAssessment,
    TransitionAttempt,
    TransitionOutcome,
    TransitionResult,
)
from plugin.worldmodel.entities.normalize import _clean_label
from plugin.worldmodel.capability import capability_graph_delta
from plugin.worldmodel.model import WorldModel


def _stem_match(haystack: str, needle: str) -> bool:
    h = _clean_label(haystack or "").lower().rstrip("….")
    n = _clean_label(needle or "").lower().rstrip("….")
    if not h or not n or len(n) < 2:
        return False
    return n in h or h.startswith(n) or n.startswith(h[: max(2, min(len(h), len(n)))])


def _copy_belief(bel: ContextualBelief) -> ContextualBelief:
    return ContextualBelief(
        value=bel.value,
        confidence=bel.confidence,
        observability=bel.observability,
        last_confirmed_world=bel.last_confirmed_world,
    )


def _prediction_dict(action: Action) -> Dict[str, Any]:
    pred = getattr(action, "prediction", None)
    if pred is None:
        return {}
    if hasattr(pred, "to_dict") and callable(pred.to_dict):
        try:
            data = pred.to_dict()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    if isinstance(pred, dict):
        return dict(pred)
    return {}


def _prediction_error(
    prediction: Dict[str, Any],
    assessment: ProgressAssessment,
    outcome: TransitionOutcome,
    after_view: Dict[str, Any],
) -> Dict[str, Any]:
    if not prediction:
        return {}
    error: Dict[str, Any] = {}
    predicted_outcome = str(prediction.get("predicted_outcome") or "").strip()
    if predicted_outcome and predicted_outcome != outcome.value:
        error["outcome"] = {
            "predicted": predicted_outcome,
            "observed": outcome.value,
        }
    expected_surface = str(prediction.get("expected_surface") or "").strip()
    expected_affordances = [
        str(a).strip() for a in (prediction.get("expected_affordances") or []) if str(a).strip()
    ]
    if expected_affordances:
        actual_affordances = {
            str(a).strip()
            for a in (assessment.newly_relevant_affordances or [])
            if str(a).strip()
        }
        missing = [a for a in expected_affordances if a not in actual_affordances]
        if missing:
            error["affordances"] = {
                "expected": expected_affordances,
                "observed": list(actual_affordances),
                "missing": missing,
            }
    if expected_surface:
        observed_surface = str(after_view.get("screen") or after_view.get("active_surface") or "").strip()
        if observed_surface and observed_surface != expected_surface:
            error["surface"] = {
                "expected": expected_surface,
                "observed": observed_surface,
            }
    return error


def _constraint_bits(
    view: Dict[str, Any],
    goal: Goal,
    features: Optional[Dict[str, Any]] = None,
    *,
    ctx: Optional[InteractionContext] = None,
    use_latent: bool = True,
) -> Dict[str, float]:
    """Goal-constraint evidence bits — occluded focus uses latent context, not FALSE."""
    feats = features or {}
    open_c = str(view.get("open_conversation") or "")
    if use_latent and ctx is not None:
        target_focus = latent_target_in_focus(ctx, goal, view)
    else:
        ref = goal.ensure_reference() if goal.contact else None
        name = (ref.active_name if ref else goal.contact) or ""
        target_focus = 1.0 if (name and _stem_match(open_c, name)) else 0.0
        if not target_focus and goal.contact and _stem_match(
            open_c, goal.contact.split()[0] if goal.contact else ""
        ):
            target_focus = 0.7

    ringing = 1.0 if (
        str(view.get("call_state") or "").lower() == "ringing"
        or feats.get("call_ringing")
    ) else 0.0
    affs = detect_goal_affordances(goal, view)
    call_affordance = 1.0 if (
        view.get("voice_call_available")
        or feats.get("call_available")
        or "initiate_voice" in affs
        or "open_call_menu" in affs
        or "start_call" in affs
    ) else 0.0
    resolved_vis = 1.0 if feats.get("has_named_entity") else 0.0
    if use_latent and ctx and ctx.open_conversation.effective and not resolved_vis:
        resolved_vis = 0.7
    query_ok = 1.0 if feats.get("query_matches_goal") else 0.0
    no_dialog = 0.0 if (view.get("unexpected_dialogs") or feats.get("has_dialog")) else 1.0

    return {
        "ringing": ringing,
        "target_in_focus": target_focus,
        "call_affordance": call_affordance,
        "target_visible": resolved_vis,
        "query_aligned": query_ok,
        "no_blocking_dialog": no_dialog,
    }


def assess_progress(
    *,
    goal: Goal,
    before_view: Dict[str, Any],
    after_view: Dict[str, Any],
    before_features: Optional[Dict[str, Any]] = None,
    after_features: Optional[Dict[str, Any]] = None,
    transition: Optional[TransitionResult] = None,
    interaction_context: Optional[InteractionContext] = None,
    execution: Optional[Dict[str, Any]] = None,
) -> ProgressAssessment:
    ctx_before = interaction_context
    if ctx_before is None:
        ctx_before = InteractionContext()
        update_interaction_context(ctx_before, goal=goal, view=before_view, features=before_features)
    ctx_after = InteractionContext(
        selected_target=ctx_before.selected_target,
        target_confidence=ctx_before.target_confidence,
        originating_world=ctx_before.originating_world,
        active_surface=ctx_before.active_surface,
        open_conversation=_copy_belief(ctx_before.open_conversation),
        reversible=ctx_before.reversible,
    )
    update_interaction_context(ctx_after, goal=goal, view=after_view, features=after_features)

    b_bits = _constraint_bits(before_view, goal, before_features, ctx=ctx_before, use_latent=True)
    a_bits = _constraint_bits(after_view, goal, after_features, ctx=ctx_after, use_latent=True)
    notes: list = []
    occlusion_notes: list = []

    b_vis = _constraint_bits(before_view, goal, before_features, use_latent=False)
    a_vis = _constraint_bits(after_view, goal, after_features, use_latent=False)
    if a_vis["target_in_focus"] < b_vis["target_in_focus"] and a_bits["target_in_focus"] >= 0.75 * max(
        b_bits["target_in_focus"], 0.01
    ):
        occlusion_notes.append("target_occluded_not_lost")
        notes.append("target_occluded_not_lost")

    constraint_delta = sum(a_bits.values()) - sum(b_bits.values())
    if a_bits["ringing"] > b_bits["ringing"]:
        notes.append("ringing_gained")
    if a_bits["target_in_focus"] > b_bits["target_in_focus"]:
        notes.append("target_focus_gained")
    if a_bits["target_in_focus"] < b_bits["target_in_focus"] - 0.15:
        notes.append("target_focus_lost")

    bf = before_features or {}
    af = after_features or {}
    conf_b = float(bf.get("resolution_confidence") or 0)
    conf_a = float(af.get("resolution_confidence") or 0)
    res_delta = (conf_a - conf_b) * 0.5 + (a_bits["target_in_focus"] - b_bits["target_in_focus"]) * 0.5

    mean_b = float(bf.get("mean_belief") or bf.get("worldview_score") or 0.5)
    mean_a = float(af.get("mean_belief") or af.get("worldview_score") or 0.5)
    conflicts_b = len(bf.get("fusion_conflicts") or [])
    conflicts_a = len(af.get("fusion_conflicts") or [])
    unc_delta = (mean_a - mean_b) + 0.05 * (conflicts_b - conflicts_a)
    if bf.get("needs_reobserve") and not af.get("needs_reobserve"):
        unc_delta += 0.1
        notes.append("reobserve_cleared")

    aff = affordance_delta(goal, before_view, after_view)
    aff_delta = aff.relevance_score
    cap_delta = capability_graph_delta(
        (before_features or {}).get("capability_graph"),
        (after_features or {}).get("capability_graph"),
    )
    if cap_delta.get("new_capabilities"):
        notes.append("new_capabilities:" + ",".join(cap_delta["new_capabilities"][:8]))
    if cap_delta.get("lost_capabilities"):
        notes.append("lost_capabilities:" + ",".join(cap_delta["lost_capabilities"][:8]))
    if goal.kind == "whatsapp_voice_call":
        aff_delta += (a_bits["call_affordance"] - b_bits["call_affordance"]) * 0.25
        if a_bits["target_in_focus"] and not b_bits["target_in_focus"]:
            aff_delta += 0.3
        if after_view.get("search_query") and not before_view.get("search_query"):
            aff_delta += 0.15
            notes.append("search_populated")
    if aff.newly_available:
        notes.append("new_affordances:" + ",".join(aff.newly_available))
    if cap_delta.get("new_capabilities"):
        notes.append("new_capabilities_affordance:" + ",".join(cap_delta["new_capabilities"][:8]))

    risk = 0.0
    if af.get("leftover_call") and not bf.get("leftover_call"):
        risk += 0.3
        notes.append("leftover_call_appeared")
    if (after_view.get("unexpected_dialogs") or af.get("has_dialog")) and not (
        before_view.get("unexpected_dialogs") or bf.get("has_dialog")
    ):
        risk += 0.25
        notes.append("dialog_appeared")
    if (
        a_bits["target_in_focus"] < b_bits["target_in_focus"] - 0.2
        and a_bits["ringing"] <= b_bits["ringing"]
        and "target_occluded_not_lost" not in occlusion_notes
        and not aff.newly_available
    ):
        risk += 0.2

    contradictions = contradiction_evidence(
        goal=goal,
        before_view=before_view,
        after_view=after_view,
        ctx=ctx_after,
        features_after=af,
    )
    if contradictions:
        notes.extend(contradictions)
        risk += 0.35 * len(contradictions)

    newly_relevant_affordances = list(
        dict.fromkeys(
            [
                *[str(a).strip() for a in aff.newly_available if str(a).strip()],
                *[str(a).strip() for a in (cap_delta.get("new_capabilities") or []) if str(a).strip()],
            ]
        )
    )

    progress = (
        0.30 * constraint_delta
        + 0.25 * res_delta
        + 0.15 * unc_delta
        + 0.40 * aff_delta
        - 0.40 * risk
    )
    tr = transition
    changed = bool(tr.changed) if tr is not None else abs(progress) >= 0.05
    change_score = tr.change_score if tr is not None else abs(progress)
    if tr is not None and not tr.changed and abs(progress) < 0.05:
        notes.append("no_observable_change")

    exec_ok = True if execution is None else bool(execution.get("ok", True))

    context_preserved = (
        a_bits["target_in_focus"] >= 0.7
        or "target_occluded_not_lost" in occlusion_notes
        or (ctx_after.open_conversation.effective and not contradictions)
    )
    state_understood = bool(
        aff.newly_available
        or a_bits["ringing"]
        or (after_view.get("open_conversation") and a_bits["target_in_focus"] >= 0.9)
        or (change_score < 0.2)
    )
    if changed and change_score >= 0.35 and not aff.newly_available and not a_bits["ringing"]:
        state_understood = False
        notes.append("novel_state_uninterpreted")

    goal_progress = "unknown"
    if contradictions and not aff.newly_available:
        goal_progress = "regression"
    elif a_bits["ringing"] > b_bits["ringing"]:
        goal_progress = "clear"
    elif aff.relevance_score >= 0.4 or (changed and aff.newly_available and context_preserved):
        goal_progress = "promising"
    elif progress >= 0.08:
        goal_progress = "clear"
    elif not changed:
        goal_progress = "none"
    elif progress <= -0.15 and contradictions:
        goal_progress = "regression"

    return ProgressAssessment(
        goal_constraints_satisfied_delta=round(constraint_delta, 4),
        target_resolution_delta=round(res_delta, 4),
        uncertainty_delta=round(unc_delta, 4),
        affordance_relevance_delta=round(aff_delta, 4),
        irreversible_risk_delta=round(risk, 4),
        progress_delta=round(progress, 4),
        notes=notes,
        execution_succeeded=exec_ok,
        meaningful_change=changed and change_score >= 0.12,
        state_understood=state_understood,
        goal_progress=goal_progress,
        newly_relevant_affordances=newly_relevant_affordances,
        context_preserved=context_preserved,
        branch_reversible=True,
        contradiction_evidence=contradictions,
        affordance_delta=aff.to_dict(),
        occlusion_notes=occlusion_notes,
        predicted_transition=str(cap_delta.get("predicted_transition") or ""),
        observed_transition=str(cap_delta.get("observed_transition") or ""),
        new_capabilities=list(cap_delta.get("new_capabilities") or []),
        lost_capabilities=list(cap_delta.get("lost_capabilities") or []),
        frontier_delta=float(cap_delta.get("frontier_delta") or 0.0),
        confidence_delta=float(cap_delta.get("confidence_delta") or 0.0),
        selected_capability_id=str(
            ((after_features or {}).get("selected_capability_id") or "")
        ),
        selected_capability_type=str(
            ((after_features or {}).get("selected_capability_type") or "")
        ),
    )


class TransitionEvaluator:
    PROGRESS_THRESHOLD = 0.08
    REGRESSION_THRESHOLD = -0.10

    def evaluate(
        self,
        *,
        goal: Goal,
        before_world: WorldModel,
        after_world: WorldModel,
        action: Action,
        before_view: Dict[str, Any],
        after_view: Dict[str, Any],
        before_features: Optional[Dict[str, Any]] = None,
        after_features: Optional[Dict[str, Any]] = None,
        transition: Optional[TransitionResult] = None,
        before_world_id: str = "",
        after_world_id: str = "",
        execution: Optional[Dict[str, Any]] = None,
        interaction_context: Optional[InteractionContext] = None,
    ) -> TransitionAttempt:
        status: GoalStatus = evaluate_goal(goal, after_world)
        if status.succeeded:
            assessment = assess_progress(
                goal=goal,
                before_view=before_view,
                after_view=after_view,
                before_features=before_features,
                after_features=after_features,
                transition=transition,
                interaction_context=interaction_context,
                execution=execution,
            )
            attrib = attribute_transition(
                action=action,
                outcome=TransitionOutcome.GOAL_SATISFIED.value,
                transition=transition,
                execution=execution,
                before_view=before_view,
                after_view=after_view,
                before_features=before_features,
                after_features=after_features,
                goal=goal,
            )
            return TransitionAttempt(
                before_world_id=before_world_id,
                after_world_id=after_world_id,
                action_family=action.action_family,
                action_key=f"{action.action_family}:{action.semantic_target}:{action.text}",
                observed_change=True,
                progress_delta=max(assessment.progress_delta, 1.0),
                outcome=TransitionOutcome.GOAL_SATISFIED.value,
                change_score=1.0 if transition is None else transition.change_score,
                reasons=["goal_satisfied"],
                assessment=assessment.to_dict(),
                attribution=attrib.to_dict(),
                effect_kind=attrib.effect_kind,
            )

        assessment = assess_progress(
            goal=goal,
            before_view=before_view,
            after_view=after_view,
            before_features=before_features,
            after_features=after_features,
            transition=transition,
            interaction_context=interaction_context,
            execution=execution,
        )
        changed = bool(transition.changed) if transition else assessment.meaningful_change
        change_score = transition.change_score if transition else abs(assessment.progress_delta)

        outcome = self._classify(
            assessment,
            transition,
            changed,
            change_score,
            action_family=action.action_family,
        )

        attrib = attribute_transition(
            action=action,
            outcome=outcome.value,
            transition=transition,
            execution=execution,
            before_view=before_view,
            after_view=after_view,
            before_features=before_features,
            after_features=after_features,
            goal=goal,
        )

        prediction = _prediction_dict(action)
        prediction_error = _prediction_error(prediction, assessment, outcome, after_view)

        return TransitionAttempt(
            before_world_id=before_world_id,
            after_world_id=after_world_id,
            action_family=action.action_family,
            action_key=f"{action.action_family}:{action.semantic_target}:{action.text}",
            prediction=prediction,
            prediction_error=prediction_error,
            observed_change=changed,
            progress_delta=assessment.progress_delta,
            outcome=outcome.value,
            change_score=change_score,
            reasons=list((transition.reasons if transition else []) + assessment.notes + attrib.notes),
            assessment=assessment.to_dict(),
            attribution=attrib.to_dict(),
            effect_kind=attrib.effect_kind,
        )

    def _classify(
        self,
        assessment: ProgressAssessment,
        transition: Optional[TransitionResult],
        changed: bool,
        change_score: float,
        *,
        action_family: str = "",
    ) -> TransitionOutcome:
        if assessment.contradiction_evidence and assessment.goal_progress == "regression":
            return TransitionOutcome.REGRESSION
        if (
            assessment.contradiction_evidence
            and assessment.irreversible_risk_delta >= 0.5
            and not assessment.newly_relevant_affordances
        ):
            return TransitionOutcome.REGRESSION

        if (
            action_family == "scroll_content"
            and assessment.execution_succeeded
            and assessment.context_preserved
            and not assessment.contradiction_evidence
            and assessment.irreversible_risk_delta < 0.35
        ):
            return TransitionOutcome.PROMISING_UNRESOLVED

        # Message/content selection is often a latent state change in WhatsApp:
        # the correct row can be selected without an obvious repaint.
        if (
            action_family == "select_content"
            and assessment.execution_succeeded
            and assessment.context_preserved
            and not assessment.contradiction_evidence
            and assessment.irreversible_risk_delta < 0.35
        ):
            return TransitionOutcome.PROMISING_UNRESOLVED

        if action_family in {"probe_hover", "probe_context_menu", "probe_focus"}:
            if (
                assessment.execution_succeeded
                and assessment.context_preserved
                and not assessment.contradiction_evidence
                and (
                    assessment.newly_relevant_affordances
                    or assessment.goal_progress == "promising"
                    or assessment.meaningful_change
                )
            ):
                return TransitionOutcome.PROMISING_UNRESOLVED
            if (
                assessment.execution_succeeded
                and changed
                and change_score >= 0.2
                and not assessment.contradiction_evidence
                and assessment.irreversible_risk_delta < 0.35
            ):
                return TransitionOutcome.PROMISING_UNRESOLVED

        if (
            assessment.execution_succeeded
            and assessment.meaningful_change
            and assessment.newly_relevant_affordances
            and assessment.context_preserved
            and not assessment.contradiction_evidence
        ):
            return TransitionOutcome.PROMISING_UNRESOLVED

        if (
            assessment.execution_succeeded
            and changed
            and change_score >= 0.35
            and not assessment.state_understood
            and not assessment.contradiction_evidence
            and assessment.branch_reversible
            and assessment.irreversible_risk_delta < 0.35
        ):
            return TransitionOutcome.PROMISING_UNRESOLVED

        if assessment.goal_progress == "promising" and assessment.meaningful_change:
            return TransitionOutcome.PROMISING_UNRESOLVED

        if assessment.progress_delta >= self.PROGRESS_THRESHOLD or assessment.goal_progress == "clear":
            return TransitionOutcome.PROGRESS
        if assessment.progress_delta > 0.02 and changed and not assessment.contradiction_evidence:
            return TransitionOutcome.PROGRESS

        if (
            (transition is not None and not transition.changed and change_score < 0.08)
            or (
                abs(assessment.progress_delta) < 0.05
                and (transition is None or not transition.changed)
            )
            or (not changed and assessment.goal_progress == "none")
        ):
            return TransitionOutcome.NO_EFFECT

        if assessment.contradiction_evidence and assessment.progress_delta <= self.REGRESSION_THRESHOLD:
            return TransitionOutcome.REGRESSION
        if (
            assessment.progress_delta <= self.REGRESSION_THRESHOLD
            and assessment.irreversible_risk_delta >= 0.35
            and not assessment.newly_relevant_affordances
            and "target_occluded_not_lost" not in assessment.occlusion_notes
        ):
            return TransitionOutcome.REGRESSION

        if not changed:
            return TransitionOutcome.NO_EFFECT
        return TransitionOutcome.UNCERTAIN
