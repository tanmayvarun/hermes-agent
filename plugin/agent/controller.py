"""Closed-loop goal controller — transition-aware observe → act → observe → evaluate."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol

from plugin.agent.action import Action
from plugin.agent.apps.registry import get_overlay
from plugin.agent.decision import DecisionEngine, get_decision_engine
from plugin.agent.executive.hierarchy import DELIBERATIVE as _DELIBERATIVE
from plugin.agent.executive.meta_action import MetaAction, MetaChoice
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
from plugin.agent.runtime.recovery import maybe_cleanup_for_storage_pressure
from plugin.agent.transition.post_perceive import (
    feature_get,
    settled_empty_search_results,
)
from plugin.agent.transition.types import TransitionSummary
from plugin.worldmodel.entities.normalize import _clean_label
from plugin.agent.whatsapp_view import entities_matching
from plugin.executor.ghost import ExecResult
from plugin.experiments.logger import EventLogger
from plugin.perception.observation import Observation

# Backward alias
PlanStep = Action

_TRUE_ENV = {"1", "true", "yes", "on"}


def _meta_perception_enabled() -> bool:
    """Whether the executive's meta-action drives control flow.

    On by default: the executive is the driver, not an observer. Its meta-action
    (VERIFY / BACKTRACK / ASK_USER / THINK / PROBE) governs the loop — gating the
    top-of-loop re-perceive and pre-empting this frame's grounded decision when
    the move is a control-flow move rather than a plain act. Set
    ``HERMES_META_PERCEPTION`` to ``0``/``false``/``no``/``off`` to fall back to
    the legacy always-perceive loop (the judgement is still computed and
    recorded for observability either way).
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
#
# A plain no-op (no_transition / no_effect, change_score 0) is deliberately NOT
# a surprise here: re-perceiving an identical world tells us nothing. That is the
# stale case, handled by backtrack, not by looking again.
_SURPRISE_EFFECTS = {
    "regression",
    "unexpected_transition",
    "transition_not_perceived",
}
_SURPRISE_OUTCOMES = {
    TransitionOutcome.REGRESSION.value,
    TransitionOutcome.UNCERTAIN.value,
}


def _last_action_surprised(execution_state: Any) -> bool:
    """Did the most recent non-observe action fail to produce the expected world?"""
    attrib = getattr(execution_state, "last_attribution", None)
    if not isinstance(attrib, dict) or not attrib:
        return False
    effect = str(attrib.get("effect_kind") or "").strip().lower()
    outcome = str(attrib.get("outcome") or "").strip().lower()
    return effect in _SURPRISE_EFFECTS or outcome in _SURPRISE_OUTCOMES


def _awaiting_verification(execution_state: Any) -> bool:
    """A non-observe action just fired and its predicted transition is unconfirmed."""
    last_action = str(getattr(execution_state, "last_action", "") or "").strip().lower()
    if not last_action or last_action == "observe":
        return False
    attrib = getattr(execution_state, "last_attribution", None)
    if not isinstance(attrib, dict) or not attrib:
        return False
    outcome = str(attrib.get("outcome") or "").strip().lower()
    return outcome in (
        _SURPRISE_OUTCOMES
        | {TransitionOutcome.PROMISING_UNRESOLVED.value}
    )


def _resolve_exhausted_backtrack(
    meta: "MetaChoice",
    *,
    backtrack_exhausted: bool,
    has_grounded_action: bool,
) -> "MetaChoice":
    """Stop an endless BACKTRACK run once retreating provably cannot help.

    After enough no-progress backtracks the branch space is exhausted: retreating
    again is the thrash the first live executive run exposed (backtrack on ~98 of
    100 iterations). Commit the grounded move if one exists; otherwise escalate,
    because there is nothing left to ground. Returns ``meta`` unchanged when
    backtracks are not exhausted or the move is not a backtrack.
    """
    if backtrack_exhausted and meta.action == MetaAction.BACKTRACK:
        if has_grounded_action:
            return MetaChoice(MetaAction.ACT, "backtracks exhausted; commit the grounded action")
        return MetaChoice(MetaAction.ASK_USER, "backtracks exhausted; nothing can be grounded")
    return meta


