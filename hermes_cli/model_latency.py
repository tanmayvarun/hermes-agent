"""Persistent moving-average latency history for model/provider routing.

This module records successful LLM response latencies in a small JSON cache
so Hermes can prefer models that have historically responded faster for the
same task or provider/model pair.

The cache is best-effort:
- writes are atomic-ish but never block the caller on failure
- unknown paths fall back to a repo-local cache under ``.hermes/``
- missing history simply leaves the original ordering intact
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

_LATENCY_ALPHA = 0.2
_LATENCY_STORE_ENV = "HERMES_MODEL_LATENCY_PATH"
_LATENCY_LOCK = threading.Lock()
_DEFAULT_TASK = "__default__"


def _repo_latency_store_path() -> Path:
    return Path(__file__).resolve().parents[1] / ".hermes" / "model_latency.json"


def latency_store_path() -> Path:
    raw = os.getenv(_LATENCY_STORE_ENV, "").strip()
    if raw:
        return Path(raw).expanduser()
    return _repo_latency_store_path()


def _normalize_provider(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_model(value: Any) -> str:
    return str(value or "").strip()


def _normalize_base_url(value: Any) -> str:
    return str(value or "").strip().rstrip("/").lower()


def _normalize_task(value: Any) -> str:
    task = str(value or "").strip().lower()
    return task or _DEFAULT_TASK


def _entry_key(
    provider: str,
    model: str,
    *,
    task: str | None = None,
    base_url: str = "",
) -> str:
    return "|".join(
        [
            _normalize_task(task),
            _normalize_provider(provider),
            _normalize_model(model),
            _normalize_base_url(base_url),
        ]
    )


def _safe_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except Exception:
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _load_store() -> dict[str, Any]:
    path = latency_store_path()
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict):
            entries = data.get("entries")
            if isinstance(entries, dict):
                return data
    except Exception:
        pass
    return {"version": 1, "entries": {}}


def _write_store(data: Mapping[str, Any]) -> None:
    path = latency_store_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(path)
    except Exception:
        # Best-effort only. Latency history must never block the caller.
        return


def _update_entry(
    data: dict[str, Any],
    *,
    provider: str,
    model: str,
    latency_s: float,
    success: bool,
    timed_out: bool = False,
    task: str | None = None,
    base_url: str = "",
) -> None:
    entries = data.setdefault("entries", {})
    if not isinstance(entries, dict):
        data["entries"] = {}
        entries = data["entries"]

    key = _entry_key(provider, model, task=task, base_url=base_url)
    entry = entries.get(key)
    now = time.time()
    if not isinstance(entry, dict):
        entry = {
            "provider": _normalize_provider(provider),
            "model": _normalize_model(model),
            "base_url": _normalize_base_url(base_url),
            "task": _normalize_task(task),
            "ewma_latency_s": float(latency_s),
            "samples": 1,
            "success_count": 1 if success else 0,
            "failure_count": 0 if success else 1,
            "timeout_count": 1 if timed_out else 0,
            "last_latency_s": float(latency_s),
            "last_success": bool(success),
            "last_timed_out": bool(timed_out),
            "last_updated_at": now,
        }
        entries[key] = entry
        return

    prev = _safe_float(entry.get("ewma_latency_s"))
    if prev is None:
        ewma = float(latency_s)
    else:
        ewma = (_LATENCY_ALPHA * float(latency_s)) + ((1.0 - _LATENCY_ALPHA) * prev)

    entry["provider"] = _normalize_provider(provider)
    entry["model"] = _normalize_model(model)
    entry["base_url"] = _normalize_base_url(base_url)
    entry["task"] = _normalize_task(task)
    entry["ewma_latency_s"] = float(ewma)
    entry["samples"] = int(entry.get("samples") or 0) + 1
    entry["success_count"] = int(entry.get("success_count") or 0) + (1 if success else 0)
    entry["failure_count"] = int(entry.get("failure_count") or 0) + (0 if success else 1)
    entry["timeout_count"] = int(entry.get("timeout_count") or 0) + (1 if timed_out else 0)
    entry["last_latency_s"] = float(latency_s)
    entry["last_success"] = bool(success)
    entry["last_timed_out"] = bool(timed_out)
    entry["last_updated_at"] = now


def record_model_outcome(
    provider: str,
    model: str,
    latency_s: float,
    *,
    success: bool,
    timed_out: bool = False,
    task: str | None = None,
    base_url: str = "",
    also_default: bool = True,
) -> None:
    """Record one model attempt outcome.

    ``task`` is optional. When provided, we also store a global
    ``__default__`` row so generic chain ordering can benefit from the same
    history without requiring a task-specific lookup.
    """
    latency = _safe_float(latency_s)
    if latency is None:
        return
    provider = _normalize_provider(provider)
    model = _normalize_model(model)
    if not provider or not model:
        return

    with _LATENCY_LOCK:
        data = _load_store()
        _update_entry(
            data,
            provider=provider,
            model=model,
            latency_s=latency,
            success=success,
            timed_out=timed_out,
            task=task,
            base_url=base_url,
        )
        if also_default and _normalize_task(task) != "__default__":
            _update_entry(
                data,
                provider=provider,
                model=model,
                latency_s=latency,
                success=success,
                timed_out=timed_out,
                task=None,
                base_url=base_url,
            )
        _write_store(data)


def record_model_latency(
    provider: str,
    model: str,
    latency_s: float,
    *,
    task: str | None = None,
    base_url: str = "",
    also_default: bool = True,
) -> None:
    """Backward-compatible wrapper for successful outcomes."""
    record_model_outcome(
        provider,
        model,
        latency_s,
        success=True,
        task=task,
        base_url=base_url,
        also_default=also_default,
    )


def get_model_latency_entry(
    provider: str,
    model: str,
    *,
    task: str | None = None,
    base_url: str = "",
) -> dict[str, Any] | None:
    """Return the best-known latency row for a provider/model pair.

    Task-specific history wins over the global ``__default__`` row.
    """
    provider = _normalize_provider(provider)
    model = _normalize_model(model)
    if not provider or not model:
        return None

    data = _load_store()
    entries = data.get("entries")
    if not isinstance(entries, dict):
        return None

    for candidate_task in (_normalize_task(task), "__default__"):
        key = _entry_key(provider, model, task=candidate_task, base_url=base_url)
        entry = entries.get(key)
        if isinstance(entry, dict):
            return entry
    return None


def _success_rate(entry: Mapping[str, Any] | None) -> float | None:
    if not isinstance(entry, Mapping):
        return None
    samples = int(entry.get("samples") or 0)
    if samples <= 0:
        return None
    success_count = int(entry.get("success_count") or 0)
    return max(0.0, min(1.0, success_count / samples))


def model_latency_priority(
    provider: str,
    model: str,
    *,
    task: str | None = None,
    base_url: str = "",
) -> tuple[bool, float, float, int]:
    """Return a sortable priority tuple.

    Sort order:
      1. known history before no-history
      2. higher success rate first
      3. lower EWMA latency first
      4. more samples first
    """
    entry = get_model_latency_entry(provider, model, task=task, base_url=base_url)
    if not isinstance(entry, dict):
        return (True, 0.0, float("inf"), 0)
    rate = _success_rate(entry)
    latency = _safe_float(entry.get("ewma_latency_s"))
    samples = int(entry.get("samples") or 0)
    return (
        False,
        -(rate if rate is not None else 0.0),
        float(latency if latency is not None else float("inf")),
        -samples,
    )


def sort_candidates_by_latency(
    candidates: Sequence[Mapping[str, Any]],
    *,
    task: str | None = None,
) -> list[dict[str, Any]]:
    """Return candidate dicts ordered by historical latency, then input order.

    Candidates with known history sort ahead of candidates with no history.
    Within history, higher success rate wins first; then lower moving-average
    latency; then larger sample size; then original order.
    """
    ranked: list[tuple[bool, float, float, int, int, dict[str, Any]]] = []
    for idx, candidate in enumerate(candidates):
        provider = _normalize_provider(candidate.get("provider"))
        model = _normalize_model(candidate.get("model"))
        base_url = _normalize_base_url(candidate.get("base_url"))
        entry = get_model_latency_entry(
            provider,
            model,
            task=task,
            base_url=base_url,
        )
        has_history = isinstance(entry, dict)
        rate = _success_rate(entry) if has_history else None
        ewma = _safe_float(entry.get("ewma_latency_s")) if isinstance(entry, dict) else None
        samples = int(entry.get("samples") or 0) if isinstance(entry, dict) else 0
        ranked.append(
            (
                not has_history,
                -(rate if rate is not None else 0.0),
                float(ewma if ewma is not None else float("inf")),
                -samples,
                idx,
                dict(candidate),
            )
        )

    ranked.sort(key=lambda row: (row[0], row[1], row[2], row[3], row[4]))
    return [row[5] for row in ranked]
