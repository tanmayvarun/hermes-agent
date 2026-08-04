"""Open a named entity on the current surface.

The substrate is an addressable entity -- something perception (or AX) has
already made targetable. Opening it is general: click the resolved target.
Which entity to open is judgment and stays with the model.

    open_entity(target) -> navigate into that conversation / channel / thread

Apps do not fork this. Resolution prefers overlay.resolve_target when a world
is supplied, then a model-supplied point, then a label click. That order is
mechanism, not planning.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Protocol, Tuple, runtime_checkable

from plugin.agent.capabilities.base import AddressableEntity, CapabilityOutcome

logger = logging.getLogger(__name__)

_POINT_TARGET_SIZE = 24


@runtime_checkable
class OpenRuntime(Protocol):
    def activate(self, app: str) -> None: ...

    def click(self, app: str, label: str, *, bounds: Optional[Tuple[float, float, float, float]] = None) -> Tuple[bool, str]: ...


@dataclass
class MacOpenRuntime:
    """macOS click adapter for open_entity."""

    def activate(self, app: str) -> None:
        from plugin.executor.ax_action import _activate_app, _is_frontmost

        if not _is_frontmost(app):
            _activate_app(app)

    def click(
        self, app: str, label: str, *, bounds: Optional[Tuple[float, float, float, float]] = None
    ) -> Tuple[bool, str]:
        from plugin.executor.ax_action import ax_click

        result = ax_click(app, label or "entity", bounds=bounds)
        return bool(result.ok), str(result.message or "")


def _point_bounds(point: Any) -> Optional[Tuple[float, float, float, float]]:
    if not point:
        return None
    try:
        x, y = int(point[0]), int(point[1])
    except (TypeError, ValueError, IndexError):
        return None
    half = _POINT_TARGET_SIZE // 2
    return (float(x - half), float(y - half), float(_POINT_TARGET_SIZE), float(_POINT_TARGET_SIZE))


def resolve_addressable(
    request_arg: str,
    extras: dict,
    overlay: Any,
    *,
    app: str = "",
) -> AddressableEntity:
    """Build the substrate from model args + optional overlay resolution."""
    app = str(app or extras.get("app") or "")
    label = (request_arg or "").strip()
    entity_id = extras.get("entity_id")
    point = extras.get("point")
    bounds = extras.get("bounds")
    world = extras.get("world")

    if world is not None and (label or entity_id is not None):
        try:
            entity = None
            # Geometry-first: a caller-supplied entity_id is the decision's already
            # grounded target (the perceptor/reference-resolver picked *this*
            # perceived object). Honour it directly and click its exact bounds.
            # Re-resolving by label here is what threw the choice away and let the
            # noisy-OCR shortest-label match grab the search-box echo or a
            # "…- Video call" row instead of the chat row.
            if entity_id is not None:
                entities = getattr(world, "entities", None)
                if isinstance(entities, dict):
                    cand = entities.get(int(entity_id)) if str(entity_id).lstrip("-").isdigit() else None
                    if cand is not None and getattr(cand, "visible", True):
                        entity = cand
                if entity is None:
                    for cand in (entities.values() if isinstance(entities, dict) else (entities or [])):
                        if getattr(cand, "id", None) == entity_id and getattr(cand, "visible", True):
                            entity = cand
                            break
            # Only fall back to overlay semantic resolution when no grounded id
            # was supplied (an AX-rich app, or the model gave a bare label).
            if entity is None and hasattr(overlay, "resolve_target") and label:
                entity = overlay.resolve_target(world, label, "click")
            if entity is not None:
                label = str(getattr(entity, "label", "") or label)
                bounds = getattr(entity, "bounds", None) or bounds
                entity_id = getattr(entity, "id", entity_id)
        except Exception as exc:
            logger.debug("overlay resolve_target failed: %s", exc)

    if bounds is None:
        bounds = _point_bounds(point)

    point_tuple: Optional[Tuple[int, int]] = None
    if point is not None:
        try:
            point_tuple = (int(point[0]), int(point[1]))
        except (TypeError, ValueError, IndexError):
            point_tuple = None

    return AddressableEntity(
        app=app,
        label=label,
        entity_id=int(entity_id) if entity_id is not None else None,
        point=point_tuple,
        bounds=tuple(bounds) if bounds is not None else None,  # type: ignore[arg-type]
    )


def open_entity(
    entity: AddressableEntity,
    runtime: OpenRuntime,
) -> CapabilityOutcome:
    """Open the addressable entity. Reports actuation, not task success."""
    if not entity.label and entity.bounds is None:
        return CapabilityOutcome(
            ok=False,
            capability="open_entity",
            message="open_entity needs a label or a point",
        )

    try:
        runtime.activate(entity.app)
        ok, message = runtime.click(entity.app, entity.label or "entity", bounds=entity.bounds)
    except Exception as exc:
        logger.warning("open_entity failed: %s", exc)
        return CapabilityOutcome(
            ok=False,
            capability="open_entity",
            realization="resolve_and_click",
            message=f"open failed: {exc}",
        )

    return CapabilityOutcome(
        ok=ok,
        capability="open_entity",
        realization="resolve_and_click",
        message=message or f"opened {entity.label!r}",
        evidence={
            "substrate": "addressable_entity",
            "label": entity.label,
            "entity_id": entity.entity_id,
            "had_bounds": entity.bounds is not None,
        },
    )
