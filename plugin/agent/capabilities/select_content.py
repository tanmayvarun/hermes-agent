"""Select / focus a content object on the current surface.

    select_content(target) -> click the message / row / link so it is the active object

Distinct from open_entity: opening navigates into a container (chat, channel);
selecting focuses an item inside an already-open surface (a message to forward).
Same mechanism (resolve + click), different intent in the world document.
"""

from __future__ import annotations

import logging

from plugin.agent.capabilities.base import AddressableEntity, CapabilityOutcome
from plugin.agent.capabilities.pointer_runtime import PointerRuntime

logger = logging.getLogger(__name__)


def select_content(entity: AddressableEntity, runtime: PointerRuntime) -> CapabilityOutcome:
    if not entity.label and entity.bounds is None:
        return CapabilityOutcome(
            ok=False,
            capability="select_content",
            message="select_content needs a label or a point",
        )

    try:
        runtime.activate(entity.app)
        ok, message = runtime.click(entity.app, entity.label or "content", bounds=entity.bounds)
    except Exception as exc:
        logger.warning("select_content failed: %s", exc)
        return CapabilityOutcome(
            ok=False,
            capability="select_content",
            realization="select_click",
            message=f"select failed: {exc}",
        )

    return CapabilityOutcome(
        ok=ok,
        capability="select_content",
        realization="select_click",
        message=message or f"selected {entity.label!r}",
        evidence={
            "substrate": "addressable_entity",
            "label": entity.label,
            "entity_id": entity.entity_id,
            "had_bounds": entity.bounds is not None,
        },
    )
