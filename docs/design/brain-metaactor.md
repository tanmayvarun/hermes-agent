# Hermes Brain as MetaActor

**Status:** Architecture locked. Incremental implementation via Slices 1–7 below.  
**Related:** [personal-agent-brain-and-substrates.md](personal-agent-brain-and-substrates.md),
[memorydesign.md](memorydesign.md),
[executive-runtime.md](executive-runtime.md),
[agent-design.md](agent-design.md).  
**Code seam (Slice 1):** [`plugin/agent/brain/`](../../plugin/agent/brain/) — `BrainWorkspace`, `ContextActivation`, `TurnRepresentation`.

---

## Stance (locked)

> **Hermes Brain is the MetaActor.** It owns the evolving interpretation of the
> user's world, actively gathers information, decides when it knows enough,
> forms intentions, and chooses effects. Memory, LLMs, search systems,
> perception, tools, and execution substrates are **resources** available to
> that Brain.

> **When a new user turn arrives, associative memory activation happens before
> semantic commitment.** Deliberate retrieval happens later only if the
> automatically activated context is insufficient.

Not the brain:

```text
TUI / Desktop / CLI
ComputerUse
MemorySystem
a single LLM invocation
```

The brain:

```text
persistent Agent Brain + BrainWorkspace + control loop (MetaActor)
```

---

## Top-level architecture

```text
                                CLIENTS
                   TUI / Desktop / CLI / Voice /
                    Automation / future Mobile
                                  │
                                  ▼
                           ClientAdapter
                                  │
                                  ▼
                            TaskIngress
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                         HERMES RUNTIME                           │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                       AGENT BRAIN                          │  │
│  │                        MetaActor                           │  │
│  │                                                            │  │
│  │   BrainWorkspace                                           │  │
│  │   ├─ current user turn                                     │  │
│  │   ├─ working/session context                               │  │
│  │   ├─ hypotheses / open questions                           │  │
│  │   ├─ known facts / evidence                                │  │
│  │   ├─ bindings / unresolved references                      │  │
│  │   ├─ intentions / desired effects                          │  │
│  │   ├─ progress                                              │  │
│  │   ├─ semantic attempt history                              │  │
│  │   └─ constraints                                           │  │
│  │                                                            │  │
│  │   ContextActivation        Deliberate information gathering│  │
│  │          │                              │                   │  │
│  │          └──────────────┬───────────────┘                   │  │
│  │                         ▼                                   │  │
│  │                  LLM Consultants                            │  │
│  │           interpretation / synthesis /                      │  │
│  │           hypothesis / planning advice                      │  │
│  └─────────────────────────┬──────────────────────────────────┘  │
│                            │                                     │
│             ┌──────────────┴───────────────┐                     │
│             │                              │                     │
│     INFORMATION SUBSTRATES          EXECUTION SYSTEM             │
│             │                              │                     │
│     ┌───────┼─────────┐           CapabilityRegistry             │
│     │       │         │                   │                      │
│   Memory  Files/Web  World          MethodFrontier               │
│                     perception             │                      │
│                                            ▼                      │
│                                  Execution Substrates             │
│                             MCP/API / browser / shell /           │
│                             ComputerUse / specialists             │
└──────────────────────────────────────────────────────────────────┘
```

One Hermes runtime. Clients are not brains. Substrates are not brains.

---

## Progressive interpretation

Do **not** treat Goal as the first rich semantic object from raw text.

```text
Raw user turn
      ↓
automatic ContextActivation
      ↓
initial LLM interpretation (consultant)
      ↓
tentative TurnRepresentation
      ↓
sufficient?
   ┌──┴──┐
  yes    no
   │      ↓
   │    Brain deliberately gathers more information
   │      ↓
   │    update BrainWorkspace
   │      ↓
   │    consult again
   └──────┬
          ↓
semantic commitment (RoleBinder)
          ↓
intentions / bindings
          ↓
method selection (MethodFrontier)
          ↓
execution
```

### TurnRepresentation (provisional)

