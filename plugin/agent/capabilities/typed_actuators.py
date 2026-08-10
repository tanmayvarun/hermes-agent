"""Typed actuator schemas — LLM selects registered forms, not free-text motors.

Keyboard chords must never collapse into pointer clicks.

Free-text parsers live in ``legacy_action_adapter`` (migration only).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class PointerClick:
    target_binding: str = ""
    label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": "pointer_click", "target_binding": self.target_binding, "label": self.label}


@dataclass(frozen=True)
class PointerContextClick:
    target_binding: str = ""
    label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "pointer_context_click",
            "target_binding": self.target_binding,
            "label": self.label,
        }


@dataclass(frozen=True)
class PointerHover:
    target_binding: str = ""
    label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": "pointer_hover", "target_binding": self.target_binding, "label": self.label}


@dataclass(frozen=True)
class KeyboardChord:
    keys: Tuple[str, ...] = ()
    target_scope: str = "active_app"
    provenance: str = "observed"  # observed | model_prior | hypothesized_method

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "keyboard_chord",
            "keys": list(self.keys),
            "target_scope": self.target_scope,
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class TextEntry:
    text: str = ""
    field_role: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": "text_entry", "text": self.text, "field_role": self.field_role}


# Backward-compatible re-exports — prefer legacy_action_adapter for new code.
def looks_like_keyboard_chord(label: str) -> bool:
    from plugin.agent.capabilities.legacy_action_adapter import (
        looks_like_keyboard_chord as _looks,
    )

    return _looks(label)


def parse_keyboard_chord(label: str, *, provenance: str = "model_prior"):
    from plugin.agent.capabilities.legacy_action_adapter import (
        parse_keyboard_chord as _parse,
    )

    return _parse(label, provenance=provenance)


def realize_keyboard_chord(app: str, chord: KeyboardChord) -> Tuple[bool, str]:
    """Execute a typed keyboard chord via System Events (not a pointer click)."""
    mods = [k for k in chord.keys if k in {"command", "control", "option", "shift"}]
    mains = [k for k in chord.keys if k not in {"command", "control", "option", "shift"}]
    if not mains:
        return False, "keyboard_chord missing main key"
    key = mains[-1]
    using = ""
    if mods:
        # AppleScript: keystroke "f" using {command down, shift down}
        parts = [f"{m} down" for m in mods]
        using = " using {" + ", ".join(parts) + "}"
    esc_key = key.replace('"', '\\"')
    script = (
        f'tell application "System Events" to keystroke "{esc_key}"{using}'
    )
    try:
        import subprocess

        from plugin.executor.ax_action import _activate_app

        _activate_app(app)
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode != 0:
            return False, f"keyboard_chord failed: {(proc.stderr or proc.stdout or '')[:160]}"
        return True, f"keyboard_chord keys={list(chord.keys)} scope={chord.target_scope}"
    except Exception as exc:
        return False, f"keyboard_chord error: {exc}"
