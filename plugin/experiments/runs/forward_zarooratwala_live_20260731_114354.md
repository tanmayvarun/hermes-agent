# Run log — `wa-forward-live-1785478434`

- JSONL: `plugin/experiments/runs/forward_zarooratwala_live_20260731_114354.jsonl`
- Events: 4

| seq | status | kind | detail |
|----:|:------:|------|--------|
| 1 | ok | whatsapp_forward_message | find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi |
| 2 | ok | step | checking Terminal Accessibility |
| 3 | fail | check | fail |
| 4 | fail | run_end | Accessibility not trusted for this host |

## Failures

- seq=3 `check`: {"ts": 1785478435.2306318, "seq": 3, "run_id": "wa-forward-live-1785478434", "kind": "check", "status": "fail", "name": "accessibility_trusted", "expected": true, "actual": false, "message": "fail", "
- seq=4 `run_end`: {"ts": 1785478435.2307358, "seq": 4, "run_id": "wa-forward-live-1785478434", "kind": "run_end", "status": "fail", "ok": false, "detail": "Accessibility not trusted for this host", "steps_ok": 2, "step
