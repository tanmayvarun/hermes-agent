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


def test_critic_rejects_search_field_chrome_as_open_conversation():
    """AX often latches the search glyph/title as open_conversation after a click.

    That is not a document referent. Critic must refuse it and recover the
    contact from inventory / prior — general search-chrome rule, not app folklore.
    """
    prior = {"surface": "chat_list", "open_conversation": ""}
    proposal = {
        "surface": "conversation",
        "open_conversation": "Q Search|",
        "objects": [
            {
                "id": "header",
                "kind": "chat_header",
                "text": "Pallavi",
                "matches_goal": True,
            }
        ],
    }
    verdict = critique_world_proposal(prior, proposal, last_action="open_entity")
    assert verdict.accepted_document["surface"] == "conversation"
    assert verdict.accepted_document["open_conversation"] == "Pallavi"
    assert any(
        d.field == "open_conversation" and d.verdict == "reject" for d in verdict.decisions
    )


def test_bullet_search_chrome_is_search_field_echo():
    """Live WA Mac AX stamps open as '• Search|' — must not pass as a contact."""
    from plugin.agent.world_critic import is_search_field_echo
    from plugin.agent.whatsapp_view import _is_contact_name, _normalize_open_conversation_text

    for title in ("• Search|", "• Search", "· Search|", "Q Search|", "Search|"):
        assert is_search_field_echo(title), title
        assert not _is_contact_name(title), title
        assert _normalize_open_conversation_text(title) == ""


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


def test_critic_rejects_conversation_when_prediction_error_says_search():
    """Direct transition evidence must downgrade a contradicted conversation patch.

    Live 210526: cloud proposed conversation while prediction_error repeatedly
    reported observed=search. Parent-edge legality alone must not win.
    """
    prior = {"surface": "search", "open_conversation": "", "search_query": "Pallavi"}
    proposal = {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "search_query": "Pallavi",
        "objects": [
            {"id": "links", "kind": "filter_chip", "text": "Links", "restricts": "result_scope"},
            {"id": "messages", "kind": "filter_chip", "text": "Messages", "restricts": "result_scope"},
            {"id": "row", "kind": "chat_row", "text": "Pallavi: https://…", "matches_goal": True},
        ],
    }
    pe = {
        "predicted_surface": "conversation",
        "observed_surface": "search",
        "matched": False,
        "verdict": "you predicted 'conversation' and the screen is 'search'.",
    }
    verdict = critique_world_proposal(
        prior,
        proposal,
        last_action="resolve_entity",
        observed_surface="search",
        prediction_error=pe,
    )
    assert verdict.accepted_document["surface"] == "search"
    assert not verdict.accepted_document.get("open_conversation")
    assert any(
        d.field == "surface" and d.verdict == "reject" for d in verdict.decisions
    )


def test_resolve_entity_intention_does_not_claim_conversation():
    """resolve_entity establishes EntityRef; it must not predict conversation_open."""
    from plugin.agent.action import Action
    from plugin.agent.unified_cognition import intention_expectation_from_decision

    decision = Action(
        action="ResolveEntity",
        action_family="resolve_entity",
        semantic_target="Pallavi",
        text="Pallavi",
        prediction={
            "expected_surface": "conversation",
            "expected_affordances": ["message_bubbles", "input_field", "header_info"],
        },
        expected_predicate="conversation",
    )
    claim = intention_expectation_from_decision(decision)
    assert claim.get("surface") == "search"
    assert claim.get("claims_navigation") is False
    assert claim.get("claims_resolution") is True
    controls = [str(c).lower() for c in (claim.get("likely_controls") or [])]
    assert "message_bubbles" not in controls
