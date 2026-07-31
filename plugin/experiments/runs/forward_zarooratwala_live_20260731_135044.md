# Run log — `wa-forward-live-1785486044`

- JSONL: `plugin/experiments/runs/forward_zarooratwala_live_20260731_135044.jsonl`
- Events: 4
- Final elapsed: `0.41s`

| seq | status | kind | detail |
|----:|:------:|------|--------|
| 1 | ok | whatsapp_forward_message | find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi |
| 2 | ok | step | checking Terminal Accessibility |
| 3 | fail | check | fail |
| 4 | fail | run_end | Accessibility not trusted for this host |

## Failures

- seq=3 `check`: {"ts": 1785486045.205927, "run_elapsed_s": 0.411758, "run_elapsed_ms": 412, "seq": 3, "run_id": "wa-forward-live-1785486044", "kind": "check", "status": "fail", "name": "accessibility_trusted", "expec
- seq=4 `run_end`: {"ts": 1785486045.208041, "run_elapsed_s": 0.413874, "run_elapsed_ms": 414, "seq": 4, "run_id": "wa-forward-live-1785486044", "kind": "run_end", "status": "fail", "ok": false, "detail": "Accessibility
