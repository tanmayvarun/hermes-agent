"""Relieve host storage pressure with staged, empathetic cleanup.

One pass: free what low-importance stages can, then return. Whether the app
is still space-blocked is decided by the next perceive after relaunch — not
inside this capability.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from plugin.agent.capabilities.base import CapabilityOutcome
from plugin.agent.capabilities.housekeeping import (
    parse_required_free_bytes_from_texts,
    warning_text_blob,
)


def relieve_host_storage(
    *,
    app: str = "",
    view: Optional[Dict[str, Any]] = None,
    features: Optional[Dict[str, Any]] = None,
    observation_texts: Optional[Sequence[str]] = None,
    evidence: Optional[Sequence[str]] = None,
    reason: str = "storage pressure",
) -> CapabilityOutcome:
    # Lazy import: recovery pulls perception_cycle → unified_cognition → capabilities.
    from plugin.agent.runtime.recovery import (
        detect_storage_pressure,
        perform_storage_cleanup,
    )

    obs = list(observation_texts or [])
    ev = list(evidence or [])
    if not ev:
        ev = detect_storage_pressure(
            view=view,
            features=features,
            observation_texts=obs,
            execution_message=reason,
        )
    if not ev and not (isinstance(view, dict) and view.get("system_warnings")):
        # Still allow an explicit act when meta named this verb under blockers.
        ev = ["meta:relieve_host_storage"]

    warn_parts: List[str] = list(obs)
    if isinstance(view, dict):
        warn_parts.extend(str(w) for w in (view.get("system_warnings") or []) if str(w).strip())
        warn_parts.extend(str(d) for d in (view.get("dialogs") or []) if str(d).strip())
    text = warning_text_blob(evidence=ev + warn_parts)
    required = parse_required_free_bytes_from_texts(text, obs)

    result = perform_storage_cleanup(
        reason=reason or "relieve_host_storage",
        evidence=ev,
        staged=True,
        headroom_text=text,
    )
    disk = dict(result.disk_cleanup or {})
    headroom_met = bool(disk.get("headroom_met"))
    free_after = int(disk.get("free_after", 0) or 0)
    free_before = int(disk.get("free_before", 0) or 0)
    freed = int(disk.get("freed", 0) or 0)
    # Execution succeeded if cleanup ran; IntentionFrame judges whether the
    # child's required_effect holds from world evidence (not this flag alone).
    execution_ok = True
    return CapabilityOutcome(
        ok=execution_ok,
        capability="relieve_host_storage",
        realization="staged_disk_cleanup",
        message=(
            f"relieved storage; freed={freed} "
            f"stages={len(disk.get('stages') or [])} "
            f"headroom_met={headroom_met} stop={disk.get('stop_reason')} "
            f"required_free={required}"
        ),
        evidence={
            "substrate": "task_evidence",
            "app": app,
            "execution_ok": execution_ok,
            "observations": {
                "free_before": free_before,
                "free_after": free_after,
                "bytes_reclaimed": freed,
            },
            "freed": freed,
            "stages": list(disk.get("stages") or []),
            "headroom_met": headroom_met,
            "stop_reason": str(disk.get("stop_reason") or ""),
            "free_after": free_after,
            "free_before": free_before,
            "target_free_bytes": int(disk.get("target_free_bytes", 0) or 0),
            "required_free_bytes": int(required) if required is not None else None,
            "environments_cleaned": int(result.environments_cleaned or 0),
            "analysis": dict(result.analysis or {}),
            # Convenience stamp for world merge — judge still owns success.
            "available_storage_bytes": free_after,
        },
    )
