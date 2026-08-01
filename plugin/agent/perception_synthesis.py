"""Generic LLM-assisted screen synthesis for ambiguous perception states.

This is intentionally app-agnostic. The helper consumes the current view,
scene graph, and goal, then asks a reasoning-capable auxiliary LLM to
summarize what screen we are on and which next actuator family is most
plausible. App overlays still own leaf-specific affordances; this module only
provides a reusable cognitive layer that can guide the next decision.
"""

from __future__ import annotations

import hashlib
import base64
import json
import logging
import os
import mimetypes
import re
import time
import threading
from urllib.parse import urlparse
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, List, Optional, Sequence

from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.reasoning_consultation import consult_reasoning
from plugin.worldmodel.model import WorldModel
from hermes_cli.model_routing import rank_task_models

logger = logging.getLogger(__name__)

_CACHE_KEY = "__perception_synthesis_cache__"
_DEFAULT_WORLDVIEW_THRESHOLD = 0.93
_DEFAULT_PERCEPTION_FAIL_HARD = True
_DEFAULT_PERCEPTION_TIMEOUT_SECONDS = 15.0
_DEFAULT_PERCEPTION_MAX_TOKENS = 192
_DEFAULT_PERCEPTION_MIN_CONFIDENCE = 0.7
_DEFAULT_PERCEPTION_PROMPT_SHAPE = "balanced"
_SCREEN_UNDERSTANDING_TASK = "screen_understanding"


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            pass
    return str(value)


def _clip_text(value: Any, limit: int = 160) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _compact_rows(rows: Any, *, limit: int = 8, text_limit: int = 160) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(rows, list):
        return out
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "entity_id": row.get("entity_id"),
                "text": _clip_text(row.get("text") or row.get("label") or row.get("description"), text_limit),
                "label": _clip_text(row.get("label"), 80),
                "description": _clip_text(row.get("description"), 80),
                "entity_type": _clip_text(row.get("entity_type"), 24),
                "role": _clip_text(row.get("role"), 24),
            }
        )
    return out


def _goal_needs_timeline_projection(goal: Goal) -> bool:
    kind = (goal.kind or "").strip().lower()
    return "forward" in kind or "message" in kind or "read" in kind


def _extract_text(response: Any) -> str:
    if isinstance(response, str):
        return response.strip()
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        message = getattr(choices[0], "message", None)
        if message is not None:
            content = getattr(message, "content", None)
            if isinstance(content, str) and content.strip():
                return content.strip()
    if isinstance(response, dict):
        for key in ("output_text", "text", "content"):
            val = response.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return str(response).strip()


