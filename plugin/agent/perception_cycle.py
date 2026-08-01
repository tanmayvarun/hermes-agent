"""Reusable observe → fuse/ingest → update world/features perception cycle.

Controller, recovery, and post-action gates should all call this — not inline
``observe(); ingest(); features()`` scrapes. Fusion runs inside ``WorldModel.ingest``.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

from plugin.agent.apps.registry import get_overlay
from plugin.agent.goal import Goal
from plugin.agent.perception_synthesis import (
    _perception_fail_hard,
    _format_perception_human_readable,
    synthesize_perception,
)
from plugin.agent.procedure import current_procedure_stage
from plugin.agent.runtime.state import RuntimeState
from plugin.agent.transition.post_perceive import (
    PerceptionAssessment,
    assess_post_action_perception,
    profile_for,
)
from plugin.perception.observation import Observation
from plugin.perception.representation import build_perception_result, structured_perception_bridge
from plugin.perception.sources.base import format_observation_raw_summary
from plugin.worldmodel.model import WorldPatch

ObserveFn = Callable[[], Observation]
WaitFn = Callable[[float, str], None]
LogFn = Callable[..., None]


@dataclass
class PerceptionSnapshot:
    """One settled (or best-effort) world belief update."""

    observation: Optional[Observation] = None
    patch: Optional[WorldPatch] = None
    view: Dict[str, Any] = field(default_factory=dict)
    features: Dict[str, Any] = field(default_factory=dict)
    worldview: float = 1.0
    assessment: Optional[PerceptionAssessment] = None
    retries: int = 0
    settled: bool = True
    action_label: str = "observe"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_label": self.action_label,
            "retries": self.retries,
            "settled": self.settled,
            "worldview": self.worldview,
            "world_id": None,
            "assessment": None if self.assessment is None else self.assessment.to_dict(),
            "view_screen": self.view.get("screen"),
            "search_query": self.view.get("search_query"),
            "needs_reobserve": bool(self.features.get("needs_reobserve")),
            "perception_incomplete": bool(
                (self.features.get("extras") or {}).get("perception_incomplete")
            ),
        }


def _perception_stall_signature(action_family: str, snap: PerceptionSnapshot) -> str:
    view = snap.view or {}
    feats = snap.features or {}
    extras = feats.get("extras") if isinstance(feats.get("extras"), dict) else {}
    parts = {
        "action_family": str(action_family or "").strip().lower(),
        "screen": str(view.get("screen") or feats.get("screen_bucket") or "").strip().lower(),
        "search_query": str(view.get("search_query") or extras.get("search_query") or "").strip().lower(),
        "open_conversation": str(view.get("open_conversation") or extras.get("open_conversation") or "").strip().lower(),
        "call_state": str(view.get("call_state") or extras.get("call_state") or "").strip().lower(),
        "failure_modes": list((snap.assessment.failure_modes if snap.assessment else []) or []),
    }
    return str(parts)


def _worldview(runtime: RuntimeState) -> float:
    score = runtime.world_model.last_worldview_score or {}
    try:
        return float(score.get("overall", 1.0))
    except (TypeError, ValueError):
        return 1.0


def _log_raw_observation(
    log_fn: Optional[LogFn],
    *,
    phase: str,
    observation: Observation,
    action_label: str,
    iteration: int = 0,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    if log_fn is None:
        return
    raw_summary = format_observation_raw_summary(observation, max_nodes=12, max_message_like=8)
    payload: Dict[str, Any] = {
        "action_label": action_label,
        "app": observation.app_name,
        "window": observation.window_name,
        "source": observation.source,
        "nodes": len(observation.nodes or []),
        "coverage": observation.coverage,
        "degraded": observation.degraded,
        "screenshot": observation.screenshot_path,
        "screenshot_available": bool(observation.screenshot_path),
        "screenshot_error": (observation.meta or {}).get("screenshot_error"),
        "raw_trace": raw_summary,
    }
    if extra:
        payload.update(extra)
    log_fn(
        phase=phase,
        payload=payload,
        status="ok",
        iteration=iteration,
    )


def _sync_overlay_hint(runtime: RuntimeState) -> str:
    hint = runtime.execution_state.peek_search_query_hint()
    if hint:
        runtime.world_model.overlay_hints["search_query"] = hint
    else:
        runtime.world_model.overlay_hints.pop("search_query", None)
    return hint


def build_view_features(
    runtime: RuntimeState,
    goal: Goal,
    *,
    worldview: Optional[float] = None,
    screenshot_path: Optional[str] = None,
    log_fn: Optional[LogFn] = None,
) -> tuple[Dict[str, Any], Dict[str, Any], float]:
    """Update overlay view + StateFeatures from current world model (no new observe)."""
    proc = goal.ensure_procedure()
    _sync_overlay_hint(runtime)
    wv = _worldview(runtime) if worldview is None else worldview
    overlay = get_overlay(goal.app, runtime.world_model)
    view = overlay.raw_view_dict(runtime.world_model) if hasattr(overlay, "raw_view_dict") else overlay.view_dict(runtime.world_model)
    feats = overlay.features(runtime.world_model, goal, worldview_score=wv).to_dict()
    # Stage 3–7: enrich geometry graph with affordances + goal attention (generic)
    scene = getattr(runtime.world_model, "last_scene_graph", None) or {}
    if not scene:
        try:
            from plugin.worldmodel.scene.reconstruct import reconstruct_world_graph

            scene = reconstruct_world_graph(
                list(runtime.world_model.entities.values()),
                app=runtime.world_model.active_app or goal.app,
                source_patch_id="view_features",
            ).to_dict()
            runtime.world_model.last_scene_graph = scene
            # App vocabulary is a hint layer under pragmatic roles
            try:
                from plugin.worldmodel.pragmatic_role import (
                    WA_CTA_LABELS,
                    WA_NAV_LABELS,
                    WA_STATUS_LABELS,
                    apply_app_vocabulary_hints,
                )

                if "whatsapp" in (runtime.world_model.active_app or goal.app or "").lower():
                    apply_app_vocabulary_hints(
                        list(runtime.world_model.entities.values()),
                        nav_labels=WA_NAV_LABELS,
                        cta_labels=WA_CTA_LABELS,
                        status_labels=WA_STATUS_LABELS,
                    )
            except Exception:
                pass
        except Exception:
            scene = {}
    if scene and not scene.get("error"):
        try:
            from plugin.worldmodel.scene.affordances import enrich_world_graph
            from plugin.worldmodel.scene.types import WorldGraph
            from plugin.worldmodel.capability import build_capability_graph

            graph = WorldGraph.from_dict(scene)
            graph = enrich_world_graph(
                graph,
                list(runtime.world_model.entities.values()),
                goal=goal,
            )
            scene = graph.to_dict()
            runtime.world_model.last_scene_graph = scene
            capability_hints = getattr(overlay, "capability_hints", None)
            hints = capability_hints(goal) if callable(capability_hints) else None
            capability_graph = build_capability_graph(
                graph,
                list(runtime.world_model.entities.values()),
                goal=goal,
                capability_hints=hints,
            )
            runtime.world_model.last_capability_graph = capability_graph.to_dict()
            runtime.world_model.last_interaction_graph = graph.context_graph.to_dict()
            if runtime.patches:
                runtime.patches[-1].scene_graph = scene
                runtime.patches[-1].capability_graph = capability_graph.to_dict()
                runtime.patches[-1].interaction_graph = graph.context_graph.to_dict()
        except Exception:
            pass
    held_last_good_world = bool(
        ((runtime.world_model.last_worldview_score or {}).get("components") or {}).get(
            "held_last_good_world"
        )
    )
    if not getattr(runtime.world_model, "last_capability_graph", None):
        try:
            from plugin.worldmodel.capability import build_capability_graph
            from plugin.worldmodel.scene.types import WorldGraph

            fallback_scene = WorldGraph.from_dict(scene) if scene and not scene.get("error") else WorldGraph()
            capability_hints = getattr(overlay, "capability_hints", None)
            hints = capability_hints(goal) if callable(capability_hints) else None
            capability_graph = build_capability_graph(
                fallback_scene,
                list(runtime.world_model.entities.values()),
                goal=goal,
                capability_hints=hints,
            )
            runtime.world_model.last_capability_graph = capability_graph.to_dict()
            runtime.world_model.last_interaction_graph = fallback_scene.context_graph.to_dict()
            if runtime.patches:
                runtime.patches[-1].capability_graph = capability_graph.to_dict()
                runtime.patches[-1].interaction_graph = fallback_scene.context_graph.to_dict()
        except Exception:
            pass
    extras = feats.setdefault("extras", {})
    if isinstance(extras, dict):
        if screenshot_path:
            extras["screenshot_path"] = screenshot_path
        worldview_components = (
            (runtime.world_model.last_worldview_score or {}).get("components") or {}
        )
        extras["observation_node_count"] = int(
            worldview_components.get("node_count") or len(runtime.world_model.entities) or 0
        )
        extras["app_content_node_count"] = int(worldview_components.get("app_content_node_count") or 0)
        extras["chrome_only_node_count"] = int(worldview_components.get("chrome_only_node_count") or 0)
        extras["task_sufficient"] = bool(worldview_components.get("task_sufficient", True))
        extras["observation_degenerate"] = bool(extras["observation_node_count"] <= 1)
        if held_last_good_world:
            extras["held_last_good_world"] = True
        if proc is not None:
            extras["selected_procedure_id"] = proc.id
            extras["selected_procedure_title"] = proc.title
            extras["selected_procedure_score"] = round(float(goal.procedure_score or 0.0), 4)
            extras["selected_procedure_reasons"] = list(goal.procedure_reasons or [])
            extras["selected_procedure"] = proc.to_dict()
            stage = current_procedure_stage(goal, feats)
            if stage is not None:
                extras["selected_procedure_stage"] = stage
                extras["selected_procedure_stage_id"] = str(stage.get("stage_id") or "")
                extras["selected_procedure_stage_objective"] = str(stage.get("stage_objective") or "")
                extras["selected_procedure_stage_required_predicates"] = list(
                    stage.get("required_predicates") or []
                )
                extras["selected_procedure_stage_satisfied_predicates"] = list(
                    stage.get("satisfied_predicates") or []
                )
                extras["selected_procedure_stage_missing_predicates"] = list(
                    stage.get("missing_predicates") or []
                )
                extras["selected_procedure_stage_preferred_capabilities"] = list(
                    stage.get("preferred_capabilities") or []
                )
                extras["selected_procedure_stage_recovery"] = list(stage.get("recovery") or [])
                extras["selected_procedure_stage_reversible"] = bool(stage.get("reversible", True))
                extras["selected_procedure_stage_confidence_threshold"] = round(
                    float(stage.get("confidence_threshold") or 0.0),
                    4,
                )
                extras["selected_procedure_stage_progress"] = round(
                    float(stage.get("stage_progress") or 0.0),
                    4,
                )
                extras["selected_procedure_progress"] = round(
                    float(stage.get("procedure_progress") or 0.0),
                    4,
                )
        extras["interaction_graph"] = getattr(runtime.world_model, "last_interaction_graph", {}) or {}
        extras["capability_graph"] = getattr(runtime.world_model, "last_capability_graph", {}) or {}
        if runtime.world_model.last_worldview_score:
            extras["worldview_score_components"] = dict(
                (runtime.world_model.last_worldview_score or {}).get("components") or {}
            )
        if scene:
            extras["world_graph"] = scene
            report = scene.get("report") or {}
            extras["scene_layout_confidence"] = report.get("layout_confidence")
            extras["scene_region_coverage"] = report.get("region_coverage")
            extras["scene_affordance_entropy"] = report.get("affordance_entropy")
            extras["scene_region_kinds"] = [
                r.get("kind") for r in (scene.get("regions") or []) if isinstance(r, dict)
            ]
            attn = scene.get("attention") or {}
            extras["scene_attention_regions"] = list(attn.get("region_ids") or [])
            extras["scene_attention_entities"] = list(attn.get("entity_ids") or [])
        cap_graph = extras.get("capability_graph") or {}
        if isinstance(cap_graph, dict):
            extras["goal_capability_ids"] = list(cap_graph.get("goal_capability_ids") or [])
            extras["capability_frontier"] = list(cap_graph.get("frontier") or [])
            goal_caps = list(cap_graph.get("goal_capability_ids") or [])
            if goal_caps:
                extras["selected_capability"] = goal_caps[0]
            else:
                node_keys = list((cap_graph.get("nodes") or {}).keys())
                extras["selected_capability"] = node_keys[0] if node_keys else ""
        if "screenshot_error" in (runtime.world_model.last_worldview_score or {}):
            extras["screenshot_error"] = (runtime.world_model.last_worldview_score or {}).get(
                "screenshot_error"
            )
    try:
        perception = synthesize_perception(
            goal,
            runtime.world_model,
            view,
            feats,
            worldview=wv,
        )
        if perception is not None:
            extras = feats.setdefault("extras", {})
            if isinstance(extras, dict):
                extras["perception_llm"] = perception.to_dict()
                extras["perception_summary"] = {
                    "screen_type": perception.screen_type,
                    "active_surface": perception.active_surface,
                    "likely_next_family": perception.likely_next_family,
                    "likely_next_target": perception.likely_next_target,
                    "confidence": round(float(perception.confidence or 0.0), 4),
                }
            summary_text = _format_perception_human_readable(
                perception,
                task_name=str((feats.get("extras") or {}).get("perception_task") or ""),
                target=(feats.get("extras") or {}).get("perception_llm", {}).get("selected_target")
                if isinstance((feats.get("extras") or {}).get("perception_llm"), dict)
                else None,
                cache_hit=False,
            )
            if log_fn is not None:
                log_fn(
                    phase="perception_summary",
                    payload={
                        "message": summary_text,
                        "detail": summary_text,
                        "text": summary_text,
                        "screen_type": perception.screen_type,
                        "active_surface": perception.active_surface,
                        "likely_next_family": perception.likely_next_family,
                        "likely_next_target": perception.likely_next_target,
                        "likely_next_text": perception.likely_next_text,
                        "confidence": round(float(perception.confidence or 0.0), 4),
                        "avoid_families": list(perception.avoid_families or []),
                        "needs_followup_observe": bool(perception.needs_followup_observe),
                    },
                    status="ok",
                    iteration=0,
                )
            summary_cb = getattr(runtime, "perception_summary_callback", None)
            if callable(summary_cb) and summary_text:
                try:
                    summary_cb(summary_text)
                except Exception:
                    pass
    except Exception as exc:
        from agent.auxiliary_client import LLMProviderExhaustedError

        if isinstance(exc, LLMProviderExhaustedError) or _perception_fail_hard():
            raise
        pass
    extras = feats.setdefault("extras", {})
    if isinstance(extras, dict) and not extras.get("perception_result"):
        try:
            structured = build_perception_result(runtime.world_model, view, feats, goal=goal)
            extras["perception_result"] = structured.to_dict()
            extras["perception_narrative"] = structured.narrative
            extras["perception_summary"] = structured_perception_bridge(structured.to_dict(), features=feats)
        except Exception:
            pass
    return view, feats, wv


def apply_observation(
    runtime: RuntimeState,
    goal: Goal,
    obs: Observation,
    *,
    action_label: str = "observe",
    target_entity_id: Optional[int] = None,
    log_fn: Optional[LogFn] = None,
    iteration: int = 0,
) -> PerceptionSnapshot:
    """
    Fuse/update half of the cycle: ingest observation → view/features.

    Use when the caller already observed (TransitionMonitor, recovery with a fixed
    Observation). Prefer ``refresh_perception`` when you own the observe callback.
    """
    _log_raw_observation(
        log_fn,
        phase="observation_raw",
        observation=obs,
        action_label=action_label,
        iteration=iteration,
        extra={
            "target_entity_id": target_entity_id,
            "world_id": runtime.execution_state.world_id,
        },
    )
    patch = runtime.world_model.ingest(
        obs,
        action=action_label,
        target_entity_id=target_entity_id,
    )
    runtime.patches.append(patch)
    view, feats, wv = build_view_features(
        runtime,
        goal,
        screenshot_path=obs.screenshot_path,
        log_fn=log_fn,
    )
    if obs.meta and isinstance(obs.meta, dict):
        extras = feats.setdefault("extras", {})
        if isinstance(extras, dict):
            if obs.meta.get("screenshot_error"):
                extras["screenshot_error"] = obs.meta.get("screenshot_error")
    if log_fn is not None:
        extras = feats.get("extras") if isinstance(feats, dict) else {}
        structured = (extras or {}).get("perception_result") if isinstance(extras, dict) else None
        structured_summary = structured if isinstance(structured, dict) else {}
        sensors = structured_summary.get("sensors") if isinstance(structured_summary.get("sensors"), list) else []
        sensor_kinds = [str(sensor.get("kind") or "") for sensor in sensors if isinstance(sensor, dict)]
        sensor_sources = [str(sensor.get("source") or "") for sensor in sensors if isinstance(sensor, dict)]
        sensor_summaries = [str(sensor.get("summary") or "") for sensor in sensors if isinstance(sensor, dict)]
        transition = structured_summary.get("transition") if isinstance(structured_summary.get("transition"), dict) else {}
        log_fn(
            phase="observation_fused",
            payload={
                "action_label": action_label,
                "screen": view.get("screen"),
                "search_query": view.get("search_query"),
                "open_conversation": view.get("open_conversation"),
                "call_state": view.get("call_state"),
                "worldview": round(float(wv or 0.0), 4),
                "worldview_score": patch.worldview_score,
                "retention": patch.retention,
                "needs_reobserve": bool(getattr(patch, "needs_reobserve", False)),
                "fusion_conflicts": list(getattr(patch, "conflicts", None) or [])[:8],
                "belief_updates": list(getattr(patch, "belief_updates", None) or [])[:8],
                "observation_node_count": (extras or {}).get("observation_node_count"),
                "app_content_node_count": (extras or {}).get("app_content_node_count"),
                "chrome_only_node_count": (extras or {}).get("chrome_only_node_count"),
                "task_sufficient": (extras or {}).get("task_sufficient"),
                "screenshot_error": (extras or {}).get("screenshot_error"),
                "perception_result_status": transition.get("status") or structured_summary.get("phase"),
                "perception_primary_surface": structured_summary.get("primary_surface_id"),
                "perception_active_object_ids": list(structured_summary.get("active_object_ids") or [])[:8],
                "perception_active_relation_ids": list(structured_summary.get("active_relation_ids") or [])[:8],
                "perception_sensor_kinds": sensor_kinds[:12],
                "perception_sensor_sources": sensor_sources[:12],
                "perception_sensor_summaries": sensor_summaries[:12],
            },
            status="ok",
            iteration=iteration,
        )
    return PerceptionSnapshot(
        observation=obs,
        patch=patch,
        view=view,
        features=feats,
        worldview=wv,
        assessment=None,
        retries=0,
        settled=True,
        action_label=action_label,
    )


def refresh_perception(
    runtime: RuntimeState,
    goal: Goal,
    *,
    observe: ObserveFn,
    action_label: str = "observe",
    target_entity_id: Optional[int] = None,
    log_fn: Optional[LogFn] = None,
    iteration: int = 0,
) -> PerceptionSnapshot:
    """
    Full cycle: observe → ingest (multi-source fuse) → view/features.

    This is the reusable primitive. Callers that need settlement/retry should use
    ``ensure_settled_perception``.
    """
    return apply_observation(
        runtime,
        goal,
        observe(),
        action_label=action_label,
        target_entity_id=target_entity_id,
        log_fn=log_fn,
        iteration=iteration,
    )


def ensure_settled_perception(
    runtime: RuntimeState,
    goal: Goal,
    *,
    observe: ObserveFn,
    action_family: str,
    wait_fn: Optional[WaitFn] = None,
    settle_s: float = 0.4,
    initial: Optional[PerceptionSnapshot] = None,
    log_fn: Optional[LogFn] = None,
    iteration: int = 0,
    search_query_hint: str = "",
) -> PerceptionSnapshot:
    """
    Refresh perception until the post-action quality gate settles, or retry budget ends.

    Uses ``POST_PERCEIVE_PROFILES[action_family]`` for retry count / settle times.
    On exhaust: marks snapshot + execution_state as perception_incomplete.
    """

    def _wait(seconds: float, reason: str) -> None:
        if wait_fn:
            wait_fn(seconds, reason)
        elif seconds > 0:
            time.sleep(seconds)

    profile = profile_for(action_family)
    hint = search_query_hint or runtime.execution_state.peek_search_query_hint()

    def _mark_unsettled(snap: PerceptionSnapshot) -> bool:
        stall_sig = _perception_stall_signature(action_family, snap)
        stall_detected = runtime.execution_state.note_perception_stall(
            stall_sig,
            reason=",".join((snap.assessment.failure_modes if snap.assessment else [])[:4]),
        )
        snap.features.setdefault("extras", {})
        if isinstance(snap.features.get("extras"), dict):
            snap.features["extras"]["perception_incomplete"] = True
            snap.features["extras"]["perception_failure_modes"] = list(
                (snap.assessment.failure_modes if snap.assessment else []) or []
            )
            snap.features["extras"]["perception_cycle_stalled"] = stall_detected
            snap.features["extras"]["perception_stall_count"] = runtime.execution_state.perception_stall_count
        runtime.execution_state.perception_incomplete = True
        runtime.execution_state.last_perception_failure_modes = list(
            (snap.assessment.failure_modes if snap.assessment else []) or []
        )
        runtime.execution_state.world_exploration_needed = not stall_detected
        if stall_detected:
            runtime.execution_state.prohibited_actions["observe||"] = max(
                runtime.execution_state.prohibited_actions.get("observe||", 0), 2
            )
        return stall_detected

    if initial is not None:
        snap = initial
        # Recompute assessment on provided snapshot
        snap.assessment = assess_post_action_perception(
            action_family=action_family,
            view=snap.view,
            features=snap.features,
            patch=snap.patch,
            search_query_hint=hint,
        )
        snap.settled = bool(snap.assessment.settled)
        if not snap.settled:
            _mark_unsettled(snap)
    else:
        snap = refresh_perception(
            runtime,
            goal,
            observe=observe,
            action_label=f"perceive_{action_family or 'default'}",
            target_entity_id=runtime.execution_state.last_target_id,
            log_fn=log_fn,
            iteration=iteration,
        )
        snap.assessment = assess_post_action_perception(
            action_family=action_family,
            view=snap.view,
            features=snap.features,
            patch=snap.patch,
            search_query_hint=hint,
        )
        snap.settled = bool(snap.assessment.settled)
        if not snap.settled:
            _mark_unsettled(snap)

    retries = 0
    while snap.assessment and not snap.assessment.settled and retries < profile.max_retries:
        retries += 1
        wait_s = profile.min_extra_settle_s
        if snap.assessment.retry_strategy == "reobserve_longer":
            wait_s = max(wait_s, settle_s)
        if log_fn:
            log_fn(
                phase="perception_retry",
                payload={
                    "attempt": retries,
                    "max": profile.max_retries,
                    "failure_modes": snap.assessment.failure_modes,
                    "retry_strategy": snap.assessment.retry_strategy,
                    "evidence": snap.assessment.evidence,
                    "action_family": action_family,
                },
                status="ok",
                iteration=iteration,
        )
        _wait(wait_s, f"perception retry ({','.join(snap.assessment.failure_modes[:3])})")
        snap = refresh_perception(
            runtime,
            goal,
            observe=observe,
            action_label=f"reobserve_post_{action_family or 'default'}",
            target_entity_id=runtime.execution_state.last_target_id,
            log_fn=log_fn,
            iteration=iteration,
        )
        snap.retries = retries
        snap.assessment = assess_post_action_perception(
            action_family=action_family,
            view=snap.view,
            features=snap.features,
            patch=snap.patch,
            search_query_hint=hint,
        )
        snap.settled = bool(snap.assessment.settled)
        if not snap.settled:
            _mark_unsettled(snap)

    snap.retries = retries
    if not snap.settled:
        if log_fn:
            log_fn(
                phase="perception_unsettled",
                payload=snap.assessment.to_dict() if snap.assessment else snap.to_dict(),
                status="fail",
                iteration=iteration,
            )
    else:
        runtime.execution_state.perception_incomplete = False
        runtime.execution_state.last_perception_failure_modes = []
        runtime.execution_state.clear_perception_stall()
        if log_fn:
            evidence = (snap.assessment.evidence if snap.assessment else {}) or {}
            log_fn(
                phase="perception_settled",
                payload={
                    "retries": retries,
                    "failure_modes": list(
                        (snap.assessment.failure_modes if snap.assessment else []) or []
                    ),
                    **evidence,
                },
                status="ok",
                iteration=iteration,
            )
    return snap
