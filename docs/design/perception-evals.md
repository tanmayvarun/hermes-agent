# Evaluating perception: a pyramid, not a benchmark

A single end-to-end success rate tells you something broke. It never tells you
what. The perception stack has several independent responsibilities --

```
raw sensing
→ structural reconstruction
→ semantic interpretation
→ affordance discovery
→ latent-action prediction
→ task-conditioned relevance
→ next-action ranking
→ transition verification
```

-- and a change can improve one while quietly destroying another. That is
exactly what happened when accessibility traversal went from excessively broad
(menu-bar items attached to messages) to excessively narrow (no content at
all). Both states pass "did the run finish", because neither run finished.

So the suite scores three separate truths and refuses to average them:

| Layer             | Core question                                       |
| ----------------- | --------------------------------------------------- |
| Observation       | Did required evidence survive sensing?              |
| Structure         | Did objects and regions form the correct hierarchy? |
| Affordance        | Did it identify what can be done now?               |
| Latent affordance | Did it predict what probes may reveal?              |
| Relevance         | Did it focus on the task-relevant subgraph?         |
| Ranking           | Are useful actions high in the frontier?            |
| Uncertainty       | Does it know when it does not know?                 |
| End to end        | Did it complete the goal safely?                    |

A correct action can come from an incorrect world model -- misread the screen
as a search dialog, click Search, get lucky. That run passes the end-to-end
check and should still fail the structure check.

## Running it

```bash
python -m plugin.evals.run                        # gates + corpus metrics
python -m plugin.evals.run --closed-loop          # also read recent run logs
python -m plugin.evals.run --json reports/now.json
python -m plugin.evals.run --baseline reports/prev.json   # fail on drift
python -m plugin.evals.harvest --frames <recording dir>   # refresh the corpus
python -m plugin.evals.post_open_pipeline         # piecewise open→hunt (A/B/C/D)
python -m plugin.evals.post_open_pipeline --live --model ollama-cloud/qwen3.5:397b
pytest tests/plugin/test_evals.py                 # the eval's own tests
```

## Piecewise post-open pipeline

End-to-end stalls hide *which* layer lied. After `open_entity`, score each
stage alone against the same trajectory (prior chat_list → post-open
conversation):

| Piece | Question |
| ----- | -------- |
| A Perception | Multimodal reading: `surface=conversation`, open contact, not search chrome |
| B Critic | Accepts that Δworld; refuses search-field chrome as `open_conversation` |
| C Brain | On accepted open source with content not visible → `locate_content` |
| D AX trap | Synthetic: AX title `Q Search\|` must not become the open referent |

Offline uses recorded replies; `--live` re-asks a real perceptor on the frozen
screenshot + packet. WhatsApp zarooratwala frames are fixtures of a general
open→hunt task, not special cases in the agent.

## Module golden corpus

Layered gold (eval-only, never training) lives under
`plugin/evals/golden/corpus/v1/`:

| Module | Gold asserts |
| --- | --- |
| perceive | surface, open conversation, no search-chrome open |
| critic | accepted Δworld; refuse search-field chrome as open |
| meta_action | next meta move; no hard VERIFY preempt |
| brain | capability on accepted world (e.g. `locate_content` after open) |

```bash
python -m plugin.evals.golden.score
python -m plugin.evals.golden.harvest_run --runs plugin/experiments/runs --limit 6
python -m plugin.evals.run   # includes [golden_v1]
```

Discipline: `v1` is frozen; promote live failures into permanent cases; never
set gold from the recorded model reply for the field under score. Harvest
writes *candidates* only — humans promote into `corpus/vN`. See
`plugin/evals/golden/README.md`.

## The frozen corpus

Fixtures are harvested from real recorded frames of the zarooratwala run: the
exact multimodal packet the model received, the reply it produced, and the
AX-derived shadow state captured alongside but never sent. Recording is
controlled by `HERMES_PERCEPTOR_RECORD_DIR`; harvesting freezes a selection
into `plugin/evals/fixtures/` bucketed by task stage.

Screenshots stay out of the repository. They are hundreds of megabytes and
regenerable; a fixture that needs pixels declares `screenshot.available` rather
than letting a metric silently score a frame it could not see.

Selection is deliberately unbalanced. Even sampling of a run yields mostly the
states it was stuck in, so the sample is capped per stage and then topped up
per failure trait -- `shell_only`, `no_ax_content`, `repeated_reading`,
`last_action_failed`, `surface_disputed`. The harvest reports which traits it
could not find, because a corpus missing its failure cases is a happy path
wearing a lab coat.

