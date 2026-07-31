# Run log — `wa-forward-live-1785490600`

- JSONL: `plugin/experiments/runs/forward_zarooratwala_live_20260731_150640.jsonl`
- Events: 4
- Final elapsed: `0.35s`

| seq | status | kind | detail |
|----:|:------:|------|--------|
| 1 | ok | whatsapp_forward_message | find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi |
| 2 | ok | step | checking Terminal Accessibility |
| 3 | fail | check | fail |
| 4 | fail | run_end | Accessibility not trusted for this host |

## Failures

- seq=3 `check`: {"ts": 1785490600.966423, "run_elapsed_s": 0.354522, "run_elapsed_ms": 355, "seq": 3, "run_id": "wa-forward-live-1785490600", "kind": "check", "status": "fail", "name": "accessibility_trusted", "expec
- seq=4 `run_end`: {"ts": 1785490600.966531, "run_elapsed_s": 0.354631, "run_elapsed_ms": 355, "seq": 4, "run_id": "wa-forward-live-1785490600", "kind": "run_end", "status": "fail", "ok": false, "detail": "Accessibility
