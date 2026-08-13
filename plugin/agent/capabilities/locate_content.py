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
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, runtime_checkable

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
    # MethodFrontier / information-gain: try this realization first when set.
    prefer_realization: str = ""
    # Realizations already information-exhausted under the current state.
    skip_realizations: tuple = ()


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

    def filter_field_ready(self) -> bool:
        """Whether a *filter/find* field (not a message composer) is ready.

        Optional for older fakes: NativeFind uses getattr and fails closed.
        """


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
        """Fail closed: only type when a filter/find field is evidenced.

        Bare ``text_input_focused()`` is insufficient (composer often holds
        focus). Surface-signature change alone is also insufficient (Cmd+F
        no-op can still churn chrome while the composer stays focused).
        """
        for _ in range(self._CONFIRM_ATTEMPTS):
            ready = getattr(runtime, "filter_field_ready", None)
            if callable(ready) and bool(ready()):
                return True
            # Legacy fakes that only expose text_input_focused + find_field_open:
            # accept focused input only when they also claim filter readiness via
            # attribute, never on composer-only focus.
            if bool(getattr(runtime, "find_field_open", False)) and runtime.text_input_focused():
                return True
            time.sleep(self._CONFIRM_INTERVAL)
            # `before` kept for call-site compatibility; signature change alone
            # must not authorize typing.
            _ = before
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

    When MethodFrontier prefers another realization (or marks one locally
    exhausted), ``prefer_realization`` / ``skip_realizations`` reorder and
    filter — otherwise AX-blind native_find would reseal forever on
    ``surface_changed=True`` without gaining information.
    """

    realizations: Sequence[ContentLocator] = field(default_factory=tuple)

    def locate(self, request: LocateRequest, runtime: LocatorRuntime) -> LocateOutcome:
        attempted: List[str] = []
        last: Optional[LocateOutcome] = None
        skip = {
            str(x).strip().lower()
            for x in (getattr(request, "skip_realizations", None) or ())
            if str(x).strip()
        }
        prefer = str(getattr(request, "prefer_realization", "") or "").strip().lower()
        ordered = list(self.realizations)
        if prefer:
            ordered = sorted(
                ordered,
                key=lambda r: (0 if str(r.name).lower() == prefer else 1),
            )

        for realization in ordered:
            name = str(realization.name or "").strip().lower()
            if name in skip:
                continue
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


# --- EffectStatus UNKNOWN contract (execution_ok ≠ effect established) --------

_LOCATE_METHOD_IDS = {
    "native_find": "locate_native_find",
    "scroll_scan": "locate_scroll_scan",
}
_LOCATE_REALIZATION_FROM_METHOD = {v: k for k, v in _LOCATE_METHOD_IDS.items()}

# Observation substrate cannot answer found/not-found → EffectStatus UNKNOWN.
_BLIND_OBSERVATION_NEEDLES = (
    "accessibility text unavailable",
    "screen must be read",
    "ax_probe_blind",
    "ax blind",
    "too blind",
    "must be read",
)
# Reliable probe saw the surface and reported absence → NOT_ACHIEVED (not UNKNOWN).
_RELIABLE_NEGATIVE_NEEDLES = (
    "without a match",
    "no match",
    "budget reached",
    "stopped changing",
    "surface stopped changing",
)


def locate_method_id(realization: str = "") -> str:
    r = str(realization or "").strip().lower()
    return _LOCATE_METHOD_IDS.get(r, f"locate_{r or 'unknown'}")


def _bump_locate_method_world_token(
    execution_state: Any, *, realization: str, surface_changed: bool
) -> None:
    """Scroll/scan state change can re-enable a previously exhausted locate method."""
    if execution_state is None:
        return
    r = str(realization or "").strip().lower()
    if r != "scroll_scan":
        return
    if not surface_changed:
        return
    try:
        tok = int(getattr(execution_state, "locate_method_world_token", 0) or 0)
        execution_state.locate_method_world_token = tok + 1
    except Exception:
        pass


def locate_method_context(execution_state: Any, *, query: str = "") -> Any:
    """MethodContext fingerprint for locate exhaustion / re-enable."""
    from plugin.agent.executive.effect_implications import method_context_from_state
    from plugin.agent.executive.intention_frame import MethodContext

    doc = None
    if execution_state is not None:
        doc = getattr(execution_state, "unified_world_document", None)
    doc = doc if isinstance(doc, dict) else {}
    try:
        ctx = method_context_from_state(execution_state, world=doc)
    except Exception:
        ctx = MethodContext()
    q = str(
        query or (getattr(execution_state, "last_locate_query", "") if execution_state else "")
        or ""
    ).strip().lower()
    tok = ""
    if execution_state is not None:
        tok = str(getattr(execution_state, "locate_method_world_token", 0) or 0)
    try:
        ctx.overlay = f"locate_q={q}|tok={tok}"
    except Exception:
        pass
    return ctx


def refresh_locate_method_frontier(execution_state: Any, *, query: str = "") -> List[str]:
    """Reactivate locate methods whose INEFFECTIVE context no longer matches."""
    if execution_state is None:
        return []
    try:
        from plugin.agent.executive.intention_frame import (
            active_intention_frame,
            clear_method_ineligible,
        )

        iframe = active_intention_frame(execution_state)
        if iframe is None:
            return []
        ctx = locate_method_context(execution_state, query=query)
        reactivated = list(iframe.method_frontier.refresh_method_frontier(ctx) or [])
        for mid in reactivated:
            clear_method_ineligible(iframe, mid)
        return reactivated
    except Exception:
        return []


def locate_skip_realizations(execution_state: Any, *, query: str = "") -> List[str]:
    """Realizations MethodFrontier has exhausted / made ineligible under current state."""
    if execution_state is None:
        return []
    refresh_locate_method_frontier(execution_state, query=query)
    out: List[str] = []
    try:
        from plugin.agent.executive.intention_frame import (
            MethodStatus,
            active_intention_frame,
        )

        iframe = active_intention_frame(execution_state)
        if iframe is None:
            return out
        fr = iframe.method_frontier
        blocked = set(fr.currently_ineligible)
        for mid, st in (fr.method_status or {}).items():
            if st == MethodStatus.INEFFECTIVE.value:
                blocked.add(mid)
        for mid in blocked:
            r = _LOCATE_REALIZATION_FROM_METHOD.get(str(mid))
            if r and r not in out:
                out.append(r)
            elif str(mid).startswith("locate_"):
                name = str(mid)[len("locate_") :]
                if name and name not in out:
                    out.append(name)
    except Exception:
        return out
    return out


def classify_locate_effect_status(
    *,
    ok: bool,
    found: bool,
    message: str = "",
    exhausted: bool = False,
) -> Dict[str, Any]:
    """Map locate evidence → EffectStatus + observation quality.

    ``ok && !found`` is **not** universally UNKNOWN:

    - blind / insufficient observation substrate → UNKNOWN (verify owed)
    - trustworthy negative or exhausted searchable domain → NOT_ACHIEVED
    """
    msg = str(message or "").lower()
    if not ok:
        return {
            "effect_status": "not_achieved",
            "observation_quality": 0.7,
            "reason": "execution_failed",
        }
    if found:
        return {
            "effect_status": "achieved",
            "observation_quality": 0.85,
            "reason": "text_match_reachable",
        }
    blind = any(n in msg for n in _BLIND_OBSERVATION_NEEDLES)
    if blind:
        return {
            "effect_status": "unknown",
            "observation_quality": 0.35,
            "reason": "observation_substrate_blind",
        }
    if exhausted:
        return {
            "effect_status": "not_achieved",
            "observation_quality": 0.8,
            "reason": "search_domain_exhausted",
        }
    if any(n in msg for n in _RELIABLE_NEGATIVE_NEEDLES):
        return {
            "effect_status": "not_achieved",
            "observation_quality": 0.75,
            "reason": "reliable_negative_observation",
        }
    # Probe completed without a blindness claim → treat as negative evidence.
    return {
        "effect_status": "not_achieved",
        "observation_quality": 0.7,
        "reason": "reliable_negative_default",
    }


def same_locate_unresolved(execution_state: Any, *, query: str = "") -> bool:
    """True when an identical locate must not be replayed (effect still UNKNOWN).

    While verify is pending, block. After resolve, MethodFrontier may advance —
    this helper only forbids *same-method* reseal, not frontier advancement.
    """
    if execution_state is None:
        return False
    q = str(query or getattr(execution_state, "last_locate_query", "") or "").strip()
    last_q = str(getattr(execution_state, "last_locate_query", "") or "").strip()
    if q and last_q and q.lower() != last_q.lower():
        return False
    if bool(getattr(execution_state, "locate_effect_verify_owed", False)):
        return True
    try:
        from plugin.agent.executive.intention_frame import active_intention_frame

        iframe = active_intention_frame(execution_state)
        if iframe is not None and bool(iframe.pending_effect_verification):
            pred = str(getattr(iframe.intention, "success_predicate", "") or "")
            if "located" in pred or "source_query" in pred:
                return True
    except Exception:
        pass
    # Frontier has another eligible SEARCH method → not same-method unresolved.
    if prefer_next_locate_realization(execution_state):
        return False
    status = str(getattr(execution_state, "last_locate_effect_status", "") or "").lower()
    if status in {"not_achieved", "unknown"} and last_q:
        return True
    return False


def _ensure_locate_search_frame(execution_state: Any, *, query: str):
    """Open/reuse SEARCH IntentionFrame with a MethodFrontier of locate methods."""
    from plugin.agent.executive.intention_frame import (
        EffectSpec,
        Intention,
        IntentionBudget,
        IntentionFrame,
        IntentionOrigin,
        MethodFrontier,
        MethodProvenance,
        MethodSpec,
        RetryPolicy,
        RetrySafety,
        ScoringPolicy,
        active_intention_frame,
        new_intention_id,
        push_intention_frame,
    )

    iframe = active_intention_frame(execution_state)
    want_pred = "source_query_located"
    if iframe is not None and str(
        getattr(iframe.intention, "success_predicate", "") or ""
    ) in {want_pred, "content_located", "source_query_located"}:
        # Ensure catalog knows both generic locate methods.
        cat = iframe.method_frontier.catalog
        if "locate_native_find" not in cat or "locate_scroll_scan" not in cat:
            for mid, settle in (
                ("locate_native_find", 800),
                ("locate_scroll_scan", 1200),
            ):
                if mid not in cat:
                    cat[mid] = MethodSpec(
                        id=mid,
                        capability="locate_content",
                        expected_effect=EffectSpec(
                            success_any=["source_query_located", "text_match_reachable"],
                            settle_window_ms=settle,
                        ),
                        retry_safety=(
                            RetrySafety.VERIFY_BEFORE_RETRY.value
                            if mid == "locate_native_find"
                            else RetrySafety.SAFE_TO_RETRY.value
                        ),
                        provenance=MethodProvenance.GENERIC_PRIOR.value,
                        reversibility=0.95 if mid == "locate_native_find" else 0.9,
                        risk=0.1 if mid == "locate_native_find" else 0.15,
                    )
                    if mid not in iframe.method_frontier.known_untried:
                        iframe.method_frontier.known_untried.append(mid)
        return iframe

    catalog = {
        "locate_native_find": MethodSpec(
            id="locate_native_find",
            capability="locate_content",
            expected_effect=EffectSpec(
                success_any=["source_query_located", "text_match_reachable"],
                settle_window_ms=800,
            ),
            retry_safety=RetrySafety.VERIFY_BEFORE_RETRY.value,
            provenance=MethodProvenance.GENERIC_PRIOR.value,
            reversibility=0.95,
            risk=0.1,
        ),
        "locate_scroll_scan": MethodSpec(
            id="locate_scroll_scan",
            capability="locate_content",
            expected_effect=EffectSpec(
                success_any=["source_query_located", "text_match_reachable"],
                settle_window_ms=1200,
            ),
            retry_safety=RetrySafety.SAFE_TO_RETRY.value,
            provenance=MethodProvenance.GENERIC_PRIOR.value,
            reversibility=0.9,
            risk=0.15,
        ),
    }
    iframe = IntentionFrame(
        intention=Intention(
            id=new_intention_id(),
            objective=f"Locate content matching {query!r} on the open surface",
            success_predicate=want_pred,
            scope="current_searchable_surface",
            created_from=IntentionOrigin(
                kind="executive_decision",
                triggering_uncertainty="source_query_unlocated",
            ),
        ),
        originating_meta_action="search",
        scoring_policy=ScoringPolicy.for_meta("search"),
        method_frontier=MethodFrontier(
            known_untried=list(catalog.keys()),
            catalog=catalog,
        ),
        retry_policy=RetryPolicy(same_method_max=1, try_alternatives=True),
        budget=IntentionBudget(
            max_methods=4, max_wall_time_s=60.0, max_perception_calls=8
        ),
    )
    push_intention_frame(execution_state, iframe)
    return iframe


def note_locate_outcome(
    execution_state: Any,
    *,
    query: str,
    ok: bool,
    found: bool,
    realization: str = "",
    message: str = "",
    surface_changed: bool = False,
    exhausted: bool = False,
) -> Dict[str, Any]:
    """Latch locate evidence into ExecutionState + IntentionFrame.

    Mirror of ``note_reveal_probe_handoff`` for searchable-surface locate:

    - ACHIEVED when match reachable
    - UNKNOWN only when observation/verification quality is insufficient
    - NOT_ACHIEVED for trustworthy negatives / exhausted search (no PERCEIVE debt)
    """
    out: Dict[str, Any] = {}
    if execution_state is None:
        return out
    q = str(query or "").strip()
    mid = locate_method_id(realization)
    classified = classify_locate_effect_status(
        ok=ok, found=found, message=message, exhausted=exhausted
    )
    effect_status = str(classified["effect_status"])
    obs_q = float(classified["observation_quality"])
    reason = str(classified["reason"])
    try:
        execution_state.last_locate_query = q
        execution_state.last_locate_realization = str(realization or "")[:40]
        execution_state.last_locate_found = bool(found)
        execution_state.last_locate_effect_status = effect_status
    except Exception:
        pass
    _bump_locate_method_world_token(
        execution_state,
        realization=str(realization or ""),
        surface_changed=bool(surface_changed),
    )

    ledger = list(getattr(execution_state, "locate_attempt_ledger", None) or [])
    entry = {
        "query": q[:80],
        "realization": str(realization or "")[:40],
        "method_id": mid,
        "execution_ok": bool(ok),
        "found": bool(found),
        "surface_changed": bool(surface_changed),
        "surface_exhausted": bool(exhausted),
        "effect_status": effect_status,
        "classify_reason": reason,
        "message": str(message or "")[:160],
        "desired_effect": "patient_visible_or_located",
        "verification": "owed" if effect_status == "unknown" else "not_required",
    }
    ledger.append(entry)
    execution_state.locate_attempt_ledger = ledger[-12:]
    out["ledger_entry"] = entry
    out["classify_reason"] = reason

    try:
        from plugin.agent.executive.intention_frame import (
            AttemptRecord,
            AttemptValidity,
            FailureClass,
            MethodOutcome,
            MethodStatus,
            apply_derived_status,
            mark_method_attempted,
            mark_method_ineligible,
            motivated_perceive_packet,
            record_method_status,
        )

        iframe = _ensure_locate_search_frame(execution_state, query=q)
        mark_method_attempted(iframe, mid)
        if effect_status == "achieved":
            record_method_status(iframe, mid, MethodStatus.SUCCEEDED.value)
            iframe.pending_effect_verification = False
            execution_state.locate_effect_verify_owed = False
            iframe.attempts.append(
                AttemptRecord(
                    method_id=mid,
                    execution_status="motor_ok",
                    observation_quality=obs_q,
                    method_outcome=MethodOutcome.EFFECT_OBSERVED.value,
                    attempt_validity=AttemptValidity.VALID.value,
                    method_status=MethodStatus.SUCCEEDED.value,
                    evidence_refs=["text_match_reachable", reason],
                )
            )
        elif effect_status == "unknown":
            # Insufficient observation — arm verify. Method not semantically
            # disproven: UNTRIED + currently_ineligible until verify resolves.
            mark_method_ineligible(iframe, mid)
            iframe.pending_effect_verification = True
            execution_state.locate_effect_verify_owed = True
            motivated_perceive_packet(
                iframe,
                purpose="effect_verification",
                question=(
                    f"Did locate({q!r} via {realization or 'find'}) surface a "
                    "binding-eligible content patient for the source query?"
                ),
                focus="searchable_surface_content",
            )
            iframe.attempts.append(
                AttemptRecord(
                    method_id=mid,
                    execution_status="motor_ok",
                    observation_quality=obs_q,
                    method_outcome=MethodOutcome.EFFECT_UNCERTAIN.value,
                    failure_class=FailureClass.EFFECT_UNCERTAIN.value,
                    attempt_validity=AttemptValidity.EFFECT_UNCERTAIN.value,
                    method_status=MethodStatus.UNTRIED.value,
                    evidence_refs=[reason, "effect_unknown"],
                )
            )
            out["pending_effect_verification"] = True
        else:
            # Trustworthy negative / exhausted / execution fail — method ineffective
            # in this MethodContext; no visual-verify debt.
            record_method_status(iframe, mid, MethodStatus.INEFFECTIVE.value)
            mark_method_ineligible(iframe, mid)
            iframe.pending_effect_verification = False
            execution_state.locate_effect_verify_owed = False
            iframe.attempts.append(
                AttemptRecord(
                    method_id=mid,
                    execution_status="motor_fail" if not ok else "motor_ok",
                    observation_quality=obs_q,
                    method_outcome=MethodOutcome.EFFECT_ABSENT.value,
                    failure_class=FailureClass.METHOD_INEFFECTIVE.value,
                    attempt_validity=AttemptValidity.VALID.value,
                    method_status=MethodStatus.INEFFECTIVE.value,
                    evidence_refs=[reason, str(message or "locate_failed")[:80]],
                )
            )
        apply_derived_status(iframe)
        out["intention_id"] = iframe.intention.id
        out["effect_status"] = effect_status
        out["method_id"] = mid
        out["eligible_methods"] = list(iframe.method_frontier.eligible_methods())
    except Exception as exc:
        logger.debug("note_locate_outcome intention bookkeeping failed: %s", exc)
        if effect_status == "unknown":
            try:
                execution_state.locate_effect_verify_owed = True
            except Exception:
                pass
    return out


# Visual-verify gaps that mean an explicit answer is not trustworthy yet.
_INSUFFICIENT_VERIFY_GAP_NEEDLES = (
    "unreadable",
    "can't see",
    "cannot see",
    "could not see",
    "ax unavailable",
    "accessibility",
    "held_last_good",
    "stale",
    "incomplete",
    "needs_more_evidence",
    "screen must be read",
    "blind",
)

# Idle reuse is not a paid visual verification look.
_INSUFFICIENT_VERIFY_MODELS = frozenset({"phash_reuse", "held_last_good", "reuse"})

# Explicit answers to the motivated locate-verification question (not inventory omission).
_EXPLICIT_LOCATE_NEGATIVE_NEEDLES = (
    "source_query_not_surfaced",
    "locate_effect_observed=false",
    "locate_effect_observed:false",
    "locate_effect_answer=no",
    "locate_effect_answer:no",
    "locate did not surface",
    "did not surface a binding-eligible",
    "locate_effect=absent",
)
_EXPLICIT_LOCATE_POSITIVE_NEEDLES = (
    "source_query_located",
    "locate_effect_observed=true",
    "locate_effect_observed:true",
    "locate_effect_answer=yes",
    "locate_effect_answer:yes",
    "locate_effect=achieved",
)
_EXPLICIT_ANSWER_YES = frozenset({"yes", "true", "achieved", "observed", "surfaced"})
_EXPLICIT_ANSWER_NO = frozenset(
    {"no", "false", "absent", "not_achieved", "not-achieved", "unobserved"}
)


def _coerce_locate_effect_answer_token(raw: Any) -> str:
    tok = str(raw if raw is not None else "").strip().lower()
    if not tok:
        return ""
    if tok in _EXPLICIT_ANSWER_YES:
        return "yes"
    if tok in _EXPLICIT_ANSWER_NO:
        return "no"
    if tok in {"unknown", "uncertain", "unsure"}:
        return "unknown"
    return ""


def extract_locate_effect_verify_answer(
    execution_state: Any,
    *,
    document: Any = None,
    evidence_gaps: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """YES / NO / UNKNOWN for the named locate-effect verification question.

    High-quality perception alone does **not** invent NO. An item missing from
    the capped task-relevant object inventory is not an authoritative negative.
    """
    doc = document
    if doc is None and execution_state is not None:
        doc = getattr(execution_state, "unified_world_document", None)
    bags: List[Dict[str, Any]] = []
    if isinstance(doc, dict):
        bags.append(doc)
    if execution_state is not None:
        uni = getattr(execution_state, "last_unified_proposal", None)
        if isinstance(uni, dict):
            bags.append(uni)
            obs = uni.get("observed_state")
            if isinstance(obs, dict):
                bags.append(obs)

    for bag in bags:
        # Typed predicate / answer fields from world or proposal.
        if bag.get("source_query_not_surfaced") is True:
            return {"answer": "no", "source": "source_query_not_surfaced"}
        if bag.get("source_query_located") is True or bag.get("content_located") is True:
            return {"answer": "yes", "source": "source_query_located"}
        if "locate_effect_observed" in bag:
            obs = bag.get("locate_effect_observed")
            if obs is True:
                return {"answer": "yes", "source": "locate_effect_observed"}
            if obs is False:
                return {"answer": "no", "source": "locate_effect_observed"}
        ans = _coerce_locate_effect_answer_token(bag.get("locate_effect_answer"))
        if ans:
            return {"answer": ans, "source": "locate_effect_answer"}
        for field in (
            "verified_effect_predicates",
            "achieved_effects",
            "effect_predicates",
        ):
            raw = bag.get(field)
            if not isinstance(raw, (list, tuple, set)):
                continue
            blob = " ".join(str(x).lower() for x in raw if str(x).strip())
            if any(n in blob for n in _EXPLICIT_LOCATE_NEGATIVE_NEEDLES):
                return {"answer": "no", "source": field}
            if any(n in blob for n in _EXPLICIT_LOCATE_POSITIVE_NEEDLES):
                return {"answer": "yes", "source": field}

    gaps = list(evidence_gaps or [])
    if not gaps and execution_state is not None:
        uni = getattr(execution_state, "last_unified_proposal", None)
        if isinstance(uni, dict) and isinstance(uni.get("evidence_gaps"), list):
            gaps = [str(g) for g in uni.get("evidence_gaps") if str(g).strip()]
    gap_blob = " ".join(str(g).lower() for g in gaps)
    # Only accept gap *answers*, not restated verification questions.
    if gap_blob and "?" not in gap_blob:
        if any(n in gap_blob for n in _EXPLICIT_LOCATE_NEGATIVE_NEEDLES):
            return {"answer": "no", "source": "evidence_gap_answer"}
        if any(n in gap_blob for n in _EXPLICIT_LOCATE_POSITIVE_NEEDLES):
            return {"answer": "yes", "source": "evidence_gap_answer"}
    return {"answer": "unknown", "source": "no_explicit_claim"}


def locate_verify_observation_trustworthy(
    execution_state: Any,
    *,
    document: Any = None,
    multimodal_ok: bool = True,
    proposal_model: str = "",
    coverage: Optional[float] = None,
    evidence_gaps: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Quality gates for trusting an *already explicit* locate-effect answer."""
    if not multimodal_ok:
        return {"trustworthy": False, "reason": "multimodal_failed"}
    model = str(proposal_model or "").strip().lower()
    if model in _INSUFFICIENT_VERIFY_MODELS:
        return {"trustworthy": False, "reason": f"model_{model or 'empty'}"}
    if execution_state is not None and bool(
        getattr(execution_state, "perception_incomplete", False)
    ):
        return {"trustworthy": False, "reason": "perception_incomplete"}
    doc = document
    if doc is None and execution_state is not None:
        doc = getattr(execution_state, "unified_world_document", None)
    if not isinstance(doc, dict):
        return {"trustworthy": False, "reason": "document_missing"}

    cov = coverage
    gaps = list(evidence_gaps or [])
    conf: Optional[float] = None
    if execution_state is not None:
        uni = getattr(execution_state, "last_unified_proposal", None)
        if isinstance(uni, dict):
            if cov is None and uni.get("coverage") is not None:
                try:
                    cov = float(uni.get("coverage"))
                except (TypeError, ValueError):
                    cov = None
            if uni.get("confidence") is not None:
                try:
                    conf = float(uni.get("confidence"))
                except (TypeError, ValueError):
                    conf = None
            if not gaps and isinstance(uni.get("evidence_gaps"), list):
                gaps = [str(g) for g in uni.get("evidence_gaps") if str(g).strip()]
            if not model:
                model = str(uni.get("model") or "").strip().lower()
                if model in _INSUFFICIENT_VERIFY_MODELS:
                    return {"trustworthy": False, "reason": f"model_{model}"}

    if cov is not None and float(cov) < 0.55:
        return {"trustworthy": False, "reason": "coverage_low"}
    if conf is not None and float(conf) < 0.55:
        return {"trustworthy": False, "reason": "confidence_low"}
    gap_blob = " ".join(str(g).lower() for g in gaps)
    if any(n in gap_blob for n in _INSUFFICIENT_VERIFY_GAP_NEEDLES):
        return {"trustworthy": False, "reason": "evidence_gaps_insufficient"}
    return {"trustworthy": True, "reason": "quality_ok"}


