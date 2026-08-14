"""Closed-loop goal controller — brain-owned tools (meta-first dispatcher).

The controller does not choose tools. Each iteration:

1. Build context from the current world (no tool run yet; bootstrap look once).
2. Brain meta decides which tool/capability to run (PERCEIVE / ACT / THINK / …).
3. Dispatch only that tool. Perception, reflection, and actuation never self-schedule.

Surprise and ``must_executive_reperceive`` are *signals into meta*, not forced
pre-meta looks by this module. After any non-observe actor result (ok or fail),
the controller invalidates the pre-act snapshot and owes a brain-scheduled
PERCEIVE before the next ACT — never ``perceive_exhausted_fall_through``
onto pre-act geometry.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)

from plugin.agent.action import Action
from plugin.agent.apps.registry import get_overlay
from plugin.agent.decision import DecisionEngine, get_decision_engine
from plugin.agent.focus_of_action import (
    clean_app_display,
    foreground_app_name,
    foreground_gate_enabled,
    foreground_matches_task,
)
from plugin.agent.executive.hierarchy import DELIBERATIVE as _DELIBERATIVE
from plugin.agent.executive.meta_action import (
    MetaAction,
    MetaChoice,
    reperception_exhausted,
)
from plugin.agent.executive.sync import (
    assess_executive_judgement,
    bind_goal,
    commit_beliefs,
    commit_bindings,
    commit_reading,
    commit_transition,
    contract_status,
    has_resolved_binding,
    open_exploration_question,
    settle_exploration_question,
    workspace_blocking_uncertainties,
    workspace_of,
)
from plugin.agent.goal import Goal, GoalStatus, evaluate_goal
from plugin.agent.policy.events import log_policy_event
from plugin.agent.runtime import inflight
from plugin.agent.runtime.state import RuntimeState
from plugin.agent.trajectory_memory import TrajectoryStepRecord, get_trajectory_memory
from plugin.agent.task_binding import ForwardTaskState
from plugin.agent.perception_cycle import (
    PerceptionSnapshot,
    apply_observation,
    build_view_features,
    ensure_settled_perception,
    refresh_perception,
)
from plugin.agent.transition import (
    EffectKind,
    ExplorationBranch,
    FailureDomain,
    TransitionEvaluator,
    TransitionMonitor,
    TransitionOutcome,
    apply_transition_confirmation,
    confirm_transition_with_llm,
    should_advance_reference_hypothesis,
    update_interaction_context,
    world_fingerprint,
)
from plugin.agent.transition.post_perceive import (
    feature_get,
    settled_empty_search_results,
)
from plugin.agent.transition.types import TransitionSummary
from plugin.worldmodel.entities.normalize import _clean_label
from plugin.agent.whatsapp_view import entities_matching
from plugin.executor.ax_action import STALE_PRECONDITION_BACKEND, bypass_next_gate
from plugin.executor.ghost import ExecResult
from plugin.experiments.logger import EventLogger
from plugin.perception.observation import Observation

# Backward alias
PlanStep = Action

_TRUE_ENV = {"1", "true", "yes", "on"}


def _meta_perception_enabled() -> bool:
    """Whether the brain's meta-action owns tool scheduling (default on).

    When enabled, the controller is a dispatcher: it runs only the tool the
    brain selected (PERCEIVE / ACT / THINK / EXPLORE / SEARCH / ASK / …).
    Set ``HERMES_META_PERCEPTION`` to ``0``/``false``/``no``/``off`` only for
    legacy always-perceive characterization (judgement is still recorded).
    """
    import os

    raw = os.getenv("HERMES_META_PERCEPTION")
    if raw is None or not raw.strip():
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off"}


# Attribution signatures that mean the last action moved the world in a way we
# did NOT predict: it went backwards, landed somewhere unexpected, or a
# transition happened that we could not confirm. These raise a "surprise" the
# executive reacts to (verify / re-perceive to re-understand before re-acting).
_SURPRISE_EFFECTS = {
    "regression",
    "unexpected_transition",
    "transition_not_perceived",
}
_SURPRISE_OUTCOMES = {
    TransitionOutcome.REGRESSION.value,
    TransitionOutcome.UNCERTAIN.value,
}

# "Nothing moved" signatures. On their own these are the stale case; paired with
# a prediction that the world *would* move they are the sharpest surprise we get.
_NO_MOVEMENT_EFFECTS = {EffectKind.NO_TRANSITION.value}
_NO_MOVEMENT_OUTCOMES = {TransitionOutcome.NO_EFFECT.value}


def _predicted_a_transition(execution_state: Any) -> bool:
    """Did the last action carry a concrete prediction that the world would move?"""
    expectation = getattr(execution_state, "unified_last_expectation", None)
    if isinstance(expectation, dict) and str(expectation.get("surface") or "").strip():
        return True
    last_transition = getattr(execution_state, "last_transition", None)
    if not isinstance(last_transition, dict):
        return False
    # A recorded prediction error is already the expected-vs-observed mismatch.
    error = last_transition.get("prediction_error")
    if isinstance(error, dict) and error:
        return True
    prediction = last_transition.get("prediction")
    if isinstance(prediction, dict):
        for key in ("predicted_outcome", "expected_surface"):
            if str(prediction.get(key) or "").strip():
                return True
    return False


def _expected_transition_absent(execution_state: Any) -> bool:
    """The predicted transition simply did not happen — a silent no-op.

    A no-op is only informative when we predicted the world would move. Then its
    absence *is* the evidence: our picture of what that control does is wrong,
    and only a fresh look carrying the failed attempt can say why. This is the
    dominant failure on an AX-blind app, where a press reports success and
    nothing opens — previously invisible to the executive, so the agent re-tried
    the same dead click forever. A no-op with nothing predicted stays
    un-surprising (the stale case, which backtrack handles), so we never
    re-perceive an identical world for no reason.
    """
    attrib = getattr(execution_state, "last_attribution", None)
    if not isinstance(attrib, dict) or not attrib:
        return False
    effect = str(attrib.get("effect_kind") or "").strip().lower()
    outcome = str(attrib.get("outcome") or "").strip().lower()
    # The effect is the precise reading and wins when present: an action that
    # never reached the app (missing geometry, a failed actuator) also reports
    # no_effect, but it says nothing about the world and must not be read as one.
    if effect:
        if effect not in _NO_MOVEMENT_EFFECTS:
            return False
    elif outcome not in _NO_MOVEMENT_OUTCOMES:
        return False
    return _predicted_a_transition(execution_state)


# Effects that mean the screen genuinely changed (forwards or backwards). Any of
# them makes another look worthwhile again.
_WORLD_MOVED_EFFECTS = {
    EffectKind.GOAL_SATISFIED.value,
    EffectKind.PROGRESS.value,
    EffectKind.PROMISING_UNRESOLVED.value,
    EffectKind.REGRESSION.value,
    "unexpected_transition",
}


def _world_moved(attribution: Any, attempt: Any = None) -> bool:
    """Did the last action actually change the world?"""
    if isinstance(attribution, dict) and attribution:
        if str(attribution.get("effect_kind") or "").strip().lower() in _WORLD_MOVED_EFFECTS:
            return True
    if attempt is not None:
        if bool(getattr(attempt, "observed_change", False)):
            return True
        try:
            if float(getattr(attempt, "change_score", 0.0) or 0.0) > 0.0:
                return True
        except (TypeError, ValueError):
            pass
    return False


def _prediction_was_contradicted(execution_state: Any) -> bool:
    """The agent's own prediction was scored against the screen and failed.

    The most direct form of surprise there is, and the only one stated in the
    agent's own terms rather than inferred from how much the world moved. The
    effect-based signals below are proxies: they catch a world that went
    backwards or did not move, but a move that lands somewhere plausible and
    entirely wrong reads as ordinary progress to them, while the prediction says
    plainly that it was not what was expected.

    Meta thrash prevention (``suppressed_rearm`` / ``surprise_armed=False``)
    must not re-arm surprise meta on the same predicted surface — but must leave
    ``matched`` truthful so motor escalate can still see effect-absent
    (live 154356). This predicate is for *meta surprise*, not mechanism.
    """
    error = getattr(execution_state, "last_prediction_error", None)
    if not isinstance(error, dict) or not error:
        return False
    if error.get("matched") is not False:
        return False
    # Surprise already consumed: do not re-arm meta surprise.
    if error.get("suppressed_rearm") or error.get("surprise_armed") is False:
        return False
    if error.get("consumed_by_reflect") and error.get("surprise_armed") is not True:
        return False
    return True


def _effect_was_absent(execution_state: Any) -> bool:
    """Judgment: predicted effect did not appear (independent of meta latch)."""
    error = getattr(execution_state, "last_prediction_error", None)
    if not isinstance(error, dict) or not error:
        return False
    if error.get("matched") is False:
        return True
    # Explicit effect_absent bit when matched was historically coerced.
    if error.get("effect_absent") is True:
        return True
    return False


def _attribution_belief_authority(attrib: Dict[str, Any]) -> str:
    """Who is allowed to steer the executive from this attribution?

    ``motor`` — actuator reported failure (thin feedback the executive owns).
    ``multimodal`` — stage1 prediction scored against a later reading.
    ``ax_settle_diagnostic`` — post-act AX/view TransitionEvaluator (logging only;
    never a rival chooser).
    """
    auth = str(attrib.get("belief_authority") or "").strip().lower()
    if auth:
        return auth
    evidence = attrib.get("evidence") if isinstance(attrib.get("evidence"), dict) else {}
    if evidence.get("executor_ok") is False:
        return "motor"
    return "ax_settle_diagnostic"


def _last_action_surprised(execution_state: Any) -> bool:
    """Executive surprise: motor fail or multimodal prediction contradicted.

    AX settle / TransitionEvaluator regression is diagnostic only — it must not
    force a look or block the one-executive loop. After an act the executive
    re-perceives (stage1) and chooses from that accepted world.
    """
    if _prediction_was_contradicted(execution_state):
        return True
    attrib = getattr(execution_state, "last_attribution", None)
    if not isinstance(attrib, dict) or not attrib:
        return False
    if _attribution_belief_authority(attrib) != "motor":
        return False
    effect = str(attrib.get("effect_kind") or "").strip().lower()
    outcome = str(attrib.get("outcome") or "").strip().lower()
    if effect in _SURPRISE_EFFECTS or outcome in _SURPRISE_OUTCOMES:
        return True
    if effect in _NO_MOVEMENT_EFFECTS or outcome in _NO_MOVEMENT_OUTCOMES:
        return True
    return False


def _post_action_look_unpaid(execution_state: Any) -> bool:
    """True until the executive finishes re-perceive after the last motor write.

    Cycle: act → result → re-perceive → decide. While this is set, the next
    capability must not run — the executive still owes the look that feeds that
    decide. Distinct from surprise-relook signals in ``_awaiting_verification``.
    """
    return bool(getattr(execution_state, "must_executive_reperceive", False)) or bool(
        getattr(execution_state, "post_action_reperceive_pending", False)
    )


def _awaiting_verification(execution_state: Any) -> bool:
    """True when the executive owes a look before the next act.

    Includes unpaid post-act re-perceive and motor surprise after a non-observe
    act. Meta uses this to schedule PERCEIVE; actuation gating for the
    act→reperceive→decide cycle uses ``_post_action_look_unpaid`` only.
    """
    if _post_action_look_unpaid(execution_state):
        return True
    last_action = str(getattr(execution_state, "last_action", "") or "").strip().lower()
    if not last_action or last_action == "observe":
        return False
    return _last_action_surprised(execution_state)


def _note_post_action_reperceive(runtime: Any, *, open_conversation: str = "", state_sig: str = "") -> None:
    """After actor returns (ok or fail): executive must re-perceive before deciding again.

    Clears carry-over that would let the next ACT bind pre-act geometry, and
    resets the consecutive-perceive streak so an owed look cannot
    ``perceive_exhausted_fall_through`` into actuation on a stale world.

    Also resets ``consecutive_surprise_relooks``: the surprise relook cap is per
    unmoving world, not per run. A fresh motor act earns a new look budget so
    the executive can schedule the post-act re-perceive (live 024346).
    """
    state = runtime.execution_state
    state.must_executive_reperceive = True
    state.post_action_reperceive_pending = True
    if open_conversation:
        state.post_action_baseline_open = str(open_conversation)
    elif not str(getattr(state, "post_action_baseline_open", "") or "").strip():
        doc = getattr(state, "unified_world_document", None) or {}
        state.post_action_baseline_open = str(
            (doc.get("open_conversation") if isinstance(doc, dict) else "") or ""
        )
    if state_sig:
        state.post_action_baseline_sig = str(state_sig)
    try:
        state.consecutive_perceives = 0
    except Exception:
        pass
    try:
        # New act → new look budget (see docstring).
        state.consecutive_surprise_relooks = 0
    except Exception:
        pass
    try:
        state.unified_perception_cache = None
    except Exception:
        pass


def _grounding_repair_satisfied(state: Any) -> bool:
    """True when the named reground target has fresh executable grounding.

    Same semantic target + current capture/frame + Actor-grade executable
    geometry + active surface. Delegates to grounding_validity so Controller
    cannot clear repair under a looser definition than Actor.
    """
    from plugin.agent.grounding_validity import grounding_repair_satisfied

    return bool(grounding_repair_satisfied(state))


def _clear_post_action_reperceive_if_fresh(
    runtime: Any,
    *,
    multimodal_ok: bool,
    proposal_model: str = "",
    open_conversation: str = "",
    state_sig: str = "",
) -> bool:
    """Mark the executive's post-act re-perceive as complete.

    Contract: act → result → re-perceive → decide. Idle ``phash_reuse`` is not a
    re-perceive. ``no_visible_change`` (post-act pixel delta) *is* — the look
    returned "unchanged," and the executive decides from that result.
    Open/sig need not change (ComposeSearchQuery keeps search chrome open).
    """
    _ = (open_conversation, state_sig)  # call-site/logging compatibility
    if not multimodal_ok:
        return False
    model = str(proposal_model or "").strip().lower()
    if model == "phash_reuse":
        return False
    state = runtime.execution_state
    if not _post_action_look_unpaid(state):
        return True
    try:
        state.must_executive_reperceive = False
        state.post_action_reperceive_pending = False
        state.post_action_baseline_open = ""
        state.post_action_baseline_sig = ""
        # Clear grounding repair only when the named target has fresh executable
        # grounding — not merely because any PERCEIVE ran.
        if bool(getattr(state, "grounding_reground_only", False)):
            if _grounding_repair_satisfied(state):
                try:
                    from plugin.agent.executive.affordance_commitment import (
                        clear_grounding_recovery,
                    )

                    clear_grounding_recovery(state)
                except Exception:
                    state.grounding_reground_only = False
                    state.grounding_reground_target = ""
                    state.grounding_reground_commitment_id = ""
            else:
                # Target disappeared / still ungrounded → escalate reveal/route
                # for the committed patient (latent restore), not a silent drop.
                try:
                    from plugin.agent.executive.affordance_commitment import (
                        active_commitment,
                        arm_grounding_recovery,
                        derive_availability,
                        AVAIL_LATENT,
                    )

                    c = active_commitment(state)
                    if c is not None and derive_availability(state, c) == AVAIL_LATENT:
                        arm_grounding_recovery(
                            state, c, reason="still_ungrounded_after_perceive"
                        )
                    else:
                        state.grounding_reground_only = False
                        state.grounding_reground_target = ""
                        state.grounding_reground_commitment_id = ""
                        state.world_exploration_needed = True
                        if not str(
                            getattr(state, "reveal_prefer_capability", "") or ""
                        ).strip():
                            state.reveal_prefer_capability = "reveal_actions"
                except Exception:
                    state.grounding_reground_only = False
                    state.grounding_reground_target = ""
                    state.world_exploration_needed = True
                    if not str(getattr(state, "reveal_prefer_capability", "") or "").strip():
                        state.reveal_prefer_capability = "reveal_actions"
                try:
                    closure = dict(getattr(state, "last_effect_closure", None) or {})
                    closure["grounding_repair"] = "target_disappeared_or_ungrounded"
                    closure["recovery"] = str(
                        closure.get("recovery") or "explore_reveal"
                    )
                    state.last_effect_closure = closure
                except Exception:
                    pass
    except Exception:
        return False
    return True


def _resolve_exhausted_backtrack(
    meta: "MetaChoice",
    *,
    backtrack_exhausted: bool,
    has_grounded_action: bool,
) -> "MetaChoice":
    """Compatibility helper: exhaustion is decided inside ``decision_ladder``.

    Prefer passing ``backtrack_exhausted`` into :func:`assess_executive_judgement`
    / ``MetaContext``. This wrapper re-runs the ladder so tests keep one API.
    """
    if not backtrack_exhausted or meta.action not in {
        MetaAction.EXPLORE,
        MetaAction.THINK,
    }:
        return meta
    from plugin.agent.executive.hierarchy import decision_ladder
    from plugin.agent.executive.meta_action import MetaContext

    return decision_ladder(
        MetaContext(
            branch_stale=True,
            backtrack_exhausted=True,
            has_grounded_action=has_grounded_action,
        )
    )


def _resolve_exhausted_information_gathering(
    meta: "MetaChoice",
    *,
    gathering_exhausted: bool,
    has_grounded_action: bool,
) -> "MetaChoice":
    """Compatibility helper: exhaustion is decided inside ``decision_ladder``."""
    if not gathering_exhausted or meta.action != MetaAction.THINK:
        return meta
    from plugin.agent.executive.hierarchy import decision_ladder
    from plugin.agent.executive.meta_action import MetaContext

    return decision_ladder(
        MetaContext(
            branch_stale=True,
            information_gathering_exhausted=True,
            has_grounded_action=has_grounded_action,
        )
    )


def _consume_surprise(execution_state: Any) -> None:
    """Mark the last surprise as handled so PERCEIVE fires once.

    The look acknowledges the prediction error. If surprise stayed on the
    prediction error. If surprise stayed on the attribution / prediction error,
    the executive would reflect the same one every frame (live zarooratwala
    123727: 68× brain_tool:reflect after one click). Stamping it consumed lets
    the next frame act on the re-understood world. The surprise still lives in
    ``recent_surprises``, so perception keeps the pattern.

    Important (154356): do **not** falsify ``matched``. Meta thrash prevention
    is ``surprise_armed=False`` / ``consumed_by_reflect``; effect judgment stays
    honest so motor escalate can still run.
    """
    attrib = getattr(execution_state, "last_attribution", None)
    if isinstance(attrib, dict):
        updated = dict(attrib)
        updated["outcome"] = "verified"
        updated["effect_kind"] = "verified"
        execution_state.last_attribution = updated
    err = getattr(execution_state, "last_prediction_error", None)
    if isinstance(err, dict) and err:
        cleared = dict(err)
        # Keep structural judgment. Only disarm meta re-arm.
        if cleared.get("matched") is False:
            cleared["effect_absent"] = True
        cleared["consumed_by_reflect"] = True
        cleared["surprise_armed"] = False
        cleared["suppressed_rearm"] = True
        execution_state.last_prediction_error = cleared


def _observe_capability_reliability(decision: Any, ok: bool) -> None:
    """Feed the executed action's outcome back into the capability registry.

    The registry seeds each verb's reliability with a conservative prior and
    ranks its shortlist by a value score built from that reliability. Nothing
    was updating the prior, so the ordering could never learn which capabilities
    actually work here. Nudging the executed verb's reliability toward the
    observed outcome (an EMA inside the registry) closes that loop: a verb that
    keeps failing on this surface drifts down the shortlist, a reliable one
    drifts up. Best-effort and side-effect free beyond the in-memory prior.
    """
    family = str(getattr(decision, "action_family", "") or "").strip().lower()
    if not family:
        return
    try:
        from plugin.agent.executive.capabilities import default_registry

        registry = default_registry()
        if registry.get(family) is not None:
            registry.observe_reliability(family, bool(ok))
    except Exception:
        pass


def _clear_search_retreat_state(execution_state: Any, *, why: str = "") -> None:
    """Clear failed-search retreat debt so a fresh SEARCH may arm."""
    try:
        from plugin.agent.capabilities.search_episode import (
            clear_search_episode,
            clear_search_retreat,
        )

        clear_search_retreat(execution_state)
        if str(
            (getattr(execution_state, "search_episode", None) or {}).get("status") or ""
        ) == "failed":
            clear_search_episode(execution_state, why=why or "retreat_cleared")
    except Exception:
        execution_state.search_retreat_owed = False


def _run_think_replan(
    runtime: RuntimeState,
    goal: Goal,
    *,
    observe: Any,
    feats: Any,
    overlay: Any,
    log: Any,
    iteration: int,
) -> str:
    """Replan branches after failed search or stale exploration (ex-IG path)."""
    if not reperception_exhausted(runtime.execution_state):
        snap_pre = refresh_perception(
            runtime,
            goal,
            observe=observe,
            action_label="meta_think_replan",
            log_fn=_perception_log_fn(log, iteration),
            iteration=iteration,
        )
        try:
            replan_feats = overlay.features(
                runtime.world_model, goal, worldview_score=snap_pre.worldview
            )
        except Exception:
            replan_feats = feats
        _multimodal_look(runtime, goal, features=replan_feats, mode="perceive")
    plan = _plan_next_branches(runtime, goal, feats)
    runtime.execution_state.consecutive_information_gathering = (
        int(getattr(runtime.execution_state, "consecutive_information_gathering", 0) or 0)
        + 1
    )
    branch_hint = _invalidate_stale_frontier(
        runtime,
        reason="strategic_search",
        fallback=plan.head or "observe",
    )
    if plan.head:
        runtime.execution_state.state_experience.pending_backtrack_family = plan.head
        branch_hint = plan.head
    _note_no_progress_replan(runtime)
    return branch_hint


def _run_explore_revert(
    runtime: RuntimeState,
    goal: Goal,
) -> Any:
    """Undo wrong branch effects before explore/search broadens (ex-backtrack path)."""
    _clear_search_retreat_state(
        runtime.execution_state, why="explore_after_failed_search"
    )
    runtime.execution_state.consecutive_backtracks = (
        int(getattr(runtime.execution_state, "consecutive_backtracks", 0) or 0) + 1
    )
    revert_outcome = None
    try:
        from plugin.agent.capabilities.base import CapabilityRequest
        from plugin.agent.capabilities.dispatch import dispatch

        revert_outcome = dispatch(
            CapabilityRequest(
                name="revert_effects",
                app=str(goal.app or "WhatsApp"),
                extras={
                    "execution_state": runtime.execution_state,
                    "goal": goal,
                    "world_document": getattr(
                        runtime.execution_state, "unified_world_document", None
                    ),
                    "user_intent": "explore_retreat",
                    "approve": True,
                },
            ),
            get_overlay(goal.app, runtime.world_model),
        )
    except Exception as exc:
        revert_outcome = type(
            "R",
            (),
            {"ok": False, "message": str(exc), "evidence": {}},
        )()
    branch_hint = _invalidate_stale_frontier(
        runtime, reason="executive_explore_retreat", fallback="observe"
    )
    _note_no_progress_replan(runtime)
    try:
        runtime.execution_state.must_executive_reperceive = True
        runtime.execution_state.post_action_reperceive_pending = True
    except Exception:
        pass
    return revert_outcome, branch_hint


# Meta-actions that unconditionally pre-empt this frame's grounded decision.
# ASK and DELEGATE escalate; WAIT is a short settle that continues.
# THINK / EXPLORE / PERCEIVE / SEARCH / ACT fall through (bounded detours).
_META_PREEMPTS = {
    MetaAction.ASK,
    MetaAction.DELEGATE,
}

# Streak caps — single source in meta_action; loop only increments counters.
from plugin.agent.executive.meta_action import (
    BACKTRACK_STREAK_CAP as _MAX_CONSECUTIVE_BACKTRACKS,
    INFORMATION_GATHERING_STREAK_CAP as _MAX_CONSECUTIVE_INFORMATION_GATHERING,
    PERCEIVE_STREAK_CAP as _MAX_CONSECUTIVE_PERCEIVES,
    PROBE_STREAK_CAP as _MAX_CONSECUTIVE_PROBES,
    SEARCH_STREAK_CAP as _MAX_CONSECUTIVE_SEARCHES,
    THINK_STREAK_CAP as _MAX_CONSECUTIVE_THINKS,
)

# The domain derives a fine-grained phase (OPEN_SOURCE, FIND_LINK, ...). The
# workspace records progress against the abstract phase ladder so regression
# protection is domain-neutral. This maps the forward machine's phases onto that
# ladder; the controller never lets a raw domain phase name reach the workspace.
_FORWARD_PHASE_TO_LADDER = {
    "preclear": "reach_source",
    "open_source": "reach_source",
    "find_link": "hunt_content",
    "open_forward": "invoke_forward",
    "pick_dest": "choose_destination",
    "done": "committed",
}


def _ladder_phase(goal_kind: str, derived_phase: str) -> str:
    """Map a domain's derived phase onto the workspace's abstract ladder."""
    dp = str(derived_phase or "").strip().lower()
    if not dp:
        return ""
    if str(goal_kind or "").strip().lower() == "whatsapp_forward_message":
        return _FORWARD_PHASE_TO_LADDER.get(dp, "")
    return ""


def _feats_extras(feats: Any) -> Dict[str, Any]:
    """Read an ``extras`` mapping from either a StateFeatures or a feature dict."""
    if isinstance(feats, dict):
        extras = feats.get("extras")
        return extras if isinstance(extras, dict) else {}
    extras = getattr(feats, "extras", None)
    return extras if isinstance(extras, dict) else {}


def _reading_surface(extras: Dict[str, Any], open_conversation: str) -> str:
    """Distil one surface label the workspace's wipe protection understands.

    The workspace only needs a coarse surface (conversation / context_menu /
    selection_mode / forward_picker / chat_list / search) to know whether an
    empty open-conversation reading is trustworthy. Derived from generic
    frontier signals, not from a WhatsApp-only field.
    """
    if not isinstance(extras, dict):
        extras = {}
    if extras.get("destination_picker_visible"):
        return "forward_picker"
    # Selection chrome ("N Selected" + toolbar) is not a context menu.
    if (
        extras.get("selection_chrome")
        or extras.get("selection_count") is not None
        or str(extras.get("active_surface") or "").strip().lower() == "selection_mode"
    ):
        return "selection_mode"
    if extras.get("forward_surface_open") or extras.get("action_menu_visible"):
        return "context_menu"
    if open_conversation or extras.get("source_conversation_visible") or extras.get("latent_conversation_open"):
        return "conversation"
    if extras.get("result_surface_visible") or extras.get("search_result_rows"):
        return "search"
    return "chat_list"


def _commit_frame_beliefs(
    runtime: RuntimeState,
    goal: Goal,
    feats: Any,
    *,
    coverage: float,
) -> None:
    """Record this frame's reading into the workspace — the one authoritative record.

    The controller already computes perception and features every iteration; this
    folds that same reading into the workspace (open conversation, phase, object
    bindings) so the executive reads task state from one place instead of from
    whichever store happened to be updated. It only proposes — the workspace
    critic decides what to accept, refusing e.g. a wipe of the open conversation
    seen from under an overlay.
    """
    extras = getattr(feats, "extras", None) or {}
    open_conversation = str(extras.get("open_conversation") or "").strip()
    derived_phase = str(
        extras.get("forward_phase")
        or (extras.get("forward_task") or {}).get("derived_phase")
        or ""
    )
    surface = _reading_surface(extras, open_conversation)
    commit_reading(
        runtime.execution_state,
        source="perception",
        surface=surface,
        # Only offer a value when we have one: an empty string here would be a
        # proposal to close, which the critic weighs against the surface.
        open_conversation=open_conversation or None,
        phase=_ladder_phase(goal.kind, derived_phase) or None,
        confidence=coverage,
        evidence=f"frame reading on {surface}",
    )
    bindings = (extras.get("forward_task") or {}).get("bindings")
    if isinstance(bindings, dict) and bindings:
        commit_bindings(
            runtime.execution_state,
            bindings=bindings,
            source="task_binding",
            evidence=f"derived on {surface}",
        )

    # Route the perceptor's own belief patch into the workspace. The unified
    # proposal (persisted this frame on the execution state) carries the model's
    # read of the scene as predicate/value beliefs plus the surface it saw.
    # Committing them here is what makes the workspace — not features.extras —
    # the single authoritative record: the critic arbitrates each against any
    # established belief, records contradictions, and counts belief flips.
    frame = int(getattr(runtime.execution_state, "decision_frame", -2) or -2)
    uni = getattr(runtime.execution_state, "last_unified_proposal", None)
    if isinstance(uni, dict) and int(uni.get("frame", -999)) == frame:
        perceived_facts: Dict[str, Any] = {}
        surf = str(uni.get("surface") or "").strip().lower()
        if surf:
            perceived_facts["surface"] = surf
        for belief in uni.get("beliefs") or []:
            predicate = str(belief.get("predicate") or "").strip()
            raw_value = belief.get("value")
            if not predicate or raw_value is None:
                continue
            if isinstance(raw_value, bool):
                # A bool predicate is still a belief when false; encode it so the
                # workspace does not treat "false" as an empty (dropped) reading.
                value_str = "true" if raw_value else "false"
            else:
                value_str = str(raw_value).strip()
            if not value_str:
                continue
            conf = belief.get("confidence")
            perceived_facts[predicate] = (
                (value_str, float(conf)) if conf is not None else value_str
            )
        if perceived_facts:
            commit_beliefs(
                runtime.execution_state,
                source="perception",
                facts=perceived_facts,
                confidence=coverage,
                evidence="unified perception belief patch",
                status="observed",
            )


@dataclass
class GoalResult:
    ok: bool
    reason: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    iterations: int = 0
    planner_invocations: int = 0

    @classmethod
    def success(cls, evidence: Optional[Dict[str, Any]] = None, **kwargs: Any) -> "GoalResult":
        return cls(ok=True, reason="goal succeeded", evidence=evidence or {}, **kwargs)

    @classmethod
    def failure(cls, reason: str, evidence: Optional[Dict[str, Any]] = None, **kwargs: Any) -> "GoalResult":
        return cls(ok=False, reason=reason, evidence=evidence or {}, **kwargs)


class ActionExecutor(Protocol):
    def execute(self, step: Action) -> ExecResult: ...


ObserveFn = Callable[[], Observation]
WaitFn = Callable[[float, str], None]

WORLDVIEW_LOW = 0.55
_DEFAULT_GOAL_RUN_TIMEOUT_SECONDS = 900.0


def resolve_step_budget(
    *,
    max_iterations: int,
    max_stepcount: Optional[int] = None,
    config: Optional[Dict[str, Any]] = None,
) -> int:
    """Resolve the effective closed-loop step budget.

    ``max_iterations`` remains the hard outer ceiling. ``max_stepcount`` is a
    soft hint from leaf runners / configs, not a semantic truth about the
    agent. We still clamp it to the caller ceiling so safety bounds remain
    intact, but the runtime should treat it as a tunable budget, not a design
    primitive.
    """
    ceiling = max(1, int(max_iterations or 1))
    candidate: Optional[int]

    if max_stepcount is not None:
        candidate = max_stepcount
    else:
        candidate = None
        cfg = config if isinstance(config, dict) else {}
        agent_cfg = cfg.get("agent") or {}
        if isinstance(agent_cfg, dict):
            raw = agent_cfg.get("max_stepcount")
            if raw is not None:
                try:
                    candidate = int(raw)
                except (TypeError, ValueError):
                    candidate = None

    if candidate is None or candidate <= 0:
        return ceiling
    return max(1, min(ceiling, int(candidate)))


def resolve_goal_run_timeout_seconds(
    *,
    goal_kind: str = "",
    config: Optional[Dict[str, Any]] = None,
) -> float:
    """Resolve the soft wall-clock timeout for a full goal run.

    The controller should not wait indefinitely just because the loop is
    still active. This budget caps the *real elapsed time* spent on one goal
    trajectory, while still allowing the per-step and per-provider budgets to
    handle smaller waits.
    """
    cfg = config if isinstance(config, dict) else {}
    agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
    raw = None
    # Env first, so a supervised experiment can widen the budget for one run
    # without editing the machine's global config. A convergence test needs to be
    # allowed to finish: a run cut off mid-task tells you the budget was small,
    # not whether the agent would have got there.
    env_raw = os.getenv("HERMES_GOAL_RUN_TIMEOUT_SECONDS", "").strip()
    if env_raw:
        try:
            raw = float(env_raw)
        except (TypeError, ValueError):
            raw = None
    if raw is None and isinstance(agent_cfg, dict):
        raw = agent_cfg.get("goal_run_timeout_seconds")
    if raw is None:
        try:
            from hermes_cli.config import load_config_readonly

            loaded = load_config_readonly() or {}
            agent_cfg = loaded.get("agent") if isinstance(loaded.get("agent"), dict) else {}
            if isinstance(agent_cfg, dict):
                raw = agent_cfg.get("goal_run_timeout_seconds")
        except Exception:
            raw = None
    if raw is None:
        raw = _DEFAULT_GOAL_RUN_TIMEOUT_SECONDS
        if str(goal_kind or "").strip().lower() in {
            "whatsapp_forward_message",
            "whatsapp_voice_call",
            "whatsapp_read_message",
        }:
            raw = 600.0
    try:
        timeout = float(raw)
    except (TypeError, ValueError):
        timeout = _DEFAULT_GOAL_RUN_TIMEOUT_SECONDS
    if timeout <= 0:
        return float("inf")
    return max(5.0, timeout)


def resolve_goal_no_progress_timeout_seconds(
    *,
    goal_kind: str = "",
    config: Optional[Dict[str, Any]] = None,
) -> float:
    """Resolve the soft no-progress watchdog for a full goal run.

    This budget is about *meaningful advancement*, not idle time. The loop can
    keep going, but the logs should make it obvious when the run has been
    alive without progress long enough to justify backtracking pressure.
    """
    cfg = config if isinstance(config, dict) else {}
    agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
    raw = None
    if isinstance(agent_cfg, dict):
        raw = agent_cfg.get("goal_no_progress_timeout_seconds")
    if raw is None:
        try:
            from hermes_cli.config import load_config_readonly

            loaded = load_config_readonly() or {}
            agent_cfg = loaded.get("agent") if isinstance(loaded.get("agent"), dict) else {}
            if isinstance(agent_cfg, dict):
                raw = agent_cfg.get("goal_no_progress_timeout_seconds")
        except Exception:
            raw = None
    if raw is None:
        raw = 45.0
        if str(goal_kind or "").strip().lower() in {
            "whatsapp_forward_message",
            "whatsapp_voice_call",
            "whatsapp_read_message",
        }:
            raw = 30.0
    try:
        timeout = float(raw)
    except (TypeError, ValueError):
        timeout = 45.0
    if timeout <= 0:
        return float("inf")
    return max(5.0, timeout)


def parse_typed_query_evidence(message: str, expected: str = "") -> str:
    msg = message or ""
    m = re.search(r"AXValue=['\"]([^'\"]+)['\"]", msg)
    if m:
        return m.group(1).strip()
    m = re.search(
        r"title=['\"]([^'\"]+)['\"]\s+desc=['\"]Search(?: or start[^'\"]*)?['\"]",
        msg,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    m = re.search(r"typed\s+['\"]([^'\"]+)['\"]", msg, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    exp = (expected or "").strip()
    if exp and exp.lower() in msg.lower():
        return exp
    return ""


def _worldview(runtime: RuntimeState) -> float:
    from plugin.agent.perception_cycle import _worldview as _wv

    return _wv(runtime)


def _view_dict(runtime: RuntimeState, goal: Goal) -> Dict[str, Any]:
    view, _, _ = build_view_features(runtime, goal)
    return view


def _feature_dict(runtime: RuntimeState, goal: Goal, worldview_score: float = 1.0) -> Dict[str, Any]:
    _, feats, _ = build_view_features(runtime, goal, worldview=worldview_score)
    return feats


def _log_cycle(
    log: Optional[EventLogger],
    *,
    iteration: int,
    phase: str,
    payload: Dict[str, Any],
    status: str = "ok",
) -> None:
    if log is None:
        return
    log.log(phase, payload, status=status, step=iteration)


# A call is worth naming once it has blocked longer than a perception call
# normally takes, and worth repeating on this cadence for as long as it hangs.
_STALL_AFTER_S = 45.0
_STALL_REPEAT_S = 30.0
_STALL_POLL_S = 5.0


def _start_stall_watchdog(
    log: Optional[EventLogger],
    iteration_ref: Dict[str, int],
) -> tuple[threading.Event, Optional[threading.Thread]]:
    """Report the call the loop is blocked inside, while it is still blocked.

    ``iteration_cost`` can only be written once an iteration ends, so a call
    that hangs produces silence for exactly as long as it is the problem. This
    watchdog runs beside the loop and names the in-flight call on a fixed
    cadence, so a stalled run says what it is waiting on in real time.
    """
    stop = threading.Event()
    if log is None:
        return stop, None

    def _watch() -> None:
        reported_at = 0.0
        while not stop.wait(_STALL_POLL_S):
            active = inflight.current()
            if active is None:
                reported_at = 0.0
                continue
            label, waiting_s = active
            if waiting_s < _STALL_AFTER_S:
                continue
            if reported_at and waiting_s - reported_at < _STALL_REPEAT_S:
                continue
            reported_at = waiting_s
            _log_cycle(
                log,
                iteration=int(iteration_ref.get("iteration") or 0),
                phase="stalled",
                payload={
                    "in_flight": label,
                    "waiting_s": round(waiting_s, 1),
                    "message": f"still waiting on {label} after {waiting_s:.0f}s",
                },
                status="warn",
            )

    thread = threading.Thread(target=_watch, name="hermes-stall-watchdog", daemon=True)
    thread.start()
    return stop, thread


def _perception_log_fn(log: Optional[EventLogger], iteration: int):
    def _fn(*, phase: str, payload: Dict[str, Any], status: str = "ok", iteration: int = 0) -> None:
        _log_cycle(log, iteration=iteration, phase=phase, payload=payload, status=status)

    return _fn


def _maybe_richer_reobserve_after_transition(
    runtime: RuntimeState,
    goal: Goal,
    *,
    observe: ObserveFn,
    decision: Action,
    attempt: Any,
    after_view: Dict[str, Any],
    after_features: Dict[str, Any],
    post_wv: float,
    log: Optional[EventLogger],
    iteration: int,
) -> tuple[Dict[str, Any], Dict[str, Any], float, bool]:
    """Use the richer screenshot/OCR path after failed non-observe transitions."""
    if decision.action_family == "observe":
        return after_view, after_features, post_wv, False
    if attempt.outcome not in {
        TransitionOutcome.NO_EFFECT.value,
        TransitionOutcome.REGRESSION.value,
        TransitionOutcome.UNCERTAIN.value,
    }:
        return after_view, after_features, post_wv, False

    try:
        snap = refresh_perception(
            runtime,
            goal,
            observe=observe,
            action_label=f"post_transition_richer_{decision.action_family or 'default'}",
            target_entity_id=runtime.execution_state.last_target_id,
        )
        if log is not None:
            _log_cycle(
                log,
                iteration=iteration,
                phase="post_transition_richer_reobserve",
                payload={
                    "action_family": decision.action_family,
                    "outcome": attempt.outcome,
                    "screenshot": bool(snap.observation and snap.observation.screenshot_path),
                    "view": {
                        "screen": snap.view.get("screen"),
                        "open_conversation": snap.view.get("open_conversation"),
                        "search_query": snap.view.get("search_query"),
                        "forward_phase": snap.features.get("extras", {}).get("forward_phase"),
                    },
                },
                status="ok",
            )
        return snap.view, snap.features, snap.worldview, True
    except Exception as exc:
        from agent.auxiliary_client import LLMProviderExhaustedError

        if isinstance(exc, LLMProviderExhaustedError):
            raise
        _log_cycle(
            log,
            iteration=iteration,
            phase="post_transition_richer_reobserve",
            payload={"action_family": decision.action_family, "outcome": attempt.outcome, "error": str(exc)},
            status="fail",
        )
        return after_view, after_features, post_wv, False


def _maybe_learn_success(runtime: RuntimeState, goal: Goal, goal_status: GoalStatus) -> None:
    try:
        from plugin.agent.resolver import get_resolution_memory

        resolved = (
            str((goal_status.evidence or {}).get("open_conversation") or "").strip()
            or str(getattr(runtime.execution_state, "last_resolved_contact", "") or "").strip()
            or (goal.contact or "")
        )
        if goal.contact and resolved:
            get_resolution_memory().record(
                goal.contact,
                resolved,
                succeeded=True,
                source="goal_success",
            )
    except Exception:
        pass


def _post_view_mentions_contact(post_view: Dict[str, Any], goal: Goal) -> bool:
    contact = (goal.contact or "").strip().lower()
    if not contact:
        return False
    blobs: List[str] = []
    for key in ("open_conversation", "search_query", "window_name", "screen"):
        val = str(post_view.get(key) or "").strip()
        if val:
            blobs.append(val)
    visible = post_view.get("visible_contacts") or []
    if isinstance(visible, list):
        blobs.extend(str(v) for v in visible if str(v).strip())
    messages = post_view.get("conversation_messages") or []
    if isinstance(messages, list):
        for msg in messages[:8]:
            if isinstance(msg, dict):
                blobs.append(str(msg.get("text") or msg.get("label") or msg.get("description") or ""))
            else:
                blobs.append(str(msg))
    return any(contact in blob.lower() for blob in blobs if blob)


def _raw_observation_mentions_ringing(obs: Optional[Observation]) -> bool:
    if obs is None:
        return False
    blobs: list[str] = []
    for node in obs.nodes or []:
        text = " ".join(
            str(part or "").strip()
            for part in (
                getattr(node, "name", ""),
                getattr(node, "description", ""),
                getattr(node, "value", "") if getattr(node, "value", None) is not None else "",
            )
            if str(part or "").strip()
        ).strip()
        if text:
            blobs.append(text.lower())
    has_calling = any(
        any(token in blob for token in ("calling", "ringing", "ongoing call", "call in progress"))
        for blob in blobs
    )
    has_end_call = any("end call" in blob or "decline" in blob for blob in blobs)
    return bool(has_calling and has_end_call)


def _maybe_advance_reference_hypothesis(
    runtime: RuntimeState,
    goal: Goal,
    *,
    attribution: Dict[str, Any],
    after_view: Dict[str, Any],
    after_features: Dict[str, Any],
    log,
    iteration: int,
) -> bool:
    """Advance search text only when attribution implicates the reference layer."""
    from plugin.agent.transition.attribution import TransitionAssessment, LayerBeliefDeltas

    layers = runtime.execution_state.hypothesis_layers
    ref = goal.ensure_reference() if goal.contact else None
    n_hyps = len((ref.search_hypotheses if ref else None) or []) or 1
    hyp_i = int(runtime.execution_state.search_hypothesis_index or 0)

    # Rebuild assessment object for the gate
    beliefs = attribution.get("affected_beliefs") or {}
    assessment = TransitionAssessment(
        action_family=str(attribution.get("action_family") or ""),
        outcome=str(attribution.get("outcome") or ""),
        effect_kind=str(attribution.get("effect_kind") or ""),
        likely_failure_domain=str(attribution.get("likely_failure_domain") or ""),
        affected_beliefs=LayerBeliefDeltas(
            reference_resolution=float(beliefs.get("reference_resolution") or 0),
            entity_resolution=float(beliefs.get("entity_resolution") or 0),
            target_actionability=float(beliefs.get("target_actionability") or 0),
            actuator_reliability=float(beliefs.get("actuator_reliability") or 0),
            perception_reliability=float(beliefs.get("perception_reliability") or 0),
        ),
        evidence=dict(attribution.get("evidence") or {}),
        notes=list(attribution.get("notes") or []),
    )
    if not should_advance_reference_hypothesis(
        assessment=assessment,
        layers=layers,
        goal=goal,
        after_view=after_view,
        after_features=after_features,
        hyp_index=hyp_i,
        n_hypotheses=n_hyps,
    ):
        return False
    if runtime.execution_state.advance_search_hypothesis(n_hyps):
        _log_cycle(
            log,
            iteration=iteration,
            phase="search_hypothesis_advance",
            payload={
                "index": runtime.execution_state.search_hypothesis_index,
                "active": goal.search_text(runtime.execution_state.search_hypothesis_index),
                "hypotheses": list((ref.search_hypotheses if ref else None) or []),
                "trigger": "reference_evidence",
                "attribution": attribution,
            },
            status="ok",
        )
        return True
    return False


def _maybe_advance_search_hypothesis(
    runtime: RuntimeState,
    goal: Goal,
    *,
    decision: Action,
    after_view: Dict[str, Any],
    after_features: Dict[str, Any],
    log,
    iteration: int,
    perception_settled: bool = False,
) -> bool:
    """Advance spelling only after settled empty judgment — never on incomplete perception."""
    # Never advance on the type_query that just opened a promising surface
    if decision.action_family == "type_query":
        _log_cycle(
            log,
            iteration=iteration,
            phase="search_hypothesis_advance_blocked",
            payload={"reason": "not_on_type_query_transition", "action_family": decision.action_family},
            status="ok",
        )
        return False

    ok_empty, reason = settled_empty_search_results(
        view=after_view,
        features=after_features,
        perception_settled=perception_settled,
    )
    if not ok_empty:
        _log_cycle(
            log,
            iteration=iteration,
            phase="search_hypothesis_advance_blocked",
            payload={
                "reason": reason,
                "action_family": decision.action_family,
                "resolution_policy": feature_get(after_features, "resolution_policy"),
                "result_surface_visible": feature_get(after_features, "result_surface_visible"),
                "contact_candidates_n": len(feature_get(after_features, "contact_candidates") or []),
            },
            status="ok",
        )
        return False

    if not after_features.get("query_matches_goal"):
        return False
    if str(after_view.get("search_query") or "").strip() == "":
        return False

    ref = goal.ensure_reference() if goal.contact else None
    n_hyps = len((ref.search_hypotheses if ref else None) or []) or 1
    hyp_i = int(runtime.execution_state.search_hypothesis_index or 0)
    if hyp_i >= n_hyps - 1:
        return False

    if not runtime.execution_state.advance_search_hypothesis(n_hyps):
        return False

    _log_cycle(
        log,
        iteration=iteration,
        phase="search_hypothesis_advance",
        payload={
            "index": runtime.execution_state.search_hypothesis_index,
            "active": goal.search_text(runtime.execution_state.search_hypothesis_index),
            "hypotheses": list((ref.search_hypotheses if ref else None) or []),
            "trigger": "empty_search_result_set",
            "decision": decision.__dict__,
            "after_features": {
                "query_matches_goal": after_features.get("query_matches_goal"),
                "resolution_policy": feature_get(after_features, "resolution_policy"),
                "resolution_confidence": feature_get(after_features, "resolution_confidence"),
                "screen_bucket": after_features.get("screen_bucket"),
                "result_surface_visible": feature_get(after_features, "result_surface_visible"),
            },
        },
        status="ok",
    )
    return True


def _apply_actuation_suppression(runtime: RuntimeState, action: Action, attribution: Dict[str, Any]) -> None:
    """Suppress the specific action key when actuation is implicated — not the query."""
    domain = str(attribution.get("likely_failure_domain") or "")
    effect = str(attribution.get("effect_kind") or "")
    if domain != FailureDomain.ACTUATION.value and effect not in {
        "missing_geometry",
        "actuator_failed",
        "no_transition",
        "not_attempted",
    }:
        return
    key = runtime.execution_state.action_key(action)
    # Longer suppress for missing geometry / actuator fail
    ttl = 4 if effect in {"missing_geometry", "actuator_failed"} else 3
    runtime.execution_state.prohibited_actions[key] = max(
        runtime.execution_state.prohibited_actions.get(key, 0), ttl
    )


def _frontier_backtrack_hint(branch: ExplorationBranch, *, fallback: str = "observe") -> str:
    """Pick the next frontier family from live branch evidence."""
    best = branch.best_non_observe_frontier(only_untried=True) or branch.best_non_observe_frontier()
    if best is None:
        best = branch.best_frontier(only_untried=True) or branch.best_frontier()
    if best is None:
        return fallback
    fam = str(best.action_family or "").strip()
    if not fam:
        return fallback
    if fam == "observe":
        return fallback
    return fam


def _invalidate_stale_frontier(
    runtime: RuntimeState,
    *,
    reason: str,
    fallback: str = "observe",
) -> str:
    """Invalidate a stale frontier and force the controller to replan."""
    branch = runtime.execution_state.exploration_branch
    hint = _frontier_backtrack_hint(branch, fallback=fallback)
    branch.invalidate_frontier(reason=reason)
    runtime.execution_state.exploration_branch = branch
    runtime.execution_state.world_exploration_needed = True
    runtime.execution_state.state_experience.pending_backtrack_family = hint or fallback
    runtime.execution_state.record_failure(reason)
    return hint or fallback


def _note_no_progress_replan(runtime: RuntimeState) -> int:
    """Count one replan forced by a branch that stopped making progress.

    ``should_escalate`` reads this counter to decide a branch is exhausted, but
    nothing incremented it, so that escalation could never fire however long the
    agent thrashed. Every retreat driven by absent progress is one of these.
    """
    count = int(getattr(runtime.execution_state, "no_progress_replans", 0) or 0) + 1
    runtime.execution_state.no_progress_replans = count
    return count


def _plan_next_branches(runtime: RuntimeState, goal: Goal, features: Any) -> Any:
    """Strategic search: which branches remain worth trying, and in what order."""
    from plugin.agent.executive.strategic_search import BranchPlan, plan_branches

    try:
        return plan_branches(
            goal,
            runtime.world_model,
            features,
            runtime.execution_state,
        )
    except Exception as exc:
        logger.debug("branch planning failed: %s", exc)
        return BranchPlan()


def _merge_affordance_hints(existing: List[str], additions: List[str]) -> List[str]:
    merged: List[str] = []
    seen = set()
    for item in list(existing) + list(additions):
        key = str(item or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(str(item).strip())
    return merged


def _semantic_state_signature(*, view: Dict[str, Any], features: Any = None, world_id: str = "") -> str:
    """Compact semantic key for experience/branching.

    Raw world signatures are too brittle for branch memory. We preserve the
    visible screen and the active cognitive slice so materially different
    surfaces do not collapse into the same state.
    """
    surface_state = feature_get(features, "surface_state") or view.get("surface_state") or {}
    if not isinstance(surface_state, dict):
        surface_state = {}
    active_subgraph = feature_get(features, "active_cognitive_subgraph") or feature_get(
        features, "active_subgraph"
    ) or {}
    if not isinstance(active_subgraph, dict):
        active_subgraph = {}

    def _norm_text(value: Any) -> str:
        return _clean_label(str(value or "")).lower().strip()

    def _list_preview(raw: Any, *, limit: int = 6) -> str:
        if not isinstance(raw, list):
            return ""
        out: List[str] = []
        for item in raw[:limit]:
            text = _norm_text(item)
            if text:
                out.append(text)
        return ",".join(out)

    active_entities = _list_preview(active_subgraph.get("active_entity_ids") or [])
    focus_regions = _list_preview(active_subgraph.get("focus_region_ids") or [])
    excluded_regions = _list_preview(active_subgraph.get("excluded_region_ids") or [])
    main_surface = _norm_text(
        view.get("screen")
        or view.get("active_surface")
        or surface_state.get("main_surface")
        or surface_state.get("sidebar_surface")
    )
    sidebar_surface = _norm_text(surface_state.get("sidebar_surface"))
    detail_surface = _norm_text(surface_state.get("detail_surface"))
    open_conversation = _norm_text(view.get("open_conversation"))
    call_state = _norm_text(view.get("call_state"))
    search_query = _norm_text(view.get("search_query"))
    tokens = [
        f"screen={main_surface or 'unknown'}",
        f"sidebar={sidebar_surface or 'none'}",
        f"detail={detail_surface or 'none'}",
        f"surface={_norm_text(view.get('active_surface') or surface_state.get('main_surface')) or 'unknown'}",
        f"open={open_conversation or 'none'}",
        f"call={call_state or 'none'}",
        f"search={search_query or 'none'}",
    ]
    if active_entities:
        tokens.append(f"active_entities={active_entities}")
    if focus_regions:
        tokens.append(f"focus_regions={focus_regions}")
    if excluded_regions:
        tokens.append(f"excluded_regions={excluded_regions}")
    if world_id:
        tokens.append(f"world={world_id}")
    return " | ".join(tokens)


def _transition_diagnosis_from_attempt(
    attempt: Any,
    *,
    after_features: Any = None,
    after_view: Optional[Dict[str, Any]] = None,
    decision: Optional[Action] = None,
) -> Dict[str, Any]:
    assessment = attempt.assessment if isinstance(getattr(attempt, "assessment", None), dict) else {}
    attribution = attempt.attribution if isinstance(getattr(attempt, "attribution", None), dict) else {}
    after_view = after_view or {}
    prediction_error = dict(getattr(attempt, "prediction_error", None) or {})
    next_move = "continue_branch"
    if str(getattr(attempt, "outcome", "") or "") in {
        TransitionOutcome.NO_EFFECT.value,
        TransitionOutcome.UNCERTAIN.value,
    }:
        next_move = "try_sibling_or_reobserve"
    elif str(getattr(attempt, "outcome", "") or "") == TransitionOutcome.REGRESSION.value:
        next_move = "backtrack"
    elif str(getattr(attempt, "outcome", "") or "") == TransitionOutcome.PROMISING_UNRESOLVED.value:
        next_move = "stay_local_and_explore"

    return {
        "outcome": str(getattr(attempt, "outcome", "") or ""),
        "action_family": str(getattr(attempt, "action_family", "") or getattr(decision, "action_family", "") or ""),
        "semantic_target": str(getattr(decision, "semantic_target", "") or ""),
        "effect_kind": str(getattr(attempt, "effect_kind", "") or ""),
        "failure_domain": str(attribution.get("likely_failure_domain") or ""),
        "goal_progress": str(assessment.get("goal_progress") or ""),
        "state_understood": bool(assessment.get("state_understood", True)),
        "context_preserved": bool(assessment.get("context_preserved", True)),
        "meaningful_change": bool(assessment.get("meaningful_change", False)),
        "confidence_delta": float(assessment.get("confidence_delta") or 0.0),
        "prediction_error": prediction_error,
        "newly_relevant_affordances": list(assessment.get("newly_relevant_affordances") or []),
        "contradiction_evidence": list(assessment.get("contradiction_evidence") or []),
        "surface": str(after_view.get("screen") or after_view.get("active_surface") or ""),
        "surface_state": dict(feature_get(after_features, "surface_state") or {}),
        "next_move": next_move,
        "notes": list(assessment.get("notes") or getattr(attempt, "reasons", []) or [])[:8],
    }


def _record_trajectory_run(
    *,
    goal: Goal,
    steps: list[TrajectoryStepRecord],
    success: bool,
    reason: str,
    evidence: Optional[Dict[str, Any]] = None,
) -> None:
    if not steps:
        return
    try:
        get_trajectory_memory().record_run(
            goal=goal,
            steps=steps,
            success=success,
            reason=reason,
            evidence=evidence or {},
        )
    except Exception:
        pass


def _transition_summary_from_attempt(attempt: Any, *, after_features: Any = None, decision: Optional[Action] = None) -> TransitionSummary:
    assessment = attempt.assessment if isinstance(getattr(attempt, "assessment", None), dict) else {}
    attribution = attempt.attribution if isinstance(getattr(attempt, "attribution", None), dict) else {}
    return TransitionSummary(
        outcome=str(getattr(attempt, "outcome", "") or ""),
        progress_delta=float(getattr(attempt, "progress_delta", 0.0) or 0.0),
        change_score=float(getattr(attempt, "change_score", 0.0) or 0.0),
        prediction=dict(getattr(attempt, "prediction", None) or {}),
        prediction_error=dict(getattr(attempt, "prediction_error", None) or {}),
        diagnosis=_transition_diagnosis_from_attempt(
            attempt,
            after_features=after_features,
            decision=decision,
        ),
        goal_progress=str(assessment.get("goal_progress") or ""),
        meaningful_change=bool(assessment.get("meaningful_change", False)),
        state_understood=bool(assessment.get("state_understood", True)),
        context_preserved=bool(assessment.get("context_preserved", True)),
        branch_reversible=bool(assessment.get("branch_reversible", True)),
        newly_relevant_affordances=list(assessment.get("newly_relevant_affordances") or []),
        contradiction_evidence=list(assessment.get("contradiction_evidence") or []),
        notes=list(assessment.get("notes") or getattr(attempt, "reasons", []) or []),
        risk=float(assessment.get("irreversible_risk_delta") or 0.0),
        confidence_delta=float(assessment.get("confidence_delta") or 0.0),
        effect_kind=str(getattr(attempt, "effect_kind", "") or ""),
        failure_domain=str(attribution.get("likely_failure_domain") or ""),
        action_family=str(getattr(attempt, "action_family", "") or getattr(decision, "action_family", "") or ""),
        selected_capability_id=str(assessment.get("selected_capability_id") or feature_get(after_features, "selected_capability_id") or ""),
        selected_capability_type=str(assessment.get("selected_capability_type") or feature_get(after_features, "selected_capability_type") or ""),
    )



def _action_has_geometry(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    pt = raw.get("target_point") or raw.get("point")
    if isinstance(pt, (list, tuple)) and len(pt) >= 2:
        return True
    bounds = raw.get("bounds")
    return isinstance(bounds, (list, tuple)) and len(bounds) >= 4


def _frontier_has_grounded_actuation(frontier: Any) -> bool:
    """True when the affordance frontier already carries a clickable non-observe move."""
    if not isinstance(frontier, dict):
        return False
    for item in frontier.get("observed_actions") or []:
        if not isinstance(item, dict):
            continue
        fam = str(item.get("family") or "").strip().lower()
        if not fam or fam in {"observe", "request_more_evidence", "scroll", "hover"}:
            continue
        if _action_has_geometry(item):
            return True
        for act in item.get("actuators") or []:
            if not isinstance(act, dict):
                continue
            pt = act.get("point") or act.get("target_point")
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                return True
            bounds = act.get("bounds")
            if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
                return True
    return False


def _openable_source_geometry(runtime: RuntimeState, feats: Any) -> bool:
    """True when OPEN_SOURCE can click a visible goal-contact row with bounds.

    Breaks the ACT↔geometry chicken-egg on chat lists: define_action can ground
    open_entity from inventory, but meta never chose ACT while has_grounded
    stayed false (live 092106).
    """
    try:
        extras = getattr(feats, "extras", None) or {}
    except Exception:
        extras = {}
    if not isinstance(extras, dict):
        return False
    phase = str(extras.get("forward_phase") or "").strip().upper()
    if not phase:
        ft = extras.get("forward_task")
        if isinstance(ft, dict):
            phase = str(ft.get("derived_phase") or "").strip().upper()
    if phase not in {"OPEN_SOURCE", "PRECLEAR"}:
        return False
    visible = bool(
        extras.get("source_conversation_visible")
        or extras.get("source_conversation_rows")
    )
    if not visible:
        ft = extras.get("forward_task") if isinstance(extras.get("forward_task"), dict) else {}
        preds = ft.get("predicates") if isinstance(ft.get("predicates"), dict) else {}
        visible = bool(preds.get("source_conversation_visible"))
    if not visible:
        return False
    contact = ""
    ft = extras.get("forward_task") if isinstance(extras.get("forward_task"), dict) else {}
    binds = ft.get("bindings") if isinstance(ft.get("bindings"), dict) else {}
    src_b = binds.get("source_conversation") if isinstance(binds.get("source_conversation"), dict) else {}
    constraints = src_b.get("constraints") if isinstance(src_b.get("constraints"), dict) else {}
    contact = str(constraints.get("name") or extras.get("source_contact") or "").strip()
    if not contact:
        return False
    try:
        from plugin.agent.apps.whatsapp_targets import entity_ok_for_click, in_sidebar_band
        from plugin.agent.whatsapp_view import contact_matches
        from plugin.worldmodel.entities.normalize import _clean_label
    except Exception:
        return False
    world = getattr(runtime, "world_model", None)
    ents = list((getattr(world, "entities", None) or {}).values()) if world is not None else []
    scene = (getattr(world, "last_scene_graph", None) or {}) if world is not None else {}
    for e in ents:
        if not getattr(e, "visible", False):
            continue
        try:
            if not in_sidebar_band(e, ents, scene_graph=scene):
                continue
            if not entity_ok_for_click(e):
                continue
            blob = (
                f"{_clean_label(getattr(e, 'label', '') or '')} "
                f"{_clean_label(getattr(e, 'semantic_role', '') or '')} "
                f"{_clean_label((getattr(e, 'attributes', None) or {}).get('description', ''))}"
            )
            if contact_matches(blob, contact, min_score=0.75):
                return True
        except Exception:
            continue
    return False


def _actuation_available(runtime: RuntimeState, feats: Any) -> bool:
    """Whether a *grounded* (geometry-bearing) non-observe move is available.

    Family name alone is not enough — that produced act=0 THINK thrash while
    sufficiency claimed the evidence was ready.
    """
    try:
        extras = getattr(feats, "extras", None) or {}
    except Exception:
        extras = {}

    def _grounded_family(raw: Any) -> bool:
        if not isinstance(raw, dict):
            return False
        fam = str(raw.get("family") or raw.get("action_family") or "").strip().lower()
        if not fam or fam in {"observe", "request_more_evidence"}:
            return False
        return _action_has_geometry(raw)

    brain = extras.get("brain_choice") if isinstance(extras, dict) else None
    if _grounded_family(brain):
        return True
    doc = getattr(runtime.execution_state, "unified_world_document", None)
    if isinstance(doc, dict):
        for key in ("suggested_actions", "next_action"):
            raw = doc.get(key)
            if _grounded_family(raw):
                return True
            if isinstance(raw, list):
                for item in raw[:8]:
                    if _grounded_family(item):
                        return True
    uni = getattr(runtime.execution_state, "last_unified_proposal", None)
    if isinstance(uni, dict):
        if _grounded_family(uni.get("next_action")):
            return True
    frontier = getattr(runtime.execution_state, "last_affordance_frontier", None)
    if _frontier_has_grounded_actuation(frontier):
        return True
    if isinstance(extras, dict) and _frontier_has_grounded_actuation(
        extras.get("affordance_frontier")
    ):
        return True
    if _openable_source_geometry(runtime, feats):
        return True
    return False


def _invalidate_geometry_for_surface_change(
    runtime: RuntimeState, *, surface: str, reason: str = ""
) -> bool:
    """Drop carried UI geometry when the accepted surface changes."""
    surf = str(surface or "").strip().lower()
    prev = str(getattr(runtime.execution_state, "last_accepted_surface", "") or "").strip().lower()
    runtime.execution_state.last_accepted_surface = surf
    if not prev or not surf or prev == surf:
        return False
    runtime.execution_state.geometry_generation = int(
        getattr(runtime.execution_state, "geometry_generation", 0) or 0
    ) + 1
    # Stale next_action / proposal points belong to the prior surface.
    uni = getattr(runtime.execution_state, "last_unified_proposal", None)
    if isinstance(uni, dict):
        na = uni.get("next_action")
        if isinstance(na, dict):
            na = dict(na)
            na.pop("target_point", None)
            na.pop("point", None)
            na.pop("bounds", None)
            na["geometry_invalidated"] = reason or f"surface {prev}->{surf}"
            uni["next_action"] = na
            uni["surface"] = surf
            runtime.execution_state.last_unified_proposal = uni
    doc = getattr(runtime.execution_state, "unified_world_document", None)
    if isinstance(doc, dict) and str(doc.get("surface") or "").strip().lower() != surf:
        # Keep document but force a multimodal look before acting on old objects.
        runtime.execution_state.must_executive_reperceive = True
    return True


def _multimodal_look(
    runtime: RuntimeState,
    goal: Goal,
    *,
    features: Any,
    mode: str = "perceive",
) -> bool:
    """Run stage-1 unified cognition as a brain look tool (PERCEIVE).

    AX refresh alone is not a perceptor look — without this, reflect reused
    stale vision geometry across surface changes.
    """
    try:
        from plugin.agent.unified_cognition import (
            consult_unified_cognition,
            unified_cognition_enabled,
        )
    except Exception:
        return False
    if not unified_cognition_enabled():
        return False
    try:
        runtime.execution_state.perception_mode = str(mode or "perceive")
    except Exception:
        pass
    # AX/app_view often knows the open chat before the accepted document does.
    # Prefer the live view so post-act choice does not keep open='• Search'.
    try:
        overlay = get_overlay(goal.app, runtime.world_model)
        view = overlay.view(runtime.world_model) if overlay is not None else {}
        open_c = str((view or {}).get("open_conversation") or "").strip()
        if open_c and hasattr(features, "extras") and isinstance(features.extras, dict):
            prior = str(features.extras.get("open_conversation") or "").strip().lower()
            if (not prior) or prior in {"• search", "• search|", "search", "q search"}:
                features.extras["open_conversation"] = open_c
        doc = getattr(runtime.execution_state, "unified_world_document", None)
        if open_c and isinstance(doc, dict):
            prior_doc = str(doc.get("open_conversation") or "").strip().lower()
            if (not prior_doc) or prior_doc in {"• search", "• search|", "search", "q search"}:
                doc["open_conversation"] = open_c
    except Exception:
        pass
    try:
        proposal = consult_unified_cognition(
            goal, runtime.world_model, features, runtime.execution_state
        )
    except Exception:
        return False
    if proposal is None:
        return False
    model = str(getattr(proposal, "model", "") or "")
    try:
        obs = dict(proposal.observed_state or {}) if isinstance(proposal.observed_state, dict) else {}
        world = dict(proposal.world_model or {}) if isinstance(getattr(proposal, "world_model", None), dict) else {}
        locate_ans = (
            obs.get("locate_effect_answer")
            or world.get("locate_effect_answer")
            or obs.get("locate_effect_observed")
            or world.get("locate_effect_observed")
        )
        uni_payload = {
            "frame": int(getattr(runtime.execution_state, "unified_frame", 0) or 0),
            "evidence_gaps": [str(g) for g in (proposal.evidence_gaps or []) if str(g).strip()],
            "coverage": proposal.coverage,
            "confidence": float(proposal.confidence or 0.0),
            "surface": str(obs.get("surface") or "").strip(),
            "probe_available": bool(getattr(proposal, "recommended_probe", None)),
            "next_action": dict(proposal.next_action or {}),
            "look_mode": str(mode or "perceive"),
            "model": model,
            "observed_state": {
                k: obs.get(k)
                for k in (
                    "surface",
                    "open_conversation",
                    "locate_effect_answer",
                    "locate_effect_observed",
                    "source_query_not_surfaced",
                    "source_query_located",
                    "verified_effect_predicates",
                )
                if k in obs
            },
        }
        if "source_query_not_surfaced" in obs or "source_query_not_surfaced" in world:
            uni_payload["source_query_not_surfaced"] = bool(
                obs.get("source_query_not_surfaced", world.get("source_query_not_surfaced"))
            )
        if "locate_effect_observed" in obs or "locate_effect_observed" in world:
            uni_payload["locate_effect_observed"] = bool(
                obs.get("locate_effect_observed", world.get("locate_effect_observed"))
            )
        if locate_ans is not None and not isinstance(locate_ans, bool):
            uni_payload["locate_effect_answer"] = locate_ans
        elif isinstance(locate_ans, bool):
            uni_payload["locate_effect_observed"] = locate_ans
        runtime.execution_state.last_unified_proposal = uni_payload
    except Exception:
        pass
    surf = str((proposal.observed_state or {}).get("surface") or "").strip().lower()
    if surf:
        _invalidate_geometry_for_surface_change(
            runtime, surface=surf, reason=f"multimodal_look:{mode}"
        )
    open_after = ""
    try:
        open_after = str((proposal.observed_state or {}).get("open_conversation") or "").strip()
        if not open_after:
            open_after = str(
                (getattr(runtime.execution_state, "unified_world_document", None) or {}).get(
                    "open_conversation"
                )
                or ""
            ).strip()
    except Exception:
        open_after = ""
    _clear_post_action_reperceive_if_fresh(
        runtime,
        multimodal_ok=True,
        proposal_model=model,
        open_conversation=open_after,
        state_sig=str(getattr(runtime.execution_state, "last_state_signature", "") or ""),
    )
    # Paid visual look after AX-blind locate: resolve EffectStatus UNKNOWN.
    # Absence alone ≠ still_unobservable — only insufficient observation does.
    try:
        state = runtime.execution_state
        if bool(getattr(state, "locate_effect_verify_owed", False)):
            from plugin.agent.capabilities.locate_content import (
                resolve_locate_effect_after_visual_verify,
            )
            from plugin.agent.source_query_binding import (
                document_establishes_locate_patient,
            )

            doc = getattr(state, "unified_world_document", None)
            q = str(getattr(state, "last_locate_query", "") or "").strip()
            # Related platform hits (e.g. Instagram path) must not satisfy patient.
            visible = bool(
                q
                and isinstance(doc, dict)
                and document_establishes_locate_patient(doc, q)
            )
            resolve_locate_effect_after_visual_verify(
                state,
                content_located=False,
                query_visible=visible,
                multimodal_ok=True,
                proposal_model=model,
                document=doc,
            )
    except Exception:
        pass
    return True


def _note_failed_motor(
    runtime: RuntimeState,
    *,
    family: str,
    target: str = "",
    point: Any = None,
) -> None:
    from plugin.agent.brain import motor_fingerprint
    from plugin.agent.executive.effect_implications import (
        method_context_from_state,
        scoped_method_avoid_key,
    )
    from plugin.agent.executive.intention_frame import active_intention_frame

    keys = list(getattr(runtime.execution_state, "avoid_motor_keys", None) or [])
    world_sig = ""
    intention_id = ""
    try:
        iframe = active_intention_frame(runtime.execution_state)
        intention_id = str(getattr(getattr(iframe, "intention", None), "id", "") or "")
        open_c = ""
        try:
            feats = getattr(runtime.execution_state, "last_features", None)
            extras = getattr(feats, "extras", None) if feats is not None else None
            if isinstance(extras, dict):
                open_c = str(extras.get("open_conversation") or "")
        except Exception:
            open_c = ""
        ctx = method_context_from_state(
            runtime.execution_state,
            world={
                "surface": str(
                    getattr(runtime.execution_state, "last_surface", "") or ""
                ),
                "open_conversation": open_c,
            },
        )
        world_sig = ctx.signature() if ctx is not None else ""
        if not world_sig:
            world_sig = str(
                getattr(runtime.execution_state, "last_world_signature", "") or ""
            )
    except Exception:
        pass
    # Point-specific grounding avoid — also world-scoped so the same XY is not
    # sticky after a legitimate surface/container transition.
    base_point = motor_fingerprint(family, target, point)
    key = f"{base_point}|sig={world_sig}" if base_point and base_point != "||" else ""
    if key and key not in keys:
        keys.append(key)
    # Method-level: scoped to intention + world signature.
    method_key = ""
    try:
        method_key = scoped_method_avoid_key(
            family,
            target,
            intention_id=intention_id,
            world_signature=world_sig,
        )
        if method_key not in keys:
            keys.append(method_key)
    except Exception:
        method_key = ""
    if key:
        runtime.execution_state.last_failed_motor_key = key
    elif method_key:
        runtime.execution_state.last_failed_motor_key = method_key
    runtime.execution_state.avoid_motor_keys = keys[-24:]


def _open_repair_should_escalate_to_search(
    runtime: RuntimeState,
    *,
    last_target: str = "",
) -> bool:
    """SEARCH only when retrieval/container identity is still owed.

    Uses authoritative bindings / search-episode state — not URL/`You:` label
    shape heuristics (those are not semantic typing).
    """
    _ = last_target  # retained for call-site compatibility / logging
    try:
        hints = runtime.world_model.overlay_hints or {}
        ft = hints.get("forward_task") if isinstance(hints, dict) else None
        preds = (ft.get("predicates") if isinstance(ft, dict) else None) or {}
        if isinstance(preds, dict):
            if preds.get("source_conversation_open"):
                return False
            if preds.get("source_object_visible"):
                return False
        ep = getattr(runtime.execution_state, "search_episode", None) or {}
        if isinstance(ep, dict) and str(ep.get("status") or "") in {
            "complete",
            "ranking",
            "retrieving",
        }:
            # Results already in hand — method failed, not retrieval.
            if ep.get("candidates") or ep.get("chosen_label") or ep.get("status") == "complete":
                return False
    except Exception:
        pass
    return True


def _note_open_source_failure(
    runtime: RuntimeState,
    decision: Any,
    *,
    reason: str = "",
) -> Dict[str, Any]:
    """Recoverable open failure: kill bad geometry, force a fresh look, escalate.

    More important than never missing: after a wrong open click the agent must
    not reuse the same eid/point or burn looks on stale perception — it must
    re-perceive and retry with a different strategy (VLM point, then search
    only when retrieval is still owed).
    """
    fam = str(getattr(decision, "action_family", "") or "").strip().lower()
    if fam not in {"open_entity", "open_contact"}:
        return {}
    last_target = str(getattr(decision, "semantic_target", "") or "")
    _note_failed_motor(
        runtime,
        family=fam,
        target=last_target,
        point=getattr(decision, "target_point", None),
    )
    # Drop phash / carried perception so the next look is not frame-1 reuse.
    try:
        runtime.execution_state.unified_perception_cache = {}
    except Exception:
        pass
    runtime.execution_state.geometry_generation = int(
        getattr(runtime.execution_state, "geometry_generation", 0) or 0
    ) + 1
    runtime.execution_state.must_executive_reperceive = True
    runtime.execution_state.post_action_reperceive_pending = True
    # Clear stale proposal geometry tied to the failed click.
    uni = getattr(runtime.execution_state, "last_unified_proposal", None)
    if isinstance(uni, dict):
        na = uni.get("next_action")
        if isinstance(na, dict):
            na = dict(na)
            na.pop("target_point", None)
            na.pop("point", None)
            na.pop("bounds", None)
            na["geometry_invalidated"] = reason or "open_source_failure"
            uni["next_action"] = na
            runtime.execution_state.last_unified_proposal = uni

    hints = runtime.world_model.overlay_hints
    if hints is None:
        runtime.world_model.overlay_hints = {}
        hints = runtime.world_model.overlay_hints
    repair = dict(hints.get("open_repair") or {})
    failed_ids = [int(x) for x in (repair.get("failed_entity_ids") or []) if str(x).lstrip("-").isdigit()]
    eid = getattr(decision, "target_entity_id", None)
    if eid is not None:
        try:
            eid_i = int(eid)
            if eid_i not in failed_ids:
                failed_ids.append(eid_i)
        except (TypeError, ValueError):
            pass
    attempts = int(repair.get("attempts") or 0) + 1
    prefer = "vlm_point"
    if attempts >= 2:
        if _open_repair_should_escalate_to_search(runtime, last_target=last_target):
            prefer = "compose_search_query"
        else:
            # Method exhausted under current world; do not wipe retrieval.
            prefer = "method_exhausted_reperceive"
    repair.update(
        {
            "failed_entity_ids": failed_ids[-8:],
            "attempts": attempts,
            "prefer": prefer,
            "last_reason": str(reason or "")[:200],
            "last_target": last_target[:120],
            "failure_class": (
                "method_ineffective"
                if prefer == "method_exhausted_reperceive"
                else str(repair.get("failure_class") or "")
            ),
        }
    )
    hints["open_repair"] = repair
    try:
        runtime.execution_state.open_repair = dict(repair)
    except Exception:
        pass
    # Mirror into features extras on the next observe via overlay_hints.
    return repair


def _handle_open_entity_effect_absent(
    runtime: RuntimeState,
    step: Any,
    *,
    fam: str = "",
    pred_error: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Prediction-miss path for open_entity / open_contact.

    Authoritative typed navigation uses ``Action.attempt_id`` only — never
    ambient ExecutionState. Missing attempt id fails closed (no debt mutation).
    Legacy / untyped opens cannot acquire navigation establish authority.
    """
    pred_error = pred_error if isinstance(pred_error, dict) else {}
    fam_l = str(
        fam
        or getattr(step, "action_family", "")
        or pred_error.get("action_family")
        or ""
    ).strip().lower()
    if step is None or fam_l not in {"open_entity", "open_contact"}:
        return {}
    open_repair = _note_open_source_failure(
        runtime,
        step,
        reason=str(pred_error.get("verdict") or "prediction_mismatch"),
    )
    referent_mismatch: Dict[str, Any] = {}
    try:
        from plugin.agent.procedures.forward_message import action_open_semantics
        from plugin.agent.role_binding import (
            apply_referent_mismatch,
            note_transition_pending,
        )

        label = str(getattr(step, "semantic_target", "") or "")
        target_kind = str(
            getattr(step, "target_kind", "") or pred_error.get("target_kind") or ""
        )
        # Causal identity rides on the Action — never ambient ExecutionState.
        attempt_id = str(getattr(step, "attempt_id", "") or "").strip()
        legacy = bool(getattr(step, "legacy_semantics", False))
        typed_nav = bool(getattr(step, "action_is_navigation", False)) and not legacy
        if typed_nav and not attempt_id:
            logger.warning(
                "open miss: typed navigation missing Action.attempt_id — "
                "causal attribution incomplete; refusing debt mutation"
            )
            return {
                "open_repair": open_repair,
                "referent_mismatch": {
                    "role": "",
                    "label": label[:120],
                    "class": "CAUSAL_ATTRIBUTION_INCOMPLETE",
                    "attempt_id": "",
                    "establishes_roles": [],
                },
            }
        ft_phase = ""
        try:
            hints0 = runtime.world_model.overlay_hints or {}
            ft0 = hints0.get("forward_task") or {}
            ft_phase = str(
                (ft0.get("derived_phase") if isinstance(ft0, dict) else "") or ""
            )
        except Exception:
            ft_phase = ""
        if typed_nav:
            est = [
                str(r)
                for r in (getattr(step, "establishes_roles", None) or [])
                if str(r).strip()
            ]
            sem = {
                "is_navigation": True,
                "target_role": "",
                "establishes_roles": est,
                "target_kind": target_kind,
                "incomplete": not bool(est),
            }
        else:
            # Legacy / untyped: RoleBinder target-role path only — never invent
            # navigation establish authority from phase/label re-inference.
            if legacy or not bool(getattr(step, "establishes_roles", None)):
                sem = {
                    "is_navigation": False,
                    "target_role": "source_container",
                    "establishes_roles": [],
                    "target_kind": target_kind,
                    "legacy": True,
                }
            else:
                sem = action_open_semantics(
                    fam_l,
                    phase=ft_phase or "OPEN_SOURCE",
                    target=label,
                    target_kind=target_kind,
                )
                # Strip any accidental navigation power from re-inference.
                if sem.get("is_navigation"):
                    sem = {
                        "is_navigation": False,
                        "target_role": str(sem.get("target_role") or "source_container"),
                        "establishes_roles": [],
                        "target_kind": target_kind,
                        "legacy": True,
                    }
        hints = runtime.world_model.overlay_hints
        if hints is None:
            runtime.world_model.overlay_hints = {}
            hints = runtime.world_model.overlay_hints
        if sem.get("is_navigation"):
            est_roles = list(sem.get("establishes_roles") or [])
            if sem.get("incomplete") or not est_roles:
                referent_mismatch = {
                    "role": "",
                    "label": label[:120],
                    "class": "INCOMPLETE_TYPED_NAVIGATION",
                    "attempt_id": attempt_id,
                    "establishes_roles": [],
                }
            else:
                note_transition_pending(
                    runtime.execution_state,
                    establishes_roles=est_roles,
                    target_label=label,
                    attempt_id=attempt_id,
                )
                referent_mismatch = {
                    "role": "",
                    "label": label[:120],
                    "class": "EXPECTED_TRANSITION_NOT_SETTLED_YET",
                    "attempt_id": attempt_id,
                    "establishes_roles": est_roles,
                }
        else:
            # Attempt-scoped debt mutation still requires Action.attempt_id.
            if not attempt_id:
                referent_mismatch = {
                    "role": str(sem.get("target_role") or "source_container"),
                    "label": label[:120],
                    "class": "CAUSAL_ATTRIBUTION_INCOMPLETE",
                    "attempt_id": "",
                }
            else:
                role = str(sem.get("target_role") or "source_container")
                ft = dict(hints.get("forward_task") or {})
                new_ft = apply_referent_mismatch(
                    runtime.execution_state,
                    role=role,
                    candidate_label=label,
                    forward_task=ft,
                    attempt_id=attempt_id,
                )
                if isinstance(new_ft, dict):
                    hints["forward_task"] = new_ft
                referent_mismatch = {
                    "role": role,
                    "label": label[:120],
                    "class": "REFERENT_MISMATCH",
                    "attempt_id": attempt_id,
                }
    except Exception as exc:
        referent_mismatch = {"error": str(exc)[:120]}
    # Ledger open ACT miss as METHOD_INEFFECTIVE when an IntentionFrame is active
    # (same world-scoped reactivation rules as reveal).
    try:
        from plugin.agent.executive.intention_frame import (
            AttemptRecord,
            AttemptValidity,
            FailureClass,
            MethodOutcome,
            MethodStatus,
            active_intention_frame,
            apply_derived_status,
            mark_method_attempted,
            record_method_status,
        )

        iframe = active_intention_frame(runtime.execution_state)
        if iframe is not None and fam_l in {"open_entity", "open_contact"}:
            mid = f"{fam_l}:{str(getattr(step, 'semantic_target', '') or '')[:80]}"
            mark_method_attempted(iframe, mid)
            from plugin.agent.executive.effect_implications import (
                method_context_from_state,
            )

            open_c = ""
            try:
                feats = getattr(runtime.execution_state, "last_features", None)
                extras = getattr(feats, "extras", None) if feats is not None else None
                if isinstance(extras, dict):
                    open_c = str(extras.get("open_conversation") or "")
                if not open_c:
                    snap = getattr(runtime, "last_snapshot", None)
                    view = getattr(snap, "view", None) if snap is not None else None
                    if isinstance(view, dict):
                        open_c = str(view.get("open_conversation") or "")
            except Exception:
                open_c = ""
            ctx = method_context_from_state(
                runtime.execution_state,
                world={
                    "surface": str(
                        getattr(runtime.execution_state, "last_surface", "") or ""
                    ),
                    "open_conversation": open_c,
                },
            )
            record_method_status(
                iframe,
                mid,
                MethodStatus.INEFFECTIVE.value,
                method_context=ctx,
                world_signature=ctx.signature(),
            )
            iframe.attempts.append(
                AttemptRecord(
                    method_id=mid,
                    execution_status="motor_ok",
                    observation_quality=0.9,
                    method_outcome=MethodOutcome.EFFECT_ABSENT.value,
                    failure_class=FailureClass.METHOD_INEFFECTIVE.value,
                    attempt_validity=AttemptValidity.VALID.value,
                    method_status=MethodStatus.INEFFECTIVE.value,
                    evidence_refs=[
                        str(pred_error.get("verdict") or "execution_effect_missing")[:120]
                    ],
                )
            )
            apply_derived_status(iframe)
    except Exception:
        pass
    return {"open_repair": open_repair, "referent_mismatch": referent_mismatch}


