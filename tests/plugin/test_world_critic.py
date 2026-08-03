"""World critic: propose/review residual updates + surface-gated remaps."""

from __future__ import annotations

from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.unified_cognition import (
    UnifiedProposal,
    persist_world_document,
    proposal_to_action,
)
from plugin.agent.world_critic import (
    critique_world_proposal,
    sidebar_search_forbidden,
)
from plugin.worldmodel.model import WorldModel


def _goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )


def test_critic_rejects_illegal_jump_to_search_from_picker():
    prior = {
        "surface": "forward_picker",
        "open_conversation": "Pallavi",
        "focused_field_role": "destination_filter",
    }
    proposal = {
        "surface": "search",
        "open_conversation": "",
        "objects": [],
    }
    verdict = critique_world_proposal(prior, proposal, last_action="type_query")
    assert verdict.surface == "forward_picker"
    assert verdict.accepted_document["open_conversation"] == "Pallavi"
    assert verdict.focused_field_role == "destination_filter"
    assert verdict.forbid_sidebar_search_motor
    assert any(d.field == "surface" and d.verdict == "reject" for d in verdict.decisions)


def test_critic_accepts_forward_picker_after_invoke():
    prior = {"surface": "conversation", "open_conversation": "Pallavi"}
    proposal = {"surface": "forward_picker", "open_conversation": "Pallavi"}
    verdict = critique_world_proposal(
        prior, proposal, last_action="invoke_affordance"
    )
    assert verdict.surface == "forward_picker"
    assert verdict.focused_field_role == "destination_filter"
    assert verdict.forbid_source_compose_remap


def test_persist_world_document_stores_critic_verdict():
    state = ExecutionState()
    state.unified_world_document = {
        "surface": "forward_picker",
        "open_conversation": "Pallavi",
    }
    state.last_action = "type_query"
    proposal = UnifiedProposal(
        world_model={"surface": "search", "open_conversation": ""},
        observed_state={"surface": "search"},
        confidence=0.9,
    )
    persist_world_document(state, proposal)
    assert state.unified_world_document["surface"] == "forward_picker"
    assert state.focused_field_role == "destination_filter"
    assert state.last_critic_verdict
    assert proposal.world_model["surface"] == "forward_picker"


def test_forward_picker_open_contact_on_visible_row_is_executed():
    """On the forward picker a visible destination row is clicked directly; the
    runtime never rewrites it into a sidebar search of the source contact."""
    world = WorldModel(active_app="WhatsApp")
    features = StateFeatures(
        conversation_open=False,
        extras={
            "app_content_node_count": 0,
            "world_document": {
                "surface": "forward_picker",
                "focused_field_role": "destination_filter",
            },
            "focused_field_role": "destination_filter",
        },
    )
    proposal = UnifiedProposal(
        observed_state={
            "surface": "forward_picker",
            "focused_field_role": "destination_filter",
        },
        next_action={
            "family": "open_contact",
            "text": "Tanmay",
            "target_label": "Tanmay",
            "target_point": [400, 500],
            "confidence": 0.95,
        },
        confidence=0.95,
    )
    action, reason = proposal_to_action(proposal, _goal(), world, features)
    assert reason == "admissible"
    assert action is not None
    assert action.action_family == "open_contact"
    assert action.grounding_reason == "unified_multimodal"
    assert "Pallavi" not in (action.text or "")


def test_sidebar_search_forbidden_helper():
    state = ExecutionState()
    state.unified_world_document = {"surface": "forward_picker"}
    state.focused_field_role = "destination_filter"
    assert sidebar_search_forbidden(state)
    assert not sidebar_search_forbidden(surface="search", role="sidebar_search")
