"""Terminal display mode: light or dark only.

Hermes contrast is driven by exactly two palettes. Skins may still supply
branding (name, logos, spinner), but UI colors always come from the active
mode so text stays readable on any terminal background.

Mode resolution (first match wins):
  1. ``display.theme`` / ``set_theme_override`` — ``light`` | ``dark`` | ``auto``
  2. ``HERMES_LIGHT`` / ``HERMES_TUI_LIGHT`` / ``HERMES_TUI_THEME``
  3. ``HERMES_TUI_BACKGROUND`` luminance
  4. ``COLORFGBG``
  5. OSC 11 background query (local TTYs only)
  6. ``TERM_PROGRAM=Apple_Terminal`` → light default
  7. Otherwise dark
"""

from __future__ import annotations

import os
import re
import sys
import time
from typing import Dict, Literal, Optional

ThemeName = Literal["light", "dark", "auto"]

_TRUE_RE = re.compile(r"^(1|true|on|yes|y)$", re.I)
_FALSE_RE = re.compile(r"^(0|false|off|no|n)$", re.I)
_LIGHT_DEFAULT_TERM_PROGRAMS = frozenset({"Apple_Terminal"})

# Explicit override from config /slash command. None = auto-detect.
_THEME_OVERRIDE: Optional[ThemeName] = None
_MODE_CACHE: Optional[bool] = None  # True = light


# ---------------------------------------------------------------------------
# Canonical palettes (aligned with ui-tui LIGHT_THEME / DARK_THEME)
# ---------------------------------------------------------------------------

DARK_COLORS: Dict[str, str] = {
    "banner_border": "#CD7F32",
    "banner_title": "#FFD700",
    "banner_accent": "#FFBF00",
    "banner_dim": "#CC9B1F",
    "banner_text": "#FFF8DC",
    "ui_accent": "#FFBF00",
    "ui_label": "#DAA520",
    "ui_ok": "#4caf50",
    "ui_error": "#ef5350",
    "ui_warn": "#ffa726",
    "prompt": "",  # inherit terminal fg
    "input_rule": "#CD7F32",
    "response_border": "#FFD700",
    "session_label": "#DAA520",
    "session_border": "#8B8682",
    "status_bar_bg": "#1a1a2e",
    "status_bar_text": "#C0C0C0",
    "status_bar_strong": "#FFD700",
    "status_bar_dim": "#8B8682",
    "status_bar_good": "#8FBC8F",
    "status_bar_warn": "#FFD700",
    "status_bar_bad": "#FF8C00",
    "status_bar_critical": "#FF6B6B",
    "voice_status_bg": "#1a1a2e",
    "selection_bg": "#3a3a55",
    "completion_menu_bg": "#1a1a2e",
    "completion_menu_current_bg": "#333355",
    "completion_menu_meta_bg": "#1a1a2e",
    "completion_menu_meta_current_bg": "#333355",
}

LIGHT_COLORS: Dict[str, str] = {
    "banner_border": "#7A4F1F",
    "banner_title": "#8B6914",
    "banner_accent": "#A0651C",
    "banner_dim": "#7A5A0F",
    "banner_text": "#3D2F13",
    "ui_accent": "#A0651C",
    "ui_label": "#7A5A0F",
    "ui_ok": "#2E7D32",
    "ui_error": "#C62828",
    "ui_warn": "#E65100",
    "prompt": "",  # inherit terminal fg
    "input_rule": "#7A4F1F",
    "response_border": "#8B6914",
    "session_label": "#7A5A0F",
    "session_border": "#7A5A0F",
    "status_bar_bg": "#F0EDE6",
    "status_bar_text": "#333333",
    "status_bar_strong": "#8B6914",
    "status_bar_dim": "#666666",
    "status_bar_good": "#2E7D32",
    "status_bar_warn": "#8B6914",
    "status_bar_bad": "#D84315",
    "status_bar_critical": "#B71C1C",
    "voice_status_bg": "#F0EDE6",
    "selection_bg": "#D4E4F7",
    "completion_menu_bg": "#F5F5F5",
    "completion_menu_current_bg": "#E8D9B8",
    "completion_menu_meta_bg": "#F5F5F5",
    "completion_menu_meta_current_bg": "#E8D9B8",
}


def set_theme_override(theme: Optional[str]) -> None:
    """Force light/dark/auto. Clears the detection cache."""
    global _THEME_OVERRIDE, _MODE_CACHE
    raw = (theme or "auto").strip().lower()
    if raw in ("light", "dark", "auto"):
        _THEME_OVERRIDE = raw  # type: ignore[assignment]
    else:
        _THEME_OVERRIDE = "auto"
    _MODE_CACHE = None


def get_theme_override() -> ThemeName:
    return _THEME_OVERRIDE or "auto"


