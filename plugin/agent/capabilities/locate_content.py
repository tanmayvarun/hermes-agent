"""Locating content that is not currently on screen.

The actuator vocabulary is motor primitives -- click, scroll, type, hover. Every
one of them is a muscle movement, so "find the message about zarooratwala" has
no verb and has to be solved by open-ended motor search: scroll, look, scroll,
look. That search is O(length of the history) in a space where each step costs a
model call, which is why runs that took this route never terminated.

The missing verb is not "search WhatsApp". It is:

    locate_content(query) -> is there content matching this, on this surface?

which is true of every app that shows a scrollable body of content -- a chat, a
mailbox, a document, a channel, a log. The capability is app-independent; only
its realization differs, and an app declares which realization it supports:

    native find      Cmd+F, type, step through matches.       O(1) calls
    scroll and scan  reveal the surface a screenful at a time. O(surface)

Scroll-and-scan is the universal fallback, so an app that declares nothing still
has the capability -- just at the worse complexity. An app whose find affordance
is neither of these contributes a third realization without the capability, the
callers, or the other apps changing.

Two properties are deliberate.

It is an affordance, not a plan. It says this surface can be searched; it does
not say what to search for, whether to search at all, which result is the right
one, or what to do next. Those are judgments and they stay with the model. Only
the step size changes, not who decides.

The iteration runs here rather than in the model. "Scroll once more and look" is
not a question -- it has no judgment in it -- so paying a model call per screenful
buys nothing. The runtime iterates while the answer is mechanical, using a
substring probe over the accessibility text, and hands back the moment the answer
needs judgment: a candidate appeared, the surface ran out, or accessibility is
too blind to probe and only eyes will do.

Composites must be reversible. Bundling steps hides them from the gate that
inspects irreversible actions, so locating -- which only ever looks -- is safe to
bundle, and anything that sends, deletes or confirms is not and stays a primitive.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Protocol, Sequence, runtime_checkable

logger = logging.getLogger(__name__)

# A scan gives up after this many screenfuls even if the surface keeps changing,
# so an infinite or circular timeline cannot hold the loop forever.
DEFAULT_SCAN_BUDGET = 12

# Consecutive unchanged screenfuls that mean the surface has nothing left.
_EXHAUSTED_AFTER_UNCHANGED = 2


@dataclass(frozen=True)
class KeyChord:
    """A key press, as the host's key code plus modifiers."""

    code: int
    cmd: bool = False
    shift: bool = False

    def describe(self) -> str:
        mods = "".join(m for m, on in (("cmd+", self.cmd), ("shift+", self.shift)) if on)
        return f"{mods}{self.code}"


@dataclass(frozen=True)
class FindAffordance:
    """How one app exposes find-within-the-current-surface.

    Declared by the app overlay. Everything here is a fact about the host app --
    which chord opens find, which advances to the next hit -- and facts are looked
    up, not inferred, so none of it is worth a model call.
    """

    open_find: KeyChord
    next_match: Optional[KeyChord] = None
    dismiss: Optional[KeyChord] = None
    # Some apps scope find to the whole app rather than the open surface, which
    # changes what a hit means: the agent may land somewhere else entirely.
    scoped_to_surface: bool = True


@dataclass(frozen=True)
class LocateRequest:
    """Find content matching `query` on whatever surface is currently open."""

    query: str
    app: str
    surface: str = ""
    budget: int = DEFAULT_SCAN_BUDGET


@dataclass
class LocateOutcome:
    """What the attempt did, reported back to the model as evidence.

    `found` is never a claim that the right thing was located -- the runtime
    cannot know that -- only that something matching the query text is now
    reachable. Whether it is *the* one is the model's call on the next frame.
    """

    ok: bool
    realization: str
    steps: int = 0
    found: bool = False
    exhausted: bool = False
    surface_changed: bool = False
    message: str = ""

    def as_evidence(self) -> dict:
        return {
            "realization": self.realization,
            "steps": self.steps,
            "text_match_reachable": self.found,
            "surface_exhausted": self.exhausted,
            "surface_changed": self.surface_changed,
            "message": self.message,
        }


