"""Capabilities that compose a forward_message flow — without bundling a plan."""

from __future__ import annotations

from typing import List, Optional, Tuple

from plugin.agent.capabilities.base import AddressableEntity, CapabilityRequest
from plugin.agent.capabilities.catalog import all_specs, model_allowed_actions, realized_verbs
from plugin.agent.capabilities.commit_irreversible import commit_irreversible, is_commit_label
from plugin.agent.capabilities.dispatch import can_dispatch, dispatch
from plugin.agent.capabilities.invoke_affordance import invoke_affordance, is_irreversible_affordance
from plugin.agent.capabilities.reveal_actions import reveal_actions
from plugin.agent.capabilities.select_content import select_content
from plugin.agent.goal import Goal
from plugin.agent.unified_cognition import ALLOWED_ACTIONS, UnifiedProposal, proposal_to_action
from plugin.worldmodel.model import WorldModel


class FakePointer:
    def __init__(self) -> None:
        self.ops: List[Tuple[str, str, Optional[tuple]]] = []

    def activate(self, app: str) -> None:
        pass

    def click(self, app: str, label: str, *, bounds=None):
        self.ops.append(("click", label, bounds))
        return True, f"clicked {label}"

    def hover(self, app: str, label: str, *, bounds=None):
        self.ops.append(("hover", label, bounds))
        return True, f"hovered {label}"

    def context_click(self, app: str, label: str, *, bounds=None):
        self.ops.append(("context_click", label, bounds))
        return True, f"context {label}"


def test_entire_forward_composition_is_in_the_vocabulary():
    needed = {
        "locate_content",
        "open_entity",
        "select_content",
        "reveal_actions",
        "invoke_affordance",
        "dismiss_transient",
        "commit_irreversible",
    }
    assert needed <= set(model_allowed_actions())
    assert needed <= set(ALLOWED_ACTIONS)
    assert needed <= set(realized_verbs())


def test_every_catalog_entry_is_realized_and_dispatchable():
    for spec in all_specs():
        assert can_dispatch(spec.name), spec.name


def test_select_content_focuses_without_claiming_navigation():
    rt = FakePointer()
    outcome = select_content(
        AddressableEntity(app="Chat", label="zarooratwala link", bounds=(1, 2, 3, 4)),
        rt,
    )
    assert outcome.ok
    assert outcome.realization == "select_click"
    assert rt.ops[0][0] == "click"


def test_reveal_actions_defaults_to_context_click():
    rt = FakePointer()
    outcome = reveal_actions(
        AddressableEntity(app="Chat", label="msg", bounds=(1, 2, 3, 4)),
        rt,
    )
    assert outcome.ok
    assert rt.ops[0][0] == "context_click"


def test_reveal_actions_honours_hover_mode():
    rt = FakePointer()
    outcome = reveal_actions(
        AddressableEntity(app="Chat", label="msg", bounds=(1, 2, 3, 4)),
        rt,
        mode="hover",
    )
    assert rt.ops[0][0] == "hover"


def test_invoke_forward_is_allowed_as_reversible():
    rt = FakePointer()
    outcome = invoke_affordance("Chat", "Forward", rt)
    assert outcome.ok
    assert not is_irreversible_affordance("Forward")


def test_invoke_refuses_send_so_the_gate_stays_visible():
    rt = FakePointer()
    outcome = invoke_affordance("Chat", "Send", rt)
    assert not outcome.ok
    assert "commit_irreversible" in outcome.message
    assert rt.ops == []


def test_commit_accepts_send_and_marks_irreversible():
    rt = FakePointer()
    outcome = commit_irreversible("Chat", "Send", rt)
    assert outcome.ok
    assert outcome.evidence["irreversible"] is True
    assert is_commit_label("Send")


def test_commit_refuses_forward_which_belongs_on_invoke():
    rt = FakePointer()
    outcome = commit_irreversible("Chat", "Forward", rt)
    assert not outcome.ok
    assert "invoke_affordance" in outcome.message
    assert rt.ops == []


def test_dispatch_invoke_send_is_refused():
    class Overlay:
        pass

    outcome = dispatch(
        CapabilityRequest(name="invoke_affordance", app="WhatsApp", arg="Send"),
        Overlay(),
    )
    assert not outcome.ok
    assert outcome.evidence.get("reason") == "irreversible"


def test_model_can_propose_each_composition_step():
    cases = [
        ("open_entity", {"text": "Pallavi", "target_point": [10, 20]}, "admissible"),
        ("locate_content", {"text": "zarooratwala"}, "admissible"),
        ("select_content", {"text": "zarooratwala link", "target_point": [10, 20]}, "admissible"),
        ("reveal_actions", {"text": "zarooratwala link", "target_point": [10, 20]}, "admissible"),
        ("invoke_affordance", {"text": "Forward"}, "admissible"),
        ("dismiss_transient", {}, "admissible"),
        ("commit_irreversible", {"text": "Send"}, "admissible"),
    ]
    for family, next_action, expected in cases:
        action, reason = proposal_to_action(
            UnifiedProposal(
                next_action={"family": family, **next_action},
                confidence=0.9,
                point_scale=1.0,
            ),
            Goal(kind="whatsapp_forward_message"),
            WorldModel(),
        )
        assert reason == expected, (family, reason)
        assert action is not None
        assert action.action_family == family
        if family == "commit_irreversible":
            assert action.reversible is False
        else:
            assert action.reversible is True
