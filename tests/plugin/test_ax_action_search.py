from __future__ import annotations

from types import SimpleNamespace

from plugin.executor import ax_action


def test_search_surface_is_accepted_when_focused_and_search_like(monkeypatch):
    el = SimpleNamespace(name="search-surface")

    monkeypatch.setattr(ax_action, "_app_root", lambda app_name: object())
    monkeypatch.setattr(
        ax_action,
        "_walk",
        lambda root: [
            (
                el,
                "AXStaticText",
                "Search",
                "",
                "Search or start new chat",
                "search field",
            )
        ],
    )

    def fake_ax_attr(node, attr):
        if node is not el:
            return None
        return {
            "AXFocused": True,
            "AXEnabled": True,
            "AXSelectedTextRange": (0, 0),
            "AXRole": "AXStaticText",
        }.get(attr)

    def fake_ax_str(node, attr):
        if node is not el:
            return ""
        return {
            "AXTitle": "Search",
            "AXValue": "",
            "AXDescription": "Search or start new chat",
            "AXHelp": "",
            "AXPlaceholderValue": "Search",
            "AXRoleDescription": "search field",
        }.get(attr, "")

    monkeypatch.setattr(ax_action, "_ax_attr", fake_ax_attr)
    monkeypatch.setattr(ax_action, "_ax_str", fake_ax_str)

    field, label = ax_action._find_search_text_field("WhatsApp")
    assert field is el
    assert label == "Search"
    assert ax_action._is_editable_text_target(el) is True


def test_search_surface_without_input_signals_is_rejected(monkeypatch):
    el = SimpleNamespace(name="search-label")

    monkeypatch.setattr(ax_action, "_app_root", lambda app_name: object())
    monkeypatch.setattr(
        ax_action,
        "_walk",
        lambda root: [
            (
                el,
                "AXStaticText",
                "Search",
                "",
                "",
                "",
            )
        ],
    )

    def fake_ax_attr(node, attr):
        if node is not el:
            return None
        return {
            "AXFocused": False,
            "AXEnabled": True,
            "AXSelectedTextRange": None,
            "AXRole": "AXStaticText",
        }.get(attr)

    def fake_ax_str(node, attr):
        if node is not el:
            return ""
        return {
            "AXTitle": "Search",
            "AXValue": "",
            "AXDescription": "Search",
            "AXHelp": "",
            "AXPlaceholderValue": "",
            "AXRoleDescription": "",
        }.get(attr, "")

    monkeypatch.setattr(ax_action, "_ax_attr", fake_ax_attr)
    monkeypatch.setattr(ax_action, "_ax_str", fake_ax_str)

    field, _ = ax_action._find_search_text_field("WhatsApp")
    assert field is None
    assert ax_action._is_editable_text_target(el) is False
