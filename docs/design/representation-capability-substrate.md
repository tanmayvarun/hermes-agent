# Representation + Capability Substrate

**Status:** Active design — first capability (`locate_content`) implemented; siblings contracted.

## The pattern

Transformers are strong at **representations** and general computation over them.
They are a poor place to rediscover host-specific motor procedures every step.

```text
sensors (pixels, AX, OCR, last result)
        ↓
perceptor / multimodal model
        ↓
typed representation of the active surface
        ↓
general capability (search, open, reveal, …)
        ↓
evidence back into the world document
```

Perception and capability are complementary:

| Piece | Job |
| --- | --- |
| Perception | Arrive at / update the representation (what surface, what is addressable, what changed). |
| Capability | Execute a general operation *on* that representation. |
| Agent loop | Choose which capability, with what arguments, and whether the outcome is the right object or branch. |

Inventing “Cmd+F then type then scroll” from `click` / `scroll` / `type` every time
burns model calls rediscovering a capability that should already be named.

## Hard rules

1. **Affordances, not plans.** A capability widens the action space. It does not
   encode an app-specific multi-step procedure (e.g. “right-click → Forward →
   pick → Send”).
2. **Judgment stays with the model.** What to search for, whether to search,
   which match is *the* one, when a branch is exhausted — never invented by the
   runtime.
3. **Mechanism stays with the runtime.** Chords, coordinate scale, iteration
   while the answer is mechanical, irreversible gates.
4. **One model call per decision, not per mechanical step.** Loops with no
   judgment (scroll-and-look) run inside the capability.
5. **Composites must be reversible.** Bundling steps hides them from the
   irreversible gate. Send / delete / confirm stay primitives.
6. **Apps declare realizations; they do not fork core.** A new host binds by
   declaring chords / adapters. An undeclared host still gets universal
   fallbacks where they exist. An orthogonal need adds a realization, not a
   parallel capability tree.

## Representation substrates

Capabilities do not take raw screenshots. They take a thin, typed projection
that perception (or the world document) has already made:

| Substrate | Meaning | Produced by |
| --- | --- | --- |
| `searchable_surface` | Current scrollable / findable body of content | Perceptor + overlay find declaration |
| `addressable_entity` | A named, targetable object (row, message, contact) | Perceptor objects / AX / content discovery |
| `candidate_set` | Visible rows to disambiguate against a goal referent | Perceptor objects + feature extras |
| `affordance_set` | Actions available on a bound entity | Perceptor + overlay hints |
| `transient_chrome` | Overlay / menu / dialog that is not the task | Perceptor surface label |

These are not a second world model. They are views of the model-owned world
document plus host declarations, shaped for capability execution.

## Three layers of vocabulary

1. **Meta-actions** — kind of executive step (`think` / `perceive` / `search` /
   `act` / …). Chosen by meta consultation.
2. **General capabilities** — catalog verbs over substrates (this section).
3. **Motor primitives** — `click` / `type` / `scroll` / …

**`MetaAction.SEARCH` owns find-among-many.** It interrogates a
`candidate_set` against a referent/criteria (query → retrieve/filter → rank)
until `SearchResult.chosen` (or fail). Stage capabilities run under SEARCH;
`MetaAction.ACT` commits (`open_entity` / `select_content` / …) only when the
target is known. This is distinct from `INFORMATION_GATHERING` (strategic
replan over action-space branches — not UI query authorship).

The runtime tracks `search_episode`
(`querying` → `retrieving` → `ranking` → `complete` | `failed`). Incomplete
episodes rewrite meta ACT→SEARCH and forbid commit verbs under SEARCH.

## General capability catalog

Capabilities compose the agent under the active meta. Find stages are realized
under SEARCH; commit verbs under ACT.

| Capability | Substrate | Contract | Status |
| --- | --- | --- | --- |
| `search` | `candidate_set` | Legacy name — executive owns `MetaAction.SEARCH`; not an ACT verb. | contract |
| `compose_search_query` | `task_evidence` | **SEARCH stage:** author a search-box string from goal evidence. Does not complete search. | **realized** |
| `resolve_entity` | `candidate_set` | **SEARCH stage (rank):** choose which visible candidate matches a referent. | **realized** |
| `locate_content` | `searchable_surface` | Make content matching `query` reachable, or report exhaustion. Never claims relevance. | **realized** (native find + scroll scan) |
| `open_entity` | `addressable_entity` | Navigate into the named entity. **ACT commit** after search completes — not a substitute for ranking. | **realized** (resolve + click) |
| `select_content` | `addressable_entity` | Focus a content object inside an open surface without navigating away. | **realized** (resolve + click) |
| `reveal_actions` | `addressable_entity` | Expose the affordance set for an entity without committing. | **realized** (context-click / hover) |
| `invoke_affordance` | `affordance_set` | Activate a *named reversible* affordance. Refuses Send/Delete. | **realized** (named click) |
| `dismiss_transient` | `transient_chrome` | Clear an overlay that is not the task. | **realized** (dismiss chord / Escape) |
| `revert_effects` | `effect_trace` | Cross-task rollback: analyze forward leg + world → approve `RevertPlan` → execute realizations. Same verb for selection undo, undoing a send (via Delete), undoing a file copy/edit. | **realized** (Escape-class); contracted Delete/trash/Undo |
| `commit_irreversible` | gated target | Send / delete / confirm. Always a gated primitive; never bundled. | **realized** (allowlisted gated click) |

### `revert_effects` is overloaded across tasks

**Graph nomenclature:** `backtrack` ≡ `revert` ≡ `rollback` — one concept. Meta
`BACKTRACK` and catalog `revert_effects` (aliases `backtrack` / `rollback`) are
the same retreat: undo the current branch’s effects, then broaden.

