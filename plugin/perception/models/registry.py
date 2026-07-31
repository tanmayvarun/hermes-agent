"""Simple in-process screen model registry."""

from __future__ import annotations

from typing import Any, List

_REGISTRY: List[Any] = []


def register_screen_model(model: Any) -> Any:
    _REGISTRY.append(model)
    return model


def list_screen_models() -> List[Any]:
    return list(_REGISTRY)


def clear_screen_models() -> None:
    _REGISTRY.clear()
