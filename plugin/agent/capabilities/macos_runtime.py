"""macOS adapter for the locate_content primitives.

The realizations in `locate_content` are written against a narrow protocol so
they can be exercised without a display. This is the one place that knows about
Quartz events and the accessibility tree.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, List, Optional, Tuple

from plugin.agent.capabilities.locate_content import KeyChord, LocatorRuntime

logger = logging.getLogger(__name__)

# Text shorter than this is chrome -- window title, tab labels, button names --
# rather than content. Letting the substring probe run against it would produce
# a confident "no match" from a surface it never actually read.
_MIN_MEANINGFUL_TEXT = 40


class MacLocatorRuntime(LocatorRuntime):
    """Mechanical primitives backed by Quartz events and the AX tree."""

    def __init__(self, app: str) -> None:
        self.app = app
        self._nodes: Optional[List[Any]] = None

    def activate(self, app: str) -> None:
        from plugin.executor.ax_action import _activate_app, _is_frontmost

        if not _is_frontmost(app):
            _activate_app(app)
            time.sleep(0.2)

    def key(self, chord: KeyChord) -> None:
        from plugin.executor.ax_action import _keydown

        self._invalidate()
        _keydown(chord.code, cmd=chord.cmd)
        time.sleep(0.15)

    def type_text(self, text: str) -> None:
        from plugin.executor.ax_action import _type_via_cgevent

        self._invalidate()
        _type_via_cgevent(text)

    def scroll(self, direction: str, amount: int) -> None:
        from plugin.executor.ax_action import _scroll_wheel

        anchor = self._surface_center()
        self._invalidate()
        if anchor is None:
            raise RuntimeError(f"no window to scroll for {self.app}")
        lines = abs(int(amount)) or 3
        _scroll_wheel(anchor[0], anchor[1], lines=lines if direction == "up" else -lines)
        time.sleep(0.25)

    def surface_text(self) -> str:
        text = self._text()
        # An app that draws its content in a custom view exposes a few chrome
        # labels and nothing else, which a probe cannot tell apart from a real
        # absence. Report it as unreadable so the caller falls back to looking.
        return text if len(text) >= _MIN_MEANINGFUL_TEXT else ""

    def surface_signature(self) -> str:
        return hashlib.sha1(self._text().encode("utf-8", "ignore")).hexdigest()[:16]

    def text_input_focused(self) -> bool:
        try:
            from plugin.executor.ax_action import _find_search_text_field

            field, _ = _find_search_text_field(self.app)
            return field is not None
        except Exception as exc:
            logger.debug("focus probe failed for %s: %s", self.app, exc)
            return False

    def filter_field_ready(self) -> bool:
        """True only when a search/find field (not composer) is grounded."""
        try:
            from plugin.agent.capabilities.action_area import (
                label_looks_like_composer,
                label_looks_like_filter,
            )
            from plugin.executor.ax_action import _find_search_text_field

            field, label = _find_search_text_field(self.app)
            if field is None:
                return False
            lab = str(label or "").strip()
            if label_looks_like_composer(lab):
                return False
            # Prefer explicit filter tokens; AXSearchField without label also ok.
            if label_looks_like_filter(lab):
                return True
            try:
                from plugin.executor.ax_action import _ax_attr

                role = str(_ax_attr(field, "AXRole") or "")
                if role == "AXSearchField":
                    return True
                focused = bool(_ax_attr(field, "AXFocused"))
            except Exception:
                focused = False
            # Focused editable with search-scored label from _find_search_text_field
            # already beat the composer penalty — accept when focused.
            return bool(focused and lab)
        except Exception as exc:
            logger.debug("filter-field probe failed for %s: %s", self.app, exc)
            return False

    def _invalidate(self) -> None:
        self._nodes = None

    def _read_nodes(self) -> List[Any]:
        if self._nodes is not None:
            return self._nodes
        try:
            from plugin.perception.macos.accessibility.ax_tree import observe_app_ax

            observation = observe_app_ax(self.app)
            self._nodes = list(getattr(observation, "nodes", None) or [])
        except Exception as exc:
            logger.debug("AX read failed for %s: %s", self.app, exc)
            self._nodes = []
        return self._nodes

    def _text(self) -> str:
        parts: List[str] = []
        for node in self._read_nodes():
            for attribute in ("name", "value", "description"):
                chunk = str(getattr(node, attribute, "") or "").strip()
                if chunk:
                    parts.append(chunk)
        return "\n".join(parts)

    def _surface_center(self) -> Optional[Tuple[float, float]]:
        for node in self._read_nodes():
            if str(getattr(node, "role", "")) != "AXWindow":
                continue
            bbox = getattr(node, "bbox", None) or ()
            if len(bbox) >= 4 and float(bbox[2]) > 1 and float(bbox[3]) > 1:
                x, y, w, h = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
                return (x + w / 2.0, y + h / 2.0)
        try:
            import pyautogui

            width, height = pyautogui.size()
            return (width / 2.0, height / 2.0)
        except Exception:
            return None
