#!/usr/bin/env python3
"""Gateway+UI probe: Zaroorat ASK → yes → WhatsApp Link QR in ui_hints/DOM."""
from __future__ import annotations

import asyncio
import json
import time
import urllib.request

import websockets

PROMPT = "Find the ZarooratWala link sent to Pallavi and forward it to Tanmay."
MODEL = "mistral-large-3:675b"
PROVIDER = "ollama-cloud"


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


async def _eval(ws, mid: list[int], expression: str, *, await_promise: bool = False) -> dict:
    res = await _cdp(
        ws,
        mid,
        "Runtime.evaluate",
        {
            "returnByValue": True,
            "awaitPromise": await_promise,
            "expression": expression,
        },
    )
    return (((res.get("result") or {}).get("result") or {}).get("value")) or {}


async def _gateway_ws_url(cdp_ws, mid: list[int]) -> str:
    val = await _eval(
        cdp_ws,
        mid,
        "(async () => await window.hermesDesktop.getGatewayWsUrl())()",
        await_promise=True,
    )
    if isinstance(val, str) and val.startswith("ws"):
        return val
    raise RuntimeError(f"getGatewayWsUrl failed: {val!r}")


async def _rpc(gws, mid: list[int], method: str, params: dict, timeout: float = 60.0) -> dict:
    mid[0] += 1
    rid = mid[0]
    await gws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        raw = await asyncio.wait_for(gws.recv(), timeout=max(0.1, deadline - time.time()))
        data = json.loads(raw)
        if data.get("id") == rid:
            return data
    raise TimeoutError(f"rpc {method} timed out")


async def _wait_complete(gws, session_id: str, timeout: float = 180.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        raw = await asyncio.wait_for(gws.recv(), timeout=max(0.1, deadline - time.time()))
        data = json.loads(raw)
        if data.get("method") != "event":
            continue
        params = data.get("params") or {}
        if params.get("type") != "message.complete":
            continue
        if str(params.get("session_id") or "") not in {"", session_id}:
            # Some payloads nest session_id under payload
            payload = params.get("payload") or {}
            if str(payload.get("session_id") or "") not in {"", session_id} and params.get(
                "session_id"
            ) not in (None, session_id):
                continue
        payload = params.get("payload") or {}
        return {
            "text": str(payload.get("text") or "")[:500],
            "waiting_for_user": bool(payload.get("waiting_for_user")),
            "ui_hints": payload.get("ui_hints")
            if isinstance(payload.get("ui_hints"), dict)
            else {},
            "raw_keys": sorted(payload.keys()),
        }
    raise TimeoutError("message.complete timeout")


async def main() -> int:
    page = _page()
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=20_000_000) as cdp:
        mid = [0]
        await _cdp(cdp, mid, "Runtime.enable")
        ws_url = await _gateway_ws_url(cdp, mid)
        print("ws", ws_url.split("?")[0])

        gmid = [0]
        async with websockets.connect(ws_url, max_size=20_000_000) as gws:
            created = await _rpc(
                gws,
                gmid,
                "session.create",
                {
                    "cols": 100,
                    "source": "desktop",
                    "model": MODEL,
                    "provider": PROVIDER,
                },
            )
            if created.get("error"):
                print("FAIL session.create", created["error"])
                return 2
            result = created.get("result") or {}
            sid = str(result.get("session_id") or result.get("id") or "")
            stored = str(result.get("stored_session_id") or "")
            print("session", {"sid": sid, "stored": stored, "keys": sorted(result.keys())[:20]})
            if not sid:
                print("FAIL no session_id", created)
                return 2

            nav_id = stored or sid

            sub = await _rpc(
                gws,
                gmid,
                "prompt.submit",
                {"session_id": sid, "text": PROMPT},
                timeout=30,
            )
            if sub.get("error"):
                print("FAIL prompt.submit", sub["error"])
                return 3
            print("submitted prompt")

            first = await _wait_complete(gws, sid, timeout=180)
            hints = first.get("ui_hints") or {}
            print(
                "first_complete",
                {
                    "waiting": first.get("waiting_for_user"),
                    "kind": hints.get("kind"),
                    "has_qr": bool(hints.get("qr_payload")),
                    "status": hints.get("status"),
                    "text": (first.get("text") or "")[:220],
                },
            )
            if not first.get("waiting_for_user") and "whatsapp" not in (
                first.get("text") or ""
            ).lower():
                print("FAIL expected WhatsApp link ASK")
                return 4

            # Approve link
            yes = await _rpc(
                gws,
                gmid,
                "prompt.submit",
                {"session_id": sid, "text": "yes"},
                timeout=30,
            )
            if yes.get("error"):
                print("FAIL yes submit", yes["error"])
                return 5
            print("submitted yes")

            second = await _wait_complete(gws, sid, timeout=180)
            hints2 = second.get("ui_hints") or {}
            qr = str(hints2.get("qr_payload") or "").strip()
            print(
                "second_complete",
                {
                    "waiting": second.get("waiting_for_user"),
                    "kind": hints2.get("kind"),
                    "has_qr": bool(qr),
                    "qr_len": len(qr),
                    "status": hints2.get("status"),
                    "text": (second.get("text") or "")[:220],
                    "ui_hints_keys": sorted(hints2.keys()),
                },
            )

            # Open the session in UI (hash alone can race; also click sidebar).
            dom = await _eval(
                cdp,
                mid,
                f"""(async () => {{
              const id = {json.dumps(nav_id)};
              location.hash = '#/' + id;
              await new Promise(r => setTimeout(r, 700));
              const rows = [...document.querySelectorAll('button,a,[role="button"],[data-session-id]')];
              const hit = rows.find(el => (el.getAttribute('data-session-id')||'').includes(id)
                || /ZarooratWala|Forwarding Zaroorat/i.test(el.textContent||''));
              if (hit) hit.click();
              await new Promise(r => setTimeout(r, 1200));
              const qrEl = document.querySelector('[data-slot="whatsapp-link-qr"]');
              const img = qrEl && qrEl.querySelector('img');
              const body = (document.body?.innerText || '').replace(/\\s+/g,' ');
              return {{
                href: location.href,
                clicked: !!(hit && (hit.textContent||'').trim().slice(0,40)),
                qr: !!qrEl,
                img: !!(img && img.getAttribute('src')),
                nullLogger: /NullEventLogger/i.test(body),
                bodyHasScan: /Scan this QR/i.test(body),
                snippet: body.slice(0, 420)
              }};
            }})()""",
                await_promise=True,
            )
            print("dom", dom)

            ok_hints = bool(qr) and bool(second.get("waiting_for_user"))
            ok_dom = bool(dom.get("qr") and dom.get("img"))
            if ok_hints and ok_dom:
                print("OK WhatsApp QR available after approve", {"hints": ok_hints, "dom": ok_dom})
                return 0
            if ok_hints:
                print("OK QR in ui_hints (DOM missed nav)", {"hints": ok_hints, "dom": ok_dom})
                return 0

            if dom.get("nullLogger") or "NullEventLogger" in (second.get("text") or ""):
                print("FAIL NullEventLogger on continue path")
                return 6
            print("FAIL no QR after approve")
            return 7


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
