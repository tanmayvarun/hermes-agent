"""Perceived rectangles must be expressed in the space the pointer acts in.

These tests exist because of a silent, total failure. Perception grabs the task
app's *window* on a Retina display, so its screenshot is offset by the window's
origin and twice the scale of the screen. Nothing converted those pixels back to
screen points, so every vision-derived click landed somewhere else.

The failure was invisible from the outside. The mouse moved, no error was
raised, and the log read ``click 'Kulvinder Ji' center=(251, 393) via entity
bounds`` — a plausible-looking success. The click hit empty space, the app did
not change, and the agent concluded the control had not worked and tried again,
forever. A live run measured the entity at (169, 377, 164, 33) while the text
was really at (86, 231, 81, 14): width and height exactly doubled, origin short
by the window's corner.

The regression these guard is therefore not "the numbers are slightly off" but
"the agent cannot act on anything it sees".
"""

from __future__ import annotations

from plugin.perception.capture_frame import CaptureFrame, frame_from_meta
from plugin.perception.observation import Observation


# The real measurement from the live run, kept as the canonical case.
WINDOW_BOUNDS_POINTS = (1.5, 42.5, 164.0, 33.0)
OBSERVED_PIXEL_BBOX = (169.0, 377.0, 164.0, 33.0)
TRUE_SCREEN_POINT_ORIGIN = (86.0, 231.0)


def test_a_retina_window_capture_is_measured_at_two_pixels_per_point():
    frame = CaptureFrame.measure(328.0, (1.5, 42.5, 164.0, 33.0))
    assert frame.scale == 2.0
    assert (frame.origin_x, frame.origin_y) == (1.5, 42.5)


def test_the_scale_is_measured_not_assumed():
    """A window on a non-Retina display is 1x while the main display is 2x."""
    assert CaptureFrame.measure(400.0, (0.0, 0.0, 400.0, 300.0)).scale == 1.0
    assert CaptureFrame.measure(800.0, (0.0, 0.0, 400.0, 300.0)).scale == 2.0


def test_a_near_integral_scale_snaps():
    """`screencapture -o` trims a pixel or two of shadow; that must not drift the far edge."""
    frame = CaptureFrame.measure(801.0, (0.0, 0.0, 400.0, 300.0))
    assert frame.scale == 2.0


def test_the_live_failure_converts_back_to_the_measured_truth():
    frame = CaptureFrame(origin_x=1.5, origin_y=42.5, scale=2.0)
    x, y, w, h = frame.bbox_to_screen(OBSERVED_PIXEL_BBOX)
    assert (x, y) == TRUE_SCREEN_POINT_ORIGIN
    # Doubling is undone; the residual on h is OCR's own box padding, not units.
    assert w == 82.0
    assert abs(h - 14.0) < 3.0


def test_a_point_carries_the_window_origin_not_just_the_scale():
    """Scaling alone leaves every click short by the window offset."""
    frame = CaptureFrame(origin_x=1.5, origin_y=42.5, scale=2.0)
    assert frame.point_to_screen(0.0, 0.0) == (1.5, 42.5)
    assert frame.point_to_screen(200.0, 400.0) == (101.5, 242.5)


def test_an_unknown_transform_is_the_identity():
    """An unconverted path must behave exactly as it did before this existed."""
    assert frame_from_meta(None).is_identity
    assert frame_from_meta({}).is_identity
    assert frame_from_meta({"capture_frame": "nonsense"}).is_identity
    identity = CaptureFrame()
    assert identity.bbox_to_screen((5.0, 6.0, 7.0, 8.0)) == (5.0, 6.0, 7.0, 8.0)


def test_a_full_screen_capture_has_no_offset():
    frame = CaptureFrame.measure(3024.0, (0.0, 0.0, 1512.0, 982.0))
    assert (frame.origin_x, frame.origin_y) == (0.0, 0.0)
    assert frame.scale == 2.0


def test_ocr_boxes_are_converted_when_the_observation_carries_a_transform():
    """The one place OCR geometry becomes world geometry is where it must convert."""
    from plugin.perception.ocr.base import OCRSpan
    from plugin.perception.ocr.recovery import _spans_to_nodes

    span = OCRSpan(text="Kulvinder Ji", bbox=OBSERVED_PIXEL_BBOX, confidence=0.9, engine="test")
    frame = CaptureFrame(origin_x=1.5, origin_y=42.5, scale=2.0)

    nodes = _spans_to_nodes([span], engine_id="test", frame=frame)

    assert len(nodes) == 1
    assert nodes[0].bbox[0] == TRUE_SCREEN_POINT_ORIGIN[0]
    assert nodes[0].bbox[1] == TRUE_SCREEN_POINT_ORIGIN[1]


def test_ocr_boxes_pass_through_untouched_without_a_transform():
    """Fixture-driven offline observations have no window and no scaling."""
    from plugin.perception.ocr.base import OCRSpan
    from plugin.perception.ocr.recovery import _spans_to_nodes

    span = OCRSpan(text="Kulvinder Ji", bbox=(10.0, 20.0, 30.0, 40.0), confidence=0.9, engine="t")
    nodes = _spans_to_nodes([span], engine_id="t")
    assert nodes[0].bbox == (10.0, 20.0, 30.0, 40.0)