def run_goal_closed_loop(
    runtime: RuntimeState,
    goal: Goal,
    *,
    observe: ObserveFn,
    execute: ActionExecutor,
    log: Optional[EventLogger] = None,
    max_iterations: int = 15,
    max_stepcount: Optional[int] = None,
    settle_s: float = 1.0,
    wait_fn: Optional[WaitFn] = None,
    retention_floor: float = 0.35,
    engine: Optional[DecisionEngine] = None,
    memory: Optional["MemorySystem"] = None,
) -> GoalResult:
    """Brain-owned tools closed loop (controller is a dispatcher).

    Per iteration while the goal is incomplete and under budget:

    1. Context from the current world (bootstrap look once; else reuse).
    2. Brain meta chooses the tool/capability for this turn.
    3. Dispatch only that tool: PERCEIVE → perceptor; ACT →
       ``define_action_step`` then actor; other metas → their handlers.

    Surprise / low worldview / dead motors set signals for meta — they do not
    force a look ahead of the brain's choice.

    Ingress note: this function is the **first legacy adapter** into the common
    TaskIngress → AgentRuntime seam. It is not the owner/composition root of
    TaskIngress. Target shape remains: all clients/harnesses → TaskIngress →
    AgentRuntime. Ownership is one-way (AgentRuntime owns RuntimeState); this
    path never attaches AgentRuntime onto RuntimeState and never auto-retrieves
    memory.
    """
    # Composition root: register domain evidence providers outside generic core.
    try:
        from plugin.agent.composition import compose_domain_adapters

        compose_domain_adapters()
    except Exception:
        pass

    # Live goal processes (HERMES_LIVE_GOAL=1) must have passed package evals
    # before the closed loop starts — same role as server boot before API calls.
    try:
        from plugin.evals.check import require_live_eval_preflight

        require_live_eval_preflight()
    except SystemExit:
        raise
    except Exception as exc:
        import os

        if str(os.getenv("HERMES_LIVE_GOAL", "") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            raise SystemExit(f"live eval preflight failed: {exc}") from exc

    # Legacy Goal → TaskRequest → AgentRuntime (first adapter; not ingress owner).
    # Locals kept for the seam; closed-loop internals continue to use ``runtime``.
    # RuntimeState must never gain an AgentRuntime backreference.
    from plugin.agent.ingress import ExecutionConstraints, TaskIngress
    from plugin.agent.memory.bootstrap import open_local_memory
    from plugin.agent.memory.system import MemorySystem, NoopMemorySystem
    from plugin.agent.runtime.agent_runtime import AgentRuntime

    if memory is not None:
        _memory: MemorySystem = memory
    else:
        try:
            _memory, _ = open_local_memory(
                start_bootstrap=True, blocking_bootstrap=False
            )
        except Exception:
            _memory = NoopMemorySystem()
    # ComputerUse benchmark: force substrate via constraints (not a harness branch).
    _task_request = TaskIngress.normalize(
        TaskIngress.from_legacy_goal(
            goal,
            client_context={
                "client": "live_harness",
                "legacy_adapter": "run_goal_closed_loop",
            },
            constraints=ExecutionConstraints(
                allowed_substrates=("computer_use",),
                forced_substrate="computer_use",
            ),
        )
    )
    agent_runtime = AgentRuntime(
        runtime_state=runtime,
        memory=_memory,
        task_request=_task_request,
    )
    if agent_runtime.runtime_state is not runtime:
        raise RuntimeError("AgentRuntime must preserve RuntimeState identity")
    # Kept at the composition boundary for future executive/memory decisions.
    # Existing loop internals continue to use ``runtime`` (same object).
    _ = agent_runtime.task_request

    eng = engine or get_decision_engine()
    # Goal tokens for branch/selection consistency + revert_effects analyze.
    try:
        refs: List[str] = []
        for attr in ("link_query", "content_query", "query", "contact", "target_contact"):
            val = str(getattr(goal, attr, "") or "").strip()
            if val and val not in refs:
                refs.append(val)
        runtime.execution_state.goal_referents = refs
    except Exception:
        pass
    if settle_s <= 0.05:
        monitor_timeout = 0.35
        monitor_poll = 0.05
    else:
        monitor_timeout = max(1.2, settle_s * 1.5)
        monitor_poll = 0.3
    monitor = TransitionMonitor(timeout_s=monitor_timeout, poll_s=monitor_poll)
    evaluator = TransitionEvaluator()
    experience = runtime.execution_state.state_experience
    trajectory_steps: list[TrajectoryStepRecord] = []
    raw_call_ring_seen = {"seen": False}
    step_budget = resolve_step_budget(
        max_iterations=max_iterations,
        max_stepcount=max_stepcount,
    )
    goal_run_timeout_s = resolve_goal_run_timeout_seconds(goal_kind=goal.kind)
    goal_no_progress_timeout_s = resolve_goal_no_progress_timeout_seconds(goal_kind=goal.kind)
    goal_run_started_at = time.monotonic()
    goal_last_progress_at = goal_run_started_at

    _log_cycle(
        log,
        iteration=0,
        phase="loop_budget",
        payload={
            "max_iterations": max_iterations,
            "max_stepcount": max_stepcount,
            "max_stepcount_hint": max_stepcount,
                "budget_semantics": "soft_hint",
                "resolved_step_budget": step_budget,
                "goal_run_timeout_s": goal_run_timeout_s,
                "goal_run_timeout_semantics": "soft_hint",
                "goal_no_progress_timeout_s": goal_no_progress_timeout_s,
                "goal_no_progress_timeout_semantics": "soft_hint",
            },
        )

    def _wait(seconds: float, reason: str) -> None:
        if wait_fn:
            wait_fn(seconds, reason)
        else:
            time.sleep(seconds)

    def _goal_run_elapsed_s() -> float:
        try:
            return max(0.0, float(time.monotonic() - goal_run_started_at))
        except Exception:
            return 0.0

    def _goal_run_budget_exceeded() -> bool:
        if goal_run_timeout_s == float("inf"):
            return False
        return _goal_run_elapsed_s() >= float(goal_run_timeout_s)

    def _goal_progress_elapsed_s() -> float:
        try:
            return max(0.0, float(time.monotonic() - goal_last_progress_at))
        except Exception:
            return 0.0

    def _goal_no_progress_budget_exceeded() -> bool:
        if goal_no_progress_timeout_s == float("inf"):
            return False
        return _goal_progress_elapsed_s() >= float(goal_no_progress_timeout_s)

    # Every GoalResult leaves through _finish_success or _finish_failure, so
    # stopping the watchdog in both covers all exits from the loop body.
    watchdog_iteration: Dict[str, int] = {"iteration": 0}
    watchdog_stop, _watchdog_thread = _start_stall_watchdog(log, watchdog_iteration)

    def _finish_success(
        evidence: Optional[Dict[str, Any]],
        *,
        iterations: int,
    ) -> GoalResult:
        watchdog_stop.set()
        result = GoalResult.success(
            evidence or {},
            iterations=iterations,
            planner_invocations=runtime.execution_state.planner_invocations,
        )
        _record_trajectory_run(
            goal=goal,
            steps=trajectory_steps,
            success=True,
            reason=result.reason,
            evidence=result.evidence,
        )
        return result

    def _finish_failure(
        reason: str,
        evidence: Optional[Dict[str, Any]],
        *,
        iterations: int,
    ) -> GoalResult:
        watchdog_stop.set()
        result = GoalResult.failure(
            reason,
            evidence or {},
            iterations=iterations,
            planner_invocations=runtime.execution_state.planner_invocations,
        )
        _record_trajectory_run(
            goal=goal,
            steps=trajectory_steps,
            success=False,
            reason=result.reason,
            evidence=result.evidence,
        )
        return result

    # Attach the goal to the workspace once, so it knows the phase ladder and
    # carries the task contract (success conditions, constraints) authoritatively.
    bind_goal(runtime.execution_state, goal)

    # Executive meta-perception state carried across iterations. The judgement
    # is computed every iteration for observability; under HERMES_META_PERCEPTION
    # it also gates whether we re-perceive at the top of the loop.
    meta_perception_enabled = _meta_perception_enabled()
    prev_meta_suppress = False
    prev_static_streak = 0
    prev_snap_pre: Optional[PerceptionSnapshot] = None
    prev_state_sig: Optional[str] = None
    static_streak = 0

    # Foreground ownership lives in the actuation capability, not here. The agent
    # owns keeping its app usable, but *how* depends on the app: perception always
    # runs in the background (window-scoped capture sees the app regardless of
    # z-order), and actuation prefers background AX actions (AXPress / AXValue,
    # invisible) and brings the app to the foreground *itself* only when it must
    # fall back to synthetic clicks/keystrokes on an AX-blind app. The executor
    # makes that choice per action, so the control loop no longer foregrounds
    # preemptively (doing so would defeat background actuation for AX-rich apps).

    # Wall-clock of the previous iteration, so each one can report its own cost.
    # Reconstructing this by diffing adjacent event timestamps was the only way to
    # see that iterations were taking 200s, and it does not attribute the time to
    # anything — a run whose dominant cost is invisible cannot be made faster.
    iteration_started_at = time.monotonic()

    for iteration in range(1, step_budget + 1):
        # Reported for the iteration just finished, at the top of the next one, so
        # that every exit path from the body is covered — the body has a dozen
        # `continue`s and a summary at the bottom would silently miss exactly the
        # iterations that took an unusual route.
        if iteration > 1:
            spent = time.monotonic() - iteration_started_at
            perception_s = float(
                getattr(runtime.execution_state, "last_perception_latency_s", 0.0) or 0.0
            )
            _log_cycle(
                log,
                iteration=iteration - 1,
                phase="iteration_cost",
                payload={
                    "iteration_s": round(spent, 1),
                    "perception_model_s": round(perception_s, 1),
                    "unaccounted_s": round(max(0.0, spent - perception_s), 1),
                    "seconds_since_anything_advanced": round(_goal_progress_elapsed_s(), 1),
                    "elapsed_s": round(_goal_run_elapsed_s(), 1),
                    "message": (
                        f"iteration {iteration - 1} took {spent:.0f}s "
                        f"({perception_s:.0f}s in the perception model)"
                    ),
                },
                status="warn" if spent >= 120 else "ok",
            )
        iteration_started_at = time.monotonic()
        watchdog_iteration["iteration"] = iteration
        if _goal_run_budget_exceeded():
            elapsed = _goal_run_elapsed_s()
            _log_cycle(
                log,
                iteration=iteration,
                phase="goal_run_budget_exceeded",
                payload={
                    "elapsed_s": round(elapsed, 3),
                    "goal_run_timeout_s": goal_run_timeout_s,
                    "step_budget": step_budget,
                    "reason": "wall_clock_budget_exhausted",
                },
                status="fail",
            )
            return _finish_failure(
                "goal wall-clock budget reached",
                {"elapsed_s": round(elapsed, 3), "goal_run_timeout_s": goal_run_timeout_s},
                iterations=iteration - 1,
            )
        progress_elapsed = _goal_progress_elapsed_s()
        no_progress_budget_exceeded = _goal_no_progress_budget_exceeded()
        # Put the clock where the decider can read it. The loop has always known
        # how long it has been since anything advanced, and logged it, but the
        # number never reached the model — so a run could spend thirteen minutes
        # reissuing one move while the only party able to choose a different one
        # had no idea any time had passed at all.
        runtime.execution_state.seconds_since_progress = round(progress_elapsed, 1)
        runtime.execution_state.no_progress_budget_s = (
            0.0 if goal_no_progress_timeout_s == float("inf") else float(goal_no_progress_timeout_s)
        )
        _log_cycle(
            log,
            iteration=iteration,
            phase="progress_clock",
            payload={
                "elapsed_s": round(_goal_run_elapsed_s(), 3),
                "elapsed_since_progress_s": round(progress_elapsed, 3),
                "goal_no_progress_timeout_s": goal_no_progress_timeout_s,
                "step_budget_remaining": max(0, step_budget - iteration + 1),
                "soft_watchdog": True,
                "no_progress_budget_exceeded": no_progress_budget_exceeded,
            },
            status="warn" if no_progress_budget_exceeded else "ok",
        )
        if no_progress_budget_exceeded:
            if bool(getattr(runtime.execution_state, "grounding_reground_only", False)):
                # Typed grounding stale: preserve bindings; only re-look.
                runtime.execution_state.must_executive_reperceive = True
                runtime.execution_state.world_exploration_needed = False
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="grounding_reground_only",
                    payload={
                        "elapsed_since_progress_s": round(progress_elapsed, 3),
                        "target": str(
                            getattr(
                                runtime.execution_state,
                                "grounding_reground_target",
                                "",
                            )
                            or ""
                        ),
                        "forbidden": [
                            "no_progress_replan",
                            "search_source_again",
                            "invalidate_frontier",
                        ],
                        "recovery": "perceive_reground",
                    },
                    status="warn",
                )
            else:
                branch_hint = _invalidate_stale_frontier(
                    runtime,
                    reason="no_progress_watchdog",
                    fallback="observe",
                )
                replans = _note_no_progress_replan(runtime)
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="no_progress_replan",
                    payload={
                        "elapsed_since_progress_s": round(progress_elapsed, 3),
                        "goal_no_progress_timeout_s": goal_no_progress_timeout_s,
                        "branch_hint": branch_hint,
                        "branch": runtime.execution_state.exploration_branch.to_dict(),
                        "no_progress_replans": replans,
                    },
                    status="warn",
                )
        runtime.execution_state.tick_search_query_hint()

        # Keeping the task app usable is the agent's job, not the user's. A call
        # or a notification steals the foreground mid-task, and every synthetic
        # click and keystroke after that lands in whatever window took it — so
        # the agent takes the foreground back itself, every iteration it finds it
        # gone, without a cap. The interruptions this answers recur by nature, so
        # a budget would just mean surrendering the task to the third phone call.
        #
        # This sits *before* perception deliberately. Raising a window changes the
        # screen; doing it after the photograph would invalidate the very frame
        # the decision is about to be made from, and the commit gate below would
        # then abort every turn on a disturbance the agent caused itself.
        _reclaim_foreground(runtime, goal, log=log, iteration=iteration)

        # Reuse the last look until the executive schedules PERCEIVE.
        # Bootstrap once so meta is not blind. Post-act / surprise flags are
        # meta signals for that schedule — not a side-channel look.
        # Open reveal episodes (pending unpaid overlay look) must not reuse a
        # stale conversation belief — that skipped menu ingest (live 142848).
        must_executive_look = bool(
            getattr(runtime.execution_state, "must_executive_reperceive", False)
        )
        _rh = getattr(runtime.execution_state, "reveal_handoff", None)
        reveal_episode_pending = (
            isinstance(_rh, dict)
            and bool(str(_rh.get("surface") or "").strip())
            and not bool(_rh.get("failed_reveal"))
            and str(_rh.get("status") or "").strip().lower()
            not in {"failed_reveal", "failed"}
            and (
                bool(_rh.get("incomplete_reveal"))
                or str(_rh.get("status") or "").strip().lower()
                in {"pending_perception", "pending", ""}
            )
        )
        surprise_demands_relook = (
            _last_action_surprised(runtime.execution_state) or must_executive_look
        ) and not reperception_exhausted(runtime.execution_state)
        try:
            if surprise_demands_relook or reveal_episode_pending:
                # Hint only; brain still chooses PERCEIVE via meta.
                runtime.execution_state.perception_mode = "reflect"
        except Exception:
            pass

        if prev_snap_pre is None or reveal_episode_pending:
            snap_pre = refresh_perception(
                runtime,
                goal,
                observe=observe,
                action_label=runtime.execution_state.last_action or "observe",
                log_fn=_perception_log_fn(log, iteration),
                iteration=iteration,
            )
            _log_cycle(
                log,
                iteration=iteration,
                phase=(
                    "perception_bootstrap"
                    if prev_snap_pre is None
                    else "perception_reveal_episode"
                ),
                payload={
                    "reason": (
                        "no prior world; initial look for brain meta"
                        if prev_snap_pre is None
                        else "reveal episode pending — fresh look, no reuse"
                    ),
                    "reveal_episode_pending": reveal_episode_pending,
                    "must_executive_look": must_executive_look,
                },
            )
        else:
            snap_pre = prev_snap_pre
            _log_cycle(
                log,
                iteration=iteration,
                phase="perception_reused",
                payload={
                    "reason": "executive reuses last world until meta PERCEIVE",
                    "must_executive_look": must_executive_look,
                    "surprise_demands_relook": surprise_demands_relook,
                    "last_meta_action": getattr(
                        runtime.execution_state, "last_meta_action", None
                    ),
                },
            )

        observation = snap_pre.observation
        patch = snap_pre.patch
        wv = snap_pre.worldview
        view = snap_pre.view
        feats_pre = snap_pre.features
        assert observation is not None and patch is not None

        # When Terminal/other chrome covers the target app, vision correctly
        # reports desktop_obscured_target / window_management — but there is
        # no AX affordance to click. Recover by forcing the app frontmost and
        # re-observing once before define_action_step.
        if target_app_obscured(feats_pre, view):
            app_name = str(goal.app or runtime.world_model.active_app or "").strip()
            recovered = recover_obscured_target_app(app_name)
            _log_cycle(
                log,
                iteration=iteration,
                phase="focus_recovery",
                payload={
                    "app": app_name,
                    "recovered": recovered,
                    "reason": "target_app_obscured",
                    "screen_type": (_perception_extras(feats_pre).get("perception_summary") or {}).get("screen_type")
                    if isinstance(_perception_extras(feats_pre).get("perception_summary"), dict)
                    else (_perception_extras(feats_pre).get("perception_llm") or {}).get("screen_type"),
                },
                status="ok" if recovered else "warn",
            )
            if recovered:
                _wait(max(settle_s, 0.8), "focus recovery — raise target app")
                snap_pre = refresh_perception(
                    runtime,
                    goal,
                    observe=observe,
                    action_label="focus_recovery",
                    log_fn=_perception_log_fn(log, iteration),
                    iteration=iteration,
                )
                observation = snap_pre.observation
                patch = snap_pre.patch
                wv = snap_pre.worldview
                view = snap_pre.view
                feats_pre = snap_pre.features
                assert observation is not None and patch is not None

        # Setup / login walls (Welcome, Link Device, …) — stop and ASK the user
        # in Hermes instead of burning the step budget on an unusable screen.
        try:
            from plugin.agent.executive.setup_blockers import detect_setup_blocker

            setup_blocker = detect_setup_blocker(
                app=str(getattr(goal, "app", "") or observation.app_name or ""),
                view=view if isinstance(view, dict) else {},
                features=feats_pre,
                observation=observation,
            )
        except Exception:
            setup_blocker = None
        if setup_blocker is not None:
            _log_cycle(
                log,
                iteration=iteration,
                phase="setup_blocker",
                payload={
                    "blocker": setup_blocker.id,
                    "app": setup_blocker.app,
                    "title": setup_blocker.title,
                },
                status="warn",
            )
            return _finish_failure(
                setup_blocker.question,
                setup_blocker.ask_evidence(),
                iterations=iteration,
            )

        _log_cycle(
            log,
            iteration=iteration,
            phase="observation",
            payload={
                "app": observation.app_name,
                "nodes": len(observation.nodes),
                "source": observation.source,
                "phase": "pre_decide",
                "fusion": (observation.meta or {}).get("fusion"),
                "world_id": runtime.execution_state.world_id,
            },
        )
        state_sig = _semantic_state_signature(
            view=view,
            features=feats_pre,
            world_id=runtime.execution_state.world_id,
        )
        runtime.execution_state.note_world_signature(state_sig, None)
        experience.visit(state_sig)
        # Track how long the world has looked identical, independent of the
        # forward-specific observe streak. This feeds the meta-perception gate
        # so a provably static world can skip a redundant re-perceive.
        if prev_state_sig is not None and state_sig == prev_state_sig:
            static_streak += 1
        else:
            static_streak = 0
        semantic_repeat = runtime.execution_state.note_semantic_state(state_sig)
        update_interaction_context(
            runtime.execution_state.interaction_context,
            goal=goal,
            view=view,
            features=feats_pre,
            world_id=runtime.execution_state.world_id,
        )

        if semantic_repeat and (
            runtime.execution_state.world_exploration_needed
            or runtime.execution_state.exploration_branch.active
        ):
            branch_hint = _invalidate_stale_frontier(
                runtime,
                reason="semantic_repeat_replan",
                fallback="observe",
            )
            _log_cycle(
                log,
                iteration=iteration,
                phase="semantic_repeat_replan",
                payload={
                    "semantic_repeat_count": runtime.execution_state.semantic_repeat_count,
                    "state_signature": state_sig,
                    "branch_hint": branch_hint,
                    "branch": runtime.execution_state.exploration_branch.to_dict(),
                },
                status="warn",
            )

        # Storage pressure is a meta/decision housekeeping signal — not a silent
        # side-channel. Record blockers for the meta packet; cleanup runs only
        # when meta/decision names relieve_host_storage (or last-resort below).
        from plugin.agent.capabilities.housekeeping import (
            admissible_housekeeping_capabilities,
            attach_housekeeping_context,
            blockers_from_features,
            is_meta_housekeeping_verb,
        )
        from plugin.agent.runtime.recovery import detect_storage_pressure

        _hk_blockers = blockers_from_features(feats_pre, view=view)
        _obs_texts = [
            getattr(node, "name", "") or getattr(node, "description", "")
            for node in (observation.nodes or [])
        ]
        _feats_for_pressure: Dict[str, Any] = {}
        if isinstance(feats_pre, dict):
            _feats_for_pressure = feats_pre
        elif feats_pre is not None and hasattr(feats_pre, "extras"):
            _ex = getattr(feats_pre, "extras", None) or {}
            if isinstance(_ex, dict):
                _feats_for_pressure = dict(_ex)
                if "perception_llm" in _ex:
                    _feats_for_pressure = {"perception_llm": _ex.get("perception_llm"), **_ex}
        _storage_ev = detect_storage_pressure(
            view=view,
            features=_feats_for_pressure,
            observation_texts=_obs_texts,
            execution_message=str((runtime.execution_state.last_result or {}).get("message") or ""),
        )
        if _storage_ev and not _hk_blockers.get("storage_pressure"):
            _hk_blockers["storage_pressure"] = True
            _hk_blockers["system_warnings"] = list(
                dict.fromkeys(
                    list(_hk_blockers.get("system_warnings") or [])
                    + [str(e)[:120] for e in _storage_ev[:3]]
                )
            )
        # Fold OCR/label lines that carry the app-quoted reclaim amount.
        if _hk_blockers.get("storage_pressure"):
            _hk_blockers["system_warnings"] = list(
                dict.fromkeys(
                    list(_hk_blockers.get("system_warnings") or [])
                    + [
                        str(t)[:120]
                        for t in _obs_texts
                        if t
                        and (
                            "free up" in str(t).lower()
                            or "mb" in str(t).lower()
                            or "storage" in str(t).lower()
                        )
                    ][:4]
                )
            )
        _hk_blockers = attach_housekeeping_context(
            _hk_blockers,
            last_action=str(getattr(runtime.execution_state, "last_action", "") or ""),
            observation_texts=_obs_texts,
        )
        _hk_caps = admissible_housekeeping_capabilities(_hk_blockers)
        runtime.execution_state.last_housekeeping_blockers = _hk_blockers  # type: ignore[attr-defined]
        runtime.execution_state.last_housekeeping_capabilities = _hk_caps  # type: ignore[attr-defined]

        # Forward: suppress identical Observe before define_action_step
        if goal.kind == "whatsapp_forward_message":
            _apply_forward_observe_stagnation(
                runtime,
                state_sig=state_sig,
                entity_count=len(observation.nodes),
                features=feats_pre,
            )
            ft = None
            if feats_pre is not None:
                if hasattr(feats_pre, "extras") and isinstance(feats_pre.extras, dict):
                    ft = feats_pre.extras.get("forward_task")
                    phase = feats_pre.extras.get("forward_phase")
                elif isinstance(feats_pre, dict):
                    ft = (feats_pre.get("extras") or {}).get("forward_task")
                    phase = (feats_pre.get("extras") or {}).get("forward_phase")
                else:
                    phase = None
            else:
                phase = None
            _log_cycle(
                log,
                iteration=iteration,
                phase="forward_task",
                payload={
                    "forward_task": ft,
                    "forward_phase": phase,
                    "suppress_observe": runtime.execution_state.suppress_observe,
                    "identical_observe_streak": runtime.execution_state.identical_observe_streak,
                },
            )

        _log_cycle(
            log,
            iteration=iteration,
            phase="world_patch",
            payload={
                "screen": patch.screen_label,
                "retention": patch.retention,
                "whatsapp_screen": view.get("screen"),
                "search_query": view.get("search_query"),
                "visible_contacts": (view.get("visible_contacts") or [])[:10],
                "open_conversation": view.get("open_conversation"),
                "call_state": view.get("call_state"),
                "worldview_score": patch.worldview_score,
                "search_query_hint": runtime.execution_state.peek_search_query_hint(),
                "phase": "pre_decide",
                "needs_reobserve": bool(getattr(patch, "needs_reobserve", False)),
                "fusion_conflicts": list(getattr(patch, "conflicts", None) or [])[:8],
                "belief_updates": list(getattr(patch, "belief_updates", None) or [])[:8],
                "world_id": runtime.execution_state.world_id,
                "interaction_context": runtime.execution_state.interaction_context.to_dict(),
                "exploration_branch": runtime.execution_state.exploration_branch.to_dict(),
            },
        )

        if getattr(patch, "conflicts", None):
            _log_cycle(
                log,
                iteration=iteration,
                phase="fusion_conflicts",
                payload={
                    "conflicts": list(patch.conflicts)[:16],
                    "needs_reobserve": bool(patch.needs_reobserve),
                    "agreement": (patch.fusion or {}).get("agreement"),
                },
                status="ok",
            )

        # Low retention / worldview / fusion conflict → *advisory* signal into
        # meta. Do NOT set must_executive_reperceive here: that flag is the hard
        # post-act look debt (sanitize forces perceive). Live 094313 re-armed it
        # every frame at retention≈0.34 and trapped meta in perceive forever
        # after a successful ComposeSearchQuery.
        soft_look_hints: list[str] = []
        if patch.retention < retention_floor and runtime.execution_state.iteration > 0:
            soft_look_hints.append("retention_low")
            _log_cycle(
                log,
                iteration=iteration,
                phase="retention_low_signal",
                payload={
                    "retention": patch.retention,
                    "floor": retention_floor,
                    "handling": "meta_signal:advisory_perceive",
                },
                status="warn",
            )

        ref = goal.ensure_reference() if goal.contact else None
        n_hyps = len((ref.search_hypotheses if ref else None) or [goal.contact]) or 1
        hyp_i = int(getattr(runtime.execution_state, "search_hypothesis_index", 0) or 0)
        hyps_left = hyp_i < n_hyps - 1
        needs_reobs = bool(getattr(patch, "needs_reobserve", False)) or bool(
            (patch.worldview_score or {}).get("needs_reobserve")
        )
        if (wv < WORLDVIEW_LOW or needs_reobs) and not hyps_left:
            node_n = len(observation.nodes)
            mean_b = float((patch.worldview_score or {}).get("mean_belief") or 0)
            skip = (not needs_reobs) and node_n >= 80 and mean_b >= 0.7 and wv >= 0.45
            if not skip:
                soft_look_hints.append(
                    "needs_reobserve" if needs_reobs else "worldview_low"
                )
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="worldview_low",
                    payload={
                        "worldview_score": patch.worldview_score,
                        "threshold": WORLDVIEW_LOW,
                        "needs_reobserve": needs_reobs,
                        "handling": "meta_signal:advisory_perceive",
                    },
                    status="fail" if wv < WORLDVIEW_LOW else "ok",
                )
        try:
            runtime.execution_state.perception_soft_signals = soft_look_hints[:6]
        except Exception:
            pass

        # Goal check BEFORE acting — overrides iteration budget when satisfied
        goal_status: GoalStatus = evaluate_goal(goal, runtime.world_model)
        _log_cycle(
            log,
            iteration=iteration,
            phase="goal_status",
            payload={
                "succeeded": goal_status.succeeded,
                "impossible": goal_status.impossible,
                "reason": goal_status.reason,
                "evidence": goal_status.evidence,
            },
            status="ok" if not goal_status.impossible else "fail",
        )
        if goal_status.succeeded:
            _maybe_learn_success(runtime, goal, goal_status)
            return _finish_success(goal_status.evidence, iterations=iteration)
        if goal_status.impossible:
            return _finish_failure(goal_status.reason, goal_status.evidence, iterations=iteration)

        if runtime.execution_state.oscillating():
            return _finish_failure(
                "action/state oscillation detected",
                {"recent": list(runtime.execution_state.recent_action_state_pairs)},
                iterations=iteration,
            )

        # Brain meta first: build features from the current world without
        # running define_action_step()/actuator. Those run only when meta is ACT.
        overlay = get_overlay(goal.app, runtime.world_model)
        feats = overlay.features(runtime.world_model, goal, worldview_score=wv)
        coverage = float(wv or 0.0)
        # Surface change invalidates geometry carried from the prior node.
        try:
            _surf_now = str(
                (view or {}).get("screen")
                or (getattr(runtime.execution_state, "unified_world_document", None) or {}).get("surface")
                or ""
            ).strip().lower()
            # Prefer canonical surface names when present on the world document.
            _doc_surf = str(
                (getattr(runtime.execution_state, "unified_world_document", None) or {}).get("surface")
                or ""
            ).strip().lower()
            if _doc_surf:
                _surf_now = _doc_surf
            if _invalidate_geometry_for_surface_change(
                runtime, surface=_surf_now, reason="accepted_surface_changed"
            ):
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="geometry_invalidated",
                    payload={"surface": _surf_now, "generation": getattr(runtime.execution_state, "geometry_generation", 0)},
                    status="warn",
                )
                has_grounded_action = False
            else:
                has_grounded_action = _actuation_available(runtime, feats)
        except Exception:
            has_grounded_action = _actuation_available(runtime, feats)
        decision = None  # filled only on MetaAction.ACT
        before_world_id = runtime.execution_state.world_id
        before_fp = world_fingerprint(runtime.world_model, view)
        before_view = dict(view)
        before_feats = _feature_dict(runtime, goal, wv)
        runtime.execution_state.decision_frame = iteration

        # --- Brain meta: what tool/capability to run this turn ---
        # Fold this frame's reading into the workspace before judging: the
        # executive must read task state (open conversation, phase, bindings)
        # from the one authoritative record, not from whichever store was last
        # touched. The workspace critic decides what to accept.
        _commit_frame_beliefs(runtime, goal, feats, coverage=coverage)
        # The domain's fresh blocking signal this frame (transient truth): the app
        # overlay's task view (the forward phase machine, demoted to a hint). The
        # executive consumes it exactly like a question — the controller never
        # reads phase names directly.
        domain_blocking: List[str] = []
        observe_hint = getattr(overlay, "observe_blocking_uncertainties", None)
        if callable(observe_hint):
            try:
                for q in observe_hint((feats.extras or {}).get("forward_task")) or []:
                    if q and str(q) not in domain_blocking:
                        domain_blocking.append(str(q))
            except Exception:
                pass
        # The workspace is authoritative over the overlay hint: if it already
        # holds a resolved source-object binding, the source is not an open
        # uncertainty no matter what the derived phase says. This is what demotes
        # the forward phase machine from a source of truth to a hint.
        if "source_object_unresolved" in domain_blocking and has_resolved_binding(
            runtime.execution_state, "source_object"
        ):
            domain_blocking = [q for q in domain_blocking if q != "source_object_unresolved"]
        # Reconcile the QuestionLedger with the domain's current signal, so the
        # ledger is a live record of what the executive is hunting for. New
        # uncertainties are opened as exploration questions (keyed by the question,
        # not the action, so a later re-test of a settled one is visibly
        # redundant); questions the domain no longer flags are answered, so they
        # stop blocking and are not re-searched. ask() is idempotent — it only
        # records new questions and extra test attempts, never reopens a settled
        # one.
        previously_open = set(workspace_blocking_uncertainties(runtime.execution_state))
        for q in domain_blocking:
            open_exploration_question(runtime.execution_state, question=q, kind="where_is")
        for q in previously_open:
            if q not in domain_blocking:
                settle_exploration_question(
                    runtime.execution_state,
                    question=q,
                    answered=True,
                    evidence="no longer flagged by the domain",
                )
        blocking_uncertainties = list(domain_blocking)
        action_surprised = _last_action_surprised(runtime.execution_state)
        awaiting_verification = _awaiting_verification(runtime.execution_state)
        # Repeated no-progress backtracks mean the branch space is exhausted:
        # nothing can be grounded and retreating again cannot help (e.g.
        # perception is starved). Escalate rather than thrash.
        backtrack_exhausted = (
            int(getattr(runtime.execution_state, "consecutive_backtracks", 0) or 0)
            >= _MAX_CONSECUTIVE_BACKTRACKS
        )
        if backtrack_exhausted and blocking_uncertainties:
            # The branch space is spent: every retreat has failed. Abandon the
            # open questions this exploration was testing so the executive stops
            # re-searching them (they drop out of blocking). Meta (LLM) then
            # chooses act / ask_user / broaden — do not pre-seed hard_block.
            for q in blocking_uncertainties:
                settle_exploration_question(
                    runtime.execution_state,
                    question=str(q),
                    answered=False,
                    evidence="branch space exhausted",
                )
        if action_surprised:
            # Record the surprise into the bounded history perception attends to,
            # so the model sees the pattern of recent failures, not just the last.
            _attrib = getattr(runtime.execution_state, "last_attribution", None) or {}
            _ev = _attrib.get("evidence") if isinstance(_attrib.get("evidence"), dict) else {}
            _pred = getattr(runtime.execution_state, "last_prediction_error", None) or {}
            if not isinstance(_pred, dict):
                _pred = {}
            runtime.execution_state.note_surprise(
                {
                    "iteration": iteration,
                    "action": str(getattr(runtime.execution_state, "last_action", "") or ""),
                    "family": str(_attrib.get("action_family") or ""),
                    "effect": str(_attrib.get("effect_kind") or ""),
                    "outcome": str(_attrib.get("outcome") or ""),
                    "failure_domain": str(_attrib.get("likely_failure_domain") or ""),
                    "world_change_score": _ev.get("change_score"),
                    "predicted_surface": _pred.get("predicted_surface"),
                    "observed_surface": _pred.get("observed_surface"),
                    "notes": [str(n) for n in (_attrib.get("notes") or []) if str(n).strip()][:3],
                }
            )
        # The perceptor's own account of what it could not establish this frame,
        # and how much of the surface it actually saw. Sourced from the unified
        # proposal when it ran this frame; otherwise the executive falls back to
        # the worldview coverage and no declared gaps (best-effort, never worse
        # than the old always-full-view assumption).
        perceptor_gaps: List[str] = []
        perceptor_coverage = coverage
        probe_available = False
        _uni = getattr(runtime.execution_state, "last_unified_proposal", None)
        if isinstance(_uni, dict) and int(_uni.get("frame", -1)) == iteration:
            perceptor_gaps = [str(g) for g in (_uni.get("evidence_gaps") or []) if str(g).strip()]
            probe_available = bool(_uni.get("probe_available"))
            if _uni.get("coverage") is not None:
                try:
                    perceptor_coverage = float(_uni.get("coverage"))
                except (TypeError, ValueError):
                    perceptor_coverage = coverage
        # Ambiguity is the THINK trigger: an unresolved contradiction in the
        # workspace, or being genuinely stuck (no grounded move, a look would not
        # help, and the branch is not yet stale enough to backtrack). Consulting
        # the reasoning model is the right move there, not another blind look.
        _ws_now = workspace_of(runtime.execution_state)
        contradiction_count = 0
        if _ws_now is not None:
            try:
                contradiction_count = len(_ws_now.unresolved_contradictions)
            except Exception:
                contradiction_count = 0
        # "Stuck" is for THINK only when looking would not help. Missing
        # geometry with observe_has_value still true is a PERCEIVE case.
        observe_still_helps = True
        _uni_for_stuck = getattr(runtime.execution_state, "last_unified_proposal", None)
        if isinstance(_uni_for_stuck, dict) and _uni_for_stuck.get("next_action"):
            observe_still_helps = False
        stuck_without_route = (
            not has_grounded_action
            and not action_surprised
            and not blocking_uncertainties
            and not backtrack_exhausted
            and not observe_still_helps
        )
        ambiguous = contradiction_count > 0 or stuck_without_route
        steps_remaining = max(0, step_budget - iteration + 1)
        # Consult the goal contract: what "done" means and what must hold. When
        # every success condition is met the executive verifies completion (ladder
        # rung 0) rather than trusting a single grounded move — the executive, not
        # a submodule, owns the completion judgement.
        contract = contract_status(runtime.execution_state)
        contract_complete = bool(contract.get("all_satisfied"))

        # --- Executability gate (before normal meta toward the parent goal) ---
        # Warning ≠ Blocker ≠ Precondition. Production path lives in
        # executability_gate.run_executability_gate (also driven by L3 evals).
        _skip_normal_meta = False
        meta = None  # type: ignore[assignment]
        sufficiency = None
        try:
            from plugin.agent.executive.executability_gate import (
                run_executability_gate,
            )

            _obs_for_block = [
                getattr(node, "name", "") or getattr(node, "description", "")
                for node in (observation.nodes or [])
            ]
            _gate = run_executability_gate(
                runtime.execution_state,
                observation_texts=_obs_for_block,
                view=view if isinstance(view, dict) else {},
                features=feats,
                app=str(goal.app or ""),
                goal_kind=str(getattr(goal, "kind", "") or "goal"),
                iteration=iteration,
            )
            _skip_normal_meta = bool(_gate.skip_normal_meta)
            if _gate.meta is not None:
                meta = _gate.meta
            if _gate.phase:
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase=_gate.phase,
                    payload=_gate.to_dict(),
                    status="ok" if _gate.phase != "executability" or (
                        _gate.assessment or {}
                    ).get("status") == "executable" else "warn",
                )
        except Exception as _exec_exc:
            logger.debug("executability gate skipped: %s", _exec_exc)
            _skip_normal_meta = False
            meta = None  # type: ignore[assignment]

        # Streak counters on execution_state are meta inputs (read inside
        # assess_executive_judgement). Do not rewrite meta.action to ACT here —
        # the executive alone chooses every MetaAction (except the explicit
        # prerequisite interruption above).
        if not _skip_normal_meta or meta is None:
            sufficiency, meta = assess_executive_judgement(
                runtime.execution_state,
                blocking_uncertainties=blocking_uncertainties,
                evidence_gaps=perceptor_gaps,
                coverage=perceptor_coverage,
                has_grounded_action=has_grounded_action,
                previously_suppressed=prev_meta_suppress,
                last_action_surprised=action_surprised,
                awaiting_verification=awaiting_verification,
                probe_available=probe_available,
                ambiguous=ambiguous,
                steps_remaining=steps_remaining,
                goal_complete=contract_complete,
                blockers=dict(
                    getattr(
                        runtime.execution_state, "last_housekeeping_blockers", None
                    )
                    or {}
                ),
                housekeeping_capabilities=list(
                    getattr(
                        runtime.execution_state,
                        "last_housekeeping_capabilities",
                        None,
                    )
                    or []
                ),
            )
        beliefs_payload: Dict[str, Any] = {}
        _ws = workspace_of(runtime.execution_state)
        if _ws is not None:
            try:
                beliefs_payload = {
                    "facts": {k: c.value for k, c in (_ws.facts or {}).items()},
                    "belief_flips": int(_ws.belief_flips or 0),
                    "contradictions": [
                        c.to_dict() if hasattr(c, "to_dict") else str(c)
                        for c in (_ws.unresolved_contradictions or [])
                    ][:8],
                }
            except Exception:
                beliefs_payload = {}
        _log_cycle(
            log,
            iteration=iteration,
            phase="executive_judgement",
            payload={
                "sufficiency": (
                    sufficiency.to_dict()
                    if sufficiency is not None and hasattr(sufficiency, "to_dict")
                    else None
                ),
                "meta_action": meta.to_dict(),
                "cognitive_mode": getattr(runtime.execution_state, "last_cognitive_mode", None),
                "mode_triggers": getattr(runtime.execution_state, "last_mode_triggers", None),
                "perception_query": getattr(runtime.execution_state, "last_perception_query", None),
                "meta_perception_enabled": meta_perception_enabled,
                "coverage": round(perceptor_coverage, 3),
                "worldview_coverage": round(coverage, 3),
                "perceptor_evidence_gaps": perceptor_gaps[:6],
                "has_grounded_action": has_grounded_action,
                "last_action_surprised": action_surprised,
                "awaiting_verification": awaiting_verification,
                "post_action_look_owed": bool(
                    getattr(runtime.execution_state, "post_action_reperceive_pending", False)
                    or getattr(runtime.execution_state, "must_executive_reperceive", False)
                ),
                "blocking_uncertainties": [str(q) for q in blocking_uncertainties][:8],
                "static_streak": static_streak,
                "beliefs": beliefs_payload,
                "goal_contract": {
                    "satisfied": [str(s) for s in (contract.get("satisfied") or [])],
                    "pending": [str(s) for s in (contract.get("pending") or [])],
                    "constraints": [str(c) for c in (contract.get("constraints") or [])],
                    "all_satisfied": contract_complete,
                },
                # Streak budgets — required to reconstruct unique meta situations.
                "streaks": {
                    "surprise_relooks": int(
                        getattr(runtime.execution_state, "consecutive_surprise_relooks", 0) or 0
                    ),
                    "perceives": int(
                        getattr(runtime.execution_state, "consecutive_perceives", 0) or 0
                    ),
                    "thinks": int(
                        getattr(runtime.execution_state, "consecutive_thinks", 0) or 0
                    ),
                    "probes": int(
                        getattr(runtime.execution_state, "consecutive_probes", 0) or 0
                    ),
                    "backtracks": int(
                        getattr(runtime.execution_state, "consecutive_backtracks", 0) or 0
                    ),
                    "information_gathering": int(
                        getattr(
                            runtime.execution_state,
                            "consecutive_information_gathering",
                            0,
                        )
                        or 0
                    ),
                },
            },
        )
        prev_meta_suppress = bool(getattr(meta, "suppress_observe", False))
        prev_static_streak = static_streak
        prev_snap_pre = snap_pre
        prev_state_sig = state_sig

        # Route by cognitive mode, don't just log it. A deliberative frame (new
        # goal, ambiguity, an exhausted branch, an approaching irreversible
        # commit, a contradiction, a surprise, or no matching procedure) should
        # run the strong enumerate/score/consult reasoner next frame rather than
        # the multimodal fast path; a reactive frame (clear intention, grounded
        # low-risk move, known transition) keeps the fast path. This is the
        # design's two-mode executive expressed as the fast-path gate the deep
        # path already honours via force_deliberation. THINK/EXPLORE set the same
        # flag for their own reasons; setting it here is idempotent.
        if (
            meta_perception_enabled
            and getattr(runtime.execution_state, "last_cognitive_mode", "") == _DELIBERATIVE
            and meta.action not in _META_PREEMPTS
        ):
            runtime.execution_state.force_deliberation = True

        # --- Meta-action as a real loop phase ---
        if meta_perception_enabled and meta.action in _META_PREEMPTS:
            _log_cycle(
                log,
                iteration=iteration,
                phase="meta_action_phase",
                payload={"meta_action": meta.to_dict(), "handling": meta.action.value},
                status="warn",
            )
            if meta.action == MetaAction.ASK:
                # Prefer a Hermes WAITING_FOR_USER turn over a silent hard-fail.
                ask_question = (
                    "I can’t make further progress on my own from this screen. "
                    "Please adjust the app so the normal UI is available, then reply **done**."
                )
                try:
                    from plugin.agent.executive.setup_blockers import (
                        DESKTOP_APP_READY_PRECONDITION,
                        USER_SETUP_BLOCKER_KIND,
                        detect_setup_blocker,
                    )

                    late_blocker = detect_setup_blocker(
                        app=str(getattr(goal, "app", "") or ""),
                        view=view if isinstance(view, dict) else {},
                        features=feats_pre,
                        observation=observation,
                    )
                    if late_blocker is not None:
                        return _finish_failure(
                            late_blocker.question,
                            {
                                **late_blocker.ask_evidence(),
                                "meta_action": meta.to_dict(),
                                "consecutive_backtracks": int(
                                    getattr(
                                        runtime.execution_state,
                                        "consecutive_backtracks",
                                        0,
                                    )
                                    or 0
                                ),
                            },
                            iterations=iteration,
                        )
                    app_label = str(getattr(goal, "app", "") or "the app").strip() or "the app"
                    ask_question = (
                        f"I’m stuck and need your help with {app_label}. "
                        "Adjust the app so I can continue, then reply **done**."
                    )
                    return _finish_failure(
                        ask_question,
                        {
                            "fallback": "ask_prerequisite",
                            "ask_precondition": DESKTOP_APP_READY_PRECONDITION,
                            "ask_question": ask_question,
                            "ui_hints": {
                                "kind": USER_SETUP_BLOCKER_KIND,
                                "blocker": "executive_ask",
                                "app": app_label,
                                "title": f"Need your help with {app_label}",
                                "body": ask_question,
                                "cta": "Reply **done** when ready",
                            },
                            "meta_action": meta.to_dict(),
                            "consecutive_backtracks": int(
                                getattr(
                                    runtime.execution_state, "consecutive_backtracks", 0
                                )
                                or 0
                            ),
                            "blocking_uncertainties": [
                                str(q) for q in blocking_uncertainties
                            ][:8],
                        },
                        iterations=iteration,
                    )
                except Exception:
                    return _finish_failure(
                        ask_question,
                        {
                            "fallback": "ask_prerequisite",
                            "ask_precondition": "desktop_app_ready",
                            "ask_question": ask_question,
                            "meta_action": meta.to_dict(),
                        },
                        iterations=iteration,
                    )
            if meta.action == MetaAction.DELEGATE:
                return _finish_failure(
                    "executive delegate runtime not configured: escalate instead",
                    {
                        "meta_action": meta.to_dict(),
                        "app_view": view,
                        "blocking_uncertainties": [str(q) for q in blocking_uncertainties][:8],
                    },
                    iterations=iteration,
                )

        if meta_perception_enabled and meta.action == MetaAction.WAIT:
            _log_cycle(
                log,
                iteration=iteration,
                phase="meta_wait",
                payload={"meta_action": meta.to_dict()},
            )
            _wait(max(settle_s, 1.0), "executive wait")
            continue

        # --- THINK: bounded deliberation; replan when search retreat or branch stale ---
        if meta_perception_enabled and meta.action == MetaAction.THINK:
            runtime.execution_state.consecutive_backtracks = 0
            runtime.execution_state.consecutive_probes = 0
            think_n = int(getattr(runtime.execution_state, "consecutive_thinks", 0) or 0) + 1
            runtime.execution_state.consecutive_thinks = think_n
            branch_stale = (
                prev_meta_suppress
                or static_streak >= 2
                or reperception_exhausted(runtime.execution_state)
            )
            retreat_or_stale = bool(
                getattr(runtime.execution_state, "search_retreat_owed", False)
            ) or branch_stale
            if retreat_or_stale and think_n <= _MAX_CONSECUTIVE_THINKS:
                _clear_search_retreat_state(
                    runtime.execution_state, why="think_after_failed_search"
                )
                branch_hint = _run_think_replan(
                    runtime,
                    goal,
                    observe=observe,
                    feats=feats,
                    overlay=overlay,
                    log=log,
                    iteration=iteration,
                )
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="meta_think_replan",
                    payload={
                        "meta_action": meta.to_dict(),
                        "branch_hint": branch_hint,
                        "retreat_or_stale": retreat_or_stale,
                        "consecutive_information_gathering": int(
                            getattr(
                                runtime.execution_state,
                                "consecutive_information_gathering",
                                0,
                            )
                            or 0
                        ),
                    },
                    status="warn",
                )
            if think_n <= _MAX_CONSECUTIVE_THINKS:
                runtime.execution_state.force_deliberation = True
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="meta_think",
                    payload={"meta_action": meta.to_dict(), "consecutive_thinks": think_n},
                )
                prev_meta_suppress = False
                _wait(settle_s, "executive think")
                continue
            _log_cycle(
                log,
                iteration=iteration,
                phase="meta_think",
                payload={
                    "meta_action": meta.to_dict(),
                    "consecutive_thinks": think_n,
                    "handling": "think_exhausted_redecide",
                },
                status="warn",
            )
            prev_meta_suppress = False
            _wait(settle_s, "executive think exhausted")
            continue

        # Any non-preempting frame (we are about to observe/act normally) breaks a
        # retreat / think run: the branch is no longer being retreated.
        # PERCEIVE streak is managed below (look vs redecide when budget spent).
        # EXPLORE actuates reveal stages (like SEARCH) — do not clear its streak here.
        if meta.action not in {MetaAction.PERCEIVE, MetaAction.EXPLORE, MetaAction.SEARCH}:
            runtime.execution_state.consecutive_backtracks = 0
            runtime.execution_state.consecutive_information_gathering = 0
            runtime.execution_state.consecutive_thinks = 0
            runtime.execution_state.consecutive_probes = 0
            runtime.execution_state.consecutive_perceives = 0

        # --- PERCEIVE: bounded looks, then ACT to bind geometry via define_action ---
        if meta.action == MetaAction.PERCEIVE:
            look_owed = _awaiting_verification(runtime.execution_state)
            perceive_n = int(
                getattr(runtime.execution_state, "consecutive_perceives", 0) or 0
            ) + 1
            if look_owed:
                perceive_n = 1
            runtime.execution_state.consecutive_perceives = perceive_n
            if perceive_n <= _MAX_CONSECUTIVE_PERCEIVES or look_owed:
                try:
                    runtime.execution_state.perception_mode = "perceive"
                except Exception:
                    pass
                surprise_look = bool(surprise_demands_relook or action_surprised)
                if surprise_look:
                    runtime.execution_state.consecutive_surprise_relooks = (
                        int(
                            getattr(
                                runtime.execution_state, "consecutive_surprise_relooks", 0
                            )
                            or 0
                        )
                        + 1
                    )
                    _consume_surprise(runtime.execution_state)
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="meta_action_phase",
                    payload={
                        "meta_action": meta.to_dict(),
                        "handling": "brain_tool:perceive",
                        "consecutive_perceives": perceive_n,
                        "look_owed": look_owed,
                        "surprise_look": surprise_look,
                    },
                )
                snap_pre = refresh_perception(
                    runtime,
                    goal,
                    observe=observe,
                    action_label="meta_perceive",
                    log_fn=_perception_log_fn(log, iteration),
                    iteration=iteration,
                )
                try:
                    look_feats = overlay.features(
                        runtime.world_model, goal, worldview_score=snap_pre.worldview
                    )
                except Exception:
                    look_feats = feats
                multimodal_ok = _multimodal_look(
                    runtime, goal, features=look_feats, mode="perceive"
                )
                still_owed = _awaiting_verification(runtime.execution_state)
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="brain_tool_look",
                    payload={
                        "mode": "perceive",
                        "multimodal": multimodal_ok,
                        "meta": "perceive",
                        "consecutive_perceives": perceive_n,
                        "look_owed": look_owed,
                        "still_owed": still_owed,
                    },
                )
                # Do not clear the post-act owe here — _multimodal_look clears it
                # only when stage1 was fresh. Failed/phash looks keep the owe.
                prev_meta_suppress = False
                prev_static_streak = static_streak
                prev_snap_pre = snap_pre
                prev_state_sig = state_sig
                _wait(settle_s, "executive perceive")
                continue
            # Look still owed: keep perceiving; never actuate without MetaAction.ACT.
            if _awaiting_verification(runtime.execution_state):
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="meta_action_phase",
                    payload={
                        "meta_action": meta.to_dict(),
                        "consecutive_perceives": perceive_n,
                        "handling": "perceive_owed_no_act_fallthrough",
                    },
                    status="warn",
                )
                runtime.execution_state.consecutive_perceives = 0
                prev_meta_suppress = False
                prev_static_streak = static_streak
                prev_snap_pre = None
                prev_state_sig = state_sig
                _wait(settle_s, "executive perceive owed")
                continue
            # Streak spent: leave counter high so next judgement sees
            # perceive_streak_exhausted and may choose ACT — do not actuate here.
            _log_cycle(
                log,
                iteration=iteration,
                phase="meta_action_phase",
                payload={
                    "meta_action": meta.to_dict(),
                    "consecutive_perceives": perceive_n,
                    "handling": "perceive_exhausted_redecide",
                },
                status="warn",
            )
            prev_meta_suppress = False
            prev_static_streak = static_streak
            prev_snap_pre = snap_pre
            prev_state_sig = state_sig
            _wait(settle_s, "executive perceive exhausted")
            continue

        # --- ACT (or exhausted THINK/PERCEIVE fall-through) ---
        # Executive cycle: act → result → re-perceive → decide. While the
        # post-act look is unpaid, do not run define_action / motor — including
        # PERCEIVE fallthrough. Never clear the debt to "unblock" ACT (live
        # 033711). Surprise-relook exhaustion alone must not gate actuation
        # here; that is handled by meta after the look is paid.
        if _post_action_look_unpaid(runtime.execution_state):
            _log_cycle(
                log,
                iteration=iteration,
                phase="meta_action_phase",
                payload={
                    "meta_action": meta.to_dict(),
                    "handling": "act_blocked_post_act_look_unpaid",
                    "post_action_reperceive_pending": bool(
                        getattr(
                            runtime.execution_state,
                            "post_action_reperceive_pending",
                            False,
                        )
                    ),
                    "must_executive_reperceive": bool(
                        getattr(
                            runtime.execution_state,
                            "must_executive_reperceive",
                            False,
                        )
                    ),
                },
                status="warn",
            )
            prev_meta_suppress = False
            prev_static_streak = static_streak
            prev_snap_pre = None
            prev_state_sig = state_sig
            _wait(settle_s, "act blocked; post-act look unpaid")
            continue
        # ACT commits; SEARCH actuates find-stage capabilities only. No silent
        # fallthrough from THINK/PERCEIVE — those redecide when spent.
        may_actuate = bool(getattr(meta, "may_actuate", False)) or (
            meta.action is MetaAction.ACT
        )
        if not may_actuate:
            # Last-resort: if storage pressure persists and meta keeps skipping
            # offered housekeeping, run relieve once as a named capability call
            # (not a nameless side-channel).
            _blockers_now = dict(
                getattr(runtime.execution_state, "last_housekeeping_blockers", None) or {}
            )
            _ignore_n = int(
                getattr(runtime.execution_state, "housekeeping_ignore_streak", 0) or 0
            )
            if _blockers_now.get("storage_pressure"):
                runtime.execution_state.housekeeping_ignore_streak = _ignore_n + 1  # type: ignore[attr-defined]
            else:
                runtime.execution_state.housekeeping_ignore_streak = 0  # type: ignore[attr-defined]
            if (
                _blockers_now.get("storage_pressure")
                and int(getattr(runtime.execution_state, "housekeeping_ignore_streak", 0) or 0)
                >= 2
            ):
                from plugin.agent.capabilities.base import CapabilityRequest
                from plugin.agent.capabilities.dispatch import dispatch

                try:
                    _lr_feats = _feature_dict(runtime, goal, wv)
                except Exception:
                    _lr_feats = dict(_feats_for_pressure)
                _hk_outcome = dispatch(
                    CapabilityRequest(
                        name="relieve_host_storage",
                        app=str(goal.app or "WhatsApp"),
                        extras={
                            "view": view,
                            "features": _lr_feats,
                            "observation_texts": _obs_texts,
                            "reason": "last_resort_storage_pressure",
                        },
                    ),
                    get_overlay(goal.app, runtime.world_model),
                )
                runtime.execution_state.housekeeping_ignore_streak = 0  # type: ignore[attr-defined]
                runtime.execution_state.last_action = "relieve_host_storage"
                runtime.execution_state.last_housekeeping_evidence = dict(  # type: ignore[attr-defined]
                    _hk_outcome.evidence or {}
                )
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="housekeeping_act",
                    payload={
                        "capability": "relieve_host_storage",
                        "source": "last_resort",
                        "outcome": {
                            "ok": _hk_outcome.ok,
                            "message": _hk_outcome.message,
                            "evidence": dict(_hk_outcome.evidence or {}),
                        },
                    },
                    status="ok" if _hk_outcome.ok else "warn",
                )
                _wait(max(settle_s, 0.4), "last-resort housekeeping")
                continue
            _log_cycle(
                log,
                iteration=iteration,
                phase="meta_action_phase",
                payload={
                    "meta_action": meta.to_dict(),
                    "handling": "no_actuation_this_turn",
                },
                status="warn",
            )
            prev_meta_suppress = bool(getattr(meta, "suppress_observe", False))
            prev_static_streak = static_streak
            prev_snap_pre = snap_pre
            prev_state_sig = state_sig
            _wait(settle_s, f"executive {meta.action.value}")
            continue

        # Meta-named housekeeping capability: dispatch without goal decision.
        _meta_cap = str(getattr(meta, "capability", "") or "").strip().lower()
        if _meta_cap and is_meta_housekeeping_verb(_meta_cap):
            from plugin.agent.capabilities.base import CapabilityRequest
            from plugin.agent.capabilities.dispatch import dispatch

            _hk_extras: Dict[str, Any] = {
                "view": view,
                "observation_texts": _obs_texts,
                "reason": str(meta.reason or "meta housekeeping"),
                "world": runtime.world_model,
                "dialogs": list(
                    (getattr(feats_pre, "extras", {}) or {}).get("dialogs") or []
                )
                if feats_pre is not None
                else list((view or {}).get("dialogs") or []),
            }
            try:
                _hk_extras["features"] = _feature_dict(runtime, goal, wv)
            except Exception:
                _hk_extras["features"] = {}
            _hk_outcome = dispatch(
                CapabilityRequest(
                    name=_meta_cap,
                    app=str(goal.app or "WhatsApp"),
                    extras=_hk_extras,
                ),
                get_overlay(goal.app, runtime.world_model),
            )
            runtime.execution_state.housekeeping_ignore_streak = 0  # type: ignore[attr-defined]
            runtime.execution_state.last_action = _meta_cap
            runtime.execution_state.last_housekeeping_evidence = dict(  # type: ignore[attr-defined]
                _hk_outcome.evidence or {}
            )
            _log_cycle(
                log,
                iteration=iteration,
                phase="housekeeping_act",
                payload={
                    "meta_action": meta.to_dict(),
                    "capability": _meta_cap,
                    "source": "meta",
                    "outcome": {
                        "ok": _hk_outcome.ok,
                        "message": _hk_outcome.message,
                        "evidence": dict(_hk_outcome.evidence or {}),
                    },
                },
                status="ok" if _hk_outcome.ok else "warn",
            )
            prev_meta_suppress = bool(getattr(meta, "suppress_observe", False))
            prev_static_streak = static_streak
            prev_snap_pre = snap_pre
            prev_state_sig = state_sig
            _wait(max(settle_s, 0.4), f"housekeeping {_meta_cap}")
            continue

        if meta.action is MetaAction.SEARCH:
            runtime.execution_state.consecutive_backtracks = 0
            runtime.execution_state.consecutive_information_gathering = 0
            runtime.execution_state.consecutive_thinks = 0
            runtime.execution_state.consecutive_probes = 0
            runtime.execution_state.consecutive_perceives = 0
            search_n = int(
                getattr(runtime.execution_state, "consecutive_searches", 0) or 0
            ) + 1
            runtime.execution_state.consecutive_searches = search_n
            if search_n > _MAX_CONSECUTIVE_SEARCHES:
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="meta_search",
                    payload={
                        "meta_action": meta.to_dict(),
                        "consecutive_searches": search_n,
                        "handling": "search_exhausted_redecide",
                    },
                    status="warn",
                )
                prev_meta_suppress = False
                _wait(settle_s, "executive search exhausted")
                continue
        elif meta.action is MetaAction.EXPLORE:
            search_failed = str(
                (getattr(runtime.execution_state, "search_episode", None) or {}).get(
                    "status"
                )
                or ""
            ) == "failed"
            retreat_owed = bool(
                getattr(runtime.execution_state, "search_retreat_owed", False)
            ) or search_failed
            if retreat_owed:
                revert_outcome, branch_hint = _run_explore_revert(runtime, goal)
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="meta_explore_retreat",
                    payload={
                        "meta_action": meta.to_dict(),
                        "branch_hint": branch_hint,
                        "revert_effects": {
                            "ok": bool(getattr(revert_outcome, "ok", False)),
                            "message": str(getattr(revert_outcome, "message", "") or "")[
                                :200
                            ],
                            "realization": str(
                                getattr(revert_outcome, "realization", "") or ""
                            ),
                        },
                    },
                    status="warn",
                )
            runtime.execution_state.consecutive_backtracks = 0
            runtime.execution_state.consecutive_information_gathering = 0
            runtime.execution_state.consecutive_thinks = 0
            runtime.execution_state.consecutive_searches = 0
            runtime.execution_state.consecutive_perceives = 0
            probe_n = int(
                getattr(runtime.execution_state, "consecutive_probes", 0) or 0
            ) + 1
            runtime.execution_state.consecutive_probes = probe_n
            if probe_n > _MAX_CONSECUTIVE_PROBES:
                stance = str(
                    getattr(runtime.execution_state, "last_affordance_stance", "") or ""
                ).strip().lower()
                grounded_n = len(
                    list(
                        getattr(
                            runtime.execution_state,
                            "last_grounded_affordance_set",
                            None,
                        )
                        or []
                    )
                )
                handoff = getattr(runtime.execution_state, "reveal_handoff", None)
                reveal_failed = isinstance(handoff, dict) and (
                    bool(handoff.get("failed_reveal"))
                    or str(handoff.get("status") or "").strip().lower()
                    in {"failed_reveal", "failed"}
                )
                # Probe budget spent: always leave EXPLORE — ACT with escalated
                # route (or act_clear commit). Never explore_exhausted_redecide
                # with sticky incomplete debt (live 142848).
                handling = (
                    "explore_exhausted_act_clear"
                    if stance == "act_clear" or grounded_n > 0
                    else "explore_exhausted_act_escalate"
                )
                meta = MetaChoice(
                    MetaAction.ACT,
                    (
                        "explore exhausted — goal act clear, commit"
                        if handling == "explore_exhausted_act_clear"
                        else "explore exhausted — act escalated route, do not re-explore"
                    ),
                    {
                        "act": 1.0,
                        handling: 1.0,
                        "grounded_n": float(grounded_n),
                        "reveal_episode_failed": 1.0 if reveal_failed else 0.0,
                    },
                )
                runtime.execution_state.consecutive_probes = 0
                # Mark episode terminal so sync cannot re-seed route debt.
                if isinstance(handoff, dict) and not reveal_failed:
                    try:
                        runtime.execution_state.reveal_handoff = {
                            **dict(handoff),
                            "failed_reveal": True,
                            "status": "failed_reveal",
                            "incomplete_reveal": False,
                        }
                    except Exception:
                        pass
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="meta_explore",
                    payload={
                        "meta_action": meta.to_dict(),
                        "consecutive_probes": probe_n,
                        "handling": handling,
                        "affordance_stance": stance,
                        "grounded_n": grounded_n,
                    },
                    status="warn",
                )
        else:
            runtime.execution_state.consecutive_searches = 0

        _log_cycle(
            log,
            iteration=iteration,
            phase="meta_action_phase",
            payload={
                "meta_action": meta.to_dict(),
                "handling": (
                    "brain_tool:search"
                    if meta.action is MetaAction.SEARCH
                    else (
                        "brain_tool:explore"
                        if meta.action is MetaAction.EXPLORE
                        else "brain_tool:act"
                    )
                ),
                "consecutive_searches": int(
                    getattr(runtime.execution_state, "consecutive_searches", 0) or 0
                ),
                "consecutive_probes": int(
                    getattr(runtime.execution_state, "consecutive_probes", 0) or 0
                ),
            },
        )
        runtime.execution_state.decision_frame = iteration
        # Brain capability: define how to act (perceptor evidence + consultation),
        # then hand a complete Action to the actor.
        decision = eng.define_action_step(
            goal,
            runtime.world_model,
            runtime.execution_state,
            worldview_score=wv,
            state_signature=state_sig,
            state_experience=experience,
        )
        # Do not clear must_executive_reperceive / post_action_reperceive_pending
        # here. Only a fresh multimodal look clears the post-act owe; clearing
        # before ACT allowed perceive→fallthrough onto pre-act geometry.
        overlay = get_overlay(goal.app, runtime.world_model)
        feats = overlay.features(runtime.world_model, goal, worldview_score=wv)
        before_world_id = runtime.execution_state.world_id
        before_fp = world_fingerprint(runtime.world_model, view)
        before_view = dict(view)
        before_feats = _feature_dict(runtime, goal, wv)

        # Low resolution confidence: observe to refine; ask only after attempts
        policy = str(feats.extras.get("resolution_policy") or "")
        if (
            feats.extras.get("needs_confirmation")
            and feats.query_matches_goal
            and policy == "ask"
        ):
            amb_count = int(getattr(runtime.execution_state, "ambiguous_observe_count", 0) or 0) + 1
            runtime.execution_state.ambiguous_observe_count = amb_count  # type: ignore[attr-defined]
            cands = feats.extras.get("contact_candidates") or []
            _log_cycle(
                log,
                iteration=iteration,
                phase="contact_low_confidence",
                payload={
                    "candidates": cands,
                    "contact": goal.contact,
                    "count": amb_count,
                    "confidence": feats.extras.get("resolution_confidence"),
                    "policy": policy,
                },
                status="fail" if amb_count >= 3 else "ok",
            )
            if amb_count >= 3:
                return _finish_failure(
                    f"low confidence for {goal.contact!r} — confirm exact name",
                    {
                        "candidates": cands,
                        "needs_confirmation": True,
                        "resolution_confidence": feats.extras.get("resolution_confidence"),
                        "app_view": view,
                    },
                    iterations=iteration,
                )
        elif policy == "auto":
            runtime.execution_state.ambiguous_observe_count = 0  # type: ignore[attr-defined]

        # The completed perception, in prose, immediately before the decision it
        # produced. Without this a run log records what the agent *did* with no
        # account of what it understood, which is the first thing anyone
        # diagnosing a wrong move needs. Written by the critic (perception's last
        # stage), so it reflects the accepted document rather than the raw
        # proposal.
        # Prediction against outcome, as its own line in the run. A developer
        # reading a wrong move needs to see what the agent thought would happen
        # before seeing what it did next; previously the prediction existed only
        # inside a decision trace and its scoring nowhere at all.
        pred_error = getattr(runtime.execution_state, "last_prediction_error", None)
        if isinstance(pred_error, dict) and pred_error:
            mismatched = pred_error.get("matched") is False
            # Mechanism follows effect judgment, not meta surprise latch.
            effect_absent = _effect_was_absent(runtime.execution_state) or mismatched
            _log_cycle(
                log,
                iteration=iteration,
                phase="prediction_error" if mismatched else "prediction_held",
                payload={
                    "message": str(pred_error.get("verdict") or ""),
                    "detail": str(pred_error.get("verdict") or ""),
                    **{k: v for k, v in pred_error.items() if k != "verdict"},
                },
                status="warn" if mismatched else "ok",
            )
            # Motor reported ok but the world did not match the prediction
            # (e.g. reveal_actions → still conversation). Record the failed
            # latch so ACT cannot re-issue the same family+point, and reverse
            # the provisional reliability credit taken at gesture time.
            # Runs even when meta surprise was consumed (suppressed_rearm).
            if effect_absent:
                step = getattr(runtime.execution_state, "last_plan_step", None)
                # Causal attribution: close the attempt that made the prediction.
                # A later PERCEIVE/observe must not become the blamed family.
                fam = str(
                    pred_error.get("action_family")
                    or pred_error.get("family")
                    or pred_error.get("capability")
                    or getattr(
                        runtime.execution_state, "last_act_family", None
                    )
                    or ""
                ).strip().lower()
                if fam in {"observe", "perception", "perceive", "look", ""}:
                    fam = str(
                        getattr(step, "action_family", "")
                        or getattr(runtime.execution_state, "last_action", "")
                        or pred_error.get("expected_capability")
                        or ""
                    ).strip().lower()
                if fam in {"observe", "perception", "perceive", "look"}:
                    fam = str(
                        getattr(
                            runtime.execution_state, "last_instrumental_family", ""
                        )
                        or ""
                    ).strip().lower()
                # Prefer Action.attempt_id; do not invent ambient attribution here.
                attempt_id = str(getattr(step, "attempt_id", "") or "").strip()
                _note_failed_motor(
                    runtime,
                    family=fam,
                    target=str(
                        pred_error.get("target")
                        or getattr(step, "semantic_target", "")
                        or ""
                    ),
                    point=getattr(step, "target_point", None) if step is not None else None,
                )
                if attempt_id:
                    try:
                        runtime.execution_state.last_effect_attempt_id = attempt_id
                    except Exception:
                        pass
                reveal_esc: Dict[str, Any] = {}
                if fam in {
                    "reveal_actions",
                    "revealactions",
                    "right_click",
                    "context_click",
                }:
                    # Even when reflect later coerces matched=True, the first
                    # overlay miss must rotate the reveal motor (153213).
                    try:
                        from plugin.agent.capabilities.reveal_actions import (
                            escalate_failed_reveal,
                        )

                        reveal_esc = escalate_failed_reveal(
                            runtime.execution_state,
                            target=str(
                                getattr(step, "semantic_target", "") or ""
                            ),
                            point=(
                                getattr(step, "target_point", None)
                                if step is not None
                                else None
                            ),
                            last_gesture=str(
                                getattr(
                                    runtime.execution_state, "reveal_probe_mode", ""
                                )
                                or "context_click"
                            ),
                        )
                    except Exception:
                        reveal_esc = {}
                if step is not None:
                    _observe_capability_reliability(step, False)
                runtime.execution_state.must_executive_reperceive = True
                open_repair = {}
                referent_mismatch: Dict[str, Any] = {}
                commitment_recovery: Dict[str, Any] = {}
                if step is not None and fam in {"open_entity", "open_contact"}:
                    # Motor ok + wrong/unsettled semantic effect. Typed content
                    # navigation → settle debt; container open → REFERENT_MISMATCH.
                    handled = _handle_open_entity_effect_absent(
                        runtime,
                        step,
                        fam=fam,
                        pred_error=pred_error,
                    )
                    open_repair = dict(handled.get("open_repair") or {})
                    referent_mismatch = dict(handled.get("referent_mismatch") or {})
                # Generic commitment path: evidence-based GROUNDING only.
                # Effect absence alone does not force grounding class.
                if fam in {
                    "invoke_affordance",
                    "commit_irreversible",
                } or str(getattr(step, "semantic_target", "") or "").strip():
                    try:
                        from plugin.agent.executive.affordance_commitment import (
                            handle_failed_committed_action,
                        )
                        from plugin.agent.executive.intention_frame import (
                            AttemptValidity,
                            FailureClass,
                            MethodStatus,
                            active_intention_frame,
                            record_method_status,
                        )

                        tgt = str(
                            pred_error.get("target")
                            or getattr(step, "semantic_target", "")
                            or ""
                        )
                        commitment_recovery = handle_failed_committed_action(
                            runtime.execution_state,
                            family=fam,
                            target=tgt,
                            point=(
                                getattr(step, "target_point", None)
                                if step is not None
                                else None
                            ),
                            pred_error=pred_error
                            if isinstance(pred_error, dict)
                            else {},
                            surface_before=str(
                                pred_error.get("expected_surface")
                                or pred_error.get("predicted")
                                or getattr(
                                    runtime.execution_state, "last_surface", ""
                                )
                                or ""
                            ),
                            surface_after=str(
                                pred_error.get("observed_surface")
                                or pred_error.get("actual")
                                or ""
                            ),
                        )
                        if (
                            commitment_recovery.get("classified") == "grounding"
                            and step is not None
                        ):
                            iframe = active_intention_frame(
                                runtime.execution_state
                            )
                            if iframe is not None:
                                mid = str(
                                    commitment_recovery.get(
                                        "preserve_semantic_method"
                                    )
                                    or (
                                        f"{fam}:{tgt[:80]}"
                                        if fam and tgt
                                        else ""
                                    )
                                )
                                if mid:
                                    # Preserve semantic method (do not mark INEFFECTIVE).
                                    record_method_status(
                                        iframe,
                                        mid,
                                        MethodStatus.UNTRIED.value,
                                    )
                                    try:
                                        runtime.execution_state.last_effect_closure = {
                                            **dict(
                                                getattr(
                                                    runtime.execution_state,
                                                    "last_effect_closure",
                                                    None,
                                                )
                                                or {}
                                            ),
                                            "attempt_validity": (
                                                AttemptValidity.INCONCLUSIVE_GROUNDING.value
                                            ),
                                            "failure_class": (
                                                FailureClass.GROUNDING.value
                                            ),
                                            "commitment_id": commitment_recovery.get(
                                                "commitment_id"
                                            ),
                                        }
                                    except Exception:
                                        pass
                    except Exception:
                        commitment_recovery = {}
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="execution_effect_missing",
                    payload={
                        "family": fam,
                        "message": "gesture ok but predicted transition absent",
                        "prediction_error": pred_error,
                        "open_repair": open_repair or None,
                        "reveal_escalation": reveal_esc or None,
                        "referent_mismatch": referent_mismatch or None,
                        "commitment_recovery": commitment_recovery or None,
                    },
                    status="fail",
                )

        narration = str(getattr(runtime.execution_state, "last_perception_narration", "") or "")
        if narration:
            critic = getattr(runtime.execution_state, "last_critic_verdict", None)
            # Say so when the prose belongs to an earlier frame. The narration
            # survives a frame the perceptor did not run, and logging it plainly
            # reads as a fresh look at a screen nobody looked at — which sent one
            # diagnosis of a wrong click down the wrong path entirely.
            narration_frame = int(
                getattr(runtime.execution_state, "last_perception_narration_frame", 0) or 0
            )
            current_frame = int(getattr(runtime.execution_state, "unified_frame", 0) or 0)
            carried_over = bool(narration_frame and current_frame and narration_frame < current_frame)
            if carried_over:
                narration = (
                    f"[carried over from frame {narration_frame}; no fresh perception this "
                    f"iteration] {narration}"
                )
            _log_cycle(
                log,
                iteration=iteration,
                phase="perception_summary",
                payload={
                    "message": narration,
                    "detail": narration,
                    "text": narration,
                    "narration_frame": narration_frame,
                    "carried_over": carried_over,
                    "surface": str(getattr(runtime.execution_state, "accepted_surface", "") or "")
                    or str((getattr(runtime.execution_state, "unified_world_document", None) or {}).get("surface") or ""),
                    "focused_field_role": str(
                        getattr(runtime.execution_state, "focused_field_role", "") or ""
                    ),
                    "critic_decisions": (critic or {}).get("decisions") if isinstance(critic, dict) else None,
                },
                status="ok",
            )

        trace = eng.last_trace
        selector_timeout_s = 0.0
        selector_timeout_source = ""
        if trace is not None and isinstance(trace.selector, dict):
            try:
                selector_timeout_s = float(trace.selector.get("timeout_s") or 0.0)
            except Exception:
                selector_timeout_s = 0.0
            selector_timeout_source = str(trace.selector.get("timeout_source") or "")
        _log_cycle(
            log,
            iteration=iteration,
            phase="decision_budget",
            payload={
                "step_budget": step_budget,
                "step_budget_remaining": max(0, step_budget - iteration + 1),
                "settle_s": settle_s,
                "monitor_timeout_s": monitor_timeout,
                "monitor_poll_s": monitor_poll,
                "selector_timeout_s": selector_timeout_s,
                "selector_timeout_source": selector_timeout_source,
                "decision_budget_semantics": "soft_hint",
            },
        )
        _log_cycle(
            log,
            iteration=iteration,
            phase="decision_engine",
            payload={
                "planner_invocations": runtime.execution_state.planner_invocations,
                "decision": None if decision is None else decision.__dict__,
                "trace": None if trace is None else {
                    "features": trace.features,
                    "candidates": trace.candidates,
                    "chosen": trace.chosen,
                },
                "app_view": view,
                "worldview_score": runtime.world_model.last_worldview_score,
                "world_id": before_world_id,
                "state_signature": state_sig,
            },
            status="ok" if decision is not None else "fail",
        )
        _log_cycle(
            log,
            iteration=iteration,
            phase="planner_decision",
            payload={
                "planner_invocations": runtime.execution_state.planner_invocations,
                "decision": None if decision is None else decision.__dict__,
                "whatsapp_view": view,
            },
            status="ok" if decision is not None else "fail",
        )

        if decision is None:
            return _finish_failure(
                "DecisionEngine produced no valid action",
                view,
                iterations=iteration,
            )

        # Bind action to current world version
        decision.observed_in_world = before_world_id
        runtime.execution_state.active_action_world_id = before_world_id
        runtime.execution_state.last_target_id = decision.target_entity_id

        log_policy_event(
            {
                "goal_kind": goal.kind,
                "bucket_key": feats.bucket_key(goal.kind),
                "feature_hash": feats.feature_hash(goal.kind),
                "action_family": decision.action_family,
                "action": decision.action,
                "target": decision.semantic_target,
                "success_delta": 0.0,
                "phase": "decide",
                "score": decision.score,
            }
        )

        if decision.action.lower() == "observe":
            runtime.execution_state.record(decision, {"ok": True, "backend": "noop", "message": "observe"})
            if runtime.execution_state.world_exploration_needed:
                runtime.execution_state.world_explore_observe_count = (
                    int(runtime.execution_state.world_explore_observe_count or 0) + 1
                )
            if goal.kind == "whatsapp_forward_message":
                _note_forward_observe(runtime, state_sig)
            _wait(settle_s, decision.rationale or "observe settle")
            continue

        # Non-observe clears observe streak
        runtime.execution_state.identical_observe_streak = 0
        runtime.execution_state.suppress_observe = False
        if goal.kind == "whatsapp_forward_message":
            hints = runtime.world_model.overlay_hints
            if hints is None:
                runtime.world_model.overlay_hints = {}
                hints = runtime.world_model.overlay_hints
            ft = dict(hints.get("forward_task") or {})
            ft["suppress_observe"] = False
            hints["forward_task"] = ft

        # Refuse stale world binding (should not happen mid-cycle, but guard executors)
        if decision.observed_in_world and decision.observed_in_world != runtime.execution_state.world_id:
            pred = decision.prediction if isinstance(decision.prediction, dict) else {}
            _log_cycle(
                log,
                iteration=iteration,
                phase="stale_action_target",
                payload={
                    "action_world": decision.observed_in_world,
                    "current_world": runtime.execution_state.world_id,
                    "action": decision.__dict__,
                },
                status="fail",
            )
            experience.record_outcome(
                state_sig,
                decision,
                TransitionOutcome.NO_EFFECT,
                progress_delta=0.0,
                predicted_outcome=str(pred.get("predicted_outcome") or ""),
                predicted_progress=float(pred.get("expected_progress") or 0.0),
                predicted_affordances=list(pred.get("expected_affordances") or []),
            )
            continue

        execution = execute.execute(decision)
        # Find-stage latch: every resolve/compose/type outcome must update the
        # search episode (complete / fail+retreat) even if the executor forked
        # around dispatch (live 212533 / 213012).
        # Stale/foreground refusals are handled inside note_find_stage_outcome
        # (must NOT arm search_retreat — live 202457).
        try:
            from plugin.agent.capabilities.search_episode import note_find_stage_outcome

            note_find_stage_outcome(
                runtime.execution_state,
                family=str(
                    getattr(decision, "action_family", None)
                    or getattr(decision, "action", "")
                    or ""
                ),
                ok=bool(getattr(execution, "ok", False)),
                message=str(getattr(execution, "message", "") or ""),
            )
        except Exception:
            pass
        # Thin motor feedback only. World belief comes from the next executive
        # re-perceive (stage1), not from AX settle. Success *or* failure: owe
        # act → re-perceive → decide before the next capability.
        if str(decision.action or "").strip().lower() != "observe":
            _note_post_action_reperceive(
                runtime,
                open_conversation=str((view or {}).get("open_conversation") or ""),
                state_sig=str(state_sig or ""),
            )
            # Stamp what *this* act claimed the next world should show. Surprise
            # is inferred on the post-act look (prediction_error), not from AX
            # settle heuristics.
            try:
                from plugin.agent.unified_cognition import stamp_act_intention

                stamped = stamp_act_intention(runtime.execution_state, decision)
            except Exception:
                stamped = {}
            if stamped:
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="act_intention",
                    payload=stamped,
                )
            # Actor motors reveal via context_click and skips reveal_actions();
            # still record handoff so the next perceive must ground affordance_set.
            try:
                fam = str(
                    getattr(decision, "action_family", None)
                    or getattr(decision, "action", "")
                    or ""
                ).strip().lower()
                fam_compact = fam.replace("_", "").replace("-", "")
                if fam in {"reveal_actions", "revealactions", "right_click", "context_click"}:
                    exec_ok = bool(getattr(execution, "ok", False))
                    if exec_ok:
                        from plugin.agent.capabilities.reveal_actions import (
                            current_reveal_probe_mode,
                            note_reveal_probe_handoff,
                        )

                        gesture = ""
                        try:
                            gesture = str(
                                getattr(decision, "gesture", None)
                                or getattr(
                                    getattr(runtime, "execution_state", None),
                                    "reveal_probe_mode",
                                    "",
                                )
                                or ""
                            ).strip().lower()
                        except Exception:
                            gesture = ""
                        if gesture not in {"context_click", "hover"}:
                            gesture = current_reveal_probe_mode(runtime.execution_state)
                        note_reveal_probe_handoff(
                            runtime.execution_state, gesture=gesture
                        )
                        _log_cycle(
                            log,
                            iteration=iteration,
                            phase="reveal_handoff",
                            payload={
                                "incomplete_reveal": True,
                                "substrate": "addressable_entity",
                                "discovery": "pending_perception",
                                "surface": "context_menu",
                                "probe_gesture": gesture,
                            },
                        )
                # locate_content: EffectStatus UNKNOWN latch (dispatch may have
                # already noted; re-note is idempotent on ledger append).
                if fam_compact in {"locatecontent", "locate"} or fam == "locate_content":
                    from plugin.agent.capabilities.locate_content import note_locate_outcome

                    msg = str(getattr(execution, "message", "") or "")
                    found = False
                    if "text_match_reachable=true" in msg.lower():
                        found = True
                    elif "text_match_reachable=false" in msg.lower():
                        found = False
                    realization = ""
                    if "realization=" in msg:
                        try:
                            realization = msg.split("realization=", 1)[1].split()[0]
                        except Exception:
                            realization = ""
                    query = str(
                        getattr(decision, "text", None)
                        or getattr(decision, "semantic_target", None)
                        or getattr(runtime.execution_state, "last_locate_query", "")
                        or ""
                    ).strip()
                    # Skip duplicate note when dispatch already latched this query.
                    already = (
                        bool(getattr(runtime.execution_state, "locate_effect_verify_owed", False))
                        or str(
                            getattr(runtime.execution_state, "last_locate_effect_status", "")
                            or ""
                        )
                        == "achieved"
                    ) and str(
                        getattr(runtime.execution_state, "last_locate_query", "") or ""
                    ).strip().lower() == query.lower()
                    if query and not already:
                        note_info = note_locate_outcome(
                            runtime.execution_state,
                            query=query,
                            ok=bool(getattr(execution, "ok", False)),
                            found=found,
                            realization=realization,
                            message=msg,
                        )
                        _log_cycle(
                            log,
                            iteration=iteration,
                            phase="locate_effect",
                            payload={
                                "effect_status": note_info.get("effect_status")
                                or getattr(
                                    runtime.execution_state,
                                    "last_locate_effect_status",
                                    "",
                                ),
                                "pending_effect_verification": bool(
                                    note_info.get("pending_effect_verification")
                                    or getattr(
                                        runtime.execution_state,
                                        "locate_effect_verify_owed",
                                        False,
                                    )
                                ),
                                "query": query[:80],
                                "realization": realization,
                                "found": found,
                            },
                        )
                    elif already and bool(
                        getattr(runtime.execution_state, "locate_effect_verify_owed", False)
                    ):
                        _log_cycle(
                            log,
                            iteration=iteration,
                            phase="locate_effect",
                            payload={
                                "effect_status": getattr(
                                    runtime.execution_state,
                                    "last_locate_effect_status",
                                    "",
                                ),
                                "pending_effect_verification": True,
                                "query": query[:80],
                                "realization": realization
                                or getattr(
                                    runtime.execution_state,
                                    "last_locate_realization",
                                    "",
                                ),
                                "found": found,
                            },
                        )
            except Exception:
                pass
            prev_meta_suppress = False
            prev_snap_pre = None

        # The continuity gate refused this click: the target rectangle no longer
        # held what the decision asked for, so the actuator declined rather than
        # clicking whatever had taken its place. Nothing reached the app.
        #
        # That is deliberately not an outcome. Recording it would tell the
        # transition machinery the action produced no effect, and the world critic
        # would condemn an affordance that was never invoked — the agent would
        # teach itself that a working control is dead because the screen moved
        # while it was thinking. The only correct response is to look again.
        if str(getattr(execution, "backend", "")) == STALE_PRECONDITION_BACKEND:
            aborts = _note_stale_abort(runtime)
            msg = str(getattr(execution, "message", "") or "")
            status = str(getattr(execution, "status", "") or "")
            # Geometry/frame failure with intact semantic target → local reground.
            grounding_local = any(
                tok in msg.lower() or tok in status.lower()
                for tok in (
                    "outside task window",
                    "off_task_window",
                    "stale_coordinate_frame",
                    "unknown_coordinate_frame",
                    "grounding_uncertain",
                    "inconclusive_grounding",
                    "invalid_coordinate",
                )
            ) or status in {
                "off_task_window",
                "inconclusive_grounding",
                "grounding_uncertain",
            }
            if grounding_local:
                runtime.execution_state.grounding_reground_only = True
                runtime.execution_state.grounding_reground_target = str(
                    decision.semantic_target or decision.action or ""
                )[:120]
                # Prefer commitment-scoped debt when an active commitment matches.
                try:
                    from plugin.agent.executive.affordance_commitment import (
                        arm_grounding_recovery,
                        ensure_commitment_from_menu_observation,
                        list_commitments,
                    )

                    c = None
                    tgt = str(decision.semantic_target or decision.action or "")
                    for item in list_commitments(runtime.execution_state):
                        if tgt and tgt.lower() in (
                            item.label.lower(),
                            item.semantic_method_id.lower(),
                        ):
                            c = item
                            break
                    if c is None and tgt:
                        c = ensure_commitment_from_menu_observation(
                            runtime.execution_state,
                            label=tgt,
                            patient_ref=str(
                                getattr(
                                    runtime.execution_state,
                                    "grounding_reground_patient_ref",
                                    "",
                                )
                                or ""
                            ),
                        )
                    if c is not None:
                        arm_grounding_recovery(
                            runtime.execution_state, c, reason="stale_precondition"
                        )
                except Exception:
                    pass
                runtime.execution_state.must_executive_reperceive = True
                # Do not burn no-progress / frontier invalidate on a typed
                # grounding failure — semantic binding stays.
                runtime.execution_state.world_exploration_needed = False
            _log_cycle(
                log,
                iteration=iteration,
                phase="stale_precondition",
                payload={
                    "action": decision.action,
                    "action_family": decision.action_family,
                    "target": decision.semantic_target,
                    "message": execution.message,
                    "consecutive_stale_aborts": aborts,
                    "budget": MAX_CONSECUTIVE_STALE_ABORTS,
                    "grounding_reground_only": bool(
                        getattr(runtime.execution_state, "grounding_reground_only", False)
                    ),
                    "recovery": "perceive_reground" if grounding_local else "relook",
                },
                status="warn",
            )
            if aborts <= MAX_CONSECUTIVE_STALE_ABORTS:
                # Look owed already set above; keep snap invalid.
                prev_meta_suppress = False
                prev_snap_pre = None
                continue
            # The target will not settle (a live-updating list, a playing video).
            # Re-looking has stopped paying, and an agent that never commits is no
            # better than one that commits wrongly, so let the next attempt through
            # and let the ordinary transition machinery judge a real outcome.
            runtime.execution_state.consecutive_stale_aborts = 0
            try:
                from plugin.agent.executive.affordance_commitment import (
                    clear_grounding_recovery,
                )

                clear_grounding_recovery(runtime.execution_state)
            except Exception:
                runtime.execution_state.grounding_reground_only = False
            bypass_next_gate()
            _log_cycle(
                log,
                iteration=iteration,
                phase="stale_precondition_budget_spent",
                payload={"aborts": aborts, "reason": "target never settled; committing next attempt"},
                status="warn",
            )
            prev_meta_suppress = False
            prev_snap_pre = None
            continue

        runtime.execution_state.consecutive_stale_aborts = 0
        runtime.execution_state.record(decision, execution.__dict__)
        # Ledger the attempt the moment it lands, before any judgement of it. The
        # count is what tells the next decision that this move has been tried
        # here before, which the consecutive-repeat counter cannot say about a
        # loop that alternates between two moves.
        attempt = runtime.execution_state.note_attempt(
            family=decision.action_family or decision.action,
            target=decision.semantic_target or decision.text,
            surface=str(getattr(runtime.execution_state, "accepted_surface", "") or ""),
            iteration=iteration,
        )
        _observe_capability_reliability(decision, execution.ok)
        _log_cycle(
            log,
            iteration=iteration,
            phase="execution",
            payload={
                **execution.__dict__,
                "plan_step": decision.__dict__,
                "world_id": before_world_id,
                "attempts_on_this_move": int(attempt.get("attempts", 1) or 1),
            },
            status="ok" if execution.ok else "fail",
        )

        if goal.kind == "whatsapp_forward_message" and execution.ok:
            _bind_forward_after_execution(runtime, decision)

        if not execution.ok:
            runtime.execution_state.record_failure(execution.message)
            pred = decision.prediction if isinstance(decision.prediction, dict) else {}
            experience.record_outcome(
                state_sig,
                decision,
                TransitionOutcome.NO_EFFECT,
                progress_delta=-0.2,
                predicted_outcome=str(pred.get("predicted_outcome") or ""),
                predicted_progress=float(pred.get("expected_progress") or 0.0),
                predicted_affordances=list(pred.get("expected_affordances") or []),
            )
            # Attribute execute-fail to actuation — never advance reference
            from plugin.agent.transition.attribution import attribute_transition

            attrib = attribute_transition(
                action=decision,
                outcome=TransitionOutcome.NO_EFFECT.value,
                execution=execution.__dict__,
                before_view=before_view,
                after_view=before_view,
                before_features=before_feats,
                after_features=before_feats,
                goal=goal,
            )
            runtime.execution_state.hypothesis_layers.apply(attrib)
            motor_attrib = attrib.to_dict()
            motor_attrib["belief_authority"] = "motor"
            runtime.execution_state.last_attribution = motor_attrib
            _note_post_action_reperceive(runtime)
            prev_meta_suppress = False
            prev_snap_pre = None
            _apply_actuation_suppression(runtime, decision, motor_attrib)
            runtime.execution_state.world_exploration_needed = True
            experience.pending_backtrack_family = "observe"
            _log_cycle(
                log,
                iteration=iteration,
                phase="transition_attribution",
                payload=motor_attrib,
                status="fail",
            )
            log_policy_event(
                {
                    "goal_kind": goal.kind,
                    "bucket_key": feats.bucket_key(goal.kind),
                    "action_family": decision.action_family,
                    "success_delta": -0.5,
                    "phase": "execute_fail",
                    "failure_domain": attrib.likely_failure_domain,
                    "effect_kind": attrib.effect_kind,
                }
            )
            continue

        if decision.action_family == "open_contact" and decision.semantic_target:
            runtime.execution_state.last_resolved_contact = decision.semantic_target  # type: ignore[attr-defined]

        if decision.action_family == "start_call" and execution.ok:
            hints = runtime.world_model.overlay_hints
            hints["start_call_count"] = int(hints.get("start_call_count") or 0) + 1

        if decision.action_family == "end_call":
            msg = (execution.message or "").lower()
            noop = (not execution.ok) or (
                "center=none" in msg and "hangup" not in msg and "escape" not in msg and "axpress" not in msg
            )
            if noop or not execution.ok:
                streak = int(getattr(runtime.execution_state, "end_call_fail_streak", 0) or 0) + 1
                runtime.execution_state.end_call_fail_streak = streak
                runtime.world_model.overlay_hints["end_call_fail_streak"] = streak
            else:
                runtime.execution_state.end_call_fail_streak = 0
                runtime.world_model.overlay_hints["end_call_fail_streak"] = 0

        if decision.action.lower() == "type":
            evidence_q = parse_typed_query_evidence(execution.message, decision.text or goal.contact)
            if evidence_q:
                runtime.execution_state.set_search_query_hint(evidence_q, ttl=4)
                runtime.world_model.overlay_hints["search_query"] = evidence_q
                # Recorded from the keystrokes, which is the only account of the
                # query that does not depend on reading the field back. The view
                # derives its own, and on the frames that matter it cannot: the
                # field's text gets taken for the open chat's title instead, so
                # the query goes missing exactly when it is needed to recognise
                # that echo. Sourcing the memory from the view therefore never
                # populated it at all in the case it exists for. The hint above
                # expires after four cycles; this is kept until superseded.
                runtime.world_model.last_search_query = evidence_q
            try:
                from plugin.perception.interpreters.execution import ExecutionInterpreter
                from plugin.perception.fusion.engine import get_fusion_engine

                hyps = ExecutionInterpreter().interpret_feedback(
                    action="type",
                    text=evidence_q or (decision.text or ""),
                    ok=True,
                    message=execution.message or "",
                )
                if hyps:
                    frame = get_fusion_engine().fuse_hypotheses(
                        hyps,
                        app=runtime.world_model.active_app or goal.app,
                        sources=["execution"],
                    )
                    runtime.world_model.overlay_hints["execution_frame"] = frame.report.to_dict()
            except Exception:
                pass

        def _ingest_obs(obs: Observation) -> Any:
            # TransitionMonitor observes separately; fuse/update via shared cycle.
            if decision.action_family == "start_call" and _raw_observation_mentions_ringing(obs):
                raw_call_ring_seen["seen"] = True
            apply_observation(
                runtime,
                goal,
                obs,
                action_label=decision.action.lower(),
                target_entity_id=runtime.execution_state.last_target_id,
                log_fn=_perception_log_fn(log, iteration),
                iteration=iteration,
            )
            return runtime.world_model

        def _view_from_world(_wm: Any) -> Dict[str, Any]:
            return _view_dict(runtime, goal)

        transition, _after_wm, post_view = monitor.wait_for_change_or_stability(
            before_fp=before_fp,
            observe=observe,
            ingest=_ingest_obs,
            view_fn=_view_from_world,
            wait_fn=wait_fn,
            min_settle_s=max(settle_s * 0.5, 0.4) if decision.action.lower() != "type" else max(settle_s, 0.8),
        )

        if transition.changed and transition.change_score >= 0.2:
            runtime.execution_state.bump_world_id(significant=True)
            runtime.execution_state.last_target_id = None

        after_world_id = runtime.execution_state.world_id
        post_wv = _worldview(runtime)
        after_feats = _feature_dict(runtime, goal, post_wv)

        # Reusable observe→fuse→update cycle with settlement retries
        initial_snap = PerceptionSnapshot(
            observation=None,
            patch=runtime.patches[-1] if runtime.patches else None,
            view=dict(post_view),
            features=after_feats,
            worldview=post_wv,
            action_label=f"post_{decision.action_family}",
        )
        settled_snap = ensure_settled_perception(
            runtime,
            goal,
            observe=observe,
            action_family=decision.action_family,
            wait_fn=_wait,
            settle_s=settle_s,
            initial=initial_snap,
            log_fn=_perception_log_fn(log, iteration),
            iteration=iteration,
            search_query_hint=runtime.execution_state.peek_search_query_hint(),
        )
        post_view = settled_snap.view
        after_feats = settled_snap.features
        post_wv = settled_snap.worldview
        after_world_id = runtime.execution_state.world_id
        perception_settled = bool(settled_snap.settled)
        _log_cycle(
            log,
            iteration=iteration,
            phase="post_transition_settled_view",
            payload={
                "action_family": decision.action_family,
                "screen": post_view.get("screen"),
                "call_state": post_view.get("call_state"),
                "open_conversation": post_view.get("open_conversation"),
                "search_query": post_view.get("search_query"),
                "visible_contacts": (post_view.get("visible_contacts") or [])[:10],
                "perception_settled": perception_settled,
            },
            status="ok",
        )

        if runtime.execution_state.search_refinement_pending:
            active_hypothesis = goal.search_text(runtime.execution_state.search_hypothesis_index)
            search_query = str(feature_get(after_feats, "search_query") or "").strip()
            if search_query and active_hypothesis and search_query.lower() == active_hypothesis.lower():
                runtime.execution_state.search_refinement_pending = False
            elif feature_get(after_feats, "result_surface_visible"):
                runtime.execution_state.search_refinement_pending = False
        after_state_sig = _semantic_state_signature(
            view=post_view,
            features=after_feats,
            world_id=after_world_id,
        )
        runtime.execution_state.note_world_signature(after_state_sig, decision)

        _log_cycle(
            log,
            iteration=iteration,
            phase="post_observation",
            payload={
                "transition": transition.to_dict(),
                "world_id": after_world_id,
            },
        )
        _log_cycle(
            log,
            iteration=iteration,
            phase="post_world_patch",
            payload={
                "whatsapp_screen": post_view.get("screen"),
                "search_query": post_view.get("search_query"),
                "visible_contacts": (post_view.get("visible_contacts") or [])[:10],
                "open_conversation": post_view.get("open_conversation"),
                "call_state": post_view.get("call_state"),
                "worldview_score": runtime.world_model.last_worldview_score,
                "entities_matching_contact": entities_matching(
                    runtime.world_model, goal.contact, limit=12
                ),
                "search_query_hint": runtime.execution_state.peek_search_query_hint(),
                "world_id": after_world_id,
                "transition_change_score": transition.change_score,
                "interaction_context": runtime.execution_state.interaction_context.to_dict(),
            },
        )

        # Evaluate against pre-action latent context (object permanence), then refresh
        pre_action_ctx = runtime.execution_state.interaction_context
        attempt = evaluator.evaluate(
            goal=goal,
            before_world=runtime.world_model,
            after_world=runtime.world_model,
            action=decision,
            before_view=before_view,
            after_view=post_view,
            before_features=before_feats,
            after_features=after_feats,
            transition=transition,
            before_world_id=before_world_id,
            after_world_id=after_world_id,
            execution=execution.__dict__,
            interaction_context=pre_action_ctx,
        )
        update_interaction_context(
            runtime.execution_state.interaction_context,
            goal=goal,
            view=post_view,
            features=after_feats,
            world_id=after_world_id,
        )
        runtime.execution_state.last_transition = attempt.to_dict()
        attrib_dict = dict(attempt.attribution or {})
        # AX settle / TransitionEvaluator is diagnostic — not executive belief.
        attrib_dict["belief_authority"] = "ax_settle_diagnostic"
        runtime.execution_state.last_attribution = attrib_dict
        # The world moved, so a further look has something new to read: the
        # diagnostic re-look budget is restored. Only a run of moves that leave
        # the world untouched should exhaust it.
        if _world_moved(attrib_dict, attempt):
            runtime.execution_state.consecutive_surprise_relooks = 0
        attempt_progress_delta = float(getattr(attempt, "progress_delta", 0.0) or 0.0)
        belief_updates_raw = attrib_dict.get("belief_updates") or []
        if belief_updates_raw:
            from plugin.agent.transition.belief_state import BeliefUpdate

            runtime.execution_state.record_belief_updates(
                [
                    BeliefUpdate.from_dict(item) if isinstance(item, dict) else item
                    for item in belief_updates_raw
                    if item is not None
                ]
            )
        from plugin.agent.transition.belief_state import Experiment, Expectation, Hypothesis, Uncertainty

        effect_kind = str(attrib_dict.get("effect_kind") or attempt.effect_kind or "")
        action_family = str(attrib_dict.get("action_family") or decision.action_family or "")
        target_label = str(decision.semantic_target or attrib_dict.get("semantic_target") or "")
        if (
            action_family in {"open_entity", "open_contact"}
            and effect_kind in {"no_transition", "actuator_failed", "not_attempted", "no_effect"}
        ):
            repair = _note_open_source_failure(
                runtime, decision, reason=f"effect_kind={effect_kind}"
            )
            _log_cycle(
                log,
                iteration=iteration,
                phase="open_source_repair",
                payload={"open_repair": repair, "effect_kind": effect_kind},
                status="warn",
            )
        # Record where the screen went into the workspace — the one authoritative
        # transition history the executive reasons over.
        _before_extras = _feats_extras(before_feats)
        _after_extras = _feats_extras(after_feats)
        commit_transition(
            runtime.execution_state,
            action=str(decision.action or ""),
            family=action_family or str(decision.action_family or ""),
            before_surface=_reading_surface(
                _before_extras, str(_before_extras.get("open_conversation") or "")
            ),
            after_surface=_reading_surface(
                _after_extras, str(_after_extras.get("open_conversation") or "")
            ),
            outcome=str(getattr(attempt, "outcome", "") or effect_kind or ""),
            progress_delta=attempt_progress_delta,
        )
        if effect_kind in {"transition_not_perceived", "missing_geometry"}:
            uncertainty = Uncertainty(
                question="Is perception stale or incomplete for the current post-action world?",
                importance=0.9,
                blocking_goal_predicates=["world_transition_confirmed"],
                candidate_values=["perception_stale", "perception_complete", "actuation_failed"],
                confidence_gap=0.45,
                staleness=1.0,
            )
            hypotheses = [
                Hypothesis(
                    explanation="The action succeeded but the current frame is not yet settled.",
                    confidence=0.42,
                    causal_assumptions=["sensor settlement lag"],
                    predicted_observations=["settled frame reveals the expected affordance"],
                    discriminating_experiments=["reobserve", "wait_then_observe"],
                ),
                Hypothesis(
                    explanation="The action did not land on the intended target.",
                    confidence=0.33,
                    causal_assumptions=["actuator miss or missing geometry"],
                    predicted_observations=["no target-specific affordance appears"],
                    discriminating_experiments=["inspect target geometry"],
                ),
            ]
            experiment = Experiment(
                capability="Observe",
                target=None,
                kind="observational",
                beliefs_tested=["perception_reliable", "world_transition_observed"],
                beliefs_changed=["perception_reliable"],
                expected_goal_progress=0.08,
                expected_information_gain=0.55,
                risk=0.02,
                cost=0.08,
                reversible=True,
                preconditions=["post_action_settled"],
                provenance={"effect_kind": effect_kind, "action_family": action_family},
            )
            expectation = Expectation(
                predicted_world_changes=["settled frame clarifies the current surface"],
                predicted_non_changes=["intent should remain unchanged"],
                expected_affordances=["reobserve"],
                timing_ms=800,
                contradiction_conditions=["world changes again before settle"],
                sensor_requirements=["pyobjc_ax", "vision"],
                side_effects=[],
                provenance={"effect_kind": effect_kind, "action_family": action_family},
            )
        elif effect_kind in {"actuator_failed", "no_transition", "not_attempted"}:
            uncertainty = Uncertainty(
                question="Did the actuator reach the intended target and make a world change?",
                importance=0.85,
                blocking_goal_predicates=["action_landings"],
                candidate_values=["actuator_failed", "target_misgrounded", "world_unchanged"],
                confidence_gap=0.4,
                staleness=0.4,
            )
            hypotheses = [
                Hypothesis(
                    explanation="The target was not grounded to a valid actuator.",
                    confidence=0.38,
                    causal_assumptions=["grounding mismatch"],
                    predicted_observations=["target-specific affordance remains absent"],
                    discriminating_experiments=["inspect target geometry"],
                ),
                Hypothesis(
                    explanation="The intended action is valid but the actuator failed transiently.",
                    confidence=0.34,
                    causal_assumptions=["transient actuator issue"],
                    predicted_observations=["same action may succeed after settle or alternate route"],
                    discriminating_experiments=["retry on same surface after settle"],
                ),
            ]
            experiment = Experiment(
                capability=decision.capability_type or action_family or "unknown",
                target=target_label or None,
                kind="mixed" if action_family in {"open_contact", "select_content"} else "interventional",
                beliefs_tested=["actuator_reliable", "target_actionability"],
                beliefs_changed=["actuator_reliable"],
                expected_goal_progress=max(0.0, float(attempt_progress_delta or decision.value_delta or 0.0)),
                expected_information_gain=0.32,
                risk=max(0.02, float(abs(attempt_progress_delta)) * 0.4),
                cost=0.12,
                reversible=bool(getattr(decision, "reversible", True)),
                preconditions=["grounded_target"],
                provenance={"effect_kind": effect_kind, "action_family": action_family},
            )
            expectation = Expectation(
                predicted_world_changes=["target affordance or destination picker should appear"],
                predicted_non_changes=["reference intent should not change"],
                expected_affordances=["act_on_target"],
                timing_ms=1200,
                contradiction_conditions=["same world repeats without new affordances"],
                sensor_requirements=["pyobjc_ax"],
                side_effects=[],
                provenance={"effect_kind": effect_kind, "action_family": action_family},
            )
        elif effect_kind == "promising_unresolved":
            uncertainty = Uncertainty(
                question="Which local affordance best advances the current promising branch?",
                importance=0.72,
                blocking_goal_predicates=["branch_progress"],
                candidate_values=["forward_picker", "destination_picker", "source_object_selected"],
                confidence_gap=0.28,
                staleness=0.2,
            )
            hypotheses = [
                Hypothesis(
                    explanation="The branch is locally promising and should be continued rather than reset.",
                    confidence=0.55,
                    causal_assumptions=["new affordances indicate progress"],
                    predicted_observations=["one of the new affordances becomes actionable"],
                    discriminating_experiments=["continue branch locally"],
                )
            ]
            experiment = Experiment(
                capability=decision.capability_type or action_family or "observe",
                target=target_label or None,
                kind="mixed",
                beliefs_tested=["branch_promising", "goal_progressing"],
                beliefs_changed=["branch_promising"],
                expected_goal_progress=max(0.05, float(attempt_progress_delta or decision.value_delta or 0.0)),
                expected_information_gain=0.24,
                risk=max(0.01, float(abs(attempt_progress_delta)) * 0.25),
                cost=0.10,
                reversible=bool(getattr(decision, "reversible", True)),
                preconditions=["branch_active"],
                provenance={"effect_kind": effect_kind, "action_family": action_family},
            )
            expectation = Expectation(
                predicted_world_changes=["new local affordance should remain available"],
                predicted_non_changes=["do not re-enter global search unless branch fails"],
                expected_affordances=["local_branch_action"],
                timing_ms=900,
                contradiction_conditions=["branch collapses back to the prior world"],
                sensor_requirements=["pyobjc_ax", "vision"],
                side_effects=[],
                provenance={"effect_kind": effect_kind, "action_family": action_family},
            )
        else:
            uncertainty = Uncertainty(
                question="What belief should change next to advance the goal?",
                importance=0.5,
                blocking_goal_predicates=["next_step"],
                candidate_values=["progress", "verification", "search"],
                confidence_gap=0.2,
                staleness=0.1,
            )
            hypotheses = [
                Hypothesis(
                    explanation="The current world state is stable enough to continue.",
                    confidence=0.5,
                    causal_assumptions=["no strong contradiction"],
                    predicted_observations=["next planned action remains available"],
                    discriminating_experiments=["continue current procedure"],
                )
            ]
            experiment = Experiment(
                capability=decision.capability_type or action_family or "observe",
                target=target_label or None,
                kind="observational" if action_family == "observe" else "mixed",
                beliefs_tested=["goal_progressing"],
                beliefs_changed=["goal_progressing"],
                expected_goal_progress=max(0.0, float(attempt_progress_delta)),
                expected_information_gain=0.18,
                risk=0.05,
                cost=0.05,
                reversible=bool(getattr(decision, "reversible", True)),
                preconditions=[],
                provenance={"effect_kind": effect_kind, "action_family": action_family},
            )
            expectation = Expectation(
                predicted_world_changes=["goal path should remain consistent"],
                predicted_non_changes=["no new contradiction should appear"],
                expected_affordances=["continue"],
                timing_ms=1000,
                contradiction_conditions=["world becomes inconsistent"],
                sensor_requirements=["pyobjc_ax"],
                side_effects=[],
                provenance={"effect_kind": effect_kind, "action_family": action_family},
            )

        runtime.execution_state.set_active_uncertainty(uncertainty)
        runtime.execution_state.set_active_hypotheses(hypotheses)
        runtime.execution_state.set_active_experiment(experiment)
        runtime.execution_state.belief_store.expectations[experiment.capability.lower()] = expectation
        transition_summary = _transition_summary_from_attempt(
            attempt,
            after_features=after_feats,
            decision=decision,
        )
        runtime.execution_state.last_transition_summary = transition_summary.to_dict()
        if getattr(eng, "last_trace", None) is not None:
            eng.last_trace.transition_summary = transition_summary
        # Apply layer belief updates from causal attribution
        if attrib_dict:
            from plugin.agent.transition.attribution import (
                TransitionAssessment,
                LayerBeliefDeltas,
            )
            from plugin.agent.transition.belief_state import BeliefUpdate

            beliefs = attrib_dict.get("affected_beliefs") or {}
            ta = TransitionAssessment(
                action_family=str(attrib_dict.get("action_family") or ""),
                outcome=str(attrib_dict.get("outcome") or attempt.outcome),
                effect_kind=str(attrib_dict.get("effect_kind") or attempt.effect_kind),
                likely_failure_domain=str(attrib_dict.get("likely_failure_domain") or ""),
                affected_beliefs=LayerBeliefDeltas(
                    reference_resolution=float(beliefs.get("reference_resolution") or 0),
                    entity_resolution=float(beliefs.get("entity_resolution") or 0),
                    target_actionability=float(beliefs.get("target_actionability") or 0),
                    actuator_reliability=float(beliefs.get("actuator_reliability") or 0),
                    perception_reliability=float(beliefs.get("perception_reliability") or 0),
                ),
                belief_updates=[
                    BeliefUpdate.from_dict(item) if isinstance(item, dict) else item
                    for item in (attrib_dict.get("belief_updates") or [])
                    if item is not None
                ],
                evidence=dict(attrib_dict.get("evidence") or {}),
                notes=list(attrib_dict.get("notes") or []),
            )
            runtime.execution_state.hypothesis_layers.apply(ta)

        # Sync entity confidence from resolution when available
        conf = float(after_feats.get("resolution_confidence") or 0)
        if conf > 0:
            runtime.execution_state.hypothesis_layers.entity_confidence = max(
                runtime.execution_state.hypothesis_layers.entity_confidence, conf
            )

        _FORWARD = {
            TransitionOutcome.PROGRESS.value,
            TransitionOutcome.PROMISING_UNRESOLVED.value,
            TransitionOutcome.GOAL_SATISFIED.value,
        }

        # Compat: keep last_verification shape for older log consumers
        runtime.execution_state.record_verification(
            {
                "passed": attempt.outcome in _FORWARD,
                "reason": attempt.outcome,
                "expected_predicate": "TransitionEvaluator",
                "evidence": attempt.to_dict(),
                "executor_ok": execution.ok,
                "effect_kind": attempt.effect_kind,
                "failure_domain": attrib_dict.get("likely_failure_domain"),
            }
        )
        experience.record_outcome(
            state_sig,
            decision,
            TransitionOutcome(attempt.outcome),
            progress_delta=attempt_progress_delta,
            predicted_outcome=str((attempt.prediction or {}).get("predicted_outcome") or ""),
            predicted_progress=float((attempt.prediction or {}).get("expected_progress") or 0.0),
            predicted_affordances=list((attempt.prediction or {}).get("expected_affordances") or []),
        )

        _log_cycle(
            log,
            iteration=iteration,
            phase="transition_eval",
            payload={
                "attempt": attempt.to_dict(),
                "summary": transition_summary.to_dict(),
            },
            status="ok"
            if attempt.outcome in _FORWARD
            else "fail"
            if attempt.outcome
            in {TransitionOutcome.NO_EFFECT.value, TransitionOutcome.REGRESSION.value}
            else "ok",
        )
        _log_cycle(
            log,
            iteration=iteration,
            phase="transition_attribution",
            payload={
                **attrib_dict,
                "transition_summary": transition_summary.to_dict(),
                "hypothesis_layers": runtime.execution_state.hypothesis_layers.to_dict(),
                "interaction_context": runtime.execution_state.interaction_context.to_dict(),
                "exploration_branch": runtime.execution_state.exploration_branch.to_dict(),
            },
            status="ok",
        )
        _log_cycle(
            log,
            iteration=iteration,
            phase="post_transition_diagnosis",
            payload={
                "diagnosis": transition_summary.diagnosis,
                "summary": transition_summary.to_dict(),
                "state_signature": after_state_sig,
            },
            status="ok",
        )
        # Compat log kind
        _log_cycle(
            log,
            iteration=iteration,
            phase="verification",
            payload={
                "passed": attempt.outcome in _FORWARD,
                "reason": attempt.outcome,
                "expected_predicate": "TransitionEvaluator",
                "evidence": attempt.to_dict(),
                "executor_ok": execution.ok,
                "transition_summary": transition_summary.to_dict(),
            },
            status="ok" if attempt.outcome in _FORWARD else "fail",
        )
        trajectory_steps.append(
            TrajectoryStepRecord(
                step_index=iteration,
                state_signature=after_state_sig,
                state_bucket=str(feats.bucket_key(goal.kind)),
                family_bucket=str(feats.bucket_key(goal.family_key())),
                action=decision.action,
                action_family=decision.action_family,
                next_state_signature=after_state_sig,
                next_state_bucket=str(after_feats.bucket_key(goal.kind))
                if hasattr(after_feats, "bucket_key")
                else str(feature_get(after_feats, "screen_bucket") or feature_get(after_feats, "wa_screen") or "unknown"),
                semantic_target=decision.semantic_target,
                outcome=attempt.outcome,
                progress_delta=attempt_progress_delta,
                surface=str(runtime.execution_state.interaction_context.active_surface or ""),
                reversible=bool(getattr(decision, "reversible", True)),
                score=float(decision.score or 0.0),
            )
        )

        post_view, after_feats, post_wv, richer_reobserve = _maybe_richer_reobserve_after_transition(
            runtime,
            goal,
            observe=observe,
            decision=decision,
            attempt=attempt,
            after_view=post_view,
            after_features=after_feats,
            post_wv=post_wv,
            log=log,
            iteration=iteration,
        )
        if richer_reobserve:
            after_world_id = runtime.execution_state.world_id
            after_state_sig = _semantic_state_signature(
                view=post_view,
                features=after_feats,
                world_id=after_world_id,
            )
            runtime.execution_state.note_world_signature(
                after_state_sig,
                decision,
            )

        post_call_state = str(post_view.get("call_state") or after_feats.get("call_state") or "").strip().lower()
        if (
            goal.kind == "whatsapp_voice_call"
            and post_call_state == "ringing"
        ):
            try:
                from plugin.agent.apps.whatsapp import _call_mentions_contact

                overlay = get_overlay(goal.app, runtime.world_model)
                view_obj = overlay.raw_view(runtime.world_model) if hasattr(overlay, "raw_view") else overlay._view(runtime.world_model)
                if not _call_mentions_contact(view_obj, runtime.world_model, goal.contact):
                    pass
                else:
                    runtime.execution_state.world_exploration_needed = False
                    runtime.execution_state.exploration_branch = ExplorationBranch()
                    if decision.capability_id:
                        runtime.execution_state.capability_memory.record_success(
                            goal_kind=goal.kind,
                            capability_id=decision.capability_id,
                            entity_id=after_world_id,
                            world_id=after_world_id,
                            outcome=TransitionOutcome.GOAL_SATISFIED.value,
                        )
                    return _finish_success(post_view or attempt.to_dict(), iterations=iteration)
            except Exception:
                pass

        if goal.kind == "whatsapp_forward_message":
            _forward_predicate_gate_after_transition(
                runtime,
                decision=decision,
                attempt_outcome=attempt.outcome,
                after_feats=after_feats,
                log=log,
                iteration=iteration,
                goal=goal,
            )

        transition_confirmation = confirm_transition_with_llm(
            goal,
            runtime.world_model,
            post_view,
            after_feats,
            decision,
            attempt,
            runtime.execution_state.interaction_context,
        )
        if transition_confirmation is not None:
            apply_transition_confirmation(
                runtime,
                goal=goal,
                action=decision,
                attempt=attempt,
                confirmation=transition_confirmation,
                after_view=post_view,
                after_features=after_feats,
                world_id=after_world_id,
            )
            _log_cycle(
                log,
                iteration=iteration,
                phase="transition_confirmation",
                payload=transition_confirmation.to_dict(),
                status="ok" if transition_confirmation.confirmed else "fail",
            )

        delta = attempt_progress_delta
        log_policy_event(
            {
                "goal_kind": goal.kind,
                "bucket_key": feats.bucket_key(goal.kind),
                "action_family": decision.action_family,
                "success_delta": delta,
                "phase": "transition",
                "outcome": attempt.outcome,
                "effect_kind": attempt.effect_kind,
                "failure_domain": attrib_dict.get("likely_failure_domain"),
                "change_score": float(getattr(attempt, "change_score", 0.0) or 0.0),
            }
        )

        # Goal satisfied after transition — override max iterations
        post_goal = evaluate_goal(goal, runtime.world_model)
        if (
            not post_goal.succeeded
            and goal.kind == "whatsapp_voice_call"
            and str(settled_snap.view.get("call_state") or "").strip().lower() == "ringing"
        ):
            if not goal.require_contact_in_call or _post_view_mentions_contact(settled_snap.view, goal):
                post_goal = GoalStatus(
                    succeeded=True,
                    reason="call ringing",
                    evidence=dict(settled_snap.view),
                )
        if (
            not post_goal.succeeded
            and goal.kind == "whatsapp_voice_call"
            and raw_call_ring_seen["seen"]
        ):
            if not goal.require_contact_in_call or _post_view_mentions_contact(settled_snap.view, goal):
                post_goal = GoalStatus(
                    succeeded=True,
                    reason="raw observation ringing",
                    evidence={
                        **dict(settled_snap.view),
                        "raw_call_ring_seen": True,
                    },
                )
        if (
            not post_goal.succeeded
            and goal.kind == "whatsapp_voice_call"
            and _raw_observation_mentions_ringing(settled_snap.observation)
        ):
            if not goal.require_contact_in_call or _post_view_mentions_contact(settled_snap.view, goal):
                post_goal = GoalStatus(
                    succeeded=True,
                    reason="raw observation ringing",
                    evidence={
                        **dict(settled_snap.view),
                        "raw_observation": {
                            "app": settled_snap.observation.app_name if settled_snap.observation else "",
                            "window": settled_snap.observation.window_name if settled_snap.observation else "",
                            "source": settled_snap.observation.source if settled_snap.observation else "",
                        },
                    },
                )
        if post_goal.succeeded or attempt.outcome == TransitionOutcome.GOAL_SATISFIED.value:
            goal_last_progress_at = time.monotonic()
            runtime.execution_state.world_exploration_needed = False
            runtime.execution_state.exploration_branch = ExplorationBranch()
            if decision.capability_id:
                runtime.execution_state.capability_memory.record_success(
                    goal_kind=goal.kind,
                    capability_id=decision.capability_id,
                    entity_id=decision.target_entity_id,
                    world_id=after_world_id,
                    outcome=attempt.outcome,
            )
            _maybe_learn_success(runtime, goal, post_goal if post_goal.succeeded else goal_status)
            return _finish_success(post_goal.evidence or attempt.to_dict(), iterations=iteration)

        # Geometry miss is activity without advancement — do not credit progress.
        geom_miss = False
        try:
            res = getattr(runtime.execution_state, "last_result", None) or {}
            if isinstance(res, dict) and str(res.get("status") or "") == "geometry_mismatch":
                geom_miss = True
            closure = getattr(runtime.execution_state, "last_effect_closure", None) or {}
            if isinstance(closure, dict) and closure.get("geometry_mismatch"):
                geom_miss = True
        except Exception:
            geom_miss = False
        if geom_miss:
            try:
                runtime.execution_state.last_effect_closure = {
                    **(dict(getattr(runtime.execution_state, "last_effect_closure", None) or {})),
                    "geometry_mismatch": True,
                    "modes": list(
                        (getattr(runtime.execution_state, "last_effect_closure", None) or {}).get(
                            "modes"
                        )
                        or []
                    )
                    + ["geometry_mismatch"],
                }
                runtime.execution_state.must_executive_reperceive = True
            except Exception:
                pass

        if (
            attempt.outcome == TransitionOutcome.PROMISING_UNRESOLVED.value
            and not geom_miss
        ):
            goal_last_progress_at = time.monotonic()
            # Enter / continue bounded local branch — do NOT thrash observe or revise intent
            assessment = attempt.assessment or {}
            surface = str(runtime.execution_state.interaction_context.active_surface or "")
            branch = runtime.execution_state.exploration_branch
            revealed_affordances = _merge_affordance_hints(
                list(assessment.get("newly_relevant_affordances") or []),
                list(assessment.get("new_capabilities") or []),
            )
            if not branch.active:
                branch = ExplorationBranch(
                    origin_state=state_sig,
                    entry_action=attempt.action_key,
                    current_state=after_state_sig,
                    active_surface=surface,
                    last_surface=surface,
                    depth=1,
                    reversible=bool(assessment.get("branch_reversible", True)),
                    active=True,
                    newly_relevant_affordances=list(revealed_affordances),
                )
            elif branch.active_surface == "search_results" and branch.depth == 0:
                branch.depth = 1
                branch.note_step(
                    state_signature=after_state_sig,
                    surface=surface,
                    newly_relevant_affordances=list(revealed_affordances),
                )
            else:
                branch.depth += 1
                branch.note_step(
                    state_signature=after_state_sig,
                    surface=surface,
                    newly_relevant_affordances=list(revealed_affordances),
                )
            if revealed_affordances:
                ctx = runtime.execution_state.interaction_context
                if ctx is not None:
                    ctx.latent_affordances = _merge_affordance_hints(
                        list(getattr(ctx, "latent_affordances", []) or []),
                        revealed_affordances,
                    )
                if not branch.strategy.branch_hypothesis:
                    branch.strategy.branch_hypothesis = "reveal surfaced latent actions"
                if not experience.pending_backtrack_family:
                    branch_hint = _frontier_backtrack_hint(branch, fallback="")
                    if branch_hint:
                        experience.pending_backtrack_family = branch_hint
            branch.contradiction_count = max(branch.contradiction_count, len(assessment.get("contradiction_evidence") or []))
            runtime.execution_state.exploration_branch = branch
            runtime.execution_state.world_exploration_needed = False
            runtime.execution_state.world_explore_observe_count = 0
            experience.pending_backtrack_family = (
                experience.pending_backtrack_family or _frontier_backtrack_hint(branch, fallback="")
            )
            if decision.action_family == "open_contact":
                runtime.execution_state.open_contact_fail_streak = 0
            _log_cycle(
                log,
                iteration=iteration,
                phase="branch_explore",
                payload=branch.to_dict(),
                status="ok",
            )
            # Never advance search hyp on promising entry — explore results first
            if decision.action_family == "type_query":
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="search_hypothesis_advance_blocked",
                    payload={
                        "reason": "promising_branch",
                        "perception_settled": perception_settled,
                        "resolution_policy": feature_get(after_feats, "resolution_policy"),
                    },
                    status="ok",
                )
            if branch.budget_exhausted():
                # Exhausted patience → soft backtrack without marking entry as regression
                runtime.execution_state.record_failure("branch_budget_exhausted")
                # Only now consider spelling refine if results truly empty after settlement.
                _maybe_advance_search_hypothesis(
                    runtime,
                    goal,
                    decision=Action(
                        action="Observe",
                        action_family="observe",
                        rationale="branch budget — check settled empty",
                    ),
                    after_view=post_view,
                    after_features=after_feats,
                    log=log,
                    iteration=iteration,
                    perception_settled=perception_settled,
                )
                experience.pending_backtrack_family = _frontier_backtrack_hint(branch)
                runtime.execution_state.exploration_branch = ExplorationBranch()
            continue

        if attempt.outcome == TransitionOutcome.PROGRESS.value:
            goal_last_progress_at = time.monotonic()
            if decision.action_family == "open_contact":
                runtime.execution_state.open_contact_fail_streak = 0
            if decision.action_family == "type_query":
                runtime.execution_state.type_query_fail_streak = 0
            if decision.capability_id:
                runtime.execution_state.capability_memory.record_success(
                    goal_kind=goal.kind,
                    capability_id=decision.capability_id,
                    entity_id=decision.target_entity_id,
                    world_id=after_world_id,
                    outcome=attempt.outcome,
                )
            # Progress within world → intent still fixed; never revise reference here
            runtime.execution_state.world_exploration_needed = False
            runtime.execution_state.world_explore_observe_count = 0
            experience.pending_backtrack_family = ""
            # Clear branch on clear progress past the overlay
            if runtime.execution_state.exploration_branch.active:
                runtime.execution_state.exploration_branch.depth += 1
                runtime.execution_state.exploration_branch.note_step(
                    state_signature=after_state_sig,
                    surface=str(runtime.execution_state.interaction_context.active_surface or ""),
                    newly_relevant_affordances=list(
                        (attempt.assessment or {}).get("newly_relevant_affordances") or []
                    ),
                )
            continue

        if attempt.outcome == TransitionOutcome.NO_EFFECT.value:
            runtime.execution_state.record_failure(
                f"no_effect:{decision.action_family}:{attempt.effect_kind}"
            )
            _apply_actuation_suppression(runtime, decision, attrib_dict)
            if decision.action_family == "type_query":
                runtime.execution_state.type_query_fail_streak += 1
                key = runtime.execution_state.action_key(decision)
                runtime.execution_state.prohibited_actions[key] = max(
                    runtime.execution_state.prohibited_actions.get(key, 0), 2
                )
            elif decision.action_family == "open_search":
                runtime.execution_state.search_refinement_pending = True
            branch = runtime.execution_state.exploration_branch
            if decision.action_family == "observe" and perception_settled:
                if _maybe_advance_search_hypothesis(
                    runtime,
                    goal,
                    decision=decision,
                    after_view=post_view,
                    after_features=after_feats,
                    log=log,
                    iteration=iteration,
                    perception_settled=perception_settled,
                ):
                    runtime.execution_state.world_exploration_needed = False
                    experience.pending_backtrack_family = ""
                    continue
            if branch.active:
                if decision.action_family == "observe":
                    branch.observe_count += 1
                else:
                    branch.no_effect_count += 1
                branch.note_step(
                    state_signature=after_state_sig,
                    surface=str(runtime.execution_state.interaction_context.active_surface or ""),
                    newly_relevant_affordances=[],
                )
                runtime.execution_state.exploration_branch = branch
                if branch.budget_exhausted():
                    experience.pending_backtrack_family = _frontier_backtrack_hint(branch)
                    runtime.execution_state.exploration_branch = ExplorationBranch()
                    runtime.execution_state.world_exploration_needed = True
                else:
                    # Stay on branch: try alternate local affordance, not global re-search
                    runtime.execution_state.world_exploration_needed = False
                    experience.pending_backtrack_family = _frontier_backtrack_hint(branch)
            else:
                domain = str(attrib_dict.get("likely_failure_domain") or "")
                if domain in {
                    FailureDomain.ACTUATION.value,
                    FailureDomain.PERCEPTION.value,
                    FailureDomain.UNKNOWN.value,
                }:
                    runtime.execution_state.world_exploration_needed = True
                    if decision.action_family != "scroll_content":
                        experience.pending_backtrack_family = "observe"
            _maybe_advance_reference_hypothesis(
                runtime,
                goal,
                attribution=attrib_dict,
                after_view=post_view,
                after_features=after_feats,
                log=log,
                iteration=iteration,
            )
            continue

        if attempt.outcome == TransitionOutcome.REGRESSION.value:
            # AX settle "regression" is logged, but must not ban the capability
            # or block actuation — the next executive stage1 look owns the story.
            runtime.execution_state.record_failure(f"regression_diagnostic:{decision.action_family}")
            # Object-scoped invoke that lost the patient → referent repair debt.
            fam_l = str(decision.action_family or "").strip().lower()
            notes = " ".join(
                str(n)
                for n in (
                    list((attempt.assessment or {}).get("notes") or [])
                    + list(getattr(attempt, "reasons", None) or [])
                )
            ).lower()
            if fam_l == "invoke_affordance" and any(
                tok in notes
                for tok in (
                    "wrong_target",
                    "target_deselected",
                    "wrong_target_visible",
                )
            ):
                try:
                    step = decision
                    fp = ""
                    try:
                        from plugin.agent.brain import motor_fingerprint

                        fp = motor_fingerprint(
                            fam_l,
                            str(getattr(step, "semantic_target", "") or ""),
                            getattr(step, "target_point", None),
                        )
                    except Exception:
                        fp = str(
                            getattr(runtime.execution_state, "last_failed_motor_key", "")
                            or ""
                        )
                    prev = dict(
                        getattr(runtime.execution_state, "last_effect_closure", None)
                        or {}
                    )
                    runtime.execution_state.last_effect_closure = {
                        **prev,
                        "referent_repair_owed": True,
                        "fingerprint": fp or prev.get("fingerprint") or "",
                        "modes": list(prev.get("modes") or [])
                        + ["wrong_target", "referent_mismatch"],
                        "action_family": fam_l,
                    }
                    if fp:
                        runtime.execution_state.last_failed_motor_key = fp
                except Exception:
                    pass
            _log_cycle(
                log,
                iteration=iteration,
                phase="ax_settle_regression_diagnostic",
                payload={
                    "action_family": decision.action_family,
                    "outcome": attempt.outcome,
                    "note": "AX settle regression ignored for executive belief; "
                    "must_executive_reperceive owns the next look",
                    "must_executive_reperceive": True,
                },
                status="warn",
            )
            _maybe_advance_reference_hypothesis(
                runtime,
                goal,
                attribution=attrib_dict,
                after_view=post_view,
                after_features=after_feats,
                log=log,
                iteration=iteration,
            )
            continue

        # UNCERTAIN — gather more info next cycle; do not mutate reference
        if runtime.execution_state.exploration_branch.active:
            # Epistemic patience inside a promising branch
            if decision.action_family == "observe":
                runtime.execution_state.exploration_branch.observe_count += 1
            runtime.execution_state.exploration_branch.note_step(
                state_signature=after_state_sig,
                surface=str(runtime.execution_state.interaction_context.active_surface or ""),
                newly_relevant_affordances=list(
                    (attempt.assessment or {}).get("newly_relevant_affordances") or []
                ),
            )
            experience.pending_backtrack_family = ""
            runtime.execution_state.world_exploration_needed = False
        elif str(attrib_dict.get("likely_failure_domain") or "") == FailureDomain.PERCEPTION.value:
            runtime.execution_state.world_exploration_needed = True
            experience.pending_backtrack_family = "observe"
        continue

    # Budget exhausted — still succeed if world already satisfies goal
    final_status = evaluate_goal(goal, runtime.world_model)
    if final_status.succeeded:
        _maybe_learn_success(runtime, goal, final_status)
        return _finish_success(final_status.evidence, iterations=step_budget)

    return _finish_failure(
        "Maximum step count reached",
        {
            **_view_dict(runtime, goal),
            "budget": {
                "max_iterations": max_iterations,
                "max_stepcount": max_stepcount,
                "resolved_step_budget": step_budget,
            },
        },
        iterations=step_budget,
    )


