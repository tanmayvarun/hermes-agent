"""Tests for light/dark display mode wrappers in cli.py."""

from __future__ import annotations

import pytest


@pytest.fixture
def cli_mod(monkeypatch):
    """Import cli with light-mode caches cleared each test."""
    import cli as _cli
    import hermes_cli.display_mode as dm

    monkeypatch.setattr(_cli, "_LIGHT_MODE_CACHE", None)
    monkeypatch.setattr(dm, "_MODE_CACHE", None)
    monkeypatch.setattr(dm, "_THEME_OVERRIDE", None)
    for var in (
        "HERMES_LIGHT",
        "HERMES_TUI_LIGHT",
        "HERMES_TUI_THEME",
        "HERMES_TUI_BACKGROUND",
        "COLORFGBG",
    ):
        monkeypatch.delenv(var, raising=False)
    return _cli


class TestLightModeDetection:
    def test_hermes_light_env_true_forces_light(self, cli_mod, monkeypatch):
        monkeypatch.setenv("HERMES_LIGHT", "1")
        assert cli_mod._detect_light_mode() is True

    def test_hermes_light_env_false_forces_dark(self, cli_mod, monkeypatch):
        monkeypatch.setenv("HERMES_LIGHT", "0")
        monkeypatch.delenv("HERMES_TUI_LIGHT", raising=False)
        monkeypatch.delenv("HERMES_TUI_THEME", raising=False)
        monkeypatch.delenv("HERMES_TUI_BACKGROUND", raising=False)
        monkeypatch.delenv("COLORFGBG", raising=False)
        assert cli_mod._detect_light_mode() is False

    def test_theme_hint_light(self, cli_mod, monkeypatch):
        monkeypatch.setenv("HERMES_TUI_THEME", "light")
        assert cli_mod._detect_light_mode() is True

    def test_background_hex_hint_light(self, cli_mod, monkeypatch):
        monkeypatch.setenv("HERMES_TUI_BACKGROUND", "#FFFFFF")
        assert cli_mod._detect_light_mode() is True

    def test_background_hex_hint_dark(self, cli_mod, monkeypatch):
        monkeypatch.setenv("HERMES_TUI_BACKGROUND", "#1a1a2e")
        assert cli_mod._detect_light_mode() is False

    def test_colorfgbg_light_bg_slot(self, cli_mod, monkeypatch):
        monkeypatch.setenv("COLORFGBG", "0;15")
        assert cli_mod._detect_light_mode() is True

    def test_cache_is_sticky(self, cli_mod, monkeypatch):
        monkeypatch.setenv("HERMES_LIGHT", "1")
        assert cli_mod._detect_light_mode() is True
        # Module-level cache sticks until reset.
        cli_mod._LIGHT_MODE_CACHE = True
        monkeypatch.setenv("HERMES_LIGHT", "0")
        assert cli_mod._detect_light_mode() is True


class TestOsc11Probe:
    @pytest.mark.parametrize("var", ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"))
    def test_skips_over_ssh(self, cli_mod, monkeypatch, var):
        monkeypatch.setattr(cli_mod.sys.stdin, "isatty", lambda: True, raising=False)
        monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True, raising=False)
        for v in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"):
            monkeypatch.delenv(v, raising=False)
        monkeypatch.setenv(var, "1.2.3.4 5555 22")
        assert cli_mod._query_osc11_background() is None

    def test_skips_when_not_a_tty(self, cli_mod, monkeypatch):
        monkeypatch.setattr(cli_mod.sys.stdin, "isatty", lambda: False, raising=False)
        assert cli_mod._query_osc11_background() is None


class TestLightModeRemap:
    def test_remap_no_op_in_dark_mode(self, cli_mod, monkeypatch):
        cli_mod._LIGHT_MODE_CACHE = False
        assert cli_mod._maybe_remap_for_light_mode("#FFF8DC") == "#FFF8DC"

    def test_remap_known_dark_palette_color(self, cli_mod, monkeypatch):
        from hermes_cli.display_mode import DARK_COLORS, LIGHT_COLORS

        cli_mod._LIGHT_MODE_CACHE = True
        dark = DARK_COLORS["banner_text"]
        light = LIGHT_COLORS["banner_text"]
        assert cli_mod._maybe_remap_for_light_mode(dark) == light

    def test_remap_case_insensitive(self, cli_mod, monkeypatch):
        from hermes_cli.display_mode import DARK_COLORS, LIGHT_COLORS

        cli_mod._LIGHT_MODE_CACHE = True
        assert (
            cli_mod._maybe_remap_for_light_mode(DARK_COLORS["banner_text"].lower())
            == LIGHT_COLORS["banner_text"]
        )

    def test_remap_unknown_color_passthrough(self, cli_mod, monkeypatch):
        cli_mod._LIGHT_MODE_CACHE = True
        assert cli_mod._maybe_remap_for_light_mode("#ABCDEF") == "#ABCDEF"


class TestSkinConfigHook:
    def test_hook_installed(self, cli_mod):
        from hermes_cli.skin_engine import SkinConfig

        assert getattr(SkinConfig, "_hermes_light_mode_hook_installed", False) is True

    def test_hook_is_idempotent(self, cli_mod):
        from hermes_cli.skin_engine import SkinConfig

        before = SkinConfig.get_color
        cli_mod._install_skin_light_mode_hook()
        after = SkinConfig.get_color
        assert before is after

    def test_skin_color_uses_light_palette(self, cli_mod, monkeypatch):
        import hermes_cli.display_mode as dm
        from hermes_cli.skin_engine import SkinConfig

        monkeypatch.setattr(dm, "_THEME_OVERRIDE", "light")
        monkeypatch.setattr(dm, "_MODE_CACHE", None)
        cli_mod._LIGHT_MODE_CACHE = None
        skin = SkinConfig(
            name="test",
            colors={"banner_text": "#FFF8DC", "response_border": "#FFD700"},
        )
        assert skin.get_color("banner_text") == dm.LIGHT_COLORS["banner_text"]
        assert skin.get_color("response_border") == dm.LIGHT_COLORS["response_border"]

    def test_skin_color_uses_dark_palette(self, cli_mod, monkeypatch):
        import hermes_cli.display_mode as dm
        from hermes_cli.skin_engine import SkinConfig

        monkeypatch.setattr(dm, "_THEME_OVERRIDE", "dark")
        monkeypatch.setattr(dm, "_MODE_CACHE", None)
        cli_mod._LIGHT_MODE_CACHE = None
        skin = SkinConfig(name="test", colors={"banner_text": "#E8F4F2"})
        assert skin.get_color("banner_text") == dm.DARK_COLORS["banner_text"]
