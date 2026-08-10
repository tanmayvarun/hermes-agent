"""Legacy free-text → typed capability adapters (marked for deletion).

Production path: LLM emits registered capability_id + validated args.
These parsers exist only at the ingestion boundary for older string actions.
"""

from __future__ import annotations

import re
from typing import List, Optional

from plugin.agent.capabilities.typed_actuators import KeyboardChord

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
    """Legacy heuristic — do not use for new capability selection."""
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
    """Parse free-text like press_cmd_shift_f into a typed KeyboardChord.

    DEPRECATED for production selection. Prefer capability_id=keyboard_chord
    with args.keys. Kept for migration of string affordance labels.
    """
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
            if low:
                keys.append(low[0] if len(low) > 1 and low.endswith("key") else low)
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
