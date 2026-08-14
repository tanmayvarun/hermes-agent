"""Desired-effect → compatible method (not object → default OpenEntity).

Goldens from live 20260811_131030: open_entity + context_menu thrash on a
visible zarooratwala content hit, then SEARCH escalation that invalidated
upstream retrieval.
"""

from __future__ import annotations

from plugin.agent.action import Action
from plugin.agent.brain import motor_fingerprint
from plugin.agent.controller import (
    _handle_open_entity_effect_absent,
    _note_open_source_failure,
)
from plugin.agent.decision_consultation import sanitize_decision
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import RuntimeState
from plugin.agent.unified_cognition import (
    UnifiedProposal,
    intention_expectation_from_decision,
    proposal_to_action,
)
from plugin.worldmodel.model import WorldModel


def _link_object(**overrides):
    base = {
        "id": "msg_link",
        "kind": "message",
        "text": "You: https://www.example.com/item",
        "label": "You: https://www.example.com/item",
        "point": [240, 350],
    }
    base.update(overrides)
    return base


def test_same_object_forward_goal_rewrites_open_plus_menu_to_reveal():
    """Forward goal on open conversation: desired effect reveal, not open."""
    world = WorldModel(active_app="App")
    proposal = UnifiedProposal(
        next_action={
            "family": "open_entity",
            "target_label": "You: https://www.example.com/item",
            "target_id": "msg_link",
            "target_point": [240, 350],
            "coordinate_space": "screen",
        },
        confidence=0.95,
        observed_state={"surface": "conversation", "open_conversation": "Alice"},
        expected_transition={
            "surface": "context_menu",
            "likely_controls": ["Forward", "Reply", "Copy"],
        },
        world_model={"objects": [_link_object()]},
    )
    action, reason = proposal_to_action(
        proposal,
        Goal(
            kind="forward_message",
            app="App",
            contact="Alice",
            link_query="example",
            target_contact="Bob",
        ),
        world,
    )
    assert action is not None, reason
    assert action.action_family == "reveal_actions"
    assert (action.prediction or {}).get("expected_surface") == "context_menu"


def test_same_object_open_goal_keeps_open_content_effect():
    """'Open this link' may still use open_entity; expectation stays navigational."""
    decision = Action(
        action="OpenEntity",
        action_family="open_entity",
        semantic_target="You: https://www.example.com/item",
        prediction={"expected_surface": "conversation"},
    )
    assert intention_expectation_from_decision(decision)["surface"] == "conversation"


def test_search_surface_open_plus_menu_coerces_to_conversation_claim():
    """On search, open_entity must claim container open — not context_menu."""
    world = WorldModel(active_app="App")
    proposal = UnifiedProposal(
        next_action={
            "family": "open_entity",
            "target_label": "You: https://www.example.com/item",
            "target_point": [240, 350],
            "coordinate_space": "screen",
        },
        confidence=0.95,
        observed_state={"surface": "search"},
        expected_transition={
            "surface": "context_menu",
            "likely_controls": ["Forward", "Reply"],
        },
    )
    action, reason = proposal_to_action(
        proposal,
        Goal(
            kind="forward_message",
            contact="Alice",
            link_query="example",
            target_contact="Bob",
        ),
        world,
    )
    assert action is not None, reason
    assert action.action_family == "open_entity"
    assert (action.prediction or {}).get("expected_surface") == "conversation"
    assert (action.prediction or {}).get("source") == "family_contract"


def test_open_entity_effect_missing_blocks_reground_retry():
    """After motor_ok + effect_missing, same family+target is not re-admitted."""
    from plugin.agent.executive.effect_implications import (
        avoid_key_blocks_method,
        method_context_from_state,
    )

    rt = RuntimeState(world_model=WorldModel(active_app="App"))
    rt.execution_state.last_surface = "search"
    hit = "You: https://www.example.com/item"
    decision = Action(
        action="OpenEntity",
        action_family="open_entity",
        semantic_target=hit,
        target_point=(242.0, 354.0),
        establishes_roles=["source_container"],
        action_is_navigation=True,
        expected_predicate="conversation",
    )
    handled = _handle_open_entity_effect_absent(
        rt,
        decision,
        fam="open_entity",
        pred_error={"matched": False, "verdict": "prediction_mismatch"},
    )
    assert handled.get("open_repair")
    avoid = list(rt.execution_state.avoid_motor_keys or [])
    ctx = method_context_from_state(rt.execution_state, world={"surface": "search"})
    # Same world signature + re-grounded XY still blocked.
    assert avoid_key_blocks_method(
        avoid,
        family="open_entity",
        target=hit,
        intention_id="",
        world_signature=ctx.signature(),
        point_key=motor_fingerprint("open_entity", hit, (429.0, 355.0)),
    ) or avoid_key_blocks_method(
        avoid,
        family="open_entity",
        target=hit,
        intention_id="",
        world_signature=ctx.signature(),
        point_key="",
    )


def test_sanitize_blocks_url_open_when_source_open_and_hunting():
    """URL escape removed: source open + hunt must not admit open_entity(link)."""
    from plugin.agent.decision_consultation import build_decision_brief
    from plugin.agent.features import StateFeatures

    brief = build_decision_brief(
        Goal(
            kind="whatsapp_forward_message",
            contact="Pallavi",
            target_contact="Tanmay",
            link_query="example",
        ),
        world_document={
            "surface": "conversation",
            "open_conversation": "Pallavi",
            "objects": [
                {
                    "text": "You: https://www.example.com/item",
                    "kind": "message",
                    "matches_goal": True,
                }
            ],
        },
        features=StateFeatures(conversation_open=True, extras={}),
    )
    assert brief.task_state.source_chat_open is True
    assert brief.task_state.phase == "hunt_content"
    rejected = sanitize_decision(
        {
            "capability": "open_entity",
            "target": "You: https://www.example.com/item",
            "why": "open the link",
        },
        brief,
    )
    # Must not admit OpenEntity(URL) while hunting — previously
    # ``_looks_like_url_blob`` exempted this path.
    assert not rejected.ok
    assert rejected.capability != "open_entity" or not rejected.ok
    # Prefer operate-on-content methods when the hunt gate is the one that fires.
    if "locate_content" in rejected.why or "reveal" in rejected.why:
        return
    assert "not actionable" in rejected.why or "SEARCH" in rejected.why


def test_contrastive_identity_goal_does_not_require_open_entity():
    """'Who sent this?' → no ACT open; identity is perceptual."""
    # Structural: open_entity is not forced merely because a link object exists.
    decision = Action(
        action="Observe",
        action_family="observe",
        semantic_target="You: https://www.example.com/item",
    )
    assert intention_expectation_from_decision(decision) == {}


def test_two_content_open_misses_prefer_method_exhausted_not_search():
    rt = RuntimeState(world_model=WorldModel(active_app="App"))
    rt.execution_state.search_episode = {
        "status": "complete",
        "candidates": [{"label": "You: https://www.example.com/item"}],
        "chosen_label": "You: https://www.example.com/item",
    }
    hit = "You: https://www.example.com/item"
    for pt in ((242.0, 354.0), (429.0, 355.0)):
        repair = _note_open_source_failure(
            rt,
            Action(
                action="OpenEntity",
                action_family="open_entity",
                semantic_target=hit,
                target_point=pt,
            ),
            reason="prediction_mismatch",
        )
    assert repair["prefer"] == "method_exhausted_reperceive"
    assert repair.get("failure_class") == "method_ineffective"