def clear_mode_cache() -> None:
    global _MODE_CACHE
    _MODE_CACHE = None


def init_theme_from_config(config: dict) -> None:
    """Read ``display.theme`` from config (light|dark|auto)."""
    display = config.get("display") or {}
    if not isinstance(display, dict):
        display = {}
    theme = display.get("theme", "auto")
    set_theme_override(theme if isinstance(theme, str) else "auto")


def _luminance_from_hex(hex_str: str) -> float | None:
    s = (hex_str or "").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6 or not all(c in "0123456789abcdefABCDEF" for c in s):
        return None
    try:
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError:
        return None
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def _query_osc11_background() -> str | None:
    """Ask the terminal for its background color via OSC 11."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return None
    if any(os.environ.get(v) for v in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY")):
        return None
    try:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
    except Exception:
        return None
    try:
        try:
            tty.setcbreak(fd)
        except Exception:
            return None
        try:
            sys.stdout.write("\x1b]11;?\x1b\\")
            sys.stdout.flush()
        except Exception:
            return None
        import select

        deadline = time.monotonic() + 0.1
        buf = b""
        while time.monotonic() < deadline:
            r, _, _ = select.select([fd], [], [], deadline - time.monotonic())
            if not r:
                continue
            try:
                chunk = os.read(fd, 64)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            if b"\x1b\\" in buf or b"\x07" in buf:
                break
        m = re.search(rb"rgb:([0-9a-fA-F]+)/([0-9a-fA-F]+)/([0-9a-fA-F]+)", buf)
        if not m:
            return None

        def norm(h: bytes) -> int:
            v = int(h, 16)
            bits = len(h) * 4
            return (v * 255) // ((1 << bits) - 1) if bits else 0

        r, g, b = norm(m.group(1)), norm(m.group(2)), norm(m.group(3))
        return f"#{r:02X}{g:02X}{b:02X}"
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSAFLUSH, old)
        except Exception:
            pass


def detect_light_mode(*, force_refresh: bool = False) -> bool:
    """Return True when the active display mode is light."""
    global _MODE_CACHE
    if not force_refresh and _MODE_CACHE is not None:
        return _MODE_CACHE

    result = False
    try:
        override = _THEME_OVERRIDE or "auto"
        if override == "light":
            result = True
            _MODE_CACHE = result
            return result
        if override == "dark":
            result = False
            _MODE_CACHE = result
            return result

        for var in ("HERMES_LIGHT", "HERMES_TUI_LIGHT"):
            v = (os.environ.get(var) or "").strip().lower()
            if _TRUE_RE.match(v):
                result = True
                _MODE_CACHE = result
                return result
            if _FALSE_RE.match(v):
                _MODE_CACHE = result
                return result

        theme = (os.environ.get("HERMES_TUI_THEME") or "").strip().lower()
        if theme == "light":
            result = True
            _MODE_CACHE = result
            return result
        if theme == "dark":
            _MODE_CACHE = result
            return result

        bg_lum = _luminance_from_hex(os.environ.get("HERMES_TUI_BACKGROUND") or "")
        if bg_lum is not None:
            result = bg_lum >= 0.5
            _MODE_CACHE = result
            return result

        cfgbg = (os.environ.get("COLORFGBG") or "").strip()
        if cfgbg:
            last = cfgbg.split(";")[-1] if ";" in cfgbg else cfgbg
            if last.isdigit():
                bg = int(last)
                if bg in {7, 15}:
                    result = True
                    _MODE_CACHE = result
                    return result
                if 0 <= bg < 16:
                    _MODE_CACHE = result
                    return result

        bg_color = _query_osc11_background()
        if bg_color:
            lum = _luminance_from_hex(bg_color)
            if lum is not None:
                result = lum >= 0.5
                _MODE_CACHE = result
                return result

        tp = (os.environ.get("TERM_PROGRAM") or "").strip()
        if tp in _LIGHT_DEFAULT_TERM_PROGRAMS:
            result = True
    except Exception:
        result = False

    _MODE_CACHE = result
    return result


def active_mode_name() -> Literal["light", "dark"]:
    return "light" if detect_light_mode() else "dark"


def active_palette() -> Dict[str, str]:
    return LIGHT_COLORS if detect_light_mode() else DARK_COLORS


def resolve_color(key: str, fallback: str = "") -> str:
    """Resolve a UI color from the active light/dark palette only."""
    palette = active_palette()
    if key in palette:
        return palette[key]
    # Alias common fallbacks so callers with legacy keys still work.
    if fallback.startswith("#") or fallback == "":
        # Prefer same-key from the other palette? No — use fallback if
        # provided and looks like a color, else empty/default text.
        if key in DARK_COLORS:
            return DARK_COLORS[key] if not detect_light_mode() else LIGHT_COLORS.get(key, fallback)
        return fallback
    return fallback