def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()
    if not raw.startswith("{"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_label(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).lower()


def _perception_prompt_shape() -> str:
    try:
        from hermes_cli.config import load_config_readonly

        cfg = load_config_readonly() or {}
        agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
        raw = agent_cfg.get("perception_llm_prompt_shape", _DEFAULT_PERCEPTION_PROMPT_SHAPE)
        value = str(raw or _DEFAULT_PERCEPTION_PROMPT_SHAPE).strip().lower()
        return value or _DEFAULT_PERCEPTION_PROMPT_SHAPE
    except Exception:
        return _DEFAULT_PERCEPTION_PROMPT_SHAPE


def _perception_cache_key(
    goal: Goal,
    world: WorldModel,
    view: Dict[str, Any],
    features: StateFeatures,
    *,
    task_name: str,
) -> str:
    scene = getattr(world, "last_scene_graph", None) or {}
    payload = {
        "task_name": task_name,
        "goal": {
            "kind": goal.kind,
            "contact": goal.contact,
            "target_contact": goal.target_contact,
            "link_query": goal.link_query,
            "app": goal.app,
            "procedure_id": goal.procedure_id,
        },
        "view": {
            "screen": view.get("screen"),
            "search_query": view.get("search_query"),
            "open_conversation": view.get("open_conversation"),
            "visible_contacts": list(view.get("visible_contacts") or [])[:12],
            "search_visible": view.get("search_visible"),
            "search_focused": view.get("search_focused"),
            "blocking_overlay": view.get("blocking_overlay"),
            "system_warnings": list(view.get("system_warnings") or [])[:8],
        },
        "features": {
            "screen_bucket": features.screen_bucket,
            "conversation_open": features.conversation_open,
            "call_available": features.call_available,
            "call_ringing": features.call_ringing,
            "leftover_call": features.leftover_call,
            "search_focused": features.search_focused,
            "query_matches_goal": features.query_matches_goal,
            "goal_progress": round(float(features.goal_progress or 0.0), 3),
            "worldview_score": round(float(features.worldview_score or 1.0), 3),
            "mean_belief": round(float(features.mean_belief or 1.0), 3),
            "needs_reobserve": bool(features.needs_reobserve),
            "observation_node_count": int(features.extras.get("observation_node_count") or 0),
            "app_content_node_count": int(features.extras.get("app_content_node_count") or 0),
            "chrome_only_node_count": int(features.extras.get("chrome_only_node_count") or 0),
            "task_sufficient": bool(features.extras.get("task_sufficient", True)),
            "blocking_overlay": bool(features.extras.get("blocking_overlay")),
            "system_warnings": list(features.extras.get("system_warnings") or [])[:8],
            "conversation_context_window": int(features.extras.get("conversation_context_window") or 0),
            "conversation_message_relevance": features.extras.get("conversation_message_relevance") or {},
            "conversation_timeline": features.extras.get("conversation_timeline") or [],
            "active_cognitive_subgraph": features.extras.get("active_cognitive_subgraph") or {},
        },
        "scene": {
            "report": scene.get("report") or {},
            "attention": scene.get("attention") or {},
            "region_kinds": [r.get("kind") for r in (scene.get("regions") or []) if isinstance(r, dict)],
        },
        "conversation_context": list(features.extras.get("conversation_context_text") or [])[:100],
        "prompt_shape": _perception_prompt_shape(),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _compact_view_packet(
    goal: Goal,
    view: Dict[str, Any],
    features: StateFeatures,
    *,
    visible_entities: List[Dict[str, Any]],
    prompt_shape: str = "",
) -> Dict[str, Any]:
    extras = features.extras if isinstance(features.extras, dict) else {}
    ranked_messages = extras.get("ranked_conversation_messages") or []
    conversation_context = extras.get("conversation_context_text") or []
    conversation_timeline = extras.get("conversation_timeline") or []
    screen = str(view.get("screen") or "").strip().upper()
    search_surface = bool(view.get("search_focused")) or screen in {"SEARCH", "SEARCH_RESULTS"}
    prompt_shape_norm = str(prompt_shape or _DEFAULT_PERCEPTION_PROMPT_SHAPE).strip().lower()
    if prompt_shape_norm == "compact":
        entity_limit = 5 if search_surface else 8
        ranked_limit = 2 if search_surface else 4
        context_limit = 2 if search_surface else 4
        text_limit = 120 if search_surface else 180
        include_affordance_entropy = False
    elif prompt_shape_norm == "rich":
        entity_limit = 12 if search_surface else 14
        ranked_limit = 6 if search_surface else 8
        context_limit = 6 if search_surface else 8
        text_limit = 180 if search_surface else 220
        include_affordance_entropy = True
    else:
        entity_limit = 8 if search_surface else 10
        ranked_limit = 4 if search_surface else 5
        context_limit = 4 if search_surface else 5
        text_limit = 150 if search_surface else 180
        include_affordance_entropy = True
    compact_ranked: List[Dict[str, Any]] = []
    if isinstance(ranked_messages, list):
        for row in ranked_messages[:ranked_limit]:
            if not isinstance(row, dict):
                continue
            compact_ranked.append(
                {
                    "entity_id": row.get("entity_id"),
                    "score": row.get("score"),
                    "text": _clip_text(row.get("text") or row.get("label") or row.get("description"), text_limit),
                    "reason": _clip_text(row.get("reason"), 120),
                }
            )
    compact_context: List[str] = []
    if isinstance(conversation_context, list):
        compact_context = [_clip_text(text, text_limit) for text in conversation_context[:context_limit]]
    compact_timeline: List[Dict[str, Any]] = []
    if isinstance(conversation_timeline, list):
        compact_timeline = _compact_rows(conversation_timeline, limit=context_limit, text_limit=text_limit)
    return {
        "goal": {
            "kind": goal.kind,
            "contact": goal.contact,
            "target_contact": goal.target_contact,
            "link_query": goal.link_query,
            "app": goal.app,
        },
        "screen": {
            "app": _clip_text(view.get("app"), 32),
            "screen": _clip_text(view.get("screen"), 24),
            "window_name": _clip_text(view.get("window_name"), 80),
            "screenshot_path": _clip_text(extras.get("screenshot_path") or view.get("screenshot_path"), 180),
            "observation_node_count": int(extras.get("observation_node_count") or 0),
            "app_content_node_count": int(extras.get("app_content_node_count") or 0),
            "chrome_only_node_count": int(extras.get("chrome_only_node_count") or 0),
            "task_sufficient": bool(extras.get("task_sufficient", True)),
            "observation_degenerate": bool(extras.get("observation_degenerate")),
            "held_last_good_world": bool(extras.get("held_last_good_world")),
            "world_exploration_needed": bool(extras.get("world_exploration_needed")),
            "perception_incomplete": bool(extras.get("perception_incomplete")),
            "perception_cycle_stalled": bool(extras.get("perception_cycle_stalled")),
            "search_visible": bool(view.get("search_visible")),
            "search_focused": bool(view.get("search_focused")),
            "search_query": _clip_text(view.get("search_query"), 80),
            "open_conversation": _clip_text(view.get("open_conversation"), 80),
            "voice_call_available": bool(view.get("voice_call_available")),
            "call_state": _clip_text(view.get("call_state"), 24),
            "composer_visible": bool(view.get("composer_visible")),
            "blocking_overlay": bool(view.get("blocking_overlay")),
            "unexpected_dialogs": [_clip_text(x, 48) for x in (view.get("unexpected_dialogs") or [])[:4]],
            "system_warnings": [_clip_text(x, 80) for x in (view.get("system_warnings") or [])[:4]],
        },
        "evidence": {
            "visible_entities": visible_entities[:entity_limit],
            "ranked_messages": compact_ranked[:ranked_limit],
            "conversation_context": compact_context[:context_limit],
            "conversation_timeline": compact_timeline[:context_limit],
            "scene_report": {
                "layout_confidence": extras.get("scene_layout_confidence"),
                "region_coverage": extras.get("scene_region_coverage"),
                **(
                    {"affordance_entropy": extras.get("scene_affordance_entropy")}
                    if include_affordance_entropy
                    else {}
                ),
            },
        },
        "instructions": (
            "Infer screen meaning from AX evidence only. Return strict JSON with "
            "screen_type, active_surface, likely_next_family, likely_next_target, "
            "likely_next_text, confidence, avoid_families, supporting_evidence, "
            "contradictions, needs_followup_observe."
        ),
    }


def _screen_understanding_needed(view: Dict[str, Any], features: StateFeatures) -> bool:
    extras = features.extras if isinstance(features.extras, dict) else {}
    screen = str(view.get("screen") or "").strip().upper()
    screenshot_path = str(extras.get("screenshot_path") or view.get("screenshot_path") or "").strip()
    try:
        layout_conf = float(extras.get("scene_layout_confidence") or 1.0)
    except Exception:
        layout_conf = 1.0
    try:
        coverage = float(extras.get("scene_region_coverage") or 1.0)
    except Exception:
        coverage = 1.0
    if not screenshot_path and int(extras.get("app_content_node_count") or 0) <= 0 and not bool(extras.get("conversation_timeline")):
        # Let AX-only but semantically rich states still consult the perceptor.
        # This is the common dialog/search/list recovery path where the model
        # should reason over the live world graph even if no screenshot was
        # captured for that turn.
        if screen not in {"CALLING", "DIALOG", "SEARCH", "SEARCH_RESULTS", "CONVERSATION", "LIST"}:
            return False
    return (
        float(features.worldview_score or 1.0) < _perception_threshold()
        or float(features.mean_belief or 1.0) < 0.9
        or bool(features.needs_reobserve)
        or bool(extras.get("perception_incomplete"))
        or bool(extras.get("world_exploration_needed"))
        or bool(extras.get("observation_degenerate"))
        or bool(extras.get("perception_cycle_stalled"))
        or layout_conf < 0.7
        or coverage < 0.8
    )


def _select_perception_task_name(view: Dict[str, Any], features: StateFeatures) -> str:
    return _SCREEN_UNDERSTANDING_TASK if _screen_understanding_needed(view, features) else "perception"


def _screenshot_to_data_url(screenshot_path: str) -> str:
    path = str(screenshot_path or "").strip()
    if not path:
        return ""
    try:
        with open(path, "rb") as fh:
            blob = fh.read()
    except Exception:
        return ""
    mime = mimetypes.guess_type(path)[0] or "image/png"
    encoded = base64.b64encode(blob).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _perception_threshold() -> float:
    try:
        from hermes_cli.config import load_config_readonly

        cfg = load_config_readonly() or {}
        agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
        raw = agent_cfg.get("perception_llm_worldview_threshold", _DEFAULT_WORLDVIEW_THRESHOLD)
        return max(0.0, min(1.0, float(raw)))
    except Exception:
        return _DEFAULT_WORLDVIEW_THRESHOLD


def _perception_enabled() -> bool:
    try:
        from hermes_cli.config import load_config_readonly

        cfg = load_config_readonly() or {}
        agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
        raw = agent_cfg.get("perception_llm_enabled", True)
        return bool(raw)
    except Exception:
        return True


def _perception_fail_hard() -> bool:
    """Return True when perception must not degrade to heuristic fallback."""
    try:
        from hermes_cli.config import load_config_readonly

        cfg = load_config_readonly() or {}
        agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
        raw = agent_cfg.get("perception_llm_fail_hard", _DEFAULT_PERCEPTION_FAIL_HARD)
        return bool(raw)
    except Exception:
        return _DEFAULT_PERCEPTION_FAIL_HARD


def _perception_timeout_seconds() -> float:
    """Return the dedicated timeout budget for perception synthesis."""
    env_timeout = os.getenv("HERMES_PERCEPTION_LLM_TIMEOUT_SECONDS", "").strip()
    if env_timeout:
        try:
            return max(5.0, min(float(env_timeout), 15.0))
        except Exception:
            pass
    try:
        from hermes_cli.config import load_config_readonly

        cfg = load_config_readonly() or {}
        agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
        raw = agent_cfg.get("perception_llm_timeout_seconds", _DEFAULT_PERCEPTION_TIMEOUT_SECONDS)
        timeout = float(raw)
        return max(5.0, min(timeout, 15.0))
    except Exception:
        return _DEFAULT_PERCEPTION_TIMEOUT_SECONDS


def _perception_max_tokens() -> int:
    """Return the completion budget for structured perception output."""
    env_max = os.getenv("HERMES_PERCEPTION_LLM_MAX_TOKENS", "").strip()
    if env_max:
        try:
            return max(64, int(float(env_max)))
        except Exception:
            pass
    try:
        from hermes_cli.config import load_config_readonly

        cfg = load_config_readonly() or {}
        agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
        raw = agent_cfg.get("perception_llm_max_tokens", _DEFAULT_PERCEPTION_MAX_TOKENS)
        return max(64, int(float(raw)))
    except Exception:
        return _DEFAULT_PERCEPTION_MAX_TOKENS


def _perception_min_confidence() -> float:
    """Return the confidence threshold for promoting a perception result."""
    env_min = os.getenv("HERMES_PERCEPTION_LLM_MIN_CONFIDENCE", "").strip()
    if env_min:
        try:
            return max(0.0, min(float(env_min), 1.0))
        except Exception:
            pass
    try:
        from hermes_cli.config import load_config_readonly

        cfg = load_config_readonly() or {}
        agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
        raw = agent_cfg.get("perception_llm_min_confidence", _DEFAULT_PERCEPTION_MIN_CONFIDENCE)
        return max(0.0, min(float(raw), 1.0))
    except Exception:
        return _DEFAULT_PERCEPTION_MIN_CONFIDENCE


def _main_runtime_snapshot() -> Dict[str, Any]:
    try:
        from agent.auxiliary_client import get_runtime_main_snapshot

        return get_runtime_main_snapshot()
    except Exception:
        return {}


def _runtime_supports_vision(main_runtime: Optional[Dict[str, Any]] = None) -> bool:
    runtime = dict(main_runtime or {})
    provider = str(runtime.get("provider") or "").strip()
    model = str(runtime.get("model") or "").strip()
    if not provider or not model:
        return False
    try:
        from agent.models_dev import get_model_info

        info = get_model_info(provider, model)
        return bool(info and info.supports_vision())
    except Exception:
        return False


def _perception_task_target(
    main_runtime: Optional[Dict[str, Any]] = None,
    *,
    task_name: str = "perception",
) -> Dict[str, Any]:
    """Return the provider/model/base_url for perception calls.

    Perception now prefers the live runtime main lane when present so the
    screen-understanding path cannot drift onto a stale auxiliary provider
    from persisted task config. If no live runtime is available, fall back to
    the configured task slot.
    """
    runtime = dict(main_runtime or {})
    try:
        from agent.auxiliary_client import _get_auxiliary_task_config

        task_cfg = _get_auxiliary_task_config(task_name) or {}
        if task_name == _SCREEN_UNDERSTANDING_TASK and not task_cfg:
            task_cfg = _get_auxiliary_task_config("perception") or {}
    except Exception:
        task_cfg = {}

    if task_name == _SCREEN_UNDERSTANDING_TASK and not _runtime_supports_vision(runtime):
        runtime = {}

    provider = str(
        runtime.get("provider")
        or task_cfg.get("provider")
        or ("auto" if task_name == _SCREEN_UNDERSTANDING_TASK else "ollama-cloud")
    ).strip() or ("auto" if task_name == _SCREEN_UNDERSTANDING_TASK else "ollama-cloud")
    model = str(
        runtime.get("model")
        or task_cfg.get("model")
        or ("auto" if task_name == _SCREEN_UNDERSTANDING_TASK else "gpt-oss:120b")
    ).strip() or ("auto" if task_name == _SCREEN_UNDERSTANDING_TASK else "gpt-oss:120b")
    base_url = str(
        runtime.get("base_url")
        or task_cfg.get("base_url")
        or ""
    ).strip()
    api_key = str(
        runtime.get("api_key")
        or task_cfg.get("api_key")
        or ""
    ).strip()
    return {
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
    }


def _perception_task_targets(
    main_runtime: Optional[Dict[str, Any]] = None,
    *,
    task_name: str = "perception",
) -> List[Dict[str, Any]]:
    """Return ordered provider/model targets for a perception consultation.

    The primary route is the shared task router. For screen-understanding
    calls, that router should surface the Ollama Cloud chain first, so the
    perceptor can naturally step from qwen3.5:cloud -> kimi-k3:cloud ->
    gemma4:cloud when the current answer is too uncertain.
    """
    runtime = dict(main_runtime or {})
    task_cfg = {}
    try:
        from agent.auxiliary_client import _get_auxiliary_task_config, _resolve_task_provider_model

        task_cfg = _get_auxiliary_task_config(task_name) or {}
        if task_name == _SCREEN_UNDERSTANDING_TASK and not task_cfg:
            task_cfg = _get_auxiliary_task_config("perception") or {}
    except Exception:
        task_cfg = {}
        _resolve_task_provider_model = None  # type: ignore[assignment]

    if task_name == _SCREEN_UNDERSTANDING_TASK:
        runtime = {}

    targets: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def _append_target(
        provider: str = "",
        model: str = "",
        base_url: str = "",
        api_key: str = "",
        api_mode: str = "",
        source: str = "",
        rank: int = -1,
    ) -> None:
        provider_norm = str(provider or "").strip().lower()
        model_norm = str(model or "").strip()
        base_norm = str(base_url or "").strip()
        key = (provider_norm, model_norm.lower(), base_norm)
        if not provider_norm and not model_norm:
            return
        if key in seen:
            return
        seen.add(key)
        targets.append(
            {
                "provider": provider_norm,
                "model": model_norm,
                "base_url": base_norm,
                "api_key": str(api_key or "").strip(),
                "api_mode": str(api_mode or "").strip(),
                "source": source,
                "rank": rank,
            }
        )

    # Explicit per-task override wins first when present.
    if task_cfg:
        explicit_provider = str(task_cfg.get("provider") or "").strip()
        explicit_model = str(task_cfg.get("model") or "").strip()
        if explicit_provider or explicit_model:
            try:
                from agent.auxiliary_client import _resolve_task_provider_model

                resolved = _resolve_task_provider_model(
                    task_name,
                    provider=explicit_provider or None,
                    model=explicit_model or None,
                    base_url=str(task_cfg.get("base_url") or "").strip() or None,
                    api_key=str(task_cfg.get("api_key") or "").strip() or None,
                )
                if task_name == _SCREEN_UNDERSTANDING_TASK:
                    resolved_provider_norm = str(resolved[0] or "").strip().lower()
                    if resolved_provider_norm and resolved_provider_norm != "ollama-cloud":
                        logger.info(
                            "Perception LLM: ignoring legacy screen_understanding override provider=%s model=%s; cloud chain will own the route",
                            resolved[0],
                            resolved[1],
                        )
                        resolved = None
                if resolved is not None:
                    _append_target(
                        provider=resolved[0],
                        model=resolved[1] or explicit_model,
                        base_url=resolved[2] or "",
                        api_key=resolved[3] or "",
                        api_mode=resolved[4] or "",
                        source="task_config",
                        rank=0,
                    )
            except Exception:
                if task_name != _SCREEN_UNDERSTANDING_TASK:
                    _append_target(
                        provider=explicit_provider,
                        model=explicit_model,
                        base_url=str(task_cfg.get("base_url") or "").strip(),
                        api_key=str(task_cfg.get("api_key") or "").strip(),
                        api_mode=str(task_cfg.get("api_mode") or "").strip(),
                        source="task_config",
                        rank=0,
                    )

    # Shared router ranking. For screen-understanding, prefer the cloud-only
    # multimodal chain and ignore the current runtime's smaller text-only lane.
    current_provider = "" if task_name == _SCREEN_UNDERSTANDING_TASK else str(runtime.get("provider") or "").strip()
    current_base_url = "" if task_name == _SCREEN_UNDERSTANDING_TASK else str(runtime.get("base_url") or "").strip()
    try:
        ranked = rank_task_models(
            task_name,
            current_provider=current_provider,
            current_base_url=current_base_url,
            probe_custom_providers=True,
            probe_current_custom_provider=False,
        )
    except Exception:
        ranked = []
    if task_name == _SCREEN_UNDERSTANDING_TASK:
        ollama_ranked = [cand for cand in ranked if str(getattr(cand, "provider", "") or "").strip().lower() == "ollama-cloud"]
        if ollama_ranked:
            ranked = ollama_ranked

    try:
        from agent.auxiliary_client import _resolve_task_provider_model
    except Exception:
        _resolve_task_provider_model = None  # type: ignore[assignment]

    for idx, cand in enumerate(ranked):
        provider = str(getattr(cand, "provider", "") or "").strip()
        model = str(getattr(cand, "model", "") or "").strip()
        base_url = str(getattr(cand, "base_url", "") or "").strip()
        if not provider or not model:
            continue
        if _resolve_task_provider_model is not None:
            try:
                resolved = _resolve_task_provider_model(
                    task_name,
                    provider=provider,
                    model=model,
                    base_url=base_url or None,
                )
                _append_target(
                    provider=resolved[0],
                    model=resolved[1] or model,
                    base_url=resolved[2] or base_url,
                    api_key=resolved[3] or "",
                    api_mode=resolved[4] or "",
                    source=f"ranked:{getattr(cand, 'source', '') or ''}",
                    rank=idx + 1,
                )
                continue
            except Exception:
                pass
        _append_target(
            provider=provider,
            model=model,
            base_url=base_url,
            source=f"ranked:{getattr(cand, 'source', '') or ''}",
            rank=idx + 1,
        )

    if targets:
        return targets
    return [_perception_task_target(main_runtime, task_name=task_name)]


def _perception_reasoning_config(target: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Only request explicit thinking when the selected perception model is expected
    to support it. Some fast chat-oriented models reject the flag outright.
    """
    provider = str(target.get("provider") or "").strip().lower()
    model = str(target.get("model") or "").strip().lower()

    if not model:
        return None
    if "qwen2.5:32b" in model:
        return None
    if provider in {"ollama-remote", "ollama"}:
        return None
    return {"enabled": True, "effort": "low"}


def _call_llm_hard_timeout(timeout_s: float, **kwargs: Any) -> Any:
    """Run ``call_llm`` in a daemon thread and enforce a wall-clock timeout."""
    from agent.auxiliary_client import call_llm

    result: Dict[str, Any] = {}
    error: Dict[str, BaseException] = {}
    done = threading.Event()

    def _runner() -> None:
        try:
            result["value"] = call_llm(**kwargs)
        except BaseException as exc:  # pragma: no cover - surfaced in caller
            error["exc"] = exc
        finally:
            done.set()

    thread = threading.Thread(target=_runner, name="perception-llm", daemon=True)
    thread.start()
    if not done.wait(timeout_s):
        raise TimeoutError(f"perception llm timed out after {timeout_s:.1f}s")
    if "exc" in error:
        raise error["exc"]
    return result.get("value")


def _perception_extra_body(main_runtime: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Request JSON-mode output on transports that support it.

    Ollama's OpenAI-compatible chat endpoint understands ``format=json`` and
    is the current primary route for the live WhatsApp run. Forcing JSON mode
    there materially reduces the chance that the model emits a prose preface
    or other non-JSON wrapper around the perception summary.
    """
    runtime = dict(main_runtime or {})
    provider = str(runtime.get("provider") or "").strip().lower()
    base_url = str(runtime.get("base_url") or "").strip()
    host = ""
    try:
        host = urlparse(base_url).hostname or ""
    except Exception:
        host = ""
    if provider in {"ollama", "ollama-remote", "ollama-cloud"} or "ollama" in host:
        return {"format": "json"}
    return {}


def _should_run_perception_llm(view: Dict[str, Any], features: StateFeatures) -> bool:
    if not _perception_enabled():
        return False
    extras = features.extras if isinstance(features.extras, dict) else {}
    screen = str(view.get("screen") or "").strip().upper()
    node_count = int(features.extras.get("observation_node_count") or 0)
    app_content_node_count = int(extras.get("app_content_node_count") or 0)
    task_sufficient = bool(extras.get("task_sufficient", True))
    screenshot_path = str(extras.get("screenshot_path") or view.get("screenshot_path") or "").strip()
    if not screenshot_path and app_content_node_count <= 0 and not bool(extras.get("conversation_timeline")):
        # Keep ambiguous AX-only dialog/search/list states in play so the
        # consultation layer can reason about the current world graph even
        # when no screenshot has been captured for this turn.
        if screen not in {"CALLING", "DIALOG", "SEARCH", "SEARCH_RESULTS", "CONVERSATION", "LIST"}:
            return False
    degenerate = node_count <= 1
    if degenerate:
        # Sparse post-action frames are exactly where semantic recovery is needed.
        # If we have a retained world, a pending branch, or any recovery flag,
        # keep the LLM in the loop instead of silencing it.
        recovery_signal = bool(getattr(features, "needs_reobserve", False))
        recovery_signal = recovery_signal or bool(features.extras.get("perception_incomplete"))
        recovery_signal = recovery_signal or bool(features.extras.get("world_exploration_needed"))
        recovery_signal = recovery_signal or bool(features.extras.get("perception_cycle_stalled"))
        recovery_signal = recovery_signal or bool(features.extras.get("held_last_good_world"))
        recovery_signal = recovery_signal or bool(features.call_ringing or features.leftover_call)
        recovery_signal = recovery_signal or str(view.get("screen") or "").upper() in {
            "CALLING",
            "DIALOG",
            "SEARCH",
            "SEARCH_RESULTS",
            "CONVERSATION",
            "LIST",
        }
        if not recovery_signal:
            return False
    if features.needs_reobserve:
        return True
    if features.call_ringing or features.leftover_call:
        return True
    if bool(features.extras.get("perception_incomplete")):
        return True
    if bool(features.extras.get("unexpected_dialogs")):
        return True
    if bool(features.extras.get("blocking_overlay")):
        return True
    if bool(features.extras.get("system_warnings")):
        return True
    if float(features.worldview_score or 1.0) < _perception_threshold():
        return True
    if float(features.mean_belief or 1.0) < 0.85:
        return True
    if str(view.get("screen") or "").upper() in {"CALLING", "DIALOG", "SEARCH", "SEARCH_RESULTS"}:
        return True
    if bool(features.extras.get("world_exploration_needed")):
        return True
    if bool(features.extras.get("perception_cycle_stalled")):
        return True
    if not task_sufficient and app_content_node_count >= 1:
        return True
    if str(features.extras.get("resolution_policy") or "").lower() in {"observe", "ask"}:
        return True
    return False


def _coerce_state_features(features: Any) -> tuple[StateFeatures, Optional[Dict[str, Any]]]:
    """Accept either the dataclass or the dict shape used by some callers."""
    if isinstance(features, StateFeatures):
        return features, None
    if isinstance(features, dict):
        extras = features.get("extras")
        if not isinstance(extras, dict):
            extras = {}
        return (
            StateFeatures(
                app=str(features.get("app") or ""),
                screen_kind=str(features.get("screen_kind") or features.get("screen_bucket") or "unknown"),
                screen_bucket=str(features.get("screen_bucket") or "unknown"),
                has_dialog=bool(features.get("has_dialog")),
                has_text_query=bool(features.get("has_text_query")),
                query_matches_goal=bool(features.get("query_matches_goal")),
                has_named_entity=bool(features.get("has_named_entity")),
                conversation_open=bool(features.get("conversation_open")),
                call_available=bool(features.get("call_available")),
                call_ringing=bool(features.get("call_ringing")),
                leftover_call=bool(features.get("leftover_call")),
                search_focused=bool(features.get("search_focused")),
                goal_progress=float(features.get("goal_progress") or 0.0),
                worldview_score=float(features.get("worldview_score") or 1.0),
                mean_belief=float(features.get("mean_belief") or 1.0),
                needs_reobserve=bool(features.get("needs_reobserve")),
                extras=dict(extras),
            ),
            features,
        )
    return StateFeatures(), None


@dataclass
class PerceptionSynthesis:
    screen_type: str = "unknown"
    active_surface: str = ""
    likely_next_family: str = "observe"
    likely_next_target: str = ""
    likely_next_text: str = ""
    confidence: float = 0.0
    avoid_families: List[str] = field(default_factory=list)
    supporting_evidence: List[str] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)
    needs_followup_observe: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "screen_type": self.screen_type,
            "active_surface": self.active_surface,
            "likely_next_family": self.likely_next_family,
            "likely_next_target": self.likely_next_target,
            "likely_next_text": self.likely_next_text,
            "confidence": round(float(self.confidence or 0.0), 4),
            "avoid_families": list(self.avoid_families),
            "supporting_evidence": list(self.supporting_evidence),
            "contradictions": list(self.contradictions),
            "needs_followup_observe": bool(self.needs_followup_observe),
            "raw": _json_safe(self.raw),
        }


def build_perception_prompt_payload(
    goal: Goal,
    world: WorldModel,
    view: Dict[str, Any],
    features: StateFeatures,
    *,
    prompt_shape: Optional[str] = None,
) -> Dict[str, Any]:
    scene = getattr(world, "last_scene_graph", None) or {}
    visible_entities: List[Dict[str, Any]] = []
    attention = scene.get("attention") or {}
    attention_ids = {int(x) for x in (attention.get("entity_ids") or []) if str(x).strip().isdigit()}
    extras = features.extras if isinstance(features.extras, dict) else {}
    active_subgraph = extras.get("active_cognitive_subgraph") or {}
    active_entity_ids = {
        int(x)
        for x in (active_subgraph.get("active_entity_ids") or [])
        if str(x).strip().isdigit()
    }
    goal_terms = [
        str(goal.contact or "").strip().lower(),
        str(goal.target_contact or "").strip().lower(),
        str(goal.link_query or "").strip().lower(),
    ]
    ranked_entities = []
    for entity in list(world.entities.values()):
        if not getattr(entity, "visible", False):
            continue
        label = getattr(entity, "label", "") or getattr(entity, "semantic_role", "")
        role = getattr(entity, "role", "")
        entity_type = getattr(entity, "entity_type", "")
        actions = list(getattr(entity, "actions", []) or [])
        blob = " ".join([str(label), str(role), str(entity_type)]).lower()
        score = 0
        if getattr(entity, "id", None) in attention_ids:
            score += 10
        if any(term and term in blob for term in goal_terms):
            score += 5
        if actions:
            score += 1
        ranked_entities.append(
            (
                score,
                {
                    "id": getattr(entity, "id", None),
                    "label": label,
                    "role": role,
                    "entity_type": entity_type,
                    "region_kind": getattr(entity, "region_kind", ""),
                    "actions": actions,
                },
            )
        )
    for _, ent in sorted(ranked_entities, key=lambda item: item[0], reverse=True)[:12]:
        visible_entities.append(ent)

    if _goal_needs_timeline_projection(goal):
        relevant_visible_entities: List[Dict[str, Any]] = []
        for ent in visible_entities:
            ent_type = str(ent.get("entity_type") or "").lower()
            ent_role = str(ent.get("role") or "").lower()
            if ent_type in {"menu", "menubar"} or ent_role in {"axmenuitem", "axmenubar", "axmenubaritem"}:
                continue
            ent_blob = " ".join(
                [
                    str(ent.get("label") or ""),
                    str(ent.get("role") or ""),
                    str(ent.get("entity_type") or ""),
                ]
            ).lower()
            ent_id = ent.get("id")
            if ent_id is not None:
                try:
                    if int(ent_id) in active_entity_ids:
                        relevant_visible_entities.append(ent)
                        continue
                except Exception:
                    pass
            if any(term and term in ent_blob for term in goal_terms):
                relevant_visible_entities.append(ent)
                continue
            if ent.get("entity_type") == "textfield" and "search" in ent_blob:
                relevant_visible_entities.append(ent)
                continue
            if ent.get("entity_type") == "button" and any(token in ent_blob for token in ("forward", "search")):
                relevant_visible_entities.append(ent)
                continue
        if relevant_visible_entities:
            visible_entities = relevant_visible_entities

    payload = _compact_view_packet(
        goal,
        view,
        features,
        visible_entities=visible_entities,
        prompt_shape=prompt_shape or _perception_prompt_shape(),
    )
    return payload


def _build_prompt(
    goal: Goal,
    world: WorldModel,
    view: Dict[str, Any],
    features: StateFeatures,
    *,
    prompt_shape: Optional[str] = None,
    task_name: str = "perception",
) -> List[Dict[str, Any]]:
    payload = build_perception_prompt_payload(goal, world, view, features, prompt_shape=prompt_shape)
    if task_name == _SCREEN_UNDERSTANDING_TASK:
        payload["instructions"] = (
            "Infer screen meaning from the screenshot and AX evidence together. "
            "Return strict JSON with screen_type, active_surface, likely_next_family, "
            "likely_next_target, likely_next_text, confidence, avoid_families, "
            "supporting_evidence, contradictions, needs_followup_observe."
        )
    elif _goal_needs_timeline_projection(goal):
        payload["instructions"] = (
            "Infer screen meaning from AX evidence only. For message-relevance tasks, "
            "treat conversation_timeline as the primary source of truth, prefer visible "
            "timeline rows and links over unrelated chrome, and ignore terminal/file/menu noise. "
            "Return strict JSON with screen_type, active_surface, likely_next_family, "
            "likely_next_target, likely_next_text, confidence, avoid_families, "
            "supporting_evidence, contradictions, needs_followup_observe."
        )
    return [
        {
            "role": "system",
            "content": (
                "Return strict JSON only. "
                + (
                    "Infer screen meaning from screenshot pixels and AX evidence."
                    if task_name == _SCREEN_UNDERSTANDING_TASK
                    else "Infer screen meaning from AX evidence."
                )
            ),
        },
        {
            "role": "user",
            "content": (
                [
                    {
                        "type": "text",
                        "text": json.dumps(
                            payload,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=False,
                            default=str,
                        ),
                    },
                    *(
                        [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": data_url,
                                },
                            }
                        ]
                        if task_name == _SCREEN_UNDERSTANDING_TASK
                        and (data_url := _screenshot_to_data_url(
                            str((features.extras if isinstance(features.extras, dict) else {}).get("screenshot_path")
                                or view.get("screenshot_path")
                                or "")
                        ))
                        else []
                    ),
                ]
                if task_name == _SCREEN_UNDERSTANDING_TASK
                else json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=False,
                    default=str,
                )
            ),
        },
    ]