def _forward_hints(runtime: RuntimeState) -> Dict[str, Any]:
    hints = runtime.world_model.overlay_hints
    if hints is None:
        runtime.world_model.overlay_hints = {}
        hints = runtime.world_model.overlay_hints
    return hints


def _perception_extras(features: Any) -> Dict[str, Any]:
    extras = getattr(features, "extras", None)
    if extras is None and isinstance(features, dict):
        extras = features.get("extras")
    return extras if isinstance(extras, dict) else {}


def target_app_obscured(features: Any, view: Optional[Dict[str, Any]] = None) -> bool:
    """True when perception says the target app is covered by another window."""
    extras = _perception_extras(features)
    perception = extras.get("perception_llm") if isinstance(extras.get("perception_llm"), dict) else {}
    summary = extras.get("perception_summary") if isinstance(extras.get("perception_summary"), dict) else {}
    screen_type = str(
        perception.get("screen_type")
        or summary.get("screen_type")
        or (view or {}).get("screen")
        or ""
    ).strip().lower()
    surface = str(
        perception.get("active_surface")
        or summary.get("active_surface")
        or ""
    ).strip().lower()
    family = str(
        perception.get("likely_next_family")
        or summary.get("likely_next_family")
        or ""
    ).strip().lower()
    if "obscured" in screen_type or screen_type == "desktop_obscured_target":
        return True
    if family in {"window_management", "focus_app", "activate_app"}:
        return True
    if "terminal" in surface and "foreground" in surface:
        return True
    if "background" in surface and "whatsapp" in surface:
        return True
    return False


