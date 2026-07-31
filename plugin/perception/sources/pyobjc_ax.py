"""PyObjC deep AX perception source."""

from __future__ import annotations

from plugin.perception.sources.base import ObservationBundle, PerceptionSource, timed_observe


class PyObjcAxSource:
    source_id = "pyobjc_ax"

    def observe(self, app: str) -> ObservationBundle:
        from plugin.perception.macos.accessibility.ax_tree import observe_app_ax

        return timed_observe(self.source_id, observe_app_ax, app)