**The operational discipline that matters most: every discovered failure
becomes a permanent fixture.**

## Semantic world-understanding harness

Click-outcome evals miss the failure class of live 184742: the agent opened
Send-to, then treated background source-selection chrome as
`destination_selected`. That is **cross-surface semantic contamination**.

The dedicated harness lives at `plugin/evals/perception_semantic/`:

```bash
python -m plugin.evals.perception_semantic --expand-metamorphic
```

Each golden freezes the **production input packet** (screenshot reference +
compact AX with parentage + executive question + bindings + frontier), a
**structured gold world** (surfaces, typed owned claims, affordances,
acceptable/forbidden actions), and often a **contaminated reply** for the
negative path. Scoring is layered (surface, ownership, predicates,
cross-surface isolation, affordances, task actions, safety) — never one
giant JSON equal/not-equal.

Metamorphic family for the seed case: background selected-count 1→2→3 must
keep `destination_selected=false`; renaming the destination; and the single
causal positive — recipient checkbox selected → `destination_selected=true`.

CI gate: `semantic_perception_zero_cross_surface_contamination`.
Tag cases by **phenomenon** (`nested_surfaces`, `foreground_authority`, …)
not only by app. Screenshots stay out of git under
`plugin/experiments/fixtures/perceptor/`.

Live failures enter the curriculum via:

```bash
python -m plugin.evals.perception_semantic.harvest_failure --from-run <run> --auto-fail
# annotate eval_candidates/<id>/annotation.json
python -m plugin.evals.perception_semantic.promote --candidate <id> --phenomenon cross_surface
```

Set `HERMES_PERCEPTION_EVAL_CANDIDATES_DIR` alongside
`HERMES_PERCEPTOR_RECORD_DIR` so production packets freeze automatically.

## Ground truth that does not agree with itself

The temptation with recorded frames is to label them from the reply recorded
alongside. That builds an eval which confirms whatever the model believed. Each
derived label therefore comes from a source the model did not produce:

- `shadow` -- AX-derived predicates captured during the run, never sent
- `outcome` -- what the *next* frame shows the last action actually did
- `contract` -- the task's own composition rules, written down in `annotations.py`
- `manual` -- a human who looked at the screenshot

Anything none of those settles is left unlabelled, and metrics skip unlabelled
fields and report coverage. A 90% accuracy over 20% coverage is a different
claim from the same number over the whole corpus, and the report says which.

One caveat is load-bearing. On WhatsApp the shadow screen label is computed
over the *fused* world, which -- with no accessible content -- is populated
from the model's own objects. It is marked `shadow_fused` and is **not** used
for accuracy, only for an agreement diagnostic. Accuracy is scored against gold
labels alone.

Gold labels live in `plugin/evals/annotations/overrides.jsonl`, keyed by
fixture id, each carrying a note describing what was visible in the screenshot.
Do not add a line for a frame you have not looked at.

## What the first run found

Running the suite over 43 frozen fixtures surfaced four things immediately.

**Accessibility contributes nothing on this app.** Every frame carries exactly
two AX nodes, `AXApplication` and `AXWindow`. App-content recall is 0.00 and
chrome pollution is 1.00, and neither is an eval bug: WhatsApp publishes no
content to accessibility. Every claim about a message, a row or a control comes
from the screenshot. This is the strongest available argument for the
vision-first path, and it should be re-measured whenever the traversal changes.

**A single `screen` label is the wrong shape.** The derived label reports the
base pane while the model reports the overlay, and on inspection the model was
right every time: a Send-to sheet or a context menu owns the interaction while
open. Ground truth is now compositional -- `{sidebar, main, overlay}` -- and
overlay detection is scored separately.

**The derived label flaps while the screen does not.** Two visually identical
consecutive frames received different shadow labels. The temporal-consistency
work in the deferred list has a real target.

**A wrong-recipient bug, live in the resolver.** With the forward picker
filtered to "Tanmay", every visible row was a group whose name merely contains
it -- "Aakash <> Tanmay", "Tanmay <> Artha". The recorded reply chose one at
0.8 confidence, and `heuristic_resolve` independently chose another. The
resolver now abstains below a confidence floor and penalises multi-party
threads for person-shaped roles, keeping the ranking so the caller can narrow
the query instead of forwarding to strangers. Two gates hold that shut.

That last one is the argument for the whole exercise: it was found by an
offline metric over recorded frames, not by a live run, and it would have sent
a private message to a group of strangers.

## The metrics

Each returns a value **and** the number of fixtures it could score. A metric
that skipped 80% of the corpus and reported 0.95 is worse than no metric.

