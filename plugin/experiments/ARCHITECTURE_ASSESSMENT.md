# Plugin World Model — Architecture Assessment

**Date:** 2026-07-22  
**Scope:** Honest answers to the diagnostic questionnaire (A–I + the single most revealing question).  
**Rule:** Prefer code paths and logged evidence over aspirational STACK.md claims.

**Verdict in one line:** There is a real, LLM-free, in-memory WorldModel with identity patching. The **live** Call Pallavi path now uses a closed decision loop (`run_goal_closed_loop` + `DecisionEngine.decide` one action per observation). Fixture dry-run now also snapshots a single decision rather than walking a multi-step plan.

> Update (selector policy): live actuator choice is now model-selected from grounded candidates, and irreversible actions are blocked unless the selector confidence clears `agent.irreversible_action_confidence_threshold` (default `0.7`). The intent is to remove heuristic CTA ranking from the live path rather than tuning it.

> Update (closed-loop refactor): live `for step in plan.steps` was removed. See `plugin/agent/controller.py`, `plugin/agent/decision.py`, `plugin/agent/whatsapp_view.py`, `plugin/agent/predicates.py`. Tests: `tests/plugin/test_closed_loop.py`.

---

## Package map (what exists)

```
plugin/
  worldmodel/          # persistent-in-process WorldModel (no LLM imports)
    model.py           # WorldModel.ingest / summary / find_entity
    entities/          # Entity, normalize, IdentityTracker (Hungarian)
    screens/detect.py  # screen labels from entity signatures
    transitions/       # TransitionStore + predict()
    graph/navigation.py
    persistence/store.py  # SQLite helpers (implemented, rarely wired into live loop)
  perception/          # Observation from macapptree / PyObjC AX / fixtures
  executor/            # Ghost CLI → PyObjC AX fallback (ax_action.py)
  agent/
    decision.py        # DecisionEngine.decide → one next Action
    runtime/state.py   # RuntimeState(world_model, execution_state, …)
    runtime/recovery.py# recover_after_unexpected → ingest + decision snapshot
  experiments/
    call_pallavi.py    # LIVE orchestrator today (closed-loop observe/act/reobserve)
    harness.py         # offline scorecard
    logger.py          # JSONL EventLogger
  adapters/hermes/tools.py  # world_* + plugin_call_whatsapp tools
  cli.py               # observe | inspect | replay | eval | call-pallavi
```

---

# A. World Model

## 1. What exactly is the WorldModel?

**File:** `plugin/worldmodel/model.py`

```python
@dataclass
class WorldModel:
    active_app: str = ""
    current_screen: Optional[Screen] = None
    entities: Dict[int, Entity] = field(default_factory=dict)
    transitions: TransitionStore = field(default_factory=TransitionStore)
    navigation_graph: NavigationGraph = field(default_factory=NavigationGraph)
    tracker: IdentityTracker = field(default_factory=IdentityTracker)
    screens: ScreenDetector = field(default_factory=ScreenDetector)
    _prev_entities: List[Entity] = field(default_factory=list)
    _prev_screen_id: Optional[int] = None
```

**Entity** (`plugin/worldmodel/entities/entity.py`):

```python
@dataclass
class Entity:
    id: int
    entity_type: str          # button | textfield | list | static | …
    semantic_role: str
    actions: List[str]
    role: str                 # raw AX role
    label: str
    bounds: (x, y, w, h)
    parent_id: Optional[int]
    child_ids: List[int]
    visible: bool
    enabled: bool
    snapshot_count: int
    raw_ax_id: str
    attributes: Dict[str, Any]
```

**Runtime wrapper** (`plugin/agent/runtime/state.py`):

```python
@dataclass
class RuntimeState:
    world_model: WorldModel
    active_task: str
    execution_state: ExecutionState   # last_action, last_target_id, last_result, step
    conversation: List[Dict]
    patches: List[WorldPatch]
```

### Compared to the “good answer” checklist

| Desired field | Present? | Notes |
|---|---|---|
| `active_application` | Yes | `active_app` |
| `active_window` | Partial | On `Observation.window_name`, not a first-class WM field |
| `current_screen` | Yes | `Screen(id, label, signature)` |
| `entities` | Yes | Dict[int, Entity] |
| `focused_entity` | **No** | Not modeled |
| `navigation_graph` | Yes | |
| `pending_goal` | Partial | Lives on `RuntimeState.active_task`, not WorldModel |
| `execution_state` | Partial | On `RuntimeState`, not WorldModel |
| `SearchQuery` / `Results=[]` | **No** | No typed query field; search text inferred from entity labels / AX checks |

