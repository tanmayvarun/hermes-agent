"""Clear transient chrome that is not the task.

The substrate is transient chrome -- a menu, dialog, or overlay perception
decided is in the way. Dismissal is general: send the host's dismiss chord
(Escape on almost every macOS app). Whether clearing was the right move is
judgment and stays with the model.

    dismiss_transient() -> clear the overlay / menu

Safe to composite: Escape is reversible. Never used to confirm or send.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Protocol, runtime_checkable

from plugin.agent.capabilities.base import CapabilityOutcome, TransientChrome
from plugin.agent.capabilities.locate_content import KeyChord

logger = logging.getLogger(__name__)

# Escape is the universal macOS dismiss. Overlays may declare another chord.
MACOS_DISMISS = KeyChord(code=53)


@runtime_checkable
class DismissRuntime(Protocol):
    def activate(self, app: str) -> None: ...

    def key(self, chord: KeyChord) -> None: ...


@dataclass
class MacDismissRuntime:
    """macOS Escape adapter for dismiss_transient."""

    def activate(self, app: str) -> None:
        from plugin.executor.ax_action import _activate_app, _is_frontmost

        # Do not activate if already frontmost -- activating under an open
        # native menu can reorder windows; Escape still reaches a frontmost app.
        if not _is_frontmost(app):
            _activate_app(app)

    def key(self, chord: KeyChord) -> None:
        from plugin.executor.ax_action import _keydown

        _keydown(chord.code, cmd=chord.cmd)


def dismiss_chord_for(overlay: Any) -> KeyChord:
    declared = getattr(overlay, "dismiss_affordance", None)
    if isinstance(declared, KeyChord):
        return declared
    return MACOS_DISMISS


def dismiss_transient(
    chrome: TransientChrome,
    runtime: DismissRuntime,
    *,
    chord: Optional[KeyChord] = None,
) -> CapabilityOutcome:
    chord = chord or MACOS_DISMISS
    try:
        runtime.activate(chrome.app)
        runtime.key(chord)
    except Exception as exc:
        logger.warning("dismiss_transient failed: %s", exc)
        return CapabilityOutcome(
            ok=False,
            capability="dismiss_transient",
            realization="dismiss_chord",
            message=f"dismiss failed: {exc}",
        )

    return CapabilityOutcome(
        ok=True,
        capability="dismiss_transient",
        realization="dismiss_chord",
        message=f"sent dismiss ({chord.describe()})",
        evidence={
            "substrate": "transient_chrome",
            "chord": chord.describe(),
            "surface": chrome.surface,
        },
    )
