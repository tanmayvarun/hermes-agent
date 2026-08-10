# Agent design — executive meta-action contract (v1)

This document freezes the **executive / brain** layer: why the agent spends the
next unit of effort. Platform hosts (macOS, Linux, Android, WhatsApp, Finder,
Gmail, filesystem, browser, memory, APIs) are **implementations underneath**
capability adapters — never architectural assumptions above this boundary.

Related code: [`plugin/agent/executive/meta_action.py`](../../plugin/agent/executive/meta_action.py),
[`plugin/agent/executive/meta_contract.py`](../../plugin/agent/executive/meta_contract.py),
[`plugin/agent/capabilities/search_episode.py`](../../plugin/agent/capabilities/search_episode.py).

---

## Key design rule

> **A meta-action represents the executive's reason for spending the next unit of
> effort, not the mechanism used to do it.**

So:

| Not this (mechanism) | This (purpose) |
| --- | --- |
| take screenshot / AX dump | **PERCEIVE** |
| type into a search bar | **SEARCH** (or ACT if committing elsewhere) |
| click | **ACT**, **SEARCH**, or **EXPLORE** depending on *why* |
| call an LLM | often **THINK** (or internal to another meta) |

The same meta-actions remain valid on macOS, Linux, Android, Gmail, a filesystem,
a browser, long-term memory, an API, or another agent.

---

## Core vocabulary (freeze these eight)

| Meta-action | Executive meaning | Category |
| --- | --- | --- |
| **THINK** | Derive something from information already available | epistemic |
| **PERCEIVE** | Acquire a current description of some **known** scope | epistemic |
| **SEARCH** | Find something satisfying **known criteria** in a search space | epistemic |
| **EXPLORE** | Discover possibilities when target / route / search space is insufficiently known | epistemic |
| **ACT** | Intentionally change external state toward the goal | instrumental |
| **ASK** | Request missing information, judgment, permission, or clarification from another actor | epistemic |
| **DELEGATE** | Assign a bounded objective to another capable agent / skill | control |
| **WAIT** | Allow time or an external process to change state before reconsidering | control |

### Explicitly *not* top-level meta-actions

These are intentions, controller operations, or capability details — not peers of
the eight:

| Name | Where it belongs |
| --- | --- |
| **VERIFY** | Intention (“establish that X”) satisfied by PERCEIVE / SEARCH / ASK / WAIT / THINK |
| **BACKTRACK** | Exploration-controller operation over branch state; next meta may be EXPLORE / SEARCH / PERCEIVE / ACT |
| **RETRIEVE** | Known-address fetch — usually a capability under PERCEIVE / ACT; promote later only if needed |
| **REMEMBER / PLAN / CLICK / TYPE** | Substrate or motor; never meta |
| **REFLECT** | Runtime procedure: surprise → PERCEIVE (+ THINK over mismatch) |
| **INFORMATION_GATHERING** | Trajectory / exploration-controller replan → **THINK** or **EXPLORE**; not SEARCH |
| **PROBE** | Affordance reveal → **EXPLORE** |
| **ASK_USER** | Same intention as **ASK** |

---

## Universal envelope

All meta-actions share one request / result shape so filesystem search, visual
perception, a delegated coding task, and a user clarification feed the same
executive workspace.

```text
MetaActionRequest
  kind, objective, intention_id, belief_context, motivation,
  scope, constraints, success_condition, expected_result,
  budget, task_id, parent_action_id

MetaActionResult
  status ∈ success | partial | not_found | blocked | failed | uncertain
  observations, artifacts, proposed_belief_updates,
  discovered_capabilities, unresolved_questions, suggested_next_moves,
  side_effects, confidence, provenance
```

**Mandatory on every meta-action:** *why*, *what it expects to learn or change*,
*how we know it is done* (motivation / expected_result / success_condition).

Kind-specific payloads (ThinkRequest, PerceiveRequest, SearchRequest, …) sit
inside this envelope. See `meta_contract.py`.

---

## Per-meta contracts (summary)

### THINK — internal-state operation

Compute using information already available. Must **not** intentionally acquire
new external evidence or alter the external world. If new evidence is required,
THINK should recommend SEARCH / PERCEIVE / EXPLORE / ASK rather than hallucinate.

### PERCEIVE — known scope

“Tell me what is currently here.” Scope is known; modality is irrelevant
(screenshot+AX, `ls`, Gmail API, DOM, `git status`, HTTP GET, memory slice).

Distinct from SEARCH: PERCEIVE = *what is here?*; SEARCH = *which thing
satisfies these criteria?*

### SEARCH — criteria known, location unknown

