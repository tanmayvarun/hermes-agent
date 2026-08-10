"""Context-click must prefer grounded bounds over AX sidebar label echoes."""

from __future__ import annotations

from plugin.executor import ax_action


def test_ax_context_click_prefers_bounds_over_sidebar_ax_label(monkeypatch):
    clicks = []

    class _El:
        pass

    monkeypatch.setattr(ax_action, "ax_available", lambda: True)
    monkeypatch.setattr(ax_action, "_activate_app", lambda _app: None)
    monkeypatch.setattr(
        ax_action,
        "_find_element",
        lambda *_a, **_k: _El(),
    )
    # AX resolves the left-rail preview.
    monkeypatch.setattr(ax_action, "_frame_center", lambda _el: (360.5, 151.5))
    monkeypatch.setattr(ax_action, "_refuse_stale_click", lambda *_a, **_k: None)
    monkeypatch.setattr(ax_action, "_mouse_move", lambda x, y: clicks.append(("move", x, y)))
    monkeypatch.setattr(ax_action, "_mouse_right_click", lambda x, y: clicks.append(("right", x, y)))
    monkeypatch.setattr(ax_action.time, "sleep", lambda *_a, **_k: None)

    # Decision bounds point at the conversation-pane link.
    result = ax_action.ax_context_click(
        "WhatsApp",
        "zarooratwala",
        bounds=(1330.0, 597.0, 200.0, 20.0),
    )
    assert result.ok
    assert ("right", 1430.0, 607.0) in clicks
    assert ("right", 360.5, 151.5) not in clicks
