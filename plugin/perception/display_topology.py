"""Multi-display topology for capture ↔ pointer geometry.

The agent captures a *window*, which may sit on any display. Image (0,0) is that
window's top-left, not the main display origin. AX / CGEvent speak global
Quartz points across the whole desktop. This module makes that topology an
explicit runtime fact so image inventory points are converted, screen points
are kept, and clicks that miss the task window are refused.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

Bounds = Tuple[float, float, float, float]
Point = Tuple[float, float]


@dataclass(frozen=True)
class DisplayInfo:
    index: int
    bounds: Bounds  # global (x, y, w, h)
    backing_scale: float = 1.0
    is_main: bool = False

    def contains(self, x: float, y: float, *, pad: float = 0.0) -> bool:
        bx, by, bw, bh = self.bounds
        return (
            bx - pad <= x <= bx + bw + pad
            and by - pad <= y <= by + bh + pad
        )


@dataclass(frozen=True)
class TaskSurface:
    """Where the task app window lives in the multi-display desktop."""

    app: str
    window_bounds: Optional[Bounds] = None
    window_id: Optional[int] = None
    display_index: Optional[int] = None
    display_count: int = 0
    displays: Tuple[DisplayInfo, ...] = ()
    capture_origin: Tuple[float, float] = (0.0, 0.0)
    capture_scale: float = 1.0
    point_scale: float = 1.0  # VLM image → screen (may include downscale)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app": self.app,
            "window_bounds": list(self.window_bounds) if self.window_bounds else None,
            "window_id": self.window_id,
            "display_index": self.display_index,
            "display_count": self.display_count,
            "displays": [
                {
                    "index": d.index,
                    "bounds": list(d.bounds),
                    "backing_scale": d.backing_scale,
                    "is_main": d.is_main,
                }
                for d in self.displays
            ],
            "capture_origin": list(self.capture_origin),
            "capture_scale": self.capture_scale,
            "point_scale": self.point_scale,
            "note": (
                "Image (0,0) is the task window top-left. Pointer events use "
                "global desktop points. Prefer OCR/AX screen bounds; if you "
                "emit image points, set coordinate_space=image."
            ),
        }


def list_displays() -> List[DisplayInfo]:
    """Enumerate attached displays in global Quartz coordinates."""
    try:
        from AppKit import NSScreen
    except Exception:
        return []
    out: List[DisplayInfo] = []
    try:
        screens = list(NSScreen.screens() or [])
    except Exception:
        return []
    main = None
    try:
        main = NSScreen.mainScreen()
    except Exception:
        main = None
    for i, screen in enumerate(screens):
        try:
            frame = screen.frame()
            bounds = (
                float(frame.origin.x),
                float(frame.origin.y),
                float(frame.size.width),
                float(frame.size.height),
            )
            scale = float(screen.backingScaleFactor())
        except Exception:
            continue
        is_main = False
        try:
            is_main = bool(main is not None and screen == main)
        except Exception:
            is_main = i == 0
        out.append(
            DisplayInfo(index=i, bounds=bounds, backing_scale=scale, is_main=is_main)
        )
    return out


def _normalize_owner(name: Any) -> str:
    import unicodedata

    text = str(name or "")
    cleaned = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return cleaned.strip().lower()


def window_frame_for_app(app_name: str) -> Optional[Tuple[int, Bounds]]:
    """Largest on-screen normal window for ``app_name`` → (window_id, bounds)."""
    target = _normalize_owner(app_name)
    if not target:
        return None
    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListOptionOnScreenOnly,
        )
    except Exception:
        return None
    try:
        infos = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID) or []
    except Exception:
        return None
    best: Optional[Tuple[int, Bounds]] = None
    best_area = 0.0
    for info in infos:
        owner = _normalize_owner(info.get("kCGWindowOwnerName"))
        if owner != target and target not in owner and owner not in target:
            continue
        layer = info.get("kCGWindowLayer")
        if layer not in (0, None):
            continue
        bounds = info.get("kCGWindowBounds") or {}
        try:
            x = float(bounds.get("X", 0.0))
            y = float(bounds.get("Y", 0.0))
            w = float(bounds.get("Width", 0.0))
            h = float(bounds.get("Height", 0.0))
        except (TypeError, ValueError):
            continue
        area = w * h
        if area > best_area:
            num = info.get("kCGWindowNumber")
            if num is None:
                continue
            best_area = area
            best = (int(num), (x, y, w, h))
    return best


def point_in_bounds(
    point: Optional[Sequence[float]],
    bounds: Optional[Sequence[float]],
    *,
    pad: float = 24.0,
) -> bool:
    if point is None or bounds is None or len(point) < 2 or len(bounds) < 4:
        return False
    try:
        x, y = float(point[0]), float(point[1])
        bx, by, bw, bh = (float(v) for v in tuple(bounds)[:4])
    except (TypeError, ValueError, IndexError):
        return False
    return bx - pad <= x <= bx + bw + pad and by - pad <= y <= by + bh + pad


def display_index_for_bounds(
    bounds: Optional[Sequence[float]], displays: Sequence[DisplayInfo]
) -> Optional[int]:
    if bounds is None or len(bounds) < 4 or not displays:
        return None
    try:
        cx = float(bounds[0]) + float(bounds[2]) / 2.0
        cy = float(bounds[1]) + float(bounds[3]) / 2.0
    except (TypeError, ValueError, IndexError):
        return None
    for d in displays:
        if d.contains(cx, cy):
            return d.index
    # Fallback: nearest display center.
    best_i = None
    best_d = None
    for d in displays:
        bx, by, bw, bh = d.bounds
        dx = cx - (bx + bw / 2.0)
        dy = cy - (by + bh / 2.0)
        dist = dx * dx + dy * dy
        if best_d is None or dist < best_d:
            best_d = dist
            best_i = d.index
    return best_i


def build_task_surface(
    app: str,
    *,
    capture_frame: Optional[Dict[str, Any]] = None,
    point_origin: Optional[Sequence[float]] = None,
    point_scale: Optional[float] = None,
) -> TaskSurface:
    """Snapshot multi-display topology + task window for ``app``."""
    displays = tuple(list_displays())
    found = window_frame_for_app(app)
    window_id = found[0] if found else None
    window_bounds = found[1] if found else None
    frame_ox, frame_oy, frame_scale = 0.0, 0.0, 1.0
    if isinstance(capture_frame, dict):
        try:
            frame_ox = float(capture_frame.get("origin_x", 0.0) or 0.0)
            frame_oy = float(capture_frame.get("origin_y", 0.0) or 0.0)
            frame_scale = float(capture_frame.get("scale", 1.0) or 1.0)
        except (TypeError, ValueError):
            pass
    if point_origin is not None and len(point_origin) >= 2:
        try:
            frame_ox = float(point_origin[0])
            frame_oy = float(point_origin[1])
        except (TypeError, ValueError):
            pass
    # Prefer live window origin when capture frame is stale/identity but window moved.
    if window_bounds is not None and frame_ox == 0.0 and frame_oy == 0.0:
        frame_ox, frame_oy = float(window_bounds[0]), float(window_bounds[1])
    try:
        pscale = float(point_scale) if point_scale is not None else 1.0
    except (TypeError, ValueError):
        pscale = 1.0
    if pscale <= 0:
        pscale = 1.0
    return TaskSurface(
        app=str(app or ""),
        window_bounds=window_bounds,
        window_id=window_id,
        display_index=display_index_for_bounds(window_bounds, displays),
        display_count=len(displays),
        displays=displays,
        capture_origin=(frame_ox, frame_oy),
        capture_scale=frame_scale if frame_scale > 0 else 1.0,
        point_scale=pscale,
    )


def looks_like_image_point(
    point: Optional[Sequence[float]],
    surface: TaskSurface,
) -> bool:
    """True when ``point`` is relative to the window image, not global desktop."""
    if point is None or len(point) < 2:
        return False
    try:
        x, y = float(point[0]), float(point[1])
    except (TypeError, ValueError, IndexError):
        return False
    wb = surface.window_bounds
    ox, oy = surface.capture_origin
    # Already inside the live task window in global space → screen.
    if wb is not None and point_in_bounds(point, wb, pad=48.0):
        return False
    # Left of / above a window that lives on a secondary display → image.
    if ox > 80.0 and x < ox - 8.0:
        return True
    if oy > 40.0 and y < oy - 8.0 and x < (ox + (wb[2] if wb else 2000.0)):
        # weaker; only if also not in any display's far region
        if wb is not None and x <= float(wb[2]) + 80.0 and y <= float(wb[3]) + 80.0:
            return True
    # Inside the window-local rectangle [0,w]×[0,h] while window is offset.
    if wb is not None and ox > 80.0:
        ww, wh = float(wb[2]), float(wb[3])
        if 0.0 <= x <= ww + 40.0 and 0.0 <= y <= wh + 40.0:
            return True
    return False


def to_screen_point(
    point: Optional[Sequence[float]],
    surface: TaskSurface,
    *,
    coordinate_space: str = "",
) -> Optional[Point]:
    """Convert a point to global screen points using the task surface."""
    if point is None or len(point) < 2:
        return None
    try:
        x, y = float(point[0]), float(point[1])
    except (TypeError, ValueError, IndexError):
        return None
    space = str(coordinate_space or "").strip().lower()
    if space == "screen":
        return (x, y)
    if space == "image" or looks_like_image_point(point, surface):
        ox, oy = surface.capture_origin
        scale = float(surface.point_scale) if surface.point_scale > 0 else 1.0
        # point_scale already folds capture DPI + VLM downscale (unified path).
        # When only capture_scale is known, fall back to origin + px/capture_scale.
        if scale == 1.0 and surface.capture_scale > 1.0 and space == "image":
            cs = surface.capture_scale
            return (ox + x / cs, oy + y / cs)
        return (ox + x * scale, oy + y * scale)
    return (x, y)


def to_screen_bounds(
    bounds: Optional[Sequence[float]],
    surface: TaskSurface,
    *,
    coordinate_space: str = "",
) -> Optional[Bounds]:
    if bounds is None or len(bounds) < 4:
        return None
    try:
        x, y, w, h = (float(v) for v in tuple(bounds)[:4])
    except (TypeError, ValueError):
        return None
    tl = to_screen_point((x, y), surface, coordinate_space=coordinate_space)
    if tl is None:
        return None
    space = str(coordinate_space or "").strip().lower()
    if space == "image" or looks_like_image_point((x, y), surface):
        scale = float(surface.point_scale) if surface.point_scale > 0 else 1.0
        if scale == 1.0 and surface.capture_scale > 1.0 and space == "image":
            cs = surface.capture_scale
            return (tl[0], tl[1], w / cs, h / cs)
        return (tl[0], tl[1], w * scale, h * scale)
    return (tl[0], tl[1], w, h)


def attach_task_surface(
    document: Dict[str, Any],
    surface: TaskSurface,
) -> Dict[str, Any]:
    """Stamp topology onto the world document (runtime-owned, not model-owned)."""
    out = dict(document or {})
    out["task_surface"] = surface.to_dict()
    return out
