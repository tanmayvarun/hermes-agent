# Plugin World Model POC

Risk-driven experiment: persistent macOS world model for multi-step GUI tasks.

**Stack (locked):** see [STACK.md](STACK.md) — macapptree, Ghost OS, scipy/numpy, SQLite, networkx.

**Permissions:** see [PERMISSIONS.md](PERMISSIONS.md).

**Live WhatsApp (required host):** run only from **Terminal.app or iTerm** with Accessibility enabled for that app — not from Cursor.
Preferred launch path:

```bash
open /Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent/plugin/experiments/runs/run_now_group.command
```

```bash
cd /Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent
source .venv/bin/activate
export PYTHONPATH=.
python -m plugin call-pallavi --live --hangup --contact Pallavi
```

## Quick start

```bash
cd hermes-agent
pip install -e '.[plugin-world]'   # macapptree, scipy, networkx, pyautogui
# Ghost (execution): brew install ghostwright/ghost-os/ghost-os && ghost setup

PYTHONPATH=. python -m plugin permissions
PYTHONPATH=. python -m plugin launch WhatsApp   # no special permission
# Then enable Accessibility (+ Screen Recording for shots) for Terminal.app
PYTHONPATH=. python -m plugin observe --app WhatsApp --no-screenshot

PYTHONPATH=. python -m plugin validate   # tech validation matrix
PYTHONPATH=. python -m plugin observe --fixture plugin/experiments/fixtures/whatsapp_conversation.json
PYTHONPATH=. python -m plugin inspect --fixture plugin/experiments/fixtures/whatsapp_chat.json
PYTHONPATH=. python -m plugin replay --fixtures
PYTHONPATH=. python -m plugin eval
PYTHONPATH=. python -m plugin model-benchmark --candidate-file path/to/candidates.json
PYTHONPATH=. python -m plugin call-pallavi
```

Entry point after editable install: `plugin observe` (console script).

## Hermes integration

Included in default **`hermes-cli`** (no `-t plugin_world` required):

```bash
# From Terminal.app / iTerm (Accessibility host) — not Cursor
source .venv/bin/activate
hermes chat
# then: Call Pallavi on WhatsApp
# agent should call plugin_call_whatsapp(contact="Pallavi", live=true, hangup=true)
```

Toggle via `hermes tools` → **Plugin World Model** if needed.

**Shared task contract:** UI prompt submit and Terminal live runs now both
derive the same structured `Goal`/procedure context before execution. That
keeps the desktop app, terminal runner, and world-model tools on one task
shape instead of letting the UI invent a separate interpretation.

**Shared progress clock:** live runs emit a run-relative clock from
`EventLogger` and the controller tracks both total elapsed time and elapsed
since last meaningful progress. The CLI/TUI/desktop surfaces should display
that telemetry as a view of the same work loop, not as a separate executor.

**Live control loop:** `run_call_pallavi_live` uses
`plugin.agent.controller.run_goal_closed_loop` — observe → patch →
DecisionEngine (one action) → execute → verify → repeat.

Project routing: `.hermes.md`. Live WhatsApp call flow: `skills/apple/whatsapp-call`.

Tools: `plugin_call_whatsapp`, `world_state`, `world_observe`, `world_plan`, `world_act`, `world_recover`.

Direct CLI (same live loop):

```bash
PYTHONPATH=. python -m plugin call-pallavi --live --hangup --contact Pallavi
```

## Hypothesis kill gate

If live WhatsApp entity retention &lt; 80% by Week 3, stop — delete this tree.
Offline fixture scorecard must stay green: `plugin eval`.