def test_the_world_model_remembers_the_transform_with_the_screenshot():
    """Re-deriving it later would race the window being moved or resized."""
    from plugin.worldmodel.model import WorldModel

    world = WorldModel(active_app="WhatsApp")
    obs = Observation(
        timestamp=0.0,
        app_name="WhatsApp",
        window_name="WhatsApp",
        nodes=[],
        screenshot_path="/tmp/shot.png",
        meta={"capture_frame": {"origin_x": 1.5, "origin_y": 42.5, "scale": 2.0}},
    )
    world.ingest(obs)

    assert CaptureFrame.from_dict(world.last_capture_frame).scale == 2.0
    assert CaptureFrame.from_dict(world.last_capture_frame).origin_y == 42.5


def test_the_model_downscale_and_the_retina_scale_compose():
    """Two reductions separate the model's picture from the screen; both must be undone."""
    import plugin.agent.unified_cognition as uc

    class _Img:
        width = 1600

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import PIL.Image

    original = PIL.Image.open
    PIL.Image.open = lambda *a, **k: _Img()
    try:
        # A 1600px-wide Retina capture (800 points) shown to the model at 800px:
        # each model unit is 2 image pixels, and each point is 2 pixels, so one
        # model unit is exactly one point.
        scale = uc.screen_point_scale("/tmp/x.png", 800, CaptureFrame(scale=2.0))
        assert scale == 1.0
        # Shown at 400px instead: one model unit is 4 pixels = 2 points.
        assert uc.screen_point_scale("/tmp/x.png", 400, CaptureFrame(scale=2.0)) == 2.0
    finally:
        PIL.Image.open = original


def test_a_model_point_lands_on_screen_through_scale_and_origin():
    from plugin.agent.unified_cognition import _to_screen_point

    assert _to_screen_point([100, 200], 2.0, (1.5, 42.5)) == (202, 442)
    # Without an origin the same point is short by the window corner.
    assert _to_screen_point([100, 200], 2.0) == (200, 400)


def test_fusion_carries_the_capture_transform_and_ocr_read():
    """Merging what is on screen must not discard measurements of the frame.

    Fusion reconciles competing accounts of the *contents*. The pixel-to-point
    transform and the OCR read are not accounts of anything -- they are
    measurements of the capture itself -- and the fused observation was
    dropping both. With no transform the world fell back to the identity, so
    every vision coordinate was scaled by 2.67 instead of 1.34 and a click
    aimed at a message resolved to (2271, 1550) on a 1710x1107 display, off the
    screen entirely. With no OCR read there was nothing to measure against, so
    coordinates could only ever be the model's guess.
    """
    from plugin.perception.fusion.engine import get_fusion_engine
    from plugin.perception.observation import AxNode, Observation
    from plugin.perception.sources.base import ObservationBundle

    ax = Observation(
        timestamp=0.0,
        app_name="WhatsApp",
        window_name="WhatsApp",
        nodes=[AxNode(role="AXButton", name="Search", bbox=(10.0, 10.0, 40.0, 20.0))],
        screenshot_path="/tmp/shot.png",
        meta={"capture_frame": {"origin_x": 0.0, "origin_y": 39.0, "scale": 2.0}},
    )
    ocr = Observation(
        timestamp=0.0,
        app_name="WhatsApp",
        window_name="WhatsApp",
        nodes=[AxNode(role="AXStaticText", name="Kulvinder Ji", bbox=(90.0, 228.0, 71.0, 19.0))],
        screenshot_path="/tmp/shot.png",
        source="screen2ax:visionkit",
        meta={"ocr": {"lines": [{"text": "Kulvinder Ji", "bounds": [90.0, 228.0, 71.0, 19.0]}]}},
    )

    frame = get_fusion_engine().fuse_bundles(
        [
            ObservationBundle(source_id="pyobjc_ax", observation=ax, coverage_self=0.6),
            ObservationBundle(source_id="screen2ax", observation=ocr, coverage_self=0.6),
        ],
        app="WhatsApp",
    )
    meta = frame.to_observation().meta

    assert meta.get("capture_frame") == {"origin_x": 0.0, "origin_y": 39.0, "scale": 2.0}
    assert meta.get("ocr", {}).get("lines"), "the OCR read must survive fusion"
    # And the fusion report is still there beside them.
    assert meta.get("fused_frame") is True


def test_the_world_learns_the_transform_from_a_fused_observation():
    """The end of the same wire: it has to reach the world, not just the meta."""
    from plugin.perception.capture_frame import CaptureFrame
    from plugin.perception.observation import AxNode, Observation
    from plugin.worldmodel.model import WorldModel

    world = WorldModel(active_app="WhatsApp")
    world.ingest(
        Observation(
            timestamp=0.0,
            app_name="WhatsApp",
            window_name="WhatsApp",
            nodes=[AxNode(role="AXStaticText", name="Kulvinder Ji", bbox=(90.0, 228.0, 71.0, 19.0))],
            screenshot_path="/tmp/shot.png",
            source="fused:pyobjc_ax+screen2ax",
            meta={
                "fused_frame": True,
                "capture_frame": {"origin_x": 0.0, "origin_y": 39.0, "scale": 2.0},
                "ocr": {"lines": [{"text": "Kulvinder Ji", "bounds": [90.0, 228.0, 71.0, 19.0]}]},
            },
        )
    )

    assert CaptureFrame.from_dict(world.last_capture_frame).scale == 2.0
    assert CaptureFrame.from_dict(world.last_capture_frame).origin_y == 39.0
    assert world.last_ocr_lines and world.last_ocr_lines[0]["text"] == "Kulvinder Ji"
