---
name: web-research
description: "Use when the user asks to research, compare, investigate, or recommend with sources (providers, products, APIs, markets). Research Controller under Task Controller — plan, checklist, budgets, source graph, then stop."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Research, Web, Comparison, Sources, TaskController]
    related_skills: [arxiv, research-paper-writing, filesystem-workspace]
    requires_tools: [web_search]
---

# Research Controller (under Task Controller)

This skill is the **Research** domain controller. Universal concerns
(budgets, hard stop, Task schema inject) are owned by the `task-controller`
plugin — this skill only defines research procedure.

You are a **task executor**, not an open-ended autonomous researcher.
Commit a plan, work the checklist, respect the budget, then stop.

## Hard rules

1. **Plan first.** Before any `web_search` / `web_extract`, emit a short Research Plan.
2. **Checklist via `todo`.** Create the checklist below; mark items completed as you go.
3. **Budget.** At most **5** `web_search` and **4** `web_extract` unless the user raises the budget (enforced by Task Controller).
4. **Prefer official sources.** Pricing + docs pages over blogs/roundups.
5. **Stop.** When the checklist is done **or** the budget is exhausted → synthesize. Do **not** search “one more time.”
6. **Gaps are OK.** Say “insufficient evidence” for missing dimensions; do not keep searching.
7. **For latest/current requests, verify the date on the item itself.** Do not trust a playlist, channel, or search snippet's "updated" date as proof that an episode/video is the latest one.

If Task Controller **blocks** a search/extract call, treat that as a hard stop and synthesize immediately.

## Research Plan (emit once, then execute)

```text
Research Plan
Entities: <3 names, or "choose 3 and name them">
Compare: <dimensions>
Expected sources: official pricing + docs/privacy per entity
Budget: ≤5 web_search, ≤4 web_extract
```

Do not improvise beyond this plan unless the user expands scope.

## Todo checklist

Create these items with the `todo` tool (adapt labels to the task):

1. Commit research plan
2. Collect pricing
3. Collect model / feature support
4. Collect privacy / data retention
5. Collect API compatibility
6. Synthesize comparison + recommendation
7. Cite source graph
8. Done

Mark each completed when finished. Item 8 means stop.

## Search strategy (stay under budget)

Typical efficient path (~5 searches, ~3 extracts):

1. One broad query naming all entities + the comparison dimensions.
2. One query focused on official pricing pages.
3. One query focused on privacy / ZDR / data retention.
4. Extract official pricing and/or docs pages (prefer `web_extract` on known URLs over more searches).
5. One more search only if a critical dimension is still empty.

Batch entities into fewer queries. Do not run a separate search per entity × dimension.

## Recency-sensitive answers

When the user asks for the **latest**, **newest**, **most recent**, **current**, or **today's** item:

1. Treat this as a date-validation task, not a title-match task.
2. Prefer the item's own page over playlists, channel hubs, or ranking pages.
3. Compare at least 2 plausible candidates when the search surface is noisy.
4. Report the exact publication date in the final answer.
5. If you cannot verify the item's own publication date, say so instead of guessing.

## Source graph (required in the final answer)

Maintain and print:

```text
Sources
EntityA
  → <url> — <what it supported>
EntityB
  → <url> — <what it supported>
...
```

Prefer official domains. Third-party roundups are secondary.

## Final deliverable

1. Comparison table or structured dimensions.
2. Clear recommendation with “why” and “sweet spot.”
3. Source graph (above).
4. Explicit gaps if budget ran out.

## Do not

- Start searching before the Research Plan.
- Issue parallel exploratory searches “just in case.”
- Keep searching after synthesis has started.
- Dump a bare link list without the entity → page mapping.