```text
TurnRepresentation {
    raw_turn
    detected_mentions
    possible_entity_types
    action_hints
    objects
    channels
    temporal_cues
    project/topic cues
    unresolved_references
    interpretation_status = provisional | committed
}
```

Example — `"send hi to Pallavi on WhatsApp"`:

```text
action_hint = send_message
content = "hi"
person_mention = "Pallavi"
channel_hint = "WhatsApp"
recipient.entity_id = UNKNOWN   # not yet decided
```

---

## ContextActivation (automatic)

First-class Brain stage. Runs for essentially every meaningful user turn.
Associative, cheap, high-recall. Does **not** wait for an explicit question.

```text
RawTurn → ActivationSignature → ContextActivation → BrainWorkspace
```

Activation signature cues (example):

```text
lexical: Pallavi, WhatsApp
semantic: messaging, person, communication
action: send
session: current task / recent working context
```

Activation is **inside the Brain's cognitive loop**; MemorySystem executes the
indexed lookups.

### Deliberate retrieval (later)

When enriched interpretation still has uncertainty:

```text
Brain: "I need more evidence about X."
→ SEARCH memory | files | web | current_app
→ inspect → update workspace → maybe consult → search again
```

Optimized for a specific information deficit — not the same as activation.

| Mode | When | Goal |
|---|---|---|
| ContextActivation | every meaningful turn | recall > precision |
| Deliberate SEARCH | after insufficient interpretation | solve a deficit |

---

## Memory temperatures (cache hierarchy)

```text
L0 — Current turn (raw utterance)
L1 — Working Context (session, hypotheses, recent refs)
L2 — Hot Personal Context (recent entities, active projects, salient relationships,
     preferences, recent reference resolutions, useful procedures)
L3 — Indexed Long-Term Memory (entities, relationships, episodes, facts, …)
L4 — Archive / Evidence (raw events, old episodes, large documents)
```

Normal prompt cost: **L0 + L1 + cheap L2**, then cue-triggered L3.  
L4 only when deeper evidence is necessary.

Storage architecture remains [memorydesign.md](memorydesign.md):

```text
Evidence ≠ Memory ≠ Projection ≠ Retrieval ≠ Brain belief
```

WorkingContext is Brain/runtime state — **not** durable long-term memory.

Long-term classes: Episodic, Entity, Relationship, Semantic/Factual, Preference,
Procedural, Environment/Channel. Interaction aggregates stay separate from
semantic relationships.

---

## BrainWorkspace

Foundational runtime object — the agent's persistent contextual representation
for the active session/turn loop.

```text
BrainWorkspace {
    turn
    session_ref
    working_context
    provisional_interpretation
    known_facts[]
    retrieved_evidence[]
    hypotheses[]
    open_questions[]
    unresolved_references[]
    bindings[]
    current_intention
    desired_effects[]
    progress[]
    semantic_attempt_history[]
    constraints[]
    active_context_refs[]
}
```

Evolves over time. Individual LLM calls operate on **selected projections**
(ContextViews), not the full workspace.

---

## LLM consultants (advice only)

```text
InterpretationConsultant
HypothesisConsultant
SynthesisConsultant
PlanningConsultant
SearchStrategyConsultant
ReflectionConsultant
```

Same model with different contracts is fine initially.

```text
LLM call
  receives ContextView (via ContextAssembler)
  returns Advice / Proposal
```

Does **not** directly mutate authoritative state. Brain adopts or rejects.
EntityResolver / Brain create BindingProposal; **RoleBinder commits**.

### ContextAssembler placement

```text
BrainWorkspace
     │  consultation purpose
     ▼
ContextAssembler
     │
     ▼
ConsultationContext → LLM
```

Agent context ≫ LLM context. Assembler is Brain-facing (may live under
`plugin/agent/memory/cognition.py` today; ownership is Brain consultation).

---

## Meta-actions (information / effect spaces)

```text
THINK | PERCEIVE | SEARCH | EXPLORE | ACT | ASK | DELEGATE | WAIT
```

Operate over spaces, not UI by default:

```text
SEARCH space=memory | filesystem | web | current_app
PERCEIVE source=world | process | current_document
```

