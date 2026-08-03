# Layered perception, object permanence, and affordance discovery

**Status:** Proposed — one design covering two facets of the same idea: the
perceptor must represent the scene the way a human sees it (a **stack of
layers**, with objects that *persist* behind overlays), and `reveal_actions` is
the capability that **pushes/reads an overlay layer** and grounds the actions on
it. They are the same design because a revealed menu *is* a pushed layer.

Supersedes `docs/design/reveal-actions-affordance-discovery.md` (folded in
below).

---

## 1. One root cause behind two symptoms

Perception today is **flat**: a single `surface` drawn from a fixed enum, a
single `open_conversation`, and one `objects` list.

```json
// unified_cognition._SYSTEM_PROMPT (today)
"world_model": {
  "surface": enum,            // exactly one of the CANONICAL_SURFACES
  "open_conversation": str,
  "objects": [ ... ]
}
```

The prompt forces `surface must be exactly one of: chat_list, conversation,
search, context_menu, forward_picker, dialog, blank`. So the instant the Forward
menu opens over a conversation, the model reports `surface: context_menu` and
**drops** `open_conversation`. The base layer is erased from the representation.

Everything downstream then has to *reconstruct* what perception threw away, and
that shows up as two separate-looking bugs that are really one:

- **Symptom A — belief regresses under an overlay.** `transfer_task` recomputes
  `source_conversation_open = False` when the surface role flips to
  `action_menu`, regressing the phase to `OPEN_SOURCE` even though the
  conversation is plainly still open beneath the menu. My current fix makes the
  container/object beliefs *sticky under overlays* — i.e. it rebuilds object
  permanence in the **task layer** from prior state. Wrong layer, and it will
  not generalize.

- **Symptom B — revealed actions have no home.** `reveal_actions` opens the
  menu, but the executive is handed no grounded `Forward` control, so it clicks
  `center=None`. The revealed menu has no place in the representation to live.

Both are the flat model. A human perceives the menu *floating over a still-open
conversation* — two layers, base occluded, overlay active — and reads the menu's
items as new affordances on the object below. Perception must do the same, with
no app-specific rules. This is a matter of semantic understanding, not
hardcoding.

---

## 2. Layered perception

### 2.1 Schema: a shallow layer stack

Replace the flat `surface` with a **layer stack** scoped to the current *action
subscene* (not the whole window z-order):

```json
"layers": [
  { "role": "container", "name": "Pallavi", "state": "occluded",
    "objects": [ { "kind": "message", "text": "…zarooratwala…",
                   "point": [x, y], "matches_goal": true } ] },
  { "role": "action_menu", "name": "message actions", "state": "active",
    "objects": [ { "kind": "menu_item", "text": "Forward", "point": [x, y] },
                 { "kind": "menu_item", "text": "Reply",   "point": [x, y] } ] }
]
```

- Ordered bottom → top; the **top layer is `active`**, everything under an
  overlay is `occluded`.
- `objects` belong to the layer they live on: conversation messages on the
  container layer, menu items on the action_menu layer. This is what fixes
  Symptom B — the revealed `Forward` is an object *on the overlay layer*, with a
  point, directly invocable.

### 2.2 Roles are general, never app names

Every layer carries a **role** from a small general vocabulary — the same set
`transfer_task.surface_role` already collapses app vocabularies onto:

| role | meaning |
| --- | --- |
| `container` | the context that must be open to see the object (conversation, folder, document, watch page) |
| `list` / `search` | navigational surfaces on the way to the container |
| `action_menu` | menu exposing Forward/Share/Move on the object (context menu, share sheet) |
| `destination` | picker/sheet where the transfer target is chosen |
| `dialog` | modal confirm/alert |

A Slack forward menu, a Finder context menu, and a macOS share sheet are all
`action_menu` over some `container`. No `if app ==` anywhere.

### 2.3 Object permanence is a *perceptor* judgment

