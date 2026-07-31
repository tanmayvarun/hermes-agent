# Goal-Conditioned Content Object Discovery

Hermes needs a reusable core capability for resolving task-relevant objects
from heterogeneous visible content. This is not a WhatsApp feature; WhatsApp
is just the first adapter that makes the need obvious.

The core question is:

> Given a goal and a visible collection of content objects, which object best
> satisfies the task?

Examples of content objects include:

- message rows
- links
- files
- notes
- browser tabs
- calendar items
- search hits

## Core contract

Adapters expose normalized `ContentObject` instances and stop there. The core
decides which object is relevant.

The object discovery pipeline is:

1. Adapter normalizes visible surface items into `ContentObject`.
2. Goal parser turns the prompt into `ContentQuery`.
3. Generic core scores candidate objects using type, URL, sender, container,
   text, and neighborhood signals.
4. Ambiguous cases are reranked by a reasoning-capable LLM.
5. The selected object is bound into task state.
6. The procedure continues from the bound object, not from raw UI labels.

## Key types

The reusable types now live in `plugin/worldmodel/content.py`:

- `ContentObject`
- `ContentQuery`
- `DiscoveryContext`
- `RankedContentObject`
- `ObjectResolution`
- `ContentObjectAdapter`

The generic resolver lives in `plugin/agent/object_discovery.py`.

The WhatsApp-facing compatibility wrapper in
`plugin/agent/conversation_reasoning.py` now delegates to the generic core
instead of owning message semantics itself.

## Eval harness

The synthetic benchmark for this capability lives in
`plugin/experiments/object_discovery_eval.py` and is wired into the CLI as:

```bash
plugin object-discovery-eval
```

It synthesizes message rows with URLs, previews, replies, and distractors, then
reports:

- `top1_accuracy`
- `micro_candidate_precision_at_k`
- `micro_candidate_recall_at_k`
- `micro_candidate_f1_at_k`
- macro versions of the same candidate metrics

The goal is to measure whether the generic discovery core is selecting the
right message evidence and keeping the ranked candidate set clean under
ambiguous message windows.

## Boundary

WhatsApp-specific code may:

- extract visible rows
- attach row-local metadata
- provide conversation container context
- expose read-only surface hints

WhatsApp-specific code must not:

- decide which row is the source object
- encode message-ranking policy
- hardcode semantic meanings of links, notes, or filenames
- decide the next action from the message content alone

## Why this matters

This gives Hermes a single object-discovery primitive that can be reused for
messages, notes, files, and other content surfaces. It also makes the
WhatsApp forward flow cleaner: the adapter exposes rows, the core picks the
object, and the procedure handles the rest.
