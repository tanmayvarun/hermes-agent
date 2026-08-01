from __future__ import annotations

from plugin.agent.apps.whatsapp import WhatsAppOverlay
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.perception.representation import PerceptionResult, build_perception_result
from plugin.worldmodel.capability import build_capability_graph
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel
from plugin.worldmodel.scene import WorldGraph, reconstruct_world_graph


def _goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder Ji",
        target_contact="Pallavi",
        link_query="zarooratwala",
        prompt="find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi",
    )


def _world() -> WorldModel:
    world = WorldModel(active_app="WhatsApp", last_window_name="WhatsApp")
    world.entities = {
        1: Entity(
            id=1,
            entity_type="textfield",
            semantic_role="Search",
            label="Search",
            role="AXTextField",
            bounds=(24.0, 24.0, 220.0, 34.0),
            visible=True,
            enabled=True,
            attributes={"value": "Kulvinder"},
        ),
        2: Entity(
            id=2,
            entity_type="static",
            semantic_role="Kulvinder Ji",
            label="Kulvinder Ji",
            role="AXStaticText",
            bounds=(32.0, 154.0, 180.0, 30.0),
            visible=True,
            enabled=True,
        ),
        3: Entity(
            id=3,
            entity_type="static",
            semantic_role="ZarooratWala – Fresh Groceries Delivered",
            label="ZarooratWala – Fresh Groceries Delivered",
            role="AXStaticText",
            bounds=(560.0, 310.0, 360.0, 60.0),
            visible=True,
            enabled=True,
            attributes={"description": "https://www.zarooratwala.com"},
        ),
    }
    scene = reconstruct_world_graph(list(world.entities.values()), app="WhatsApp", source_patch_id="test")
    world.last_scene_graph = scene.to_dict()
    world.last_capability_graph = build_capability_graph(
        scene,
        list(world.entities.values()),
        goal=_goal(),
    ).to_dict()
    return world


def _view() -> dict[str, object]:
    return {
        "app": "WhatsApp",
        "screen": "CONVERSATION",
        "search_visible": True,
        "search_focused": True,
        "search_query": "Kulvinder",
        "window_name": "WhatsApp",
        "visible_contacts": ["Kulvinder Ji"],
        "open_conversation": "Kulvinder Ji",
        "composer_visible": True,
        "conversation_timeline": [
            {
                "message_ids": [3],
                "entity_ids": [3],
                "text": "ZarooratWala – Fresh Groceries Delivered",
                "urls": ["https://www.zarooratwala.com"],
                "label": "ZarooratWala – Fresh Groceries Delivered",
                "description": "https://www.zarooratwala.com",
                "row_count": 1,
                "x": 560.0,
                "y": 310.0,
            }
        ],
        "world_signature": "frame-1",
    }


def test_perception_result_round_trip_and_temporal_diff():
    world = _world()
    goal = _goal()
    features = StateFeatures(
        app="WhatsApp",
        screen_kind="conversation",
        screen_bucket="conversation",
        conversation_open=True,
        has_text_query=True,
        query_matches_goal=True,
        has_named_entity=True,
        worldview_score=0.96,
        mean_belief=0.95,
        extras={
            "conversation_timeline": _view()["conversation_timeline"],
            "screenshot_path": "/tmp/whatsapp.png",
        },
    )

    first = build_perception_result(world, _view(), features, goal=goal)
    restored = PerceptionResult.from_dict(first.to_dict())
    assert restored.transition.status in {"initial", "changed", "stable", "occluded"}
    assert any(sensor.kind == "screenshot" and sensor.available for sensor in restored.sensors)
    assert any(sensor.kind == "accessibility_tree" for sensor in restored.sensors)
    assert restored.surfaces
    assert any(surface.id == "main" for surface in restored.surfaces)
    assert any(obj.kind == "message_cluster" for obj in restored.objects)
    assert "CURRENT STATE" in restored.narrative
    assert restored.transition.belief_patch.appeared_object_ids

    world.entities[4] = Entity(
        id=4,
        entity_type="button",
        semantic_role="Forward",
        label="Forward",
        role="AXButton",
        bounds=(910.0, 318.0, 96.0, 30.0),
        visible=True,
        enabled=True,
    )
    scene = reconstruct_world_graph(list(world.entities.values()), app="WhatsApp", source_patch_id="test-2")
    world.last_scene_graph = scene.to_dict()
    world.last_capability_graph = build_capability_graph(
        scene,
        list(world.entities.values()),
        goal=goal,
    ).to_dict()
    second_view = dict(_view())
    second_view["screen"] = "DIALOG"
    second_view["blocking_overlay"] = True
    second = build_perception_result(world, second_view, features, goal=goal, previous_result=first, action_label="reveal_forward_menu")

    assert second.transition.status == "changed"
    assert any(obj.id == "entity:4" for obj in second.objects)
    assert "TEMPORAL CHANGE" in second.narrative
    assert second.transition.belief_patch.appeared_object_ids
    assert any(sensor.kind == "temporal_memory" for sensor in second.sensors)


def test_whatsapp_overlay_exposes_structured_perception_result():
    world = _world()
    goal = _goal()
    overlay = WhatsAppOverlay()

    feats = overlay.features(world, goal, worldview_score=0.94)
    structured = feats.extras.get("perception_result") or {}

    assert isinstance(structured, dict)
    assert structured.get("narrative")
    assert structured.get("transition", {}).get("belief_patch", {}).get("appeared_object_ids") is not None
    assert structured.get("primary_surface_id") in {"main", "sidebar", "overlay", "base", ""}