def _consume_surprise(execution_state: Any) -> None:
    """Mark the last surprising attribution as handled so VERIFY fires once.

    A VERIFY turn re-perceives and acknowledges the surprise. If the surprise
    stayed on the attribution the executive would verify the same one every
    frame; stamping it verified lets the next frame act on the re-understood
    world instead of looping. The surprise still lives in ``recent_surprises``,
    so perception keeps the pattern.
    """
    attrib = getattr(execution_state, "last_attribution", None)
    if isinstance(attrib, dict):
        updated = dict(attrib)
        updated["outcome"] = "verified"
        updated["effect_kind"] = "verified"
        execution_state.last_attribution = updated


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


# Meta-actions that unconditionally pre-empt this frame's grounded decision.
# VERIFY/BACKTRACK/ASK_USER are terminal-ish control moves. THINK and PROBE are
# deliberate detours handled separately (they are bounded and may fall through
# to acting/observing). PERCEIVE/ACT fall through to the normal decide -> execute
# path (the re-perceive PERCEIVE wants is gated at the top of the loop).
_META_PREEMPTS = {MetaAction.VERIFY, MetaAction.BACKTRACK, MetaAction.ASK_USER}

# THINK forces the next decision onto the deliberative path; PROBE steers it
# toward a reveal. Both are bounded so a persistently ambiguous world escalates
# (falls through to act/observe) instead of thinking or probing forever.
_MAX_CONSECUTIVE_THINKS = 2
_MAX_CONSECUTIVE_PROBES = 3

