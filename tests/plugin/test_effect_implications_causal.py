"""Causal effect-implication goldens (attempt-scoped, predicate-specific)."""

from __future__ import annotations

from types import SimpleNamespace

from plugin.agent.action import Action
from plugin.agent.apps.whatsapp import build_forward_task_state
from plugin.agent.controller import _handle_open_entity_effect_absent, _note_failed_motor
from plugin.agent.executive.effect_implications import (
    annotate_world_with_effect_evidence,
    avoid_key_blocks_method,
    collect_effect_evidence,
    method_context_from_state,
)
from plugin.agent.executive.intention_frame import (
    MethodContext,
    active_intention_frame,
    push_intention_frame,
    seed_reveal_explore_frame,
)
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import ExecutionState, RuntimeState
from plugin.agent.whatsapp_view import WhatsAppWorldView
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel


def test_foreign_attempt_progress_does_not_verify_current_forward():
    """Stale progress from attempt A must not verify Forward attempt B."""
    state = ExecutionState()
    state.last_plan_step = SimpleNamespace(
        action_family="invoke_affordance",
        semantic_target="Forward",
        text="Forward",
        attempt_id="attempt-B",
    )
    state.last_result = {"ok": True, "attempt_id": "attempt-B"}
    state.last_attribution = {
        "effect_kind": "progress",
        "outcome": "progress",
        "attempt_id": "attempt-A",  # foreign
    }
    state.last_effect_attempt_id = "attempt-A"
    evidence = collect_effect_evidence(
        state, {"surface": "conversation", "screen": "conversation"}
    )
    assert "source_object_selected" not in evidence.implies
    assert "forward_route_discovered" not in evidence.achieved
    annotated = annotate_world_with_effect_evidence(
        state, {"surface": "conversation"}
    )
    assert annotated.get("source_object_selected") is not True


def test_generic_progress_does_not_imply_forward_route_discovered():
    """Even same-attempt progress grade is not semantic Forward proof."""
    state = ExecutionState()
    state.last_plan_step = SimpleNamespace(
        action_family="invoke_affordance",
        semantic_target="Forward",
        text="Forward",
        attempt_id="attempt-B",
    )
    state.last_result = {"ok": True, "attempt_id": "attempt-B"}
    state.last_attribution = {
        "effect_kind": "progress",
        "outcome": "progress",
        "attempt_id": "attempt-B",
    }
    state.last_effect_attempt_id = "attempt-B"
    evidence = collect_effect_evidence(
        state, {"surface": "conversation", "screen": "conversation"}
    )
    assert "forward_route_discovered" not in evidence.achieved
    assert "source_object_selected" not in evidence.implies


def test_same_attempt_forward_picker_surface_implies_source_selected():
    """Authoritative forward_picker world surface implies prerequisite."""
    evidence = collect_effect_evidence(
        None, {"surface": "forward_picker", "screen": "forward_picker"}
    )
    assert "source_object_selected" in evidence.implies
    assert "forward_route_discovered" in evidence.achieved


def test_same_attempt_named_effect_predicate_verifies_forward():
    state = ExecutionState()
    state.last_plan_step = SimpleNamespace(
        action_family="invoke_affordance",
        semantic_target="Forward",
        attempt_id="attempt-B",
    )
    state.last_result = {"ok": True, "attempt_id": "attempt-B"}
    state.last_attribution = {
        "attempt_id": "attempt-B",
        "verified_effect_predicates": ["forward_surface_open"],
    }
    state.last_effect_attempt_id = "attempt-B"
    evidence = collect_effect_evidence(
        state, {"surface": "conversation"}
    )
    assert "source_object_selected" in evidence.implies
    assert "forward_route_discovered" in evidence.achieved


def test_unscoped_named_effect_does_not_verify_current_attempt():
    """Named predicates without effect-side attempt_id must fail closed."""
    state = ExecutionState()
    state.last_plan_step = SimpleNamespace(
        action_family="invoke_affordance",
        semantic_target="Forward",
        attempt_id="attempt-B",
    )
    state.last_result = {"ok": True}  # no attempt id
    state.last_attribution = {
        # Named semantic effect, but no attempt_id → not causal for B.
        "verified_effect_predicates": ["forward_surface_open"],
    }
    state.last_effect_attempt_id = ""
    evidence = collect_effect_evidence(
        state, {"surface": "conversation"}
    )
    assert "source_object_selected" not in evidence.implies
    assert "forward_route_discovered" not in evidence.achieved


def test_foreign_executor_result_plus_current_picker_does_not_create_action_effect_binding():
    """Stale last_result + ambient picker must not mutate task via bind path."""
    from plugin.agent.controller import _bind_forward_after_execution
    from plugin.agent.runtime.state import RuntimeState
    from plugin.worldmodel.model import WorldModel

    rt = RuntimeState(world_model=WorldModel(active_app="WhatsApp"))
    rt.execution_state.last_surface = "forward_picker"
    # Unrelated/stale executor ok with no attempt alignment to this decision.
    rt.execution_state.last_result = {"ok": True}
    rt.world_model.overlay_hints = {
        "forward_task": {
            "predicates": {
                "source_object_selected": False,
                "source_conversation_open": True,
            },
            "derived_phase": "FIND_LINK",
        }
    }
    decision = Action(
        action="InvokeAffordance",
        action_family="invoke_affordance",
        semantic_target="Forward",
        attempt_id="attempt-forward-now",
    )
    _bind_forward_after_execution(rt, decision)
    ft = (rt.world_model.overlay_hints or {}).get("forward_task") or {}
    preds = ft.get("predicates") or {}
    assert preds.get("source_object_selected") is not True


