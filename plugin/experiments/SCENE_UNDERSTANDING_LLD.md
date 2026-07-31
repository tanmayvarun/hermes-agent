# Scene-Understanding Perception LLD

**Date:** 2026-07-23  
**Phase:** Documentation + schema contracts only (no controller behavior change).  
**Companion:** [`ARCHITECTURE_ASSESSMENT.md`](ARCHITECTURE_ASSESSMENT.md) (current recognition stack).  
**Schemas:** [`plugin/worldmodel/scene/`](../worldmodel/scene/)

---

## 1. Problem statement

Plugin has treated perception as recognition:

```text
Screen → Accessibility tree → Entities → Decision
```

That assumes the accessibility tree already contains semantics. The live **Call now group** failure proves it does not.

After typing `Now` and opening `Now…`, the controller selected `semantic='Voice'` and executed a click on **Voice message** in the composer `(1684.5, 1016.5)` — not Voice Call in the call overlay. Same lexical family (“Voice” / microphone), opposite meaning.

Humans do not perceive a UI as a bag of buttons. They reconstruct layout:

```text
Conversation
├── Header (group, status, call actions)
├── Timeline
├── Composer (text, emoji, voice message)
└── Temporary Overlay (Voice Call, Video Call, Schedule)
```

Meaning is **region-conditioned**:

| Control | Region | Affordance |
|---------|--------|------------|
| Microphone / Voice | Composer | Record voice message |
| Microphone / Voice | Call overlay | Start / participate in call |

Identical AX labels in different regions must be allowed to diverge. Flat entity fusion cannot recover that.

**North star:** perception is a **scene understanding** pipeline. Its product is a hierarchical world graph — not “N fused entities.”

---

## 2. North-star pipeline

```text
Stage 1  Raw sensors
Stage 2  Entity fusion          (exists today)
Stage 3  Layout reconstruction  (NEW — regions)
Stage 4  Context graph          (NEW — contains / occludes / …)
Stage 5  Affordance reconstruction (region-conditioned)
Stage 6  Attention              (goal → relevant subgraph)
Stage 7  Affordance distribution (P(affordance | entity, region, goal))
Stage 8  Action risk estimator
Stage 9  Counterfactual simulator
         ↓
Controller-facing WorldGraph
```

The controller should never reason primarily over pixels or a flat entity list. It receives a `WorldGraph` with regions, membership, affordance distributions, risk, and calibrated uncertainty.

The observe→fuse→update shell remains [`plugin/agent/perception_cycle.py`](../agent/perception_cycle.py) (`refresh_perception` / `ensure_settled_perception`). Later stages plug in **after** world ingest; they do not replace the cycle.

---

## 3. Stage contracts

### Stage 1 — Raw sensors

| | |
|--|--|
| **Inputs** | OS / display / AX |
| **Outputs** | AX tree, MacAppTree, screenshot, OCR, vision embeddings, window metadata |
| **Uncertainty** | Source coverage / trust per sensor |
| **Non-goals** | Semantics, affordances, decisions |
| **Today** | [`plugin/perception/sources/`](../perception/sources/) (`pyobjc_ax`, `macapptree`, `screen2ax`) |

### Stage 2 — Fusion

| | |
|--|--|
| **Inputs** | Multi-source observations / hypotheses |
| **Outputs** | Fused entities with property-level beliefs (`FusedFrame` → projected `Observation` → `Entity`) |
| **Uncertainty** | Agreement, conflicts, `needs_reobserve`, worldview components |
| **Non-goals** | Layout regions, region-conditioned meaning |
| **Today** | [`plugin/perception/fusion/`](../perception/fusion/), [`WorldModel.ingest`](../worldmodel/model.py) |

Keep Stage 1–2. Flat entities remain an **internal** Stage 2 artifact.

### Stage 3 — Layout reconstruction (NEW)

| | |
|--|--|
| **Inputs** | Fused entities + bounds (+ screenshot when available) |
| **Outputs** | `SemanticRegion[]` — header, sidebar, conversation, timeline, composer, modal, toolbar, floating_menu, navigation, status_bar, unknown |
| **Uncertainty** | Per-region confidence; uncovered entity fraction |
| **Non-goals** | Affordance labels; goal attention |
| **Today** | Gap. Weak stand-ins: `layout_hash` / screen signature in [`screens/detect.py`](../worldmodel/screens/detect.py); entity `parent_id`/`child_ids`/`bounds` mostly unused for understanding |

