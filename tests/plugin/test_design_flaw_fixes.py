"""Pins the design-flaw fixes from the zarooratwala 131748 postmortem."""

from __future__ import annotations

from plugin.agent.controller import (
    _action_has_geometry,
    _actuation_available,
    _invalidate_geometry_for_surface_change,
    _note_failed_motor,
)
from plugin.agent.executive.meta_action import MetaAction, MetaChoice
from plugin.agent.executive.sufficiency import SufficiencyInputs, assess_sufficiency
from plugin.agent.runtime.state import ExecutionState, RuntimeState
from plugin.agent.world_document import _normalize_objects
from plugin.worldmodel.model import WorldModel


def test_sufficiency_requires_grounded_action():
    verdict = assess_sufficiency(
        SufficiencyInputs(has_grounded_action=False, coverage=0.9)
    )
    assert verdict.sufficient_to_act is False
    assert "no grounded" in verdict.reason


def test_sufficiency_true_only_with_geometry_bearing_action():
    verdict = assess_sufficiency(
        SufficiencyInputs(has_grounded_action=True, coverage=0.9)
    )
    assert verdict.sufficient_to_act is True


def test_actuation_available_requires_geometry():
    rt = RuntimeState(world_model=WorldModel(active_app="WhatsApp"))
    rt.execution_state.last_unified_proposal = {
        "next_action": {"family": "reveal_actions", "target_label": "link"},
    }

    class _F:
        extras = {}

    assert _actuation_available(rt, _F()) is False
    rt.execution_state.last_unified_proposal = {
        "next_action": {
            "family": "reveal_actions",
            "target_label": "link",
            "target_point": [100, 200],
        },
    }
    assert _actuation_available(rt, _F()) is True


def test_actuation_available_from_openable_source_row():
    from plugin.worldmodel.entities.entity import Entity

    rt = RuntimeState(world_model=WorldModel(active_app="WhatsApp"))
    rt.world_model.entities = {
        1: Entity(
            id=1,
            entity_type="static",
            semantic_role="Pallavi",
            label="Pallavi",
            role="AXStaticText",
            visible=True,
            bounds=(40, 200, 220, 40),
        )
    }

    class _F:
        extras = {
            "forward_phase": "OPEN_SOURCE",
            "source_conversation_visible": True,
            "forward_task": {
                "derived_phase": "OPEN_SOURCE",
                "bindings": {
                    "source_conversation": {"constraints": {"name": "Pallavi"}},
                },
                "predicates": {"source_conversation_visible": True},
            },
        }

    assert _actuation_available(rt, _F()) is True


def test_surface_change_invalidates_geometry():
    rt = RuntimeState(world_model=WorldModel(active_app="WhatsApp"))
    rt.execution_state.last_accepted_surface = "chat_list"
    rt.execution_state.last_unified_proposal = {
        "next_action": {
            "family": "reveal_actions",
            "target_point": [305, 240],
        },
        "surface": "chat_list",
    }
    changed = _invalidate_geometry_for_surface_change(
        rt, surface="conversation", reason="test"
    )
    assert changed is True
    na = rt.execution_state.last_unified_proposal["next_action"]
    assert "target_point" not in na
    assert rt.execution_state.geometry_generation == 1


def test_failed_motor_recorded_for_avoid():
    rt = RuntimeState(world_model=WorldModel(active_app="WhatsApp"))
    _note_failed_motor(
        rt, family="reveal_actions", target="https://z.com", point=[305, 240]
    )
    assert "reveal_actions|" in rt.execution_state.last_failed_motor_key
    assert rt.execution_state.avoid_motor_keys


def test_information_gathering_wants_observe():
    choice = MetaChoice(MetaAction.THINK, "test")
    assert choice.observe_wanted is True
    assert choice.suppress_observe is False


def test_normalize_objects_keeps_bounds_and_coordinate_space():
    objs = _normalize_objects(
        [
            {
                "id": "search_field",
                "kind": "search_field",
                "text": "Search",
                "point": [150, 90],
                "bounds": [100, 70, 200, 40],
                "coordinate_space": "screen",
            }
        ],
        frame=1,
    )
    assert objs[0]["bounds"] == [100.0, 70.0, 200.0, 40.0]
    assert objs[0]["coordinate_space"] == "screen"


