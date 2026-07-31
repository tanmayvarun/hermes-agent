"""macapptree perception source."""

from __future__ import annotations

from plugin.perception.sources.base import ObservationBundle, PerceptionSource, timed_observe


class MacAppTreeSource:
    source_id = "macapptree"

    def __init__(self, *, with_screenshot: bool = False) -> None:
        self.with_screenshot = with_screenshot

    def observe(self, app: str) -> ObservationBundle:
        from plugin.perception.macos.accessibility.observer import (
            MacAppTreeObserver,
            macapptree_available,
        )

        if not macapptree_available():
            raise ImportError("macapptree not installed")

        obs_fn = MacAppTreeObserver(with_screenshot=self.with_screenshot).observe
        return timed_observe(self.source_id, obs_fn, app)
