"""Tests for hermes_cli.display_mode — light/dark only."""

from __future__ import annotations

import pytest


@pytest.fixture
def mode(monkeypatch):
    import hermes_cli.display_mode as dm

    monkeypatch.setattr(dm, "_MODE_CACHE", None)
    monkeypatch.setattr(dm, "_THEME_OVERRIDE", None)
    # Clear env signals by default
    for var in (
        "HERMES_LIGHT",
        "HERMES_TUI_LIGHT",
        "HERMES_TUI_THEME",
        "HERMES_TUI_BACKGROUND",
        "COLORFGBG",
    ):
        monkeypatch.delenv(var, raising=False)
    return dm


class TestThemeOverride:
    def test_force_light(self, mode):
        mode.set_theme_override("light")
        assert mode.detect_light_mode() is True
        assert mode.active_mode_name() == "light"

    def test_force_dark(self, mode, monkeypatch):
        monkeypatch.setenv("HERMES_LIGHT", "1")  # would be light
        mode.set_theme_override("dark")
        assert mode.detect_light_mode() is False

    def test_auto_follows_env(self, mode, monkeypatch):
        mode.set_theme_override("auto")
        monkeypatch.setenv("HERMES_TUI_THEME", "light")
        assert mode.detect_light_mode() is True


class TestPalettes:
    def test_light_banner_text_is_dark(self, mode):
        mode.set_theme_override("light")
        text = mode.resolve_color("banner_text")
        assert text == mode.LIGHT_COLORS["banner_text"]
        # Must be dark enough for white terminals
        assert text.lower() in ("#3d2f13",)

    def test_dark_banner_text_is_light(self, mode):
        mode.set_theme_override("dark")
        assert mode.resolve_color("banner_text") == mode.DARK_COLORS["banner_text"]

    def test_skin_get_color_uses_mode_not_yaml(self, mode):
        from hermes_cli.skin_engine import SkinConfig

        mode.set_theme_override("light")
        skin = SkinConfig(
            name="plugin",
            colors={"banner_text": "#E8F4F2"},  # near-white — must be ignored
        )
        assert skin.get_color("banner_text") == mode.LIGHT_COLORS["banner_text"]
