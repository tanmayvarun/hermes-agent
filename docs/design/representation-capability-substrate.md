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

## General capability catalog

Capabilities compose the agent. Search is the first fully realized member;
others are contracted so they grow the same way.

| Capability | Substrate | Contract | Status |
| --- | --- | --- | --- |
| `compose_search_query` | `task_evidence` | Author a search-box string from goal evidence, world document, and prior attempts. Does not hardcode a query template. Realization may inject via type+submit (mechanism). | **realized** (LLM author + type inject) |
| `resolve_entity` | `candidate_set` | Choose which visible candidate matches a goal referent (destination/source/…). Self markers like `(you)` are evidence, not a template. Does not claim forward/send succeeded. Realization may open/click the chosen row (mechanism). | **realized** (heuristic + optional LLM ranker) |
| `locate_content` | `searchable_surface` | Make content matching `query` reachable, or report exhaustion. Never claims relevance. | **realized** (native find + scroll scan) |
| `open_entity` | `addressable_entity` | Navigate into the named entity (conversation, channel, thread). | **realized** (resolve + click) |
| `select_content` | `addressable_entity` | Focus a content object inside an open surface without navigating away. | **realized** (resolve + click) |
| `reveal_actions` | `addressable_entity` | Expose the affordance set for an entity without committing. | **realized** (context-click / hover) |
| `invoke_affordance` | `affordance_set` | Activate a *named reversible* affordance. Refuses Send/Delete. | **realized** (named click) |
| `dismiss_transient` | `transient_chrome` | Clear an overlay that is not the task. | **realized** (dismiss chord / Escape) |
| `commit_irreversible` | gated target | Send / delete / confirm. Always a gated primitive; never bundled. | **realized** (allowlisted gated click) |

### Composition for forward_message (not a bundled plan)

The model composes these; the runtime does not encode WhatsApp's menu tree:

```text
compose_search_query             # when AX is chrome-only / entity not addressable
  → type_query(chosen)
  → resolve_entity(source)       # Pallavi vs Pallavi Ather Gen3, …
  → open_entity(chosen)
  → locate_content(query)        # only if open chat matches source referent
  → select_content(message)      # when focus helps
  → reveal_actions(message)
  → invoke_affordance(Forward)   # reversible
  → resolve_entity(destination)  # Tanmay vs Tanmay (you), …
  → open_entity(chosen)
  → commit_irreversible(Send)    # irreversible gate
```

`compose_search_query` is agentic search authorship: the model (via the
capability's LLM realization) decides how to combine evidence tokens. The
runtime must not invent templates such as ``contact + link_query``.

`resolve_entity` is agentic candidate choice: rank visible rows against the
goal referent (source on search results, destination on the forward picker).
The runtime must not hardcode ``always pick (you)`` or open WhatsApp's
top search hit when a point or resolved label exists. Keyboard Down+Return
is a last-resort mechanism only when there is no point and no candidates.

Skip any step whose postcondition is already true on screen. `dismiss_transient`
recovers from a wrong menu. New prompts will grow more compositions later;
hosts only declare realizations (`find_affordance`, `reveal_mode`, …).

Surface-dependent **variants** live under a capability as realizations
(e.g. `native_find`, `scroll_scan`, later `server_query`). The external
contract does not change when a variant is added.

## Division of vocabulary

The model sees two layers:

1. **Motor primitives** — `click`, `type`, `scroll`, `hover`, `right_click`,
   `press_escape`, `observe`. Always available; fine-grained when no capability
   applies.
2. **General capabilities** — named operations from this catalog that have at
   least one realization for the current host. Prefer these when the intent
   matches; they collapse mechanical search space.

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