Find entities / information matching criteria in a defined or discoverable space.
May internally query → inspect → refine → expand scope → rank. Executive owns
intention; adapters own motors. Returns candidates, coverage, exhausted,
unexplored_scopes (see `SearchIntent` / `SearchResult` on the search episode).

**Intelligence (not host-specific heuristics):**

1. **Evidence-grounded authorship** — the query bag is goal fields / hypotheses
   only. Do not inject intent labels (“link”, “message”, …) that the human said
   about the task but that are not content criteria. Invented AND-tokens make
   host search look “semantically wrong” when they are just lexical filters.
2. **Judge the result set against `SearchIntent`** — after retrieve, ask whether
   candidates satisfy the *criteria* (what kind of thing, which referent), not
   whether a URL substring matched a typed word. Sparse / odd fits → refine
   (drop a token, swap scope, clear a filter) inside the same SEARCH episode.
3. **Rank by semantic fit to criteria** — use perception + resolve / conversation
   relevance against the intent (e.g. “the site/brand content to forward”), not
   blacklists of hosts (`instagram.com`, `utm_`, …). Prefer URL-bearing content
   over query echoes when the intent is content; let the ranker argue *why*.
4. **Mismatch is information** — chat highlights many referent hits while the
   sidebar shows one dubious Links row ⇒ coverage/criteria mismatch ⇒ THINK or
   SEARCH-refine, not a one-shot commit on the lexical survivor.

Host adapters supply motors and observations. Executive intelligence is the
query → observe → judge-against-intent → refine loop.

### EXPLORE — route / possibility space insufficiently known

Discover structure, affordances, or routes when criteria themselves are
inadequate (“how is Forward exposed?”). Often collapses into SEARCH or ACT once
a target is known. May actuate reveal / probe motors — **not** compose / rank.

**Affordance coverage belongs with perception;** the perceptor judges sufficiency
(`affordance_stance`: `act_clear` vs `explore_needed`). EXPLORE meta means there
is still *information value* in probing — **not** that a sticky flag is set.
Sticky `route_discovery_owed` / `incomplete_reveal` must clear when grounded goal
control exists or stance is `act_clear`; runtime must not latched-force EXPLORE
over that judgment.

**`act_clear` is honest only with actuatable geometry** (point or bounds on the
goal control). A verb label without a clickable site is still coverage work —
not ACT. Under true `act_clear`, ACT **commits** (invoke/commit); it must not
Observe, re-reveal, or dismiss the open overlay (unless referent repair).

**Reveal is a bounded EXPLORE intention**, not sticky ACT. Runtime uses an
immutable `Intention` + mutable `IntentionFrame` (method frontier, attempts,
budgets): intent survives method failure; methods rotate with fresh
`target_binding` grounding; PERCEIVE must answer a named need (effect
verification / re-ground). Method effect ≠ intention success. Local route
exhaustion is derived and returns authority to the executive (SEARCH / EXPLORE /
THINK / ASK / …) — never unmotivated Observe under sticky ACT. Same-method
retry only when `SAFE_TO_RETRY` / TRANSIENT; irreversible methods use
`VERIFY_BEFORE_RETRY` / `NEVER_AUTO_RETRY`. Effect settle windows are distinct
from affordance TTL. Missing method preconditions spawn a child intention
(`suspended_by_child`); on child success the parent resumes, reobserves, and
**re-ranks** — it must not blindly replay the blocked method.

**Surface ownership (perception):** every object/belief claim carries
`owner_surface` (+ selection `semantic_role`). Typed selection predicates are
separate namespaces — e.g. `source_message_selected_count` on a background
conversation must never satisfy `destination_selected` on a foreground
destination picker. The multimodal packet includes screenshot, AX with
parentage, the executive’s scoped question, and grounded affordances; the
foreground interaction surface scopes evidence for the active intention.
Runtime scrub + Forward-without-destination guards are last-line defence —
intelligence must produce the correct world first. Unresolved destination in
an open picker → meta **SEARCH** within picker scope (`type_query`), then ACT
select, then ACT commit.

**Effect closure:** motor-ok is not world effect. After a reveal/probe that
leaves a *pending* `incomplete_reveal` or a missing predicted overlay, the next
meta is PERCEIVE then EXPLORE (escalate gesture) — not ACT on the same content
fingerprint — **unless** the new look already shows the goal act (`act_clear`),
or the episode has already failed/exhausted. Geometry that lands outside the
bound entity/scope is also non-progress and must invalidate, not latch phase.

**Referent selection fidelity:** grounding a verb (Forward visible) is not
binding the patient of that verb. Object-scoped affordances require a selected
referent whose chrome matches binding constraints — **except** when honest
`act_clear` already holds on an open action overlay (the reveal that opened
the menu scoped the patient; forcing `select_content` then is a deadlock).
Selection-mode chrome (“N Selected” + toolbar) is a distinct surface from
context/action menus and
from destination pickers. After invoke regression with wrong/deselected target,
meta owns ACT select/cancel repair — not observe thrash or re-invoke of the
same fingerprint.

