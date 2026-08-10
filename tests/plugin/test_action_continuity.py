"""The commit gate: acting on a screen that has moved on since it was perceived.

Perception photographs the screen and the action lands 35-76 seconds later
(measured on live runs). Everything here is about that gap: whether the agent
notices the target is no longer what it chose, whether it stays indifferent to
changes that do not concern it, and — just as important — whether an abort is
kept out of the machinery that judges actions, since nothing was attempted.
"""

from __future__ import annotations

import pytest

from plugin.perception.continuity import (
    CONFIRMED,
    FOCUS_DISTURBED,
    INDETERMINATE,
    SURFACE_LOST,
    ContinuityVerdict,
    ReadBack,
    Surface,
    TargetExpectation,
    assess_continuity,
    continuity_check_enabled,
    expectation_from,
    guard_click,
    label_present,
    significant_tokens,
)


def _surface(**overrides):
    base = dict(
        taken_at=0.0,
        frontmost_app="\u200eWhatsApp",
        window_id=7,
        window_bounds=(0.0, 0.0, 1200.0, 800.0),
        window_title="WhatsApp",
        readable=True,
    )
    base.update(overrides)
    return Surface(**base)


def _target(**overrides):
    base = dict(bounds=(10.0, 300.0, 300.0, 60.0), label="Kulvinder Ji")
    base.update(overrides)
    return TargetExpectation(**base)


def _assess(observation, *, live=None, expectation=None, **kwargs):
    return assess_continuity(
        expectation=expectation or _target(),
        perceived_surface=_surface(),
        live_surface=live or _surface(taken_at=60.0),
        observation=observation,
        task_app="WhatsApp",
        **kwargs,
    )


# --- reading the target ------------------------------------------------------


def test_a_row_that_was_replaced_under_us_stops_the_click():
    """The case the module exists for.

    A minute passed between choosing "Kulvinder Ji" and clicking the coordinates
    that used to be his row. If the list reordered, those coordinates now open
    somebody else's chat — and in a forwarding flow that is an irreversible
    message to the wrong person.
    """
    verdict = _assess(
        ReadBack(
            lines=("Zarooratwala Orders",),
            matched=False,
            method="ocr",
            detail="expected kulvinder, found 'zarooratwala orders'",
        )
    )
    assert verdict.state == FOCUS_DISTURBED
    assert verdict.may_commit is False


def test_an_intact_target_commits():
    verdict = _assess(
        ReadBack(lines=("Kulvinder Ji", "tap to open"), matched=True, method="ocr")
    )
    assert verdict.state == CONFIRMED
    assert verdict.may_commit is True


def test_empty_ocr_on_reversible_target_is_unconfirmed_not_a_hard_stop():
    """Empty ≠ wrong. Live OCR often misses a tight row; refusing stalls forever.

    Wrong text (another contact in the rectangle) still hard-refuses above.
    Empty read-back fails open for reversible opens so a correct click proceeds;
    irreversible Send still refuses (covered separately).
    """
    verdict = _assess(ReadBack(lines=(), matched=False, method="ocr", detail="no text found"))
    assert verdict.state == INDETERMINATE
    assert verdict.may_commit is True


def test_change_away_from_the_target_is_never_even_observed():
    """Composure is structural rather than classified.

    A notification banner, a ticking clock, an unread badge — the check reads
    only the target rectangle, so none of them can produce a verdict at all. An
    agent that aborted on any screen change would never act on a real desktop.
    """
    verdict = _assess(ReadBack(lines=("Kulvinder Ji",), matched=True, method="ocr"))
    assert verdict.may_commit is True
    assert "periphery" not in verdict.evidence


# --- reading the surface -----------------------------------------------------


def test_a_stolen_foreground_stops_a_synthetic_click():
    """A click lands wherever the keyboard points, so the app must own the front."""
    verdict = _assess(
        ReadBack(lines=("Kulvinder Ji",), matched=True, method="ocr"),
        live=_surface(taken_at=60.0, frontmost_app="Cursor"),
    )
    assert verdict.state == SURFACE_LOST
    assert verdict.may_commit is False


def test_a_background_press_is_indifferent_to_who_is_in_front():
    """An AX press is addressed to an element, so z-order cannot misdirect it."""
    verdict = _assess(
        ReadBack(lines=("Kulvinder Ji",), matched=True, method="ocr"),
        live=_surface(taken_at=60.0, frontmost_app="Cursor"),
        expectation=_target(needs_foreground=False),
    )
    assert verdict.may_commit is True


def test_a_moved_window_invalidates_every_coordinate_at_once():
    verdict = _assess(
        ReadBack(lines=("Kulvinder Ji",), matched=True, method="ocr"),
        live=_surface(taken_at=60.0, window_bounds=(40.0, 0.0, 1200.0, 800.0)),
    )
    assert verdict.state == FOCUS_DISTURBED
    assert verdict.may_commit is False


