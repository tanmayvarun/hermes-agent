"""Post-reveal affordance thoroughness (live 112904 class).

Motor-ok reveal must not silently leave an empty affordance_set. Phash must not
skip vision when an overlay is expected; menu items must promote under handoff
even when flat surface stays conversation.
"""

from types import SimpleNamespace

from plugin.agent.affordance_frontier import (
    Affordance,
    AffordanceFrontier,
    STATUS_LATENT,
    STATUS_OBSERVED,
    finalize_reveal_handoff,
    ground_revealed,
    publish_grounded_affordance_set,
)
from plugin.agent.capabilities.base import AddressableEntity
from plugin.agent.capabilities.reveal_actions import Action, RevealResult, reveal_actions
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.transition.post_perceive import assess_post_action_perception, profile_for
from plugin.agent.unified_cognition import expects_overlay_perception
from plugin.agent.world_critic import reconcile_frontier


class FakePointer:
    def __init__(self):
        self.ops = []

    def activate(self, app):
        self.ops.append(("activate", app))
        return True, "activated"

    def hover(self, app, label, bounds=None):
        self.ops.append(("hover", app, label, bounds))
        return True, "hovered"

    def context_click(self, app, label, bounds=None):
        self.ops.append(("context_click", app, label, bounds))
        return True, "menu opened"


def test_probe_outcome_is_incomplete_reveal_without_grounded_geometry():
    rt = FakePointer()
    state = ExecutionState()
    ctx = {
        "surface": "conversation",
        "layers": [],
        "frontier": {
            "latent_actions": [
                {
                    "target_label": "Forward",
                    "family": "invoke_affordance",
                    "confidence": 0.7,
                    "reversible": True,
                }
            ],
            "observed_actions": [],
        },
        "execution_state": state,
    }
    result = reveal_actions(
        AddressableEntity(app="WhatsApp", label="zarooratwala", bounds=(1, 2, 3, 4)),
        rt,
        context=ctx,
        goal_action="Forward",
    )
    outcome = result.to_outcome()
    assert result.ok is True
    assert outcome.evidence.get("incomplete_reveal") is True
    assert outcome.evidence.get("substrate") == "addressable_entity"
    assert outcome.evidence.get("handoff") is True
    assert isinstance(state.reveal_handoff, dict)
    assert state.reveal_handoff.get("surface") == "context_menu"


def test_phash_blocked_when_reveal_handoff_or_overlay_intention():
    state = ExecutionState()
    assert expects_overlay_perception(state) is False
    state.reveal_handoff = {"surface": "context_menu", "ttl": 2}
    assert expects_overlay_perception(state) is True
    state.reveal_handoff = None
    state.unified_last_expectation = {"surface": "context_menu"}
    assert expects_overlay_perception(state) is True


def test_reconcile_promotes_under_handoff_when_surface_stays_conversation():
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
            "objects": [
                {"text": "Forward", "kind": "menu_item", "point": [100, 200]},
                {"text": "Reply", "kind": "menu_item", "point": [100, 230]},
            ],
        },
        execution_state=state,
        last_action_family="reveal_actions",
    )
    labels = {a.target_label for a in frontier.observed_actions}
    assert "Forward" in labels
    assert frontier.observed_actions[-1].actuators
    assert state.last_grounded_affordance_set
    assert state.reveal_handoff is None  # cleared on successful ingest


def test_ground_revealed_ingests_menu_items_not_prelisted_as_latent():
    frontier = AffordanceFrontier(surface="context_menu", latent_actions=[])
    result = RevealResult(
        actions=[
            Action(label="Forward", target={"point": [10, 20]}, visibility="visible"),
            Action(label="Copy", target={"point": [10, 40]}, visibility="visible"),
        ]
    )
    ground_revealed(frontier, result)
    assert {a.target_label for a in frontier.observed_actions} == {"Forward", "Copy"}
    assert all(a.status == STATUS_OBSERVED and a.actuators for a in frontier.observed_actions)


def test_finalize_reveal_handoff_marks_failed_after_ttl():
    """Settle miss advances method; episode fails only when intention exhausted."""
    from plugin.agent.executive.intention_frame import (
        mark_method_attempted,
        push_intention_frame,
        seed_reveal_explore_frame,
    )

    state = ExecutionState()
    state.reveal_handoff = {"surface": "context_menu", "ttl": 2, "looks": 0}
    frontier = AffordanceFrontier(surface="conversation")
    s1 = finalize_reveal_handoff(state, frontier)
    assert s1.get("pending") is True
    assert state.reveal_handoff.get("looks") == 1
    s2 = finalize_reveal_handoff(state, frontier)
    # Intention still has sibling methods → advance, do not terminate episode.
    assert s2.get("method_advance") is True
    assert not s2.get("failed_reveal")
    assert state.reveal_handoff.get("incomplete_reveal") is False

    # Exhaust all methods → derived terminal failed_reveal.
    from plugin.agent.executive.intention_frame import MethodStatus, record_method_status

    frame = seed_reveal_explore_frame()
    for mid in list(frame.method_frontier.catalog.keys()):
        mark_method_attempted(frame, mid)
        record_method_status(frame, mid, MethodStatus.INEFFECTIVE.value)
    push_intention_frame(state, frame)
    state.reveal_handoff = {
        "surface": "context_menu",
        "ttl": 1,
        "looks": 0,
        "incomplete_reveal": True,
        "probe_gesture": "select_content",
    }
    state.reveal_prefer_capability = "select_content"
    state.reveal_probe_mode = "select_content"
    s3 = finalize_reveal_handoff(state, frontier)
    assert s3.get("failed_reveal") is True
    assert state.reveal_handoff.get("failed_reveal") is True
    assert state.reveal_handoff.get("incomplete_reveal") is False


