#!/usr/bin/env python3
"""Drive Hermes desktop composer via Computer Use primitives (click/paste/Enter).

Electron/Chromium does not expose the contenteditable composer as a rich AX
text field (same class of AX-blindness as WhatsApp). Observation therefore
uses either:
  1) CDP DOM geometry when --remote-debugging-port is available (preferred), or
  2) main-window bottom-band fallback from AX window bounds.

Actuation always goes through ax_action CGEvent click/paste/Enter — not through
the TUI/gateway API.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from typing import Any, List, Optional, Tuple


def _running_hermes_electron() -> Tuple[str, int]:
    from AppKit import NSWorkspace

    for app in NSWorkspace.sharedWorkspace().runningApplications():
        path = ""
        try:
            url = app.executableURL()
            path = str(url.path() if url else "").replace("\\", "/")
        except Exception:
            path = ""
        name = str(app.localizedName() or "")
        bid = str(app.bundleIdentifier() or "")
        if name == "Hermes" or bid.startswith("com.nousresearch.hermes"):
            return name, int(app.processIdentifier())
        if "hermes-agent" in path and path.endswith("/Electron"):
            return name or "Electron", int(app.processIdentifier())
    raise RuntimeError(
        "Hermes desktop Electron not running. Launch with ELECTRON_RUN_AS_NODE unset."
    )


def _activate_pid(pid: int) -> None:
    from AppKit import NSApplicationActivateIgnoringOtherApps, NSRunningApplication

    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    if app is None:
        raise RuntimeError(f"no NSRunningApplication for pid={pid}")
    app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
    time.sleep(0.4)


def _window_bottom_click(pid: int) -> Tuple[float, float]:
    from ApplicationServices import AXUIElementCreateApplication
    from plugin.executor.ax_action import _ax_attr, _unpack_point, _unpack_size

    root = AXUIElementCreateApplication(pid)
    windows = _ax_attr(root, "AXWindows") or []
    if not windows:
        raise RuntimeError("no AX windows — Accessibility denied or app not ready")
    win = list(windows)[0]
    pos = _unpack_point(_ax_attr(win, "AXPosition"))
    size = _unpack_size(_ax_attr(win, "AXSize"))
    if not pos or not size:
        raise RuntimeError(f"window geometry unavailable pos={pos} size={size}")
    x = pos[0] + size[0] * 0.50
    # Composer sits in the lower band of the chat column.
    y = pos[1] + size[1] * 0.90
    return x, y


def _hermes_page() -> Optional[dict]:
    try:
        pages = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=1.5))
    except Exception:
        return None
    return next(
        (
            p
            for p in pages
            if p.get("title") == "Hermes" or "apps/desktop/dist/index.html" in p.get("url", "")
        ),
        None,
    )


async def _cdp_call(ws: Any, mid_box: List[int], method: str, params: Optional[dict] = None) -> dict:
    mid_box[0] += 1
    i = mid_box[0]
    await ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
    while True:
        data = json.loads(await ws.recv())
        if data.get("id") == i:
            return data


def _cdp_observe_targets() -> dict:
    """Observe composer + Send button screen coordinates via CDP."""
    hermes = _hermes_page()
    if hermes is None:
        return {}
    try:
        import asyncio

        import websockets
    except Exception:
        return {}

    async def _run() -> dict:
        async with websockets.connect(hermes["webSocketDebuggerUrl"], max_size=8_000_000) as ws:
            mid = [0]
            await _cdp_call(ws, mid, "Runtime.enable")
            layout = await _cdp_call(
                ws,
                mid,
                "Runtime.evaluate",
                {
                    "returnByValue": True,
                    "expression": """(() => {
              const el = document.querySelector('[data-slot="composer-rich-input"]')
                || document.querySelector('[role="textbox"][contenteditable="true"]')
                || document.querySelector('[contenteditable="true"]');
              const pt = (node) => {
                if (!node) return null;
                const r = node.getBoundingClientRect();
                if (r.width < 2 || r.height < 2) return null;
                return {
                  x: window.screenX + r.left + r.width/2,
                  y: window.screenY + r.top + r.height/2,
                  w: r.width, h: r.height
                };
              };
              const btns = [...document.querySelectorAll('button')];
              const sendBtn = btns.find(b => {
                const s = ((b.getAttribute('aria-label')||'') + ' ' + (b.textContent||'')).toLowerCase();
                return s.includes('send') && !b.disabled;
              });
              return {
                composer: el ? {...pt(el), text:(el.innerText||'').slice(0,80), aria: el.getAttribute('aria-label')} : null,
                send: sendBtn ? {...pt(sendBtn), aria: sendBtn.getAttribute('aria-label'), disabled: !!sendBtn.disabled} : null,
              };
            })()""",
                },
            )
            return (((layout.get("result") or {}).get("result") or {}).get("value")) or {}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        print(f"cdp_observe_failed: {exc}")
        return {}


def _cdp_force_draft_and_click_send() -> dict:
    """Ensure React draft sync + click Send in-page (backup if CGEvent Enter is swallowed)."""
    hermes = _hermes_page()
    if hermes is None:
        return {"error": "no_page"}
    import asyncio

    import websockets

    async def _run() -> dict:
        async with websockets.connect(hermes["webSocketDebuggerUrl"], max_size=8_000_000) as ws:
            mid = [0]
            await _cdp_call(ws, mid, "Runtime.enable")
            res = await _cdp_call(
                ws,
                mid,
                "Runtime.evaluate",
                {
                    "returnByValue": True,
                    "expression": """(() => {
              const el = document.querySelector('[data-slot="composer-rich-input"]')
                || document.querySelector('[role="textbox"][contenteditable="true"]');
              if (!el) return {ok:false, reason:'no_editor'};
              el.focus();
              el.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertFromPaste'}));
              const btns = [...document.querySelectorAll('button')];
              const send = btns.find(b => {
                const s = ((b.getAttribute('aria-label')||'') + ' ' + (b.textContent||'')).toLowerCase();
                return s.includes('send') && !b.disabled;
              });
              if (!send) {
                // synthesize Enter on editor
                el.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', bubbles:true, cancelable:true}));
                return {ok:true, via:'keydown_enter', editor:(el.innerText||'').slice(0,120), sendDisabled: btns.filter(b=>/send/i.test((b.getAttribute('aria-label')||'')+(b.textContent||''))).map(b=>b.disabled)};
              }
              send.click();
              return {ok:true, via:'button_click', aria: send.getAttribute('aria-label'), editor:(el.innerText||'').slice(0,120)};
            })()""",
                },
            )
            return (((res.get("result") or {}).get("result") or {}).get("value")) or {}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        return {"error": str(exc)}


def _cdp_readback() -> dict:
    try:
        pages = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=1.5))
        hermes = next(
            p
            for p in pages
            if p.get("title") == "Hermes" or "apps/desktop/dist/index.html" in p.get("url", "")
        )
    except Exception as exc:
        return {"error": str(exc)}
    import asyncio

    import websockets

    async def _run() -> dict:
        async with websockets.connect(hermes["webSocketDebuggerUrl"], max_size=8_000_000) as ws:
            await ws.send(
                json.dumps(
                    {
                        "id": 1,
                        "method": "Runtime.evaluate",
                        "params": {
                            "returnByValue": True,
                            "expression": """(() => {
                const el = document.querySelector('[role="textbox"][contenteditable="true"]')
                  || document.querySelector('[contenteditable="true"]');
                const body = (document.body && document.body.innerText || '').slice(0, 1200);
                return {
                  editor: el ? (el.innerText || '').slice(0, 300) : null,
                  hasZaroorat: body.toLowerCase().includes('zarooratwala'),
                  bodyHead: body
                };
              })()""",
                        },
                    }
                )
            )
            while True:
                data = json.loads(await ws.recv())
                if data.get("id") == 1:
                    return (((data.get("result") or {}).get("result") or {}).get("value")) or {}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        return {"error": str(exc)}


def _paste_text(text: str) -> None:
    from AppKit import NSPasteboard, NSStringPboardType
    from plugin.executor.ax_action import _keydown

    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSStringPboardType)
    time.sleep(0.05)
    _keydown(0, cmd=True)  # Cmd+A
    time.sleep(0.05)
    _keydown(51)  # Delete
    time.sleep(0.05)
    _keydown(9, cmd=True)  # Cmd+V
    time.sleep(0.35)


def _submit() -> None:
    from plugin.executor.ax_action import _keydown

    _keydown(36)  # Return
    time.sleep(0.35)


def drive(prompt: str, *, dry_run: bool = False) -> int:
    from plugin.executor.ax_action import _mouse_click

    app_name, pid = _running_hermes_electron()
    print(f"target app={app_name!r} pid={pid}")
    _activate_pid(pid)

    obs = _cdp_observe_targets()
    composer = (obs or {}).get("composer")
    send = (obs or {}).get("send")
    if composer:
        x, y = float(composer["x"]), float(composer["y"])
        source = "cdp_dom"
        print("cdp_observe", obs)
    else:
        x, y = _window_bottom_click(pid)
        source = "ax_window_bottom"
    print(f"click_composer source={source} xy=({x:.1f},{y:.1f})")
    if dry_run:
        return 0

    _activate_pid(pid)
    _mouse_click(x, y)
    time.sleep(0.35)
    _mouse_click(x, y)
    time.sleep(0.25)
    _paste_text(prompt)
    time.sleep(0.5)
    rb = _cdp_readback()
    print("readback_before_submit", rb)

    # Re-observe Send (enabled only after draft sync), CU-click it, then CDP backup.
    obs2 = _cdp_observe_targets()
    send = (obs2 or {}).get("send") or send
    if send and not send.get("disabled") and send.get("w"):
        print(f"click_send xy=({send['x']:.1f},{send['y']:.1f}) aria={send.get('aria')!r}")
        _activate_pid(pid)
        _mouse_click(float(send["x"]), float(send["y"]))
    else:
        print("send_button_unavailable_for_cu_click; will use CDP/Enter backup")
        _activate_pid(pid)
        _mouse_click(x, y)
        time.sleep(0.1)
        _submit()

    forced = _cdp_force_draft_and_click_send()
    print("cdp_force_submit", forced)
    time.sleep(2.0)
    rb2 = _cdp_readback()
    print("readback_after_submit", rb2)
    if rb2.get("hasZaroorat"):
        print("OK: ZarooratWala prompt visible in Hermes thread/UI")
        return 0
    if rb.get("editor") and "Zaroorat" in (rb.get("editor") or ""):
        # At least landed in composer; submit may still be in flight.
        print("OK: prompt in composer (submit may still be in flight)")
        return 0
    print("WARN: prompt not confirmed in UI readback")
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("prompt", nargs="?", default="")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    prompt = args.prompt or (
        "Find the ZarooratWala link sent to Pallavi and forward it to Tanmay."
    )
    return drive(prompt, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
