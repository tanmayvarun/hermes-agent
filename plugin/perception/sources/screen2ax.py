"""Optional Screen2AX vision recovery source."""

from __future__ import annotations

from plugin.perception.observation import Observation
from plugin.perception.sources.base import ObservationBundle, timed_observe


class Screen2AxSource:
    source_id = "screen2ax"

    def __init__(
        self,
        screenshot_path: str | None = None,
        *,
        include_overlays: bool = False,
    ) -> None:
        self.screenshot_path = screenshot_path
        self.include_overlays = include_overlays

    def observe(self, app: str) -> ObservationBundle:
        def _fn(app_name: str) -> Observation:
            import time as _time

            from plugin.perception.macos.accessibility.observer import (
                attach_screenshot_to_observation,
            )
            from plugin.perception.macos.fusion.coverage import maybe_recover_with_ocr

            stub = Observation(
                timestamp=_time.time(),
                app_name=app_name,
                window_name="",
                nodes=[],
                screenshot_path=self.screenshot_path,
                source="ax_placeholder",
                coverage=0.0,
                degraded=True,
            )
            # This is the dedicated pixels->content source: it must have its own
            # screenshot to read. Running in parallel with the AX source keeps OCR
            # off the critical path.
            if not stub.screenshot_path:
                stub, _err = attach_screenshot_to_observation(
                    stub,
                    app_name=app_name,
                    require_screenshot=False,
                    include_overlays=self.include_overlays,
                )
            # Force OCR: this source's whole job is to recover content from pixels,
            # independent of AX coverage (the AX tree may be blind on this surface).
            return maybe_recover_with_ocr(stub, use_case=app_name, force=True)

        return timed_observe(self.source_id, _fn, app)
