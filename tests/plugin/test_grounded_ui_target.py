"""GroundedUiTarget: UI actuation requires geometry on the capability contract."""

from __future__ import annotations

from plugin.agent.capabilities.base import (
    AddressableEntity,
    GroundedCapabilityRequest,
    GroundedUiTarget,
)
from plugin.agent.capabilities.catalog import (
    geometry_required_capabilities,
    spec_by_name,
)
from plugin.agent.decision_consultation import apply_decision_consultation
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.unified_cognition import UnifiedProposal, proposal_to_action
from plugin.worldmodel.model import WorldModel


def _goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )


def test_compose_search_query_spec_requires_geometry():
    spec = spec_by_name("compose_search_query")
    assert spec is not None
    assert spec.requires_geometry is True
    assert "compose_search_query" in geometry_required_capabilities()
    assert "type_query" in geometry_required_capabilities()


def test_grounded_capability_request_asserts_geometry():
    req = GroundedCapabilityRequest(name="compose_search_query", app="WhatsApp")
    try:
        req.assert_grounded()
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "GroundedUiTarget" in str(exc)
    req.target = GroundedUiTarget(label="Search", point=(150.0, 90.0))
    req.assert_grounded()


def test_addressable_entity_exposes_grounded_target():
    ent = AddressableEntity(
        app="WhatsApp",
        label="Pallavi",
        entity_id=7,
        point=(167.0, 175.0),
        coordinate_space="screen",
    )
    gt = ent.grounded_target()
    assert gt.has_geometry()
    assert gt.as_next_action_fields()["target_point"] == [167.0, 175.0]
    assert gt.as_next_action_fields()["coordinate_space"] == "screen"


def test_compose_packs_search_field_geometry_from_world():
    doc = {
        "surface": "chat_list",
        "objects": [
            {
                "id": "search_field",
                "kind": "search_field",
                "text": "Search",
                "point": [150, 90],
            },
            {
                "id": "chat_pallavi",
                "kind": "chat_row",
                "text": "Pallavi",
                "point": [167, 175],
                "matches_goal": True,
            },
        ],
    }
    proposal = UnifiedProposal(
        observed_state={"surface": "chat_list"},
        world_model=doc,
        next_action={"family": "observe"},
        confidence=0.9,
    )

    class _State:
        unified_world_document = doc
        last_surprise_explanation = None
        perception_mode = ""
        last_meta_action = ""
        reflect_corrected_point = None

    class _Chooser:
        def choose(self, system, packet):
            return {
                "capability": "compose_search_query",
                "target": "",
                "why": "need search",
                "confidence": 0.9,
            }

    trace = apply_decision_consultation(
        proposal,
        _goal(),
        features=StateFeatures(extras={"app_content_node_count": 0}),
        execution_state=_State(),
        chooser=_Chooser(),
    )
    assert trace.get("applied") is True
    assert proposal.next_action["family"] == "compose_search_query"
    assert proposal.next_action.get("target_point") == [150, 90]
    assert proposal.next_action.get("target_id") == "search_field"


def test_compose_geometry_from_suggested_actions_when_next_action_empty():
    """Fast-choice leaves next_action empty; CTA geometry lives on suggestions."""
    doc = {
        "surface": "chat_list",
        "objects": [
            {"id": "t0", "kind": "search_field", "text": "search", "matches_goal": True},
        ],
    }
    proposal = UnifiedProposal(
        observed_state={"surface": "chat_list"},
        world_model=doc,
        next_action={},
        suggested_actions=[
            {
                "rank": 1,
                "family": "compose_search_query",
                "text": "search",
                "target_point": [223, 93],
                "bounds": [189.5, 86.9, 67.1, 12.4],
                "coordinate_space": "screen",
                "confidence": 0.75,
                "why": "compact_vlm",
            }
        ],
        confidence=0.75,
    )

    class _State:
        unified_world_document = doc
        last_surprise_explanation = None
        perception_mode = ""
        last_meta_action = ""
        reflect_corrected_point = None

    class _Chooser:
        def choose(self, system, packet):
            return {
                "capability": "compose_search_query",
                "target": "",
                "why": "need search",
                "confidence": 0.9,
            }

    apply_decision_consultation(
        proposal,
        _goal(),
        features=StateFeatures(extras={"app_content_node_count": 0}),
        execution_state=_State(),
        chooser=_Chooser(),
    )
    assert proposal.next_action["family"] == "compose_search_query"
    assert proposal.next_action.get("target_point") == [223.0, 93.0]
    assert proposal.next_action.get("bounds")


def test_screen_coordinate_space_skips_window_transform():
    world = WorldModel(active_app="WhatsApp")
    proposal = UnifiedProposal(
        observed_state={"surface": "chat_list"},
        next_action={
            "family": "open_entity",
            "target_label": "Search",
            "target_point": [223.0, 93.0],
            "coordinate_space": "screen",
        },
        confidence=0.9,
        point_scale=1.0,
        point_origin=(180.0, 56.0),
    )
    action, reason = proposal_to_action(
        proposal, _goal(), world, StateFeatures()
    )
    assert reason == "admissible"
    assert action is not None
    # Must not become (403, 149) via origin+scale.
    assert action.target_point == (223, 93)


def test_entity_screen_bounds_win_over_image_point_transform():
    """Vision entity bounds are screen-space; do not re-apply window origin."""
    from plugin.worldmodel.entities.entity import Entity

    world = WorldModel(active_app="WhatsApp")
    world.entities[900000] = Entity(
        id=900000,
        entity_type="search_field",
        semantic_role="search",
        label="Search",
        role="AXStaticText",
        bounds=(200.0, 80.0, 120.0, 28.0),  # screen; center=(260, 94)
        visible=True,
        confidence=0.9,
        attributes={"source": "vision", "vision_object_id": "search_field"},
    )
    proposal = UnifiedProposal(
        observed_state={"surface": "chat_list"},
        next_action={
            "family": "compose_search_query",
            "text": "zarooratwala",
            "target_label": "Search",
            "target_id": "search_field",
            "target_point": [223.0, 93.0],  # image-space; would become ~403,149
        },
        confidence=0.9,
        point_scale=1.0,
        point_origin=(180.0, 56.0),
    )
    action, reason = proposal_to_action(proposal, _goal(), world, StateFeatures())
    assert reason == "admissible"
    assert action is not None
    assert action.target_point == (260, 94)
    assert action.target_point != (403, 149)
