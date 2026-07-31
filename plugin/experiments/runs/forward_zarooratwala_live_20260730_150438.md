# Run log — `wa-forward-live-1785404078`

- JSONL: `plugin/experiments/runs/forward_zarooratwala_live_20260730_150438.jsonl`
- Events: 4

| seq | status | kind | detail |
|----:|:------:|------|--------|
| 1 | ok | whatsapp_forward_message | find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi |
| 2 | ok | step | checking Terminal Accessibility |
| 3 | fail | check | fail |
| 4 | fail | run_end | Accessibility not trusted for this host |

## Failures

- seq=3 `check`: {"ts": 1785404078.866175, "seq": 3, "run_id": "wa-forward-live-1785404078", "kind": "check", "status": "fail", "name": "accessibility_trusted", "expected": true, "actual": false, "message": "fail", "s
- seq=4 `run_end`: {"ts": 1785404078.866285, "seq": 4, "run_id": "wa-forward-live-1785404078", "kind": "run_end", "status": "fail", "ok": false, "detail": "Accessibility not trusted for this host", "steps_ok": 2, "steps
