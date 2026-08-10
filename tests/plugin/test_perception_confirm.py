"""Unit tests for the cheap perception-confirm API."""

from __future__ import annotations

from plugin.perception.confirm import SKIPPED, PerceptionConfirmResult, confirm_perception
from plugin.perception.continuity import CONFIRMED, ContinuityVerdict, FOCUS_DISTURBED


def test_confirm_gate_off_skips_valid(monkeypatch):
    monkeypatch.delenv("HERMES_ACTION_GUARD", raising=False)
    result = confirm_perception("WhatsApp", "Pallavi", (100.0, 100.0, 80.0, 40.0))
    assert result.valid is True
    assert result.state == SKIPPED
    assert result.reason == "action_guard_disabled"


def test_confirm_disturbed_invalid(monkeypatch):
    monkeypatch.setenv("HERMES_ACTION_GUARD", "1")
    from plugin.perception import continuity as cont

    monkeypatch.setattr(
        cont,
        "guard_click",
        lambda *a, **k: ContinuityVerdict(
            state=FOCUS_DISTURBED,
            reason="expected pallavi, found raman",
            may_commit=False,
            evidence={"found": "raman"},
        ),
    )
    result = confirm_perception("WhatsApp", "Pallavi", (100.0, 100.0, 80.0, 40.0))
    assert result.valid is False
    assert result.state == FOCUS_DISTURBED
    assert "pallavi" in result.reason.lower() or "raman" in result.reason.lower()
    assert result.evidence.get("found") == "raman"
    assert result.to_dict()["valid"] is False


def test_confirm_confirmed_valid(monkeypatch):
    monkeypatch.setenv("HERMES_ACTION_GUARD", "1")
    from plugin.perception import continuity as cont

    monkeypatch.setattr(
        cont,
        "guard_click",
        lambda *a, **k: ContinuityVerdict(
            state=CONFIRMED, reason="label still present", may_commit=True
        ),
    )
    result = confirm_perception("WhatsApp", "Pallavi", (100.0, 100.0, 80.0, 40.0))
    assert result.valid is True
    assert result.state == CONFIRMED


def test_confirm_ungrounded_none_verdict_skips(monkeypatch):
    monkeypatch.setenv("HERMES_ACTION_GUARD", "1")
    from plugin.perception import continuity as cont

    monkeypatch.setattr(cont, "guard_click", lambda *a, **k: None)
    result = confirm_perception("WhatsApp", "Pallavi", None)
    assert isinstance(result, PerceptionConfirmResult)
    assert result.valid is True
    assert result.state == SKIPPED
