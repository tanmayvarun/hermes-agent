"""AX-native click/type via PyObjC — used when Ghost CLI is unavailable.

WhatsApp (Electron) ignores AXValue writes. Typing must:
1. Bring WhatsApp to front
2. Click the real AXTextField/AXSearchField (geometric center)
3. Clear the field
4. Send CGEvent unicode keystrokes
5. Verify AXValue contains the query
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, List, Optional, Tuple

from plugin.executor.ghost import ExecResult

logger = logging.getLogger(__name__)

_BIDI = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_EDITABLE_ROLES = {"AXTextField", "AXSearchField", "AXComboBox"}


def ax_available() -> bool:
    try:
        from ApplicationServices import AXUIElementCreateApplication  # noqa: F401
        from AppKit import NSWorkspace  # noqa: F401

        return True
    except ImportError:
        return False


def _clean(s: str) -> str:
    return _BIDI.sub("", s or "").strip()


def _pid_for_app(app_name: str) -> Optional[int]:
    from AppKit import NSWorkspace

    needle = (app_name or "").lower()
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        name = str(app.localizedName() or "")
        bundle = str(app.bundleIdentifier() or "")
        if name.lower() == needle or needle in name.lower():
            return int(app.processIdentifier())
        if "whatsapp" in needle and "whatsapp" in bundle.lower():
            return int(app.processIdentifier())
    return None


def _activate_app(app_name: str) -> None:
    from AppKit import NSRunningApplication
    import subprocess

    # Launch Services raise is more reliable than activateWithOptions alone
    subprocess.run(["open", "-a", app_name], capture_output=True, timeout=10)
    pid = _pid_for_app(app_name)
    if pid is None:
        return
    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    if app is not None:
        app.activateWithOptions_(1 << 1)
    time.sleep(0.4)


def _ax_attr(el: Any, attr: str) -> Any:
    from ApplicationServices import AXUIElementCopyAttributeValue

    try:
        result = AXUIElementCopyAttributeValue(el, attr, None)
        if isinstance(result, tuple):
            return result[1] if len(result) >= 2 else None
        return result
    except Exception:
        return None


def _ax_str(el: Any, attr: str) -> str:
    v = _ax_attr(el, attr)
    return "" if v is None else _clean(str(v))


def _ax_children(el: Any) -> List[Any]:
    try:
        kids = _ax_attr(el, "AXChildren")
        return list(kids) if kids is not None else []
    except Exception:
        return []


def _walk(
    el: Any, depth: int = 0, max_depth: int = 35
) -> List[Tuple[Any, str, str, str, str, str]]:
    if depth > max_depth or el is None:
        return []
    role = _ax_str(el, "AXRole")
    title = _ax_str(el, "AXTitle") or _ax_str(el, "AXValue")
    desc = _ax_str(el, "AXDescription") or _ax_str(el, "AXHelp")
    placeholder = _ax_str(el, "AXPlaceholderValue")
    role_description = _ax_str(el, "AXRoleDescription")
    out = [(el, role, title, desc, placeholder, role_description)]
    for child in _ax_children(el):
        out.extend(_walk(child, depth + 1, max_depth))
    return out


def _app_root(app_name: str) -> Any:
    from ApplicationServices import AXUIElementCreateApplication

    pid = _pid_for_app(app_name)
    if pid is None:
        raise RuntimeError(f"app not running: {app_name}")
    return AXUIElementCreateApplication(pid)


def _match_score(needle: str, title: str, desc: str, role: str, placeholder: str = "") -> float:
    n = _clean(needle).lower()
    if not n:
        return 0.0
    title_c = _clean(title).lower()
    desc_c = _clean(desc).lower()
    ph_c = _clean(placeholder).lower()
    blob = f"{title_c} {desc_c} {ph_c}".strip()
    # Exact title/desc beats substring ("Search" must not lose to "Search results")
    if title_c == n or desc_c == n or ph_c == n:
        return 4.0
    if blob == n:
        return 3.5
    # Penalize longer labels that merely contain the needle
    if n in title_c or n in desc_c:
        extra = max(len(title_c), len(desc_c)) - len(n)
        return max(0.5, 2.0 - 0.15 * extra)
    nt, bt = set(n.split()), set(blob.split())
    if nt and bt and nt <= bt:
        return 1.5
    return 0.0


def _text_input_score(
    el: Any,
    role: str,
    title: str,
    desc: str,
    placeholder: str = "",
    role_description: str = "",
) -> float:
    """Score whether an AX element can plausibly receive text input.

    We intentionally do not require a textbook editable role alone. Electron apps
    often surface search inputs through composite surfaces, so we combine role,
    focus, placeholder, role description, and live value evidence.
    """

    blob = f"{title} {desc} {placeholder} {role_description}".lower()
    value = _ax_str(el, "AXValue")
    focused = bool(_ax_attr(el, "AXFocused"))
    enabled = bool(_ax_attr(el, "AXEnabled"))
    selected_range = _ax_attr(el, "AXSelectedTextRange")

    score = 0.0
    if role in _EDITABLE_ROLES:
        score += 2.25
    elif role in {"AXButton", "AXStaticText", "AXGroup", "AXUnknown"}:
        score += 0.15
    if role_description and any(tok in role_description.lower() for tok in ("text", "field", "search", "input")):
        score += 1.0
    if "search" in blob:
        score += 1.6
    if placeholder and any(tok in placeholder.lower() for tok in ("search", "type", "find")):
        score += 1.5
    if focused:
        score += 2.2
    if selected_range is not None:
        score += 1.0
    if enabled:
        score += 0.25
    if not value:
        score += 0.4
    elif len(value) <= 80:
        score += 0.15
    else:
        score -= 2.0
    if "compose" in blob or ("message" in blob and "search" not in blob):
        score -= 4.0
    if role in {"AXButton", "AXStaticText"} and not (focused or selected_range is not None):
        if "search" not in blob and not placeholder:
            score -= 1.0
    return score


def _find_element(
    app_name: str,
    needle: str,
    *,
    prefer_roles: Optional[List[str]] = None,
) -> Optional[Any]:
    root = _app_root(app_name)
    best = None
    best_score = 0.0
    for el, role, title, desc, placeholder, role_description in _walk(root):
        score = _match_score(needle, title, desc, role, placeholder)
        if prefer_roles and role in prefer_roles:
            score += 0.5
        # WhatsApp sidebar Search is often AXStaticText
        if needle.lower() == "search" and role == "AXStaticText" and _clean(title).lower() == "search":
            score += 1.0
        if score > best_score:
            best_score = score
            best = el
    return best if best_score >= 1.0 else None


def _find_search_text_field(app_name: str) -> Tuple[Optional[Any], str]:
    root = _app_root(app_name)
    candidates: List[Tuple[float, Any, str]] = []
    for el, role, title, desc, placeholder, role_description in _walk(root):
        blob = f"{title} {desc} {placeholder} {role_description}".lower()
        if not any(
            (
                "search" in blob,
                "find" in blob,
                bool(_ax_attr(el, "AXFocused")),
                bool(_ax_attr(el, "AXSelectedTextRange")),
                role in _EDITABLE_ROLES,
            )
        ):
            continue
        score = _text_input_score(el, role, title, desc, placeholder, role_description)
        label = title or placeholder or desc or role
        candidates.append((score, el, label))
    if not candidates:
        return None, ""
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_el, best_label = candidates[0]
    if best_score < 2.8:
        return None, ""
    return best_el, best_label


def _is_editable_text_target(el: Any) -> bool:
    if el is None:
        return False
    try:
        role = str(_ax_attr(el, "AXRole") or "")
        title = _ax_str(el, "AXTitle") or _ax_str(el, "AXValue")
        desc = _ax_str(el, "AXDescription") or _ax_str(el, "AXHelp")
        placeholder = _ax_str(el, "AXPlaceholderValue")
        role_description = _ax_str(el, "AXRoleDescription")
    except Exception:
        role = ""
        title = ""
        desc = ""
        placeholder = ""
        role_description = ""
    return _text_input_score(el, role, title, desc, placeholder, role_description) >= 2.8


def _press(el: Any) -> Any:
    from ApplicationServices import AXUIElementPerformAction

    return AXUIElementPerformAction(el, "AXPress")


def _unpack_point(val: Any) -> Optional[Tuple[float, float]]:
    if val is None:
        return None
    try:
        if hasattr(val, "x") and hasattr(val, "y"):
            return float(val.x), float(val.y)
    except Exception:
        pass
    try:
        if hasattr(val, "__getitem__"):
            return float(val[0]), float(val[1])
    except Exception:
        pass
    # AXValueRef — byref(CGPoint) fails on PyObjC; repr embeds the numbers:
    # <AXValue …> {value = x:12.000000 y:34.000000 type = kAXValueCGPointType}
    m = re.search(r"x:([-\d.]+)\s+y:([-\d.]+)", str(val))
    if m:
        return float(m.group(1)), float(m.group(2))
    try:
        from ApplicationServices import AXValueGetValue, kAXValueCGPointType
        from Quartz import CGPoint

        pt = CGPoint(0, 0)
        if AXValueGetValue(val, kAXValueCGPointType, pt):
            return float(pt.x), float(pt.y)
    except Exception:
        pass
    return None


def _unpack_size(val: Any) -> Optional[Tuple[float, float]]:
    if val is None:
        return None
    try:
        if hasattr(val, "width") and hasattr(val, "height"):
            return float(val.width), float(val.height)
    except Exception:
        pass
    try:
        if hasattr(val, "__getitem__"):
            return float(val[0]), float(val[1])
    except Exception:
        pass
    m = re.search(r"w:([-\d.]+)\s+h:([-\d.]+)", str(val))
    if m:
        return float(m.group(1)), float(m.group(2))
    try:
        from ApplicationServices import AXValueGetValue, kAXValueCGSizeType
        from Quartz import CGSize

        sz = CGSize(0, 0)
        if AXValueGetValue(val, kAXValueCGSizeType, sz):
            return float(sz.width), float(sz.height)
    except Exception:
        pass
    return None


def _query_visible_in_search(app: str, text: str) -> Tuple[bool, str]:
    """WhatsApp often mirrors the query on AXStaticText(desc=Search), not AXTextField.AXValue."""
    needle = _clean(text).lower()
    if not needle:
        return False, ""
    for el, role, title, desc, placeholder, role_description in _walk(_app_root(app)):
        value = _ax_str(el, "AXValue")
        blob_parts = [title, desc, placeholder, value]
        if role in {"AXTextField", "AXSearchField", "AXComboBox"}:
            if needle in _clean(value).lower() or needle in _clean(placeholder).lower() and needle in _clean(value).lower():
                if needle in _clean(value).lower():
                    return True, f"{role} value={value!r}"
        # Electron search input mirror
        if "search" in _clean(desc).lower() and needle in _clean(title).lower():
            return True, f"{role} title={title!r} desc={desc!r}"
        if "search" in _clean(desc).lower() and needle in _clean(value).lower():
            return True, f"{role} value={value!r} desc={desc!r}"
        if role == "AXStaticText" and needle == _clean(title).lower() and "search" in " ".join(blob_parts).lower():
            return True, f"static title={title!r}"
    return False, ""


def _frame_center(el: Any) -> Optional[Tuple[float, float]]:
    pos = _unpack_point(_ax_attr(el, "AXPosition"))
    size = _unpack_size(_ax_attr(el, "AXSize"))
    if not pos or not size:
        return None
    x, y = pos
    w, h = size
    if w <= 0 or h <= 0:
        return None
    return x + w / 2.0, y + h / 2.0


def _bounds_center(bounds: Optional[Tuple[float, float, float, float]]) -> Optional[Tuple[float, float]]:
    if not bounds or len(bounds) < 4:
        return None
    x, y, w, h = float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3])
    if w <= 4 or h <= 4:
        return None  # zero/tiny AX frames are not clickable (common for WA Voice Call)
    return x + w / 2.0, y + h / 2.0


def _mouse_click(x: float, y: float) -> None:
    from Quartz import (
        CGEventCreateMouseEvent,
        CGEventPost,
        kCGEventLeftMouseDown,
        kCGEventLeftMouseUp,
        kCGHIDEventTap,
        kCGMouseButtonLeft,
    )

    pt = (x, y)
    down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, pt, kCGMouseButtonLeft)
    up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, pt, kCGMouseButtonLeft)
    CGEventPost(kCGHIDEventTap, down)
    time.sleep(0.02)
    CGEventPost(kCGHIDEventTap, up)
    time.sleep(0.15)


def _mouse_move(x: float, y: float) -> None:
    from Quartz import CGEventCreateMouseEvent, CGEventPost, kCGEventMouseMoved, kCGHIDEventTap

    pt = (x, y)
    ev = CGEventCreateMouseEvent(None, kCGEventMouseMoved, pt, 0)
    CGEventPost(kCGHIDEventTap, ev)
    time.sleep(0.12)


def _mouse_right_click(x: float, y: float) -> None:
    from Quartz import (
        CGEventCreateMouseEvent,
        CGEventPost,
        kCGEventRightMouseDown,
        kCGEventRightMouseUp,
        kCGHIDEventTap,
        kCGMouseButtonRight,
    )

    pt = (x, y)
    down = CGEventCreateMouseEvent(None, kCGEventRightMouseDown, pt, kCGMouseButtonRight)
    up = CGEventCreateMouseEvent(None, kCGEventRightMouseUp, pt, kCGMouseButtonRight)
    CGEventPost(kCGHIDEventTap, down)
    time.sleep(0.02)
    CGEventPost(kCGHIDEventTap, up)
    time.sleep(0.15)


def _keydown(key_code: int, *, cmd: bool = False) -> None:
    from Quartz import (
        CGEventCreateKeyboardEvent,
        CGEventPost,
        CGEventSetFlags,
        kCGEventFlagMaskCommand,
        kCGHIDEventTap,
    )

    down = CGEventCreateKeyboardEvent(None, key_code, True)
    up = CGEventCreateKeyboardEvent(None, key_code, False)
    if cmd:
        CGEventSetFlags(down, kCGEventFlagMaskCommand)
        CGEventSetFlags(up, kCGEventFlagMaskCommand)
    CGEventPost(kCGHIDEventTap, down)
    CGEventPost(kCGHIDEventTap, up)


def _type_via_cgevent(text: str) -> None:
    from Quartz import (
        CGEventCreateKeyboardEvent,
        CGEventKeyboardSetUnicodeString,
        CGEventPost,
        kCGHIDEventTap,
    )

    for ch in text:
        down = CGEventCreateKeyboardEvent(None, 0, True)
        up = CGEventCreateKeyboardEvent(None, 0, False)
        CGEventKeyboardSetUnicodeString(down, len(ch), ch)
        CGEventKeyboardSetUnicodeString(up, len(ch), ch)
        CGEventPost(kCGHIDEventTap, down)
        CGEventPost(kCGHIDEventTap, up)
        time.sleep(0.05)
    time.sleep(0.1)


def _type_via_system_events(app: str, text: str) -> bool:
    """Keystrokes via System Events into the frontmost process (Terminal AX host)."""
    import subprocess

    # Escape for AppleScript string
    esc = text.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
    tell application "{app}" to activate
    delay 0.35
    tell application "System Events"
      tell process "{app}"
        set frontmost to true
        keystroke "{esc}"
      end tell
    end tell
    '''
    try:
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
        return proc.returncode == 0
    except Exception as e:
        logger.warning("System Events type failed: %s", e)
        return False


def _paste_via_clipboard(app: str, text: str) -> bool:
    """Use the system clipboard plus Cmd+V as a robust text-injection path."""
    import subprocess

    prev = ""
    try:
        prev_proc = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
        if prev_proc.returncode == 0:
            prev = prev_proc.stdout
    except Exception:
        prev = ""

    try:
        subprocess.run(["pbcopy"], input=text, text=True, capture_output=True, timeout=5)
        subprocess.run(
            [
                "osascript",
                "-e",
                f'tell application "{app}" to activate',
                "-e",
                "delay 0.15",
                "-e",
                'tell application "System Events" to keystroke "v" using command down',
            ],
            capture_output=True,
            timeout=10,
        )
        time.sleep(0.15)
        return True
    except Exception as e:
        logger.warning("Clipboard paste failed: %s", e)
        return False
    finally:
        try:
            subprocess.run(["pbcopy"], input=prev, text=True, capture_output=True, timeout=5)
        except Exception:
            pass


def _open_search_ui(app: str, bounds: Optional[Tuple[float, float, float, float]] = None) -> str:
    """Open WhatsApp search. Prefer Cmd+F — Search chrome often has invalid AXPosition (x=-1)."""
    import subprocess

    _activate_app(app)
    time.sleep(0.25)
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'tell application "{app}" to activate',
                "-e",
                "delay 0.25",
                "-e",
                'tell application "System Events" to keystroke "f" using command down',
            ],
            capture_output=True,
            timeout=10,
        )
        time.sleep(0.65)
    except Exception:
        _keydown(3, cmd=True)
        time.sleep(0.55)

    for _ in range(8):
        field, _ = _find_search_text_field(app)
        if field is not None:
            return "Cmd+F search shortcut"
        time.sleep(0.12)

    # Fallback: click Search chrome / observed bounds
    for prefer in (
        ["AXStaticText", "AXButton"],
        ["AXButton", "AXStaticText", "AXTextField", "AXSearchField"],
    ):
        chrome = _find_element(app, "Search", prefer_roles=prefer)
        if chrome is None:
            continue
        center = _frame_center(chrome) or _bounds_center(bounds)
        if center and center[0] >= 0 and center[1] >= 0:
            _activate_app(app)
            _mouse_click(center[0], center[1])
            for _ in range(8):
                field, _ = _find_search_text_field(app)
                if field is not None:
                    return f"clicked Search center={center}"
                time.sleep(0.12)
            return f"clicked Search center={center}"
        try:
            _press(chrome)
            for _ in range(8):
                field, _ = _find_search_text_field(app)
                if field is not None:
                    return "pressed Search via AXPress"
                time.sleep(0.12)
            return "pressed Search via AXPress"
        except Exception:
            pass

    center = _bounds_center(bounds)
    if center and center[0] >= 0 and center[1] >= 0:
        _activate_app(app)
        _mouse_click(center[0], center[1])
        time.sleep(0.6)
        return f"clicked Search bounds center={center}"
    return "Cmd+F search shortcut (no textfield confirmed)"


def _focus_field(app: str, el: Any, bounds: Optional[Tuple[float, float, float, float]] = None) -> None:
    from ApplicationServices import AXUIElementSetAttributeValue

    _activate_app(app)
    try:
        AXUIElementSetAttributeValue(el, "AXFocused", True)
    except Exception:
        pass
    try:
        _press(el)
    except Exception:
        pass
    center = _frame_center(el) or _bounds_center(bounds)
    if center:
        _activate_app(app)
        _mouse_click(center[0], center[1])
    time.sleep(0.3)


def ax_click(
    app: str,
    target: str,
    *,
    bounds: Optional[Tuple[float, float, float, float]] = None,
) -> ExecResult:
    if not ax_available():
        return ExecResult(ok=False, backend="ax", message="PyObjC ApplicationServices unavailable")
    try:
        _activate_app(app)
        prefer = ["AXButton", "AXLink", "AXMenuItem", "AXCheckBox", "AXPopUpButton", "AXStaticText"]
        if _clean(target).lower() == "search":
            # Opening search via Cmd+F is more reliable than clicking chrome
            # (AXPosition for Search is often x=-1).
            how = _open_search_ui(app, bounds=bounds)
            return ExecResult(
                ok=True,
                backend="ax",
                message=f"open Search via {how}",
                command=f"ax_click {app} {target}",
            )
        # Prefer world-model entity bounds when valid — live WhatsApp often has a
        # search-mirror AXStaticText title=<query> that steals name-based lookup.
        bounds_center = _bounds_center(bounds)
        if bounds_center is not None and bounds_center[0] >= 0 and bounds_center[1] >= 0:
            _mouse_click(bounds_center[0], bounds_center[1])
            time.sleep(0.25)
            return ExecResult(
                ok=True,
                backend="ax",
                message=f"click {_clean(target)!r} center={bounds_center} via entity bounds",
                command=f"ax_click {app} {target}",
            )
        el = _find_element(app, target, prefer_roles=["AXButton", "AXLink", "AXMenuItem"])
        if el is None:
            el = _find_element(app, target, prefer_roles=prefer)
        if el is None:
            el = _find_element(app, target, prefer_roles=["AXStaticText", "AXButton"])
        center = _frame_center(el) if el is not None else None
        if center is not None and (center[0] < 0 or center[1] < 0):
            center = None
        if center is None and el is None:
            return ExecResult(
                ok=False,
                backend="ax",
                message=f"AX element not found for {target!r}",
                command=f"ax_click {target}",
            )
        if center:
            _mouse_click(center[0], center[1])
            err = 0
        else:
            err = _press(el)
        time.sleep(0.25)
        return ExecResult(
            ok=True,
            backend="ax",
            message=f"click {_clean(target)!r} center={center} code={err!r}",
            command=f"ax_click {app} {target}",
        )
    except Exception as e:
        logger.exception("ax_click failed")
        return ExecResult(ok=False, backend="ax", message=str(e), command=f"ax_click {target}")


def ax_hover(
    app: str,
    target: str,
    *,
    bounds: Optional[Tuple[float, float, float, float]] = None,
) -> ExecResult:
    if not ax_available():
        return ExecResult(ok=False, backend="ax", message="PyObjC ApplicationServices unavailable")
    try:
        _activate_app(app)
        el = _find_element(app, target, prefer_roles=["AXButton", "AXLink", "AXMenuItem", "AXStaticText"])
        center = _frame_center(el) if el is not None else None
        if center is None:
            center = _bounds_center(bounds)
        if center is None:
            return ExecResult(ok=False, backend="ax", message=f"hover target not found for {target!r}", command=f"ax_hover {app} {target}")
        _mouse_move(center[0], center[1])
        return ExecResult(
            ok=True,
            backend="ax",
            message=f"hover {_clean(target)!r} center={center}",
            command=f"ax_hover {app} {target}",
        )
    except Exception as e:
        logger.exception("ax_hover failed")
        return ExecResult(ok=False, backend="ax", message=str(e), command=f"ax_hover {target}")


def ax_context_click(
    app: str,
    target: str,
    *,
    bounds: Optional[Tuple[float, float, float, float]] = None,
) -> ExecResult:
    if not ax_available():
        return ExecResult(ok=False, backend="ax", message="PyObjC ApplicationServices unavailable")
    try:
        _activate_app(app)
        el = _find_element(app, target, prefer_roles=["AXButton", "AXLink", "AXMenuItem", "AXStaticText"])
        center = _frame_center(el) if el is not None else None
        if center is None:
            center = _bounds_center(bounds)
        if center is None:
            return ExecResult(ok=False, backend="ax", message=f"context click target not found for {target!r}", command=f"ax_context_click {app} {target}")
        _mouse_right_click(center[0], center[1])
        return ExecResult(
            ok=True,
            backend="ax",
            message=f"context click {_clean(target)!r} center={center}",
            command=f"ax_context_click {app} {target}",
        )
    except Exception as e:
        logger.exception("ax_context_click failed")
        return ExecResult(ok=False, backend="ax", message=str(e), command=f"ax_context_click {target}")


def ax_press_escape(app: str) -> ExecResult:
    """Send Escape to the target app (dismiss overlays / cancel call UI)."""
    import subprocess

    try:
        _activate_app(app)
        time.sleep(0.15)
        subprocess.run(
            [
                "osascript",
                "-e",
                f'tell application "{app}" to activate',
                "-e",
                "delay 0.15",
                "-e",
                'tell application "System Events" to key code 53',
            ],
            capture_output=True,
            timeout=5,
        )
        time.sleep(0.35)
        return ExecResult(ok=True, backend="ax", message="pressed Escape", command="key code 53")
    except Exception as e:
        return ExecResult(ok=False, backend="ax", message=f"Escape failed: {e}", command="key code 53")


def ax_hangup_call(
    app: str,
    *,
    bounds: Optional[Tuple[float, float, float, float]] = None,
    label: str = "End Call",
) -> ExecResult:
    """Hang up WhatsApp call UI. Never report success for a no-op center=None click.

    Order: valid bounds click → live AX End Call/Decline with frame → AXPress → Escape.
    """
    if not ax_available():
        return ExecResult(ok=False, backend="ax", message="PyObjC ApplicationServices unavailable")
    try:
        _activate_app(app)
        time.sleep(0.15)
        center = _bounds_center(bounds)
        if center is not None and center[0] >= 0 and center[1] >= 0:
            _mouse_click(center[0], center[1])
            time.sleep(0.3)
            return ExecResult(
                ok=True,
                backend="ax",
                message=f"hangup click {label!r} center={center} via bounds",
                command=f"ax_hangup {app}",
            )

        for needle in ("End Call", "End call", "Decline", label):
            if not needle:
                continue
            el = _find_element(app, needle, prefer_roles=["AXButton", "AXMenuItem", "AXLink"])
            if el is None:
                continue
            frame = _frame_center(el)
            if frame is not None and frame[0] >= 0 and frame[1] >= 0:
                _mouse_click(frame[0], frame[1])
                time.sleep(0.3)
                return ExecResult(
                    ok=True,
                    backend="ax",
                    message=f"hangup click {needle!r} center={frame} via AX",
                    command=f"ax_hangup {app}",
                )
            try:
                err = _press(el)
                time.sleep(0.3)
                return ExecResult(
                    ok=True,
                    backend="ax",
                    message=f"hangup AXPress {needle!r} code={err!r}",
                    command=f"ax_hangup {app}",
                )
            except Exception:
                continue

        esc = ax_press_escape(app)
        if esc.ok:
            return ExecResult(
                ok=True,
                backend="ax",
                message="hangup via Escape (no clickable End Call)",
                command=f"ax_hangup {app}",
            )
        return ExecResult(
            ok=False,
            backend="ax",
            message="hangup failed: no clickable End Call and Escape failed",
            command=f"ax_hangup {app}",
        )
    except Exception as e:
        logger.exception("ax_hangup_call failed")
        return ExecResult(ok=False, backend="ax", message=str(e), command=f"ax_hangup {app}")


def ax_type(
    app: str,
    text: str,
    *,
    into: Optional[str] = None,
    submit: bool = False,
    search_bounds: Optional[Tuple[float, float, float, float]] = None,
) -> ExecResult:
    if not ax_available():
        return ExecResult(ok=False, backend="ax", message="PyObjC ApplicationServices unavailable")
    try:
        from ApplicationServices import AXUIElementSetAttributeValue
        import subprocess

        esc = text.replace("\\", "\\\\").replace('"', '\\"')
        attempt_notes: List[str] = []
        ok = False
        evidence = ""
        field_label = ""
        open_how = ""
        value_now = ""

        for attempt in range(2):
            _activate_app(app)
            time.sleep(0.25)
            if attempt > 0:
                ax_press_escape(app)
                time.sleep(0.15)
            open_how = _open_search_ui(app, bounds=search_bounds)
            attempt_notes.append(f"open={open_how}")

            field, field_label = _find_search_text_field(app)
            if field is None and into:
                field = _find_element(
                    app,
                    into,
                    prefer_roles=["AXTextField", "AXSearchField", "AXComboBox"],
                )
                if field is not None and not _is_editable_text_target(field):
                    field = None
                else:
                    field_label = into or ""

            if field is None:
                attempt_notes.append("editable_field=missing")
                continue

            try:
                AXUIElementSetAttributeValue(field, "AXFocused", True)
            except Exception:
                pass
            try:
                _press(field)
            except Exception:
                pass
            center = _frame_center(field) or _bounds_center(search_bounds)
            if center:
                _activate_app(app)
                _mouse_click(center[0], center[1])
            time.sleep(0.2)
            try:
                AXUIElementSetAttributeValue(field, "AXValue", "")
                AXUIElementSetAttributeValue(field, "AXValue", text)
                time.sleep(0.25)
            except Exception as e:
                logger.warning("AXValue set failed: %s", e)

            pasted = _paste_via_clipboard(app, text)
            attempt_notes.append(f"paste={pasted}")

            if not pasted:
                subprocess.run(
                    [
                        "osascript",
                        "-e",
                        f'tell application "{app}" to activate',
                        "-e",
                        "delay 0.2",
                        "-e",
                        'tell application "System Events" to keystroke "a" using command down',
                        "-e",
                        "delay 0.05",
                        "-e",
                        'tell application "System Events" to key code 51',
                        "-e",
                        "delay 0.08",
                        "-e",
                        f'tell application "System Events" to keystroke "{esc}"',
                    ],
                    capture_output=True,
                    timeout=20,
                )
                time.sleep(0.55)
            else:
                time.sleep(0.35)

            if not _query_visible_in_search(app, text)[0]:
                _type_via_cgevent(text)
                time.sleep(0.35)

            if field is not None:
                try:
                    AXUIElementSetAttributeValue(field, "AXValue", text)
                    time.sleep(0.15)
                except Exception:
                    pass

            value_now = _ax_str(field, "AXValue") if field is not None else ""
            ok, evidence = _query_visible_in_search(app, text)
            if not ok and text.lower() in (value_now or "").lower():
                ok = True
                evidence = f"textfield AXValue={value_now!r}"
            if not ok and pasted and text.lower() in (value_now or "").lower():
                ok = True
                evidence = f"clipboard AXValue={value_now!r}"
            if ok:
                break

        if submit and ok:
            _keydown(36)
            time.sleep(0.35)

        if not ok and any("editable_field=missing" in note for note in attempt_notes):
            return ExecResult(
                ok=False,
                backend="ax",
                message=f"no editable field confirmed for {text!r}; attempts={attempt_notes!r}",
                command=f"ax_type {app} {text}",
            )

        return ExecResult(
            ok=ok,
            backend="ax",
            message=(
                f"typed {text!r} into search field label={field_label or 'Search'!r} "
                f"AXValue={value_now!r} open={open_how!r} evidence={evidence!r} "
                f"attempts={attempt_notes!r} submit={submit}"
            ),
            command=f"ax_type {app} {text}",
        )
    except Exception as e:
        logger.exception("ax_type failed")
        return ExecResult(ok=False, backend="ax", message=str(e), command=f"ax_type {text}")
