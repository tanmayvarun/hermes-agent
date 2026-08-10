"""CoordinateFrame round-trip and double-transform refusal."""

from plugin.perception.coordinate_frame import (
    build_frame_graph,
    ensure_screen_space,
    frame_graph_from_task_surface,
    roundtrip_error_px,
    transform,
)


def test_image_screen_roundtrip_retina_window():
    err = roundtrip_error_px(
        (200.0, 400.0),
        image_size=(1581.0, 979.0),
        window_origin=(220.0, 25.0),
        point_scale=0.5,  # 2x retina via 1/scale style → use capture
        capture_scale=2.0,
    )
    # With point_scale=0.5: screen = origin + image*0.5; reverse should match.
    assert err < 1e-6


def test_cross_domain_roundtrips_within_few_px():
    cases = [
        # browser button
        ((120.0, 80.0), (1440.0, 900.0), (0.0, 0.0), 1.0, 1.0),
        # Finder file
        ((40.0, 200.0), (1200.0, 800.0), (100.0, 50.0), 1.0, 1.0),
        # WhatsApp message (retina + window offset)
        ((900.0, 240.0), (1581.0, 979.0), (774.0, 25.0), 1.0 / 1.4328125, 1.4328125),
        # system dialog
        ((300.0, 300.0), (800.0, 600.0), (200.0, 100.0), 1.0, 1.0),
    ]
    for pt, size, origin, pscale, cscale in cases:
        err = roundtrip_error_px(
            pt,
            image_size=size,
            window_origin=origin,
            point_scale=pscale,
            capture_scale=cscale,
        )
        assert err < 3.0, (pt, err)


def test_screen_space_refuses_double_transform():
    from plugin.perception.display_topology import TaskSurface

    surface = TaskSurface(
        app="WhatsApp",
        capture_origin=(774.0, 25.0),
        capture_scale=2.0,
        point_scale=1.43,
        window_bounds=(774.0, 25.0, 800.0, 900.0),
    )
    pt, bd, audit = ensure_screen_space(
        (450.0, 230.0),
        None,
        coordinate_space="screen",
        surface=surface,
    )
    assert pt == (450.0, 230.0)
    assert audit.get("double_transform_refused") is True


def test_image_point_projects_with_origin_and_scale():
    graph = build_frame_graph(
        image_size=(1581.0, 979.0),
        window_origin_in_screen=(220.0, 25.0),
        point_scale=1.0,
        capture_scale=2.0,
    )
    # point_scale=1 and capture>1 → scale becomes 1/capture = 0.5
    img = graph.get(graph.image_frame_id)
    scr = graph.get(graph.screen_frame_id)
    assert img and scr
    screen = transform((100.0, 200.0), img, scr)
    assert abs(screen[0] - (220.0 + 50.0)) < 1e-6
    assert abs(screen[1] - (25.0 + 100.0)) < 1e-6


def test_task_surface_adapter():
    from plugin.perception.display_topology import TaskSurface

    g = frame_graph_from_task_surface(
        TaskSurface(
            app="X",
            capture_origin=(10.0, 20.0),
            point_scale=2.0,
            capture_scale=2.0,
        ),
        image_size=(100.0, 100.0),
    )
    assert g.image_frame_id and g.screen_frame_id