This is semantic segmentation of the UI — regions, not buttons.

### Stage 4 — Context graph (NEW)

| | |
|--|--|
| **Inputs** | Regions + entities |
| **Outputs** | `ContextGraph` with edges `contains`, `occludes`, `adjacent`, `controls` |
| **Uncertainty** | Edge confidence; missing membership → unknown |
| **Non-goals** | Goal-specific attention |
| **Today** | AX parent/child kept on `Entity` but not promoted to a scene graph; screen-level [`NavigationGraph`](../worldmodel/graph/navigation.py) is between screens, not within-screen layout |

Example: `Composer —contains→ Microphone` vs `CallOverlay —contains→ Microphone`.

### Stage 5 — Affordance reconstruction

| | |
|--|--|
| **Inputs** | Context graph + region kinds + entity capabilities |
| **Outputs** | Region-conditioned capability hypotheses (messaging region → voice message; communication region → start call) |
| **Uncertainty** | Competing hypotheses when membership is weak |
| **Non-goals** | Final calibrated distributions (Stage 7); execution |
| **Today** | Label-pattern `_GOAL_AFFORDANCES` / `detect_goal_affordances` in [`transition/context.py`](../agent/transition/context.py) — **projection**, not scene understanding |

### Stage 6 — Attention

| | |
|--|--|
| **Inputs** | Goal + context graph + Stage 5 hypotheses |
| **Outputs** | `AttentionSubgraph` (region_ids + entity_ids) |
| **Uncertainty** | Attention mass / residual outside subgraph |
| **Non-goals** | Actuation |
| **Today** | Goal → feature flags → candidate enum over **all** matching labels ([`policy/candidates.py`](../agent/policy/candidates.py)) — no spatial / region attention |

For `Call now group`, attention should mass on Header / Call Overlay / communication controls; Composer should receive near-zero mass.

### Stage 7 — Semantic affordance network

| | |
|--|--|
| **Inputs** | Entity + region + context + goal |
| **Outputs** | `AffordanceDistribution` — e.g. Microphone∈Composer → P(record_voice_message)=0.97, P(start_voice_call)=0.01 |
| **Uncertainty** | Entropy of the distribution; high entropy = do not collapse to label-only |
| **Non-goals** | Risk / counterfactuals |
| **Today** | Discrete pattern hits, not distributions |

### Stage 8 — Action risk estimator

| | |
|--|--|
| **Inputs** | Affordance hypotheses |
| **Outputs** | `ActionRisk` — side_effect_class (`explore` / `reversible` / `external` / `irreversible`), risk ∈ [0,1], expected state delta summary |
| **Uncertainty** | Risk confidence |
| **Non-goals** | Full world simulation |
| **Today** | Trajectory-level `risk = max(0, -value_delta)` and `irreversible_risk_delta` — not scene-conditioned |

**Contract:** when affordance entropy is high, prefer low-risk explore over external side effects.

### Stage 9 — Counterfactual simulator

| | |
|--|--|
| **Inputs** | Candidate affordance + WorldGraph |
| **Outputs** | `CounterfactualRollout` — predicted state delta / whether goal predicates advance |
| **Uncertainty** | Prediction confidence |
| **Non-goals** | Replacing post-action TransitionMonitor |
| **Today** | Observe after act only; no simulate-before-act |

Stub type only in this phase.

---

## 4. Controller contract

Decision engines ([`decision.py`](../agent/decision.py), candidates, recovery) **may** eventually attend only to:

- `WorldGraph.attention` (or full graph when attention empty)
- `AffordanceDistribution` over attended entities
- `ActionRisk` for candidate affordances
- `SceneUnderstandingReport` uncertainty (layout confidence, coverage, affordance entropy)

They **must not** treat a flat `Entity` bag / raw AX labels as the primary semantic surface once Stages 3–7 are wired.

Until wiring exists, today’s path is unchanged: overlays → `StateFeatures` → candidates → scores. Flat entities remain the live decision substrate; this LLD defines the **target** contract only.

