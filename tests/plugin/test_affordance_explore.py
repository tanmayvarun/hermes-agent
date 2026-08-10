"""Current-node affordance closure after critic acceptance."""

from __future__ import annotations

from plugin.agent.affordance_explore import (
    NODE_SCOPE_CURRENT,
    NODE_SCOPE_TRANSITION,
    classify_node_scope,
    close_current_node_frontier,
)
from plugin.agent.unified_cognition import UnifiedProposal


class _State:
    def __init__(self) -> None:
        self.last_affordance_frontier = {
            "surface": "conversation",
            "observed_actions": [{"family": "select_content", "target_label": "msg"}],
            "latent_actions": [
                {
                    "family": "invoke_affordance",
                    "target_label": "Forward",
                    "status": "latent",
                    "available_now": False,
                }
            ],
            "probe_actions": [],
        }


def test_classify_open_entity_as_transition():
    assert classify_node_scope("open_entity") == NODE_SCOPE_TRANSITION
    assert classify_node_scope("reveal_actions") == NODE_SCOPE_CURRENT


def test_close_folds_missing_probe_and_suggestions():
    state = _State()
    proposal = UnifiedProposal(
        missing_affordance_information=["pinned banner Reply control"],
        recommended_probe={
            "family": "reveal_actions",
            "target_id": 7,
            "may_reveal": ["Forward"],
            "reason": "context menu on message",
        },
        suggested_actions=[
            {
                "rank": 1,
                "family": "reveal_actions",
                "target_id": 7,
                "why": "message row is selected; Forward is latent",
                "confidence": 0.8,
            }
        ],
    )
    report = close_current_node_frontier(
        accepted_world={"surface": "conversation", "objects": [{"id": 7, "text": "hi"}]},
        passive_frontier=state.last_affordance_frontier,
        proposal=proposal,
        execution_state=state,
    )
    frontier = report["frontier"]
    assert report["needs_relook"] is False
    assert frontier["node_closure"]["status"].startswith("soft_complete")
    scopes = {
        a.get("node_scope")
        for key in ("observed_actions", "latent_actions", "probe_actions")
        for a in (frontier.get(key) or [])
    }
    assert NODE_SCOPE_CURRENT in scopes
    assert any(
        a.get("source") == "missing_affordance_information"
        for a in frontier["observed_actions"]
    )
    assert any(a.get("source") == "perceptor_recommended_probe" for a in frontier["probe_actions"])
    assert state.last_affordance_frontier is frontier