def _fallback_summary(goal: Goal, view: Dict[str, Any], features: StateFeatures) -> PerceptionSynthesis:
    raise RuntimeError(
        "perception synthesis requires an LLM result; refusing deterministic fallback"
    )


def _parse_summary(parsed: Dict[str, Any], goal: Goal, view: Dict[str, Any], features: StateFeatures) -> PerceptionSynthesis:
    avoid = parsed.get("avoid_families") or parsed.get("avoid") or []
    evidence = parsed.get("supporting_evidence") or parsed.get("evidence") or []
    contradictions = parsed.get("contradictions") or []
    screen_type = str(parsed.get("screen_type") or parsed.get("screen") or view.get("screen") or features.screen_bucket or "unknown").strip().lower() or "unknown"
    active_surface = str(parsed.get("active_surface") or parsed.get("surface") or features.extras.get("active_surface") or "").strip().lower()
    likely_next_family = str(parsed.get("likely_next_family") or parsed.get("next_family") or parsed.get("choice_family") or "observe").strip().lower() or "observe"
    likely_next_target = str(parsed.get("likely_next_target") or parsed.get("target") or "").strip()
    likely_next_text = str(parsed.get("likely_next_text") or parsed.get("text") or "").strip()
    conf_raw = parsed.get("confidence", parsed.get("score", 0.0))
    try:
        confidence = max(0.0, min(1.0, float(conf_raw or 0.0)))
    except (TypeError, ValueError):
        confidence = 0.0
    return PerceptionSynthesis(
        screen_type=screen_type,
        active_surface=active_surface,
        likely_next_family=likely_next_family,
        likely_next_target=likely_next_target,
        likely_next_text=likely_next_text,
        confidence=confidence,
        avoid_families=[str(x).strip().lower() for x in avoid if str(x).strip()],
        supporting_evidence=[str(x) for x in evidence if str(x)],
        contradictions=[str(x) for x in contradictions if str(x)],
        needs_followup_observe=bool(parsed.get("needs_followup_observe", parsed.get("needs_observe", False))),
        raw=parsed,
    )


