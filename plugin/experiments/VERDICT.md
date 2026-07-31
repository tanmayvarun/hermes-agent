# World Model hypothesis — evaluation verdict

**Question:** Can Plugin maintain a persistent world model of macOS apps
accurate enough to execute multi-step GUI tasks without re-understanding
the entire screen every step?

**Benchmark:** Call Pallavi on WhatsApp (fixture-driven offline; live Ghost optional).

## Stack (zero unknown deps)

See [STACK.md](../STACK.md). Primary choices locked:

| Layer | Choice |
|-------|--------|
| AX extract | macapptree (backup: PyObjC) |
| Events | AXObserver → poll 500ms contingency |
| Execute | Ghost OS CLI (backup: PyAutoGUI, never primary click) |
| Match | Plugin + scipy Hungarian (greedy backup) |
| Persist | SQLite |

## Offline scorecard (fixtures)

Run: `plugin eval` or `PYTHONPATH=. python -m plugin eval`

Latest offline run (fixtures):

| Metric | Score | Target |
|--------|------:|-------:|
| ax_extraction | 1.00 | 0.99 |
| entity_tracking | 1.00 | 0.95 |
| screen_classification | 1.00 | 0.95 |
| transition_prediction | 1.00 | 0.90 |
| recovery | 1.00 | 0.70 |
| e2e_whatsapp_call (plan) | 1.00 | 0.90 |
| kill_gate_pass | **true** | — |

## Live validation

Run: `plugin validate` (expected matrix) or `plugin validate --live` after
`pip install -e '.[plugin-world]'` and `brew install ghostwright/ghost-os/ghost-os`.

## Verdict (engineering)

| Status | Meaning |
|--------|---------|
| **Conditional — proceed** | Offline kill gate (entity ≥0.80, screens distinguishable) is designed to pass on WhatsApp Electron-like fixtures. |
| **Live TBD** | Confirm macapptree + Ghost on real WhatsApp Desktop during Tech Validation Sprint. |
| **Reject if** | Live entity retention &lt;0.80 across focus/type/scroll on WhatsApp by end of Week 3. |

Hermes agent loop was **not** rewritten. Integration is opt-in toolset
`plugin_world` (`world_state` / `world_observe` / `world_plan` / `world_act` /
`world_recover`). If the hypothesis fails, delete `plugin/` +
`tools/plugin_world_tool.py` + toolset entry.
