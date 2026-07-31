"""Launch apps without Accessibility or AppleScript — Launch Services only."""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class LaunchResult:
    ok: bool
    app: str
    message: str
    command: List[str]


def launch_app(app: str, *, activate: bool = True) -> LaunchResult:
    """Launch (and optionally focus) an app via ``open -a``.

    No Accessibility, Screen Recording, or Automation permission required.
    Avoids AppleScript ``tell application … to activate``.
    """
    name = (app or "").strip()
    if not name:
        return LaunchResult(ok=False, app="", message="app name required", command=[])

    if shutil.which("open") is None:
        return LaunchResult(
            ok=False,
            app=name,
            message="'open' not found (macOS Launch Services required)",
            command=[],
        )

    candidates = [
        ["open", "-a", name],
        ["open", "-gj", "-a", name],
        ["open", "-na", name],
        ["open", f"/Applications/{name}.app"],
    ]
    last_err = ""
    for index, cmd in enumerate(candidates):
        for attempt in range(2):
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            except Exception as e:
                last_err = str(e)
                break
            if proc.returncode == 0:
                _ = activate  # open already activates; kept for API clarity
                return LaunchResult(ok=True, app=name, message=f"launched via {' '.join(cmd)}", command=cmd)
            last_err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
            if attempt == 0 and index < len(candidates) - 1:
                time.sleep(0.8)
        # Try the next launch form after a short settle.
        time.sleep(0.4)

    return LaunchResult(ok=False, app=name, message=last_err or "failed to launch", command=candidates[-1])


def permissions_checklist() -> str:
    """Human-readable permission layers (see PERMISSIONS.md)."""
    return """\
Plugin macOS permission layers
==============================
LIVE REQUIREMENT: run from Terminal.app or iTerm (NOT Cursor agent).

Launch / activate app ........ NONE  (plugin launch → open -a)
Read AX tree (world model) ... Accessibility  → enable Terminal / iTerm
Click / type / scroll ........ Accessibility  (Ghost or PyObjC AX)
Screenshots .................. Screen Recording  (optional)
AppleScript / Apple Events ... NOT USED in POC

Setup:
  System Settings → Privacy & Security → Accessibility → Terminal (or iTerm) ON
  Then in that terminal:
    cd hermes-agent && source .venv/bin/activate && export PYTHONPATH=.
    python -m plugin call-pallavi --live --hangup --contact Pallavi

See plugin/PERMISSIONS.md
"""