**Start anywhere:** recovery must work with an empty `effect_trace` (user left
bad chrome on). Judgment uses **branch fitness** (goal needed evidence kinds ×
world objects × typed blockers such as `filter_chip` / selection chrome). Host
overlays may *tag* filter chips; core must not match chip label string sets or
force-rewrite meta for a named trap.

```text
user/brain/meta: backtrack | rollback | unfit branch
  → revert_effects
       analyze(effect_trace LIFO undo_hint, then blocking chrome) → RevertPlan
       approve (auto only for low-risk allowlisted steps)
       execute realizations (+ look debt between steps)
```

| Forward effect / blocker | Realization (mechanism) | Risk |
| --- | --- | --- |
| Selection chrome / filter_chip / menu / picker | `press_escape` | low |
| Message already sent | `delete_committed_message` → `commit_irreversible(Delete)` | high (gated) |
| File copied | `remove_copied_file` → trash / delete copy | high (gated) |
| File / text edited | `undo_edit` → host Undo | medium |

Escape-class aliases (`clear_selection_escape`, `clear_search_filter`, …)
normalize to `press_escape`. Irreversible undo steps **compose**
`commit_irreversible`. High-risk plans never auto-approve.

### Composition for forward_message (not a bundled plan)

The model composes these; the runtime does not encode WhatsApp's menu tree:

```text
meta SEARCH (source / content referent)   # find-among-many mode
  → compose_search_query                  # stage: author
  → retrieve candidates                   # perceive / locate
  → resolve_entity                        # stage: rank → SearchResult.chosen
meta ACT
  → open_entity(chosen)                   # COMMIT
  → locate_content / select / reveal / invoke_affordance(Forward)
meta SEARCH (destination)                 # picker space
  → resolve_entity
meta ACT
  → open_entity(chosen)
  → commit_irreversible(Send)
```

`compose_search_query` is agentic search authorship: the model (via the
capability's LLM realization) decides how to combine evidence tokens. The
runtime must not invent templates such as ``contact + link_query``. Authorship
alone never means search is done.

`resolve_entity` is agentic candidate choice: rank visible rows against the
goal referent (source on search results, destination on the forward picker).
The runtime must not hardcode ``always pick (you)``, open the top hit, or
promote `matches_goal` directly to `open_entity` while ranking is unfinished.
Query-echo rows (self-echo of the typed string) are demoted when better-fitting
candidates exist. Keyboard Down+Return is a last-resort mechanism only when
there is no point and no candidates.

Skip any step whose postcondition is already true on screen. `dismiss_transient`
recovers from a wrong menu. New prompts will grow more compositions later;
hosts only declare realizations (`find_affordance`, `reveal_mode`, …).

Surface-dependent **variants** live under a capability as realizations
(e.g. `native_find`, `scroll_scan`, later `server_query`). The external
contract does not change when a variant is added.

## Division of vocabulary

The model sees three layers:

1. **Meta-actions** — kind of step (`search` vs `act` vs `perceive` vs
   `information_gathering` / strategic replan). Executive owns completion debt.
2. **General capabilities** — named operations from this catalog that have at
   least one realization for the current host. Prefer these when the intent
   matches; they collapse mechanical search space. Find stages under SEARCH;
   commit under ACT.
3. **Motor primitives** — `click`, `type`, `scroll`, `hover`, `right_click`,
   `press_escape`, `observe`. Always available; fine-grained when no capability
   applies.

## Growth model

- New messaging app → declare `find_affordance` (and later entity/open bindings).
  Core unchanged.
- New orthogonal need → add a realization under an existing capability, or add
  a catalog entry with the same contract shape.
- Do **not** grow by teaching the model longer click scripts.

## Evaluation (efficacy depends on this)

Vocabulary membership tests are necessary but not sufficient. Efficacy is
measured by whether the *right capability is chosen for the substrate*:

| Layer | What it catches | Where |
| --- | --- | --- |
| Unit / fake host | App-independence, dead-find typing hazard, Send-via-invoke refusal | `tests/plugin/test_locate_content.py`, `test_capability_host_fakes.py`, `test_forward_capability_composition.py` |
| Scenario suite | Scroll-hunt, early destination open, visible-target still locating, Send via click/invoke | `capability_eval.evaluate_forward_scenarios` |
| Multi-step trajectories | Relapse to hunt after visible; Send before Forward; happy-path composition | `capability_eval.evaluate_forward_trajectories` |
| Per-frame capability choice | Same checks on recorded / live-replayed frames | `perceptor_eval` → `capability_choice` score |
| Evidence contract | Locate must not claim relevance; commit must mark irreversible | `score_outcome_evidence_contract` |

Run:

```bash
python -m plugin.experiments.perceptor_eval --frames <dir> --capability-scenarios
python -m pytest tests/plugin/test_capability_eval.py tests/plugin/test_capability_host_fakes.py -q
```

A system that scores 100% on scene representation but low on capability choice
will not converge. Treat capability choice as a first-class kill gate.

## Relation to existing design docs

- Complements [belief-centric-control-loop.md](belief-centric-control-loop.md):
  capabilities are the experiments the controller can run; perception owns
  belief update.
- Complements [app-semantic-overlays.md](app-semantic-overlays.md): overlays
  declare host realizations; they do not own planning.
- Complements [content-object-discovery.md](content-object-discovery.md):
  discovery chooses *which* object among visible candidates; `locate_content`
  makes off-screen candidates reachable so discovery can run.
- Procedures remain staged *intent shape*, not keystroke macros
  ([procedure-execution-substrate.md](procedure-execution-substrate.md)).
