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
    allow_hypothesized_chord: bool = False,
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

    # Typed actuators: keyboard chords must never become named_click.
    from plugin.agent.capabilities.typed_actuators import (
        looks_like_keyboard_chord,
        parse_keyboard_chord,
        realize_keyboard_chord,
    )

    if looks_like_keyboard_chord(name):
        chord = parse_keyboard_chord(name, provenance="model_prior")
        if chord is None:
            return CapabilityOutcome(
                ok=False,
                capability="invoke_affordance",
                realization="refused_untyped_chord",
                message=(
                    f"{name!r} looks like a keyboard chord but could not be "
                    "parsed; refuse click fallback"
                ),
                evidence={
                    "refused": name,
                    "reason": "keyboard_chord_unparsed",
                    "hypothesized_method": True,
                    "provenance": "model_prior",
                },
            )
        if not allow_hypothesized_chord and chord.provenance == "model_prior":
            return CapabilityOutcome(
                ok=False,
                capability="invoke_affordance",
                realization="hypothesized_method",
                message=(
                    f"{name!r} is a model-prior keyboard chord, not a grounded "
                    "affordance — refuse click realization"
                ),
                evidence={
                    "refused": name,
                    "reason": "model_prior_chord",
                    "hypothesized_method": True,
                    "provenance": "model_prior",
                    "typed": chord.to_dict(),
                },
            )
        ok, message = realize_keyboard_chord(app, chord)
        return CapabilityOutcome(
            ok=ok,
            capability="invoke_affordance",
            realization="keyboard_chord",
            message=message,
            evidence={
                "substrate": "keyboard",
                "affordance": name,
                "typed": chord.to_dict(),
            },
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
