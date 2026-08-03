"""Activate a named *reversible* affordance.

    invoke_affordance("Forward") -> click that control

The substrate is an affordance set already on screen (context menu, toolbar,
picker). The model names which affordance; the runtime clicks it.

Irreversible names (Send, Delete, …) are refused here and must go through
commit_irreversible. That is the gate: bundling Send into "invoke" would hide
it from the irreversible path.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional, Set

from plugin.agent.capabilities.base import CapabilityOutcome
from plugin.agent.capabilities.open_entity import _point_bounds
from plugin.agent.capabilities.pointer_runtime import PointerRuntime

logger = logging.getLogger(__name__)

# Labels that must never be taken through the reversible invoke path.
_IRREVERSIBLE_LABELS: Set[str] = {
    "send",
    "send message",
    "delete",
    "delete chat",
    "delete message",
    "remove",
    "confirm",
    "ok",
    "yes",
    "empty trash",
    "empty chat",
    "leave",
    "leave group",
    "block",
    "block contact",
    "report",
}


def _normalize_label(label: str) -> str:
    return re.sub(r"\s+", " ", (label or "").strip().lower())


def is_irreversible_affordance(label: str) -> bool:
    return _normalize_label(label) in _IRREVERSIBLE_LABELS


def invoke_affordance(
    app: str,
    affordance: str,
    runtime: PointerRuntime,
    *,
    bounds: Optional[tuple] = None,
    point: Any = None,
) -> CapabilityOutcome:
    name = (affordance or "").strip()
    if not name:
        return CapabilityOutcome(
            ok=False,
            capability="invoke_affordance",
            message="invoke_affordance requires the affordance name in text",
        )
    if is_irreversible_affordance(name):
        return CapabilityOutcome(
            ok=False,
            capability="invoke_affordance",
            message=(
                f"{name!r} is irreversible; use commit_irreversible so the "
                "risk gate can see it"
            ),
            evidence={"refused": name, "reason": "irreversible"},
        )

    if bounds is None:
        bounds = _point_bounds(point)

    try:
        runtime.activate(app)
        ok, message = runtime.click(app, name, bounds=bounds)
    except Exception as exc:
        logger.warning("invoke_affordance failed: %s", exc)
        return CapabilityOutcome(
            ok=False,
            capability="invoke_affordance",
            realization="named_click",
            message=f"invoke failed: {exc}",
        )

    return CapabilityOutcome(
        ok=ok,
        capability="invoke_affordance",
        realization="named_click",
        message=message or f"invoked {name!r}",
        evidence={
            "substrate": "affordance_set",
            "affordance": name,
            "had_bounds": bounds is not None,
        },
    )
