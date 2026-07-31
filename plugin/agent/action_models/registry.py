"""Simple in-process action model registry."""

from __future__ import annotations

from typing import Any, List

_REGISTRY: List[Any] = []


def register_action_model(model: Any) -> Any:
    _REGISTRY.append(model)
    return model


def list_action_models() -> List[Any]:
    return list(_REGISTRY)


def clear_action_models() -> None:
    _REGISTRY.clear()