When an overlay is on top, the perceptor decides — from the pixels **and**
continuity with its own prior document — whether the base is:

- **still open beneath** (`state: occluded`, kept in the stack), or
- **actually replaced / dismissed** (dropped from the stack).

That is object permanence, and it belongs in perception because it is a
semantic reading of the scene, not a task rule. The perceptor already carries
its previous `world_model` forward verbatim, so it has exactly the evidence a
human uses: "the menu appeared *on top of* the chat I was just in; the chat did
not go anywhere."

**Consequence for the binder:** `transfer_task` becomes trivial and general —

```text
container_open   = any layer with role == container   (active OR occluded)
object_visible   = any object with matches_goal on the container layer
action_menu_open = any layer with role == action_menu
destination_open = any layer with role == destination
```

The sticky-belief code is **deleted**; permanence is sourced from perception, not
reconstructed from prior task state.

### 2.4 Human-readable rendering lists every layer

`render_scene_summary` today emits one flat sentence. It should enumerate the
stack so a developer can visually verify perception against the screenshot:

```
Scene (2 layers):
  L0 container "Pallavi" (occluded) — 6 messages; target link present
  L1 action_menu on the ZarooratWala message (active) — [Forward, Reply, Copy, Star, Delete]

Task context: forwarding "zarooratwala" from Pallavi → Tanmay; phase OPEN_FORWARD
```

Two rules:

1. **List all layers and overlays** in the action subscene, with role, name,
   `active`/`occluded`, and each layer's salient objects. Multiple overlays
   (menu over dialog over container) all appear.
2. The rendering **converts detailed input into a higher-level representation**
   of the current action subscene — it is the artifact a human reads to confirm
   perception is "as correct as possible."

### 2.5 Perception is scene truth; the executive owns task topology

The last line ("Task context: …") is an **annotation**, not part of the scene.
Perception describes *what is on screen* (the layer stack); the executive owns
*where we are in the plan* (container → object → action → destination → commit).
Folding task phase into perception would re-entangle the two. So:

- Perception emits `layers` (+ objects, beliefs, coverage) — world truth.
- The human-readable rendering is *annotated* with the executive's current
  objective/phase for context, so scene + intent are verifiable together.
