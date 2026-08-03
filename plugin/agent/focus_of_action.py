"""The perceptor's awareness of *where the action is*, and whether it may act.

The perceptor is the agent's eyes; the brain equates to a human operator. Two
faculties live here, both about staying anchored to the task instead of merely
narrating whatever pixels are on screen:

* Foreground awareness (:func:`foreground_app_name`,
  :func:`foreground_matches_task`). A human operator interrupted mid-task — a
  call comes in, someone switches to YouTube — does not keep clicking blindly;
  they wait until they are back in the right window. These helpers give the brain
  that awareness so it can hold, persist its goal, and resume, rather than act on
  the wrong surface (where keystrokes would land in the foreign app anyway).

* Focus-of-action hierarchy (:class:`FocusOfAction`, added in a later pass): the
  structured ``app → layer → region → focus object`` reading with object
  permanence, plus a human-readable audit summary.
"""

from __future__ import annotations

import os
import unicodedata
from typing import Any, Optional


def foreground_gate_enabled() -> bool:
    """Whether the brain should hold while a foreign app is frontmost.

    Opt-in, like the other live faculties (unified cognition, layered
    perception, meta-perception): the live launcher turns it on, while offline
    tests that drive the control loop headlessly (whose frontmost app is the
    test runner, never the task app) leave it off so the gate never engages.
    """
    raw = os.getenv("HERMES_FOREGROUND_GATE", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def normalize_app_name(name: Any) -> str:
    """App name with invisible Unicode format marks dropped, lowercased.

    macOS reports some apps with leading bidi/format marks — WhatsApp appears as
    ``"\u200eWhatsApp"`` — so raw string equality silently misses them. Dropping
    Unicode ``Cf`` (format) characters and collapsing whitespace makes the
    comparison robust.
    """
    text = str(name or "")
    cleaned = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return " ".join(cleaned.strip().lower().split())


def task_anchor_app(goal: Any) -> str:
    """The application the task is anchored to (its home surface)."""
    return str(getattr(goal, "app", "") or "").strip()


def foreground_app_name() -> str:
    """Name of the frontmost application, or "" when it cannot be determined.

    Uses ``NSWorkspace`` (no special permission). Returning "" on any failure
    lets the caller fail open — treat the task app as in front — so a missing
    signal never wedges the agent in a permanent wait.
    """
    try:
        from AppKit import NSWorkspace  # type: ignore
    except Exception:
        return ""
    try:
        workspace = NSWorkspace.sharedWorkspace()
        app = workspace.frontmostApplication() if workspace is not None else None
        return str(app.localizedName() or "") if app is not None else ""
    except Exception:
        return ""


def foreground_matches_task(goal: Any, *, foreground: Optional[str] = None) -> bool:
    """Whether the foreground app is the task's app.

    Fails open: an unknown task app or an undeterminable foreground both count as
    a match, so the persistence gate only *holds* on positive evidence that a
    foreign app is in front — never on missing information.
    """
    task = normalize_app_name(task_anchor_app(goal))
    if not task:
        return True
    fg = normalize_app_name(foreground if foreground is not None else foreground_app_name())
    if not fg:
        return True
    return task in fg or fg in task