---

## 5. Current → target map

| Concern | Today (projection / stand-in) | Target |
|---------|-------------------------------|--------|
| Sensors | `perception/sources/*` | Stage 1 (keep) |
| Fusion | `perception/fusion/*`, `WorldModel.ingest` | Stage 2 (keep) |
| Observe shell | `perception_cycle.refresh_perception` | Keep; attach scene stages after ingest |
| Screen / mode | `ScreenDetector`, WA `LIST`/`CONVERSATION`/`CALLING` | Coarse; not layout regions |
| View projection | `WhatsAppWorldView`, `composer_visible`, etc. | Derived from regions later |
| Active surface | `InteractionContext.active_surface` | Bind to active region(s) |
| Goal affordances | Label regex `_GOAL_AFFORDANCES` | Stage 5–7 distributions |
| Spatial crumbs | `layout_hash`, entity `bounds`, `parent_id` | Inputs to Stage 3–4 |
| World product | Flat `Dict[id, Entity]` + patch | `WorldGraph` |

Approximate stand-ins above are **not** scene understanding. Improving them without a region graph will keep reproducing Voice / Voice message collisions.

---

## 6. Kill-gate (future Stage 3–5)

Once layout + context + affordance reconstruction exist:

1. Entity labeled Voice / Microphone with `region_kind=composer` → mass on `record_voice_message`.
2. Same label family with `region_kind=floating_menu` (call overlay) → mass on `start_voice_call` / `initiate_voice`.
3. Call goal attention must not select composer voice controls when a call overlay is present.
4. Schema already expresses this (see tests); reconstruction must populate it.

Live trace reference: `plugin/experiments/runs/terminal_now_group_20260723_135657_console.txt` — `Voice` → `Voice message` at composer coordinates.

---

## 7. Phasing

| Phase | Scope |
|-------|--------|
| **Stage 3+4 (geometry)** | `reconstruct_world_graph` — **app-agnostic** bands/clusters only (no product labels). Attached to `WorldPatch.scene_graph`. |
| **Stage 5–7 (generic)** | `affordances.enrich_world_graph` — region→capability priors + goal-kind→region attention; `attention_score_delta` biases DecisionEngine. Still no WhatsApp vocabulary in scene core. |
| **Next** | Stage 8–9 risk/counterfactual; optional app overlays may *annotate* but must not own region membership. |
| **Later** | ViT region segmentation, GNN relations, UI graph ⋈ knowledge graph. |

No ML is required for this document’s “done” criteria.

---

## 8. Invariants

1. **Absence of region membership ⇒ high-entropy / unknown affordance** — never collapse to label-only.
2. **Identical AX labels in different regions may diverge in meaning.**
3. **High affordance entropy ⇒ prefer low-risk explore** (Stage 8 contract; behavior later).
4. **Perception answers hierarchical questions**, not entity count: What regions exist? Who belongs where? What capabilities does each region provide? Which controls realize them? What is safe to explore? How uncertain is each interpretation?

---

## 9. Schema package (this phase)

Typed contracts (no reconstruction logic):

- `RegionKind`, `SemanticRegion`
- `SceneEdge`, `ContextGraph`
- `AffordanceHypothesis`, `AffordanceDistribution`
- `ActionRisk`, `AttentionSubgraph`
- `WorldGraph`, `SceneUnderstandingReport`
- `CounterfactualRollout` (Stage 9 stub)

Import: `from plugin.worldmodel.scene import WorldGraph, …`

**Not wired** into `controller.py`, `decision.py`, or `perception_cycle.py` in this phase.

---

## 10. Non-goals (this phase)

- Layout reconstruction algorithms (geometry clustering, ViT)
- Changing Voice candidate selection or live WhatsApp behavior
- WhatsApp-only Voice heuristics as a substitute for regions
- GNN / counterfactual simulator implementation
- Merging UI graph with long-term knowledge graph

---

## 11. Done criteria (this phase)

- [x] This LLD exists and maps stages ↔ current files
- [x] `plugin/worldmodel/scene/` schemas importable with dict round-trip
- [x] Contract test: same label under composer vs floating_menu → distinct affordance hypotheses
- [x] Controller / decision / candidates untouched; `pytest tests/plugin/` green
