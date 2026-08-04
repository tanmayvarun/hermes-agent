"""The transform between a screenshot's pixels and the screen the agent clicks.

A capture is not the screen. Two things separate them, and both must be undone
before a perceived rectangle can be actuated:

*Scale.* On a Retina display the window server composites at 2x, so a capture of
a 400-point-wide window is 800 pixels wide. Coordinates read off those pixels are
twice the value the pointer expects, because ``CGEventCreateMouseEvent`` speaks
points.

*Origin.* Perception grabs the task app's window, not the whole screen
(``screencapture -l <window>``), so that an occluding window cannot leak into the
vision path. Coordinates in that image are relative to the window's top-left
corner, while the pointer's are relative to the display's.

Left unconverted, both errors compound and every vision-derived click lands
somewhere else entirely — near enough the truth to look plausible in a log
("click 'Kulvinder Ji' center=(251, 393)"), far enough to hit empty space. The
action then reports success, nothing happens, and the agent loops on a control
it believes it pressed. That failure is silent by construction, which is why the
transform is made explicit here and carried with the observation rather than
being re-derived, guessed, or assumed to be the identity by each consumer.

The scale is measured, not assumed: the ratio of the captured image's width to
the window's width in points. That is correct across mixed-DPI setups, where a
window on a non-Retina second display has scale 1.0 while the main display is at
2.0, and a hard-coded ``backingScaleFactor`` from the main screen would be wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

# The identity: a capture already in screen points with its origin at the
# display's corner. Used when nothing better is known, so an unconverted path
# behaves exactly as it did before this module existed.
IDENTITY_KEY = "capture_frame"


@dataclass(frozen=True)
class CaptureFrame:
    """Maps a point in captured-image pixels to a point on screen, in points."""

    origin_x: float = 0.0
    origin_y: float = 0.0
    scale: float = 1.0

    @property
    def is_identity(self) -> bool:
        return self.origin_x == 0.0 and self.origin_y == 0.0 and self.scale == 1.0

    def point_to_screen(self, x: float, y: float) -> Tuple[float, float]:
        s = self.scale if self.scale > 0 else 1.0
        return (self.origin_x + float(x) / s, self.origin_y + float(y) / s)

    def bbox_to_screen(
        self, bbox: Optional[Sequence[float]]
    ) -> Optional[Tuple[float, float, float, float]]:
        """Convert an (x, y, w, h) box from image pixels to screen points."""
        if bbox is None:
            return None
        try:
            x, y, w, h = (float(v) for v in tuple(bbox)[:4])
        except (TypeError, ValueError):
            return None
        s = self.scale if self.scale > 0 else 1.0
        return (self.origin_x + x / s, self.origin_y + y / s, w / s, h / s)

    def as_dict(self) -> Dict[str, float]:
        return {"origin_x": self.origin_x, "origin_y": self.origin_y, "scale": self.scale}

    @classmethod
    def from_dict(cls, raw: Any) -> "CaptureFrame":
        if not isinstance(raw, dict):
            return cls()
        try:
            return cls(
                origin_x=float(raw.get("origin_x", 0.0) or 0.0),
                origin_y=float(raw.get("origin_y", 0.0) or 0.0),
                scale=float(raw.get("scale", 1.0) or 1.0),
            )
        except (TypeError, ValueError):
            return cls()

    @classmethod
    def measure(
        cls,
        image_width_px: float,
        window_bounds_points: Optional[Sequence[float]],
    ) -> "CaptureFrame":
        """Derive the transform from the image and the window it was scoped to.

        ``window_bounds_points`` is (x, y, w, h) in Quartz global display points,
        as ``kCGWindowBounds`` reports it. A full-screen capture passes None and
        gets the origin at (0, 0) with the scale still measured.
        """
        try:
            width_px = float(image_width_px)
        except (TypeError, ValueError):
            return cls()
        if width_px <= 0:
            return cls()
        if window_bounds_points is None:
            return cls()
        try:
            wx, wy, ww, _wh = (float(v) for v in tuple(window_bounds_points)[:4])
        except (TypeError, ValueError):
            return cls()
        if ww <= 0:
            return cls(origin_x=wx, origin_y=wy, scale=1.0)
        scale = width_px / ww
        # A capture is composited at an integral backing scale. Snapping absorbs
        # the pixel or two `screencapture -o` trims from the shadow border, which
        # would otherwise leave a scale like 2.004 and drift the far edge of a
        # wide window by several points.
        nearest = round(scale)
        if nearest >= 1 and abs(scale - nearest) <= 0.05:
            scale = float(nearest)
        return cls(origin_x=wx, origin_y=wy, scale=scale)


def frame_from_meta(meta: Any) -> CaptureFrame:
    """Read the transform an observation carries, or the identity if it carries none."""
    if not isinstance(meta, dict):
        return CaptureFrame()
    return CaptureFrame.from_dict(meta.get(IDENTITY_KEY))
