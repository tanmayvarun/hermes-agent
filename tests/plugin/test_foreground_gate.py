"""The perceptor/brain foreground awareness that keeps the agent goal-persistent.

These cover the decision logic of the persistence gate: whether the frontmost
app is the task's app, with the Unicode/format-mark normalisation macOS forces
(WhatsApp reports itself as "\u200eWhatsApp"), and the opt-in toggle that keeps
the gate off for headless control-loop tests.
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
    """A user who has switched to another app is positive evidence to hold."""
    assert not foreground_matches_task(_Goal("WhatsApp"), foreground="Cursor")
    assert not foreground_matches_task(_Goal("WhatsApp"), foreground="YouTube")
    assert not foreground_matches_task(_Goal("WhatsApp"), foreground="Safari")


def test_gate_fails_open_on_missing_signals():
    """Never hold on missing information: an unknown task app or an
    undeterminable foreground both count as a match."""
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
