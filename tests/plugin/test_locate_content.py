"""locate_content is an affordance, not a WhatsApp feature.

These tests are written against apps that do not exist, on purpose. If the
capability only works when the host is WhatsApp, or only when accessibility is
healthy, it is a script wearing a capability's name and these fail.
"""

from __future__ import annotations

from typing import List, Optional

import pytest

from plugin.agent.capabilities.locate_content import (
    MACOS_FIND,
    FindAffordance,
    KeyChord,
    LocateContent,
    LocateRequest,
    NativeFind,
    ScrollScan,
    default_realizations,
)


class FakeSurface:
    """A scrollable body of content, revealed a screenful at a time.

    `screens` is what accessibility would report for each position. A screen of
    "" models an app that draws its content in a custom view, where the text
    probe is blind and only the pixels carry the answer.
    """

    def __init__(
        self,
        screens: List[str],
        *,
        find_opens: bool = False,
        find_jumps_to: Optional[int] = None,
    ) -> None:
        self.screens = screens
        self.position = 0
        self.find_opens = find_opens
        self.find_jumps_to = find_jumps_to
        self.find_field_open = False
        self.typed: List[str] = []
        self.keys: List[KeyChord] = []
        self.scrolls = 0
        self.activations = 0

    # -- LocatorRuntime ---------------------------------------------------

    def activate(self, app: str) -> None:
        self.activations += 1

    def key(self, chord: KeyChord) -> None:
        self.keys.append(chord)
        if chord == MACOS_FIND.open_find and self.find_opens:
            self.find_field_open = True
        elif chord == MACOS_FIND.next_match and self.find_field_open:
            if self.find_jumps_to is not None:
                self.position = self.find_jumps_to

    def type_text(self, text: str) -> None:
        self.typed.append(text)

    def scroll(self, direction: str, amount: int) -> None:
        self.scrolls += 1
        self.position = min(self.position + 1, len(self.screens) - 1)

    def surface_text(self) -> str:
        return self.screens[self.position]

    def surface_signature(self) -> str:
        return f"{self.position}:{self.find_field_open}"

    def text_input_focused(self) -> bool:
        return self.find_field_open

    def filter_field_ready(self) -> bool:
        return self.find_field_open


def _request(query: str = "zarooratwala", app: str = "SomeChatApp", budget: int = 12) -> LocateRequest:
    return LocateRequest(query=query, app=app, budget=budget)


# --- the capability exists regardless of the app -------------------------


def test_an_app_that_declares_nothing_still_has_the_capability():
    surface = FakeSurface(["hello", "how are you", "the zarooratwala link", "bye"])
    capability = LocateContent(realizations=default_realizations(find=None))

    outcome = capability.locate(_request(), surface)

    assert outcome.found
    assert outcome.realization == "scroll_scan"


def test_declaring_a_find_affordance_turns_a_scan_into_one_step():
    screens = ["a"] * 40 + ["the zarooratwala link"]
    surface = FakeSurface(screens, find_opens=True, find_jumps_to=40)
    capability = LocateContent(realizations=default_realizations(find=MACOS_FIND))

    outcome = capability.locate(_request(), surface)

    assert outcome.found
    assert outcome.realization == "native_find"
    assert outcome.steps == 1
    assert surface.scrolls == 0


def test_an_app_with_a_different_chord_needs_no_change_to_the_capability():
    # An app whose find is Cmd+E rather than Cmd+F contributes a declaration,
    # not a code path.
    cmd_e = FindAffordance(open_find=KeyChord(code=14, cmd=True), next_match=KeyChord(code=36))
    surface = FakeSurface(["a", "the zarooratwala link"], find_jumps_to=1)
    surface.find_opens = False

    # The fake only opens on MACOS_FIND, so teach it this app's chord.
    def key(chord: KeyChord) -> None:
        surface.keys.append(chord)
        if chord == cmd_e.open_find:
            surface.find_field_open = True
        elif chord == cmd_e.next_match and surface.find_field_open:
            surface.position = 1

    surface.key = key  # type: ignore[method-assign]

    outcome = LocateContent(realizations=default_realizations(find=cmd_e)).locate(_request(), surface)

    assert outcome.found
    assert outcome.realization == "native_find"


# --- typing into an unopened find must never happen ----------------------


