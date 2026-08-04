"""Foreground persistence: the agent keeps its own app usable, uncapped.

Keeping the task app in front is the agent's job rather than the user's. A call
or a notification steals the foreground mid-task, and every synthetic click and
keystroke after that lands in whatever window took it — so the agent raises its
app again itself, each time it finds it gone. There is no budget, because the
interruptions this answers recur by nature; a cap would just mean surrendering
the task to the third phone call.

These cover the predicate (is the frontmost app the task's, through the
Unicode/format-mark normalisation macOS forces — WhatsApp reports itself as
"\u200eWhatsApp"), the opt-in toggle that keeps headless tests clear of it, and
the loop-level reclaim itself.
"""

from __future__ import annotations

from plugin.agent.focus_of_action import (
    foreground_gate_enabled,
    foreground_matches_task,
    normalize_app_name,
    task_anchor_app,
)


class _Goal:
    def __init__(self, app: str = "WhatsApp") -> None:
        self.app = app


def test_normalize_strips_the_bidi_mark_macos_prepends():
    """macOS reports WhatsApp's owner with a leading LEFT-TO-RIGHT MARK; the
    normaliser must drop it so equality does not silently fail."""
    assert normalize_app_name("\u200eWhatsApp") == "whatsapp"
    assert normalize_app_name("  WhatsApp  ") == "whatsapp"


def test_foreground_matches_when_frontmost_is_the_task_app():
    assert foreground_matches_task(_Goal("WhatsApp"), foreground="\u200eWhatsApp")
    assert foreground_matches_task(_Goal("WhatsApp"), foreground="WhatsApp")


def test_a_foreign_frontmost_app_does_not_match():
    """A foreign app in front is positive evidence that the agent must reclaim."""
    assert not foreground_matches_task(_Goal("WhatsApp"), foreground="Cursor")
    assert not foreground_matches_task(_Goal("WhatsApp"), foreground="YouTube")
    assert not foreground_matches_task(_Goal("WhatsApp"), foreground="Safari")


def test_gate_fails_open_on_missing_signals():
    """Never act on missing information: an unknown task app or an
    undeterminable foreground both count as a match, so the agent cannot start
    fighting for a foreground nobody took."""
    assert foreground_matches_task(_Goal(""), foreground="Safari")
    assert foreground_matches_task(_Goal("WhatsApp"), foreground="")


def test_gate_is_opt_in(monkeypatch):
    monkeypatch.delenv("HERMES_FOREGROUND_GATE", raising=False)
    assert foreground_gate_enabled() is False
    monkeypatch.setenv("HERMES_FOREGROUND_GATE", "1")
    assert foreground_gate_enabled() is True
    monkeypatch.setenv("HERMES_FOREGROUND_GATE", "0")
    assert foreground_gate_enabled() is False


def test_task_anchor_app_reads_the_goal():
    assert task_anchor_app(_Goal("WhatsApp")) == "WhatsApp"
    assert task_anchor_app(_Goal("")) == ""


# --- the loop-level reclaim --------------------------------------------------


class _ExecState:
    foreground_reclaims = 0


class _World:
    active_app = "WhatsApp"


class _Runtime:
    def __init__(self) -> None:
        self.execution_state = _ExecState()
        self.world_model = _World()


def _reclaim_harness(monkeypatch, *, holder: str, enabled: bool = True):
    """Drive ``_reclaim_foreground`` with the window server and actuator stubbed."""
    import plugin.agent.controller as controller

    raised: list = []
    logged: list = []
    monkeypatch.setenv("HERMES_FOREGROUND_GATE", "1" if enabled else "0")
    monkeypatch.setattr(controller, "foreground_app_name", lambda: holder)
    monkeypatch.setattr(controller, "_log_cycle", lambda *a, **k: logged.append(k))
    monkeypatch.setattr(
        "plugin.executor.ax_action._activate_app", lambda name: raised.append(name)
    )
    runtime = _Runtime()
    acted = controller._reclaim_foreground(runtime, _Goal("WhatsApp"), log=None, iteration=1)
    return acted, raised, runtime, logged


def test_the_agent_takes_the_foreground_back_from_a_foreign_app(monkeypatch):
    acted, raised, runtime, _ = _reclaim_harness(monkeypatch, holder="Cursor")
    assert acted is True
    assert raised == ["WhatsApp"]
    assert runtime.execution_state.foreground_reclaims == 1


def test_the_agent_does_not_raise_an_app_that_is_already_in_front(monkeypatch):
    """A needless raise would defeat background actuation for AX-rich apps."""
    acted, raised, runtime, _ = _reclaim_harness(monkeypatch, holder="\u200eWhatsApp")
    assert acted is False
    assert raised == []
    assert runtime.execution_state.foreground_reclaims == 0


def test_reclaiming_is_uncapped_because_interruptions_recur(monkeypatch):
    """Three calls in a row must not end with the agent giving up the screen."""
    import plugin.agent.controller as controller

    raised: list = []
    monkeypatch.setenv("HERMES_FOREGROUND_GATE", "1")
    monkeypatch.setattr(controller, "foreground_app_name", lambda: "FaceTime")
    monkeypatch.setattr(controller, "_log_cycle", lambda *a, **k: None)
    monkeypatch.setattr(
        "plugin.executor.ax_action._activate_app", lambda name: raised.append(name)
    )

    runtime = _Runtime()
    for iteration in range(1, 6):
        controller._reclaim_foreground(runtime, _Goal("WhatsApp"), log=None, iteration=iteration)

    assert raised == ["WhatsApp"] * 5
    assert runtime.execution_state.foreground_reclaims == 5


def test_reclaim_stays_off_until_the_launcher_enables_it(monkeypatch):
    acted, raised, _, _ = _reclaim_harness(monkeypatch, holder="Cursor", enabled=False)
    assert acted is False
    assert raised == []


def test_an_unreadable_foreground_never_provokes_a_reclaim(monkeypatch):
    """Missing information must not start the agent grabbing the screen."""
    acted, raised, _, _ = _reclaim_harness(monkeypatch, holder="")
    assert acted is False
    assert raised == []
