"""Recover an app blocked by storage/system chrome so the goal UI is usable again.

Typical path: click an Exit/Close CTA when grounded, then relaunch/activate the app.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence, Tuple

from plugin.agent.capabilities.base import CapabilityOutcome
from plugin.agent.capabilities.pointer_runtime import MacPointerRuntime

logger = logging.getLogger(__name__)

_EXIT_LABELS = (
    "exit whatsapp",
    "quit whatsapp",
    "exit",
    "quit",
    "close",
)


def _norm(label: str) -> str:
    return " ".join(str(label or "").strip().lower().split())


def find_exit_cta(
    world: Any = None,
    *,
    dialogs: Optional[Sequence[str]] = None,
) -> Tuple[str, Optional[Tuple[float, float]], Optional[Tuple[float, float, float, float]]]:
    """Return (label, point, bounds) for a visible exit/close control if any."""
    # Prefer world entities with geometry.
    entities = getattr(world, "entities", None) or {}
    best = ("", None, None)
    best_score = -1
    for ent in entities.values() if isinstance(entities, dict) else []:
        if not getattr(ent, "visible", True):
            continue
        label = _norm(getattr(ent, "label", "") or "")
        if not label:
            continue
        score = -1
        for i, tok in enumerate(_EXIT_LABELS):
            if label == tok or tok in label:
                score = len(_EXIT_LABELS) - i
                break
        if score < 0:
            continue
        bounds = getattr(ent, "bounds", None)
        point = None
        if bounds and len(bounds) >= 4:
            x, y, w, h = [float(v) for v in bounds[:4]]
            point = (x + w / 2.0, y + h / 2.0)
            bounds_t = (x, y, w, h)
        else:
            bounds_t = None
        if score > best_score and (point is not None or bounds_t is not None):
            best_score = score
            best = (getattr(ent, "label", "") or label, point, bounds_t)
    if best[0]:
        return best

    for raw in dialogs or []:
        low = _norm(raw)
        if any(tok in low for tok in _EXIT_LABELS):
            return (str(raw), None, None)
    return ("", None, None)


def recover_blocked_app(
    *,
    app: str,
    world: Any = None,
    dialogs: Optional[Sequence[str]] = None,
    runtime: Any = None,
) -> CapabilityOutcome:
    app_name = str(app or "WhatsApp").strip() or "WhatsApp"
    label, point, bounds = find_exit_cta(world, dialogs=dialogs)
    clicked = False
    click_message = "no exit CTA geometry"
    pointer = runtime or MacPointerRuntime()

    if label and (point is not None or bounds is not None):
        try:
            pointer.activate(app_name)
            ok_click, msg = pointer.click(app_name, label, bounds=bounds)
            clicked = bool(ok_click)
            click_message = msg or f"clicked exit CTA {label!r}"
        except Exception as exc:
            logger.warning("recover_blocked_app click failed: %s", exc)
            click_message = f"exit click failed: {exc}"

    launched = False
    launch_message = ""
    try:
        from plugin.perception.macos.launch import launch_app
        from plugin.executor.ax_action import _activate_app

        result = launch_app(app_name, activate=True)
        launched = bool(getattr(result, "ok", False) or result is True)
        if not launched:
            _activate_app(app_name)
            launched = True
        launch_message = f"relaunched/activated {app_name}"
    except Exception as exc:
        logger.warning("recover_blocked_app launch failed: %s", exc)
        launch_message = f"launch failed: {exc}"
        try:
            from plugin.executor.ax_action import _activate_app

            _activate_app(app_name)
            launched = True
            launch_message = f"activated {app_name} after launch error"
        except Exception as exc2:
            launch_message = f"activate failed: {exc2}"

    ok = bool(clicked or launched)
    return CapabilityOutcome(
        ok=ok,
        capability="recover_blocked_app",
        realization="exit_cta_then_launch",
        message=f"{click_message}; {launch_message}",
        evidence={
            "substrate": "transient_chrome",
            "app": app_name,
            "exit_label": label,
            "clicked_exit": clicked,
            "launched": launched,
            "point": list(point) if point else None,
            "bounds": list(bounds) if bounds else None,
        },
    )
