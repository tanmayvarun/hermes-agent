"""Open click: VLM point wins over disagreeing AX bounds; failures repair."""

from __future__ import annotations

from types import SimpleNamespace

from plugin.agent.action import Action
from plugin.agent.actor import brief_from_brain_choice
from plugin.agent.controller import _note_open_source_failure
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import RuntimeState
from plugin.agent.unified_cognition import UnifiedProposal, proposal_to_action
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel


def test_actor_prefers_brain_point_when_object_bounds_disagree():
    """011539: brain [270,143] must not click AX fragment center (138,142)."""
    brief = brief_from_brain_choice(
        {
            "family": "open_entity",
            "target_label": "Pallavi - J/ zarooratwala Pallavi",
            "target_id": "pallavi_row",
            "target_point": [270, 143],
            "coordinate_space": "screen",
        },
        {
            "surface": "chat_list",
            "objects": [
                {
                    "id": "pallavi_row",
                    "kind": "chat_row",
                    "text": "Pallavi - J/ zarooratwala Pallavi",
                    "point": [270, 143],
                    "bounds": [100, 130, 76, 24],  # center ≈ (138, 142)
                    "matches_goal": True,
                }
            ],
        },
        app="WhatsApp",
    )
    assert brief.point == (270.0, 143.0)
    assert brief.bounds is not None
    cx = brief.bounds[0] + brief.bounds[2] / 2.0
    cy = brief.bounds[1] + brief.bounds[3] / 2.0
    assert abs(cx - 270.0) <= 12.0
    assert abs(cy - 143.0) <= 12.0


def test_open_entity_cta_wins_over_calls_rail_inventory_point():
    """012852: inventory [130,140] hit Calls; CTA [270,143] is the chat row."""
    brief = brief_from_brain_choice(
        {
            "family": "open_entity",
            "target_label": "Pallavi | ✓✓ zarooratwala Pallavi",
            "target_id": "obj_pallavi_row",
            "target_point": [270, 143],
            "coordinate_space": "screen",
        },
        {
            "surface": "chat_list",
            "objects": [
                {
                    "id": "obj_pallavi_row",
                    "kind": "chat_row",
                    "text": "Pallavi | ✓✓ zarooratwala Pallavi",
                    "point": [130, 140],  # Calls / left-rail mispoint
                    "matches_goal": True,
                }
            ],
        },
        app="WhatsApp",
        capability="open_entity",
    )
    assert brief.point == (270.0, 143.0)
    assert brief.bounds is not None
    cx = brief.bounds[0] + brief.bounds[2] / 2.0
    cy = brief.bounds[1] + brief.bounds[3] / 2.0
    assert abs(cx - 270.0) <= 12.0
    assert abs(cy - 143.0) <= 12.0


def test_proposal_to_action_keeps_screen_vlm_point_over_disagreeing_entity():
    world = WorldModel(active_app="WhatsApp")
    ent = Entity(
        id=6,
        entity_type="static",
        semantic_role="Pallavi|",
        label="Pallavi|",
        role="AXStaticText",
        bounds=(100.0, 130.0, 76.0, 24.0),  # center 138,142
        actions=[],
        attributes={},
        visible=True,
    )
    world.entities = {6: ent}
    proposal = UnifiedProposal(
        world_model={"surface": "chat_list", "open_conversation": "", "objects": []},
        observed_state={"surface": "chat_list"},
        next_action={
            "family": "open_entity",
            "target_label": "Pallavi - J/ zarooratwala Pallavi",
            "target_id": 6,
            "target_point": [270, 143],
            "coordinate_space": "screen",
        },
        confidence=0.95,
        expected_transition={"surface": "conversation"},
    )
    action, reason = proposal_to_action(
        proposal,
        Goal(kind="whatsapp_forward_message", contact="Pallavi"),
        world,
    )
    assert action is not None, reason
    assert action.target_point == (270, 143)


def test_open_source_failure_invalidates_and_escalates_to_search():
    runtime = RuntimeState()
    runtime.world_model = WorldModel(active_app="WhatsApp")
    runtime.world_model.overlay_hints = {}
    runtime.execution_state.unified_perception_cache = {"phash": 1, "parsed": {}}
    decision = Action(
        action="OpenEntity",
        action_family="open_entity",
        semantic_target="Pallavi",
        target_entity_id=6,
        target_point=(138.0, 142.0),
    )
    r1 = _note_open_source_failure(runtime, decision, reason="no_transition")
    assert r1["attempts"] == 1
    assert r1["prefer"] == "vlm_point"
    assert 6 in r1["failed_entity_ids"]
    assert runtime.execution_state.must_executive_reperceive is True
    assert runtime.execution_state.unified_perception_cache == {}

    r2 = _note_open_source_failure(runtime, decision, reason="still_closed")
    assert r2["attempts"] == 2
    assert r2["prefer"] == "compose_search_query"
    assert runtime.world_model.overlay_hints["open_repair"]["prefer"] == "compose_search_query"