# How many consecutive refusals before the gate yields. A target that never
# settles would otherwise abort forever, and an agent that never commits is no
# better than one that commits wrongly.
MAX_CONSECUTIVE_STALE_ABORTS = 3


def _note_stale_abort(runtime: RuntimeState) -> int:
    """Count one click the continuity gate refused because the screen had moved on."""
    count = int(getattr(runtime.execution_state, "consecutive_stale_aborts", 0) or 0) + 1
    runtime.execution_state.consecutive_stale_aborts = count
    return count


def _reclaim_foreground(runtime: RuntimeState, goal: Goal, *, log: Any, iteration: int) -> bool:
    """Take the foreground back when a foreign app holds it. Returns whether it acted.

    Ground truth from ``NSWorkspace`` rather than inference from pixels: asking
    the window server who is frontmost is free and exact, where reading it out of
    a screenshot means hoping the vision model emits the right screen-type string.
    The old path did the latter and only recovered when perception happened to
    describe the obstruction correctly.

    Fails open throughout — an undeterminable foreground or an unknown task app is
    never treated as evidence of a takeover, so a missing signal cannot start the
    agent fighting for a foreground nobody took.
    """
    if not foreground_gate_enabled():
        return False
    app_name = str(goal.app or runtime.world_model.active_app or "").strip()
    if not app_name:
        _log_cycle(
            log,
            iteration=iteration,
            phase="foreground_reclaim",
            payload={"skip_reason": "no_task_app", "reclaimed": False},
            status="skip",
        )
        return False
    holder = foreground_app_name()
    if not holder:
        # Fail-open, but leave a breadcrumb — silent skips made 092106
        # impossible to audit when Cursor was visibly frontmost.
        _log_cycle(
            log,
            iteration=iteration,
            phase="foreground_reclaim",
            payload={
                "app": app_name,
                "skip_reason": "unknown_foreground_fail_open",
                "reclaimed": False,
            },
            status="skip",
        )
        return False
    if foreground_matches_task(goal, foreground=holder):
        # Only sample matches so the log is not flooded when WhatsApp stays front.
        if int(iteration or 0) % 10 == 1:
            _log_cycle(
                log,
                iteration=iteration,
                phase="foreground_reclaim",
                payload={
                    "app": app_name,
                    "holder": clean_app_display(holder),
                    "skip_reason": "already_task_app",
                    "reclaimed": False,
                },
                status="skip",
            )
        return False

    try:
        from plugin.executor.ax_action import _activate_app

        _activate_app(app_name)
        reclaimed = True
    except Exception as exc:
        logger.debug("foreground reclaim failed: %s", exc)
        reclaimed = False

    count = int(getattr(runtime.execution_state, "foreground_reclaims", 0) or 0) + 1
    runtime.execution_state.foreground_reclaims = count
    _log_cycle(
        log,
        iteration=iteration,
        phase="foreground_reclaim",
        payload={
            "app": app_name,
            "taken_by": clean_app_display(holder),
            "reclaimed": reclaimed,
            "reclaims_this_run": count,
            "reason": "a foreign app held the foreground the agent needs to act in",
        },
        status="ok" if reclaimed else "warn",
    )
    return reclaimed


