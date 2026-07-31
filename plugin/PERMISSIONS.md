# macOS permissions for Plugin

## Live requirement (now)

**Live WhatsApp control must be run from Terminal.app or iTerm — not from Cursor’s agent terminal.**

macOS attaches Accessibility to the **host app** of the process:

| You run from | Enable Accessibility for |
|--------------|--------------------------|
| **Terminal.app** / **iTerm** | Terminal / iTerm |
| Cursor agent / IDE terminal | Cursor (avoid for POC live runs) |
| Hermes Desktop later | Hermes.app |

### One-time setup

1. **System Settings → Privacy & Security → Accessibility** → enable **Terminal** (and/or **iTerm**)
2. Optional: **Screen Recording** → same app (only if using `--screenshot`)
3. Quit and reopen that terminal after granting

### Preferred launcher

Open the repo-owned `.command` wrapper so Launch Services, not Apple Events, gives Terminal ownership of the child process:

```bash
open /Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent/plugin/experiments/runs/run_now_group.command
```

### Live command (copy into Terminal.app)

```bash
cd /Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent
source .venv/bin/activate
export PYTHONPATH=.
python -m plugin permissions
python -m plugin call-pallavi --live --hangup --contact Pallavi
```

Logs: `plugin/experiments/runs/call_pallavi_live.jsonl`

`plugin call-pallavi --live` **refuses to continue** if the process is not Accessibility-trusted (AX error -25211 / empty tree).
If the host line says `Codex.app`, treat that as a launch failure and stop.

---

## Permission layers

| Capability | Permission | How Plugin does it |
|------------|------------|--------------------|
| Launch WhatsApp | **None** | `open -a "WhatsApp"` |
| Read UI hierarchy (AX) | **Accessibility** | macapptree / PyObjC AX → World Model |
| Click / type / scroll | **Accessibility** | Ghost OS or PyObjC AX Press |
| Screenshots | **Screen Recording** | optional (`--screenshot`) |
| AppleScript | **Automation** | **Not used** |

## What we avoid

No AppleScript. Stack stays:

```text
App → Accessibility tree → World Model → Planner → Accessibility actions
```