def test_failed_reveal_escalates_off_context_click_live_153213():
    """LIVE 153213: motor-ok context_click without menu must not loop forever."""
    from plugin.agent.actor import CAPABILITY_GESTURE, brief_from_brain_choice
    from plugin.agent.capabilities.reveal_actions import (
        escalate_failed_reveal,
        reveal_motor_fingerprint,
    )

    state = ExecutionState()
    state.reveal_handoff = {
        "surface": "context_menu",
        "ttl": 2,
        "looks": 0,
        "probe_gesture": "context_click",
        "incomplete_reveal": True,
    }
    state.last_plan_step = type(
        "S",
        (),
        {
            "action_family": "reveal_actions",
            "semantic_target": "ZarooratWala - Fresh Groceries",
            "target_point": (380.0, 210.0),
        },
    )()
    frontier = AffordanceFrontier(surface="conversation")
    finalize_reveal_handoff(state, frontier)
    s2 = finalize_reveal_handoff(state, frontier)
    # Method-level advance under surviving intention (not sticky episode death).
    assert s2.get("method_advance") is True or s2.get("failed_reveal") is True
    assert state.reveal_probe_mode == "hover"
    assert state.reveal_prefer_capability == "reveal_actions"
    key = reveal_motor_fingerprint(
        "context_click",
        "ZarooratWala - Fresh Groceries",
        (380.0, 210.0),
    )
    assert key in (state.avoid_motor_keys or [])

    # Second failure rotates to select_content (toolbar Forward path).
    esc = escalate_failed_reveal(
        state,
        target="ZarooratWala - Fresh Groceries",
        point=(380.0, 210.0),
        last_gesture="hover",
    )
    assert esc.get("next_mode") == "select_content"
    assert state.reveal_prefer_capability == "select_content"

    # Actor must honor hover override (catalog default is context_click).
    assert CAPABILITY_GESTURE["reveal_actions"] == "context_click"
    brief = brief_from_brain_choice(
        {
            "family": "reveal_actions",
            "target_label": "ZarooratWala - Fresh Groceries",
            "target_point": [380.0, 210.0],
            "gesture": "hover",
            "coordinate_space": "screen",
        },
        {
            "surface": "conversation",
            "objects": [
                {
                    "text": "ZarooratWala - Fresh Groceries",
                    "kind": "message_bubble",
                    "point": [380.0, 210.0],
                }
            ],
        },
        app="WhatsApp",
        capability="reveal_actions",
    )
    assert brief.gesture == "hover"


def test_reveal_post_perceive_profile_and_affordance_gate_after_look():
    assert profile_for("reveal_actions").max_retries >= 2
    state = ExecutionState()
    state.reveal_handoff = {"surface": "context_menu", "ttl": 2}
    # Look still owed → do not demand affordance_set yet (AX settle path).
    state.post_action_reperceive_pending = True
    a1 = assess_post_action_perception(
        action_family="reveal_actions",
        view={"screen": "CONVERSATION"},
        features={},
        execution_state=state,
    )
    assert "affordance_set_empty" not in a1.failure_modes
    # Look paid, handoff still empty → incomplete.
    state.post_action_reperceive_pending = False
    state.must_executive_reperceive = False
    a2 = assess_post_action_perception(
        action_family="reveal_actions",
        view={"screen": "CONVERSATION"},
        features={},
        execution_state=state,
    )
    assert "affordance_set_empty" in a2.failure_modes
    assert a2.settled is False


def test_note_reveal_probe_handoff_sets_incomplete_on_execution_state():
    from plugin.agent.capabilities.reveal_actions import note_reveal_probe_handoff

    state = ExecutionState()
    note_reveal_probe_handoff(state)
    assert state.reveal_handoff["surface"] == "context_menu"
    assert state.reveal_handoff["incomplete_reveal"] is True
    assert expects_overlay_perception(state) is True


def test_publish_affordance_set_parity_with_actuators():
    state = ExecutionState()
    frontier = AffordanceFrontier(
        surface="context_menu",
        observed_actions=[
            Affordance(
                id="fwd",
                family="invoke_affordance",
                status=STATUS_OBSERVED,
                target_label="Forward",
                actuators=[{"type": "coordinate_click", "point": [1, 2], "confidence": 0.9}],
            )
        ],
    )
    published = publish_grounded_affordance_set(state, frontier)
    assert len(published) == 1
    assert published[0]["target_label"] == "Forward"
    assert state.last_grounded_affordance_set[0]["actuators"]
