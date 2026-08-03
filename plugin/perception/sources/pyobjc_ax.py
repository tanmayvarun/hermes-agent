"""PyObjC deep AX perception source.

Deep AX gives a rich element tree but no pixels. When ``with_screenshot`` is
set (the default), this source also captures the screen and attaches it to the
observation so accessibility structure and pixels travel together — the
redundant, complete input the multimodal perceptor is designed around. When one
channel is blind (e.g. a chrome-only AX tree), the other can still carry the
scene.
"""

from __future__ import annotations

from plugin.perception.macos.accessibility.observer import attach_screenshot_to_observation
from plugin.perception.sources.base import (
    ObservationBundle,
    format_observation_raw_summary,
    timed_observe,
)


class PyObjcAxSource:
    source_id = "pyobjc_ax"

    def __init__(self, *, with_screenshot: bool = True) -> None:
        self.with_screenshot = with_screenshot

    def observe(self, app: str) -> ObservationBundle:
        from plugin.perception.macos.accessibility.ax_tree import observe_app_ax

        bundle = timed_observe(self.source_id, observe_app_ax, app)
        if self.with_screenshot:
            obs, screenshot_error = attach_screenshot_to_observation(
                bundle.observation,
                app_name=app,
                require_screenshot=False,
            )
            bundle.observation = obs
            # The raw summary caches screenshot=… so refresh it after attaching.
            bundle.raw_meta = dict(bundle.raw_meta or {})
            bundle.raw_meta["raw_summary"] = format_observation_raw_summary(obs)
            if screenshot_error:
                bundle.raw_meta["screenshot_error"] = screenshot_error
        return bundle
