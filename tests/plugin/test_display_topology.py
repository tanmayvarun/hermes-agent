"""Multi-display topology: image↔screen conversion and off-window refuse."""

from __future__ import annotations

from types import SimpleNamespace

from plugin.agent.actor import brief_from_brain_choice, execute_actor
from plugin.perception.display_topology import (
    TaskSurface,
    attach_task_surface,
    looks_like_image_point,
    point_in_bounds,
    to_screen_point,
)


def _surface_secondary() -> TaskSurface:
    # WhatsApp on display 2 (to the right of a 1920-wide main).
    return TaskSurface(
        app="WhatsApp",
        window_bounds=(1962.0, 39.0, 1581.0, 979.0),
        window_id=1,
        display_index=1,
        display_count=2,
        capture_origin=(1962.0, 39.0),
        capture_scale=1.0,
        point_scale=1.0,
    )


def test_image_point_converts_via_capture_origin():
    surf = _surface_secondary()
    assert looks_like_image_point((790, 500), surf) is True
    assert looks_like_image_point((3417, 947), surf) is False
    assert to_screen_point((790, 500), surf, coordinate_space="image") == (
        1962.0 + 790.0,
        39.0 + 500.0,
    )
    assert to_screen_point((3417, 947), surf, coordinate_space="screen") == (3417.0, 947.0)


def test_point_in_window_detects_primary_miss():
    surf = _surface_secondary()
    assert point_in_bounds((2752, 539), surf.window_bounds) is True
    assert point_in_bounds((790, 500), surf.window_bounds) is False


def test_actor_converts_image_inventory_and_keeps_global_cta():
    surf = _surface_secondary()
    doc = attach_task_surface(
        {
            "surface": "conversation",
            "objects": [
                {
                    "id": "obj_msg",
                    "kind": "message_bubble",
                    "text": "zarooratwala Pallavi",
                    "point": [790, 500],
                    "coordinate_space": "image",
                    "matches_goal": True,
                }
            ],
        },
        surf,
    )
    brief = brief_from_brain_choice(
        {
            "family": "reveal_actions",
            "target_id": "obj_msg",
            "target_label": "zarooratwala Pallavi",
            "target_point": [3417, 947],
            "coordinate_space": "screen",
        },
        doc,
        app="WhatsApp",
        capability="reveal_actions",
    )
    assert brief.point == (3417.0, 947.0)
    cx = brief.bounds[0] + brief.bounds[2] / 2.0
    assert abs(cx - 3417.0) <= 12.0


def test_actor_refuses_click_outside_task_window(monkeypatch):
    from plugin.agent import actor as actor_mod

    def fake_surface(app, **kwargs):
        return _surface_secondary()

    monkeypatch.setattr(
        "plugin.perception.display_topology.build_task_surface", fake_surface
    )
    brief = SimpleNamespace(
        gesture="click",
        app="WhatsApp",
        point=(790.0, 500.0),
        bounds=(778.0, 488.0, 24.0, 24.0),
        label="zarooratwala",
        text="",
        field_role="none",
        open_search_ui=False,
        capability="reveal_actions",
        target_id="x",
        scroll_direction="down",
        scroll_amount=3,
        task_window_bounds=(1962.0, 39.0, 1581.0, 979.0),
        to_dict=lambda: {"gesture": "click", "point": [790, 500]},
    )
    # Bypass validate by patching
    monkeypatch.setattr(actor_mod, "validate_brief", lambda b: (True, "ok"))
    monkeypatch.setattr(actor_mod, "_commit_perception_confirm", lambda *a, **k: None)
    result = execute_actor(brief)
    assert result.ok is False
    assert result.status == "off_task_window"