Brain chooses the cognitive operation; capability selection realizes it.

---

## Runtime ownership

```text
AgentRuntime
├── AgentSession        → BrainWorkspace, WorkingContext, TaskStates,
│                         pending questions, suspended intentions,
│                         session constraints, semantic attempt history
├── Brain (MetaActor)
├── MemorySystem        → process/profile owned (not per chat session)
├── CapabilityRegistry
├── ExecutionRegistry
├── LLMConsultants
└── RuntimeServices
```

```text
Client ≠ Session ≠ Runtime ≠ Memory
```

Multiple clients may attach to one session. Multiple sessions share one personal
MemorySystem.

### Memory startup (profile)

```text
Hermes profile starts
→ open LocalMemorySystem
→ load projections + source cursors
→ MemoryBootstrapCoordinator (incremental, non-blocking)
→ expose source readiness (READY | AUTH_REQUIRED | PARTIAL | …)
```

Absence in an uninitialized source is **not** negative evidence.

Offline maintenance is **MemoryConsolidator** (not “Memory Brain”) — cannot
decide what the active agent should do.

---

## Authority table

| Component | Authority |
|---|---|
| **Agent Brain / MetaActor** | what to investigate, what evidence means, what goal/intention to pursue |
| **BrainWorkspace** | current cognitive state |
| **MemorySystem** | durable memory/evidence and efficient retrieval |
| **MemoryConsolidator** | derived-memory formation/refinement |
| **LLM consultant** | reasoning/advice/proposals over supplied context |
| **RoleBinder** | authoritative task-role identity commit |
| **CapabilityRegistry** | what methods are available |
| **MethodFrontier** | method selection under executive policy |
| **Execution substrate** | realization of selected method |
| **WorldState** | current observed environment |
| **Client** | user IO/rendering only |

---

## Module ownership map (migration target)

Conceptual ownership — **do not mass-move files in Slice 1**.

```text
agent/
├── runtime/     agent_runtime, session, task_ingress
├── brain/       workspace, context_activation, interpretation,
│                meta_actor, consultations, turn_representation
├── memory/      stores, projections, query, bootstrap, adapters, consolidator
├── executive/   intention, role_binding, progress, capability_registry,
│                method_frontier
└── substrates/  mcp, filesystem, browser, computer_use, specialists
```

---

## Pallavi happy path (product behavior)

```text
USER: "send hi to Pallavi on WhatsApp"
  → TaskIngress RawTurn
  → ContextActivation (both Pallavis + relationships + WhatsApp IDs + procedures)
  → BrainWorkspace populated
  → Interpretation consultant (provisional; recipient likely E123)
  → BindingProposal → RoleBinder commits E123
  → MethodFrontier → structured WhatsApp / ComputerUse
  → substrate receives Person E123 + WhatsApp W17 — never chooses which Pallavi
```

Harder prompts (e.g. “send the old PhonePe deck to Pallavi”) use the same
MetaActor with deliberate SEARCH when activation is insufficient.

---

## Implementation sequence

Stop expanding storage architecture. Reuse LocalMemorySystem as L2/L3 backend.

| Slice | Deliverable |
|---|---|
| **1** | BrainWorkspace + ContextActivation on every normal TUI turn; no semantic commit |
| **2** | LLM interpretation consumes activated ContextView → provisional TurnRepresentation |
| **3** | Generic entity resolution from BrainWorkspace (retire send-specific memory special path) |
| **4** | Deliberate MetaActor memory SEARCH when activation insufficient |
| **5** | RoleBinder after contextual interpretation |
| **6** | MethodFrontier strictly after semantic bindings; ComputerUse gets resolved targets |
| **7** | MemoryConsolidator: episodes, semantic compaction, procedures/preferences, vectors |

### Evidence acquisition before ASK (generic Brain/MetaActor behavior)

Behavioral principle:

> **uncertain semantic commitment → gather discriminating evidence → reinterpret → commit or ASK**

ASK is terminal information acquisition after bounded evidence effort — not the
first response to a narrow numeric margin.

