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


def _is_frontmost(app_name: str) -> bool:
    """Whether the named app is currently the frontmost application.

    Capability runtimes call this so they only activate the app when it is *not*
    already frontmost — keeping background actuation background (no needless raise)
    and only foregrounding when a synthetic click/keystroke genuinely requires it.
    """
    needle = _clean(str(app_name or "")).lower()
    if not needle:
        return False
    try:
        from AppKit import NSWorkspace

        front = NSWorkspace.sharedWorkspace().frontmostApplication()
    except Exception:
        return False
    if front is None:
        return False
    name = _clean(str(front.localizedName() or "")).lower()
    if not name:
        return False
    return name == needle or needle in name or name in needle


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


def _action_names(el: Any) -> List[str]:
    """The AX actions an element advertises (e.g. AXPress, AXConfirm)."""
    try:
        from ApplicationServices import AXUIElementCopyActionNames
    except Exception:
        return []
    try:
        result = AXUIElementCopyActionNames(el, None)
        names = result[1] if isinstance(result, tuple) and len(result) >= 2 else result
        return [str(n) for n in (names or [])]
    except Exception:
        return []


def _supports_press(el: Any) -> bool:
    """Whether the element can be invoked programmatically via AXPress.

    This is the gate for *background* actuation: if the app exposes an AXPress
    action on the target, the agent can invoke it directly — no activation, no
    mouse movement, nothing the user sees. AX-blind apps (WhatsApp/Electron)
    advertise no actions, so this returns False and the caller falls back to a
    foreground synthetic click.
    """
    return "AXPress" in _action_names(el)


def _press_ok(err: Any) -> bool:
    """kAXErrorSuccess is 0; PyObjC may return None on success."""
    return err in (0, None)


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