def _format_perception_human_readable(
    summary: PerceptionSynthesis,
    *,
    task_name: str,
    target: Optional[Dict[str, Any]] = None,
    cache_hit: bool = False,
) -> str:
    parts = [
        f"Perception summary[{task_name}]",
        "(cached)" if cache_hit else "(fresh)",
        f"screen={summary.screen_type or 'unknown'}",
        f"surface={summary.active_surface or 'unknown'}",
        f"next={summary.likely_next_family or 'observe'}",
    ]
    if summary.likely_next_target:
        parts.append(f"target={summary.likely_next_target}")
    if summary.likely_next_text:
        parts.append(f"text={_clip_text(summary.likely_next_text, 120)}")
    parts.append(f"confidence={float(summary.confidence or 0.0):.2f}")
    if target:
        parts.append(
            "route="
            + "/".join(
                [
                    str(target.get("provider") or "").strip() or "auto",
                    str(target.get("model") or "").strip() or "default",
                ]
            )
        )
    if summary.supporting_evidence:
        parts.append(f"evidence={_clip_text(' | '.join(summary.supporting_evidence), 220)}")
    if summary.contradictions:
        parts.append(f"contradictions={_clip_text(' | '.join(summary.contradictions), 160)}")
    if summary.needs_followup_observe:
        parts.append("followup_observe=True")
    return " ; ".join(parts)


