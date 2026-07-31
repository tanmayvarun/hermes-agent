"""Resolve AppOverlay by active app / goal.app."""

from __future__ import annotations

from typing import Optional

from plugin.agent.apps.base import AppOverlay
from plugin.agent.apps.whatsapp import WhatsAppOverlay
from plugin.worldmodel.model import WorldModel

_OVERLAYS: list = [WhatsAppOverlay()]


def get_overlay(app: str = "", world: Optional[WorldModel] = None) -> AppOverlay:
    name = (app or (world.active_app if world else "") or "").lower()
    for ov in _OVERLAYS:
        for n in ov.app_names:
            if n.lower() in name or name in n.lower():
                return ov
    # Default: WhatsApp overlay for current POC benchmark
    return _OVERLAYS[0]


def register_overlay(overlay: AppOverlay) -> None:
    _OVERLAYS.insert(0, overlay)