- The schema's model-set `progress.phase` overlaps with the executive's phase
  today; collapse to **one authoritative phase (the executive's)** and let
  perception report only scene.

### 2.6 The critic validates layer push/pop, not surface jumps

`world_critic._surface_transition_ok` currently encodes flat-surface rules —
parents, openers, and special-cases like "refuse conversation→search during
locate/select" (the zarooratwala drift). Those special cases exist *only because
the flat model cannot express "a menu opened over the still-open chat."*

With layers, the critic reasons over **stack operations**, which is more
semantic and needs fewer special cases:

- **push overlay** (`action_menu` / `dialog` / `destination` appears on top):
  legal only after a reveal/opener action; the base layer must remain in the
  stack as `occluded`. A proposal that pushes an overlay *and* drops the base is
  rejected (that is the permanence violation).
- **pop overlay** (Escape / dismiss): legal; reveals the layer beneath.
- **swap base** (container → search with no overlay): the drift class — refuse
  during an in-container hunt exactly as today, but now expressible directly as
  "you replaced the base layer instead of pushing over it."

---

## 3. `reveal_actions` as affordance discovery (pushes/reads a layer)

(Folded in from the prior standalone doc; re-framed onto the layer model.)

### 3.1 What it should be

`reveal_actions` answers one question about an object: **"what can I do to this,
right now or after one probe, and how do I invoke each?"** It returns a
grounded **ActionSet** — visible *and* latent actions — and its result *is*
perception: it pushes/reads the overlay layer that carries those actions.

It is the sibling of content-object discovery (which answers "which object
matches the goal"); both are specializations of the umbrella ability
**perceive**. Perception is not UI-bound — a message bubble, a Finder file, a
YouTube video and a Slack message expose actions through different realizations
but one contract.

### 3.2 Relationship to the affordance frontier

The frontier (`docs/design/affordance-frontier.md`) is the *catalog* —
observed / latent / probe. `reveal_actions` is the *act of discovery*: it
consumes a `latent` entry (`Forward`, `available_after: context_click`, p=0.7),
performs the trigger, and turns it into an **observed, grounded** action —
i.e. it **pushes the `action_menu` layer** and grounds its items. It is the arm
that moves entries from latent to observed.

### 3.3 Contract

```text
reveal_actions(target, world, *, goal=None, probe_budget=1) -> RevealResult
```

`RevealResult`: `actions: list[Action]`, `surface_opened` (which overlay layer it
left active, `""` if restored), `method` (`read|hover|context_click|menu|keyboard`),
`escalated` (probe spent?), `coverage` (0..1), `evidence`.

`Action`: `label`, `invocation` (`direct|hover|context_click|menu_path|keyboard`),
`visibility` (`visible|latent`), `target` (`{point}` or `{entity_id}` — grounded),
`reversible`, `confidence`.

The grounded `target` is the crux (Symptom B): revealed controls are
materialized as addressable entities (the existing vision→entity path) and land
as objects on the pushed `action_menu` layer.

### 3.4 Realization: a strategy ladder, not an app switch

1. **read (no side effect).** Assemble visible actions from what perception has —
   AX supported-actions, the object inventory, the frontier's `observed_actions`.
   If the goal action is here, return it. Free.
2. **probe (state-mutating), budgeted.** If the goal action is latent, spend a
   probe via an evidence-ordered ladder of UI patterns: `hover` → `context_click`
   → click `more / ⋯` → app menu bar → `keyboard`. Order comes from the
   frontier's `expected_information_gain` and overlay hints
   (`reveal_mode`, `affordance_priors`), **never** `if app ==`.
3. **capture + ground.** Re-perceive the revealed layer, materialize its controls
   as entities, emit them as `observed` actions with points; report `coverage`
   and `missing_affordance_information` for anything seen but not grounded.

Per-app knowledge shrinks to declarative overlay hints (`reveal_mode`,
`affordance_priors(surface)`) — exactly the affordance-hint config the WhatsApp
de-specialization (Stage 3) is moving toward.

**Non-UI:** the same contract holds off-screen. A Finder file's ladder is
context-menu / File-menu / keyboard; a pure data surface returns inherent actions
(`open`, `move`, `delete`) at tier 1 with no probe. The executive sees one
uniform `RevealResult`.

### 3.5 Idempotence = state-aware, not side-effect-free

Probing mutates the UI, so `reveal_actions` is **active perception (a PROBE)**.
"Re-callable" means state-aware:

- Before gesturing, check the stack. If the `action_menu` layer for this target
  is already active, **skip the gesture and just read + ground** it. Two calls
  yield the same set, not two menus.
- The capability owns a **restore-or-hand-off** decision: by default leave the
  overlay layer active and report `surface_opened` so the executive can invoke
  immediately; if it abandons discovery it pops the layer (Escape). Either way
  the next reading is consistent — and, with §2, the base layer stays `occluded`
  throughout.

### 3.6 Who invokes it, and how often

- **Brain-gated (primary).** The executive spends `reveal_actions` when the goal
  needs an action that is not visible — the information-value decision it already
  makes for probes.
- **Perceptor-invoked (bounded).** For the *active* object the perceptor may run
  tier-1 `read` automatically, so every perception response already carries that
  object's visible actions. It does **not** auto-probe (tier 2).

So perception always includes visible affordances; latent-action discovery is a
budgeted probe the brain chooses. After either, the executive decides — act, or
probe again — and the loop continues.

### 3.7 How this dissolves the blocker

Object visible → executive sees `Forward` is latent behind `context_click` →
spends one `reveal_actions` probe → gets `Forward {invocation: menu_path,
target: {point}}` grounded on the pushed `action_menu` layer → invokes it →
`destination` layer opens. No `center=None`, and the container stays `occluded`
in the stack the whole time, so no phase regression. The hover-then-right-click
executor fix already landed is one *realization primitive* in tier 2's ladder,
not the capability itself.

---

## 4. Migration (additive, flagged)

1. **Add `layers`** to the schema/prompt/parser additively. Derive back-compat
   fields for existing readers: `surface = top-layer role → canonical name`,
   `open_conversation = base container layer name`. Nothing breaks day one.
2. **Perceptor emits permanence:** keep the base layer `occluded` under overlays;
   update `render_scene_summary` to the layered rendering (+ task annotation).
3. **Binder reads layers** (`transfer_task`): container/object/menu/destination
   from the stack. **Delete the sticky-belief patch** — keep it only as a clearly
   marked temporary bridge until layered perception is proven live.
4. **Critic → push/pop** (`world_critic`): validate stack operations; retire the
   flat surface-jump special cases as their layer equivalents land.
5. **Migrate remaining `surface` / `open_conversation` readers** to the stack,
   then remove the derived back-compat fields.
6. **`reveal_actions`** returns `RevealResult` and populates the overlay layer;
   frontier flips `latent → observed` with grounded targets.

Toggle each stage behind a flag; keep the current flat path parsing until the
layer contract is proven on the Zarooratwala forward.

---

## 5. Evaluation

**Layered perception (component):**

- **Layer decomposition:** given a screenshot with a menu over a conversation,
  perception emits ≥2 layers with correct roles and `occluded`/`active` states.
- **Object permanence:** across an overlay open→close, the container layer stays
  in the stack (occluded) and returns to `active`; no belief flip
  (extends `plugin/evals/temporal.py`).
- **Grounding:** overlay-layer objects (menu items) carry usable points.
- **Human-readable fidelity:** the rendering lists every layer + overlay present.

**`reveal_actions` (component):**

- **Recall of the goal action** across synthetic ActionSets (WhatsApp / Slack /
  Finder / YouTube): returns the goal action grounded, `read` when visible,
  probe only when latent.
- **Idempotence:** calling twice over an already-active overlay yields the same
  set and does not double-gesture.

**Closed-loop:**

- Zarooratwala forward advances `FIND_LINK → OPEN_FORWARD → PICK_DEST` with one
  probe at the menu step, container `occluded` throughout, no rollback loop and
  no phase regression.

---

## 6. Decisions & open questions

Decided:

- **Layer depth cap = ≤ 3** within the action subscene (container ← dialog ←
  menu). Keeps the packet small; deeper stacks are collapsed to the top 3.
- **`progress.phase` collapses into the executive's single authoritative phase.**
  Perception reports scene only; the human-readable rendering annotates it with
  the executive's phase.
- **Sequencing: layers first** (schema + permanence + critic + binder-reads-stack),
  then `reveal_actions`.

Decided (reveal_actions):

- **Hand-off, with a short TTL.** After a probe, `reveal_actions` leaves the
  revealed overlay layer active and reports `surface_opened`, so the executive
  can invoke an action immediately without a re-probe. The opened surface is
  marked with a TTL (a small number of frames); if nothing acts on it within the
  TTL it is dismissed so perception does not carry a stale overlay indefinitely.
- **Information-only probes cost less than committing actions.** A probe that
  only reveals affordances is charged a fraction of a step against the budget, so
  discovery is not penalised as if it were an irreversible move. Committing
  actions still cost a full step.
- **Perceptor auto-runs tier-1 (`read`) for the active object every frame;
  tier-2 (probing) stays brain-gated.** Every perception response already
  carries the active object's visible actions for free; latent-action discovery
  is a budgeted probe the executive chooses.

Still open:

- **Coverage honesty** — how aggressively to report
  `missing_affordance_information` for custom-drawn controls capture cannot
  ground.