def test_a_find_chord_that_does_nothing_never_types_the_query():
    """The hazard: in a chat app the composer holds focus, so typing a query
    into an unopened find and pressing Return sends it to the person you were
    reading -- an irreversible act hidden inside a read-only capability."""
    surface = FakeSurface(["a", "b", "c"], find_opens=False)

    outcome = NativeFind(MACOS_FIND).locate(_request(), surface)

    assert not outcome.ok
    assert surface.typed == []
    assert MACOS_FIND.next_match not in surface.keys


def test_a_dead_find_chord_falls_through_to_scanning():
    surface = FakeSurface(["a", "b", "the zarooratwala link"], find_opens=False)

    outcome = LocateContent(realizations=default_realizations(find=MACOS_FIND)).locate(_request(), surface)

    assert outcome.found
    assert outcome.realization == "scroll_scan"
    assert surface.typed == []


def test_prefer_and_skip_honor_method_frontier_without_repeating_native_find():
    """Information-exhausted native_find must not reseal ahead of scroll_scan."""
    screens = ["a", "b", "the zarooratwala link"]
    surface = FakeSurface(screens, find_opens=True, find_jumps_to=2)
    capability = LocateContent(realizations=default_realizations(find=MACOS_FIND))

    outcome = capability.locate(
        LocateRequest(
            query="zarooratwala",
            app="SomeChatApp",
            prefer_realization="scroll_scan",
            skip_realizations=("native_find",),
        ),
        surface,
    )

    assert outcome.realization == "scroll_scan"
    assert outcome.found
    assert surface.typed == []
    assert surface.scrolls >= 1


def test_signature_change_alone_does_not_authorize_typing():
    """Fail closed: chrome churn / Cmd+F no-op must not type into composer."""
    surface = FakeSurface(["a", "the zarooratwala link"])

    # Surface changes but never reports a find/filter field.
    def key(chord: KeyChord) -> None:
        surface.keys.append(chord)
        if chord == MACOS_FIND.open_find:
            surface.position = 1

    surface.key = key  # type: ignore[method-assign]

    outcome = NativeFind(MACOS_FIND).locate(_request(), surface)

    assert not outcome.ok
    assert surface.typed == []


def test_native_find_does_not_type_when_only_composer_focused():
    """Cmd+F no-op + composer-like focus ⇒ refuse type (wrong-locus field)."""
    surface = FakeSurface(["composer draft"], find_opens=False)

    def text_input_focused() -> bool:
        return True  # composer holds focus

    def filter_field_ready() -> bool:
        return False

    surface.text_input_focused = text_input_focused  # type: ignore[method-assign]
    surface.filter_field_ready = filter_field_ready  # type: ignore[method-assign]

    outcome = NativeFind(MACOS_FIND).locate(_request(), surface)

    assert not outcome.ok
    assert surface.typed == []


# --- the scan terminates -------------------------------------------------


def test_a_surface_that_stops_changing_is_reported_exhausted_not_retried():
    surface = FakeSurface(["top", "middle", "end"])

    outcome = ScrollScan().locate(_request(), surface)

    assert outcome.exhausted
    assert not outcome.found
    assert surface.scrolls < 12


def test_an_endless_surface_stops_at_the_budget():
    surface = FakeSurface([f"screen {i}" for i in range(500)])

    outcome = ScrollScan().locate(_request(budget=6), surface)

    assert not outcome.found
    assert not outcome.exhausted
    assert outcome.steps == 6


def test_content_already_on_screen_costs_no_scrolling():
    surface = FakeSurface(["the zarooratwala link is right here"])

    outcome = ScrollScan().locate(_request(), surface)

    assert outcome.found
    assert surface.scrolls == 0


# --- blindness is reported, not guessed ----------------------------------


def test_a_surface_the_probe_cannot_read_hands_back_after_one_screenful():
    """With no accessibility text the probe cannot answer, and the only
    instrument left is the model's eyes -- so burning the budget scrolling past
    unread screens would skip the very content it was sent to find."""
    surface = FakeSurface(["", "", "", ""])

    outcome = ScrollScan().locate(_request(), surface)

    assert outcome.ok
    assert outcome.steps == 1
    assert not outcome.found
    assert not outcome.exhausted
    assert "must be read" in outcome.message


def test_a_hit_is_reachability_not_relevance():
    """The runtime can say the text is present. Whether it is *the* message is
    a judgment, and the outcome must not claim to have made it."""
    surface = FakeSurface(["an old zarooratwala link", "a newer zarooratwala link"])

    outcome = ScrollScan().locate(_request(), surface)

    evidence = outcome.as_evidence()
    assert evidence["text_match_reachable"] is True
    assert "selected" not in evidence
    assert "target" not in evidence


