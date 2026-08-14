"""150708: window-scoped capture misses context menus; overlay_display fixes it."""

from __future__ import annotations

from types import SimpleNamespace

from plugin.agent.affordance_frontier import (
    Affordance,
    AffordanceFrontier,
    STATUS_LATENT,
)
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.unified_cognition import expects_overlay_perception
from plugin.agent.world_critic import reconcile_frontier
from plugin.perception.macos.accessibility.observer import (
    resolve_screenshot_capture_mode,
)


def test_default_capture_mode_is_window():
    assert resolve_screenshot_capture_mode(include_overlays=False) == "window"


def test_overlay_expectancy_selects_overlay_display():
    state = ExecutionState()
    state.reveal_handoff = {
        "surface": "context_menu",
        "ttl": 2,
        "incomplete_reveal": True,
    }
    assert expects_overlay_perception(state) is True
    assert (
        resolve_screenshot_capture_mode(
            include_overlays=expects_overlay_perception(state)
        )
        == "overlay_display"
    )


def test_failure_window_pixels_cannot_ground_forward():
    """Failure class: conversation-only objects (what -l capture shows) ⇒ no Forward."""
    state = ExecutionState()
    state.reveal_handoff = {"surface": "context_menu", "ttl": 2, "incomplete_reveal": True}
    frontier = AffordanceFrontier(surface="conversation", latent_actions=[])
    reconcile_frontier(
        frontier,
        document={
            "surface": "conversation",
            "objects": [
                {
                    "text": "https://www.zarooratwala.com/?utm_source=ig...",
                    "kind": "message_bubble",
                    "point": [100, 200],
                },
                {
                    "text": "Forwarded: Chunni ko bhi Prabal se baat karna hai...",
                    "kind": "message_bubble",
                    "point": [100, 300],
                },
            ],
        },
        execution_state=state,
        last_action_family="reveal_actions",
    )
    labels = {a.target_label for a in frontier.observed_actions}
    assert "Forward" not in labels
    assert not any(str(x).lower().startswith("forwarded") for x in labels)


def test_success_overlay_document_promotes_forward_menu():
    from plugin.perception.coordinate_frame import build_frame_graph

    state = ExecutionState()
    state.reveal_handoff = {"surface": "context_menu", "ttl": 2, "incomplete_reveal": True}
    graph = build_frame_graph(
        image_size=(1000.0, 800.0),
        window_origin_in_screen=(0.0, 0.0),
        point_scale=1.0,
        capture_scale=1.0,
        capture_id="c_overlay",
    )
    document = {
        "surface": "conversation",
        "capture_id": "c_overlay",
        "frame_graph": graph.to_dict(),
        "objects": [
            {
                "text": "Forward",
                "kind": "menu_item",
                "is_menu_item": True,
                "point": [3100, 320],
                "coordinate_space": "screen",
                "geometry_source": "ocr",
                "owner_surface": "context_menu",
            },
            {
                "text": "Reply",
                "kind": "menu_item",
                "is_menu_item": True,
                "point": [3100, 280],
                "coordinate_space": "screen",
                "geometry_source": "ocr",
                "owner_surface": "context_menu",
            },
        ],
    }
    state.unified_world_document = document
    state.task_surface = {
        "capture_id": "c_overlay",
        "frame_graph": graph.to_dict(),
    }
    frontier = AffordanceFrontier(
        surface="conversation",
        latent_actions=[
            Affordance(
                id="fwd",
                family="invoke_affordance",
                status=STATUS_LATENT,
                target_label="Forward",
            )
        ],
    )
    reconcile_frontier(
        frontier,
        document=document,
        execution_state=state,
        last_action_family="reveal_actions",
    )
    labels = {a.target_label for a in frontier.observed_actions}
    assert "Forward" in labels
    assert frontier.observed_actions[-1].actuators
    assert state.last_grounded_affordance_set
    assert state.reveal_handoff is None


def test_attach_screenshot_records_overlay_mode(monkeypatch):
    from plugin.perception.macos.accessibility import observer as obs_mod
    from plugin.perception.observation import Observation

    captured = {}

    def fake_capture(*, app_name="WhatsApp", include_overlays=False):
        captured["include_overlays"] = include_overlays
        from plugin.perception.capture_frame import CaptureFrame

        return "/tmp/fake.png", None, CaptureFrame()

    monkeypatch.setattr(obs_mod, "_capture_screen_screenshot", fake_capture)
    stub = Observation(
        timestamp=0.0,
        app_name="WhatsApp",
        window_name="",
        nodes=[],
        source="test",
        coverage=0.0,
        degraded=False,
    )
    out, err = obs_mod.attach_screenshot_to_observation(
        stub, app_name="WhatsApp", include_overlays=True
    )
    assert err is None
    assert captured["include_overlays"] is True
    assert out.meta.get("screenshot_capture_mode") == "overlay_display"
    assert out.meta.get("screenshot_source") == "overlay_display"


def test_live_observe_threads_include_overlays(monkeypatch, tmp_path):
    from pathlib import Path

    from plugin.experiments import live_observe
    from plugin.experiments.logger import EventLogger
    from plugin.perception.observation import AxNode, Observation

    seen = {}

    def fake_fused(app, **kwargs):
        seen.update(kwargs)
        obs = Observation(
            timestamp=0.0,
            app_name=app,
            window_name="",
            nodes=[AxNode(name="x", description="")],
            source="pyobjc_ax",
            coverage=1.0,
            degraded=False,
        )
        return obs, SimpleNamespace(sources=["pyobjc_ax"], agreement=1.0, node_counts={})

    monkeypatch.setattr(
        "plugin.perception.fusion.fuse.observe_fused",
        fake_fused,
    )
    log = EventLogger(path=Path(tmp_path) / "overlay_capture_test.jsonl", also_console=False)
    live_observe._live_observe(
        log, app="WhatsApp", step=1, with_screenshot=True, include_overlays=True
    )
    assert seen.get("include_overlays") is True
    assert seen.get("with_screenshot") is True
