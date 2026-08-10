"""Unit tests for the actor motor-brief contract."""

from __future__ import annotations

from types import SimpleNamespace

from plugin.agent.actor import (
    STALE_PRECONDITION,
    ActorBrief,
    RecordingMotor,
    brief_from_brain_choice,
    brief_from_plan_step,
    exec_backend_for_actor_result,
    execute_actor,
    infer_field_role,
    validate_brief,
)
from plugin.perception.continuity import ContinuityVerdict, FOCUS_DISTURBED


def test_validate_destination_filter_requires_geometry():
    ok, why = validate_brief(
        ActorBrief(
            gesture="type",
            text="Tanmay",
            field_role="destination_filter",
            open_search_ui=False,
        )
    )
    assert not ok
    assert "without_geometry" in why


def test_validate_compose_search_query_requires_geometry():
    ok, why = validate_brief(
        ActorBrief(
            gesture="type",
            text="zarooratwala",
            field_role="sidebar_search",
            open_search_ui=True,
            capability="compose_search_query",
        )
    )
    assert not ok
    assert why == "compose_search_query_without_geometry"


def test_validate_strips_open_search_ui_when_geometry_present():
    """Legacy open_search_ui flag must not block a grounded type brief."""
    ok, why = validate_brief(
        ActorBrief(
            gesture="type",
            text="Tanmay",
            point=(10.0, 20.0),
            field_role="destination_filter",
            open_search_ui=True,
        )
    )
    assert ok, why


def test_actor_never_invents_search_geometry_from_world():
    """Brain omitted id/label/point — actor must not latch the first search_field."""
    brief = brief_from_brain_choice(
        {"family": "compose_search_query", "text": "zarooratwala"},
        {
            "surface": "chat_list",
            "objects": [
                {
                    "id": "search_field",
                    "kind": "search_field",
                    "text": "Search",
                    "point": [150, 90],
                },
            ],
        },
        app="WhatsApp",
    )
    assert brief.point is None
    assert brief.bounds is None
    ok, why = validate_brief(brief)
    assert not ok
    assert "without_geometry" in why


def test_actor_keeps_ax_search_point_when_vlm_objects_are_only_rows():
    """Live 123746: plan_step has Q Search@[160,107]; chat_row inventory must not drop it."""
    step = SimpleNamespace(
        action_family="compose_search_query",
        action="ComposeSearchQuery",
        text="zarooratwala",
        semantic_target="Q Search",
        target_entity_id=5,
        target_point=[160, 107],
        scroll_direction="",
        scroll_amount=0,
    )
    brief = brief_from_plan_step(
        step,
        {
            "surface": "chat_list",
            "objects": [
                {
                    "id": "pallavi_row",
                    "kind": "chat_row",
                    "text": "Pallavi",
                    "matches_goal": True,
                    "point": [207, 291],
                }
            ],
        },
        app="WhatsApp",
    )
    assert brief.point is not None
    assert abs(brief.point[0] - 160.0) < 1.0
    assert abs(brief.point[1] - 107.0) < 1.0
    ok, why = validate_brief(brief)
    assert ok, why


def test_actor_keeps_q_search_when_first_chat_row_within_pad():
    """Live 215556: first chat_row ~80px under Search must not strip filter chrome."""
    brief = brief_from_brain_choice(
        {
            "family": "compose_search_query",
            "text": "zarooratwala Pallavi",
            "target_label": "Q Search",
            "target_point": [228, 93],
            "geometry_source": "ax_plan_step",
        },
        {
            "surface": "chat_list",
            "objects": [
                {
                    "id": "row1",
                    "kind": "chat_row",
                    "text": "14/146",
                    "point": [250, 160],
                }
            ],
        },
        app="WhatsApp",
        capability="compose_search_query",
    )
    assert brief.point is not None
    assert abs(brief.point[0] - 228.0) < 1.0
    assert abs(brief.point[1] - 93.0) < 1.0
    ok, why = validate_brief(brief)
    assert ok, why


def test_execute_type_records_open_search_ui_false():
    motor = RecordingMotor()
    brief = ActorBrief(
        gesture="type",
        app="WhatsApp",
        text="Tanmay",
        point=(420.0, 180.0),
        field_role="destination_filter",
        open_search_ui=False,
    )
    result = execute_actor(brief, motor=motor)
    assert result.ok
    assert result.status == "executed"
    assert motor.calls[0]["op"] == "type"
    assert motor.calls[0]["open_search_ui"] is False
    assert motor.calls[0]["bounds"] is not None


def test_incomplete_brief_never_calls_motor():
    motor = RecordingMotor()
    result = execute_actor(
        ActorBrief(gesture="click", label="Pallavi"),
        motor=motor,
    )
    assert not result.ok
    assert result.status == "incomplete_brief"
    assert motor.calls == []


def test_handoff_picker_type_binds_filter_geometry():
    brief = brief_from_brain_choice(
        {
            "family": "type_query",
            "text": "Tanmay",
            "target_label": "Search",
            "coordinate_space": "screen",
        },
        {
            "surface": "forward_picker",
            "objects": [
                {
                    "id": "f1",
                    "kind": "search_field",
                    "text": "Search",
                    "point": [420, 180],
                    "coordinate_space": "screen",
                },
                {"id": "c1", "kind": "contact_row", "text": "Tanmay", "point": [300, 400]},
            ],
        },
        app="WhatsApp",
    )
    assert brief.field_role == "destination_filter"
    assert brief.open_search_ui is False
    assert brief.point == (420.0, 180.0)
    ok, _ = validate_brief(brief)
    assert ok


