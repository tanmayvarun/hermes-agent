"""Task-aware model routing for Hermes Agent.

This module sits above the provider catalogs and selects a task-specific
subset of the *currently active* models.

The goal is to keep the core policy centralized:

* ``chat_runtime`` prefers deep, high-capacity models for planning and
  synthesis. The default floor is 100B when model size is knowable.
* ``computer_use`` prefers fast iterative models. The default band is
  14B..32B when model size is knowable.

The router merges:

* the existing active provider rows from ``list_authenticated_providers``
* explicitly configured provider plugins such as remote Ollama

and then ranks the resulting model candidates using capability metadata
already present in the repo.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log2
import os
from typing import Any, Iterable, Optional

from agent.models_dev import get_model_info
from hermes_cli.model_latency import model_latency_priority
from hermes_cli.auth import is_provider_explicitly_configured
from hermes_cli.fallback_config import estimate_model_params_b
from hermes_cli.model_switch import list_authenticated_providers
from hermes_cli.models import provider_model_ids
from providers import get_provider_profile, list_providers


@dataclass(frozen=True)
class TaskModelProfile:
    """Routing policy for a task family."""

    name: str
    min_params_b: float | None = None
    max_params_b: float | None = None
    prefer_size: str = "larger"  # larger | smaller
    require_tool_call: bool = True
    prefer_reasoning: bool = True
    prefer_structured_output: bool = True
    prefer_vision: bool = False
    prefer_local: bool = False
    preferred_models: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskModelCandidate:
    """A single ranked model candidate for a task."""

    provider: str
    model: str
    score: float
    base_url: str = ""
    params_b: float | None = None
    context_window: int = 0
    reasoning: bool = False
    tool_call: bool = False
    structured_output: bool = False
    vision: bool = False
    source: str = ""
    notes: tuple[str, ...] = ()


_TASK_ALIASES: dict[str, str] = {
    "chat": "chat_runtime",
    "assistant": "chat_runtime",
    "planning": "chat_runtime",
    "chat_runtime": "chat_runtime",
    "perception": "perception",
    "screen_perception": "perception",
    "vision": "screen_understanding",
    "screen_understanding": "screen_understanding",
    "screen_understand": "screen_understanding",
    "screen_parse": "screen_understanding",
    "surface_analysis": "screen_understanding",
    "computer": "computer_use",
    "computer_use": "computer_use",
    "gui": "computer_use",
    "computer-use": "computer_use",
}

TASK_PROFILES: dict[str, TaskModelProfile] = {
    "chat_runtime": TaskModelProfile(
        name="chat_runtime",
        min_params_b=100.0,
        prefer_size="larger",
        require_tool_call=True,
        prefer_reasoning=True,
        prefer_structured_output=True,
        prefer_local=False,
    ),
    "computer_use": TaskModelProfile(
        name="computer_use",
        min_params_b=14.0,
        max_params_b=32.0,
        prefer_size="smaller",
        require_tool_call=True,
        prefer_reasoning=False,
        prefer_structured_output=True,
        prefer_local=True,
    ),
    "perception": TaskModelProfile(
        name="perception",
        min_params_b=14.0,
        max_params_b=32.0,
        prefer_size="smaller",
        require_tool_call=True,
        prefer_reasoning=True,
        prefer_structured_output=True,
        prefer_local=True,
    ),
    "screen_understanding": TaskModelProfile(
        name="screen_understanding",
        min_params_b=100.0,
        prefer_size="larger",
        require_tool_call=True,
        prefer_reasoning=True,
        prefer_structured_output=True,
        prefer_vision=True,
        prefer_local=False,
        # Every model here MUST be included-plan. A single extra-usage model that
        # 402s ("extra usage balance empty") marks the whole ollama-cloud provider
        # unhealthy for 600s, poisoning the working vision model on every later
        # cycle. kimi-k3 is extra-usage-only AND text-only (rejects images), so it
        # was pure downside in the vision chain — dropped. qwen3.5 is the proven
        # included-plan vision model; gemma4 is an included-plan safety net (worst
        # case a 500, which does not poison the provider like a 402 does).
        preferred_models=("qwen3.5:cloud", "gemma4:cloud"),
    ),
}


def get_task_profile(task: str | None) -> TaskModelProfile:
    """Return the canonical routing profile for *task*."""
    normalized = str(task or "").strip().lower().replace(" ", "_")
    canonical = _TASK_ALIASES.get(normalized, normalized)
    return TASK_PROFILES.get(canonical, TASK_PROFILES["chat_runtime"])


def _is_local_provider(provider: str, base_url: str = "") -> bool:
    slug = (provider or "").strip().lower()
    if slug in {"ollama-remote", "lmstudio"}:
        return True
    host = (base_url or "").strip().lower()
    if not host:
        return False
    return any(token in host for token in ("localhost", "127.0.0.1", "::1"))


def _allow_remote_ollama_for_chat_runtime() -> bool:
    """Return True when chat-runtime routing may include hosted Ollama.

    Default: off.  Realtime chat should not depend on hosted Ollama because
    the remote box can be materially slower / less responsive than the main
    cloud path.  Computer-use tasks still keep hosted Ollama in play via the
    task profile's local-provider preference.
    """
    value = str(os.getenv("HERMES_ALLOW_OLLAMA_REMOTE_CHAT", "") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _provider_rows(
    *,
    task_profile: TaskModelProfile,
    current_provider: str = "",
    current_base_url: str = "",
    rows: Optional[list[dict[str, Any]]] = None,
    refresh: bool = False,
    probe_custom_providers: bool = True,
    probe_current_custom_provider: bool = False,
) -> list[dict[str, Any]]:
    if rows is None:
        rows = list_authenticated_providers(
            current_provider=current_provider,
            current_base_url=current_base_url,
            max_models=None,
            refresh=refresh,
            for_picker=False,
            probe_custom_providers=probe_custom_providers,
            probe_current_custom_provider=probe_current_custom_provider,
            min_params_b=task_profile.min_params_b,
        )
    else:
        rows = [dict(row) for row in rows if isinstance(row, dict)]
        if task_profile.name == "chat_runtime" and not _allow_remote_ollama_for_chat_runtime():
            rows = [
                row
                for row in rows
                if str(row.get("slug") or "").strip().lower() != "ollama-remote"
            ]

    seen: set[str] = {str(row.get("slug", "")).strip().lower() for row in rows if row.get("slug")}
    for profile in list_providers():
        slug = str(profile.name or "").strip().lower()
        if not slug or slug in seen:
            continue
        if task_profile.name == "chat_runtime" and slug == "ollama-remote" and not _allow_remote_ollama_for_chat_runtime():
            continue
        if not is_provider_explicitly_configured(slug):
            continue

        models = provider_model_ids(slug, min_params_b=task_profile.min_params_b)
        if not models:
            models = list(profile.fallback_models or ())
        if not models:
            continue

        rows.append(
            {
                "slug": slug,
                "name": profile.display_name or profile.name,
                "is_current": False,
                "is_user_defined": False,
                "models": list(models),
                "total_models": len(models),
                "source": "plugin",
                "api_url": profile.base_url,
            }
        )
        seen.add(slug)
    return rows


def _candidate_notes(
    *,
    task_profile: TaskModelProfile,
    provider: str,
    model: str,
    params_b: float | None,
    reasoning: bool,
    tool_call: bool,
    structured_output: bool,
    context_window: int,
    local_provider: bool,
) -> tuple[str, ...]:
    notes: list[str] = []
    if params_b is not None:
        notes.append(f"params={params_b:g}B")
    else:
        notes.append("params=unknown")
    if tool_call:
        notes.append("tool_call")
    if reasoning:
        notes.append("reasoning")
    if structured_output:
        notes.append("structured_output")
    if context_window:
        notes.append(f"context={context_window}")
    if local_provider:
        notes.append("local")
    if provider:
        notes.append(f"provider={provider}")
    if model:
        notes.append(f"model={model}")
    if task_profile.name:
        notes.append(f"task={task_profile.name}")
    return tuple(notes)


def _preferred_model_rank(task_profile: TaskModelProfile, provider: str, model: str) -> int | None:
    """Return the 0-based rank for a profile's preferred model list."""
    if not task_profile.preferred_models:
        return None
    provider_norm = str(provider or "").strip().lower()
    model_norm = str(model or "").strip().lower()
    for idx, preferred in enumerate(task_profile.preferred_models):
        pref_norm = str(preferred or "").strip().lower()
        if not pref_norm:
            continue
        if pref_norm == model_norm:
            return idx
        if provider_norm and pref_norm == f"{provider_norm}/{model_norm}":
            return idx
    return None


