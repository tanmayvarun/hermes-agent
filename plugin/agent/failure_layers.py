"""Layered failure diagnosis — do not blame capabilities while grounding is uncertain.

Order:
  semantic target → binding → fresh grounding → transform → realization → effect → effect perception
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

# Beliefs that imply capability/platform failure — forbidden while grounding uncertain.
_CAPABILITY_FAILURE_BELIEFS: Set[str] = {
    "mouse_interaction_blocked",
    "context_menu_opaque",
    "selection_mode_inactive",
    "whatsapp_gestures_broken",
    "pointer_dead",
    "ui_unresponsive",
}


def grounding_uncertain(execution_state: Any, evidence: Optional[Dict[str, Any]] = None) -> bool:
    ev = evidence if isinstance(evidence, dict) else {}
    if str(getattr(execution_state, "attempt_validity", "") or "") == "inconclusive_grounding":
        return True
    if ev.get("geometry_mismatch") or ev.get("attempt_validity") == "inconclusive_grounding":
        return True
    dist = ev.get("intended_vs_landed_distance_px")
    try:
        if dist is not None and float(dist) >= 80.0:
            return True
    except (TypeError, ValueError):
        pass
    ga = ev.get("geometry_audit") if isinstance(ev.get("geometry_audit"), dict) else {}
    try:
        if ga.get("intended_vs_landed_px") is not None and float(ga["intended_vs_landed_px"]) >= 80.0:
            return True
    except (TypeError, ValueError):
        pass
    return False


def filter_capability_failure_beliefs(
    beliefs: Any,
    *,
    execution_state: Any = None,
    evidence: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Strip over-strong capability conclusions when lower layers are unresolved."""
    if not isinstance(beliefs, (list, tuple, set)):
        return []
    uncertain = grounding_uncertain(execution_state, evidence)
    out: List[str] = []
    for b in beliefs:
        key = str(b or "").strip().lower().replace(" ", "_")
        if uncertain and key in _CAPABILITY_FAILURE_BELIEFS:
            continue
        if b:
            out.append(str(b))
    return out


def diagnosis_layer(execution_state: Any, evidence: Optional[Dict[str, Any]] = None) -> str:
    """Return the deepest verified layer name; blame stops here."""
    if grounding_uncertain(execution_state, evidence):
        return "fresh_grounding"
    ev = evidence or {}
    if ev.get("actuator_error") or str(ev.get("status") or "") == "motor_fail":
        return "actuator_realization"
    if ev.get("effect_absent") or ev.get("geometry_mismatch"):
        return "world_effect"
    return "effect_perception"