def test_handoff_reveal_prefers_content_kind():
    brief = brief_from_brain_choice(
        {
            "family": "reveal_actions",
            "target_label": "zarooratwala",
            "coordinate_space": "screen",
        },
        {
            "surface": "conversation",
            "objects": [
                {"id": "row", "kind": "chat_row", "text": "Pallavi", "point": [100, 100]},
                {
                    "id": "msg",
                    "kind": "message_link_preview",
                    "text": "zarooratwala link",
                    "point": [1575, 295],
                    "matches_goal": True,
                    "coordinate_space": "screen",
                },
            ],
        },
    )
    assert brief.gesture == "context_click"
    assert brief.target_id == "msg"
    assert brief.point == (1575.0, 295.0)


def test_infer_field_role_surfaces():
    assert infer_field_role("forward_picker", "type_query") == "destination_filter"
    assert infer_field_role("chat_list", "compose_search_query") == "sidebar_search"
    assert infer_field_role("conversation", "locate_content") == "in_chat_find"
    # Live 095344: open chat leftover must still type into sidebar Search.
    assert infer_field_role("conversation", "compose_search_query") == "sidebar_search"


def test_compose_on_conversation_does_not_latch_contact_or_into_name():
    """Live 095344: target Pallavi + contact id must not become into=Pallavi."""
    motor = RecordingMotor()
    brief = brief_from_brain_choice(
        {
            "family": "compose_search_query",
            "text": "zarooratwala Pallavi",
            "target_label": "Pallavi",
            "target_id": "900000",
            "target_point": [2127, 363],
            "coordinate_space": "screen",
        },
        {
            "surface": "conversation",
            "open_conversation": "Pallavi",
            "objects": [
                {
                    "id": "search_field",
                    "kind": "search_field",
                    "text": "Search",
                    "point": [150, 90],
                    "coordinate_space": "screen",
                },
                {
                    "id": "900000",
                    "kind": "contact",
                    "text": "Pallavi",
                    "point": [2127, 363],
                    "coordinate_space": "screen",
                },
            ],
        },
        app="WhatsApp",
    )
    assert brief.label == "Search"
    assert brief.field_role == "sidebar_search"
    assert brief.target_id == "search_field"
    assert brief.point == (150.0, 90.0)
    result = execute_actor(brief, motor=motor)
    assert result.ok
    assert motor.calls[0]["into"] == "Search"


def test_brief_from_plan_step():
    step = SimpleNamespace(
        action_family="type_query",
        action="type",
        text="Tanmay",
        semantic_target="Search",
        target_entity_id="",
        target_point=(420.0, 180.0),
        scroll_direction=None,
        scroll_amount=None,
    )
    brief = brief_from_plan_step(
        step,
        {"surface": "forward_picker", "objects": []},
        app="WhatsApp",
    )
    assert brief.gesture == "type"
    assert brief.field_role == "destination_filter"
    assert brief.open_search_ui is False
    assert brief.point == (420.0, 180.0)


def test_actor_perception_confirm_refuses_before_motor(monkeypatch):
    """Actor commit transaction uses perception confirm; no write when invalid."""
    monkeypatch.setenv("HERMES_ACTION_GUARD", "1")
    from plugin.perception import continuity as cont

    monkeypatch.setattr(
        cont,
        "guard_click",
        lambda *a, **k: ContinuityVerdict(
            state=FOCUS_DISTURBED,
            reason="something else is at the target now — expected pallavi, found 'raman'",
            may_commit=False,
        ),
    )
    motor = RecordingMotor()
    result = execute_actor(
        ActorBrief(
            gesture="click",
            app="WhatsApp",
            label="Pallavi",
            point=(167.0, 175.0),
            capability="open_entity",
        ),
        motor=motor,
    )
    assert not result.ok
    assert result.status == STALE_PRECONDITION
    assert "perception_invalid" in result.message
    assert result.evidence.get("perception_confirm", {}).get("valid") is False
    assert motor.calls == []
    assert exec_backend_for_actor_result(result) == STALE_PRECONDITION


def test_actor_perception_confirm_passes_then_motors(monkeypatch):
    monkeypatch.setenv("HERMES_ACTION_GUARD", "1")
    from plugin.perception import continuity as cont
    from plugin.perception.continuity import CONFIRMED

    monkeypatch.setattr(
        cont,
        "guard_click",
        lambda *a, **k: ContinuityVerdict(
            state=CONFIRMED, reason="ok", may_commit=True
        ),
    )
    motor = RecordingMotor()
    result = execute_actor(
        ActorBrief(
            gesture="click",
            app="WhatsApp",
            label="Pallavi",
            point=(167.0, 175.0),
        ),
        motor=motor,
    )
    assert result.ok
    assert result.status == "executed"
    assert len(motor.calls) == 1
    assert result.evidence.get("perception_confirm") == "passed"
    assert exec_backend_for_actor_result(result) == "actor"


def test_actor_refuses_point_outside_bounds_scope(monkeypatch):
    """Cross-pane brief (point in content, bounds on list) must not motor."""
    monkeypatch.setenv("HERMES_ACTION_GUARD", "0")
    motor = RecordingMotor()
    result = execute_actor(
        ActorBrief(
            gesture="context_click",
            app="WhatsApp",
            label="https://example.com/item",
            point=(1233.0, 241.0),
            bounds=(280.0, 220.0, 80.0, 40.0),  # list band — far from point
            capability="reveal_actions",
        ),
        motor=motor,
    )
    assert not result.ok
    assert result.status == "geometry_mismatch"
    assert motor.calls == []
