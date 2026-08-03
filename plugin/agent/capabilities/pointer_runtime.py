"""Shared macOS pointer adapter for entity/affordance capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Tuple, runtime_checkable


@runtime_checkable
class PointerRuntime(Protocol):
    def activate(self, app: str) -> None: ...

    def click(
        self, app: str, label: str, *, bounds: Optional[Tuple[float, float, float, float]] = None
    ) -> Tuple[bool, str]: ...

    def hover(
        self, app: str, label: str, *, bounds: Optional[Tuple[float, float, float, float]] = None
    ) -> Tuple[bool, str]: ...

    def context_click(
        self, app: str, label: str, *, bounds: Optional[Tuple[float, float, float, float]] = None
    ) -> Tuple[bool, str]: ...


@dataclass
class MacPointerRuntime:
    def activate(self, app: str) -> None:
        from plugin.executor.ax_action import _activate_app, _is_frontmost

        if not _is_frontmost(app):
            _activate_app(app)

    def click(
        self, app: str, label: str, *, bounds: Optional[Tuple[float, float, float, float]] = None
    ) -> Tuple[bool, str]:
        from plugin.executor.ax_action import ax_click

        result = ax_click(app, label or "target", bounds=bounds)
        return bool(result.ok), str(result.message or "")

    def hover(
        self, app: str, label: str, *, bounds: Optional[Tuple[float, float, float, float]] = None
    ) -> Tuple[bool, str]:
        from plugin.executor.ax_action import ax_hover

        result = ax_hover(app, label or "target", bounds=bounds)
        return bool(result.ok), str(result.message or "")

    def context_click(
        self, app: str, label: str, *, bounds: Optional[Tuple[float, float, float, float]] = None
    ) -> Tuple[bool, str]:
        from plugin.executor.ax_action import ax_context_click

        result = ax_context_click(app, label or "target", bounds=bounds)
        return bool(result.ok), str(result.message or "")
