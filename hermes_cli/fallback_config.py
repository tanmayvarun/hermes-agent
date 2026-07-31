"""Helpers for reading the effective ordered model chain from config."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# Hard floor for Hermes agentic use: never select undersized models.
MIN_ALLOWED_PARAMS_B = 100.0

# Explicit sizes for model IDs that do not embed a parameter count in the name.
# Used by min_params_b filtering (fail-closed for unknown IDs when a threshold
# is set — these overrides keep well-known small models correctly excluded).
_KNOWN_PARAMS_B: dict[str, float] = {
    "codestral-latest": 22.0,
    "codestral": 22.0,
    "openrouter/free": 0.0,  # opaque router — treat as unknown/small
}

# Capture every NNb / NN.Nb token in a model id (e.g. gpt-oss:120b, 550b-a55b).
_PARAM_TOKEN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[bB]\b")


def _normalized_base_url(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().rstrip("/")


def resolve_entry_api_key(entry: dict[str, Any] | None) -> str | None:
    """API key for one fallback entry: inline ``api_key``, else ``key_env``.

    Mirrors the custom-provider convention (``key_env`` names the env var
    holding the key; ``api_key_env`` accepted as an alias). Returns None when
    neither yields a non-empty value, letting ``resolve_runtime_provider``
    fall through to the provider's standard credential resolution.
    """
    if not isinstance(entry, dict):
        return None
    inline = str(entry.get("api_key") or "").strip()
    if inline:
        return inline
    key_env = str(entry.get("key_env") or entry.get("api_key_env") or "").strip()
    if key_env:
        return os.getenv(key_env, "").strip() or None
    return None


def estimate_model_params_b(model_id: str | None) -> float | None:
    """Best-effort parameter count in billions for a model id.

    Prefers an embedded size token (``120b``, ``550b-a55b`` → 550) over the
    known-overrides table. Returns ``None`` when no size can be inferred.
    """
    if not model_id or not isinstance(model_id, str):
        return None
    mid = model_id.strip()
    if not mid:
        return None

    lower = mid.lower()
    if lower in _KNOWN_PARAMS_B:
        return float(_KNOWN_PARAMS_B[lower])
    # Also match bare id without provider prefix.
    bare = lower.rsplit("/", 1)[-1]
    if bare in _KNOWN_PARAMS_B:
        return float(_KNOWN_PARAMS_B[bare])

    tokens = [float(m.group(1)) for m in _PARAM_TOKEN_RE.finditer(mid)]
    if not tokens:
        return None
    return max(tokens)


def get_min_params_b(config: dict[str, Any] | None) -> float | None:
    """Return the effective ``min_params_b`` floor.

    Hermes now treats ``100`` as the minimum acceptable model size by default.
    A higher explicit config value may raise the floor further, but the floor
    never drops below ``MIN_ALLOWED_PARAMS_B``.
    """
    config = config or {}
    raw: Any = None
    model_cfg = config.get("model")
    if isinstance(model_cfg, dict) and "min_params_b" in model_cfg:
        raw = model_cfg.get("min_params_b")
    elif "min_params_b" in config:
        raw = config.get("min_params_b")

    if raw in (None, "", False):
        return MIN_ALLOWED_PARAMS_B
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return MIN_ALLOWED_PARAMS_B
    if value <= 0:
        return MIN_ALLOWED_PARAMS_B
    return max(float(value), MIN_ALLOWED_PARAMS_B)


def meets_min_params_b(model_id: str | None, min_params_b: float | None) -> bool:
    """True when *model_id* meets the threshold (or filtering is disabled).

    Unknown sizes fail closed when a threshold is active.
    """
    if min_params_b is None:
        min_params_b = MIN_ALLOWED_PARAMS_B
    size = estimate_model_params_b(model_id)
    if size is None:
        return False
    return size >= float(min_params_b)


def _iter_fallback_entries(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        candidates = [raw]
    elif isinstance(raw, list):
        candidates = raw
    else:
        return []

    entries: list[dict[str, Any]] = []
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        provider = str(entry.get("provider") or "").strip()
        model = str(entry.get("model") or "").strip()
        if not provider or not model:
            continue

        normalized = dict(entry)
        normalized["provider"] = provider
        normalized["model"] = model

        base_url = _normalized_base_url(entry.get("base_url"))
        if base_url:
            normalized["base_url"] = base_url

        entries.append(normalized)
    return entries


def _entry_identity(entry: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(entry.get("provider") or "").strip().lower(),
        str(entry.get("model") or "").strip().lower(),
        _normalized_base_url(entry.get("base_url")).lower(),
    )


def get_ordered_model_chain(config: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return the effective ordered model chain merged across config keys.

    ``fallback_providers`` remains the primary source of truth and keeps its
    order. Legacy ``fallback_model`` entries are appended afterwards unless
    they target the same provider/model/base_url route as an earlier entry.
    The returned list always contains fresh dict copies.

    When ``model.min_params_b`` (or top-level ``min_params_b``) is a positive
    number, entries whose model id is below that size — or whose size cannot
    be estimated — are dropped.
    """

    config = config or {}
    chain: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for key in ("fallback_providers", "fallback_model"):
        for entry in _iter_fallback_entries(config.get(key)):
            identity = _entry_identity(entry)
            if identity in seen:
                continue
            seen.add(identity)
            chain.append(entry)

    min_b = get_min_params_b(config)
    if min_b is None:
        return chain

    filtered: list[dict[str, Any]] = []
    for entry in chain:
        model = str(entry.get("model") or "")
        if meets_min_params_b(model, min_b):
            filtered.append(entry)
        else:
            size = estimate_model_params_b(model)
            logger.info(
                "min_params_b=%.0f: dropping fallback %s/%s (estimated=%s)",
                min_b,
                entry.get("provider"),
                model,
                f"{size:.0f}B" if size is not None else "unknown",
                )
    # Preserve the declared provider order. Latency-based preference is a
    # separate concern and must not silently reshuffle an explicit fallback
    # chain here, otherwise the runtime can diverge from the user's intended
    # left-to-right order.
    return filtered