def test_a_closed_window_stops_everything():
    verdict = _assess(
        ReadBack(matched=True, method="ocr"),
        live=_surface(taken_at=60.0, window_id=None),
    )
    assert verdict.state == SURFACE_LOST


def test_a_window_nudged_a_pixel_is_still_the_same_window():
    """Sub-pixel drift and rounding must not read as the world moving."""
    verdict = _assess(
        ReadBack(lines=("Kulvinder Ji",), matched=True, method="ocr"),
        live=_surface(taken_at=60.0, window_bounds=(1.0, 0.0, 1200.0, 800.0)),
    )
    assert verdict.may_commit is True


# --- failure posture ---------------------------------------------------------


def test_an_unreadable_screen_lets_an_ordinary_action_through():
    """Never wedge on missing information: that is the state before this existed."""
    verdict = _assess(ReadBack(method="none", detail="could not capture"))
    assert verdict.state == INDETERMINATE
    assert verdict.may_commit is True


def test_an_unreadable_screen_stops_an_irreversible_one():
    """Sending to the wrong contact cannot be undone, so doubt has to stop it."""
    verdict = _assess(
        ReadBack(method="none", detail="could not capture"),
        expectation=_target(label="Send", irreversible=True),
    )
    assert verdict.state == INDETERMINATE
    assert verdict.may_commit is False


def test_an_ungrounded_action_is_not_treated_as_disturbed():
    """A keystroke has no rectangle; absence of a target is not evidence of one moving."""
    verdict = _assess(None, expectation=TargetExpectation(label="type query"))
    assert verdict.state == INDETERMINATE
    assert verdict.may_commit is True


# --- matching a label the way a screen actually renders it -------------------


@pytest.mark.parametrize(
    "expected, lines, should_match",
    [
        ("Kulvinder Ji", ["Kulvinder Ji", "tap to open chat"], True),
        ("Kulvinder Ji", ["kulvinder ji"], True),
        # WhatsApp truncates long names, so the row holds only a prefix.
        ("Zarooratwala Orders", ["Zaroorat\u2026", "yesterday"], True),
        # OCR mangles emoji; the name beside it still has to match.
        ("Mum \u2764\ufe0f", ["Mum EIEI"], True),
        ("Kulvinder Ji", ["Zarooratwala Orders"], False),
        ("Kulvinder Ji", [], False),
    ],
)
def test_label_matching_is_lenient_about_form_and_strict_about_identity(
    expected, lines, should_match
):
    matched, _ = label_present(expected, lines)
    assert matched is should_match


def test_matching_never_turns_on_a_filler_word():
    """"the", "to", "chat" are everywhere on screen; a match on one means nothing."""
    assert significant_tokens("to the chat") == []
    matched, reason = label_present("to the chat", ["something entirely different"])
    assert matched is False
    assert "distinctive" in reason


# --- where the gate lives ----------------------------------------------------
#
# At the actuator, not in the control loop. The decision upstream frequently
# carries no geometry at all — a live trace showed open_contact reaching the
# executor with target_entity_id=None and target_point=None, the rectangle being
# resolved by label inside the executor. A gate above that would be checking a
# rectangle nobody clicks, which is worse than no gate because it reports safety
# it never established.


def test_the_gate_is_off_unless_the_launcher_turns_it_on():
    """It reads the live screen, so a headless test must never trip it."""
    assert continuity_check_enabled() is False
    assert guard_click("WhatsApp", "Kulvinder Ji", (0.0, 0.0, 100.0, 40.0)) is None


def test_an_ungrounded_click_is_not_checked(monkeypatch):
    """No rectangle, nothing to verify — and nothing to claim about safety."""
    monkeypatch.setenv("HERMES_ACTION_GUARD", "1")
    assert guard_click("WhatsApp", "Kulvinder Ji", None) is None
    assert guard_click("WhatsApp", "Kulvinder Ji", (0.0, 0.0, 1.0, 1.0)) is None


def test_a_send_label_is_treated_as_irreversible():
    from plugin.agent.capabilities.invoke_affordance import is_irreversible_affordance

    assert is_irreversible_affordance("Send") is True
    assert expectation_from((0.0, 0.0, 80.0, 30.0), label="Send", irreversible=True).irreversible


