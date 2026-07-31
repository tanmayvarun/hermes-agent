# Run log — `wa-forward-live-1785277037`

- JSONL: `plugin/experiments/runs/forward_zarooratwala_live_20260729_034717.jsonl`
- Events: 11

| seq | status | kind | detail |
|----:|:------:|------|--------|
| 1 | ok | whatsapp_forward_message | find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi |
| 2 | ok | step | checking Terminal Accessibility |
| 3 | ok | check | pass |
| 4 | ok | check | pass |
| 5 | fail | check | fail |
| 6 | ok | check | pass |
| 7 | ok | step | launched via open -a WhatsApp |
| 8 | ok | step | WhatsApp startup settle |
| 9 | ok | step | app=WhatsApp screenshot=True |
| 10 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 11 | fail | run_end | initial observe failed: strict perception required fused observation |

## Failures

- seq=5 `check`: {"ts": 1785277038.6482391, "seq": 5, "run_id": "wa-forward-live-1785277037", "kind": "check", "status": "fail", "name": "ghost_cli_installed", "expected": true, "actual": false, "message": "fail", "st
- seq=11 `run_end`: {"ts": 1785277124.9492989, "seq": 11, "run_id": "wa-forward-live-1785277037", "kind": "run_end", "status": "fail", "ok": false, "detail": "initial observe failed: strict perception required fused obse
