#!/usr/bin/env python3
"""Focus WhatsApp Search AXTextField and type Pallavi; dump coordinate types."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

OUT = Path(__file__).with_name("search_diag2.txt")


def main() -> None:
    lines: list[str] = []

    def log(m: str) -> None:
        print(m, flush=True)
        lines.append(m)

    from ApplicationServices import (
        AXUIElementPerformAction,
        AXUIElementSetAttributeValue,
        AXValueGetType,
        AXValueGetValue,
        kAXValueCGPointType,
        kAXValueCGSizeType,
    )
    from Quartz import CGPoint, CGSize
    from ctypes import byref

    from plugin.executor import ax_action as ax

    subprocess.run(["open", "-a", "WhatsApp"], capture_output=True)
    time.sleep(1.0)
    ax._activate_app("WhatsApp")
    time.sleep(0.3)
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "WhatsApp" to activate',
            "-e",
            "delay 0.3",
            "-e",
            'tell application "System Events" to keystroke "f" using command down',
        ],
        capture_output=True,
    )
    time.sleep(0.8)

    target = None
    for el, role, title, desc, placeholder in ax._walk(ax._app_root("WhatsApp")):
        if role == "AXTextField" and "search" in (placeholder or "").lower():
            target = el
            pos = ax._ax_attr(el, "AXPosition")
            size = ax._ax_attr(el, "AXSize")
            log(f"found textfield ph={placeholder!r} value={ax._ax_str(el, 'AXValue')!r}")
            log(f"pos type={type(pos)} repr={pos!r}")
            log(f"size type={type(size)} repr={size!r}")
            try:
                log(f"AXValueGetType(pos)={AXValueGetType(pos)}")
                log(f"AXValueGetType(size)={AXValueGetType(size)}")
            except Exception as e:
                log(f"gettype err {e}")
            try:
                pt = CGPoint()
                sz = CGSize()
                r1 = AXValueGetValue(pos, kAXValueCGPointType, byref(pt))
                r2 = AXValueGetValue(size, kAXValueCGSizeType, byref(sz))
                log(f"byref r1={r1} pt=({pt.x},{pt.y}) r2={r2} sz=({sz.width},{sz.height})")
            except Exception as e:
                log(f"byref fail {e}")
            break

    if target is None:
        log("NO_SEARCH_TEXTFIELD")
        OUT.write_text("\n".join(lines) + "\n")
        return

    try:
        AXUIElementSetAttributeValue(target, "AXFocused", True)
        log("set AXFocused")
    except Exception as e:
        log(f"focus fail {e}")
    try:
        AXUIElementPerformAction(target, "AXPress")
        log("AXPress")
    except Exception as e:
        log(f"press fail {e}")
    time.sleep(0.35)

    # Clear + type via System Events
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "WhatsApp" to activate',
            "-e",
            "delay 0.2",
            "-e",
            'tell application "System Events" to keystroke "a" using command down',
            "-e",
            "delay 0.05",
            "-e",
            'tell application "System Events" to key code 51',
            "-e",
            "delay 0.1",
            "-e",
            'tell application "System Events" to keystroke "Pallavi"',
        ],
        capture_output=True,
    )
    time.sleep(0.7)
    log(f"textfield value after type={ax._ax_str(target, 'AXValue')!r} focused={bool(ax._ax_attr(target, 'AXFocused'))}")

    for el, role, title, desc, placeholder in ax._walk(ax._app_root("WhatsApp")):
        v = ax._ax_str(el, "AXValue")
        t = title or ""
        blob = f"{t} {desc} {placeholder} {v}"
        if "Pallavi" in blob or (
            role in {"AXTextField", "AXSearchField"} and "search" in f"{placeholder} {desc}".lower()
        ):
            log(
                f"HIT {role} title={title!r} desc={desc!r} ph={placeholder!r} "
                f"value={v!r} focused={bool(ax._ax_attr(el, 'AXFocused'))}"
            )

    # Also try AXUIElementSetAttributeValue AXValue
    try:
        AXUIElementSetAttributeValue(target, "AXValue", "TESTSET")
        time.sleep(0.2)
        log(f"after AXValue set={ax._ax_str(target, 'AXValue')!r}")
    except Exception as e:
        log(f"AXValue set fail {e}")

    log("DONE")
    OUT.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