**This is not “screenshots + LLM.”** Perception builds an `Observation` of AX nodes; `WorldModel.ingest` patches entities. The world model module forbids LLM imports (`plugin/worldmodel/_no_llm.py` + tests).

---

## 2. Is the world model persistent?

**Yes within a process run — independent of the LLM prompt.**

- Lifetime: `RuntimeState.world_model` object in memory for the duration of `run_call_pallavi_live` / Hermes `plugin_world` session.
- Update API: `WorldModel.ingest(obs, action=…)` → `IdentityTracker.update` → replace `self.entities` with matched IDs → optional `TransitionStore.record`.
- **Not** reconstructed from pixels each step.
- **Cross-process / disk persistence:** `WorldStore` (SQLite) exists in `plugin/worldmodel/persistence/store.py` but is **not** hooked into the live Call Pallavi loop. Across restarts, the model starts empty.

Correct short answer:

```
Persistent object in memory for a run.
Observation patches it via ingest().
Not rebuilt from screenshots each step.
Not yet durable across process restarts in the live path.
```

---

## 3. World model before vs after typing “Pallavi”

There is **no** structured `SearchBox.focused` / `SearchQuery` / `Results` object.

What actually happens after Type:

1. `ax_type("WhatsApp", "Pallavi")` (executor)
2. Wait for UI settle
3. `_live_observe` → full AX tree
4. `runtime.world_model.ingest(obs, action="open_search")`
5. Heuristic checks: contact entity found? “Clear text”? query substring in labels?

**Conceptual diff (what we *wish* we logged vs what we log):**

```
Desired (not implemented as fields)
  SearchBox.focused=False → True
  SearchQuery="" → "Pallavi"
  Results=[] → [Pallavi, …]

Actual (implemented)
  WorldPatch.retention ≈ 0.76–0.99
  entities: new/changed labels appear (e.g. contact rows with "Pallavi")
  screen_label: often still mis-labeled "call" on live WhatsApp (screen detector weak)
  execution.message: typed 'Pallavi' … AXValue='Pallavi' evidence=…
  check search_bar_has_query: pass/fail
```

From a successful live JSONL (`call_pallavi_live.jsonl`):

| Step | Event | Evidence |
|------|--------|----------|
| 2 | execution | `typed 'Pallavi' … AXValue='Pallavi' evidence="AXTextField value='Pallavi'"` |
| 2 | observation | `nodes=269` |
| 2 | world_patch | `action=open_search retention≈0.764` |
| 2 | check | `search_bar_has_query` pass |

**Gap:** We patch the entity dict, but we do **not** expose a typed “query field” delta. Assessing “only changed fields” requires comparing `_entity_snapshot` before/after (logged sometimes) or replaying fixtures — not a first-class SearchQuery object.

---

## 4. What percentage of the world model changes after each action?

`WorldPatch` returns:

- `retention` = fraction of previous entities **identity-matched** (kept IDs)
- `matched_ids`, `new_entity_ids`

Live examples (same run):

| After action | Nodes observed | Retention | Interpretation |
|---|---|---|---|
| preclear hangup | 351 | ~0.996 | Almost all IDs retained |
| open Search (Cmd+F) | 351 | ~0.997 | Tiny change |
| type Pallavi | 269 | ~0.764 | ~24% of prior entities *not* retained / churn |
| open chat | 269 | ~0.764 | Similar churn |
| call | 352 | 1.0 then 0.764 | Polling oscillates tree size |

Offline harness (`run_identity_harness`) measures retention under focus/type/scroll jitter on fixtures — kill-gate expects ≥ 0.80.

**Honest read:** Identity tracking exists and retention is measured. Live WhatsApp Electron trees still churn hard (node count 269↔352), so “240 entities, 3 changed” is **not** what we see in production yet. High retention on quiet steps; large churn when the search/results subtree reshapes.

---

# B. Observation Loop

## 5. When is a new observation taken?

**Live Call Pallavi** (`run_call_pallavi_live`):

```
Observe (initial)
  → Plan once
  → for each plan step:
        Resolve entity from current WorldModel
        Execute action
        Wait (settle)
        Observe
        ingest(patch)
        (optional checks: search_bar / ringing)
```

So: **after every executed action** (plus initial, plus ringing poll), not on a timer, not only on failure.

**Wrong pattern we do *not* use for observation:** plan then five actions then one observe.  
**Wrong pattern we *do* use for planning:** plan once then multiple actions (see §D).

