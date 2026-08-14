"""First-class coordinate frames for observation → actuation.

Every geometric object carries a ``Grounding`` with a ``coordinate_frame_id``.
Conversions go only through ``transform()``. Motor landing updates attempt
evidence — it never rewrites object grounding.

Invariants
----------
* CaptureFrame ≠ WindowFrame. Image origin in window and window origin in
  screen are distinct; never equate ``capture_origin`` with window origin
  for ROI / cropped / resized captures.
* Frame graphs are stamped at capture time with stable IDs bound to a
  ``capture_id``. A grounding must not outlive its frame graph.
* Missing / stale frame IDs fail closed on the actuation path
  (``UnknownCoordinateFrame`` / ``StaleCoordinateFrame``).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import uuid

Point = Tuple[float, float]
Bounds = Tuple[float, float, float, float]
Geometry = Union[Point, Bounds]

FRAME_GRAPH_KEY = "frame_graph"
CAPTURE_ID_KEY = "capture_id"


class CoordinateFrameError(Exception):
    """Base for fail-closed geometry errors on the actuation path."""

    code: str = "coordinate_frame_error"

    def __init__(self, message: str = "", *, code: str = "") -> None:
        super().__init__(message or self.code)
        if code:
            self.code = code


class UnknownCoordinateFrame(CoordinateFrameError):
    code = "unknown_coordinate_frame"


class StaleCoordinateFrame(CoordinateFrameError):
    code = "stale_coordinate_frame"


class GroundingUncertain(CoordinateFrameError):
    code = "grounding_uncertain"


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
    capture_id: str = ""

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
            raise UnknownCoordinateFrame("CoordinateFrame.from_dict requires a dict")
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

        fid = str(raw.get("frame_id") or "").strip()
        if not fid:
            raise UnknownCoordinateFrame("CoordinateFrame missing frame_id")
        return cls(
            frame_id=fid,
            space=str(raw.get("space") or "screen").strip().lower(),
            image_size=_xy("image_size"),
            image_origin_in_window=_xy("image_origin_in_window"),
            window_origin_in_screen=_xy("window_origin_in_screen"),
            crop_rect_in_parent=crop_t,
            scale_x=float(raw.get("scale_x") or 1.0) or 1.0,
            scale_y=float(raw.get("scale_y") or raw.get("scale_x") or 1.0) or 1.0,
            backing_scale=float(raw.get("backing_scale") or 1.0) or 1.0,
            parent_frame_id=str(raw.get("parent_frame_id") or ""),
            capture_id=str(raw.get("capture_id") or ""),
        )


@dataclass
class Grounding:
    """Authoritative geometry for a semantic object — never motor landing."""

    coordinate_frame_id: str
    point: Optional[Point] = None
    bbox: Optional[Bounds] = None
    provenance: str = ""
    confidence: float = 0.0
    capture_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "coordinate_frame_id": self.coordinate_frame_id,
            "point": list(self.point) if self.point else None,
            "bbox": list(self.bbox) if self.bbox else None,
            "provenance": self.provenance,
            "confidence": round(float(self.confidence), 3),
            "capture_id": self.capture_id,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> Optional["Grounding"]:
        """Parse grounding. Missing frame_id → None (fail closed at act time)."""
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
        fid = str(raw.get("coordinate_frame_id") or raw.get("frame_id") or "").strip()
        if not fid:
            # Never invent "screen" — actionable geometry requires a frame id.
            return None
        if not point and not bbox:
            return None
        return cls(
            coordinate_frame_id=fid,
            point=point,
            bbox=bbox,
            provenance=str(raw.get("provenance") or ""),
            confidence=float(raw.get("confidence") or 0.0),
            capture_id=str(raw.get("capture_id") or ""),
        )


@dataclass
class FrameGraph:
    """Active frames for one observation (image → window → screen)."""

    frames: Dict[str, CoordinateFrame] = field(default_factory=dict)
    image_frame_id: str = ""
    window_frame_id: str = ""
    screen_frame_id: str = ""
    capture_id: str = ""

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
            "capture_id": self.capture_id,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> Optional["FrameGraph"]:
        """Parse a graph. Does not certify actuation readiness — call
        ``validate_for_actuation()`` before motor use.
        """
        if not isinstance(raw, dict) or not raw.get("frames"):
            return None
        frames: Dict[str, CoordinateFrame] = {}
        for k, v in (raw.get("frames") or {}).items():
            try:
                frames[str(k)] = CoordinateFrame.from_dict(v)
            except CoordinateFrameError:
                continue
        if not frames:
            return None
        return cls(
            frames=frames,
            image_frame_id=str(raw.get("image_frame_id") or ""),
            window_frame_id=str(raw.get("window_frame_id") or ""),
            screen_frame_id=str(raw.get("screen_frame_id") or ""),
            capture_id=str(raw.get("capture_id") or ""),
        )

    def validate_for_actuation(self) -> "FrameGraph":
        """Authoritative validity: required frames, parent chain, spaces, scales.

        Partially corrupt graphs (e.g. image+screen without window) must not
        become trusted actuation topology.
        """
        img = self.get(self.image_frame_id) or self.by_space("image")
        win = self.get(self.window_frame_id) or self.by_space("window")
        scr = self.get(self.screen_frame_id) or self.by_space("screen")
        if img is None or win is None or scr is None:
            raise UnknownCoordinateFrame(
                "FrameGraph incomplete for actuation — need image, window, screen"
            )
        if img.space != "image" or win.space != "window" or scr.space != "screen":
            raise UnknownCoordinateFrame(
                f"FrameGraph space mismatch: image={img.space!r} "
                f"window={win.space!r} screen={scr.space!r}"
            )
        if img.parent_frame_id and img.parent_frame_id != win.frame_id:
            raise UnknownCoordinateFrame(
                f"image.parent={img.parent_frame_id!r} != window={win.frame_id!r}"
            )
        if win.parent_frame_id and win.parent_frame_id != scr.frame_id:
            raise UnknownCoordinateFrame(
                f"window.parent={win.parent_frame_id!r} != screen={scr.frame_id!r}"
            )
        for fr in (img, win, scr):
            if not (float(fr.scale_x) > 0.0 and float(fr.scale_y) > 0.0):
                raise UnknownCoordinateFrame(
                    f"non-positive scale on frame {fr.frame_id!r}"
                )
            if float(fr.scale_x) != float(fr.scale_x) or float(fr.scale_y) != float(
                fr.scale_y
            ):
                raise UnknownCoordinateFrame(f"NaN scale on frame {fr.frame_id!r}")
        cid = str(self.capture_id or "").strip()
        for fr in (img, win, scr):
            fcid = str(fr.capture_id or "").strip()
            if cid and fcid and fcid != cid:
                raise StaleCoordinateFrame(
                    f"frame {fr.frame_id!r} capture_id={fcid!r} != graph={cid!r}"
                )
        # Normalize resolved ids onto the graph for downstream resolve_frame.
        self.image_frame_id = img.frame_id
        self.window_frame_id = win.frame_id
        self.screen_frame_id = scr.frame_id
        if not self.capture_id:
            self.capture_id = (
                str(img.capture_id or win.capture_id or scr.capture_id or "").strip()
            )
        return self


def assert_grounding_fresh(grounding: Grounding, graph: FrameGraph) -> None:
    """Entity geometry is ephemeral to its capture — refuse cross-capture motors.

    Semantic identity (EntityRef) may survive capture c42→c43; Grounding must not.
    """
    if grounding is None or graph is None:
        raise GroundingUncertain("assert_grounding_fresh requires grounding and graph")
    g_cid = str(grounding.capture_id or "").strip()
    graph_cid = str(graph.capture_id or "").strip()
    if not g_cid or not graph_cid:
        raise GroundingUncertain(
            "missing capture_id on Grounding or FrameGraph — re-ground"
        )
    if g_cid != graph_cid:
        raise StaleCoordinateFrame(
            f"Grounding.capture_id={g_cid!r} != active FrameGraph.capture_id="
            f"{graph_cid!r} — re-ground"
        )


def new_capture_id() -> str:
    return f"c_{uuid.uuid4().hex[:10]}"


def frame_id_for_space(
    graph: Optional["FrameGraph"],
    coordinate_space: str,
) -> str:
    """FrameGraph frame_id for ``coordinate_space``, or \"\" if unknown.

    Never invents a frame. Screen geometry must not receive the image frame id
    (and vice versa).
    """
    if graph is None:
        return ""
    space = str(coordinate_space or "").strip().lower()
    if space == "screen":
        fid = str(getattr(graph, "screen_frame_id", "") or "").strip()
        if fid:
            return fid
        fr = graph.by_space("screen")
        return str(fr.frame_id if fr is not None else "") or ""
    if space == "image":
        fid = str(getattr(graph, "image_frame_id", "") or "").strip()
        if fid:
            return fid
        fr = graph.by_space("image")
        return str(fr.frame_id if fr is not None else "") or ""
    if space == "window":
        fid = str(getattr(graph, "window_frame_id", "") or "").strip()
        if fid:
            return fid
        fr = graph.by_space("window")
        return str(fr.frame_id if fr is not None else "") or ""
    return ""


def resolve_frame_id_for_space(
    *,
    frame_id: str = "",
    coordinate_space: str = "",
    graph: Optional["FrameGraph"] = None,
) -> str:
    """Keep ``frame_id`` only when it matches ``coordinate_space``.

    Missing stamp → FrameGraph fallback for that space. Wrong-space stamp →
    empty (fail closed). Never copies a generic document frame onto geometry.
    """
    space = str(coordinate_space or "").strip().lower()
    if space not in {"screen", "image", "window"}:
        return ""
    expected = frame_id_for_space(graph, space)
    fid = str(frame_id or "").strip()
    if not fid:
        return expected
    if graph is not None:
        fr = graph.get(fid)
        if fr is not None:
            if str(fr.space or "").strip().lower() == space:
                return fid
            return ""  # impossible pairing: e.g. image frame on screen geometry
        # Unknown id not in graph — refuse rather than trust a generic stamp.
        return ""
    # No graph: allow only space-suffixed / desktop screen identity forms.
    low = fid.lower()
    if f"/{space}" in low:
        return fid
    if space == "screen" and low in {"desktop:current", "screen"}:
        return fid
    return ""


def new_frame_id(space: str = "frame", *, capture_id: str = "") -> str:
    """Stable-within-capture frame id: ``capture:<id>/<space>`` when possible."""
    cid = str(capture_id or "").strip()
    sp = str(space or "frame").strip().lower() or "frame"
    if cid:
        return f"capture:{cid}/{sp}"
    return f"{sp}_{uuid.uuid4().hex[:8]}"


def screen_identity_frame(*, capture_id: str = "") -> CoordinateFrame:
    fid = "desktop:current" if not capture_id else f"capture:{capture_id}/screen"
    return CoordinateFrame(
        frame_id=fid,
        space="screen",
        capture_id=capture_id,
    )


def build_frame_graph(
    *,
    image_size: Sequence[float] = (0.0, 0.0),
    window_origin_in_screen: Sequence[float] = (0.0, 0.0),
    image_origin_in_window: Sequence[float] = (0.0, 0.0),
    capture_scale: float = 1.0,
    point_scale: float = 1.0,
    backing_scale: float = 1.0,
    crop_rect_in_parent: Optional[Sequence[float]] = None,
    capture_id: str = "",
) -> FrameGraph:
    """Build image/window/screen frames. Capture ≠ window ≠ screen.

    ``window_origin_in_screen`` — task window top-left in global desktop points.
    ``image_origin_in_window`` — where the captured image's (0,0) sits inside
    the window (0,0 for full-window capture; nonzero for ROI / crop).
    ``crop_rect_in_parent`` — optional crop in the parent (window) space.
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
        # Crop implies image origin in window unless explicitly set.
        if iox == 0.0 and ioy == 0.0:
            iox, ioy = crop[0], crop[1]
    cid = str(capture_id or new_capture_id())
    screen = CoordinateFrame(
        frame_id=new_frame_id("screen", capture_id=cid),
        space="screen",
        window_origin_in_screen=(wox, woy),
        backing_scale=float(backing_scale or 1.0),
        capture_id=cid,
    )
    window = CoordinateFrame(
        frame_id=new_frame_id("window", capture_id=cid),
        space="window",
        window_origin_in_screen=(wox, woy),
        scale_x=1.0,
        scale_y=1.0,
        backing_scale=float(backing_scale or 1.0),
        parent_frame_id=screen.frame_id,
        capture_id=cid,
    )
    image = CoordinateFrame(
        frame_id=new_frame_id("image", capture_id=cid),
        space="image",
        image_size=(iw, ih),
        image_origin_in_window=(iox, ioy),
        window_origin_in_screen=(wox, woy),
        crop_rect_in_parent=crop,
        scale_x=sx,
        scale_y=sy,
        backing_scale=float(backing_scale or cs or 1.0),
        parent_frame_id=window.frame_id,
        capture_id=cid,
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
        capture_id=cid,
    )