# --- the capability decides nothing about the task -----------------------


def test_the_capability_never_chooses_the_query():
    with pytest.raises(TypeError):
        LocateRequest(app="SomeChatApp")  # type: ignore[call-arg]


def test_an_empty_query_is_not_something_to_go_looking_for():
    surface = FakeSurface(["a", "b"])

    assert not NativeFind(MACOS_FIND).available(_request(query="  "))
    outcome = LocateContent(realizations=[NativeFind(MACOS_FIND)]).locate(_request(query="  "), surface)

    assert not outcome.ok
    assert surface.typed == []


# --- the model can actually reach the verb -------------------------------


def _proposal(**next_action):
    from plugin.agent.unified_cognition import UnifiedProposal

    return UnifiedProposal(next_action=next_action, confidence=0.9)


def test_locate_content_is_in_the_vocabulary_offered_to_the_model():
    from plugin.agent.unified_cognition import ALLOWED_ACTIONS

    assert "locate_content" in ALLOWED_ACTIONS


def test_the_model_can_ask_to_locate_content():
    from plugin.agent.goal import Goal
    from plugin.agent.unified_cognition import proposal_to_action
    from plugin.worldmodel.model import WorldModel

    action, reason = proposal_to_action(
        _proposal(family="locate_content", text="zarooratwala"),
        Goal(kind="forward_message", app="SomeChatApp"),
        WorldModel(),
    )

    assert reason == "admissible"
    assert action is not None
    assert action.action_family == "locate_content"
    assert action.text == "zarooratwala"


def test_locating_needs_no_coordinate_because_the_runtime_supplies_the_mechanism():
    from plugin.agent.goal import Goal
    from plugin.agent.unified_cognition import proposal_to_action
    from plugin.worldmodel.model import WorldModel

    action, reason = proposal_to_action(
        _proposal(family="locate_content", text="zarooratwala", target_point=None, target_id=None),
        Goal(kind="forward_message", app="SomeChatApp"),
        WorldModel(),
    )

    assert reason == "admissible"
    assert action is not None


def test_locating_without_a_query_is_rejected():
    """What to look for is the judgment; the runtime has no business inventing it."""
    from plugin.agent.goal import Goal
    from plugin.agent.unified_cognition import proposal_to_action
    from plugin.worldmodel.model import WorldModel

    action, reason = proposal_to_action(
        _proposal(family="locate_content", text=""),
        Goal(kind="forward_message", app="SomeChatApp"),
        WorldModel(),
    )

    assert action is None
    assert reason == "locate_without_query"


# --- adding an app is a declaration, not a code path ---------------------


def test_an_overlay_that_declares_a_chord_gets_native_find_first():
    from plugin.agent.apps.base import content_locators

    class SlackLikeOverlay:
        app_names = ["Slack"]
        find_affordance = MACOS_FIND

    names = [r.name for r in content_locators(SlackLikeOverlay())]

    assert names == ["native_find", "scroll_scan"]


def test_an_overlay_that_declares_nothing_still_gets_the_capability():
    from plugin.agent.apps.base import content_locators

    class BareOverlay:
        app_names = ["SomeApp"]

    names = [r.name for r in content_locators(BareOverlay())]

    assert names == ["scroll_scan"]


def test_an_app_may_contribute_an_orthogonal_realization():
    """A host whose find is neither a chord nor scrolling -- a jump-to-date
    control, a server-side query -- adds a realization without the capability,
    the callers, or the other apps changing."""
    from plugin.agent.apps.base import content_locators
    from plugin.agent.capabilities.locate_content import LocateOutcome

    class ServerSideQuery:
        name = "server_side_query"

        def available(self, request) -> bool:
            return True

        def locate(self, request, runtime) -> LocateOutcome:
            return LocateOutcome(ok=True, realization=self.name, found=True)

    class ExoticOverlay:
        app_names = ["Exotic"]

        def content_locators(self):
            return [ServerSideQuery(), ScrollScan()]

    realizations = content_locators(ExoticOverlay())
    outcome = LocateContent(realizations=realizations).locate(_request(), FakeSurface(["x"]))

    assert outcome.realization == "server_side_query"
    assert outcome.found


def test_whatsapp_declares_the_standard_chord_and_nothing_procedural():
    from plugin.agent.apps.base import content_locators
    from plugin.agent.apps.whatsapp import WhatsAppOverlay

    names = [r.name for r in content_locators(WhatsAppOverlay())]

    assert names == ["native_find", "scroll_scan"]
