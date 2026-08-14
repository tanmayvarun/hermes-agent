#!/usr/bin/env python3
"""Submit ZarooratWala prompt into running Hermes desktop via CDP."""
from __future__ import annotations

import asyncio
import json
import urllib.request

import websockets

PROMPT = "Find the ZarooratWala link sent to Pallavi and forward it to Tanmay."


async def main() -> None:
    pages = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
    hermes = next(
        p
        for p in pages
        if p.get("title") == "Hermes" or "apps/desktop/dist/index.html" in p.get("url", "")
    )
    print("URL", hermes["url"])

    async with websockets.connect(hermes["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
        mid = 0

        async def call(method: str, params: dict | None = None) -> dict:
            nonlocal mid
            mid += 1
            i = mid
            await ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
            while True:
                data = json.loads(await ws.recv())
                if data.get("id") == i:
                    return data

        await call("Runtime.enable")
        find = await call(
            "Runtime.evaluate",
            {
                "returnByValue": True,
                "expression": """(() => {
          function walk(root, out=[]) {
            if (!root.querySelectorAll) return out;
            root.querySelectorAll('*').forEach(el => {
              if (el.shadowRoot) walk(el.shadowRoot, out);
              const role = el.getAttribute && el.getAttribute('role');
              if (el.tagName==='TEXTAREA' || el.tagName==='INPUT' || role==='textbox' || el.isContentEditable) {
                out.push({tag: el.tagName, role, testid: el.getAttribute('data-testid'), ph: el.getAttribute('placeholder'), aria: el.getAttribute('aria-label'), cls: String(el.className||'').slice(0,100)});
              }
            });
            return out;
          }
          const inputs = walk(document);
          let focused = null;
          for (const s of ['[data-testid="composer"]','textarea','[contenteditable="true"]','[role="textbox"]']) {
            const el = document.querySelector(s);
            if (el) { el.focus(); el.click(); focused = s; break; }
          }
          return {focused, inputs: inputs.slice(0,25), text:(document.body.innerText||'').slice(0,1200)};
        })()""",
            },
        )
        val = (((find.get("result") or {}).get("result") or {}).get("value"))
        print("FIND", json.dumps(val, indent=2)[:3500])

        typed = await call(
            "Runtime.evaluate",
            {
                "returnByValue": True,
                "expression": f"""(() => {{
          let el = document.activeElement;
          if (!el || (el === document.body)) {{
            el = document.querySelector('textarea, [contenteditable="true"], [role="textbox"]');
          }}
          if (!el) return {{ok:false}};
          el.focus();
          const text = {json.dumps(PROMPT)};
          if (el.isContentEditable) {{
            el.textContent = '';
            document.execCommand('insertText', false, text);
            el.dispatchEvent(new InputEvent('input', {{bubbles:true}}));
          }} else {{
            const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
            Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, text);
            el.dispatchEvent(new Event('input', {{bubbles:true}}));
          }}
          return {{ok:true, tag: el.tagName, preview: (el.value||el.innerText||'').slice(0,160)}};
        }})()""",
            },
        )
        print("TYPED", json.dumps((((typed.get("result") or {}).get("result") or {}).get("value"))))

        send = await call(
            "Runtime.evaluate",
            {
                "returnByValue": True,
                "expression": """(() => {
          const btns = [...document.querySelectorAll('button, [role="button"]')];
          const best = btns.find(b => /send/i.test((b.getAttribute('aria-label')||'') + (b.getAttribute('data-testid')||'') + (b.textContent||'')) && !b.disabled);
          if (best) { best.click(); return {clicked:true, label:(best.getAttribute('aria-label')||best.textContent||'').trim().slice(0,80)}; }
          return {clicked:false, sample: btns.slice(0,25).map(b => ((b.getAttribute('aria-label')||b.textContent||'').trim().slice(0,50)))};
        })()""",
            },
        )
        send_val = (((send.get("result") or {}).get("result") or {}).get("value"))
        print("SEND", json.dumps(send_val))
        if not (send_val or {}).get("clicked"):
            await call(
                "Input.dispatchKeyEvent",
                {
                    "type": "keyDown",
                    "key": "Enter",
                    "code": "Enter",
                    "windowsVirtualKeyCode": 13,
                    "nativeVirtualKeyCode": 13,
                },
            )
            await call(
                "Input.dispatchKeyEvent",
                {
                    "type": "keyUp",
                    "key": "Enter",
                    "code": "Enter",
                    "windowsVirtualKeyCode": 13,
                    "nativeVirtualKeyCode": 13,
                },
            )
            print("ENTER")

        await asyncio.sleep(4)
        body = await call(
            "Runtime.evaluate",
            {"returnByValue": True, "expression": "document.body.innerText.slice(0,2500)"},
        )
        print("BODY", (((body.get("result") or {}).get("result") or {}).get("value") or "")[:2500])


if __name__ == "__main__":
    asyncio.run(main())