def _score_candidate(
    *,
    task_profile: TaskModelProfile,
    provider: str,
    model: str,
    params_b: float | None,
    reasoning: bool,
    tool_call: bool,
    structured_output: bool,
    vision: bool,
    context_window: int,
    local_provider: bool,
    current_provider: bool,
    preferred_rank: int | None,
) -> float:
    score = 0.0

    if preferred_rank is not None:
        score += max(0.0, 6.0 - (preferred_rank * 1.25))

    if tool_call:
        score += 2.0
    if task_profile.require_tool_call and not tool_call:
        score -= 5.0

    if reasoning:
        score += 1.5 if task_profile.prefer_reasoning else 0.5

    if structured_output:
        score += 0.75 if task_profile.prefer_structured_output else 0.25

    if vision:
        score += 0.4 if task_profile.prefer_vision else 0.05
    elif task_profile.prefer_vision:
        score -= 0.2

    if context_window > 0:
        score += min(context_window / 200000.0, 1.0) * 0.8

    if local_provider and task_profile.prefer_local:
        score += 0.75

    if current_provider:
        score += 0.2

    if params_b is not None:
        if task_profile.min_params_b is not None and params_b < task_profile.min_params_b:
            score -= 3.0
        if task_profile.max_params_b is not None and params_b > task_profile.max_params_b:
            score -= 3.0

        if task_profile.prefer_size == "larger":
            if task_profile.min_params_b and params_b >= task_profile.min_params_b:
                ratio = params_b / task_profile.min_params_b
                score += min(1.25, log2(max(ratio, 1.0) + 1.0) / 2.0)
            else:
                score += min(0.5, params_b / 100.0)
        else:
            if task_profile.max_params_b and task_profile.min_params_b and task_profile.max_params_b > task_profile.min_params_b:
                span = task_profile.max_params_b - task_profile.min_params_b
                normalized = max(0.0, min(1.0, (params_b - task_profile.min_params_b) / span))
                score += 1.25 - normalized
            elif task_profile.min_params_b:
                score += max(0.0, 1.0 - (params_b / max(task_profile.min_params_b, 1.0)))
    else:
        # Unknown size: keep it in play, but do not let it outrank known
        # in-band models for the current task.
        score += 0.1
        if task_profile.prefer_size == "larger" and reasoning and context_window >= 128000:
            score += 0.35
        if task_profile.prefer_size == "smaller" and local_provider and tool_call:
            score += 0.25

    return score