def test_the_actuator_refuses_a_stale_click_with_a_distinct_marker(monkeypatch):
    """The refusal must be distinguishable from an ordinary actuation failure.

    The controller keys on this marker to re-perceive rather than judge the
    action; if it looked like a normal failure the world critic would condemn an
    affordance that was never invoked.
    """
    import plugin.executor.ax_action as ax

    monkeypatch.setattr(
        "plugin.perception.continuity.guard_click",
        lambda *a, **k: ContinuityVerdict(
            state=FOCUS_DISTURBED, reason="something else is there now", may_commit=False
        ),
    )
    result = ax._refuse_stale_click("WhatsApp", "Kulvinder Ji", (10.0, 300.0, 240.0, 56.0))
    assert result is not None
    assert result.ok is False
    assert result.backend == ax.STALE_PRECONDITION_BACKEND
    assert "something else is there now" in result.message


def test_the_actuator_proceeds_when_the_target_is_confirmed(monkeypatch):
    import plugin.executor.ax_action as ax

    monkeypatch.setattr(
        "plugin.perception.continuity.guard_click",
        lambda *a, **k: ContinuityVerdict(state=CONFIRMED, reason="intact", may_commit=True),
    )
    assert ax._refuse_stale_click("WhatsApp", "Kulvinder Ji", (10.0, 300.0, 240.0, 56.0)) is None


def test_a_broken_gate_never_blocks_an_action(monkeypatch):
    """An unavailable check is the state the agent was in before it existed."""
    import plugin.executor.ax_action as ax

    def _boom(*a, **k):
        raise RuntimeError("Vision unavailable")

    monkeypatch.setattr("plugin.perception.continuity.guard_click", _boom)
    assert ax._refuse_stale_click("WhatsApp", "Kulvinder Ji", (10.0, 300.0, 240.0, 56.0)) is None


def test_ax_click_consults_the_gate_before_moving_the_mouse(monkeypatch):
    """The wiring, not just the units.

    The first version of this gate sat in the control loop and never fired once
    in a live run, because the decision it inspected carried no geometry — the
    executor resolved the rectangle itself, further down. Unit tests of the
    judgement all passed while the agent clicked blind. So this asserts the path
    that actually matters: a refusal reaches ax_click and the mouse never moves.
    """
    import plugin.executor.ax_action as ax

    clicks: list = []
    monkeypatch.setattr(ax, "ax_available", lambda: True)
    monkeypatch.setattr(ax, "_find_element", lambda *a, **k: None)
    monkeypatch.setattr(ax, "_activate_app", lambda *a, **k: None)
    monkeypatch.setattr(ax, "_mouse_click", lambda x, y: clicks.append((x, y)))
    monkeypatch.setattr(
        "plugin.perception.continuity.guard_click",
        lambda *a, **k: ContinuityVerdict(
            state=FOCUS_DISTURBED, reason="a different chat is there now", may_commit=False
        ),
    )

    result = ax.ax_click("WhatsApp", "Kulvinder Ji", bounds=(10.0, 300.0, 240.0, 56.0))

    assert clicks == [], "the gate refused, so the mouse must not have moved"
    assert result.ok is False
    assert result.backend == ax.STALE_PRECONDITION_BACKEND


def test_ax_click_clicks_normally_when_the_target_is_confirmed(monkeypatch):
    import plugin.executor.ax_action as ax

    clicks: list = []
    monkeypatch.setattr(ax, "ax_available", lambda: True)
    monkeypatch.setattr(ax, "_find_element", lambda *a, **k: None)
    monkeypatch.setattr(ax, "_activate_app", lambda *a, **k: None)
    monkeypatch.setattr(ax, "_mouse_click", lambda x, y: clicks.append((x, y)))
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setattr(
        "plugin.perception.continuity.guard_click",
        lambda *a, **k: ContinuityVerdict(state=CONFIRMED, reason="intact", may_commit=True),
    )

    result = ax.ax_click("WhatsApp", "Kulvinder Ji", bounds=(10.0, 300.0, 240.0, 56.0))

    assert clicks == [(130.0, 328.0)], "should click the centre of the supplied bounds"
    assert result.ok is True


# --- false negatives are the costlier error ----------------------------------
#
# From a live run: the vision model put the click on the right chat row, the
# read rectangle clipped mid-word, OCR returned 'ala' out of "zarooratwala", and
# the gate refused a correct click twice. A wrong click is caught by the
# transition machinery; a refused correct click just stalls the run.


def test_empty_ocr_on_reversible_target_fails_open():
    """No text ≠ wrong text. Empty read-back must not stall open_entity forever."""
    from plugin.perception.continuity.relevance import assess_continuity
    from plugin.perception.continuity.witness import ReadBack, expectation_from

    expectation = expectation_from(
        (142.0, 183.0, 47.0, 16.0), label="Pallavi https://photos.app.goo.gl/x", irreversible=False
    )
    verdict = assess_continuity(
        expectation=expectation,
        perceived_surface=None,
        live_surface=None,
        observation=ReadBack(method="ocr", lines=(), matched=False, detail="no text found"),
    )
    assert verdict.may_commit is True
    assert verdict.state == INDETERMINATE


