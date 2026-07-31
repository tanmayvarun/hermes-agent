"""WhatsApp entity semantic typing — narrow type set with confidence beliefs."""

from __future__ import annotations

import re
from typing import Tuple

from plugin.worldmodel.belief import Belief
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.entities.normalize import _clean_label
from plugin.worldmodel.model import WorldModel

# Narrow set from LLD
SEMANTIC_TYPES = (
    "contact",
    "group",
    "community",
    "search_box",
    "call_button",
    "message_list",
    "chrome",
    "unknown",
)

_PHONE_RE = re.compile(r"^\+?\d[\d\s\-]{6,}$")
_CHROME = {
    "search",
    "search or start new chat",
    "chats",
    "status",
    "calls",
    "settings",
    "new chat",
    "mute",
    "archive",
}


def infer_semantic_type(entity: Entity) -> Tuple[str, float]:
    """Heuristic type + confidence for a WhatsApp UI entity."""
    role = (entity.role or "").lower()
    et = (entity.entity_type or "").lower()
    lab = _clean_label(entity.label or "")
    low = lab.lower()
    desc = _clean_label(str((entity.attributes or {}).get("description") or ""))
    blob = f"{lab} {desc} {entity.semantic_role or ''}".lower()

    if et == "textfield" or "search" in role or low in {"search", "search or start new chat"}:
        return "search_box", 0.95
    if low in {"call", "voice call", "voice call", "audio call", "end call", "end"} or (
        "call" in low and et == "button" and len(low) < 24
    ):
        return "call_button", 0.92
    if low in _CHROME or et in {"toolbar", "window", "scroll"}:
        return "chrome", 0.8
    if "message" in low and "chat with" in blob:
        return "message_list", 0.7
    if et == "button" and "call" in low and "message" not in low:
        return "call_button", 0.95

    # Row-like chat entries
    if et not in {"button", "link", "cell", "unknown"}:
        return "unknown", 0.3

    if "community" in low or "announcement group" in low:
        return "community", 0.88
    if (
        "<>" in low
        or " group" in f" {low}"
        or low.endswith(" group")
        or "created this group" in blob
        or " intro" in f" {low}"
    ):
        return "group", 0.9

    # Truncated sidebar labels often groups in WA Electron
    if lab.endswith("…") or lab.endswith("..."):
        if not _PHONE_RE.match(lab.rstrip("….")):
            return "group", 0.78

    if _PHONE_RE.match(lab):
        return "contact", 0.9

    tokens = [t for t in low.replace(",", " ").split() if t]
    # Multi-token with Office/HR/Support → still contact
    if tokens and all(len(t) >= 2 for t in tokens):
        # Single-token personal name → contact
        if len(tokens) == 1 and not lab.endswith("…"):
            return "contact", 0.82
        if len(tokens) >= 2 and not any(x in low for x in ("group", "community", "announcement")):
            return "contact", 0.75

    return "unknown", 0.4


def apply_semantic_types(world: WorldModel) -> None:
    """Attach semantic_type beliefs to all visible entities."""
    for e in world.entities.values():
        if not e.visible:
            continue
        kind, conf = infer_semantic_type(e)
        e.beliefs["semantic_type"] = Belief(value=kind, confidence=conf)
        e.attributes = dict(e.attributes or {})
        e.attributes["semantic_type"] = kind
        e.attributes["semantic_type_confidence"] = conf


def entity_semantic_type(entity: Entity) -> Tuple[str, float]:
    b = entity.beliefs.get("semantic_type") if entity.beliefs else None
    if b is not None:
        return str(b.value), float(b.confidence)
    # Fall back to attributes / infer
    attrs = entity.attributes or {}
    if attrs.get("semantic_type"):
        return str(attrs["semantic_type"]), float(attrs.get("semantic_type_confidence") or 0.5)
    return infer_semantic_type(entity)