---

## 6. Is every action followed by verification?

**Mixed.**

| Action | Verification |
|--------|----------------|
| Type Pallavi | Yes — `search_bar_has_query` (contact / Clear text / label substring) + executor `AXValue`/evidence |
| Click Search | Weak — observe+patch only; no assert `SearchBox.focused=True` |
| Click Pallavi | Weak — observe+patch; no assert “chat with Pallavi open” |
| Click Call | Stronger — `_verify_ringing_poll` / `detect_call_ringing` (End call / calling patterns) |
| Executor `ok=True` | Means Ghost/AX API succeeded — **not** sufficient alone for Type (we added UI evidence) |

So we are **not** purely “API returned OK”; Type and Call have UI checks. Intermediate clicks are under-verified.

---

## 7. How do you detect action failure?

Mechanisms today:

1. Executor returns `ExecResult.ok=False` (e.g. type with empty AXValue / no evidence).
2. Explicit checks fail (`search_bar_has_query`, `call_is_ringing`).
3. Entity resolve fails (`no entity for …`) → abort click.
4. **Missing:** generic “expected world predicate vs observed patch” framework. No expected-state DSL.

Expected ideal:

```
Expected: Search focused
Observed: no change → Failure
```

Actual for Search click: often only “Cmd+F ran; retention high; continue plan.”

---

# C. Entity Tracking

## 8. Entity identity algorithm

**File:** `plugin/worldmodel/entities/identity.py`

Similarity (weighted):

| Signal | Weight |
|--------|--------|
| AX `role` exact | 0.30 |
| Label similarity (exact / substring / token Jaccard) | 0.30 |
| Bounds IoU | 0.25 |
| Parent ID match | 0.10 |
| Children-count proximity | 0.05 |

Assignment: **Hungarian** (`scipy.optimize.linear_sum_assignment`) with greedy fallback.  
Thresholds: `MATCH_THRESHOLD=0.55`, `ALIAS_THRESHOLD=0.40`.

Stable IDs live on `IdentityTracker._entities`; matched entities keep `id` and bump `snapshot_count`.

**Not** “node index in this frame.”

---

## 9. Can entity IDs survive scrolling?

**Designed to:** geometry IoU + label/role should keep IDs when bounds shift modestly. Harness shifts bbox by +12px and scores retention.

**Live WhatsApp reality:** large subtree replace on search/open-chat causes retention drops (~0.76). Scroll-specific chat-list survival is **not proven** in live logs. Treat as “algorithm present; WhatsApp stress still breaks retention often.”

---

# D. Planner

## 10. Does the decision engine output one action or an entire plan?

**Entire plan** (multi-step).

```python
Plan(
  goal="Call Pallavi",
  steps=[
    PlanStep(Click, Search),
    PlanStep(Type, Search, text="Pallavi"),
    PlanStep(Click, Pallavi),
    PlanStep(Click, Call),
  ],
)
```

The live runner uses a “one next action” loop, not an enumerated multi-step plan.

Desired robotics style: **one next action**.  
Current POC style: **DecisionEngine chooses one action per observation**.

---

## 11. Is the decision engine called after every observation?

**No (live).**

WhatsApp call invocations today:

```
N × observe+ingest
N × DecisionEngine.decide
N × execute(action)
N × re-observe
```

Fixture path with `--inject-fault` can call `recover_after_unexpected` → a fresh decision snapshot again once.

Hermes tools: `world_plan` / `world_recover` *can* replan if the outer agent calls them — but `plugin_call_whatsapp` / `run_call_pallavi_live` do not.

---

# E. Replanning

## 12. Unexpected popup (“Update Available”)

**Code exists:** `recover_after_unexpected` in `plugin/agent/runtime/recovery.py`:

```
observe → ingest(action="recover_observe") → DecisionEngine.decide → new Action snapshot
```

**Wired in live Call Pallavi?** **No.** Live loop never watches for popups or calls recover.  
**Wired in:** fixture harness + `world_recover` Hermes tool + `inject_fault` fixture branch.

So the correct architecture *module* exists; the live controller does **not** use it. Live behavior on popup: continue previous plan (wrong).

---

## 13. What if Pallavi isn’t found?

After Type:

- If `search_bar_has_query` fails → **abort** (break loop).
- If query landed but contact entity missing → `typed_ok` may still pass via label substring; Click Pallavi may then fail with `no entity` → abort.

There is **no** “No Results → new decision (try alternate spelling / open New Chat)” branch. Stop / fail, don’t replan.

