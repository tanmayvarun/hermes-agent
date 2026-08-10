"""Task-conditioned ROI crop + honest point remapping for unified perception."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from plugin.agent.features import StateFeatures
from plugin.agent.unified_cognition import (
    _encode_perception_image,
    _phase_from_features,
    _to_screen_point,
    resolve_phase_roi,
    screen_point_scale,
)
from plugin.perception.capture_frame import CaptureFrame


def test_open_source_roi_is_sidebar_band():
    box = resolve_phase_roi("OPEN_SOURCE", 1000, 800)
    assert box == (70, 0, 420, 800)


def test_find_link_roi_is_main_pane():
    box = resolve_phase_roi("FIND_LINK", 1000, 800)
    assert box == (420, 0, 1000, 800)


def test_pick_dest_roi_is_main_pane():
    box = resolve_phase_roi("PICK_DEST", 1000, 800)
    assert box == (420, 0, 1000, 800)


def test_open_forward_uses_vertical_neighborhood_when_focus_known():
    box = resolve_phase_roi("OPEN_FORWARD", 1000, 800, focus_y_px=400.0)
    assert box is not None
    left, top, right, bottom = box
    assert left == 420
    assert right == 1000
    assert top < 400 < bottom
    assert (bottom - top) >= 180


def test_unknown_phase_is_full_window():
    assert resolve_phase_roi("DONE", 1000, 800) is None
    assert resolve_phase_roi("", 1000, 800) is None


def test_phase_from_features_reads_forward_task():
    feats = StateFeatures(
        extras={"forward_task": {"derived_phase": "OPEN_SOURCE"}},
    )
    assert _phase_from_features(feats) == "OPEN_SOURCE"
    feats2 = StateFeatures(extras={"forward_phase": "FIND_LINK"})
    assert _phase_from_features(feats2) == "FIND_LINK"


def test_encode_applies_crop_then_width_cap(tmp_path: Path):
    path = tmp_path / "shot.png"
    Image.new("RGB", (2000, 1000), color=(40, 40, 40)).save(path)
    data_url, size, crop, nbytes = _encode_perception_image(
        str(path),
        crop_box=(140, 0, 840, 1000),
        max_width=640,
    )
    assert data_url.startswith("data:image/jpeg;base64,")
    assert crop == (140, 0, 840, 1000)
    assert size[0] == 640
    assert nbytes > 0


def test_roi_point_remap_uses_crop_width_and_origin(tmp_path: Path):
    """A model point in the cropped image must land on the correct screen point."""
    path = tmp_path / "shot.png"
    # 1600px wide Retina capture of an 800pt window.
    Image.new("RGB", (1600, 1000), color=(10, 10, 10)).save(path)
    capture = CaptureFrame(origin_x=10.0, origin_y=40.0, scale=2.0)
    crop = resolve_phase_roi("OPEN_SOURCE", 1600, 1000)
    assert crop is not None
    _url, size, applied, _n = _encode_perception_image(
        str(path), crop_box=crop, max_width=640
    )
    assert applied is not None
    source_w = applied[2] - applied[0]
    scale = screen_point_scale(
        str(path), size[0], capture, source_width_px=source_w
    )
    origin = (
        capture.origin_x + applied[0] / capture.scale,
        capture.origin_y + applied[1] / capture.scale,
    )
    # Model (0,0) is the crop's top-left in screen points.
    assert _to_screen_point([0, 0], scale, origin) == (
        round(origin[0]),
        round(origin[1]),
    )
    # Mid-crop in model space should sit inside the sidebar band on screen.
    mid = _to_screen_point([size[0] / 2, 100], scale, origin)
    assert mid is not None
    assert origin[0] < mid[0] < capture.origin_x + (applied[2] / capture.scale)
