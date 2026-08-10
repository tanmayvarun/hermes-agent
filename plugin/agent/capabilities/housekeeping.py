"""Housekeeping capability family — relieve host pressure, recover blocked apps.

These are ordinary catalog capabilities chosen under ``act`` (optionally named by
the meta consultant). They are not a separate meta-action.

Flow under storage pressure: relieve once → brain relaunches (recover) → next
perceive decides if the app is still blocked → relieve may be named again.
Loop max_iterations bounds the cycle; no separate relieve-iter counter.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

HOUSEKEEPING_CAPABILITIES = frozenset(
    {
        "relieve_host_storage",
        "recover_blocked_app",
        "dismiss_transient",
    }
)

# Verbs the meta consultant may name to short-circuit goal decision under blockers.
META_HOUSEKEEPING_VERBS = frozenset(
    {
        "relieve_host_storage",
        "recover_blocked_app",
    }
)

_EXIT_CTA_LABELS = (
    "exit whatsapp",
    "exit",
    "quit",
    "close",
    "ok",
)


def is_housekeeping_capability(name: str) -> bool:
    key = str(name or "").strip().lower().replace("-", "_")
    return key in HOUSEKEEPING_CAPABILITIES


def is_meta_housekeeping_verb(name: str) -> bool:
    key = str(name or "").strip().lower().replace("-", "_")
    return key in META_HOUSEKEEPING_VERBS


def parse_required_free_bytes_from_texts(*parts: Any) -> Optional[int]:
    """Parse an app-quoted free-space ask (e.g. 'free up at least 11.88 MB')."""
    blob_parts: List[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, (list, tuple, set)):
            blob_parts.extend(str(x) for x in part if str(x).strip())
        else:
            text = str(part).strip()
            if text:
                blob_parts.append(text)
    text = " ".join(blob_parts)
    if not text.strip():
        return None
    try:
        from plugin.agent.runtime.recovery import _load_disk_cleanup_library

        lib = _load_disk_cleanup_library()
        if hasattr(lib, "parse_required_free_bytes"):
            return lib.parse_required_free_bytes(text=text)
    except Exception:
        return None
    return None


def blockers_from_features(features: Any = None, view: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Compact blocker signals for the meta packet (no pixels)."""
    extras: Dict[str, Any] = {}
    if features is not None:
        if hasattr(features, "extras") and isinstance(features.extras, dict):
            extras = dict(features.extras)
        elif isinstance(features, dict):
            extras = dict(features.get("extras") or features)
    view = view if isinstance(view, dict) else {}
    warnings = list(extras.get("system_warnings") or view.get("system_warnings") or [])
    storage_pressure = bool(
        extras.get("storage_pressure")
        or warnings
        or view.get("storage_pressure")
    )
    dialogs = [str(d) for d in (extras.get("dialogs") or view.get("dialogs") or []) if str(d).strip()]
    exit_cta = any(
        any(tok in str(d).strip().lower() for tok in _EXIT_CTA_LABELS)
        for d in dialogs
    )
    # Also detect Exit labels that may only appear as entity text in warnings.
    warning_blob = " ".join(str(w).lower() for w in warnings)
    if "exit" in warning_blob:
        exit_cta = True
    return {
        "storage_pressure": storage_pressure,
        "system_warnings": [str(w)[:120] for w in warnings[:4]],
        "blocking_overlay": bool(extras.get("blocking_overlay") or view.get("blocking_overlay")),
        "exit_cta_visible": exit_cta,
        "surface": str(extras.get("active_surface") or view.get("screen") or "")[:40],
    }


def attach_housekeeping_context(
    blockers: Optional[Dict[str, Any]] = None,
    *,
    last_action: str = "",
    observation_texts: Sequence[str] = (),
) -> Dict[str, Any]:
    """Add last housekeeping verb + parsed reclaim ask for the meta packet."""
    b = dict(blockers or {})
    last = str(last_action or "").strip().lower().replace("-", "_")
    if last in META_HOUSEKEEPING_VERBS:
        b["last_housekeeping"] = last
    required = parse_required_free_bytes_from_texts(
        observation_texts,
        b.get("system_warnings") or [],
    )
    if required is not None:
        b["required_free_bytes"] = int(required)
    return b


def admissible_housekeeping_capabilities(
    blockers: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """Shortlist of housekeeping verbs admissible given current blockers."""
    b = dict(blockers or {})
    out: List[Dict[str, str]] = []
    if b.get("storage_pressure") or b.get("system_warnings"):
        out.append(
            {
                "name": "relieve_host_storage",
                "why": (
                    "host/app reports insufficient free space; one staged relieve "
                    "pass, then relaunch so perception can re-check the blocker"
                ),
            }
        )
        out.append(
            {
                "name": "recover_blocked_app",
                "why": (
                    "exit/relaunch the storage-blocked app so a fresh look can tell "
                    "whether the reclaim was enough"
                ),
            }
        )
    elif b.get("blocking_overlay") or b.get("exit_cta_visible"):
        out.append(
            {
                "name": "recover_blocked_app",
                "why": "blocking chrome prevents the task UI; recover then resume the goal",
            }
        )
        out.append(
            {
                "name": "dismiss_transient",
                "why": "clear reversible overlay/menu that is not the task",
            }
        )
    return out


def warning_text_blob(
    *,
    evidence: Sequence[str] = (),
    blockers: Optional[Dict[str, Any]] = None,
) -> str:
    parts = [str(x) for x in evidence if str(x).strip()]
    if blockers:
        parts.extend(str(w) for w in (blockers.get("system_warnings") or []) if str(w).strip())
    return " ".join(parts)