@runtime_checkable
class LocatorRuntime(Protocol):
    """The mechanical primitives a realization needs from the host.

    Kept as a narrow injected interface so realizations are testable without a
    display, and so the macOS specifics stay in one adapter.
    """

    def activate(self, app: str) -> None: ...

    def key(self, chord: KeyChord) -> None: ...

    def type_text(self, text: str) -> None: ...

    def scroll(self, direction: str, amount: int) -> None: ...

    def surface_text(self) -> str:
        """Readable text of the current surface, or "" when accessibility is blind."""

    def surface_signature(self) -> str:
        """Cheap identity of what is on screen, for detecting that nothing moved."""

    def text_input_focused(self) -> bool:
        """Whether a text field is focused and ready to receive the query."""


@runtime_checkable
class ContentLocator(Protocol):
    """One way of realizing locate_content on a host app."""

    name: str

    def available(self, request: LocateRequest) -> bool: ...

    def locate(self, request: LocateRequest, runtime: LocatorRuntime) -> LocateOutcome: ...


def _matches(haystack: str, query: str) -> bool:
    """Deterministic text presence -- not relevance, which is the model's job."""
    needle = (query or "").strip().lower()
    if not needle:
        return False
    return needle in (haystack or "").lower()


class NativeFind:
    """Use the app's own find affordance.

    Cheapest realization by far: one chord, one query, and the app does the
    seeking. It reports `found` only when the surface text confirms a hit, so an
    app that silently no-ops on the chord degrades to the next realization
    instead of reporting a success the screen does not support.

    Typing is the dangerous part and is gated on confirming the find field
    opened. In a messaging app the composer is the default focus, so typing a
    query into an unopened find and pressing Return does not search -- it sends
    the query to the person you were reading. That is an irreversible act
    smuggled inside a capability the gate believes is read-only, so the chord
    must be observed to have worked before a single character is typed.
    """

    name = "native_find"

    # The find field is a UI animation away, not a network call away.
    _CONFIRM_ATTEMPTS = 8
    _CONFIRM_INTERVAL = 0.12

    def __init__(self, affordance: FindAffordance, *, settle_seconds: float = 0.4) -> None:
        self.affordance = affordance
        self._settle = settle_seconds

    def available(self, request: LocateRequest) -> bool:
        return bool(request.query.strip())

    def _find_opened(self, runtime: LocatorRuntime, before: str) -> bool:
        for _ in range(self._CONFIRM_ATTEMPTS):
            if runtime.text_input_focused():
                return True
            # A surface that visibly changed also counts: some apps expose the
            # find bar without marking it focused, and refusing those would
            # discard the affordance over a reporting quirk.
            if runtime.surface_signature() != before:
                return True
            time.sleep(self._CONFIRM_INTERVAL)
        return False

    def locate(self, request: LocateRequest, runtime: LocatorRuntime) -> LocateOutcome:
        before = runtime.surface_signature()
        try:
            runtime.activate(request.app)
            runtime.key(self.affordance.open_find)

            if not self._find_opened(runtime, before):
                # Nothing to undo: the chord was a no-op and nothing was typed.
                return LocateOutcome(
                    ok=False,
                    realization=self.name,
                    message=(
                        f"{self.affordance.open_find.describe()} did not open a find field; "
                        "not typing, since focus may be a message composer"
                    ),
                )

            runtime.type_text(request.query)
            if self.affordance.next_match is not None:
                runtime.key(self.affordance.next_match)
            time.sleep(self._settle)
        except Exception as exc:
            logger.warning("native find failed on %s: %s", request.app, exc)
            return LocateOutcome(
                ok=False,
                realization=self.name,
                message=f"find affordance failed: {exc}",
            )

        text = runtime.surface_text()
        # No accessibility text means the probe cannot answer either way. Say so
        # rather than guessing; the model is about to look at the screen anyway.
        found = _matches(text, request.query) if text else False
        # Find field was confirmed and the query was typed — a completed attempt.
        # Always report surface_changed so LocateContent does not discard native
        # find and fall through to blind scroll_scan loops.
        return LocateOutcome(
            ok=True,
            realization=self.name,
            steps=1,
            found=found,
            surface_changed=True,
            message=(
                f"opened find ({self.affordance.open_find.describe()}) and queried {request.query!r}"
                if text
                else "queried via find; accessibility text unavailable, screen must be read"
            ),
        )