### ACT — intentional external change for the goal

Send, move, click known Forward, deploy, rename, post. Method may be mouse,
keyboard, shell, API, … Purpose defines the meta: the same click can be EXPLORE,
SEARCH, or ACT.

### ASK — another actor

User, coworker, agent, or service. Prefer ASK when more autonomous computation
is worse than requesting information / authority.

### DELEGATE — bounded objective to a specialist

Executive remains parent-goal owner. Sub-agent must not redefine the parent goal.

### WAIT — time / external process

Download, app open, deploy, email reply, animation. Prefer WAIT then PERCEIVE
over observe-observe-observe loops.

---

## Choosing among meta-actions

Construct a `DecisionProblem` (goal, intention, known, unknown,
blocking_uncertainty, available_meta_actions), then use this **semantic**
guidance (not a rigid if/else tree):

```text
Enough evidence for a reliable goal-advancing action?     → ACT
Know what to find (criteria)?                             → SEARCH
Know the scope; need its current state?                   → PERCEIVE
Lack a sufficiently defined target or route?              → EXPLORE
Existing information can resolve the issue?               → THINK
Another actor has information / authority?                → ASK
Bounded objective a specialist solves better?             → DELEGATE
Missing information expected through time?                → WAIT
```

Epistemic moves carry `EpistemicExpectation` (questions, information gain,
coverage). ACT carries `InstrumentalExpectation` (goal progress, transition).
Shared utility sketch:

```text
Utility = goal_progress + information_value + reversibility
        − risk − cost − latency − repeat_penalty
```

---

## Generic scope and entities

Do **not** bake host types into executive contracts.

```text
ScopeRef(domain, locator)     # filesystem path, app UI surface, email thread, memory…
EntityRef(entity_type, domain, identity, properties…)
```

Domain adapters understand concrete IDs; the executive reasons about entity /
scope / confidence / provenance.

---

## Memory and long-running tasks

Memory is a **substrate / world**, not a meta-action. The executive may
PERCEIVE / SEARCH / EXPLORE / THINK over memory the same way as over a folder or
inbox.

Tasks persist as `TaskRecord` (goal, intention, beliefs, bindings, open
questions, exploration state, artifacts, commitments). On return, reconstruct
workspace from current request + relevant memory — restore a checkpoint, do not
replay giant chat history.

---

## Architectural invariants

1. The executive owns the goal and persistent task state.
2. Meta-actions describe cognitive purpose, never implementation mechanism.
3. All domain-specific behavior lives behind capability contracts.
4. Perception is modality- and domain-neutral.
5. Search means criteria-known / location-unknown.
6. Explore means route / possibility-space insufficiently known.
7. Think cannot fabricate external evidence.
8. Act requires an externally changing intended effect.
9. Every meta-action declares motivation, expected result, and stopping condition.
10. Memory is accessible through the same meta-actions, not a separate control architecture.
11. Sub-agents may be sophisticated; the executive remains parent-goal owner.
12. Historical task context is reconstructed into the workspace, not replayed as conversation.

---

## Resulting core architecture

```text
                    USER / CONTINUING TASK
                             │
                    Context reconstruction
                current request + relevant memory
                             │
                             ▼
                  EXECUTIVE WORKSPACE
            (goal, beliefs, intention, questions,
             hypotheses, bindings, exploration, …)
                             │
                    Construct decision problem
                             │
                             ▼
                     Choose meta-action
         THINK PERCEIVE SEARCH EXPLORE ACT ASK DELEGATE WAIT
                             │
                  capability runtime
                             │
             domain / platform implementation
                             │
                 observations / results
                             │
               Update executive workspace → choose again
```

None of these boxes say WhatsApp, Finder, macOS, screenshot, shell, or LLM.
Those appear only below the capability boundary.

---

## Migration notes (codebase)

The runtime accepts **only** the eight core meta-actions. There are **no runtime
aliases** — legacy tokens (`probe`, `verify`, `ask_user`, `reflect`,
`information_gathering`, `backtrack`) are rejected at parse time.

Golden fixtures and eval gates have been updated to the core eight. Legacy
concepts map to core semantics in documentation only:

| Legacy concept | v1 meta-action |
| --- | --- |
| surprise look + explain | PERCEIVE (+ THINK over mismatch) |
| branch retreat / replan | EXPLORE or THINK |
| verify intention | PERCEIVE |
| ask user | ASK |
| probe affordance | EXPLORE |

`python -m plugin.evals.check` is the hard gate for meta-action contracts.