def test_reveal_actor_keeps_global_screen_cta_over_image_inventory_point():
    """014321: inventory [790,500] must not beat decision [3417,947] on display 2."""
    brief = brief_from_brain_choice(
        {
            "family": "reveal_actions",
            "target_label": "zarooratwala Pallavi 12:33 AM",
            "target_id": "obj_msg_zarooratwala",
            "target_point": [3417, 947],
            "coordinate_space": "screen",
        },
        {
            "surface": "conversation",
            "task_surface": {
                "app": "WhatsApp",
                "window_bounds": [1962.0, 39.0, 1581.0, 979.0],
                "display_index": 1,
                "display_count": 2,
                "capture_origin": [1962.0, 39.0],
                "capture_scale": 1.0,
                "point_scale": 1.0,
            },
            "objects": [
                {
                    "id": "obj_msg_zarooratwala",
                    "kind": "message_bubble",
                    "text": "zarooratwala Pallavi 12:33 AM",
                    "point": [790, 500],  # image-space
                    "matches_goal": True,
                }
            ],
        },
        app="WhatsApp",
        capability="reveal_actions",
    )
    assert brief.point == (3417.0, 947.0)
    assert brief.bounds is not None
    cx = brief.bounds[0] + brief.bounds[2] / 2.0
    cy = brief.bounds[1] + brief.bounds[3] / 2.0
    assert abs(cx - 3417.0) <= 12.0
    assert abs(cy - 947.0) <= 12.0


def test_reveal_uses_bound_pane_object_not_sidebar_vlm_point():
    """013229: reveal kept [320,160]/entity 7 while source_object was pane message."""
    world = WorldModel(active_app="WhatsApp")
    sidebar = Entity(
        id=7,
        entity_type="static",
        semantic_role="J/ zarooratwala Pallavi|",
        label="J/ zarooratwala Pallavi|",
        role="AXStaticText",
        bounds=(249.0, 154.0, 142.0, 12.0),
        actions=[],
        attributes={},
        visible=True,
    )
    pane = Entity(
        id=80,
        entity_type="static",
        semantic_role="zarooratwala Pallavi",
        label="zarooratwala Pallavi",
        role="AXStaticText",
        bounds=(1588.0, 922.0, 129.0, 13.0),
        actions=[],
        attributes={},
        visible=True,
    )
    window = Entity(
        id=1,
        entity_type="window",
        semantic_role="WhatsApp",
        label="WhatsApp",
        role="AXWindow",
        bounds=(105.0, 25.0, 1710.0, 979.0),
        actions=[],
        attributes={},
        visible=True,
    )
    world.entities = {1: window, 7: sidebar, 80: pane}
    world.overlay_hints = {
        "forward_task": {
            "bindings": {
                "source_object": {
                    "resolved_entity_id": 80,
                    "candidate_entity_ids": [80],
                    "status": "provisional",
                }
            }
        }
    }
    proposal = UnifiedProposal(
        world_model={"surface": "conversation", "open_conversation": "Pallavi", "objects": []},
        observed_state={"surface": "conversation"},
        next_action={
            "family": "reveal_actions",
            "target_label": "zarooratwala Pallavi",
            "target_id": 7,
            "target_point": [320, 160],
            "coordinate_space": "screen",
        },
        confidence=1.0,
        expected_transition={"surface": "context_menu"},
    )
    action, reason = proposal_to_action(
        proposal,
        Goal(
            kind="whatsapp_forward_message",
            contact="Pallavi",
            target_contact="Tanmay",
            link_query="zarooratwala",
        ),
        world,
    )
    assert action is not None, reason
    assert action.target_entity_id == 80
    assert action.target_point is not None
    assert abs(float(action.target_point[0]) - 1652.5) <= 8.0
    assert abs(float(action.target_point[1]) - 928.5) <= 8.0


def test_open_repair_clears_when_source_conversation_opens():
    from plugin.agent.apps.whatsapp import build_forward_task_state
    from plugin.agent.whatsapp_view import WhatsAppWorldView

    world = WorldModel(active_app="WhatsApp")
    world.overlay_hints = {
        "open_repair": {"attempts": 2, "prefer": "compose_search_query", "failed_entity_ids": [6]}
    }
    view = WhatsAppWorldView(
        screen="CONVERSATION",
        open_conversation="Pallavi",
        search_query="",
    )
    build_forward_task_state(
        Goal(kind="whatsapp_forward_message", contact="Pallavi", target_contact="Tanmay", link_query="zarooratwala"),
        world,
        view,
        leftover=False,
    )
    assert "open_repair" not in (world.overlay_hints or {})