# Backtracking retreats the branch to explore elsewhere. If it repeats this many
# times with no real move in between, the branch space is exhausted and looking/
# retreating again cannot help (e.g. perception is starved and nothing can be
# grounded); the executive escalates to the user instead of thrashing.
_MAX_CONSECUTIVE_BACKTRACKS = 5

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
    forward_picker / chat_list / search) to know whether an empty open-conversation
    reading is trustworthy. Derived from generic frontier signals, not from a
    WhatsApp-only field.
    """
    if not isinstance(extras, dict):
        extras = {}
    if extras.get("destination_picker_visible"):
        return "forward_picker"
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
    if isinstance(agent_cfg, dict):
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


def resolve_foreground_wait_cap_seconds() -> float:
    """How long the agent may wait for its app to return to the foreground.

    Waiting for the user to return to the task app is *free* — it does not spend
    the step budget or trip the no-progress watchdog — but it is capped so a task
    left permanently backgrounded ends instead of hanging forever. Overridable
    via ``HERMES_FOREGROUND_WAIT_CAP_SECONDS`` (<= 0 waits indefinitely).
    """
    raw = os.getenv("HERMES_FOREGROUND_WAIT_CAP_SECONDS", "")
    try:
        cap = float(raw) if str(raw).strip() else 240.0
    except (TypeError, ValueError):
        cap = 240.0
    if cap <= 0:
        return float("inf")
    return cap


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
) -> GoalResult:
    """
    Trajectory-aware closed loop:

    observe → update belief + interaction context → if goal done: success
    → affordances → experience filter → choose one action
    → execute → TransitionMonitor → re-observe → evaluate outcome
    → on PROMISING_UNRESOLVED: bounded branch exploration (not immediate regression)
    → suppress / continue / backtrack only after clear contradiction or budget
    """

    eng = engine or get_decision_engine()
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

    def _finish_success(
        evidence: Optional[Dict[str, Any]],
        *,
        iterations: int,
    ) -> GoalResult:
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

    # Foreground ownership. The agent owns its goal, so keeping the task app
    # usable is the agent's job, never the user's. Two faculties make that work:
    # perception runs in the *background* (window-scoped capture sees the app
    # regardless of z-order, so a look never needs the app frontmost), and
    # actuation *brings the app to the foreground itself* — keystrokes and clicks
    # land in the frontmost window, so before acting the agent activates its own
    # app, persistently, rather than waiting for the user to do it. The only
    # thing it cannot overcome is a surface it genuinely cannot raise (a locked
    # screen); that is capped so a truly unusable machine ends the run instead of
    # hanging, and the activation time is free (it does not burn the step budget
    # or trip the stall watchdog).
    from plugin.agent.focus_of_action import (
        foreground_app_name,
        foreground_gate_enabled,
        foreground_matches_task,
        task_anchor_app,
    )

    foreground_wait_cap_s = resolve_foreground_wait_cap_seconds()
    foreground_gate_on = foreground_gate_enabled()
    # Families that read/reason only: they use window-scoped capture and the AX
    # tree, neither of which needs the app frontmost, so they never foreground.
    _NON_ACTUATING_FAMILIES = {"observe", "think", "wait", "noop"}

    def _ensure_task_foreground(iteration: int, *, action_family: str) -> tuple[bool, float]:
        """Bring the task app frontmost so the agent can act — the agent's job.

        A no-op for background-capable families and when the app is already
        frontmost. Otherwise the agent activates its own app and retries,
        persistently, until it is frontmost or the cap is hit (a surface it
        cannot raise, e.g. a locked screen). The elapsed time is free.
        """
        nonlocal goal_run_started_at, goal_last_progress_at
        if not foreground_gate_on:
            return True, 0.0
        if str(action_family or "").strip().lower() in _NON_ACTUATING_FAMILIES:
            return True, 0.0
        if foreground_matches_task(goal):
            return True, 0.0
        task_app = task_anchor_app(goal)
        waited = 0.0
        poll = 2.0
        raised = True
        while True:
            # Bringing the app forward is the agent's responsibility: activate it.
            try:
                recover_obscured_target_app(task_app)
            except Exception:
                pass
            _wait(poll, reason="bringing task app to foreground")
            waited += poll
            fg = foreground_app_name()
            _log_cycle(
                log,
                iteration=iteration,
                phase="foregrounding_task_app",
                payload={
                    "foreground_app": fg,
                    "task_app": task_app,
                    "action_family": str(action_family or ""),
                    "waited_s": round(waited, 1),
                    "wait_cap_s": foreground_wait_cap_s,
                    "reason": "activating the task app so the agent can act (the agent owns this, not the user)",
                },
                status="warn",
            )
            if foreground_matches_task(goal, foreground=fg):
                break
            if waited >= foreground_wait_cap_s:
                raised = False
                break
        # Activation time is free: advance both clocks so the baselines are
        # unchanged whether or not the app could be raised.
        goal_run_started_at += waited
        goal_last_progress_at += waited
        return raised, waited

    for iteration in range(1, step_budget + 1):
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
            branch_hint = _invalidate_stale_frontier(
                runtime,
                reason="no_progress_watchdog",
                fallback="observe",
            )
            _log_cycle(
                log,
                iteration=iteration,
                phase="no_progress_replan",
                payload={
                    "elapsed_since_progress_s": round(progress_elapsed, 3),
                    "goal_no_progress_timeout_s": goal_no_progress_timeout_s,
                    "branch_hint": branch_hint,
                    "branch": runtime.execution_state.exploration_branch.to_dict(),
                },
                status="warn",
            )
        runtime.execution_state.tick_search_query_hint()
        # Meta-perception gate: reuse the prior snapshot instead of paying for a
        # re-perceive that cannot tell us more. Two conditions must both hold:
        #  - the world is provably static (the last action moved nothing), so
        #    reusing the previous snapshot is lossless; and
        #  - the executive's last judgement did not want another look (it chose
        #    to act/backtrack, not perceive/probe).
        # This is the executive driving perception rather than the old
        # always-perceive default, without the risk of reusing a stale view
        # after an action that actually changed the world.
        skip_reperception = (
            meta_perception_enabled
            and prev_snap_pre is not None
            and prev_static_streak >= 1
            and prev_meta_suppress
            # A surprise from the last action means our model of what happened is
            # wrong — always re-perceive to re-understand, never reuse.
            and not _last_action_surprised(runtime.execution_state)
        )
        if skip_reperception:
            snap_pre = prev_snap_pre
            _log_cycle(
                log,
                iteration=iteration,
                phase="perception_skipped",
                payload={
                    "reason": "executive judged re-perception low value on a stable world",
                    "meta_suppressed": prev_meta_suppress,
                    "static_streak": prev_static_streak,
                    "last_meta_action": getattr(
                        runtime.execution_state, "last_meta_action", None
                    ),
                },
            )
        else:
            snap_pre = refresh_perception(
                runtime,
                goal,
                observe=observe,
                action_label=runtime.execution_state.last_action or "observe",
                log_fn=_perception_log_fn(log, iteration),
                iteration=iteration,
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
        # re-observing once before decide.
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

        storage_cleanup = maybe_cleanup_for_storage_pressure(
            runtime,
            view=view,
            features=feats_pre,
            observation_texts=[
                getattr(node, "name", "") or getattr(node, "description", "")
                for node in (observation.nodes or [])
            ],
            execution_message=str((runtime.execution_state.last_result or {}).get("message") or ""),
            reason_hint=str(goal.description or goal.kind),
        )
        if storage_cleanup is not None:
            _log_cycle(
                log,
                iteration=iteration,
                phase="storage_cleanup",
                payload=storage_cleanup.to_dict(),
                status="ok",
            )
            _wait(max(settle_s, 0.4), "storage pressure cleanup")
            continue

        # Forward: suppress identical Observe before decide
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

        if patch.retention < retention_floor and runtime.execution_state.iteration > 0:
            _wait(settle_s, "identity retention collapse — re-observe")
            snap = refresh_perception(
                runtime,
                goal,
                observe=observe,
                action_label="reobserve_low_retention",
                log_fn=_perception_log_fn(log, iteration),
                iteration=iteration,
            )
            patch = snap.patch or patch
            runtime.execution_state.bump_world_id(significant=True)
            wv = snap.worldview
            view = snap.view
            observation = snap.observation or observation
            state_sig = _semantic_state_signature(view=view, features=feats_pre, world_id=runtime.execution_state.world_id)

        # Low worldview / fusion conflict → re-perceive (skip thrash when hyps remain)
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
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="worldview_low",
                    payload={
                        "worldview_score": patch.worldview_score,
                        "threshold": WORLDVIEW_LOW,
                        "needs_reobserve": needs_reobs,
                    },
                    status="fail" if wv < WORLDVIEW_LOW else "ok",
                )
                _wait(max(settle_s, 0.4), "low worldview / fusion conflict — re-observe")
                snap = refresh_perception(
                    runtime,
                    goal,
                    observe=observe,
                    action_label="reobserve_low_worldview",
                    log_fn=_perception_log_fn(log, iteration),
                    iteration=iteration,
                )
                patch = snap.patch or patch
                runtime.execution_state.bump_world_id(significant=True)
                wv = snap.worldview
                view = snap.view
                observation = snap.observation or observation
                state_sig = _semantic_state_signature(view=view, features=feats_pre, world_id=runtime.execution_state.world_id)

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

        before_world_id = runtime.execution_state.world_id
        before_fp = world_fingerprint(runtime.world_model, view)
        before_view = dict(view)
        before_feats = _feature_dict(runtime, goal, wv)

        # Per-turn token so any reading persisted during decide() (e.g. the
        # unified proposal's evidence_gaps / coverage / belief patch) can be
        # matched to *this* loop turn. execution_state.iteration only advances on
        # executed actions, so it cannot be used as the frame here.
        runtime.execution_state.decision_frame = iteration
        decision = eng.decide(
            goal,
            runtime.world_model,
            runtime.execution_state,
            worldview_score=wv,
            state_signature=state_sig,
            state_experience=experience,
        )
        overlay = get_overlay(goal.app, runtime.world_model)
        feats = overlay.features(runtime.world_model, goal, worldview_score=wv)

        # --- Executive judgement: one authoritative act-vs-perceive verdict ---
        # Computed and recorded every iteration for observability. Under
        # HERMES_META_PERCEPTION it also gates the next iteration's re-perceive.
        has_grounded_action = bool(decision) and str(decision.action or "").strip().lower() != "observe"
        coverage = float(wv or 0.0)
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
            # re-searching them (they drop out of blocking) and escalates instead
            # of hunting the same unanswerable thing forever.
            for q in blocking_uncertainties:
                settle_exploration_question(
                    runtime.execution_state,
                    question=str(q),
                    answered=False,
                    evidence="branch space exhausted",
                )
        hard_block = backtrack_exhausted and not has_grounded_action
        if action_surprised:
            # Record the surprise into the bounded history perception attends to,
            # so the model sees the pattern of recent failures, not just the last.
            _attrib = getattr(runtime.execution_state, "last_attribution", None) or {}
            _ev = _attrib.get("evidence") if isinstance(_attrib.get("evidence"), dict) else {}
            runtime.execution_state.note_surprise(
                {
                    "iteration": iteration,
                    "action": str(getattr(runtime.execution_state, "last_action", "") or ""),
                    "family": str(_attrib.get("action_family") or ""),
                    "effect": str(_attrib.get("effect_kind") or ""),
                    "outcome": str(_attrib.get("outcome") or ""),
                    "failure_domain": str(_attrib.get("likely_failure_domain") or ""),
                    "world_change_score": _ev.get("change_score"),
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
        stuck_without_route = (
            not has_grounded_action
            and not action_surprised
            and not blocking_uncertainties
            and not backtrack_exhausted
        )
        ambiguous = contradiction_count > 0 or stuck_without_route
        steps_remaining = max(0, step_budget - iteration + 1)
        # Consult the goal contract: what "done" means and what must hold. When
        # every success condition is met the executive verifies completion (ladder
        # rung 0) rather than trusting a single grounded move — the executive, not
        # a submodule, owns the completion judgement.
        contract = contract_status(runtime.execution_state)
        contract_complete = bool(contract.get("all_satisfied"))
        sufficiency, meta = assess_executive_judgement(
            runtime.execution_state,
            blocking_uncertainties=blocking_uncertainties,
            evidence_gaps=perceptor_gaps,
            coverage=perceptor_coverage,
            has_grounded_action=has_grounded_action,
            previously_suppressed=prev_meta_suppress,
            last_action_surprised=action_surprised,
            awaiting_verification=awaiting_verification,
            hard_block=hard_block,
            probe_available=probe_available,
            ambiguous=ambiguous,
            steps_remaining=steps_remaining,
            goal_complete=contract_complete,
        )
        # Backtracks exhausted: stop retreating (commit or escalate). Without this
        # the executive prefers BACKTRACK (higher value than a thin ACT) forever,
        # which is the thrash the first live run exposed.
        meta = _resolve_exhausted_backtrack(
            meta,
            backtrack_exhausted=backtrack_exhausted,
            has_grounded_action=has_grounded_action,
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
                "sufficiency": sufficiency.to_dict(),
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
                "blocking_uncertainties": [str(q) for q in blocking_uncertainties][:8],
                "static_streak": static_streak,
                "beliefs": beliefs_payload,
                "goal_contract": {
                    "satisfied": [str(s) for s in (contract.get("satisfied") or [])],
                    "pending": [str(s) for s in (contract.get("pending") or [])],
                    "constraints": [str(c) for c in (contract.get("constraints") or [])],
                    "all_satisfied": contract_complete,
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
        # path already honours via force_deliberation. THINK/PROBE set the same
        # flag for their own reasons; setting it here is idempotent.
        if (
            meta_perception_enabled
            and getattr(runtime.execution_state, "last_cognitive_mode", "") == _DELIBERATIVE
            and meta.action not in _META_PREEMPTS
        ):
            runtime.execution_state.force_deliberation = True

        # --- Meta-action as a real loop phase ---
        # Under HERMES_META_PERCEPTION the executive's meta-action does not only
        # gate perception: VERIFY / BACKTRACK / ASK_USER are control-flow moves
        # that pre-empt executing this frame's grounded decision. ACT / THINK /
        # PERCEIVE / PROBE fall through to the normal decide -> execute path.
        if meta_perception_enabled and meta.action in _META_PREEMPTS:
            _log_cycle(
                log,
                iteration=iteration,
                phase="meta_action_phase",
                payload={"meta_action": meta.to_dict(), "handling": meta.action.value},
                status="warn" if meta.action == MetaAction.ASK_USER else "ok",
            )
            if meta.action == MetaAction.ASK_USER:
                return _finish_failure(
                    "executive escalated to the user: no self-serve move resolves the block",
                    {
                        "meta_action": meta.to_dict(),
                        "app_view": view,
                        "consecutive_backtracks": int(
                            getattr(runtime.execution_state, "consecutive_backtracks", 0) or 0
                        ),
                        "blocking_uncertainties": [str(q) for q in blocking_uncertainties][:8],
                    },
                    iterations=iteration,
                )
            if meta.action == MetaAction.BACKTRACK:
                # The branch has gone stale. Retreat by invalidating the current
                # frontier so the next decision explores elsewhere, instead of
                # committing this frame's stale-branch action.
                runtime.execution_state.consecutive_backtracks = (
                    int(getattr(runtime.execution_state, "consecutive_backtracks", 0) or 0) + 1
                )
                branch_hint = _invalidate_stale_frontier(
                    runtime, reason="executive_backtrack", fallback="observe"
                )
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="meta_backtrack",
                    payload={
                        "branch_hint": branch_hint,
                        "branch": runtime.execution_state.exploration_branch.to_dict(),
                        "consecutive_backtracks": runtime.execution_state.consecutive_backtracks,
                    },
                    status="warn",
                )
            elif meta.action == MetaAction.VERIFY:
                # The last action surprised us; we have already re-perceived this
                # frame. Consume the surprise so we verify it once, then spend the
                # turn confirming rather than committing a move we cannot trust.
                _consume_surprise(runtime.execution_state)
                # Verifying is a real move, not a retreat: the backtrack run ends.
                runtime.execution_state.consecutive_backtracks = 0
            # A terminal control move is neither a think nor a probe streak.
            runtime.execution_state.consecutive_thinks = 0
            runtime.execution_state.consecutive_probes = 0
            # Both VERIFY and BACKTRACK want a fresh look next iteration — never
            # let the perception gate reuse the prior snapshot after a meta move.
            prev_meta_suppress = False
            _wait(settle_s, f"executive {meta.action.value}")
            continue

        # --- THINK / PROBE: deliberate detours that steer the next decision ---
        # Unlike the terminal preempts these are bounded: a world that stays
        # ambiguous or unreveal-able escalates to acting/observing rather than
        # thinking or probing in place forever (the re-search failure class).
        if meta_perception_enabled and meta.action == MetaAction.THINK:
            runtime.execution_state.consecutive_backtracks = 0
            runtime.execution_state.consecutive_probes = 0
            think_n = int(getattr(runtime.execution_state, "consecutive_thinks", 0) or 0) + 1
            runtime.execution_state.consecutive_thinks = think_n
            if think_n <= _MAX_CONSECUTIVE_THINKS:
                # Force the next decision onto the deliberative path (skip the
                # multimodal fast path so the enumerate/score/consult reasoner runs).
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
                    "handling": "exhausted_fall_through",
                },
                status="warn",
            )
            runtime.execution_state.consecutive_thinks = 0
        elif meta_perception_enabled and meta.action == MetaAction.PROBE:
            runtime.execution_state.consecutive_backtracks = 0
            runtime.execution_state.consecutive_thinks = 0
            probe_n = int(getattr(runtime.execution_state, "consecutive_probes", 0) or 0) + 1
            runtime.execution_state.consecutive_probes = probe_n
            if probe_n <= _MAX_CONSECUTIVE_PROBES:
                # Steer the next decision toward a reveal: invalidate the current
                # frontier so the model re-explores what a reversible action would
                # expose, and force the deliberative path to pick it.
                branch_hint = _invalidate_stale_frontier(
                    runtime, reason="executive_probe", fallback="observe"
                )
                runtime.execution_state.force_deliberation = True
                _log_cycle(
                    log,
                    iteration=iteration,
                    phase="meta_probe",
                    payload={
                        "meta_action": meta.to_dict(),
                        "branch_hint": branch_hint,
                        "consecutive_probes": probe_n,
                    },
                )
                prev_meta_suppress = False
                _wait(settle_s, "executive probe")
                continue
            _log_cycle(
                log,
                iteration=iteration,
                phase="meta_probe",
                payload={
                    "meta_action": meta.to_dict(),
                    "consecutive_probes": probe_n,
                    "handling": "exhausted_fall_through",
                },
                status="warn",
            )
            runtime.execution_state.consecutive_probes = 0

        # Any non-preempting frame (we are about to observe/act normally) breaks a
        # backtrack / think / probe run: the branch is no longer being retreated.
        runtime.execution_state.consecutive_backtracks = 0
        runtime.execution_state.consecutive_thinks = 0
        runtime.execution_state.consecutive_probes = 0

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

        # About to actuate: keystrokes/clicks land in the frontmost window, so
        # ensure the task app is frontmost first — the agent raises its own app
        # rather than waiting for the user. Background-capable families skip this.
        fg_raised, fg_waited_s = _ensure_task_foreground(
            iteration, action_family=decision.action_family
        )
        if not fg_raised:
            _log_cycle(
                log,
                iteration=iteration,
                phase="foreground_unavailable",
                payload={
                    "foreground_app": foreground_app_name(),
                    "task_app": task_anchor_app(goal),
                    "action_family": decision.action_family,
                    "waited_s": round(fg_waited_s, 1),
                    "wait_cap_s": foreground_wait_cap_s,
                    "reason": "could not raise the task app to act (screen locked or activation blocked)",
                },
                status="fail",
            )
            return _finish_failure(
                "could not bring the task app to the foreground to act",
                {
                    "foreground_app": foreground_app_name(),
                    "task_app": task_anchor_app(goal),
                    "waited_s": round(fg_waited_s, 1),
                },
                iterations=iteration - 1,
            )

        execution = execute.execute(decision)
        runtime.execution_state.record(decision, execution.__dict__)
        _observe_capability_reliability(decision, execution.ok)
        _log_cycle(
            log,
            iteration=iteration,
            phase="execution",
            payload={**execution.__dict__, "plan_step": decision.__dict__, "world_id": before_world_id},
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
            runtime.execution_state.last_attribution = attrib.to_dict()
            _apply_actuation_suppression(runtime, decision, attrib.to_dict())
            runtime.execution_state.world_exploration_needed = True
            experience.pending_backtrack_family = "observe"
            _log_cycle(
                log,
                iteration=iteration,
                phase="transition_attribution",
                payload=attrib.to_dict(),
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
        attrib_dict = attempt.attribution or {}
        runtime.execution_state.last_attribution = attrib_dict
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

        if attempt.outcome == TransitionOutcome.PROMISING_UNRESOLVED.value:
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
            runtime.execution_state.record_failure(f"regression:{decision.action_family}")
            key = runtime.execution_state.action_key(decision)
            runtime.execution_state.prohibited_actions[key] = max(
                runtime.execution_state.prohibited_actions.get(key, 0), 4
            )
            branch = runtime.execution_state.exploration_branch
            if branch.active:
                branch.contradiction_count += 1
            runtime.execution_state.exploration_branch = ExplorationBranch()
            runtime.execution_state.world_exploration_needed = True
            experience.pending_backtrack_family = _frontier_backtrack_hint(branch)
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
    if fam == "select_content" and decision.target_entity_id is not None:
        selected_id = int(decision.target_entity_id)
        hints["source_object_entity_id"] = selected_id
        ft = dict(hints.get("forward_task") or {})
        state = ForwardTaskState.from_dict(ft)
        source_binding = state.binding("source_object")
        source_binding.resolved_entity_id = selected_id
        source_binding.status = "provisional"
        source_binding.confidence = max(source_binding.confidence, 0.7)
        source_binding.evidence = [f"latently_selected entity_id={selected_id}"]
        state.predicates.source_object_visible = True
        state.predicates.source_object_selected = True
        state.derive_phase(leftover=False)
        hints["forward_task"] = state.to_dict()
    if fam == "forward_message":
        hints["forward_commit_started"] = True


def _forward_predicate_gate_after_transition(
    runtime: RuntimeState,
    *,
    decision: Action,
    attempt_outcome: str,
    after_feats: Any,
    log: Optional[EventLogger],
    iteration: int,
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
