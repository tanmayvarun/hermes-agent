"""Action-area contracts: bind capabilities to legal UI regions."""

from __future__ import annotations

from plugin.agent.actor import (
    ActorBrief,
    RecordingMotor,
    brief_from_brain_choice,
    execute_actor,
    validate_brief,
)
from plugin.agent.capabilities.action_area import (
    ActionArea,
    contract_for,
    object_matches_area,
    validate_actuation_grounding,
)
from plugin.agent.decision_consultation import _ground_choice_on_world


def test_filter_contract_rejects_contact_and_composer_kinds():
    c = contract_for("compose_search_query")
    assert c is not None
    assert c.area == ActionArea.FILTER_INPUT
    assert object_matches_area({"kind": "search_field", "text": "Search"}, c)
    assert not object_matches_area({"kind": "contact", "text": "Alice"}, c)
    assert not object_matches_area({"kind": "composer", "text": "Type a message"}, c)


def test_validate_refuses_high_cost_wrong_area_before_motor():
    ok, why = validate_actuation_grounding(
        capability="compose_search_query",
        field_role="sidebar_search",
        label="Type a message",
        target_kind="composer",
    )
    assert not ok
    assert "wrong_action_area" in why

    brief = ActorBrief(
        gesture="type",
        capability="type_query",
        field_role="destination_filter",
        label="Alice",
        text="Alice",
        point=(800.0, 400.0),
        target_kind="contact",
    )
    vok, vwhy = validate_brief(brief)
    assert not vok
    assert "wrong_action_area" in vwhy
    motor = RecordingMotor()
    result = execute_actor(brief, motor=motor)
    assert not result.ok
    assert motor.calls == []


def test_ground_choice_exclusive_filter_ignores_matches_goal_contact():
    grounded = _ground_choice_on_world(
        {
            "surface": "conversation",
            "objects": [
                {"id": "f1", "kind": "search_field", "text": "Search", "point": [10, 20]},
                {
                    "id": "c1",
                    "kind": "contact",
                    "text": "Alice",
                    "matches_goal": True,
                    "point": [800, 400],
                },
            ],
        },
        "compose_search_query",
        "Alice",
    )
    assert grounded.get("target_id") == "f1"
    assert grounded.get("target_point") == [10, 20]


def test_handoff_strips_contact_cta_when_no_filter_in_world():
    brief = brief_from_brain_choice(
        {
            "family": "compose_search_query",
            "text": "find tokens",
            "target_label": "Alice",
            "target_id": "c1",
            "target_point": [800, 400],
        },
        {
            "surface": "conversation",
            "objects": [
                {"id": "c1", "kind": "contact", "text": "Alice", "point": [800, 400]},
                {"id": "comp", "kind": "composer", "text": "Type a message", "point": [900, 900]},
            ],
        },
        app="GenericApp",
    )
    assert brief.point is None
    ok, why = validate_brief(brief)
    assert not ok
    assert "without_geometry" in why