def _clear_focused_field_keys(app: str) -> bool:
    """Cmd+A then Delete so type fallbacks replace the field instead of appending.

    Live 202832: paste reported ok but verify failed, then CGEvent appended into
    a half-corrupt WhatsApp search box → ``zarooratwala Pallavipo`` / No results.
    """
    import subprocess

    try:
        proc = subprocess.run(
            [
                "osascript",
                "-e",
                f'tell application "{app}" to activate',
                "-e",
                "delay 0.15",
                "-e",
                'tell application "System Events" to keystroke "a" using command down',
                "-e",
                "delay 0.05",
                "-e",
                "tell application \"System Events\" to key code 51",
                "-e",
                "delay 0.08",
            ],
            capture_output=True,
            text=True,
            timeout=12,
        )
        return proc.returncode == 0
    except Exception as e:
        logger.warning("clear focused field failed: %s", e)
        return False


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
    # Always select-all + delete before typing — never append into a dirty field.
    script = f'''
    tell application "{app}" to activate
    delay 0.35
    tell application "System Events"
      tell process "{app}"
        set frontmost to true
        keystroke "a" using command down
        delay 0.05
        key code 51
        delay 0.08
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
    """Use the system clipboard plus Cmd+V as a robust text-injection path.

    The previous clipboard must not be restored until Cmd+V has been consumed —
    restoring immediately races the paste and leaves the field empty (live
    zarooratwala: ``paste=True`` but ``AXValue=''``).
    """
    import subprocess

    prev = ""
    try:
        prev_proc = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
        if prev_proc.returncode == 0:
            prev = prev_proc.stdout
    except Exception:
        prev = ""

    pasted = False
    try:
        copy = subprocess.run(
            ["pbcopy"], input=text, text=True, capture_output=True, timeout=5
        )
        if copy.returncode != 0:
            return False
        # Select-all first so a half-typed field is replaced, not appended.
        proc = subprocess.run(
            [
                "osascript",
                "-e",
                f'tell application "{app}" to activate',
                "-e",
                "delay 0.2",
                "-e",
                'tell application "System Events" to keystroke "a" using command down',
                "-e",
                "delay 0.08",
                "-e",
                'tell application "System Events" to keystroke "v" using command down',
                "-e",
                "delay 0.35",
            ],
            capture_output=True,
            text=True,
            timeout=12,
        )
        pasted = proc.returncode == 0
        if not pasted:
            err = (proc.stderr or proc.stdout or "").strip()[:160]
            logger.warning("Clipboard paste osascript failed: %s", err or proc.returncode)
        else:
            time.sleep(0.2)
        return pasted
    except Exception as e:
        logger.warning("Clipboard paste failed: %s", e)
        return False
    finally:
        # Only restore after the paste keystroke had time to read the board.
        if pasted or prev:
            try:
                time.sleep(0.15)
                subprocess.run(
                    ["pbcopy"], input=prev, text=True, capture_output=True, timeout=5
                )
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


# Backend marker for a click the continuity gate refused. The controller keys on
# it to re-perceive instead of judging the action: nothing was attempted, so the
# affordance is not inert, the plan is not wrong, and recording an outcome here
# would let the world critic condemn a control that was never invoked.
STALE_PRECONDITION_BACKEND = "stale_precondition"


_bypass_gate_once = False


def bypass_next_gate() -> None:
    """Let the next gated click through unchecked.

    The escape hatch for a target that never settles — a live-updating list, a
    playing video. Refusing forever is its own failure mode: an agent that never
    commits is no better than one that commits wrongly, and at least a real
    attempt produces an outcome the transition machinery can learn from.
    """
    global _bypass_gate_once
    _bypass_gate_once = True


# Sizes of the boxes the system *synthesises* around an estimated point: 24 from
# open_entity's point target, 48 from a materialised vision entity. Neither is a
# measurement of a real control, and the difference matters to the commit gate —
# see TargetExpectation.estimated.
_SYNTHETIC_BOX_SIZES = (24.0, 48.0)


def _is_estimated_box(bounds: Optional[Tuple[float, float, float, float]]) -> bool:
    """Whether this rectangle was invented around a point rather than measured."""
    if not bounds or len(bounds) < 4:
        return False
    try:
        w, h = float(bounds[2]), float(bounds[3])
    except (TypeError, ValueError):
        return False
    return w == h and w in _SYNTHETIC_BOX_SIZES


def _refuse_stale_click(
    app: str,
    target: str,
    bounds: Optional[Tuple[float, float, float, float]],
) -> Optional[ExecResult]:
    """Refuse a bounds click whose target no longer reads as what was asked for."""
    global _bypass_gate_once
    if _bypass_gate_once:
        _bypass_gate_once = False
        return None
    try:
        from plugin.agent.capabilities.invoke_affordance import is_irreversible_affordance
        from plugin.perception.continuity import guard_click

        verdict = guard_click(
            app,
            _clean(target),
            bounds,
            irreversible=is_irreversible_affordance(_clean(target)),
            estimated=_is_estimated_box(bounds),
        )
    except Exception:
        return None
    if verdict is None or verdict.may_commit:
        return None
    return ExecResult(
        ok=False,
        backend=STALE_PRECONDITION_BACKEND,
        message=f"refused stale click on {_clean(target)!r}: {verdict.reason}",
        command=f"ax_click {app} {target}",
    )


def ax_click(
    app: str,
    target: str,
    *,
    bounds: Optional[Tuple[float, float, float, float]] = None,
) -> ExecResult:
    if not ax_available():
        return ExecResult(ok=False, backend="ax", message="PyObjC ApplicationServices unavailable")
    try:
        # Background-first: if the target resolves to an element that advertises
        # AXPress, invoke it directly — no activation, no mouse movement, nothing
        # the user sees. This is how an AX-rich app is driven while the user works
        # in another window. AX-blind apps (WhatsApp) resolve nothing pressable
        # here and fall through to the foreground synthetic-click path below.
        target_l = _clean(target).lower()
        # Context-menu verbs (Forward/Share/…) often advertise AXPress but only
        # commit when the app is frontmost. Live zarooratwala: background AXPress
        # 'Forward' left surface=context_menu and never opened the picker.
        _FOREGROUND_MENU_VERBS = {
            "forward",
            "forward message",
            "forward messages",
            "share",
            "reply",
            "copy",
            "delete",
            "info",
            "star",
            "pin",
            "react",
        }
        if target_l != "search" and target_l not in _FOREGROUND_MENU_VERBS:
            el_bg = _find_element(
                app,
                target,
                prefer_roles=["AXButton", "AXLink", "AXMenuItem", "AXCheckBox", "AXPopUpButton"],
            )
            if el_bg is not None and _supports_press(el_bg):
                # Geometry wins over name. When the caller supplies world bounds,
                # only background-press if the named element sits there — a
                # same-named chrome echo (filter field, breadcrumb, status) must
                # not steal the press. Without bounds, press true controls by
                # name; never treat bare static text as the target.
                bc = _bounds_center(bounds)
                fc = _frame_center(el_bg)
                role_bg = str(_ax_attr(el_bg, "AXRole") or "")
                if role_bg == "AXMenuItem":
                    coincides = False
                elif bc is not None:
                    coincides = (
                        fc is not None
                        and fc[0] >= 0
                        and fc[1] >= 0
                        and abs(fc[0] - bc[0]) <= 40.0
                        and abs(fc[1] - bc[1]) <= 40.0
                    )
                else:
                    coincides = role_bg != "AXStaticText"
                if coincides:
                    err_bg = _press(el_bg)
                    if _press_ok(err_bg):
                        time.sleep(0.2)
                        return ExecResult(
                            ok=True,
                            backend="ax_bg",
                            message=f"AXPress {_clean(target)!r} in background (no foreground)",
                            command=f"ax_click {app} {target}",
                        )

        _activate_app(app)
        prefer = ["AXButton", "AXLink", "AXMenuItem", "AXCheckBox", "AXPopUpButton", "AXStaticText"]
        if _clean(target).lower() == "search" and (
            bounds is None or _bounds_center(bounds) is None
        ):
            # Inventing Search via Cmd+F is forbidden. Callers must supply
            # grounded bounds from perception (same contract as ax_type).
            return ExecResult(
                ok=False,
                backend="ax",
                message="search_click_without_grounded_bounds; refusing Cmd+F invent",
                command=f"ax_click {app} {target}",
            )
        # Prefer world-model entity bounds when valid — live WhatsApp often has a
        # search-mirror AXStaticText title=<query> that steals name-based lookup.
        bounds_center = _bounds_center(bounds)
        if bounds_center is not None and bounds_center[0] >= 0 and bounds_center[1] >= 0:
            # Defense in depth: brain→actor owns the transactional commit gate
            # (plugin.agent.actor.execute_actor). Keep the same freshness refuse
            # here for legacy non-actor callers that still hit ax_click directly.
            refusal = _refuse_stale_click(app, target, bounds)
            if refusal is not None:
                return refusal
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
        # Grounded decision bounds own content geometry. AX label match often
        # resolves the sidebar preview that echoes the query ("zarooratwala…")
        # and steals the right-click from the conversation-pane link.
        bounds_center = _bounds_center(bounds)
        el = _find_element(app, target, prefer_roles=["AXButton", "AXLink", "AXMenuItem", "AXStaticText"])
        ax_center = _frame_center(el) if el is not None else None
        if ax_center is not None and (ax_center[0] < 0 or ax_center[1] < 0):
            ax_center = None
        center = None
        if bounds_center is not None and bounds_center[0] >= 0 and bounds_center[1] >= 0:
            center = bounds_center
            if (
                ax_center is not None
                and abs(ax_center[0] - bounds_center[0]) <= 40.0
                and abs(ax_center[1] - bounds_center[1]) <= 40.0
            ):
                center = ax_center
        else:
            center = ax_center
        if center is None:
            return ExecResult(ok=False, backend="ax", message=f"context click target not found for {target!r}", command=f"ax_context_click {app} {target}")
        # Same freshness transaction as ax_click (actor owns the primary gate).
        if bounds is not None:
            refusal = _refuse_stale_click(app, target, bounds)
            if refusal is not None:
                return refusal
        # Move the pointer onto the target and let the app register the hover
        # before right-clicking. Apps like WhatsApp only build the row's context
        # menu for the element under the cursor; a cold right-click at a point
        # the pointer never visited opens an empty/wrong menu (or nothing).
        _mouse_move(center[0], center[1])
        time.sleep(0.08)
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
        time.sleep(0.1)
        try:
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'tell application "{app}" to activate',
                    "-e",
                    "delay 0.1",
                    "-e",
                    'tell application "System Events" to key code 53',
                ],
                capture_output=True,
                timeout=2,
            )
        except Exception:
            # System Events can hang under load; CGEvent Escape still dismisses.
            _keydown(53)
        time.sleep(0.25)
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


def _looks_like_search_field_label(label: str) -> bool:
    """True when a label/placeholder describes Search — not a chat composer."""
    low = _clean(label).lower()
    if not low:
        return False
    if any(tok in low for tok in ("type a message", "message", "compose", "write a")):
        if "search" not in low and "find" not in low:
            return False
    return any(tok in low for tok in ("search", "find", "filter", "q search"))


def ax_type(
    app: str,
    text: str,
    *,
    into: Optional[str] = None,
    submit: bool = False,
    search_bounds: Optional[Tuple[float, float, float, float]] = None,
    open_search_ui: bool = False,
) -> ExecResult:
    """Type into a grounded search/filter field.

    Requires ``search_bounds`` from perception. Never invents a field via Cmd+F
    or a global AX "Search" hunt — ``open_search_ui`` is ignored (legacy flag;
    invent path closed). Callers without geometry must refuse upstream.

    Hard safety (live 095344): if the grounded click is *not* on the AX Search
    field, do **not** type at that focus — that dumped the query into the open
    chat composer (Godrej / Pallavi drafts). Retarget to the real Search field
    when AX can name it; otherwise refuse without keystrokes.
    """
    if not ax_available():
        return ExecResult(ok=False, backend="ax", message="PyObjC ApplicationServices unavailable")
    if search_bounds is None:
        return ExecResult(
            ok=False,
            backend="ax",
            message=(
                f"type_without_grounded_bounds for {text!r}; "
                "refusing Cmd+F / global Search invent"
            ),
            command=f"ax_type {app} {text}",
        )
    if open_search_ui:
        logger.warning(
            "ax_type: open_search_ui ignored (invent forbidden); using grounded bounds only"
        )
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
            # Grounded only: click the provided field geometry. Never Cmd+F.
            open_how = "grounded_field"
            center = _bounds_center(search_bounds)
            if center and center[0] >= 0 and center[1] >= 0:
                _mouse_click(center[0], center[1])
                time.sleep(0.35)
                open_how = f"clicked grounded field center={center}"
            else:
                return ExecResult(
                    ok=False,
                    backend="ax",
                    message=(
                        f"type_without_usable_bounds for {text!r}; "
                        "refusing Cmd+F / global Search invent"
                    ),
                    command=f"ax_type {app} {text}",
                )
            attempt_notes.append(f"open={open_how}")

            # Only accept an AX field that sits on the grounded rectangle —
            # unless that rectangle missed Search entirely, in which case we
            # retarget to the real Search field rather than typing into whatever
            # the wrong click focused (composer / chat row).
            def _near_grounded(el: Any) -> bool:
                fc = _frame_center(el)
                bc = _bounds_center(search_bounds)
                if not fc or not bc:
                    return False
                return abs(fc[0] - bc[0]) <= 96.0 and abs(fc[1] - bc[1]) <= 96.0

            field, field_label = _find_search_text_field(app)
            retargeted = False
            if field is not None and not _near_grounded(field):
                attempt_notes.append("ax_search_field_off_grounded_bounds")
                if _looks_like_search_field_label(field_label):
                    # Wrong geometry from the model — correct to AX Search.
                    retargeted = True
                    attempt_notes.append("retarget_ax_search_field")
                    fc = _frame_center(field)
                    if fc:
                        _activate_app(app)
                        _mouse_click(fc[0], fc[1])
                        time.sleep(0.3)
                        open_how = f"retargeted ax search center={fc}"
                else:
                    field, field_label = None, ""
            if field is None and into and _looks_like_search_field_label(into):
                cand = _find_element(
                    app,
                    into,
                    prefer_roles=["AXTextField", "AXSearchField", "AXComboBox"],
                )
                if (
                    cand is not None
                    and _is_editable_text_target(cand)
                    and _near_grounded(cand)
                ):
                    field, field_label = cand, (into or "")
                else:
                    field = None
            elif field is None and into and not _looks_like_search_field_label(into):
                # Live 095344: into='Pallavi' — a contact name is not a search field.
                attempt_notes.append(f"refuse_into_non_search_label={into!r}")

            if field is None:
                # Never type at a grounded click we could not confirm as Search.
                # Live 095344 typed into the Godrej/Pallavi composer this way.
                return ExecResult(
                    ok=False,
                    backend="ax",
                    message=(
                        f"refuse_type_non_search_focus for {text!r}; "
                        f"grounded click was not the Search field "
                        f"(into={into!r}) attempts={attempt_notes!r}"
                    ),
                    command=f"ax_type {app} {text}",
                )

            try:
                AXUIElementSetAttributeValue(field, "AXFocused", True)
            except Exception:
                pass
            try:
                _press(field)
            except Exception:
                pass
            if not retargeted:
                center = _frame_center(field) or _bounds_center(search_bounds)
                if center:
                    _activate_app(app)
                    _mouse_click(center[0], center[1])
            time.sleep(0.2)
            if field is not None:
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
                # Never append: clear first (live 202832 Pallavipo garble).
                cleared = _clear_focused_field_keys(app)
                attempt_notes.append(f"clear_before_cgevent={cleared}")
                _type_via_cgevent(text)
                time.sleep(0.35)
            if not _query_visible_in_search(app, text)[0]:
                # CGEvent can be swallowed when focus is wrong; System Events
                # keystrokes into the app process are a second injection path.
                se_ok = _type_via_system_events(app, text)
                attempt_notes.append(f"system_events={se_ok}")
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