def rank_task_models(
    task: str | None,
    *,
    current_provider: str = "",
    current_base_url: str = "",
    rows: Optional[list[dict[str, Any]]] = None,
    refresh: bool = False,
    probe_custom_providers: bool = True,
    probe_current_custom_provider: bool = False,
) -> list[TaskModelCandidate]:
    """Return task-specific model candidates sorted best-first."""
    profile = get_task_profile(task)
    provider_rows = _provider_rows(
        task_profile=profile,
        current_provider=current_provider,
        current_base_url=current_base_url,
        rows=rows,
        refresh=refresh,
        probe_custom_providers=probe_custom_providers,
        probe_current_custom_provider=probe_current_custom_provider,
    )

    candidates: list[TaskModelCandidate] = []
    current_slug = (current_provider or "").strip().lower()
    for row in provider_rows:
        provider = str(row.get("slug") or "").strip().lower()
        model_ids = row.get("models") or []
        if not isinstance(model_ids, list):
            continue
        api_url = str(row.get("api_url") or "").strip()
        local_provider = _is_local_provider(provider, api_url)
        is_current_provider = bool(row.get("is_current")) or (provider and provider == current_slug)
        for model in model_ids:
            if not isinstance(model, str):
                continue
            model = model.strip()
            if not model:
                continue
            params_b = estimate_model_params_b(model)
            model_info = None
            try:
                model_info = get_model_info(provider, model)
            except Exception:
                model_info = None
            preferred_rank = _preferred_model_rank(profile, provider, model)
            is_preferred = preferred_rank is not None

            # Chat-runtime routing must stay high-confidence: if we cannot
            # establish that a model is large enough, do not let it into the
            # live chain. This keeps the selector from drifting into unrelated
            # OAuth/backdoor providers that merely happen to be authenticated.
            if profile.name == "chat_runtime" and params_b is None:
                continue

            tool_call = bool(model_info.tool_call) if model_info is not None else True
            reasoning = bool(model_info.reasoning) if model_info is not None else False
            structured_output = bool(model_info.structured_output) if model_info is not None else False
            vision = bool(model_info.supports_vision()) if model_info is not None else False
            context_window = int(model_info.context_window) if model_info is not None else 0

            if profile.require_tool_call and not tool_call:
                continue
            if (
                profile.prefer_size == "larger"
                and params_b is not None
                and profile.min_params_b is not None
                and params_b < profile.min_params_b
                and not is_preferred
            ):
                continue
            if (
                profile.prefer_size == "smaller"
                and params_b is not None
                and profile.max_params_b is not None
                and params_b > profile.max_params_b
                and not is_preferred
            ):
                continue
            if profile.prefer_vision and model_info is not None and not vision and not is_preferred:
                continue

            score = _score_candidate(
                task_profile=profile,
                provider=provider,
                model=model,
                params_b=params_b,
                reasoning=reasoning,
                tool_call=tool_call,
                structured_output=structured_output,
                vision=vision,
                context_window=context_window,
                local_provider=local_provider,
                current_provider=is_current_provider,
                preferred_rank=preferred_rank,
            )
            if (
                profile.name == "chat_runtime"
                and provider == "openrouter"
                and model == "openai/gpt-oss-120b"
            ):
                score += 2.0
            notes = _candidate_notes(
                task_profile=profile,
                provider=provider,
                model=model,
                params_b=params_b,
                reasoning=reasoning,
                tool_call=tool_call,
                structured_output=structured_output,
                context_window=context_window,
                local_provider=local_provider,
            )
            candidates.append(
                TaskModelCandidate(
                    provider=provider,
                    model=model,
                    base_url=api_url,
                    score=score,
                    params_b=params_b,
                    context_window=context_window,
                    reasoning=reasoning,
                    tool_call=tool_call,
                    structured_output=structured_output,
                    vision=vision,
                    source=str(row.get("source") or ""),
                    notes=notes,
                )
            )

    candidates.sort(
        key=lambda c: (
            -c.score,
            *model_latency_priority(c.provider, c.model, task=profile.name, base_url=c.base_url),
            -(c.params_b or 0.0),
            -c.context_window,
            c.provider,
            c.model.lower(),
        )
    )
    return candidates