def test_empty_ocr_on_irreversible_target_still_refuses():
    from plugin.perception.continuity.relevance import assess_continuity
    from plugin.perception.continuity.witness import ReadBack, expectation_from

    expectation = expectation_from(
        (100.0, 800.0, 80.0, 30.0), label="Send", irreversible=True
    )
    verdict = assess_continuity(
        expectation=expectation,
        perceived_surface=None,
        live_surface=None,
        observation=ReadBack(method="ocr", lines=(), matched=False, detail="no text found"),
    )
    assert verdict.may_commit is False


def test_a_clipped_word_fragment_confirms_rather_than_contradicts():
    from plugin.perception.continuity.witness import label_present

    ok, why = label_present("Kulvinder Ji - You: https://www.zarooratwala.com/...", ["ala"])
    assert ok, why
    assert "fragment" in why


def test_a_fragment_of_a_different_row_still_refuses():
    """Leniency about form must not become indifference about identity."""
    from plugin.perception.continuity.witness import label_present

    assert label_present("Kulvinder Ji", ["Zarooratwala Orders"])[0] is False
    assert label_present("Pallavi", ["Kulvinder Ji"])[0] is False
    # Too short to be distinctive: two letters must not match everything.
    assert label_present("Kulvinder Ji", ["ji"])[0] is False


def test_an_estimated_point_is_read_as_a_row_not_as_a_dot():
    """The error in a guessed point is the size of the guess, so read the band."""
    from plugin.perception.continuity.witness import expectation_from

    estimated = expectation_from((389.0, 576.0, 24.0, 24.0), label="Kulvinder Ji", estimated=True)
    x, y, w, h = estimated.padded()
    assert (w, h) == (340.0, 44.0)
    # Centred on the estimate, so the row it sits in is what gets read.
    assert (x + w / 2, y + h / 2) == (401.0, 588.0)


def test_a_measured_rectangle_is_still_read_tightly():
    """A real extent is a claim that can be checked strictly; a guess is not."""
    from plugin.perception.continuity.witness import expectation_from

    measured = expectation_from((86.0, 231.0, 82.0, 15.0), label="Kulvinder Ji")
    assert measured.padded() == (80.0, 225.0, 94.0, 27.0)


def test_synthetic_boxes_are_recognised_as_estimates():
    import plugin.executor.ax_action as ax

    assert ax._is_estimated_box((100.0, 100.0, 24.0, 24.0)) is True   # point target
    assert ax._is_estimated_box((100.0, 100.0, 48.0, 48.0)) is True   # vision entity
    assert ax._is_estimated_box((86.0, 231.0, 82.0, 15.0)) is False   # measured row
    assert ax._is_estimated_box(None) is False


# --- the abort is not an outcome ---------------------------------------------


def test_consecutive_refusals_are_counted_and_bounded():
    """A target that never settles must eventually be acted on anyway.

    A live-updating list or a playing video under the target would abort forever,
    and an agent that never commits is no better than one that commits wrongly.
    """
    from plugin.agent.controller import MAX_CONSECUTIVE_STALE_ABORTS, _note_stale_abort

    class _State:
        consecutive_stale_aborts = 0

    class _Runtime:
        execution_state = _State()

    runtime = _Runtime()
    counts = [_note_stale_abort(runtime) for _ in range(MAX_CONSECUTIVE_STALE_ABORTS + 1)]
    assert counts == [1, 2, 3, 4]
    # The controller yields once the count passes the budget.
    assert counts[-1] > MAX_CONSECUTIVE_STALE_ABORTS


def test_yielding_actually_lets_the_next_click_through(monkeypatch):
    """Resetting the counter is not enough — the gate itself has to stand down.

    Without this the "budget spent" branch just restarts the count and the run
    aborts forever, which is the livelock the budget exists to prevent.
    """
    import plugin.executor.ax_action as ax

    monkeypatch.setattr(
        "plugin.perception.continuity.guard_click",
        lambda *a, **k: ContinuityVerdict(
            state=FOCUS_DISTURBED, reason="never settles", may_commit=False
        ),
    )
    rect = (10.0, 300.0, 240.0, 56.0)
    assert ax._refuse_stale_click("WhatsApp", "Kulvinder Ji", rect) is not None

    ax.bypass_next_gate()
    assert ax._refuse_stale_click("WhatsApp", "Kulvinder Ji", rect) is None, "one click through"
    assert ax._refuse_stale_click("WhatsApp", "Kulvinder Ji", rect) is not None, "then guarded again"
