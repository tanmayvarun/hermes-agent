"""ensure_whatsapp_bridge_running: linked → start daemon; already live → no-op."""

from __future__ import annotations


def test_ensure_bridge_short_circuits_when_live(monkeypatch) -> None:
    from hermes_cli import whatsapp_pairing as wp

    monkeypatch.setattr(wp, "probe_bridge_connection", lambda **_k: (True, "connected"))
    called = {"n": 0}

    def _boom(**_k):
        called["n"] += 1
        raise AssertionError("should not spawn")

    monkeypatch.setattr(wp, "_start_long_lived_bridge", _boom)
    ok, detail = wp.ensure_whatsapp_bridge_running()
    assert ok is True
    assert detail == "connected"
    assert called["n"] == 0


def test_ensure_bridge_requires_link(monkeypatch) -> None:
    from hermes_cli import whatsapp_pairing as wp

    monkeypatch.setattr(wp, "probe_bridge_connection", lambda **_k: (False, "unreachable"))
    monkeypatch.setattr(wp, "is_whatsapp_linked", lambda **_k: False)
    ok, detail = wp.ensure_whatsapp_bridge_running()
    assert ok is False
    assert detail == "not_linked"


def test_ensure_bridge_spawns_when_linked_and_down(monkeypatch) -> None:
    from hermes_cli import whatsapp_pairing as wp

    monkeypatch.setattr(wp, "probe_bridge_connection", lambda **_k: (False, "unreachable"))
    monkeypatch.setattr(wp, "is_whatsapp_linked", lambda **_k: True)
    monkeypatch.setattr(wp, "bridge_available", lambda: (True, "ok"))
    monkeypatch.setattr(
        wp, "_start_long_lived_bridge", lambda **_k: (True, "connected")
    )
    ok, detail = wp.ensure_whatsapp_bridge_running()
    assert ok is True
    assert detail == "connected"
