#!/usr/bin/env python3
"""Fresh Hermes session on ollama-cloud model, submit ZarooratWala, report Stage A signals."""
from __future__ import annotations

import asyncio
import json
import time
import urllib.request
from pathlib import Path

import websockets
from AppKit import NSApplicationActivateIgnoringOtherApps, NSWorkspace
from plugin.executor.ax_action import _keydown, _mouse_click

import os
import sys

PROMPT = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.environ.get(
        "HERMES_PROBE_PROMPT",
        "Find the ZarooratWala link sent to Pallavi and forward it to Tanmay.",
    )
)
MODEL = "nemotron-3-ultra"
PROVIDER = "ollama-cloud"
AGENT_LOG = Path.home() / ".hermes/logs/agent.log"


def _activate_electron() -> int:
    import subprocess

    from AppKit import NSRunningApplication

    # Prefer pgrep — NSWorkspace path matching is brittle across Electron launches.
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", "Electron.app/Contents/MacOS/Electron apps/desktop"],
            text=True,
        ).strip()
        if out:
            pid = int(out.splitlines()[0])
            app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
            if app is not None:
                app.unhide()
                app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            return pid
    except Exception:
        pass
    for a in NSWorkspace.sharedWorkspace().runningApplications():
        path = str(a.executableURL().path() if a.executableURL() else "")
        name = str(a.localizedName() or "")
        if name in {"Hermes", "Plugin"} or (
            "Electron.app/Contents/MacOS/Electron" in path
            and ("hermes-agent" in path or "apps/desktop" in path)
        ):
            a.unhide()
            a.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            return int(a.processIdentifier())
    raise RuntimeError("Hermes Electron not running")


def _page() -> dict:
    pages = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=2))
    return next(
        p
        for p in pages
        if p.get("title") in {"Hermes", "Plugin"}
        or "apps/desktop/dist/index.html" in p.get("url", "")
    )


async def _cdp(ws, mid: list[int], method: str, params: dict | None = None) -> dict:
    mid[0] += 1
    i = mid[0]
    await ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
    while True:
        data = json.loads(await ws.recv())
        if data.get("id") == i:
            return data