class ScrollScan:
    """Reveal the surface a screenful at a time.

    The universal fallback, so the capability exists on an app that declares no
    find affordance at all. The loop lives here rather than in the model because
    "scroll again and look" carries no judgment -- but it only stays here while a
    substring probe can answer. When accessibility gives no text the probe is
    blind, and the scan returns after a single screenful so the model can use the
    one instrument that still works, which is its eyes.
    """

    name = "scroll_scan"

    def __init__(self, *, direction: str = "up", amount: int = 5) -> None:
        self.direction = direction
        self.amount = amount

    def available(self, request: LocateRequest) -> bool:
        return True

    def locate(self, request: LocateRequest, runtime: LocatorRuntime) -> LocateOutcome:
        runtime.activate(request.app)

        if _matches(runtime.surface_text(), request.query):
            return LocateOutcome(
                ok=True,
                realization=self.name,
                steps=0,
                found=True,
                message="match already on the surface",
            )

        unchanged = 0
        last = runtime.surface_signature()
        budget = max(1, int(request.budget))

        for step in range(1, budget + 1):
            try:
                runtime.scroll(self.direction, self.amount)
            except Exception as exc:
                logger.warning("scroll scan failed on %s: %s", request.app, exc)
                return LocateOutcome(
                    ok=False,
                    realization=self.name,
                    steps=step - 1,
                    message=f"scroll failed: {exc}",
                )

            text = runtime.surface_text()
            signature = runtime.surface_signature()
            changed = signature != last
            last = signature

            if not text:
                # Blind: one screenful, then hand the frame to the model.
                return LocateOutcome(
                    ok=True,
                    realization=self.name,
                    steps=step,
                    surface_changed=changed,
                    message="revealed a screenful; accessibility text unavailable, screen must be read",
                )

            if _matches(text, request.query):
                return LocateOutcome(
                    ok=True,
                    realization=self.name,
                    steps=step,
                    found=True,
                    surface_changed=True,
                    message=f"match reachable after {step} screenful(s)",
                )

            unchanged = unchanged + 1 if not changed else 0
            if unchanged >= _EXHAUSTED_AFTER_UNCHANGED:
                return LocateOutcome(
                    ok=True,
                    realization=self.name,
                    steps=step,
                    exhausted=True,
                    message=f"surface stopped changing after {step} screenful(s); no match",
                )

        return LocateOutcome(
            ok=True,
            realization=self.name,
            steps=budget,
            surface_changed=True,
            message=f"scanned {budget} screenful(s) without a match; budget reached",
        )


@dataclass
class LocateContent:
    """The capability: try each declared realization until one answers.

    Ordering is cheapest-first, which is the overlay's declaration order. A
    realization that reports `ok=False` did not work on this host, so the next
    one is tried; that is how an app whose find chord does nothing still ends up
    scanning rather than reporting a hollow success.
    """

    realizations: Sequence[ContentLocator] = field(default_factory=tuple)

    def locate(self, request: LocateRequest, runtime: LocatorRuntime) -> LocateOutcome:
        attempted: List[str] = []
        last: Optional[LocateOutcome] = None

        for realization in self.realizations:
            if not realization.available(request):
                continue
            attempted.append(realization.name)
            outcome = realization.locate(request, runtime)
            last = outcome
            if outcome.ok and (outcome.found or outcome.exhausted or outcome.surface_changed):
                return outcome

        if last is not None:
            return last
        return LocateOutcome(
            ok=False,
            realization="none",
            message=f"no realization available (tried: {', '.join(attempted) or 'none'})",
        )


def default_realizations(find: Optional[FindAffordance] = None) -> List[ContentLocator]:
    """Cheapest-first realizations for an app, given whatever it declares."""
    realizations: List[ContentLocator] = []
    if find is not None:
        realizations.append(NativeFind(find))
    realizations.append(ScrollScan())
    return realizations


# macOS apps overwhelmingly share these, so an overlay usually declares the
# standard chord rather than inventing one.
MACOS_FIND = FindAffordance(
    open_find=KeyChord(code=3, cmd=True),  # Cmd+F
    next_match=KeyChord(code=36),  # Return steps to the first/next hit
    dismiss=KeyChord(code=53),  # Escape
)