def test_action_has_geometry_helper():
    assert _action_has_geometry({"target_point": [1, 2]})
    assert _action_has_geometry({"bounds": [0, 0, 10, 10]})
    assert not _action_has_geometry({"family": "open_entity"})


def test_reconcile_prefers_inventory_when_perceptor_disagrees():
    from plugin.agent.decision_consultation import _reconcile_perceptor_with_inventory

    document = {
        "objects": [
            {
                "id": "msg_1",
                "kind": "message",
                "text": "https://zarooratwala.com",
                "point": [1356, 420],
                "bounds": [1200, 400, 300, 40],
                "coordinate_space": "screen",
            }
        ]
    }
    world_geo = {
        "target_id": "msg_1",
        "target_label": "https://zarooratwala.com",
        "target_point": [1356, 420],
        "bounds": [1200, 400, 300, 40],
        "coordinate_space": "screen",
    }
    perc_geo = {"target_point": [305, 240], "target_label": "https://zarooratwala.com"}
    out = _reconcile_perceptor_with_inventory(world_geo, perc_geo, document)
    assert out["geometry_source"] == "inventory"
    assert out["target_point"] == [1356.0, 420.0]


def test_prediction_error_does_not_rearm_after_reflect_consume():
    """Meta surprise stays disarmed; effect judgment stays honest (154356)."""
    from plugin.agent.controller import _effect_was_absent, _prediction_was_contradicted
    from plugin.agent.unified_cognition import note_prediction_error, UnifiedProposal

    class _State:
        unified_last_expectation = {"surface": "search", "likely_controls": ["Search"]}
        last_prediction_error = {
            "matched": False,
            "effect_absent": True,
            "consumed_by_reflect": True,
            "surprise_armed": False,
            "predicted_surface": "search",
        }

    state = _State()
    proposal = UnifiedProposal(
        world_model={"surface": "conversation", "objects": []},
        confidence=0.5,
    )
    err = note_prediction_error(state, proposal)
    # Judgment: effect still absent.
    assert err.get("matched") is False
    assert err.get("effect_absent") is True
    # Meta latch: do not re-arm surprise on the same predicted surface.
    assert err.get("suppressed_rearm") is True
    assert err.get("surprise_armed") is False
    state.last_prediction_error = err
    assert _prediction_was_contradicted(state) is False
    assert _effect_was_absent(state) is True


def test_ig_exhausted_is_an_executive_act_decision():
    """Retreat budget spent → meta chooses ACT; loop does not rewrite after."""
    from plugin.agent.executive.hierarchy import decision_ladder
    from plugin.agent.executive.meta_action import MetaAction, MetaContext

    choice = decision_ladder(
        MetaContext(
            branch_stale=True,
            information_gathering_exhausted=True,
            has_grounded_action=False,
        )
    )
    assert choice.action is MetaAction.ACT
    assert choice.scores.get("retreat_exhausted") == 1.0


def test_perceive_streak_is_capped_for_meta_not_silent_act():
    from plugin.agent.controller import _MAX_CONSECUTIVE_PERCEIVES
    from plugin.agent.executive.hierarchy import decision_ladder
    from plugin.agent.executive.meta_action import MetaAction, MetaContext
    from plugin.agent.runtime.state import ExecutionState

    assert _MAX_CONSECUTIVE_PERCEIVES == 2
    state = ExecutionState()
    assert getattr(state, "consecutive_perceives", None) == 0
    # With streak exhausted and a grounded move, executive chooses ACT.
    choice = decision_ladder(
        MetaContext(
            has_grounded_action=True,
            perceive_streak_exhausted=True,
            branch_stale=False,
        )
    )
    assert choice.action is MetaAction.ACT


def test_named_object_wins_over_conflicting_brain_point():
    from plugin.agent.actor import brief_from_brain_choice

    brief = brief_from_brain_choice(
        {
            "family": "reveal_actions",
            "target_id": "msg_1",
            "target_label": "https://zarooratwala.com",
            "target_point": [305, 240],
        },
        {
            "surface": "conversation",
            "objects": [
                {
                    "id": "msg_1",
                    "kind": "message",
                    "text": "https://zarooratwala.com",
                    "point": [1356, 420],
                    "bounds": [1200, 400, 300, 40],
                    "coordinate_space": "screen",
                }
            ],
        },
        capability="reveal_actions",
    )
    assert brief.point == (1356.0, 420.0)
