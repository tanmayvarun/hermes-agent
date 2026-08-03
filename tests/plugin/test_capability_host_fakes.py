"""Host-fake depth for every realized capability — not WhatsApp-shaped.

Mirrors the locate_content standard: if a capability only works for one app's
chord or one AX quirk, these fail.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from plugin.agent.capabilities.base import AddressableEntity, TransientChrome
from plugin.agent.capabilities.commit_irreversible import commit_irreversible
from plugin.agent.capabilities.dismiss_transient import MACOS_DISMISS, dismiss_chord_for, dismiss_transient
from plugin.agent.capabilities.invoke_affordance import invoke_affordance
from plugin.agent.capabilities.locate_content import KeyChord
from plugin.agent.capabilities.open_entity import open_entity, resolve_addressable
from plugin.agent.capabilities.reveal_actions import reveal_actions, reveal_mode_for
from plugin.agent.capabilities.select_content import select_content


class FakePointer:
    def __init__(self) -> None:
        self.ops: List[Tuple[str, str, Optional[tuple]]] = []
        self.activations = 0

    def activate(self, app: str) -> None:
        self.activations += 1

    def click(self, app: str, label: str, *, bounds=None):
        self.ops.append(("click", app, label, bounds))
        return True, f"clicked {label}"

    def hover(self, app: str, label: str, *, bounds=None):
        self.ops.append(("hover", app, label, bounds))
        return True, f"hovered {label}"

    def context_click(self, app: str, label: str, *, bounds=None):
        self.ops.append(("context_click", app, label, bounds))
        return True, f"context {label}"


class FakeDismiss:
    def __init__(self) -> None:
        self.keys: List[KeyChord] = []
        self.activations = 0

    def activate(self, app: str) -> None:
        self.activations += 1

    def key(self, chord: KeyChord) -> None:
        self.keys.append(chord)


def test_open_entity_works_on_a_nonexistent_messaging_app():
    rt = FakePointer()
    outcome = open_entity(
        AddressableEntity(app="Signalish", label="Alice", bounds=(10, 20, 80, 40)),
        rt,
    )
    assert outcome.ok
    assert rt.ops[0][1] == "Signalish"
    assert outcome.evidence["substrate"] == "addressable_entity"


def test_select_content_is_not_the_same_claim_as_open_entity():
    """Selecting focuses in-place; evidence must not say the surface navigated."""
    rt = FakePointer()
    outcome = select_content(
        AddressableEntity(app="Mailish", label="invoice.pdf", point=(100, 200), bounds=(88, 188, 24, 24)),
        rt,
    )
    assert outcome.ok
    assert outcome.capability == "select_content"
    assert "opened" not in outcome.message.lower()
    assert outcome.evidence.get("label") == "invoice.pdf"


def test_reveal_mode_is_an_overlay_declaration_not_core_logic():
    class HoverApp:
        reveal_mode = "hover"

    class ContextApp:
        reveal_mode = "context_click"

    assert reveal_mode_for(HoverApp()) == "hover"
    assert reveal_mode_for(ContextApp()) == "context_click"
    assert reveal_mode_for(object()) == "context_click"


def test_reveal_without_target_never_touches_the_pointer():
    rt = FakePointer()
    outcome = reveal_actions(AddressableEntity(app="Chat"), rt)
    assert not outcome.ok
    assert rt.ops == []


def test_invoke_on_exotic_app_still_blocks_delete():
    rt = FakePointer()
    outcome = invoke_affordance("ExoticIM", "Delete", rt)
    assert not outcome.ok
    assert rt.ops == []


def test_invoke_accepts_reply_as_reversible_on_any_host():
    rt = FakePointer()
    outcome = invoke_affordance("HangoutsLike", "Reply", rt, point=[50, 60])
    assert outcome.ok
    assert rt.ops[0][0] == "click"
    assert rt.ops[0][2] == "Reply"


def test_dismiss_uses_overlay_chord_not_hardcoded_escape_only():
    class Overlay:
        dismiss_affordance = KeyChord(code=12, cmd=True)

    assert dismiss_chord_for(Overlay()).code == 12
    rt = FakeDismiss()
    outcome = dismiss_transient(
        TransientChrome(app="Slackish", surface="context_menu"),
        rt,
        chord=dismiss_chord_for(Overlay()),
    )
    assert outcome.ok
    assert rt.keys[0].code == 12


def test_default_dismiss_is_escape_when_undeclared():
    rt = FakeDismiss()
    outcome = dismiss_transient(TransientChrome(app="Bare"), rt)
    assert outcome.ok
    assert rt.keys == [MACOS_DISMISS]


def test_commit_delete_is_allowlisted_and_marked_irreversible():
    rt = FakePointer()
    outcome = commit_irreversible("AnyApp", "Delete message", rt)
    assert outcome.ok
    assert outcome.evidence["irreversible"] is True


def test_resolve_addressable_prefers_overlay_without_assuming_whatsapp():
    class Row:
        id = 9
        label = "#general"
        bounds = (0.0, 10.0, 200.0, 30.0)

    class Overlay:
        def resolve_target(self, world, semantic, action):
            return Row()

    entity = resolve_addressable("general", {"world": object()}, Overlay(), app="Slackish")
    assert entity.app == "Slackish"
    assert entity.label == "#general"
    assert entity.entity_id == 9
