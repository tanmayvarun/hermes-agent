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


# Visual-verify gaps that mean absence cannot be trusted yet.
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


def locate_verify_can_establish_absence(
    execution_state: Any,
    *,
    document: Any = None,
    multimodal_ok: bool = True,
    proposal_model: str = "",
    coverage: Optional[float] = None,
    evidence_gaps: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Whether a paid visual verify can establish *absence* of the locate patient.

    ``query not visible`` is not itself ``still_unobservable``. Absence is only
    NOT_ACHIEVED when observation quality is sufficient to establish it.
    """
    if not multimodal_ok:
        return {"sufficient": False, "reason": "multimodal_failed"}
    model = str(proposal_model or "").strip().lower()
    if model in _INSUFFICIENT_VERIFY_MODELS:
        return {"sufficient": False, "reason": f"model_{model or 'empty'}"}
    if execution_state is not None and bool(
        getattr(execution_state, "perception_incomplete", False)
    ):
        return {"sufficient": False, "reason": "perception_incomplete"}
    doc = document
    if doc is None and execution_state is not None:
        doc = getattr(execution_state, "unified_world_document", None)
    if not isinstance(doc, dict):
        return {"sufficient": False, "reason": "document_missing"}
    if "objects" not in doc or not isinstance(doc.get("objects"), list):
        return {"sufficient": False, "reason": "object_inventory_missing"}

    cov = coverage
    gaps = list(evidence_gaps or [])
    if execution_state is not None:
        uni = getattr(execution_state, "last_unified_proposal", None)
        if isinstance(uni, dict):
            if cov is None and uni.get("coverage") is not None:
                try:
                    cov = float(uni.get("coverage"))
                except (TypeError, ValueError):
                    cov = None
            if not gaps and isinstance(uni.get("evidence_gaps"), list):
                gaps = [str(g) for g in uni.get("evidence_gaps") if str(g).strip()]
            if not model:
                model = str(uni.get("model") or "").strip().lower()
                if model in _INSUFFICIENT_VERIFY_MODELS:
                    return {"sufficient": False, "reason": f"model_{model}"}

    if cov is not None and float(cov) < 0.55:
        return {"sufficient": False, "reason": "coverage_low"}
    gap_blob = " ".join(str(g).lower() for g in gaps)
    if any(n in gap_blob for n in _INSUFFICIENT_VERIFY_GAP_NEEDLES):
        return {"sufficient": False, "reason": "evidence_gaps_insufficient"}
    return {"sufficient": True, "reason": "observed_absence_capable"}


def resolve_locate_effect_after_visual_verify(
    execution_state: Any,
    *,
    content_located: bool = False,
    query_visible: bool = False,
    multimodal_ok: bool = True,
    proposal_model: str = "",
    document: Any = None,
) -> Dict[str, Any]:
    """Resolve locate verify using observation quality, not bare visibility."""
    if content_located or query_visible:
        return resolve_locate_effect_verification(
            execution_state,
            content_located=content_located,
            query_visible=query_visible,
            still_unobservable=False,
        )
    quality = locate_verify_can_establish_absence(
        execution_state,
        document=document,
        multimodal_ok=multimodal_ok,
        proposal_model=proposal_model,
    )
    out = resolve_locate_effect_verification(
        execution_state,
        content_located=False,
        query_visible=False,
        still_unobservable=not bool(quality.get("sufficient")),
    )
    out["observation_sufficient"] = bool(quality.get("sufficient"))
    out["observation_reason"] = str(quality.get("reason") or "")
    return out


def resolve_locate_effect_verification(
    execution_state: Any,
    *,
    content_located: bool = False,
    query_visible: bool = False,
    still_unobservable: bool = False,
) -> Dict[str, Any]:
    """Close locate EffectStatus UNKNOWN after a verify PERCEIVE.

    ACHIEVED → clear debt; method succeeded.
    NOT_ACHIEVED (observed absence) → METHOD_INEFFECTIVE in this context.
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
            out.update({"resolved": True, "effect_status": "achieved"})
            return out

        execution_state.locate_effect_verify_owed = False
        if still_unobservable:
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
        else:
            execution_state.last_locate_effect_status = "not_achieved"
            if iframe is not None:
                iframe.pending_effect_verification = False
                record_method_status(iframe, mid, MethodStatus.INEFFECTIVE.value)
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
        ledger = list(getattr(execution_state, "locate_attempt_ledger", None) or [])
        if ledger:
            last = dict(ledger[-1])
            last["verification"] = (
                "still_unobservable" if still_unobservable else "not_achieved"
            )
            ledger[-1] = last
            execution_state.locate_attempt_ledger = ledger
        out.update(
            {
                "resolved": True,
                "effect_status": execution_state.last_locate_effect_status,
                "advance_method": True,
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