def frame_graph_from_capture_artifact(
    *,
    capture_id: str = "",
    image_size: Sequence[float] = (0.0, 0.0),
    window_origin_in_screen: Sequence[float] = (0.0, 0.0),
    image_origin_in_window: Sequence[float] = (0.0, 0.0),
    capture_scale: float = 1.0,
    point_scale: float = 1.0,
    backing_scale: float = 1.0,
    crop_rect_in_parent: Optional[Sequence[float]] = None,
) -> FrameGraph:
    """Authoritative builder for capture-time stamping.

    Producers must pass window origin and image-in-window origin separately.
    """
    return build_frame_graph(
        image_size=image_size,
        window_origin_in_screen=window_origin_in_screen,
        image_origin_in_window=image_origin_in_window,
        capture_scale=capture_scale,
        point_scale=point_scale,
        backing_scale=backing_scale,
        crop_rect_in_parent=crop_rect_in_parent,
        capture_id=capture_id or new_capture_id(),
    )


def frame_graph_from_task_surface(
    surface: Any,
    *,
    image_size: Sequence[float] = (0.0, 0.0),
) -> FrameGraph:
    """Legacy adapter: TaskSurface → FrameGraph.

    Prefer a stamped ``frame_graph`` on the surface/document. When reconstructing,
    treat ``capture_origin`` as *window* origin only when no explicit window
    origin or image-in-window origin is present (full-window uncropped case).
    ROI captures must supply ``image_origin_in_window`` / ``crop_rect``.
    """
    if surface is None:
        return build_frame_graph(image_size=image_size)

    # Prefer already-stamped graph.
    if isinstance(surface, dict):
        stamped = FrameGraph.from_dict(surface.get("frame_graph"))
        if stamped is not None:
            return stamped
        window_origin = (
            surface.get("window_origin_in_screen")
            or surface.get("window_origin")
            or surface.get("capture_origin")
            or (0.0, 0.0)
        )
        image_origin = surface.get("image_origin_in_window") or (0.0, 0.0)
        crop = surface.get("crop_rect_in_parent") or surface.get("crop_rect")
        return build_frame_graph(
            image_size=image_size or surface.get("image_size") or (0.0, 0.0),
            window_origin_in_screen=window_origin,
            image_origin_in_window=image_origin,
            capture_scale=float(surface.get("capture_scale") or 1.0),
            point_scale=float(surface.get("point_scale") or 1.0),
            backing_scale=float(surface.get("backing_scale") or surface.get("capture_scale") or 1.0),
            crop_rect_in_parent=crop,
            capture_id=str(surface.get("capture_id") or ""),
        )

    stamped_obj = getattr(surface, "frame_graph", None)
    if isinstance(stamped_obj, FrameGraph):
        return stamped_obj
    if isinstance(stamped_obj, dict):
        g = FrameGraph.from_dict(stamped_obj)
        if g is not None:
            return g

    window_origin = getattr(surface, "window_origin_in_screen", None) or getattr(
        surface, "capture_origin", (0.0, 0.0)
    )
    image_origin = getattr(surface, "image_origin_in_window", (0.0, 0.0))
    crop = getattr(surface, "crop_rect_in_parent", None)
    return build_frame_graph(
        image_size=image_size,
        window_origin_in_screen=window_origin,
        image_origin_in_window=image_origin,
        capture_scale=float(getattr(surface, "capture_scale", 1.0) or 1.0),
        point_scale=float(getattr(surface, "point_scale", 1.0) or 1.0),
        backing_scale=float(
            getattr(surface, "backing_scale", None)
            or getattr(surface, "capture_scale", 1.0)
            or 1.0
        ),
        crop_rect_in_parent=crop,
        capture_id=str(getattr(surface, "capture_id", "") or ""),
    )


