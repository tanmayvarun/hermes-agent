# Run log — `wa-forward-live-1785224555`

- JSONL: `plugin/experiments/runs/forward_zarooratwala_live_20260728_131235.jsonl`
- Events: 8

| seq | status | kind | detail |
|----:|:------:|------|--------|
| 1 | ok | whatsapp_forward_message | find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi |
| 2 | ok | step | checking Terminal Accessibility |
| 3 | ok | check | pass |
| 4 | ok | check | pass |
| 5 | fail | check | fail |
| 6 | ok | check | pass |
| 7 | fail | step | _LSOpenURLsWithCompletionHandler() failed for the application /Applications/WhatsApp.app with error -600.; _LSOpenURLsWi |
| 8 | fail | run_end | failed to launch WhatsApp: _LSOpenURLsWithCompletionHandler() failed for the application /Applications/WhatsApp.app with |

## Failures

- seq=5 `check`: {"ts": 1785224555.748353, "seq": 5, "run_id": "wa-forward-live-1785224555", "kind": "check", "status": "fail", "name": "ghost_cli_installed", "expected": true, "actual": false, "message": "fail", "ste
- seq=7 `step`: {"ts": 1785224555.813719, "seq": 7, "run_id": "wa-forward-live-1785224555", "kind": "step", "status": "fail", "name": "launch_whatsapp", "message": "_LSOpenURLsWithCompletionHandler() failed for the a
- seq=8 `run_end`: {"ts": 1785224555.8139222, "seq": 8, "run_id": "wa-forward-live-1785224555", "kind": "run_end", "status": "fail", "ok": false, "detail": "failed to launch WhatsApp: _LSOpenURLsWithCompletionHandler() 