async def prepare_and_submit() -> dict:
    hermes = _page()
    async with websockets.connect(hermes["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
        mid = [0]
        await _cdp(ws, mid, "Runtime.enable")

        # Pin ollama-cloud model in desktop composer prefs + start new session route.
        prep = await _cdp(
            ws,
            mid,
            "Runtime.evaluate",
            {
                "returnByValue": True,
                "expression": f"""(() => {{
          localStorage.setItem('hermes.desktop.composer.model', {json.dumps(MODEL)});
          localStorage.setItem('hermes.desktop.composer.provider', {json.dumps(PROVIDER)});
          localStorage.setItem('hermes.desktop.composer.model-source', 'manual');
          // Navigate to a brand-new ephemeral session id.
          const id = 'probe_' + Date.now().toString(36);
          location.hash = '#/' + id;
          return {{ id, model: localStorage.getItem('hermes.desktop.composer.model'),
                    provider: localStorage.getItem('hermes.desktop.composer.provider'),
                    href: location.href }};
        }})()""",
            },
        )
        prep_val = (((prep.get("result") or {}).get("result") or {}).get("value")) or {}
        print("prep", prep_val)
        await asyncio.sleep(2.5)

        # Observe composer + send
        obs = await _cdp(
            ws,
            mid,
            "Runtime.evaluate",
            {
                "returnByValue": True,
                "expression": """(() => {
          const el = document.querySelector('[data-slot="composer-rich-input"]')
            || document.querySelector('[role="textbox"][contenteditable="true"]');
          const pt = (node) => {
            if (!node) return null;
            const r = node.getBoundingClientRect();
            if (r.width < 2 || r.height < 2) return null;
            return {x: window.screenX + r.left + r.width/2, y: window.screenY + r.top + r.height/2, w:r.width, h:r.height};
          };
          const send = [...document.querySelectorAll('button')].find(b => /send/i.test((b.getAttribute('aria-label')||'')+(b.textContent||'')) && !b.disabled);
          // model pill text if present
          const pills = [...document.querySelectorAll('button')].map(b => (b.getAttribute('aria-label')||b.textContent||'').trim()).filter(Boolean).slice(0,40);
          return {composer: el ? {...pt(el), text:(el.innerText||'').slice(0,80)} : null,
                  send: send ? pt(send) : null, pills, href: location.href};
        })()""",
            },
        )
        obs_val = (((obs.get("result") or {}).get("result") or {}).get("value")) or {}
        print("observe", {k: obs_val.get(k) for k in ("composer", "send", "href")})
        print("pills_sample", (obs_val.get("pills") or [])[:15])

        comp = obs_val.get("composer")
        if not comp:
            raise RuntimeError("composer not found after new session nav")

        pid = _activate_electron()
        print("activated", pid)
        _mouse_click(float(comp["x"]), float(comp["y"]))
        time.sleep(0.25)
        _mouse_click(float(comp["x"]), float(comp["y"]))
        time.sleep(0.2)

        # paste prompt
        from AppKit import NSPasteboard, NSStringPboardType

        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(PROMPT, NSStringPboardType)
        _keydown(0, cmd=True)
        time.sleep(0.05)
        _keydown(51)
        time.sleep(0.05)
        _keydown(9, cmd=True)
        time.sleep(0.5)

        # force draft + submit
        forced = await _cdp(
            ws,
            mid,
            "Runtime.evaluate",
            {
                "returnByValue": True,
                "expression": """(() => {
          const el = document.querySelector('[data-slot="composer-rich-input"]')
            || document.querySelector('[role="textbox"][contenteditable="true"]');
          if (!el) return {ok:false};
          el.focus();
          el.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertFromPaste'}));
          const send = [...document.querySelectorAll('button')].find(b => /send/i.test((b.getAttribute('aria-label')||'')+(b.textContent||'')) && !b.disabled);
          if (send) { send.click(); return {ok:true, via:'send', editor:(el.innerText||'').slice(0,120)}; }
          el.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', bubbles:true, cancelable:true}));
          return {ok:true, via:'enter', editor:(el.innerText||'').slice(0,120)};
        })()""",
            },
        )
        print("submit", (((forced.get("result") or {}).get("result") or {}).get("value")))
        return prep_val


def monitor(seconds: int = 90) -> list[str]:
    start = AGENT_LOG.stat().st_size if AGENT_LOG.exists() else 0
    hits: list[str] = []
    deadline = time.time() + seconds
    keys = (
        "zaroorat",
        "turn_context",
        "agentruntime",
        "taskingress",
        "compose_domain",
        "computer_use",
        "native_computer",
        "acceptance",
        "nemotron-3-ultra",
        "ollama-cloud",
        "openrouter",
        "not found",
        "fallback",
        "methodfrontier",
        "selected_method",
        "whatsapp_gateway",
        "missing_precondition",
        "bridge_unavailable",
        "search_unsupported",
        "link a device",
        "waiting_for_user",
        "executor_fallback",
        "observe_begin",
        "maximum step",
    )
    while time.time() < deadline:
        data = AGENT_LOG.read_text(errors="replace")
        chunk = data[start:]
        start = len(data)
        for ln in chunk.splitlines():
            low = ln.lower()
            if any(k in low for k in keys):
                hits.append(ln)
                print("LOG", ln[:300], flush=True)
        time.sleep(2)
    return hits


async def ui_progress_poll(seconds: int = 180) -> dict:
    """Poll UI for Link-ASK / QR / running while agent.log is tailed elsewhere."""
    flags = {"ask": False, "qr": False, "running": False, "sid": ""}
    hermes = _page()
    async with websockets.connect(hermes["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
        mid = [0]
        await _cdp(ws, mid, "Runtime.enable")
        deadline = time.time() + seconds
        while time.time() < deadline:
            r = await _cdp(
                ws,
                mid,
                "Runtime.evaluate",
                {
                    "returnByValue": True,
                    "expression": """(() => {
                      const body=(document.body.innerText||'').replace(/\\s+/g,' ');
                      const qr=!!document.querySelector('[data-slot="whatsapp-link-qr"]');
                      const ask=/Link a device|Allow me to show a WhatsApp/i.test(body);
                      const running=/thinking|working|running|executing|step/i.test(body.slice(-900));
                      const sid=(location.href.match(/#\\/([^/?#]+)/)||[])[1]||'';
                      return {ask, qr, running, sid, snippet: body.slice(-500)};
                    })()""",
                },
            )
            val = (((r.get("result") or {}).get("result") or {}).get("value")) or {}
            flags["sid"] = val.get("sid") or flags["sid"]
            if val.get("ask"):
                flags["ask"] = True
            if val.get("qr"):
                flags["qr"] = True
            if val.get("running"):
                flags["running"] = True
            print(
                f"UI ask={val.get('ask')} qr={val.get('qr')} running={val.get('running')} "
                f"snip={(val.get('snippet') or '')[-180:]}",
                flush=True,
            )
            await asyncio.sleep(12)
    return flags


def main() -> int:
    _activate_electron()
    prep = asyncio.run(prepare_and_submit())
    print("monitoring...", flush=True)

    async def _run():
        ui_task = asyncio.create_task(ui_progress_poll(200))
        hits = await asyncio.to_thread(monitor, 200)
        flags = await ui_task
        return hits, flags

    hits, ui_flags = asyncio.run(_run())
    joined = "\n".join(hits).lower()
    print("\n=== SUMMARY ===")
    print("session_prep", prep)
    print("ui_flags", ui_flags)
    print("saw_zaroorat_turn", "zaroorat" in joined)
    print("saw_link_ask", ui_flags.get("ask") or "missing_precondition" in joined or "link a device" in joined)
    print("saw_qr", ui_flags.get("qr"))
    print("saw_gateway", "whatsapp_gateway" in joined)
    print("saw_bridge_unavailable", "bridge_unavailable" in joined)
    print("saw_search_unsupported", "search_unsupported" in joined)
    print("saw_executor_fallback", "executor_fallback" in joined or "fallback" in joined)
    print("saw_computer_use", "native_computer" in joined or "computer_use" in joined or "observe_begin" in joined)
    print("saw_max_steps", "maximum step" in joined)
    print(
        "saw_stage_a",
        any(k in joined for k in ("agentruntime", "taskingress", "compose_domain", "native_computer", "methodfrontier")),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
