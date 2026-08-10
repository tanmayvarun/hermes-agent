"""Typed actuator schemas — LLM selects registered forms, not free-text motors.

Keyboard chords must never collapse into pointer clicks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


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


_CHORD_RE = re.compile(
    r"^(?:press[_ ]?)?(?:(?:cmd|command|ctrl|control|alt|option|shift)[_+]?)+\w+$",
    re.I,
)
_KEY_ALIASES = {
    "cmd": "command",
    "command": "command",
    "ctrl": "control",
    "control": "control",
    "alt": "option",
    "option": "option",
    "shift": "shift",
}


def looks_like_keyboard_chord(label: str) -> bool:
    text = re.sub(r"\s+", "_", (label or "").strip().lower())
    if not text:
        return False
    if text.startswith("press_") and any(
        k in text for k in ("cmd", "command", "ctrl", "shift", "alt", "option")
    ):
        return True
    return bool(_CHORD_RE.match(text.replace("+", "_")))


def parse_keyboard_chord(
    label: str, *, provenance: str = "model_prior"
) -> Optional[KeyboardChord]:
    """Parse free-text like press_cmd_shift_f into a typed KeyboardChord."""
    if not looks_like_keyboard_chord(label):
        return None
    text = re.sub(r"^press[_ ]?", "", (label or "").strip(), flags=re.I)
    text = text.replace("+", "_").replace("-", "_").replace(" ", "_")
    parts = [p for p in text.split("_") if p]
    keys: List[str] = []
    for p in parts:
        low = p.lower()
        if low in _KEY_ALIASES:
            keys.append(_KEY_ALIASES[low])
        elif len(low) == 1 or low in {"enter", "return", "escape", "tab", "space"}:
            keys.append(low)
        else:
            # Multi-letter leftover may be the key char (e.g. "f").
            if low:
                keys.append(low[0] if len(low) > 1 and low.endswith("key") else low)
    # Deduplicate modifiers while preserving order.
    seen = set()
    ordered: List[str] = []
    for k in keys:
        if k in seen and k in {"command", "control", "option", "shift"}:
            continue
        seen.add(k)
        ordered.append(k)
    if len(ordered) < 2:
        return None
    return KeyboardChord(
        keys=tuple(ordered),
        target_scope="active_app",
        provenance=provenance,
    )


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
