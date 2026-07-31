"""Optional Screen2AX vision recovery source."""

from __future__ import annotations

from plugin.perception.observation import Observation
from plugin.perception.sources.base import ObservationBundle, timed_observe


class Screen2AxSource:
    source_id = "screen2ax"

    def __init__(self, screenshot_path: str | None = None) -> None:
        self.screenshot_path = screenshot_path

    def observe(self, app: str) -> ObservationBundle:
        def _fn(app_name: str) -> Observation:
            from plugin.perception.macos.fusion.coverage import maybe_recover_with_screen2ax

            stub = Observation(
                timestamp=0.0,
                app_name=app_name,
                window_name="",
                nodes=[],
                screenshot_path=self.screenshot_path,
                source="ax_placeholder",
                coverage=0.0,
                degraded=True,
            )
            return maybe_recover_with_screen2ax(stub)

        return timed_observe(self.source_id, _fn, app)