| Metric | Layer | Direction |
| --- | --- | --- |
| `ax_content_recall` (weighted: critical 10, relevant 5, decorative 1) | observation | higher |
| `chrome_pollution_rate` | observation | lower |
| `surface_accuracy` (gold labels only) | structure | higher |
| `surface_agreement_with_shadow` (diagnostic, not a gate) | structure | higher |
| `overlay_detection_rate` | structure | higher |
| `target_grounding_accuracy` | structure | higher |
| `object_scope_violation_rate` | structure | lower |
| `critical_cta_recall` | affordance | higher |
| `invalid_cta_rate` | affordance | lower |
| `latent_affordance_f1` | latent affordance | higher |
| `task_focus_score` | relevance | higher |
| `distractor_capture_rate` | relevance | lower |
| `top3_acceptable_action_rate` (+ MRR) | ranking | higher |
| `forbidden_action_rate` | ranking | lower |
| `unsupported_high_confidence_rate` | uncertainty | lower |
| `evidence_gap_declaration_rate` | uncertainty | higher |
| stage completion, steps-to-goal, false-success rate | end to end | -- |

Two deserve explanation.

`top3_acceptable_action_rate` normalises motor verbs to the capability they
amount to on that surface, so a bare `click` on a chat list scores as
`open_entity`. Without that, the metric measures vocabulary drift rather than
action quality -- it read 0.279 before normalisation and 0.814 after, with no
change to the system under test.

Closed-loop stages are a ladder, not a checklist. A destination cannot have
been chosen on a picker that never opened, so a later flag without its
predecessor is evidence the signal fired on an *attempt*; the raw flags are
kept as `claimed_stages` for diagnosis. Before this, stalled runs looked half
finished.

## Gates

`plugin/evals/gates.py` holds one scenario per failure that reached a live run,
reduced to the smallest input that reproduces it and asserted against the code
as it stands. Any single failure fails CI -- no averaging, no interval:

- a global menu item becoming a task CTA (`Settings` → search)
- `Forward` bound to whatever generic button was nearby
- an object-scoped gesture landing on the encryption notice
- `Pallavi` opening `Pallavi Ather Gen3`
- a group thread winning a destination meant for a person
- a containment-only match being acted on instead of abstaining
- a finished phase restarted by re-searching the open source chat
- a picker jumping to sidebar search on a typing action
- a keyboard shortcut overriding a chosen target point
- a confident claim with no screenshot and no content nodes
- `Send` taken through the reversible path
- a predicted control reported as observed
- a run filename containing the goal keyword entering the frontier

Statistical gates are separate and directional: critical CTA recall may not
fall more than 1%, top-3 not more than 2%, pollution may not rise more than 5%,
unsupported claims may not rise at all.

## Deliberately not built

Named so the gaps are choices rather than oversights.

- **Calibration** (Brier, ECE, reliability diagrams). Needs many comparable
  examples per confidence bucket; 43 fixtures cannot support it.
- **Metamorphic invariants** (window moved, theme changed, timestamps
  altered). High value, needs a capture harness that can re-shoot a scene under
  transformation.
- **Counterfactual pairs** (remove Forward, expect a probe instead). Needs
  synthetic scene editing.
- **Temporal-consistency sequences**. The corpus is frame-indexed and ordered,
  so belief-flip rate and object-identity continuity are the natural next
  metrics; the flapping shadow label above is a waiting first case.
- **Cross-sensor reconciliation under controlled disagreement**. Requires
  injecting a stale or corrupted sensor, which the harvester does not yet do.
- **Model comparison across Ollama variants**, and **online shadow evals**.
  Both need the live replay path (`perceptor_eval --live`) wired to this corpus
  rather than a second one.
- **Efficiency and cost per correct action.** Latency is recorded per frame but
  not yet aggregated against correctness.

## Layout

```
plugin/evals/
├── corpus.py        frozen fixtures, traits, harvest selection
├── annotations.py   ground truth, sources, the task contract, overrides
├── metrics.py       the layered metrics
├── closed_loop.py   stage ladder over run logs
├── gates.py         hard regression scenarios + statistical gates
├── harvest.py       recording -> committed corpus (CLI)
├── run.py           the layered report (CLI)
├── fixtures/        committed, screenshot-free
└── annotations/overrides.jsonl   gold labels, one per line

tests/plugin/test_evals.py        tests for the eval itself
```

Related: [affordance-frontier.md](affordance-frontier.md),
[world-model-critic.md](world-model-critic.md).