def get_fallback_chain(config: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Backward-compatible alias for :func:`get_ordered_model_chain`.

    The repo still has older call sites and config copy that say "fallback"
    even though the behavior is an ordered left-to-right model list. Keep the
    old name working, but make the canonical semantics explicit through the
    new helper.
    """
    return get_ordered_model_chain(config)


def _filter_fallback_raw(raw: Any, min_b: float) -> Any:
    """Drop undersized entries from a fallback_providers / fallback_model value."""
    if isinstance(raw, dict):
        model = str(raw.get("model") or "").strip()
        if model and meets_min_params_b(model, min_b):
            return raw
        if model:
            size = estimate_model_params_b(model)
            logger.info(
                "min_params_b=%.0f: dropping fallback %s/%s (estimated=%s)",
                min_b,
                raw.get("provider"),
                model,
                f"{size:.0f}B" if size is not None else "unknown",
            )
        return {}
    if isinstance(raw, list):
        kept: list[dict[str, Any]] = []
        for entry in _iter_fallback_entries(raw):
            model = str(entry.get("model") or "")
            if meets_min_params_b(model, min_b):
                kept.append(entry)
            else:
                size = estimate_model_params_b(model)
                logger.info(
                    "min_params_b=%.0f: dropping fallback %s/%s (estimated=%s)",
                    min_b,
                    entry.get("provider"),
                    model,
                    f"{size:.0f}B" if size is not None else "unknown",
                )
        return kept
    return raw


def apply_min_params_b(config: dict[str, Any] | None) -> dict[str, Any]:
    """Enforce ``min_params_b`` on primary model + fallback lists in-place.

    - Filters ``fallback_providers`` / ``fallback_model`` to entries at or
      above the threshold (unknown sizes fail closed).
    - If the primary ``model.default`` is under the threshold (or unknown),
      promote the first remaining fallback into ``model.default`` /
      ``model.provider``.
    """
    if not isinstance(config, dict):
        return {}

    min_b = get_min_params_b(config)
    if min_b is None:
        min_b = MIN_ALLOWED_PARAMS_B

    if "fallback_providers" in config:
        config["fallback_providers"] = _filter_fallback_raw(
            config.get("fallback_providers"), min_b
        )
    if "fallback_model" in config:
        config["fallback_model"] = _filter_fallback_raw(
            config.get("fallback_model"), min_b
        )

    filtered = get_fallback_chain(config)

    model_cfg = config.get("model")
    if not isinstance(model_cfg, dict):
        if filtered:
            first = filtered[0]
            config["model"] = {
                "default": first["model"],
                "provider": first["provider"],
                "min_params_b": min_b,
            }
            # Remove the promoted entry from fallback_providers if present.
            _drop_promoted_from_providers(config, first)
        return config

    primary = str(model_cfg.get("default") or model_cfg.get("model") or "").strip()
    if primary and meets_min_params_b(primary, min_b):
        return config

    if not filtered:
        logger.warning(
            "min_params_b=%.0f: primary %r is below threshold and no "
            "fallback meets the floor",
            min_b,
            primary or "(unset)",
        )
        return config

    first = filtered[0]
    old = primary or "(unset)"
    model_cfg["default"] = first["model"]
    model_cfg["provider"] = first["provider"]
    _drop_promoted_from_providers(config, first)
    logger.info(
        "min_params_b=%.0f: promoted primary %s → %s/%s",
        min_b,
        old,
        first["provider"],
        first["model"],
    )
    return config


def _drop_promoted_from_providers(
    config: dict[str, Any], promoted: dict[str, Any]
) -> None:
    """Remove the promoted primary from ``fallback_providers`` so it is not tried twice."""
    raw = config.get("fallback_providers")
    if not isinstance(raw, list):
        return
    identity = _entry_identity(promoted)
    config["fallback_providers"] = [
        entry
        for entry in _iter_fallback_entries(raw)
        if _entry_identity(entry) != identity
    ]