def recover_obscured_target_app(app_name: str) -> bool:
    """Force the goal app frontmost so AX/screenshots see real content again."""
    name = str(app_name or "").strip()
    if not name:
        return False
    try:
        from plugin.executor.ax_action import _activate_app
        from plugin.perception.macos.launch import launch_app

        launched = launch_app(name, activate=True)
        _activate_app(name)
        return bool(getattr(launched, "ok", False))
    except Exception:
        try:
            from plugin.perception.macos.launch import launch_app

            return bool(launch_app(name, activate=True).ok)
        except Exception:
            return False


def _apply_forward_observe_stagnation(
    runtime: RuntimeState,
    *,
    state_sig: str,
    entity_count: int,
    features: Any,
) -> None:
    """If Observe repeated on an unchanged world, suppress further Observe."""
    hints = _forward_hints(runtime)
    extras = getattr(features, "extras", None)
    if extras is None and isinstance(features, dict):
        extras = features.setdefault("extras", {})
        if not isinstance(extras, dict):
            features["extras"] = {}
            extras = features["extras"]
    if extras is None:
        extras = {}
        if hasattr(features, "extras"):
            features.extras = extras

    ft = dict(hints.get("forward_task") or extras.get("forward_task") or {})
    preds = ft.get("predicates") or {}
    phase = str(ft.get("derived_phase") or extras.get("forward_phase") or "")
    bindings = ft.get("bindings") or {}
    source_object = bindings.get("source_object") if isinstance(bindings, dict) else {}
    source_status = str((source_object or {}).get("status") or "unresolved")
    unresolved_source_object = phase in {"FIND_LINK", "OPEN_FORWARD"} and source_status in {
        "unresolved",
        "ambiguous",
        "provisional",
    }
    if phase == "PICK_DEST" and not preds.get("destination_picker_visible"):
        state = ForwardTaskState.from_dict(ft)
        state.consistency_rollback()
        state.derive_phase(leftover=False)
        ft = state.to_dict()
        extras["forward_phase"] = state.derived_phase
        extras["forward_task"] = ft
        runtime.execution_state.world_exploration_needed = True
        runtime.execution_state.suppress_observe = False

    if unresolved_source_object:
        runtime.execution_state.suppress_observe = False
        ft["suppress_observe"] = False
        extras["suppress_observe"] = False
        extras["world_exploration_needed"] = True
        runtime.execution_state.world_exploration_needed = True
    elif runtime.execution_state.suppress_observe or int(
        runtime.execution_state.identical_observe_streak or 0
    ) >= 2:
        runtime.execution_state.suppress_observe = True
        ft["suppress_observe"] = True
        ft["binding_repair"] = True
        extras["suppress_observe"] = True
        extras["world_exploration_needed"] = True
        runtime.execution_state.world_exploration_needed = True
    else:
        ft["suppress_observe"] = False
        extras["suppress_observe"] = False
    hints["forward_task"] = ft
    extras["forward_task"] = ft
    _ = (state_sig, entity_count)