def locate_verify_can_establish_absence(
    execution_state: Any,
    *,
    document: Any = None,
    multimodal_ok: bool = True,
    proposal_model: str = "",
    coverage: Optional[float] = None,
    evidence_gaps: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """NOT_ACHIEVED only when an explicit negative claim is quality-validated.

    ``query not in object inventory`` + high coverage must remain UNKNOWN.
    """
    claim = extract_locate_effect_verify_answer(
        execution_state, document=document, evidence_gaps=evidence_gaps
    )
    answer = str(claim.get("answer") or "unknown")
    if answer != "no":
        return {
            "sufficient": False,
            "reason": f"no_explicit_negative:{answer}",
            "answer": answer,
            "claim_source": str(claim.get("source") or ""),
        }
    quality = locate_verify_observation_trustworthy(
        execution_state,
        document=document,
        multimodal_ok=multimodal_ok,
        proposal_model=proposal_model,
        coverage=coverage,
        evidence_gaps=evidence_gaps,
    )
    if not bool(quality.get("trustworthy")):
        return {
            "sufficient": False,
            "reason": str(quality.get("reason") or "untrusted_negative"),
            "answer": "no",
            "claim_source": str(claim.get("source") or ""),
        }
    return {
        "sufficient": True,
        "reason": "explicit_negative_validated",
        "answer": "no",
        "claim_source": str(claim.get("source") or ""),
    }


def resolve_locate_effect_after_visual_verify(
    execution_state: Any,
    *,
    content_located: bool = False,
    query_visible: bool = False,
    multimodal_ok: bool = True,
    proposal_model: str = "",
    document: Any = None,
) -> Dict[str, Any]:
    """Resolve locate verify from explicit YES/NO/UNKNOWN + quality gates.

    Trustworthy visual verification that does **not** establish the desired
    patient is ``verified_no_progress``: the attempt's information value is
    exhausted under the current state. That is distinct from incomplete
    observation (``still_unobservable``) and from an explicit world-level
    negative (``not_achieved``).
    """
    if content_located or query_visible:
        return resolve_locate_effect_verification(
            execution_state,
            content_located=content_located,
            query_visible=query_visible,
            still_unobservable=False,
        )
    # Positive explicit claim without inventory hit still counts as ACHIEVED.
    claim = extract_locate_effect_verify_answer(execution_state, document=document)
    if str(claim.get("answer") or "") == "yes":
        quality = locate_verify_observation_trustworthy(
            execution_state,
            document=document,
            multimodal_ok=multimodal_ok,
            proposal_model=proposal_model,
        )
        if bool(quality.get("trustworthy")):
            out = resolve_locate_effect_verification(
                execution_state,
                content_located=True,
                query_visible=False,
                still_unobservable=False,
            )
            out["locate_effect_answer"] = "yes"
            out["observation_reason"] = str(claim.get("source") or "")
            return out
    absence = locate_verify_can_establish_absence(
        execution_state,
        document=document,
        multimodal_ok=multimodal_ok,
        proposal_model=proposal_model,
    )
    if bool(absence.get("sufficient")):
        out = resolve_locate_effect_verification(
            execution_state,
            content_located=False,
            query_visible=False,
            still_unobservable=False,
        )
        out["observation_sufficient"] = True
        out["observation_reason"] = str(absence.get("reason") or "")
        out["locate_effect_answer"] = str(absence.get("answer") or "no")
        return out

    trust = locate_verify_observation_trustworthy(
        execution_state,
        document=document,
        multimodal_ok=multimodal_ok,
        proposal_model=proposal_model,
    )
    if bool(trust.get("trustworthy")):
        # Paid look; patient not established → exhaust this method@state.
        out = resolve_locate_effect_verification(
            execution_state,
            content_located=False,
            query_visible=False,
            still_unobservable=False,
            verified_no_progress=True,
        )
        out["observation_sufficient"] = False
        out["observation_reason"] = (
            f"verified_no_progress:{trust.get('reason') or 'quality_ok'}"
        )
        out["locate_effect_answer"] = str(
            absence.get("answer") or claim.get("answer") or "unknown"
        )
        return out

    out = resolve_locate_effect_verification(
        execution_state,
        content_located=False,
        query_visible=False,
        still_unobservable=True,
    )
    out["observation_sufficient"] = False
    out["observation_reason"] = str(
        trust.get("reason") or absence.get("reason") or "untrusted_observation"
    )
    out["locate_effect_answer"] = str(
        absence.get("answer") or claim.get("answer") or "unknown"
    )
    return out


def resolve_locate_effect_verification(
    execution_state: Any,
    *,
    content_located: bool = False,
    query_visible: bool = False,
    still_unobservable: bool = False,
    verified_no_progress: bool = False,
) -> Dict[str, Any]:
    """Close locate EffectStatus UNKNOWN after a verify PERCEIVE.

    ACHIEVED → clear debt; method succeeded.
    NOT_ACHIEVED (observed absence) → METHOD_INEFFECTIVE in this context.
    VERIFIED_NO_PROGRESS → verification paid; desired effect not observed;
    this method@state is locally exhausted (INEFFECTIVE in MethodContext) so
    SEARCH must choose an information-gaining alternative. Re-enabled when
    MethodContext changes (query / surface / scroll token).
    STILL_UNOBSERVABLE → clear verify debt; method stays *currently ineligible*
    but is **not** semantically INEFFECTIVE (lack of observability ≠ doesn't work).
    """
    out: Dict[str, Any] = {"resolved": False}
    if execution_state is None:
        return out
    if not bool(getattr(execution_state, "locate_effect_verify_owed", False)):
        try:
            from plugin.agent.executive.intention_frame import active_intention_frame

            iframe = active_intention_frame(execution_state)
            if iframe is None or not iframe.pending_effect_verification:
                return out
        except Exception:
            return out

    mid = locate_method_id(str(getattr(execution_state, "last_locate_realization", "") or ""))
    try:
        from plugin.agent.executive.intention_frame import (
            AttemptRecord,
            AttemptValidity,
            FailureClass,
            MethodOutcome,
            MethodStatus,
            active_intention_frame,
            apply_derived_status,
            mark_method_ineligible,
            record_method_status,
        )

        iframe = active_intention_frame(execution_state)
        if content_located or query_visible:
            execution_state.locate_effect_verify_owed = False
            execution_state.last_locate_effect_status = "achieved"
            execution_state.last_locate_found = True
            if iframe is not None:
                iframe.pending_effect_verification = False
                record_method_status(iframe, mid, MethodStatus.SUCCEEDED.value)
                apply_derived_status(iframe)
            ledger = list(getattr(execution_state, "locate_attempt_ledger", None) or [])
            if ledger:
                last = dict(ledger[-1])
                last["verification"] = "paid"
                last["effect_after_verification"] = "observed"
                ledger[-1] = last
                execution_state.locate_attempt_ledger = ledger
            out.update({"resolved": True, "effect_status": "achieved"})
            return out

        execution_state.locate_effect_verify_owed = False
        if still_unobservable and not verified_no_progress:
            # Epistemically unresolved: do not accumulate false "method fails".
            execution_state.last_locate_effect_status = "unknown"
            if iframe is not None:
                iframe.pending_effect_verification = False
                mark_method_ineligible(iframe, mid)
                # Keep MethodStatus UNTRIED — currently_ineligible blocks replay.
                iframe.attempts.append(
                    AttemptRecord(
                        method_id=mid,
                        execution_status="motor_ok",
                        observation_quality=0.3,
                        method_outcome=MethodOutcome.EFFECT_UNCERTAIN.value,
                        failure_class=FailureClass.EFFECT_UNCERTAIN.value,
                        attempt_validity=AttemptValidity.EFFECT_UNCERTAIN.value,
                        method_status=MethodStatus.UNTRIED.value,
                        evidence_refs=["visual_still_unobservable"],
                    )
                )
                apply_derived_status(iframe)
                out["eligible_methods"] = list(iframe.method_frontier.eligible_methods())
            verify_tag = "still_unobservable"
            effect_after = "unobservable"
        elif verified_no_progress:
            # Paid verification; patient unresolved → exhaust equivalent attempt.
            # Keep effect_status unknown (do not invent world-level absence).
            execution_state.last_locate_effect_status = "unknown"
            if iframe is not None:
                iframe.pending_effect_verification = False
                ctx = locate_method_context(
                    execution_state,
                    query=str(getattr(execution_state, "last_locate_query", "") or ""),
                )
                record_method_status(
                    iframe,
                    mid,
                    MethodStatus.INEFFECTIVE.value,
                    method_context=ctx,
                )
                iframe.attempts.append(
                    AttemptRecord(
                        method_id=mid,
                        execution_status="motor_ok",
                        observation_quality=0.7,
                        method_outcome=MethodOutcome.EFFECT_ABSENT.value,
                        failure_class=FailureClass.METHOD_INEFFECTIVE.value,
                        attempt_validity=AttemptValidity.VALID.value,
                        method_status=MethodStatus.INEFFECTIVE.value,
                        evidence_refs=[
                            "visual_verify_paid",
                            "effect_after_verification=not_observed",
                        ],
                    )
                )
                apply_derived_status(iframe)
                out["eligible_methods"] = list(iframe.method_frontier.eligible_methods())
            verify_tag = "verified_no_progress"
            effect_after = "not_observed"
        else:
            execution_state.last_locate_effect_status = "not_achieved"
            if iframe is not None:
                iframe.pending_effect_verification = False
                ctx = locate_method_context(
                    execution_state,
                    query=str(getattr(execution_state, "last_locate_query", "") or ""),
                )
                record_method_status(
                    iframe,
                    mid,
                    MethodStatus.INEFFECTIVE.value,
                    method_context=ctx,
                )
                mark_method_ineligible(iframe, mid)
                iframe.attempts.append(
                    AttemptRecord(
                        method_id=mid,
                        execution_status="motor_ok",
                        observation_quality=0.6,
                        method_outcome=MethodOutcome.EFFECT_ABSENT.value,
                        failure_class=FailureClass.METHOD_INEFFECTIVE.value,
                        attempt_validity=AttemptValidity.VALID.value,
                        method_status=MethodStatus.INEFFECTIVE.value,
                        evidence_refs=["visual_verify_no_query_patient"],
                    )
                )
                apply_derived_status(iframe)
                out["eligible_methods"] = list(iframe.method_frontier.eligible_methods())
            verify_tag = "not_achieved"
            effect_after = "absent"
        ledger = list(getattr(execution_state, "locate_attempt_ledger", None) or [])
        if ledger:
            last = dict(ledger[-1])
            last["verification"] = verify_tag
            last["effect_after_verification"] = effect_after
            ledger[-1] = last
            execution_state.locate_attempt_ledger = ledger
        out.update(
            {
                "resolved": True,
                "effect_status": execution_state.last_locate_effect_status,
                "advance_method": True,
                "verification": verify_tag,
            }
        )
    except Exception as exc:
        logger.debug("resolve_locate_effect_verification failed: %s", exc)
        try:
            execution_state.locate_effect_verify_owed = False
        except Exception:
            pass
    return out


def prefer_next_locate_realization(execution_state: Any) -> str:
    """Next locate realization from MethodFrontier.eligible_methods() — not a ladder.

    ``scroll_scan`` is one registered MethodSpec; the frontier ranks what remains
    eligible after the current method route is ineligible / ineffective.
    """
    if execution_state is None:
        return ""
    if bool(getattr(execution_state, "locate_effect_verify_owed", False)):
        return ""
    try:
        from plugin.agent.executive.intention_frame import active_intention_frame

        q = str(getattr(execution_state, "last_locate_query", "") or "")
        refresh_locate_method_frontier(execution_state, query=q)
        iframe = active_intention_frame(execution_state)
        if iframe is None:
            return ""
        current = locate_method_id(
            str(getattr(execution_state, "last_locate_realization", "") or "")
        )
        for mid in iframe.method_frontier.eligible_methods():
            if mid == current:
                continue
            if mid in _LOCATE_REALIZATION_FROM_METHOD:
                return _LOCATE_REALIZATION_FROM_METHOD[mid]
            if str(mid).startswith("locate_"):
                return str(mid)[len("locate_") :]
        return ""
    except Exception:
        return ""