def test_same_method_may_be_reconsidered_after_world_signature_changes():
    """Scoped avoid from search must not block same label in conversation."""
    rt = RuntimeState(world_model=WorldModel(active_app="App"))
    rt.execution_state.last_surface = "search"
    push_intention_frame(rt.execution_state, seed_reveal_explore_frame())
    hit = "https://www.example.com/item"
    _note_failed_motor(
        rt,
        family="open_entity",
        target=hit,
        point=(242.0, 354.0),
    )
    keys = list(rt.execution_state.avoid_motor_keys or [])
    assert keys
    # Same intention + search signature → blocked.
    search_ctx = method_context_from_state(
        rt.execution_state, world={"surface": "search"}
    )
    iframe = active_intention_frame(rt.execution_state)
    assert avoid_key_blocks_method(
        keys,
        family="open_entity",
        target=hit,
        intention_id=iframe.intention.id,
        world_signature=search_ctx.signature(),
        point_key="",
    )
    # Conversation signature → not blocked (world changed).
    conv_ctx = MethodContext(
        surface="conversation",
        semantic_container="Alice",
        target_selected=False,
        action_surface_visible=False,
        overlay="",
    )
    assert not avoid_key_blocks_method(
        keys,
        family="open_entity",
        target=hit,
        intention_id=iframe.intention.id,
        world_signature=conv_ctx.signature(),
        point_key="",
    )


def test_same_surface_different_container_reconsiders_method():
    """Same surface, different semantic_container → method failure not sticky."""
    from plugin.agent.executive.effect_implications import scoped_method_avoid_key

    rt = RuntimeState(world_model=WorldModel(active_app="App"))
    rt.execution_state.last_surface = "conversation"
    push_intention_frame(rt.execution_state, seed_reveal_explore_frame())
    hit = "https://www.example.com/item"
    iframe = active_intention_frame(rt.execution_state)
    alice_ctx = method_context_from_state(
        rt.execution_state,
        world={"surface": "conversation", "open_conversation": "Alice"},
    )
    alice_key = scoped_method_avoid_key(
        "open_entity",
        hit,
        intention_id=iframe.intention.id,
        world_signature=alice_ctx.signature(),
    )
    rt.execution_state.avoid_motor_keys = [alice_key]
    assert "ctr=alice" in alice_ctx.signature()
    assert avoid_key_blocks_method(
        rt.execution_state.avoid_motor_keys,
        family="open_entity",
        target=hit,
        intention_id=iframe.intention.id,
        world_signature=alice_ctx.signature(),
    )
    bob_ctx = method_context_from_state(
        rt.execution_state,
        world={"surface": "conversation", "open_conversation": "Bob"},
    )
    assert "ctr=bob" in bob_ctx.signature()
    assert alice_ctx.signature() != bob_ctx.signature()
    assert not avoid_key_blocks_method(
        rt.execution_state.avoid_motor_keys,
        family="open_entity",
        target=hit,
        intention_id=iframe.intention.id,
        world_signature=bob_ctx.signature(),
    )


def test_method_ineffective_uses_real_world_signature_not_intention_scope():
    rt = RuntimeState(world_model=WorldModel(active_app="App"))
    rt.execution_state.last_surface = "search"
    frame = seed_reveal_explore_frame()
    push_intention_frame(rt.execution_state, frame)
    decision = Action(
        action="OpenEntity",
        action_family="open_entity",
        semantic_target="https://www.example.com/x",
        target_point=(10.0, 20.0),
        establishes_roles=["source_container"],
        action_is_navigation=True,
        attempt_id="attempt-open-1",
    )
    _handle_open_entity_effect_absent(
        rt,
        decision,
        fam="open_entity",
        pred_error={"matched": False, "verdict": "prediction_mismatch"},
    )
    mid = f"open_entity:{decision.semantic_target[:80]}"
    stored = frame.method_frontier.ineffective_in_world_signature.get(mid) or ""
    assert stored
    assert "surface=search" in stored
    # Must be MethodContext signature, not the intention.scope prose string.
    assert stored != str(frame.intention.scope or "")
    assert stored.startswith("surface=")


def test_open_conversation_identity_sync_closes_open_source():
    """Pipeline: open_conversation=Alice + goal contact → FIND_LINK."""
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Alice",
        target_contact="Bob",
        link_query="example",
    )
    wm = WorldModel(active_app="WhatsApp")
    alice = Entity(
        id=1,
        entity_type="static",
        semantic_role="Alice",
        label="Alice",
        role="AXStaticText",
        bounds=(100.0, 40.0, 40.0, 16.0),
        actions=[],
        attributes={},
        visible=True,
    )
    wm.entities[1] = alice
    view = WhatsAppWorldView(
        screen="CONVERSATION",
        open_conversation="Alice",
    )
    prior = {
        "predicates": {"source_conversation_open": False},
        "derived_phase": "OPEN_SOURCE",
        "bindings": {
            "source_conversation": {
                "name": "source_conversation",
                "status": "unresolved",
            }
        },
    }
    state = build_forward_task_state(goal, wm, view, leftover=False, prior=prior)
    conv = state.binding("source_conversation")
    assert conv.status == "confirmed"
    assert state.predicates.source_conversation_open is True
    assert state.derived_phase == "FIND_LINK"