---

# F. Transition Model

## 14. Are transitions stored?

**Yes, in memory** when `ingest(..., action=…)` sees screen id change:

```
TransitionStore.record(from_screen, to_screen, action, target_entity_id, diff)
NavigationGraph.sync_from_store(...)
```

Offline fixture replay builds Conversation → Search → Chat → Call edges.  
Live often mis-detects screen as `"call"` throughout, so **few meaningful transitions** get recorded even when UI actually changed.

SQLite persistence of transitions: API exists on `WorldStore`, not used by live runner.

---

## 15. Can Plugin predict the next screen?

**API:** `TransitionStore.predict(from_screen, action, target_entity_id?)`  
**Harness:** `run_transition_harness` checks predict consistency after fixture replay.

**Live Call Pallavi:** does **not** call `predict` before acting, does **not** compare prediction vs observation. Prediction is eval-only today.

---

# G. Closed Loop

## 16. What is the control loop?

### Implemented (observation after action — good)

```
Observe → World.ingest
     → Plan (ONCE)
     → Action
     → Wait
     → Observe → World.ingest
     → Action
     → …
```

### Desired closed loop (decision engine in the loop)

```
Observe → World Update → DecisionEngine → One Action → Execute → Observe → …
```

### Live Call Pallavi as code shape

```
execute_plan():
  observe(); ingest()
  action = DecisionEngine.decide(...)
  execute(action)
  wait()
  observe(); ingest()
  maybe_check(...)
```

This matches the questionnaire’s “root cause” sketch: the system can type Pallavi and patch the world, but the next decision must come from the updated world, not from a fixed precomputed plan.

---

## 17. Where is the feedback loop implemented?

| Concern | File | Role |
|---------|------|------|
| **Live orchestrator (actual controller)** | `plugin/experiments/call_pallavi.py` → `run_call_pallavi_live` | Closed-loop observe/decide/act/reobserve |
| World patch | `plugin/worldmodel/model.py` → `ingest` | |
| Identity | `plugin/worldmodel/entities/identity.py` | |
| Decision engine | `plugin/agent/decision.py` | One next action per observation |
| Recovery / replan | `plugin/agent/runtime/recovery.py` | Not on live happy path |
| Hermes tool façade | `plugin/adapters/hermes/tools.py` | Manual observe/decide/act/recover |

There is **no** single class named `ClosedLoopController`. The closest “one orchestrator” is `run_call_pallavi_live`, and it is open-loop w.r.t. planning.

---

# H. Logging

## 18. Logs for one execution

Logger: `plugin/experiments/logger.py` → JSONL + markdown summary.

Kinds emitted: `run_start`, `observation`, `world_patch`, `planner_decision`, `step`, `execution`, `check`, `world_summary`, `run_end`.

Example skeleton from a successful live run:

```
OBSERVE   nodes=269/351  source=pyobjc_ax
WORLD PATCH  screen=call  retention=0.99  (preclear)
PLANNER   steps=[Click Search, Type Pallavi, Click Pallavi, Click Call]   ← once
EXECUTOR  open Search via Cmd+F
OBSERVE + PATCH
EXECUTOR  typed 'Pallavi' AXValue='Pallavi'
OBSERVE + PATCH  retention≈0.76
CHECK     search_bar_has_query pass
EXECUTOR  click Pallavi
OBSERVE + PATCH
EXECUTOR  click Voice Call
OBSERVE + ringing poll
CHECK     call_is_ringing
EXECUTOR  hangup End Call
```

Artifacts:

- `plugin/experiments/runs/call_pallavi_live.jsonl`
- `plugin/experiments/runs/call_pallavi_live.md`
- Terminal consoles under `plugin/experiments/runs/terminal_live_*_console.txt`

**Gap vs ideal log:** no explicit “WORLD PATCH: Search focused=False→True” field-level diff; screen label often wrong (`call` while searching).

---

# I. Architecture modularity

## 19. Stop after every action / inspect world?

**Partial.**

- CLI: `plugin observe`, `plugin inspect` — inspect current (or fixture) world.
- No `--step` / interactive breakpoint in `call-pallavi --live`.
- Hermes: call `world_observe` / `world_state` / `world_act` one tool at a time if using `-t plugin_world` without `plugin_call_whatsapp`.

So: modular *enough* for manual stepping via Hermes tools; **not** a first-class “pause after each action” flag on the live benchmark.

---

## 20. Can I replay offline?

**Yes (fixture / log level).**

