"""Post-accept promote + multi-pass explore (235701 timing / discovery class).

Motor-ok reveal can leave menu pixels in the *accepted* world document while
``_frontier_for_packet`` already reconciled against the prior doc. Promote must
run after critic accept; incomplete handoff schedules bounded relooks without
OCR bypass.
"""

from __future__ import annotations

from types import SimpleNamespace

from plugin.agent.affordance_explore import close_current_node_frontier, explore_budget
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.world_critic import promote_frontier_after_accept, reconcile_frontier
from plugin.agent.affordance_frontier import Affordance, AffordanceFrontier, STATUS_LATENT


def test_promote_frontier_after_accept_grounds_forward_from_accepted_doc():
    state = ExecutionState()
    state.reveal_handoff = {
        "surface": "context_menu",
        "ttl": 2,
        "incomplete_reveal": True,
    }
    state.last_plan_step = SimpleNamespace(action_family="reveal_actions")
    # Prior frontier had no menu (simulates pre-stage1 reconcile miss).
    state.last_affordance_frontier = {
        "surface": "conversation",
        "observed_actions": [],
        "latent_actions": [],
        "probe_actions": [],
    }
    accepted = {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "objects": [
            {"text": "zarooratwala", "kind": "outgoing_message", "point": [100, 100]},
            {"text": "Forward", "kind": "menu_item", "is_menu_item": True, "point": [200, 280]},
            {"text": "Reply", "kind": "menu_item", "is_menu_item": True, "point": [200, 240]},
        ],
        "layers": [
            {
                "role": "container",
                "name": "Pallavi",
                "state": "occluded",
                "objects": [
                    {
                        "text": "zarooratwala",
                        "kind": "outgoing_message",
                        "point": [100, 100],
                    }
                ],
            },
            {
                "role": "action_menu",
                "name": "message actions",
                "state": "active",
                "objects": [
                    {
                        "text": "Forward",
                        "kind": "menu_item",
                        "point": [200, 280],
                    }
                ],
            },
        ],
    }
    state.unified_world_document = accepted

    status = promote_frontier_after_accept(
        state,
        accepted_document=accepted,
        last_action_family="reveal_actions",
    )
    assert status["promoted"] is True
    assert status["grounded"] >= 1
    labels = {
        str(a.get("target_label") or "")
        for a in (state.last_grounded_affordance_set or [])
    }
    assert "Forward" in labels
    assert state.reveal_handoff is None


def test_close_node_schedules_relook_when_handoff_ungrounded():
    state = ExecutionState()
    state.reveal_handoff = {
        "surface": "context_menu",
        "ttl": 4,
        "incomplete_reveal": True,
        "explore_budget": 2,
        "explore_used": 0,
    }
    report = close_current_node_frontier(
        accepted_world={
            "surface": "conversation",
            "open_conversation": "Pallavi",
            "objects": [
                {"text": "zarooratwala", "kind": "outgoing_message", "point": [1, 2]}
            ],
        },
        passive_frontier={"surface": "conversation", "observed_actions": [], "latent_actions": [], "probe_actions": []},
        proposal=None,
        execution_state=state,
    )
    assert report["needs_relook"] is True
    assert state.must_executive_reperceive is True
    assert int((state.reveal_handoff or {}).get("explore_used") or 0) == 1
    assert report["closure"]["status"] == "needs_relook"


def test_explore_budget_exhausts_without_ocr_inventing_forward():
    state = ExecutionState()
    state.reveal_handoff = {
        "surface": "context_menu",
        "ttl": 4,
        "incomplete_reveal": True,
        "explore_budget": 1,
        "explore_used": 1,  # already spent
    }
    # Document has no menu verbs — promote must not invent Forward from OCR.
    report = close_current_node_frontier(
        accepted_world={
            "surface": "conversation",
            "objects": [{"text": "yeah", "kind": "message", "point": [1, 1]}],
        },
        passive_frontier={"surface": "conversation"},
        execution_state=state,
    )
    assert report["needs_relook"] is False
    assert report["closure"]["status"] == "explore_exhausted"
    grounded = state.last_grounded_affordance_set or []
    assert not any(
        str(a.get("target_label") or "").lower() == "forward" for a in grounded
    )


def test_handoff_alone_promotes_without_plan_step_family():
    """Post-accept path may run after plan step cleared; handoff must still promote."""
    state = ExecutionState()
    state.reveal_handoff = {"surface": "context_menu", "ttl": 2}
    frontier = AffordanceFrontier(
        surface="conversation",
        latent_actions=[
            Affordance(
                id="fwd",
                family="invoke_affordance",
                status=STATUS_LATENT,
                target_label="Forward",
            )
        ],
    )
    reconcile_frontier(
        frontier,
        document={
            "surface": "conversation",
            "objects": [{"text": "Forward", "kind": "menu_item", "point": [10, 20]}],
        },
        execution_state=state,
        last_action_family="",  # cleared
    )
    assert any(a.target_label == "Forward" and a.actuators for a in frontier.observed_actions)


def test_default_explore_budget_is_positive():
    assert explore_budget() >= 1
