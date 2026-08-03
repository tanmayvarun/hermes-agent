"""Resolve AppOverlay by active app / goal.app."""

from __future__ import annotations

from typing import Optional

from plugin.agent.apps.base import AppOverlay
from plugin.agent.apps.filesystem import FilesystemOverlay
from plugin.agent.apps.generic import GenericOverlay
from plugin.agent.apps.whatsapp import WhatsAppOverlay
from plugin.worldmodel.model import WorldModel

# Named overlays, matched by app name. The generic overlay is the domain-neutral
# fallback — resolution is not WhatsApp-centric, so an unknown app gets the
# general machinery, not WhatsApp's vocabulary.
_OVERLAYS: list = [WhatsAppOverlay(), FilesystemOverlay()]
_GENERIC = GenericOverlay()


def get_overlay(app: str = "", world: Optional[WorldModel] = None) -> AppOverlay:
    name = (app or (world.active_app if world else "") or "").lower()
    for ov in _OVERLAYS:
        for n in ov.app_names:
            if n == "*":
                continue
            if n.lower() in name or name in n.lower():
                return ov
    return _GENERIC


def register_overlay(overlay: AppOverlay) -> None:
    _OVERLAYS.insert(0, overlay)