def synthesize_perception(
    goal: Goal,
    world: WorldModel,
    view: Dict[str, Any],
    features: StateFeatures | Dict[str, Any],
    *,
    worldview: float | None = None,
) -> Optional[PerceptionSynthesis]:
    """Return a reusable, cached screen interpretation when the state is ambiguous."""
    features_obj, features_dict = _coerce_state_features(features)
    if worldview is not None:
        features_obj.worldview_score = float(worldview)
    if not _should_run_perception_llm(view, features_obj):
        return None

    task_name = _select_perception_task_name(view, features_obj)
    cache_key = _perception_cache_key(goal, world, view, features_obj, task_name=task_name)
    cached = getattr(world, "last_perception_synthesis", None) or {}
    if isinstance(cached, dict) and cached.get("cache_key") == cache_key:
        raw = cached.get("summary")
        if isinstance(raw, dict):
            summary = _parse_summary(raw, goal, view, features_obj)
            logger.info(
                "Perception LLM human summary: %s",
                _format_perception_human_readable(
                    summary,
                    task_name=task_name,
                    target=raw.get("selected_target") if isinstance(raw.get("selected_target"), dict) else None,
                    cache_hit=True,
                ),
            )
            return summary

    try:
        main_runtime = _main_runtime_snapshot()
        prompt_shape = _perception_prompt_shape()
        prompt_shapes = [prompt_shape]
        if prompt_shape != "rich":
            prompt_shapes.append("rich")
        max_tokens = max(192, _perception_max_tokens())
        targets = _perception_task_targets(main_runtime, task_name=task_name)
        min_confidence = _perception_min_confidence()
        summary = None
        best_summary = None
        best_consultation = None
        best_target: Optional[Dict[str, Any]] = None
        best_shape = ""
        total_attempts = 0
        logger.info(
            "Perception LLM target chain: task=%s min_confidence=%.2f targets=%s",
            task_name,
            min_confidence,
            [
                f"{str(t.get('provider') or '').strip()}/{str(t.get('model') or '').strip()}"
                for t in targets
            ],
        )
        for target_index, target in enumerate(targets, start=1):
            for attempt, shape in enumerate(prompt_shapes, start=1):
                total_attempts += 1
                prompt_messages = _build_prompt(
                    goal,
                    world,
                    view,
                    features_obj,
                    prompt_shape=shape,
                    task_name=task_name,
                )
                prompt_payload = {}
                prompt_text = ""
                try:
                    user_content = prompt_messages[1]["content"]
                    if isinstance(user_content, str):
                        prompt_text = user_content
                        prompt_payload = json.loads(user_content)
                    elif isinstance(user_content, list):
                        text_parts = [
                            str((part or {}).get("text") or "")
                            for part in user_content
                            if isinstance(part, dict) and part.get("type") == "text"
                        ]
                        prompt_text = "\n".join(text_parts)
                        if text_parts:
                            prompt_payload = json.loads(text_parts[0])
                except Exception:
                    prompt_payload = {}
                entity_count = len(((prompt_payload.get("evidence") or {}).get("visible_entities") or []))
                context_count = len(((prompt_payload.get("evidence") or {}).get("conversation_context") or []))
                logger.info(
                    "Perception LLM prompt built: goal=%s target=%d/%d attempt=%d entities=%d context=%d chars=%d search_surface=%s shape=%s max_tokens=%d",
                    goal.kind,
                    target_index,
                    len(targets),
                    attempt,
                    entity_count,
                    context_count,
                    len(prompt_text or str(prompt_messages[1]["content"])),
                    bool(view.get("search_focused")) or str(view.get("screen") or "").upper() in {"SEARCH", "SEARCH_RESULTS"},
                    shape,
                    max_tokens,
                )
                logger.info(
                    "Perception LLM route: task=%s runtime_provider=%s runtime_model=%s target_provider=%s target_model=%s target_base_url=%s api_key_present=%s target_source=%s",
                    task_name,
                    str(main_runtime.get("provider") or ""),
                    str(main_runtime.get("model") or ""),
                    str(target.get("provider") or ""),
                    str(target.get("model") or ""),
                    str(target.get("base_url") or ""),
                    bool(str(target.get("api_key") or "").strip()),
                    str(target.get("source") or ""),
                )
                start = time.time()
                consultation = consult_reasoning(
                    task_name,
                    prompt_messages,
                    caller=lambda **kwargs: _call_llm_hard_timeout(
                        _perception_timeout_seconds(),
                        **kwargs,
                    ),
                    call_kwargs={
                        "task": task_name,
                        "provider": target.get("provider") or None,
                        "model": target.get("model") or None,
                        "base_url": target.get("base_url") or None,
                        "api_key": target.get("api_key") or None,
                        "timeout": _perception_timeout_seconds(),
                        "main_runtime": main_runtime,
                        "extra_body": _perception_extra_body(main_runtime),
                        "reasoning_config": _perception_reasoning_config(target),
                    },
                    temperature=0.0,
                    max_tokens=max_tokens,
                )
                elapsed = time.time() - start
                logger.info("Perception LLM completed in %.2fs", elapsed)
                raw_text = consultation.raw_response
                parsed = consultation.parsed
                if parsed:
                    candidate_summary = _parse_summary(parsed, goal, view, features_obj)
                    features_obj.extras["perception_consultation"] = consultation.to_dict()
                    if best_summary is None or candidate_summary.confidence > best_summary.confidence:
                        best_summary = candidate_summary
                        best_consultation = consultation
                        best_target = target
                        best_shape = shape
                    if candidate_summary.confidence >= min_confidence and not candidate_summary.needs_followup_observe:
                        summary = candidate_summary
                        best_consultation = consultation
                        best_target = target
                        best_shape = shape
                        break
                    logger.info(
                        "Perception LLM candidate insufficient: task=%s target=%s/%s confidence=%.3f needs_followup_observe=%s threshold=%.2f — advancing to next candidate",
                        task_name,
                        str(target.get("provider") or ""),
                        str(target.get("model") or ""),
                        candidate_summary.confidence,
                        candidate_summary.needs_followup_observe,
                        min_confidence,
                    )
                    continue
                logger.warning(
                    "Perception LLM returned non-JSON response on target %d/%d attempt %d/%d (shape=%s): %s",
                    target_index,
                    len(targets),
                    attempt,
                    len(prompt_shapes),
                    shape,
                    raw_text[:1200],
                )
            if summary is not None:
                break
        if summary is None:
            summary = best_summary
        if summary is None:
            raise RuntimeError("Perception LLM returned non-JSON response")
    except Exception as exc:  # pragma: no cover - perception must remain resilient
        from agent.auxiliary_client import LLMProviderExhaustedError

        if isinstance(exc, LLMProviderExhaustedError) or _perception_fail_hard():
            raise
        raise RuntimeError("perception synthesis failed without an LLM result") from exc

    result = summary.to_dict()
    result["cache_key"] = cache_key
    if best_consultation is not None:
        result["consultation"] = best_consultation.to_dict()
    if best_target is not None:
        result["selected_target"] = {
            "provider": best_target.get("provider"),
            "model": best_target.get("model"),
            "base_url": best_target.get("base_url"),
            "source": best_target.get("source"),
            "rank": best_target.get("rank"),
            "shape": best_shape,
        }
    logger.info(
        "Perception LLM human summary: %s",
        _format_perception_human_readable(
            summary,
            task_name=task_name,
            target=result.get("selected_target") if isinstance(result.get("selected_target"), dict) else None,
            cache_hit=False,
        ),
    )
    world.last_perception_synthesis = {
        "cache_key": cache_key,
        "summary": result,
    }
    features_obj.extras["perception_llm"] = result
    features_obj.extras["perception_human_readable"] = _format_perception_human_readable(
        summary,
        task_name=task_name,
        target=result.get("selected_target") if isinstance(result.get("selected_target"), dict) else None,
        cache_hit=False,
    )
    features_obj.extras["perception_summary"] = {
        "screen_type": result.get("screen_type", "unknown"),
        "active_surface": result.get("active_surface", ""),
        "likely_next_family": result.get("likely_next_family", "observe"),
        "likely_next_target": result.get("likely_next_target", ""),
        "confidence": result.get("confidence", 0.0),
    }
    features_obj.extras["perception_task"] = task_name
    if features_dict is not None:
        extras = features_dict.setdefault("extras", {})
        if isinstance(extras, dict):
            extras["perception_llm"] = result
            extras["perception_human_readable"] = features_obj.extras.get("perception_human_readable")
            extras["perception_summary"] = dict(features_obj.extras.get("perception_summary") or {})
            extras["perception_task"] = task_name
    return summary
