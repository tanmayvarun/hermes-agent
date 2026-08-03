"""reveal_actions is affordance discovery, not one right-click.

These pin the redesign's contract and double as its component eval: it reads an
already-open menu without gesturing (idempotence), spends a probe only when the
goal action is latent, grounds what it finds, and feeds the frontier.
"""

from types import SimpleNamespace

from plugin.agent.affordance_frontier import (
    Affordance,
    AffordanceFrontier,
    STATUS_LATENT,
    STATUS_OBSERVED,
    ground_revealed,
)
from plugin.agent.capabilities.base import AddressableEntity
from plugin.agent.capabilities.reveal_actions import (
    Action,
    RevealResult,
    action_surface_open,
    reveal_actions,
    reveal_ladder,
    visible_actions_from_context,
)


class FakePointer:
    """Records pointer ops; each op is (verb, ...)."""

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


def _menu_context():
    return {
        "surface": "context_menu",
        "layers": [
            {"role": "container", "name": "Pallavi", "state": "occluded", "objects": []},
            {
                "role": "action_menu",
                "state": "active",
                "objects": [
                    {"kind": "menu_item", "text": "Forward", "point": [100, 200]},
                    {"kind": "menu_item", "text": "Reply", "point": [100, 230]},
                    {"kind": "menu_item", "text": "Delete", "point": [100, 260]},
                ],
            },
        ],
    }


# --- the guard the old behaviour relied on -----------------------------------


def test_no_target_never_touches_the_pointer():
    rt = FakePointer()
    result = reveal_actions(AddressableEntity(app="Chat"), rt)
    assert result.ok is False
    assert rt.ops == []


def test_bare_call_still_probes_context_click_by_default():
    rt = FakePointer()
    result = reveal_actions(AddressableEntity(app="Chat", label="msg", bounds=(1, 2, 3, 4)), rt)
    assert result.ok is True
    assert result.escalated is True
    assert ("context_click", "Chat", "msg", (1, 2, 3, 4)) in rt.ops


# --- tier 0: idempotent read of an already-open menu -------------------------


def test_open_menu_is_read_not_re_gestured():
    rt = FakePointer()
    result = reveal_actions(
        AddressableEntity(app="WhatsApp", label="zarooratwala msg", bounds=(1, 2, 3, 4)),
        rt,
        context=_menu_context(),
    )
    # No gesture: the menu is already open, so we read + ground it.
    assert rt.ops == []
    assert result.method == "read"
    assert result.escalated is False
    fwd = result.action_for("Forward")
    assert fwd is not None and fwd.is_grounded and fwd.target["point"] == [100, 200]
    # Delete is grounded but flagged irreversible.
    assert result.action_for("Delete").reversible is False


def test_calling_twice_over_an_open_menu_yields_the_same_set_no_second_menu():
    rt = FakePointer()
    ctx = _menu_context()
    ent = AddressableEntity(app="WhatsApp", label="msg", bounds=(1, 2, 3, 4))
    first = reveal_actions(ent, rt, context=ctx)
    second = reveal_actions(ent, rt, context=ctx)
    assert rt.ops == []  # never gestured
    assert {a.label for a in first.actions} == {a.label for a in second.actions}


# --- tier 1 / tier 2: read visible, probe only when latent -------------------


def test_probe_spent_when_goal_action_is_latent_and_menu_closed():
    rt = FakePointer()
    ctx = {
        "surface": "conversation",
        "layers": [{"role": "container", "name": "Pallavi", "state": "active", "objects": []}],
        "frontier": {
            "observed_actions": [],
            "latent_actions": [
                {"target_label": "Forward", "family": "invoke_affordance", "confidence": 0.7, "reversible": True}
            ],
        },
    }
    result = reveal_actions(
        AddressableEntity(app="WhatsApp", label="msg", bounds=(1, 2, 3, 4)),
        rt,
        context=ctx,
        goal_action="Forward",
    )
    assert result.escalated is True
    assert ("context_click", "WhatsApp", "msg", (1, 2, 3, 4)) in rt.ops
    assert result.surface_opened == "context_menu"
    # the expected (latent) Forward is reported for the executive
    assert result.action_for("Forward") is not None


def test_visible_goal_action_short_circuits_the_probe():
    rt = FakePointer()
    ctx = _menu_context()  # Forward is visible + grounded on the open menu
    result = reveal_actions(
        AddressableEntity(app="WhatsApp", label="msg", bounds=(1, 2, 3, 4)),
        rt,
        context=ctx,
        goal_action="Forward",
    )
    assert rt.ops == []
    assert result.method == "read"


def test_no_probe_budget_returns_visible_without_gesturing():
    rt = FakePointer()
    ctx = {
        "surface": "conversation",
        "layers": [{"role": "container", "name": "Pallavi", "state": "active", "objects": []}],
        "frontier": {"observed_actions": [], "latent_actions": [{"target_label": "Forward"}]},
    }
    result = reveal_actions(
        AddressableEntity(app="WhatsApp", label="msg", bounds=(1, 2, 3, 4)),
        rt,
        context=ctx,
        goal_action="Forward",
        probe_budget=0,
    )
    assert rt.ops == []
    assert result.ok is False


# --- pure helpers ------------------------------------------------------------


def test_action_surface_open_detects_menu_layer_and_surface():
    assert action_surface_open(_menu_context()) is True
    assert action_surface_open({"surface": "conversation", "layers": []}) is False
    assert action_surface_open(None) is False


def test_reveal_ladder_puts_declared_mode_first():
    assert reveal_ladder({}, "hover")[0] == "hover"
    assert reveal_ladder({}, "context_click")[0] == "context_click"


def test_visible_actions_ground_from_the_open_menu_layer():
    actions = visible_actions_from_context(_menu_context())
    labels = {a.label for a in actions}
    assert {"Forward", "Reply", "Delete"} <= labels
    assert all(a.is_grounded for a in actions)


# --- frontier loop: latent -> observed --------------------------------------


def test_ground_revealed_promotes_latent_to_observed():
    frontier = AffordanceFrontier(
        surface="conversation",
        latent_actions=[
            Affordance(id="fwd", family="invoke_affordance", status=STATUS_LATENT, target_label="Forward"),
            Affordance(id="del", family="commit_irreversible", status=STATUS_LATENT, target_label="Delete", reversible=False),
        ],
    )
    result = RevealResult(
        actions=[Action(label="Forward", target={"point": [100, 200]}, visibility="visible")]
    )
    ground_revealed(frontier, result)

    observed_labels = {a.target_label for a in frontier.observed_actions}
    latent_labels = {a.target_label for a in frontier.latent_actions}
    assert "Forward" in observed_labels
    assert frontier.observed_actions[-1].status == STATUS_OBSERVED
    assert frontier.observed_actions[-1].actuators[0]["point"] == [100, 200]
    # Delete was not revealed/grounded, so it stays latent.
    assert "Delete" in latent_labels
