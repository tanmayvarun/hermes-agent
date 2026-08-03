"""open_entity and dismiss_transient — general, reversible, host-declared."""

from __future__ import annotations

from typing import List, Optional, Tuple

from plugin.agent.capabilities.base import AddressableEntity, CapabilityRequest, TransientChrome
from plugin.agent.capabilities.catalog import model_allowed_actions, spec_by_name
from plugin.agent.capabilities.dismiss_transient import MACOS_DISMISS, dismiss_transient
from plugin.agent.capabilities.dispatch import can_dispatch, dispatch
from plugin.agent.capabilities.locate_content import KeyChord
from plugin.agent.capabilities.open_entity import open_entity, resolve_addressable
from plugin.agent.goal import Goal
from plugin.agent.unified_cognition import ALLOWED_ACTIONS, UnifiedProposal, proposal_to_action
from plugin.worldmodel.model import WorldModel


class FakeOpenRuntime:
    def __init__(self) -> None:
        self.clicks: List[Tuple[str, str, Optional[tuple]]] = []

    def activate(self, app: str) -> None:
        pass

    def click(self, app: str, label: str, *, bounds=None):
        self.clicks.append((app, label, bounds))
        return True, f"clicked {label}"


class FakeDismissRuntime:
    def __init__(self) -> None:
        self.keys: List[KeyChord] = []

    def activate(self, app: str) -> None:
        pass

    def key(self, chord: KeyChord) -> None:
        self.keys.append(chord)


def test_open_and_dismiss_are_in_the_model_vocabulary():
    allowed = model_allowed_actions()
    assert "open_entity" in allowed
    assert "dismiss_transient" in allowed
    assert ALLOWED_ACTIONS == allowed


def test_both_are_dispatchable():
    assert can_dispatch("open_entity")
    assert can_dispatch("dismiss_transient")
    assert can_dispatch("press_escape")  # alias


def test_open_entity_clicks_the_resolved_label():
    runtime = FakeOpenRuntime()
    entity = AddressableEntity(app="SomeChat", label="Pallavi", bounds=(10, 20, 100, 40))

    outcome = open_entity(entity, runtime)

    assert outcome.ok
    assert runtime.clicks == [("SomeChat", "Pallavi", (10, 20, 100, 40))]
    assert outcome.evidence["substrate"] == "addressable_entity"


def test_open_entity_accepts_a_point_without_a_label():
    runtime = FakeOpenRuntime()
    entity = AddressableEntity(app="SomeChat", label="", point=(100, 200), bounds=(88, 188, 24, 24))

    outcome = open_entity(entity, runtime)

    assert outcome.ok
    assert runtime.clicks[0][2] == (88, 188, 24, 24)


def test_open_entity_without_target_is_rejected():
    outcome = open_entity(AddressableEntity(app="SomeChat"), FakeOpenRuntime())
    assert not outcome.ok


def test_resolve_uses_overlay_when_world_is_present():
    class Entity:
        def __init__(self):
            self.id = 7
            self.label = "Pallavi"
            self.bounds = (1.0, 2.0, 3.0, 4.0)

    class Overlay:
        def resolve_target(self, world, semantic, action):
            return Entity()

    entity = resolve_addressable(
        "Pallavi",
        {"world": object(), "app": "WhatsApp"},
        Overlay(),
        app="WhatsApp",
    )
    assert entity.label == "Pallavi"
    assert entity.bounds == (1.0, 2.0, 3.0, 4.0)
    assert entity.entity_id == 7


def test_dismiss_sends_the_host_chord():
    runtime = FakeDismissRuntime()
    outcome = dismiss_transient(TransientChrome(app="SomeChat", surface="context_menu"), runtime)

    assert outcome.ok
    assert runtime.keys == [MACOS_DISMISS]
    assert outcome.evidence["substrate"] == "transient_chrome"


def test_overlay_may_declare_a_different_dismiss_chord():
    class Overlay:
        dismiss_affordance = KeyChord(code=99)

    outcome = dispatch(
        CapabilityRequest(name="dismiss_transient", app="Exotic"),
        Overlay(),
    )
    # Dispatch uses the real Mac runtime; we only check chord selection here.
    from plugin.agent.capabilities.dismiss_transient import dismiss_chord_for

    assert dismiss_chord_for(Overlay()).code == 99
    assert outcome.capability == "dismiss_transient"


def test_model_can_propose_open_entity():
    action, reason = proposal_to_action(
        UnifiedProposal(
            next_action={"family": "open_entity", "text": "Pallavi", "target_point": [100, 200]},
            confidence=0.9,
            point_scale=1.0,
        ),
        Goal(kind="forward_message"),
        WorldModel(),
    )
    assert reason == "admissible"
    assert action is not None
    assert action.action_family == "open_entity"
    assert action.semantic_target == "Pallavi"


def test_model_can_propose_dismiss_transient():
    action, reason = proposal_to_action(
        UnifiedProposal(next_action={"family": "dismiss_transient"}, confidence=0.9),
        Goal(kind="forward_message"),
        WorldModel(),
    )
    assert reason == "admissible"
    assert action is not None
    assert action.action_family == "dismiss_transient"


def test_realized_capabilities_remain_reversible():
    for name in ("locate_content", "open_entity", "dismiss_transient"):
        assert spec_by_name(name).reversible