def _note_forward_observe(runtime: RuntimeState, state_sig: str) -> None:
    last = runtime.execution_state.last_observe_signature or ""
    if last == state_sig and runtime.execution_state.last_action == "observe":
        runtime.execution_state.identical_observe_streak = (
            int(runtime.execution_state.identical_observe_streak or 0) + 1
        )
    else:
        runtime.execution_state.identical_observe_streak = 1
    runtime.execution_state.last_observe_signature = state_sig
    if runtime.execution_state.identical_observe_streak >= 2:
        runtime.execution_state.suppress_observe = True
        hints = _forward_hints(runtime)
        ft = dict(hints.get("forward_task") or {})
        ft["suppress_observe"] = True
        ft["binding_repair"] = True
        hints["forward_task"] = ft


def _bind_forward_after_execution(runtime: RuntimeState, decision: Action) -> None:
    hints = _forward_hints(runtime)
    fam = (decision.action_family or "").lower()
    # Do NOT retire source_object_selected from invoke_affordance + last_result
    # + ambient picker surface here. That pairs action-specific executor state
    # with a world fact and can latch from a stale/unrelated result.
    # Prerequisites retire via effect_implications once perception establishes
    # forward_picker / named effect predicates (single effect authority).
    if fam in {"select_content", "reveal_actions"} and decision.target_entity_id is not None:
        selected_id = int(decision.target_entity_id)
        # Refuse to latch selection on a left-rail chat-list echo.
        try:
            from plugin.agent.apps.whatsapp_targets import in_sidebar_band

            ents = list(runtime.world_model.entities.values())
            se = runtime.world_model.entities.get(selected_id)
            if se is not None and in_sidebar_band(
                se,
                ents,
                scene_graph=getattr(runtime.world_model, "last_scene_graph", None) or {},
            ):
                return
        except Exception:
            pass
        # Honest predicates: do not latch selected / OPEN_FORWARD from a motor
        # that left incomplete_reveal or geometry_mismatch — phase is a view of
        # world evidence, not intent (live 232919 overclaim → rollback thrash).
        handoff = getattr(runtime.execution_state, "reveal_handoff", None)
        if isinstance(handoff, dict) and handoff.get("incomplete_reveal"):
            return
        closure = getattr(runtime.execution_state, "last_effect_closure", None)
        if isinstance(closure, dict) and (
            closure.get("geometry_mismatch") or closure.get("expected_overlay_missing")
        ):
            return
        result = getattr(runtime.execution_state, "last_result", None)
        try:
            from plugin.agent.executive.effect_implications import (
                execution_authoritatively_ok,
            )

            if not execution_authoritatively_ok(result):
                return
        except Exception:
            return
        if isinstance(result, dict) and str(result.get("status") or "") == "geometry_mismatch":
            return
        hints["source_object_entity_id"] = selected_id
        ft = dict(hints.get("forward_task") or {})
        state = ForwardTaskState.from_dict(ft)
        source_binding = state.binding("source_object")
        source_binding.resolved_entity_id = selected_id
        source_binding.status = "provisional"
        source_binding.confidence = max(source_binding.confidence, 0.7)
        source_binding.evidence = [f"latently_selected entity_id={selected_id}"]
        state.predicates.source_object_visible = True
        # Selection chrome / action surface must corroborate before selected=True.
        extras = {}
        try:
            feats = getattr(runtime.execution_state, "last_features", None)
            extras = getattr(feats, "extras", None) if feats is not None else {}
            if not isinstance(extras, dict) and isinstance(feats, dict):
                extras = feats.get("extras") or {}
        except Exception:
            extras = {}
        surf = str(
            (extras or {}).get("active_surface")
            or getattr(runtime.execution_state, "last_surface", "")
            or ""
        ).strip().lower()
        action_surface = surf in {
            "context_menu",
            "action_menu",
            "selection_mode",
            "forward_picker",
            "dialog",
        }
        grounded = False
        try:
            from plugin.agent.affordance_frontier import grounded_affordance_set_of

            grounded = bool(grounded_affordance_set_of(runtime.execution_state))
        except Exception:
            grounded = bool(
                getattr(runtime.execution_state, "last_grounded_affordance_set", None)
            )
        # select_content may latch selected when motor ok; reveal needs surface/set.
        if fam == "select_content" or action_surface or grounded:
            state.predicates.source_object_selected = True
        state.derive_phase(leftover=False)
        hints["forward_task"] = state.to_dict()
    if fam == "forward_message":
        hints["forward_commit_started"] = True
        try:
            import time as _time

            if float(getattr(runtime.execution_state, "instrumental_commit_at", 0.0) or 0.0) <= 0.0:
                runtime.execution_state.instrumental_commit_at = float(_time.monotonic())
        except Exception:
            pass