This is **generic MetaActor behavior**, not an identity-specific mini-agent.

```text
InformationNeed
  → EvidenceAcquisitionEpisode (domain-neutral)
       assess remaining uncertainty (EvidenceStrategy)
       → preferred evidence kinds
       → InformationCapabilityRegistry → provider
       → EvidenceResult → update hypotheses → reassess
  → domain consultant / BindingAssessment (evidence-backed)
  → ActionRiskPolicy (proceed | ASK | refuse)
```

Hard rules:

- Generic episode knows only `InformationNeed`, hypotheses:`Any`,
  `EvidenceStrategy`, budgets — not `IdentityHypothesis`.
- Domain strategies (`EntityResolutionEvidenceStrategy`,
  `DocumentResolutionEvidenceStrategy`, …) **incorporate** raw `EvidenceResult`
  payloads into hypotheses, then reassess. Providers must not mutate hypotheses.
- **Monotonic incorporate:** missing fields/rows from a new provider must not erase
  previously established evidence. Absence ≠ negative evidence.
- **Three-way epistemic state:** `known_positive` / `known_negative` / `unknown|error`
  — failed lookups must not become zeros.
- Attempts are tracked by `(evidence_kind, provider_id)`. Provider failures are
  pair-scoped unless the result declares global unavailability.
- Probe execution is exception-bounded → `EvidenceResult(ERROR)`.
- Dual budgets: `budget` (meaningful probes) and `attempt_budget` (operational).
- `BindingAssessment` uses qualitative `evidence_strength`
  (`weak|moderate|strong|decisive`) and `evidence_classes` — not fabricated
  calibrated confidence/margin. `ActionRiskPolicy.allows_binding` consumes strength.
- Evidence gathering resolves **epistemic** insufficiency only; never overrides
  `ActionRiskPolicy.REFUSE`.
- Exact-name evidence is a **prior**, not resolution authority.

Design debt (defer):

- Per-feature evidence provenance / EvidenceRefs on hypotheses
- Retrieval-coverage-aware `single_candidate` strength

Code:

- [`plugin/agent/brain/information_need.py`](../../plugin/agent/brain/information_need.py)
- [`plugin/agent/brain/evidence_acquisition.py`](../../plugin/agent/brain/evidence_acquisition.py)
- [`plugin/agent/brain/identity_consultant.py`](../../plugin/agent/brain/identity_consultant.py) (strategy + BindingAssessment)
- [`plugin/agent/brain/document_resolution.py`](../../plugin/agent/brain/document_resolution.py) (non-identity golden path)
- [`plugin/agent/information/`](../../plugin/agent/information/)

### Slice 1 acceptance

- Activation for `"send hi to Pallavi on WhatsApp"` admits candidate entities into workspace evidence when Day-0 memory exists
- Activation does **not** set `goal.committed_*`, does **not** write `desired_effects`, does **not** clear session `bindings`
- Mentions stay `role=unknown` until interpretation
- **BrainWorkspace is session-persistent**; new turns reuse and enrich it (L1 working context)
- **Activated context is input to `interpret_task_request`** (`notes.activated_context`) — not a sidecar shelf
- Empty / unready memory → empty activation, no crash
- Existing recipient_binding path remains authoritative until Slice 3–5
- L1 golden: recent session context can outrank global personal salience for the same surface form

---

## Core picture

```text
USER → TaskIngress → HERMES BRAIN
  RawTurn → ContextActivation (L1/L2/cue L3)
       → BrainWorkspace
       → LLM interpret-in-user's-world
       → sufficient? else MetaActor SEARCH/PERCEIVE → update workspace
       → semantic commitment (RoleBinder)
       → Intention / desired effect
→ MethodFrontier → MCP/API | Browser | ComputerUse → world effect → Event/Memory
```

Central principle:

> **The Brain does not wait to discover that it lacks context. Every incoming
> user turn first causes relevant parts of the user's remembered world to become
> active. The Brain then interprets the utterance inside that activated world,
> and only afterward performs deliberate search when deeper information is still
> required.**