def _to_screen(geom: Geometry, frame: CoordinateFrame) -> Geometry:
    """Map geometry from ``frame`` into global screen points."""
    space = frame.space
    if space == "screen":
        return geom
    ox, oy = frame.window_origin_in_screen
    iox, ioy = frame.image_origin_in_window
    sx = frame.scale_x if frame.scale_x > 0 else 1.0
    sy = frame.scale_y if frame.scale_y > 0 else 1.0
    if frame.crop_rect_in_parent is not None and (iox, ioy) == (0.0, 0.0):
        # Prefer explicit image_origin; crop only adds when origin unset.
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
    if frame.crop_rect_in_parent is not None and (iox, ioy) == (0.0, 0.0):
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
    fail_closed: bool = True,
) -> CoordinateFrame:
    """Resolve a frame. Actuation paths must use ``fail_closed=True`` (default)."""
    fid = str(frame_id or "").strip()
    if graph is not None and fid:
        found = graph.get(fid)
        if found is not None:
            return found
        # Same capture, different space alias (capture:c42/image vs space).
        if space:
            by_sp = graph.by_space(space)
            if by_sp is not None and (
                not by_sp.capture_id
                or not graph.capture_id
                or by_sp.capture_id == graph.capture_id
            ):
                # Requested id missing but space exists on this capture — stale id.
                raise StaleCoordinateFrame(
                    f"frame_id={fid!r} missing; space={space!r} present on capture "
                    f"{graph.capture_id!r} — re-ground"
                )
        raise StaleCoordinateFrame(
            f"frame_id={fid!r} not in active FrameGraph capture={graph.capture_id!r}"
        )

    if graph is not None and space:
        found = graph.by_space(space)
        if found is not None:
            return found

    if fail_closed:
        if fid:
            raise UnknownCoordinateFrame(f"unknown frame_id={fid!r}")
        if space:
            raise UnknownCoordinateFrame(
                f"no FrameGraph for space={space!r}; stamp at capture time"
            )
        raise UnknownCoordinateFrame("missing frame_id and FrameGraph")

    # Ingestion-boundary legacy only.
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
    coordinate_space: str = "",
    frame_id: str = "",
    graph: Optional[FrameGraph] = None,
    surface: Any = None,
    fail_closed: bool = True,
    grounding_capture_id: str = "",
) -> Tuple[Optional[Point], Optional[Bounds], Dict[str, Any]]:
    """Normalize to screen; refuse double-transform when already screen-tagged.

    Actuation: require ``frame_id`` or a stamped graph + known space. Unknown
    provenance raises ``GroundingUncertain`` / ``UnknownCoordinateFrame``.
    When ``grounding_capture_id`` is set, it must match the active graph.
    """
    space = str(coordinate_space or "").strip().lower()
    fid = str(frame_id or "").strip()

    if graph is None and surface is not None:
        # Prefer stamped graph on surface/document.
        if isinstance(surface, dict) and surface.get("frame_graph"):
            graph = FrameGraph.from_dict(surface.get("frame_graph"))
        else:
            stamped = getattr(surface, "frame_graph", None)
            if isinstance(stamped, FrameGraph):
                graph = stamped
            elif isinstance(stamped, dict):
                graph = FrameGraph.from_dict(stamped)
            elif not fail_closed:
                graph = frame_graph_from_task_surface(surface)

    # Hard ban: tagged screen with no conflicting frame passes through.
    if space == "screen" and (not fid or (graph and graph.get(fid) and graph.get(fid).space == "screen")):
        g_cid = str(grounding_capture_id or "").strip()
        if fail_closed and graph is not None and g_cid:
            graph.validate_for_actuation()
            assert_grounding_fresh(
                Grounding(
                    coordinate_frame_id=fid or graph.screen_frame_id,
                    point=(float(point[0]), float(point[1]))
                    if point and len(point) >= 2
                    else None,
                    capture_id=g_cid,
                ),
                graph,
            )
        audit: Dict[str, Any] = {
            "source_frame_id": fid or (graph.screen_frame_id if graph else "screen"),
            "source_space": "screen",
            "screen_frame_id": graph.screen_frame_id if graph else "desktop:current",
            "capture_id": graph.capture_id if graph else "",
            "grounding_capture_id": g_cid,
            "double_transform_refused": True,
            "geometry_source": "screen",
        }
        pt = (float(point[0]), float(point[1])) if point and len(point) >= 2 else None
        bd = (
            (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
            if bounds and len(bounds) >= 4
            else None
        )
        audit["window_frame_point"] = list(pt) if pt else None
        audit["global_desktop_point"] = list(pt) if pt else None
        return pt, bd, audit

    if fail_closed and graph is None:
        raise GroundingUncertain(
            "no FrameGraph on actuation path — stamp at capture; do not invent frames"
        )
    if fail_closed and graph is not None:
        graph.validate_for_actuation()
        g_cid = str(grounding_capture_id or "").strip()
        if g_cid:
            assert_grounding_fresh(
                Grounding(
                    coordinate_frame_id=fid or graph.image_frame_id,
                    point=(float(point[0]), float(point[1]))
                    if point and len(point) >= 2
                    else None,
                    capture_id=g_cid,
                ),
                graph,
            )
    if fail_closed and not fid and space not in {"image", "window", "screen"}:
        raise GroundingUncertain(
            "actionable geometry missing coordinate_frame_id and coordinate_space"
        )

    src = resolve_frame(
        graph,
        frame_id=fid,
        space=space or ("image" if not fail_closed else ""),
        fail_closed=fail_closed,
    )
    screen = resolve_frame(
        graph,
        frame_id=(graph.screen_frame_id if graph else ""),
        space="screen",
        fail_closed=fail_closed,
    )
    audit = {
        "source_frame_id": src.frame_id,
        "source_space": src.space or space or "unknown",
        "screen_frame_id": screen.frame_id,
        "capture_id": (graph.capture_id if graph else src.capture_id),
        "grounding_capture_id": str(grounding_capture_id or ""),
        "double_transform_refused": False,
        "geometry_source": space or src.space or "unknown",
    }

    pt_out: Optional[Point] = None
    bd_out: Optional[Bounds] = None
    if point is not None and len(point) >= 2:
        g = transform((float(point[0]), float(point[1])), src, screen)
        pt_out = (float(g[0]), float(g[1]))
        audit["source_point"] = [float(point[0]), float(point[1])]
        audit["global_desktop_point"] = list(pt_out)
        if graph is not None:
            win = resolve_frame(
                graph, frame_id=graph.window_frame_id, space="window", fail_closed=False
            )
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


def roundtrip_error_px(
    point_image: Point,
    *,
    image_size: Sequence[float],
    window_origin: Sequence[float],
    point_scale: float,
    capture_scale: float = 1.0,
    image_origin_in_window: Sequence[float] = (0.0, 0.0),
) -> float:
    """Image → screen → image error in image pixels (should be ~0)."""
    graph = build_frame_graph(
        image_size=image_size,
        window_origin_in_screen=window_origin,
        image_origin_in_window=image_origin_in_window,
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
