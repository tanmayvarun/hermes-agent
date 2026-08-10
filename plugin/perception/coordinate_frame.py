"""First-class coordinate frames for observation → actuation.

Every geometric object carries a ``Grounding`` with a ``coordinate_frame_id``.
Conversions go only through ``transform()``. Motor landing updates attempt
evidence — it never rewrites object grounding.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import uuid

Point = Tuple[float, float]
Bounds = Tuple[float, float, float, float]
Geometry = Union[Point, Bounds]


@dataclass(frozen=True)
class CoordinateFrame:
    """Immutable transform context for one geometric space."""

    frame_id: str
    space: str  # image | window | screen
    image_size: Tuple[float, float] = (0.0, 0.0)
    image_origin_in_window: Tuple[float, float] = (0.0, 0.0)
    window_origin_in_screen: Tuple[float, float] = (0.0, 0.0)
    crop_rect_in_parent: Optional[Bounds] = None
    scale_x: float = 1.0
    scale_y: float = 1.0
    backing_scale: float = 1.0
    parent_frame_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.crop_rect_in_parent is not None:
            d["crop_rect_in_parent"] = list(self.crop_rect_in_parent)
        d["image_size"] = list(self.image_size)
        d["image_origin_in_window"] = list(self.image_origin_in_window)
        d["window_origin_in_screen"] = list(self.window_origin_in_screen)
        return d

    @classmethod
    def from_dict(cls, raw: Any) -> "CoordinateFrame":
        if not isinstance(raw, dict):
            return screen_identity_frame()
        crop = raw.get("crop_rect_in_parent")
        crop_t: Optional[Bounds] = None
        if isinstance(crop, (list, tuple)) and len(crop) >= 4:
            crop_t = (float(crop[0]), float(crop[1]), float(crop[2]), float(crop[3]))
        def _xy(key: str, default: Tuple[float, float] = (0.0, 0.0)) -> Tuple[float, float]:
            v = raw.get(key) or default
            try:
                return (float(v[0]), float(v[1]))
            except Exception:
                return default
        return cls(
            frame_id=str(raw.get("frame_id") or new_frame_id(str(raw.get("space") or "screen"))),
            space=str(raw.get("space") or "screen").strip().lower(),
            image_size=_xy("image_size"),
            image_origin_in_window=_xy("image_origin_in_window"),
            window_origin_in_screen=_xy("window_origin_in_screen"),
            crop_rect_in_parent=crop_t,
            scale_x=float(raw.get("scale_x") or 1.0) or 1.0,
            scale_y=float(raw.get("scale_y") or raw.get("scale_x") or 1.0) or 1.0,
            backing_scale=float(raw.get("backing_scale") or 1.0) or 1.0,
            parent_frame_id=str(raw.get("parent_frame_id") or ""),
        )


@dataclass
class Grounding:
    """Authoritative geometry for a semantic object — never motor landing."""

    coordinate_frame_id: str
    point: Optional[Point] = None
    bbox: Optional[Bounds] = None
    provenance: str = ""
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "coordinate_frame_id": self.coordinate_frame_id,
            "point": list(self.point) if self.point else None,
            "bbox": list(self.bbox) if self.bbox else None,
            "provenance": self.provenance,
            "confidence": round(float(self.confidence), 3),
        }

    @classmethod
    def from_dict(cls, raw: Any) -> Optional["Grounding"]:
        if not isinstance(raw, dict):
            return None
        pt = raw.get("point")
        bb = raw.get("bbox") or raw.get("bounds")
        point = None
        bbox = None
        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
            point = (float(pt[0]), float(pt[1]))
        if isinstance(bb, (list, tuple)) and len(bb) >= 4:
            bbox = (float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3]))
        fid = str(raw.get("coordinate_frame_id") or raw.get("frame_id") or "")
        if not fid and not point and not bbox:
            return None
        return cls(
            coordinate_frame_id=fid or "screen",
            point=point,
            bbox=bbox,
            provenance=str(raw.get("provenance") or ""),
            confidence=float(raw.get("confidence") or 0.0),
        )


@dataclass
class FrameGraph:
    """Active frames for one observation (image → window → screen)."""

    frames: Dict[str, CoordinateFrame] = field(default_factory=dict)
    image_frame_id: str = ""
    window_frame_id: str = ""
    screen_frame_id: str = ""

    def get(self, frame_id: str) -> Optional[CoordinateFrame]:
        return self.frames.get(frame_id)

    def by_space(self, space: str) -> Optional[CoordinateFrame]:
        sp = str(space or "").strip().lower()
        for fr in self.frames.values():
            if fr.space == sp:
                return fr
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frames": {k: v.to_dict() for k, v in self.frames.items()},
            "image_frame_id": self.image_frame_id,
            "window_frame_id": self.window_frame_id,
            "screen_frame_id": self.screen_frame_id,
        }


def new_frame_id(space: str = "frame") -> str:
    return f"{space}_{uuid.uuid4().hex[:8]}"


def screen_identity_frame() -> CoordinateFrame:
    return CoordinateFrame(frame_id="screen_identity", space="screen")


def build_frame_graph(
    *,
    image_size: Sequence[float] = (0.0, 0.0),
    window_origin_in_screen: Sequence[float] = (0.0, 0.0),
    capture_scale: float = 1.0,
    point_scale: float = 1.0,
    backing_scale: float = 1.0,
    crop_rect_in_parent: Optional[Sequence[float]] = None,
    image_origin_in_window: Sequence[float] = (0.0, 0.0),
) -> FrameGraph:
    """Build image/window/screen frames from capture topology.

    ``point_scale`` is the VLM image→screen multiplier already used by TaskSurface
    (folds capture DPI + downscale). ``capture_scale`` is px/point from CaptureFrame.
    """
    try:
        iw, ih = float(image_size[0]), float(image_size[1])
    except Exception:
        iw, ih = 0.0, 0.0
    try:
        wox, woy = float(window_origin_in_screen[0]), float(window_origin_in_screen[1])
    except Exception:
        wox, woy = 0.0, 0.0
    try:
        iox, ioy = float(image_origin_in_window[0]), float(image_origin_in_window[1])
    except Exception:
        iox, ioy = 0.0, 0.0
    cs = float(capture_scale) if float(capture_scale or 0) > 0 else 1.0
    ps = float(point_scale) if float(point_scale or 0) > 0 else 1.0
    # Prefer explicit point_scale; else 1/capture_scale for raw pixels.
    sx = ps if ps != 1.0 or cs <= 1.0 else (1.0 / cs)
    sy = sx
    crop: Optional[Bounds] = None
    if crop_rect_in_parent is not None and len(crop_rect_in_parent) >= 4:
        crop = (
            float(crop_rect_in_parent[0]),
            float(crop_rect_in_parent[1]),
            float(crop_rect_in_parent[2]),
            float(crop_rect_in_parent[3]),
        )
    screen = CoordinateFrame(
        frame_id=new_frame_id("screen"),
        space="screen",
        window_origin_in_screen=(wox, woy),
        backing_scale=float(backing_scale or 1.0),
    )
    window = CoordinateFrame(
        frame_id=new_frame_id("window"),
        space="window",
        window_origin_in_screen=(wox, woy),
        scale_x=1.0,
        scale_y=1.0,
        backing_scale=float(backing_scale or 1.0),
        parent_frame_id=screen.frame_id,
    )
    image = CoordinateFrame(
        frame_id=new_frame_id("image"),
        space="image",
        image_size=(iw, ih),
        image_origin_in_window=(iox, ioy),
        window_origin_in_screen=(wox, woy),
        crop_rect_in_parent=crop,
        scale_x=sx,
        scale_y=sy,
        backing_scale=float(backing_scale or cs or 1.0),
        parent_frame_id=window.frame_id,
    )
    return FrameGraph(
        frames={
            screen.frame_id: screen,
            window.frame_id: window,
            image.frame_id: image,
        },
        image_frame_id=image.frame_id,
        window_frame_id=window.frame_id,
        screen_frame_id=screen.frame_id,
    )


def frame_graph_from_task_surface(
    surface: Any,
    *,
    image_size: Sequence[float] = (0.0, 0.0),
) -> FrameGraph:
    """Adapt TaskSurface / capture dict into a FrameGraph."""
    if surface is None:
        return build_frame_graph(image_size=image_size)
    if isinstance(surface, dict):
        origin = surface.get("capture_origin") or (0.0, 0.0)
        return build_frame_graph(
            image_size=image_size,
            window_origin_in_screen=origin,
            capture_scale=float(surface.get("capture_scale") or 1.0),
            point_scale=float(surface.get("point_scale") or 1.0),
            backing_scale=float(surface.get("capture_scale") or 1.0),
        )
    origin = getattr(surface, "capture_origin", (0.0, 0.0))
    return build_frame_graph(
        image_size=image_size,
        window_origin_in_screen=origin,
        capture_scale=float(getattr(surface, "capture_scale", 1.0) or 1.0),
        point_scale=float(getattr(surface, "point_scale", 1.0) or 1.0),
        backing_scale=float(getattr(surface, "capture_scale", 1.0) or 1.0),
    )


def _as_point(g: Geometry) -> Point:
    if len(g) >= 4:
        return (float(g[0]), float(g[1]))
    return (float(g[0]), float(g[1]))


def _to_screen(geom: Geometry, frame: CoordinateFrame) -> Geometry:
    """Map geometry from ``frame`` into global screen points."""
    space = frame.space
    if space == "screen":
        return geom
    ox, oy = frame.window_origin_in_screen
    iox, ioy = frame.image_origin_in_window
    sx = frame.scale_x if frame.scale_x > 0 else 1.0
    sy = frame.scale_y if frame.scale_y > 0 else 1.0
    if frame.crop_rect_in_parent is not None:
        iox += float(frame.crop_rect_in_parent[0])
        ioy += float(frame.crop_rect_in_parent[1])
    if len(geom) >= 4:
        x, y, w, h = (float(v) for v in geom[:4])
        if space == "image":
            return (ox + iox + x * sx, oy + ioy + y * sy, w * sx, h * sy)
        if space == "window":
            return (ox + x, oy + y, w, h)
        return geom
    x, y = float(geom[0]), float(geom[1])
    if space == "image":
        return (ox + iox + x * sx, oy + ioy + y * sy)
    if space == "window":
        return (ox + x, oy + y)
    return (x, y)


def _from_screen(geom: Geometry, frame: CoordinateFrame) -> Geometry:
    """Map global screen geometry into ``frame``."""
    space = frame.space
    if space == "screen":
        return geom
    ox, oy = frame.window_origin_in_screen
    iox, ioy = frame.image_origin_in_window
    sx = frame.scale_x if frame.scale_x > 0 else 1.0
    sy = frame.scale_y if frame.scale_y > 0 else 1.0
    if frame.crop_rect_in_parent is not None:
        iox += float(frame.crop_rect_in_parent[0])
        ioy += float(frame.crop_rect_in_parent[1])
    if len(geom) >= 4:
        x, y, w, h = (float(v) for v in geom[:4])
        if space == "window":
            return (x - ox, y - oy, w, h)
        if space == "image":
            return ((x - ox - iox) / sx, (y - oy - ioy) / sy, w / sx, h / sy)
        return geom
    x, y = float(geom[0]), float(geom[1])
    if space == "window":
        return (x - ox, y - oy)
    if space == "image":
        return ((x - ox - iox) / sx, (y - oy - ioy) / sy)
    return (x, y)


def transform(
    geometry: Geometry,
    from_frame: CoordinateFrame,
    to_frame: CoordinateFrame,
) -> Geometry:
    """Convert point/bbox between frames. Only legal geometric converter."""
    if from_frame.frame_id == to_frame.frame_id and from_frame.space == to_frame.space:
        return geometry
    screen_geom = _to_screen(geometry, from_frame)
    if to_frame.space == "screen":
        return screen_geom
    return _from_screen(screen_geom, to_frame)


def resolve_frame(
    graph: Optional[FrameGraph],
    *,
    frame_id: str = "",
    space: str = "",
) -> CoordinateFrame:
    if graph is not None:
        if frame_id and graph.get(frame_id):
            return graph.get(frame_id)  # type: ignore[return-value]
        if space:
            found = graph.by_space(space)
            if found is not None:
                return found
        if graph.screen_frame_id and graph.get(graph.screen_frame_id):
            return graph.get(graph.screen_frame_id)  # type: ignore[return-value]
    space_n = str(space or "screen").strip().lower()
    if space_n == "image":
        return CoordinateFrame(frame_id="loose_image", space="image")
    if space_n == "window":
        return CoordinateFrame(frame_id="loose_window", space="window")
    return screen_identity_frame()


def ensure_screen_space(
    point: Optional[Sequence[float]],
    bounds: Optional[Sequence[float]],
    *,
    coordinate_space: str,
    frame_id: str = "",
    graph: Optional[FrameGraph] = None,
    surface: Any = None,
) -> Tuple[Optional[Point], Optional[Bounds], Dict[str, Any]]:
    """Normalize to screen; refuse double-transform when already screen-tagged.

    Returns (point, bounds, audit_dict).
    """
    space = str(coordinate_space or "").strip().lower()
    if graph is None and surface is not None:
        graph = frame_graph_from_task_surface(surface)
    src = resolve_frame(graph, frame_id=frame_id, space=space or "image")
    screen = resolve_frame(graph, space="screen")
    audit: Dict[str, Any] = {
        "source_frame_id": src.frame_id,
        "source_space": src.space or space or "unknown",
        "screen_frame_id": screen.frame_id,
        "double_transform_refused": False,
        "geometry_source": space or src.space or "unknown",
    }
    # Hard ban: tagged screen must pass through unchanged.
    if space == "screen":
        audit["double_transform_refused"] = True
        pt = (float(point[0]), float(point[1])) if point and len(point) >= 2 else None
        bd = (
            (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
            if bounds and len(bounds) >= 4
            else None
        )
        audit["window_frame_point"] = list(pt) if pt else None
        audit["global_desktop_point"] = list(pt) if pt else None
        return pt, bd, audit

    pt_out: Optional[Point] = None
    bd_out: Optional[Bounds] = None
    if point is not None and len(point) >= 2:
        g = transform((float(point[0]), float(point[1])), src, screen)
        pt_out = (float(g[0]), float(g[1]))
        audit["source_point"] = [float(point[0]), float(point[1])]
        audit["global_desktop_point"] = list(pt_out)
        # Window-local for the audit chain.
        win = resolve_frame(graph, space="window")
        wpt = transform(pt_out, screen, win)
        audit["window_frame_point"] = [float(wpt[0]), float(wpt[1])]
    if bounds is not None and len(bounds) >= 4:
        g = transform(
            (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3])),
            src,
            screen,
        )
        bd_out = (float(g[0]), float(g[1]), float(g[2]), float(g[3]))
        audit["source_bbox"] = [float(v) for v in bounds[:4]]
        audit["global_desktop_bbox"] = list(bd_out)
    return pt_out, bd_out, audit


def build_geometry_audit(
    *,
    source_point: Optional[Sequence[float]] = None,
    source_bbox: Optional[Sequence[float]] = None,
    source_space: str = "",
    source_frame_id: str = "",
    geometry_source: str = "",
    global_desktop_point: Optional[Sequence[float]] = None,
    motor_event_point: Optional[Sequence[float]] = None,
    window_frame_point: Optional[Sequence[float]] = None,
    intended_vs_landed_px: Optional[float] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Structured pre/post-click geometry audit for the run log."""
    audit: Dict[str, Any] = {
        "source_frame_id": source_frame_id or source_space or "",
        "source_space": source_space,
        "geometry_source": geometry_source,
        "source_point": list(source_point)[:2] if source_point else None,
        "source_bbox": list(source_bbox)[:4] if source_bbox else None,
        "window_frame_point": list(window_frame_point)[:2] if window_frame_point else None,
        "global_desktop_point": list(global_desktop_point)[:2]
        if global_desktop_point
        else None,
        "motor_event_point": list(motor_event_point)[:2] if motor_event_point else None,
        "intended_vs_landed_px": intended_vs_landed_px,
    }
    if extra:
        audit.update(extra)
    return audit


# ---------------------------------------------------------------------------
# Round-trip helpers for goldens
# ---------------------------------------------------------------------------


def roundtrip_error_px(
    point_image: Point,
    *,
    image_size: Sequence[float],
    window_origin: Sequence[float],
    point_scale: float,
    capture_scale: float = 1.0,
) -> float:
    """Image → screen → image error in image pixels (should be ~0)."""
    graph = build_frame_graph(
        image_size=image_size,
        window_origin_in_screen=window_origin,
        point_scale=point_scale,
        capture_scale=capture_scale,
    )
    img = graph.get(graph.image_frame_id)
    scr = graph.get(graph.screen_frame_id)
    assert img and scr
    screen_pt = transform(point_image, img, scr)
    back = transform(screen_pt, scr, img)
    dx = float(back[0]) - float(point_image[0])
    dy = float(back[1]) - float(point_image[1])
    return (dx * dx + dy * dy) ** 0.5
