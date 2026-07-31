#!/usr/bin/env python3
"""Diagnose WhatsApp Search open + type under Terminal Accessibility."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

OUT = Path(__file__).with_name("search_diag_out.txt")


def main() -> None:
    lines: list[str] = []

    def log(msg: str) -> None:
        print(msg, flush=True)
        lines.append(msg)

    from AppKit import NSScreen
    from ApplicationServices import AXUIElementCreateApplication
    from plugin.executor import ax_action as ax

    subprocess.run(["open", "-a", "WhatsApp"], capture_output=True)
    time.sleep(1.2)
    ax._activate_app("WhatsApp")
    pid = ax._pid_for_app("WhatsApp")
    log(f"pid={pid}")
    if pid is None:
        OUT.write_text("\n".join(lines))
        raise SystemExit(1)

    scale = float(NSScreen.mainScreen().backingScaleFactor())
    frame = NSScreen.mainScreen().frame()
    vis = NSScreen.mainScreen().visibleFrame()
    log(f"scale={scale} frame={frame} visible={vis}")

    root = AXUIElementCreateApplication(pid)
    rows = ax._walk(root)
    log(f"nodes={len(rows)}")

    for el, role, title, desc, placeholder in rows:
        blob = f"{title}|{desc}|{placeholder}".lower()
        if "search" in blob or role in {"AXTextField", "AXSearchField", "AXComboBox"}:
            pos = ax._unpack_point(ax._ax_attr(el, "AXPosition"))
            size = ax._unpack_size(ax._ax_attr(el, "AXSize"))
            center = ax._frame_center(el)
            focused = bool(ax._ax_attr(el, "AXFocused"))
            value = ax._ax_str(el, "AXValue")
            log(
                f"ROLE={role} title={title!r} desc={desc!r} ph={placeholder!r} "
                f"pos={pos} size={size} center={center} focused={focused} value={value!r}"
            )

    log("--- Cmd+F via System Events ---")
    ax._activate_app("WhatsApp")
    time.sleep(0.25)
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "WhatsApp" to activate',
            "-e",
            "delay 0.35",
            "-e",
            'tell application "System Events" to keystroke "f" using command down',
        ],
        capture_output=True,
    )
    time.sleep(0.9)
    rows2 = ax._walk(ax._app_root("WhatsApp"))
    log(f"nodes_after_cmd_f={len(rows2)}")
    for el, role, title, desc, placeholder in rows2:
        blob = f"{title} {desc} {placeholder}".lower()
        if role in {"AXTextField", "AXSearchField", "AXComboBox"} or "search" in blob:
            log(
                f"  {role} title={title!r} ph={placeholder!r} "
                f"value={ax._ax_str(el, 'AXValue')!r} focused={bool(ax._ax_attr(el, 'AXFocused'))} "
                f"center={ax._frame_center(el)}"
            )

    log("--- type Pallavi via System Events ---")
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "WhatsApp" to activate',
            "-e",
            "delay 0.25",
            "-e",
            'tell application "System Events" to keystroke "Pallavi"',
        ],
        capture_output=True,
    )
    time.sleep(0.7)
    field, lab = ax._find_search_text_field("WhatsApp")
    val = ax._ax_str(field, "AXValue") if field else None
    log(f"after_type label={lab!r} AXValue={val!r}")

    # Clear with Cmd+A Delete then try click variants
    log("--- click Search coordinate variants ---")
    # Escape search first
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "System Events" to key code 53',  # Escape
        ],
        capture_output=True,
    )
    time.sleep(0.4)

    el = ax._find_element("WhatsApp", "Search", prefer_roles=["AXStaticText", "AXButton"])
    c = ax._frame_center(el) if el else None
    log(f"search_el_center={c}")
    if c:
        screen_h = float(frame.size.height)
        variants = [
            ("native", c[0], c[1]),
            ("scale2", c[0] * scale, c[1] * scale),
            ("flip_y", c[0], screen_h - c[1]),
            ("flip_y_scale", c[0] * scale, (screen_h - c[1]) * scale),
        ]
        for name, x, y in variants:
            ax._activate_app("WhatsApp")
            time.sleep(0.15)
            ax._mouse_click(x, y)
            time.sleep(0.65)
            f2, l2 = ax._find_search_text_field("WhatsApp")
            v2 = ax._ax_str(f2, "AXValue") if f2 else None
            n = len(ax._walk(ax._app_root("WhatsApp")))
            log(f"  click_{name}=({x:.1f},{y:.1f}) field={l2!r} value={v2!r} nodes={n}")
            # escape back
            subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to key code 53'],
                capture_output=True,
            )
            time.sleep(0.25)

    log("DONE_DIAG")
    OUT.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
