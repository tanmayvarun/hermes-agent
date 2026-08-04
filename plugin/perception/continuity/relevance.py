"""Did the screen change *in the agent's way*, or merely change?

Detecting that a screen changed is easy and nearly useless. A screen under a real
user is never still: clocks tick, unread badges increment, banners slide in and
out, contacts come online. An agent that abandoned its decision whenever anything
moved would never act — it would perceive for a minute, notice the clock had
advanced, and start over. Equally, an agent that ignored change would click the
row that something slid out from under it.

The judgement that separates those is narrower than "changed": *did what changed
intervene in the work?* That is answerable only because the decision knows what
it is reaching for — a semantic target with resolved bounds. Checking the live
rectangle against that intent is what lets the agent stay composed about a
notification in the corner while refusing to click a chat row that is no longer
the row it chose.

Indifference to irrelevant change is achieved structurally rather than by
classifying it: the check never looks anywhere but the target, so a banner in the
corner cannot produce a verdict at all. There is deliberately no "something moved
elsewhere" outcome, because nothing here is in a position to observe one.

* ``CONFIRMED`` — the target is still what the decision expected. Commit.
* ``FOCUS_DISTURBED`` — the target is not. Abort and re-perceive; the coordinates
  mean something else now.
* ``SURFACE_LOST`` — the window or the foreground moved out from under us. Abort;
  this needs reclaiming before anything else can be trusted.
* ``INDETERMINATE`` — too little could be read to tell. Fails open, so a missing
  signal never wedges the agent, except where the caller declares the action too
  costly to get wrong.

One gap is known and left open deliberately. A modal that opens *away* from the
target still swallows the click, and none of these readings can see it: the
target reads correctly because the overlay does not cover it. Occlusion *of* the
target is caught, since the window server composites overlapping windows into the
captured rectangle, so the read-back sees whatever is really on top.

This is the part of the design meant to grow. Every verdict carries its evidence
so that real runs accumulate a record of what changed and whether it mattered —
the raw material for sharpening the rules, and later for handing genuinely
ambiguous cases to a model rather than to a string comparison.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence

from plugin.perception.continuity.witness import (
    ReadBack,
    Surface,
    TargetExpectation,
    expectation_from,
    hamming,
    norm_app,
    read_back,
    take_surface,
)

CONFIRMED = "confirmed"
FOCUS_DISTURBED = "focus_disturbed"
SURFACE_LOST = "surface_lost"
INDETERMINATE = "indeterminate"

# A window that shifted more than this has invalidated every coordinate the
# decision resolved against it.
WINDOW_DRIFT_PX = 2.0

# Differing bits tolerated for a text-free (icon) target before it counts as
# changed. Icons are structural and small, so this stays tight.
ICON_TOLERANCE_BITS = 6


def _same_app(a: Any, b: Any) -> bool:
    left, right = norm_app(a), norm_app(b)
    if not left or not right:
        return True  # unknown on either side is never positive evidence of a switch
    return left == right or left in right or right in left


@dataclass(frozen=True)
class ContinuityVerdict:
    """The judgement, and everything it rested on.

    ``may_commit`` is the only field the control loop must obey. The rest exists
    so a human reading a trace can see why a run aborted, and so the thresholds
    can be tuned against real behaviour rather than intuition.
    """

    state: str = INDETERMINATE
    reason: str = ""
    may_commit: bool = True
    age_s: float = 0.0
    evidence: Dict[str, Any] = field(default_factory=dict)

    @property
    def disturbed(self) -> bool:
        return self.state in {FOCUS_DISTURBED, SURFACE_LOST}

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "state": self.state,
            "may_commit": bool(self.may_commit),
            "age_s": round(float(self.age_s), 2),
        }
        if self.reason:
            out["reason"] = self.reason
        if self.evidence:
            out["evidence"] = self.evidence
        return out

    def describe(self) -> str:
        return f"{self.state}: {self.reason}" if self.reason else self.state


def assess_continuity(
    *,
    expectation: TargetExpectation,
    perceived_surface: Optional[Surface],
    live_surface: Optional[Surface],
    observation: Optional[ReadBack] = None,
    task_app: str = "",
    resolved_icon_hash: str = "",
) -> ContinuityVerdict:
    """Decide whether the pending action may still commit.

    ``perceived_surface`` is stamped when the screen was photographed;
    ``live_surface`` immediately before actuation. ``observation`` is the live
    read-back of the target rectangle — passed in rather than taken here so the
    caller controls when the pixels are touched and the whole judgement stays
    unit-testable without a screen.
    """
    age = 0.0
    if perceived_surface is not None and live_surface is not None:
        age = max(0.0, float(live_surface.taken_at) - float(perceived_surface.taken_at))

    evidence: Dict[str, Any] = {"expectation": expectation.to_dict()}
    if perceived_surface is not None:
        evidence["perceived_surface"] = perceived_surface.to_dict()
    if live_surface is not None:
        evidence["live_surface"] = live_surface.to_dict()
    if observation is not None:
        evidence["read_back"] = observation.to_dict()

    fail_open = not expectation.irreversible

    def verdict(state: str, reason: str, may_commit: bool) -> ContinuityVerdict:
        return ContinuityVerdict(
            state=state, reason=reason, may_commit=may_commit, age_s=age, evidence=evidence
        )

    # --- 1. The surface. Cheapest, and the failures here invalidate everything
    #        downstream, so nothing else is worth reading until they pass.
    if live_surface is not None and live_surface.readable:
        if (
            expectation.needs_foreground
            and task_app
            and not _same_app(live_surface.frontmost_app, task_app)
        ):
            holder = live_surface.frontmost_app or "another app"
            return verdict(
                SURFACE_LOST, f"{holder!r} holds the foreground, not {task_app!r}", False
            )

        if perceived_surface is not None and perceived_surface.readable:
            if perceived_surface.window_id is not None and live_surface.window_id is None:
                return verdict(SURFACE_LOST, "the target window is gone", False)
            if (
                perceived_surface.window_id is not None
                and live_surface.window_id is not None
                and perceived_surface.window_id != live_surface.window_id
            ):
                return verdict(
                    SURFACE_LOST,
                    f"window changed ({perceived_surface.window_id} -> {live_surface.window_id})",
                    False,
                )
            if perceived_surface.window_bounds and live_surface.window_bounds:
                drift = max(
                    abs(a - b)
                    for a, b in zip(perceived_surface.window_bounds, live_surface.window_bounds)
                )
                if drift > WINDOW_DRIFT_PX:
                    evidence["window_drift_px"] = round(drift, 1)
                    return verdict(
                        FOCUS_DISTURBED,
                        f"the window moved or resized by {drift:.0f}px, "
                        "so every resolved coordinate is stale",
                        False,
                    )

    # --- 2. The target itself. The surface being intact says nothing about what
    #        is currently under the point we are about to click.
    if not expectation.grounded:
        # Nothing was resolved to a rectangle, so there is nothing to verify. Not
        # a disturbance — many actions are keystrokes or app-level commands.
        return verdict(INDETERMINATE, "action is not grounded to a rectangle", fail_open)

    if observation is None:
        return verdict(INDETERMINATE, "target was not read back", fail_open)

    if observation.method == "ocr":
        if observation.matched:
            return verdict(CONFIRMED, f"target still reads as expected ({observation.detail})", True)
        if observation.saw_text:
            # Text is present and it is the wrong text. This is the case the
            # whole module exists for: something took the target's place.
            return verdict(
                FOCUS_DISTURBED,
                f"something else is at the target now — {observation.detail}",
                False,
            )
        # The rectangle read as empty. Either the row scrolled away or the
        # capture caught a repaint; either way the expectation is unconfirmed.
        return verdict(
            FOCUS_DISTURBED,
            f"expected {expectation.label!r} at the target but found no text there",
            False,
        )

    if observation.method == "icon_hash":
        delta = hamming(resolved_icon_hash, observation.icon_hash)
        if delta < 0:
            return verdict(INDETERMINATE, "no comparable icon reading", fail_open)
        evidence["icon_delta_bits"] = delta
        if delta > ICON_TOLERANCE_BITS:
            return verdict(
                FOCUS_DISTURBED, f"the control at the target changed ({delta} bits)", False
            )
        return verdict(CONFIRMED, "text-free target structurally unchanged", True)

    return verdict(INDETERMINATE, observation.detail or "target could not be read", fail_open)


def continuity_check_enabled() -> bool:
    """Whether the commit gate runs.

    Opt-in like the other live faculties, because the check reads the real
    screen: the launcher turns it on, and offline tests — whose "screen" is a
    fixture — leave it off.
    """
    raw = os.getenv("HERMES_ACTION_GUARD", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def guard_click(
    app: str,
    label: str,
    bounds: Optional[Sequence[float]],
    *,
    irreversible: bool = False,
    estimated: bool = False,
) -> Optional[ContinuityVerdict]:
    """Check a pointer commit at the actuation call itself. ``None`` = not checked.

    This lives at the actuator rather than in the control loop for one reason:
    it is the only place the rectangle is *final*. The loop's decision often
    carries no geometry at all — the executor resolves the target itself, by
    label, through whichever resolver that path uses. A gate upstream of that
    would be checking a rectangle nobody clicks, which is worse than no gate,
    because it reports safety it did not establish.
    """
    if not continuity_check_enabled():
        return None
    expectation = expectation_from(
        bounds, label=label, irreversible=irreversible, estimated=estimated
    )
    if not expectation.grounded:
        return None
    try:
        return verify_before_acting(
            expectation=expectation, perceived_surface=None, task_app=app
        )
    except Exception:
        # The gate must never be the reason an action fails to happen. An
        # unavailable check is the state the agent was in before it existed.
        return None


def verify_before_acting(
    *,
    expectation: TargetExpectation,
    perceived_surface: Optional[Surface],
    task_app: str,
    resolved_icon_hash: str = "",
) -> ContinuityVerdict:
    """Take the live readings and return the verdict — the one call a caller needs.

    Kept as a thin wrapper over :func:`assess_continuity` so the judgement stays
    testable without a screen while the control loop gets a single entry point.
    """
    live_surface = take_surface(task_app)
    observation = read_back(expectation) if expectation.grounded else None
    return assess_continuity(
        expectation=expectation,
        perceived_surface=perceived_surface,
        live_surface=live_surface,
        observation=observation,
        task_app=task_app,
        resolved_icon_hash=resolved_icon_hash,
    )