```bash
PYTHONPATH=. python -m plugin replay --fixtures
PYTHONPATH=. python -m plugin replay --log path/to.jsonl   # if harness supports
PYTHONPATH=. python -m plugin call-pallavi                 # fixture dry-run
PYTHONPATH=. python -m plugin eval                         # scorecard
```

Fixture sequence: conversation → search → chat → call JSON trees under `plugin/experiments/fixtures/`.

This is approaching “robotics-grade” **for offline identity/transition eval**. Live WhatsApp still needs the Accessibility host (Terminal).

---

# The most revealing question

> After typing "Pallavi", what exact code updates the WorldModel, and where is the next decision computed again based on that updated WorldModel?

### Actual call stack (live)

```
run_call_pallavi_live()
  …
  ax_type(app, "Pallavi", …)                    # executor — UI side effect
  _wait(... search results)
  obs = _live_observe(...)                      # perception — AX tree
  patch = runtime.world_model.ingest(           # ★ WorldModel update
              obs, action="open_search")
      entities_from_observation(obs)
      IdentityTracker.update(raw)               # stable IDs
      ScreenDetector.detect(...)
      [optional] TransitionStore.record(...)
  find_action_target(... contact ...)           # resolve from patched WM
  log.check(search_bar_has_query, …)
  continue   # ★ next observation → DecisionEngine.decide() here
```

### What is missing

```
patch_world_model()
    ↓
DecisionEngine.decide(world_model)   # ← called after each observation
    ↓
execute_action()
```

Instead:

```
execute_plan()
  step_1 Click Search
  step_2 Type Pallavi     # world patched here
  step_3 Click Pallavi    # still the precomputed step
  step_4 Click Call
```

**Conclusion:** WorldModel update after typing is real. Planner re-entry based on that update is **not**. That is the architectural gap behind “it typed Pallavi but didn’t truly close the loop.”

---

# Scorecard vs questionnaire ideals

| Area | Status | Confidence |
|------|--------|------------|
| Real WorldModel class (not VLM-only) | **Pass** | High |
| In-memory persistence + patch ingest | **Pass** | High |
| Typed SearchQuery / focused_entity fields | **Fail** | High |
| Observe after every action | **Pass** | High |
| Verify every action against expected UI | **Partial** | High |
| Identity algorithm (role/label/bounds/parent) | **Pass** | High |
| IDs survive hard WhatsApp churn / scroll | **Weak live** | Medium |
| Decision engine outputs one next action | **Pass** | High |
| Decision after every observation | **Pass** | High |
| Popup replan on live path | **Fail** (module only) | High |
| Transition store | **Pass** (memory) | High |
| Predict-before-act used live | **Fail** | High |
| Closed-loop controller | **Pass** | High |
| Structured logs | **Pass** (JSONL) | High |
| Offline fixture replay | **Pass** | High |
| SQLite durability in live loop | **Fail** (unused) | High |

---

# What to build next (if closing the loop is the goal)

1. **Keep** the closed-loop controller as the core live path:

   ```
   while not goal_done and steps < max:
     obs = observe(); wm.ingest(obs)
     action = decision_engine.decide(goal, wm, execution_state)
     if action is None: break
     execute(action); wait()
     obs2 = observe(); patch = wm.ingest(obs2, action=…)
     if not verify(action, patch, wm): recover_or_replan()
   ```

2. Keep expanding **expected predicates** per action (`search_focused`, `query==Pallavi`, `contact_visible`, `ringing`).
3. Keep promoting `SearchQuery` / `focused_entity_id` onto WorldModel overlays where needed.
4. Call `recover_after_unexpected` on live when retention collapses or unexpected semantics appear.
5. Optionally persist `WorldStore` between runs once identity is stable.

Treat Plugin as: **strong perception + world patch + closed-loop decisioning**, not a fixed-script GUI runner.

---

# Quick reference: key files for reviewers

| Question theme | Read first |
|----------------|------------|
| WorldModel fields | `plugin/worldmodel/model.py`, `entities/entity.py` |
| Patch / retention | `model.py::ingest`, `entities/identity.py` |
| Live loop | `plugin/experiments/call_pallavi.py::run_call_pallavi_live` |
| Decision engine | `plugin/agent/decision.py` |
| Replan | `plugin/agent/runtime/recovery.py` |
| Transitions | `plugin/worldmodel/transitions/transition.py` |
| Logs | `plugin/experiments/runs/call_pallavi_live.jsonl` |
| Hermes entry | `plugin/adapters/hermes/tools.py` (`plugin_call_whatsapp`) |