def select_task_model_ids(
    task: str | None,
    *,
    current_provider: str = "",
    current_base_url: str = "",
    rows: Optional[list[dict[str, Any]]] = None,
    refresh: bool = False,
    limit: int | None = None,
    probe_custom_providers: bool = True,
    probe_current_custom_provider: bool = False,
) -> list[str]:
    """Return ranked model IDs for a task."""
    candidates = rank_task_models(
        task,
        current_provider=current_provider,
        current_base_url=current_base_url,
        rows=rows,
        refresh=refresh,
        probe_custom_providers=probe_custom_providers,
        probe_current_custom_provider=probe_current_custom_provider,
    )
    if limit is not None:
        candidates = candidates[:limit]
    return [f"{c.provider}/{c.model}" for c in candidates]


def select_task_model_subset(
    task: str | None,
    *,
    current_provider: str = "",
    current_base_url: str = "",
    rows: Optional[list[dict[str, Any]]] = None,
    refresh: bool = False,
    per_provider_limit: int | None = 3,
    total_limit: int | None = 12,
    probe_custom_providers: bool = True,
    probe_current_custom_provider: bool = False,
) -> dict[str, list[str]]:
    """Return the best models per provider for a task.

    The result preserves the global ranking while grouping by provider so
    callers can show a compact subset instead of an entire active catalog.
    """
    ranked = rank_task_models(
        task,
        current_provider=current_provider,
        current_base_url=current_base_url,
        rows=rows,
        refresh=refresh,
        probe_custom_providers=probe_custom_providers,
        probe_current_custom_provider=probe_current_custom_provider,
    )

    subset: dict[str, list[str]] = {}
    remaining = total_limit if total_limit is not None else None
    for candidate in ranked:
        if remaining is not None and remaining <= 0:
            break
        bucket = subset.setdefault(candidate.provider, [])
        if per_provider_limit is not None and len(bucket) >= per_provider_limit:
            continue
        bucket.append(candidate.model)
        if remaining is not None:
            remaining -= 1
    return subset
