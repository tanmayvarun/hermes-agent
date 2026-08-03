"""Commit an irreversible action — always a gated primitive.

    commit_irreversible("Send") -> click Send

Never bundled inside another capability. The allowlist is narrow on purpose:
only labels that actually commit a side effect. Everything else stays on
invoke_affordance or motor click.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional, Set

from plugin.agent.capabilities.base import CapabilityOutcome
from plugin.agent.capabilities.open_entity import _point_bounds
from plugin.agent.capabilities.pointer_runtime import PointerRuntime

logger = logging.getLogger(__name__)

_COMMIT_LABELS: Set[str] = {
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
}


def _normalize_label(label: str) -> str:
    return re.sub(r"\s+", " ", (label or "").strip().lower())


def is_commit_label(label: str) -> bool:
    return _normalize_label(label) in _COMMIT_LABELS


def commit_irreversible(
    app: str,
    label: str,
    runtime: PointerRuntime,
    *,
    bounds: Optional[tuple] = None,
    point: Any = None,
) -> CapabilityOutcome:
    name = (label or "").strip()
    if not name:
        return CapabilityOutcome(
            ok=False,
            capability="commit_irreversible",
            message="commit_irreversible requires the commit label in text",
        )
    if not is_commit_label(name):
        return CapabilityOutcome(
            ok=False,
            capability="commit_irreversible",
            message=(
                f"{name!r} is not a known irreversible commit; "
                "use invoke_affordance for reversible controls"
            ),
            evidence={"refused": name, "reason": "not_a_commit"},
        )

    if bounds is None:
        bounds = _point_bounds(point)

    try:
        runtime.activate(app)
        ok, message = runtime.click(app, name, bounds=bounds)
    except Exception as exc:
        logger.warning("commit_irreversible failed: %s", exc)
        return CapabilityOutcome(
            ok=False,
            capability="commit_irreversible",
            realization="gated_click",
            message=f"commit failed: {exc}",
        )

    return CapabilityOutcome(
        ok=ok,
        capability="commit_irreversible",
        realization="gated_click",
        message=message or f"committed {name!r}",
        evidence={
            "substrate": "gated_target",
            "label": name,
            "irreversible": True,
            "had_bounds": bounds is not None,
        },
    )
