# Plugin World Model — concrete dependency stack

**Success criterion (Week 0 / Tech Validation):** zero unknown dependencies.
Every module has a chosen library or an explicit “build ourselves” decision.

| Module | Primary | Backup | Build ourselves? |
|--------|---------|--------|------------------|
| Accessibility extraction | **macapptree** | PyObjC + AXUIElement | No |
| Accessibility events | **AXObserver (PyObjC)** | Polling 500 ms | No |
| Screenshot capture | **macapptree** | ScreenCaptureKit / Quartz | No |
| Visual recovery | **Screen2AX** (when coverage &lt; 80%) | GPT Vision / VLM (research only) | No |
| Entity normalization | Plugin | — | **Yes** |
| Stable entity matching | Plugin + **numpy/scipy** (Hungarian) | Greedy similarity | **Yes** |
| Screen identification | Plugin | Graph embedding later | **Yes** |
| Transition graph | Plugin + **networkx** (viz) | Mermaid export | **Yes** |
| World model | Plugin | — | **Yes** |
| Action execution | **Ghost OS** (`ghost` CLI) | **PyAutoGUI** | Mostly no |
| Persistence | **SQLite** | JSON for debugging | No |
| Logging / CLI UI | **rich** (already in Hermes) | Text logs | No |

Install optional POC deps:

```bash
pip install -e '.[plugin-world]'
# Ghost OS (execution): brew install ghostwright/ghost-os/ghost-os && ghost setup
```

`plugin/worldmodel/` must never import LLM SDKs (enforced by tests).

## macOS permissions (POC floor)

| Capability | Permission |
|------------|------------|
| `plugin launch` (`open -a`) | None |
| AX read / Ghost click-type | **Accessibility** |
| Screenshots / Screen2AX | **Screen Recording** |
| AppleScript | **Not used** — see [PERMISSIONS.md](PERMISSIONS.md) |

Interaction stack (general GUI agent, not app-specific scripting):

```text
App → Accessibility tree → World Model → Planner → Accessibility actions
```