def _forward_predicate_gate_after_transition(
    runtime: RuntimeState,
    *,
    decision: Action,
    attempt_outcome: str,
    after_feats: Any,
    log: Optional[EventLogger],
    iteration: int,
    goal: Any = None,
) -> None:
    """Do not keep unsupported phase beliefs after failed transitions."""
    hints = _forward_hints(runtime)
    ft = dict(hints.get("forward_task") or {})
    state = ForwardTaskState.from_dict(ft)
    expected = (decision.expected_predicate or "").strip()
    if (
        attempt_outcome == TransitionOutcome.NO_EFFECT.value
        and (
            decision.action_family == "scroll_content"
            or (decision.action or "").lower() == "scroll"
            or "scroll" in (decision.rationale or "").lower()
        )
    ):
        _log_cycle(
            log,
            iteration=iteration,
            phase="forward_predicate_scroll_no_effect",
            payload={
                "expected": expected,
                "outcome": attempt_outcome,
                "forward_task": ft,
                "after_phase": feature_get(after_feats, "forward_phase"),
            },
            status="ok",
        )
        return
    failed = attempt_outcome in {
        TransitionOutcome.NO_EFFECT.value,
        TransitionOutcome.REGRESSION.value,
    }
    if failed:
        if "SourceObjectSelected" in expected or decision.action_family == "select_content":
            hints.pop("source_object_entity_id", None)
            state.predicates.source_object_selected = False
            state.do_not_advance("source_object_selected", "select_content transition failed")
            obj = state.binding("source_object")
            if obj.status == "confirmed":
                obj.status = "provisional"
        if "DestinationPickerVisible" in expected or decision.action_family == "forward_message":
            state.predicates.destination_picker_visible = False
            state.predicates.forward_surface_open = False
            state.do_not_advance("destination_picker_visible", "forward chrome transition failed")
        state.consistency_rollback()
        state.derive_phase(leftover=False)
        ft = state.to_dict()
        hints["forward_task"] = ft
        _log_cycle(
            log,
            iteration=iteration,
            phase="forward_predicate_rollback",
            payload={
                "expected": expected,
                "outcome": attempt_outcome,
                "forward_task": ft,
                "after_phase": feature_get(after_feats, "forward_phase"),
            },
            status="fail",
        )
    else:
        aft = feature_get(after_feats, "forward_task")
        if isinstance(aft, dict):
            hints["forward_task"] = aft
            ft = aft
        # Post-act identity verify: settled *destination* must satisfy the
        # role(s) the action was meant to establish — not the clicked label.
        fam = str(decision.action_family or "").strip().lower()
        if fam in {"open_entity", "open_contact"}:
            try:
                from plugin.agent.role_binding import (
                    RoleBinder,
                    apply_referent_mismatch,
                    clear_referent_mismatch_debt,
                    note_transition_pending,
                    verify_bound_identity,
                )

                click_label = str(getattr(decision, "semantic_target", "") or "")
                target_kind = str(getattr(decision, "target_kind", "") or "")
                attempt_id = str(getattr(decision, "attempt_id", "") or "").strip()
                legacy = bool(getattr(decision, "legacy_semantics", False))
                typed_nav = (
                    bool(getattr(decision, "action_is_navigation", False))
                    and not legacy
                )
                # Settle authority comes only from Action-stamped contracts —
                # never from ambient ids or phase/label re-inference.
                if typed_nav and not attempt_id:
                    logger.warning(
                        "settle: typed navigation missing Action.attempt_id — "
                        "causal attribution incomplete; refusing debt mutation"
                    )
                    _log_cycle(
                        log,
                        iteration=iteration,
                        phase="causal_attribution_incomplete",
                        payload={
                            "click_target": click_label[:120],
                            "class": "CAUSAL_ATTRIBUTION_INCOMPLETE",
                        },
                        status="fail",
                    )
                    establish_roles = []
                    sem = {
                        "is_navigation": True,
                        "establishes_roles": [],
                        "incomplete": True,
                        "causal_incomplete": True,
                    }
                elif typed_nav:
                    est = [
                        str(r)
                        for r in (getattr(decision, "establishes_roles", None) or [])
                        if str(r).strip()
                    ]
                    sem = {
                        "is_navigation": True,
                        "establishes_roles": est,
                        "target_kind": target_kind,
                        "incomplete": not bool(est),
                    }
                    establish_roles = [] if not est else est
                elif legacy:
                    sem = {
                        "is_navigation": False,
                        "establishes_roles": [],
                        "target_kind": target_kind,
                        "legacy": True,
                    }
                    establish_roles = []
                else:
                    # Explicit container open stamped on Action may establish.
                    est = [
                        str(r)
                        for r in (getattr(decision, "establishes_roles", None) or [])
                        if str(r).strip()
                    ]
                    sem = {
                        "is_navigation": False,
                        "establishes_roles": est if attempt_id else [],
                        "target_kind": target_kind,
                    }
                    establish_roles = list(sem.get("establishes_roles") or [])
                open_name = str(
                    feature_get(after_feats, "open_conversation")
                    or feature_get(after_feats, "active_conversation")
                    or ""
                ).strip()
                goal_obj = goal
                if goal_obj is None:
                    goal_obj = {
                        "contact": str(
                            feature_get(after_feats, "goal_contact") or ""
                        ),
                        "link_query": "",
                        "target_contact": "",
                    }
                contact_ref = str(
                    getattr(goal_obj, "contact", None)
                    or (goal_obj.get("contact") if isinstance(goal_obj, dict) else "")
                    or getattr(goal_obj, "source_contact", None)
                    or (
                        goal_obj.get("source_contact")
                        if isinstance(goal_obj, dict)
                        else ""
                    )
                    or ""
                ).strip()
                # Empty open: navigation/open not settled yet — never terminal.
                # Requires Action.attempt_id (note_transition_pending refuses empty).
                if not open_name:
                    if typed_nav and establish_roles and attempt_id:
                        note_transition_pending(
                            runtime.execution_state,
                            establishes_roles=establish_roles,
                            target_label=click_label,
                            attempt_id=attempt_id,
                        )
                elif establish_roles and attempt_id:
                    binder = RoleBinder()
                    for role in establish_roles:
                        world_fact = {
                            "label": open_name,
                            "title": open_name,
                            "text": open_name,
                            "kind": "conversation",
                            "entity_kind": "conversation",
                            "open_conversation": open_name,
                            "domain": "whatsapp",
                        }
                        ok, proposal = verify_bound_identity(
                            role=role,
                            world_fact=world_fact,
                            goal=goal_obj,
                        )
                        if ok:
                            # Prefer settled open label on the proposal.
                            try:
                                proposal.candidate_label = open_name
                            except Exception:
                                pass
                            # Commit then clear — debt supersede only after commit.
                            new_ft = binder.commit_effect(
                                runtime.execution_state,
                                proposal=proposal,
                                forward_task=dict(hints.get("forward_task") or ft),
                                evidence="settled_destination_verified",
                            )
                            if isinstance(new_ft, dict):
                                hints["forward_task"] = new_ft
                                clear_referent_mismatch_debt(
                                    runtime.execution_state,
                                    role=role,
                                    verified_label=open_name,
                                    attempt_id=attempt_id,
                                )
                                _log_cycle(
                                    log,
                                    iteration=iteration,
                                    phase="role_established",
                                    payload={
                                        "role": role,
                                        "open_conversation": open_name,
                                        "click_target": click_label[:120],
                                        "attempt_id": attempt_id,
                                        "navigation": bool(sem.get("is_navigation")),
                                        "source_object_bound": False,
                                        "class": "SETTLED_DESTINATION_VERIFIED",
                                    },
                                    status="ok",
                                )
                        elif contact_ref:
                            # Settled wrong container — NAVIGATION_MISMATCH when
                            # a content hit opened an incompatible context.
                            new_ft = apply_referent_mismatch(
                                runtime.execution_state,
                                role=role,
                                candidate_label=open_name,
                                forward_task=dict(hints.get("forward_task") or ft),
                                attempt_id=attempt_id,
                            )
                            if isinstance(new_ft, dict):
                                hints["forward_task"] = new_ft
                            nav_class = "REFERENT_MISMATCH"
                            if bool(sem.get("is_navigation")) or bool(
                                getattr(decision, "action_is_navigation", False)
                            ):
                                nav_class = "NAVIGATION_MISMATCH"
                                try:
                                    from plugin.agent.capabilities.search_episode import (
                                        reject_navigation_mismatch_candidate,
                                    )

                                    reject_navigation_mismatch_candidate(
                                        runtime.execution_state,
                                        click_label=click_label,
                                        observed_container=open_name,
                                        required_container=contact_ref,
                                    )
                                except Exception:
                                    pass
                                try:
                                    runtime.execution_state.leave_wrong_conversation_owed = (
                                        True
                                    )
                                    runtime.execution_state.leave_wrong_conversation_open = (
                                        open_name
                                    )
                                    runtime.execution_state.leave_wrong_conversation_source = (
                                        contact_ref
                                    )
                                except Exception:
                                    pass
                                # Ledger: motor ok + wrong semantic container.
                                # Same-method retry is forbidden without new evidence.
                                try:
                                    from plugin.agent.executive.intention_frame import (
                                        AttemptRecord,
                                        AttemptValidity,
                                        FailureClass,
                                        MethodOutcome,
                                        MethodStatus,
                                        active_intention_frame,
                                        apply_derived_status,
                                        mark_method_attempted,
                                        record_method_status,
                                    )
                                    from plugin.agent.executive.effect_implications import (
                                        method_context_from_state,
                                    )

                                    iframe = active_intention_frame(
                                        runtime.execution_state
                                    )
                                    if iframe is not None:
                                        mid = (
                                            f"{fam}:{click_label[:80]}"
                                            if click_label
                                            else fam
                                        )
                                        mark_method_attempted(iframe, mid)
                                        ctx = method_context_from_state(
                                            runtime.execution_state,
                                            world={
                                                "surface": str(
                                                    (
                                                        hints.get("unified_world_document")
                                                        or {}
                                                    ).get("surface")
                                                    or ""
                                                ),
                                                "open_conversation": open_name,
                                            },
                                        )
                                        record_method_status(
                                            iframe,
                                            mid,
                                            MethodStatus.INEFFECTIVE.value,
                                            method_context=ctx,
                                            world_signature=ctx.signature(),
                                        )
                                        iframe.attempts.append(
                                            AttemptRecord(
                                                method_id=mid,
                                                execution_status="motor_ok",
                                                observation_quality=0.9,
                                                method_outcome=(
                                                    MethodOutcome.UNEXPECTED_EFFECT.value
                                                ),
                                                failure_class=(
                                                    FailureClass.NAVIGATION_MISMATCH.value
                                                ),
                                                attempt_validity=(
                                                    AttemptValidity.VALID.value
                                                ),
                                                method_status=(
                                                    MethodStatus.INEFFECTIVE.value
                                                ),
                                                evidence_refs=[
                                                    (
                                                        f"expected={contact_ref!r}"
                                                        f" observed={open_name!r}"
                                                    )[:160]
                                                ],
                                            )
                                        )
                                        apply_derived_status(iframe)
                                except Exception:
                                    pass
                            _log_cycle(
                                log,
                                iteration=iteration,
                                phase="referent_mismatch",
                                payload={
                                    "role": role,
                                    "open_conversation": open_name,
                                    "click_target": click_label[:120],
                                    "attempt_id": attempt_id,
                                    "proposal": proposal.to_dict(),
                                    "class": nav_class,
                                    "failure_class": (
                                        "navigation_mismatch"
                                        if nav_class == "NAVIGATION_MISMATCH"
                                        else "referent_mismatch"
                                    ),
                                },
                                status="fail",
                            )
            except Exception:
                pass
