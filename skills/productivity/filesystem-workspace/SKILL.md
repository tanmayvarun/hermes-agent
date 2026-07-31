---
name: filesystem-workspace
description: "Use when the user asks to find, organize, compare, or act on files anywhere on the machine (project, Downloads, Desktop, Documents, home, or computer-wide). Filesystem Controller under Task Controller — plan, locate_file first, escalate, shortlist, then open."
version: 1.2.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Filesystem, Workspace, Files, PDF, Downloads, Home, TaskController]
    related_skills: [web-research, ocr-and-documents, nano-pdf]
    requires_tools: [locate_file, search_files, read_file]
---

# Filesystem Controller (under Task Controller)

This skill is the **Filesystem** domain controller. Budgets and hard stops
are owned by the `task-controller` plugin — this skill only defines search
and workspace procedure.

You may search **beyond the project cwd**. Prefer `locate_file` for find
intents; absolute `search_files` paths remain available for power digs.

## Hard rules

1. **Plan first.** Before mass file tools / `terminal`, emit a Filesystem Plan.
2. **Checklist via `todo`.** Create the checklist below; mark items as you go.
3. **Capabilities over raw loops.** Find intents are owned by **LocateFileCapability**
   (`locate_file` tool). Task Controller may auto-dispatch it and inject a structured
   result — treat that as authoritative; do **not** alternate `search_files` / terminal
   find-grep loops.
4. **Raw `search_files` only if** locate capability returned failed/empty **and** the
   user asks to dig deeper — or for coding grep-style work.
5. **Escalate scope deliberately** (see below) — do not stay stuck in `.` when the user means “on my computer.”
6. **Rank before deep reads.** Use capability confidence / name / mtime; shortlist then open.
7. **Cap opens.** Top N candidates only (usually 1–3).
8. **Stop** when checklist done or Task Controller blocks a tool. Report gaps.
9. **Artifacts.** List paths touched and why chosen/rejected.

Default budgets (plugin): `locate_file` ≤2, `search_files` ≤15, `read_file` ≤40, `terminal` ≤30, `tool_calls` ≤60.

## Layering

```text
Task Controller → LocateFileCapability → filename/scoped/content search
                → read_file (show/verify)
```

The model chooses the goal (find/show). The capability owns strategy and state.

## Find flow (T1)

```text
User: Find the Plugin 3.3kW Technical Specifications V3 file
→ Task Controller may auto-run LocateFileCapability (or you call locate_file)
→ high-confidence candidate in context / tool result
→ read_file (or OCR skill) → answer
→ do NOT run 15 raw searches
```

## Scope escalation (when using search_files)

Default `path='.'` is **only the session working directory**. When digging
deeper after locate failed, widen in this order:

1. Project / cwd (`.`)
2. User-named folders if given
3. Home common dirs — pass absolute paths:
   - `~/Downloads`
   - `~/Desktop`
   - `~/Documents`
   - `~/` (entire home) with a **narrow** glob (e.g. `*brochure*.pdf`)
4. Computer-wide — `path: "/"` (or macOS `/Users`) **only if** home search failed and the user wants a machine-wide find; keep the glob tight and `limit` small

Never start with `/` unless the user asked for a full-disk search or narrower scopes returned nothing.

```text
# Prefer
locate_file(query="Plugin 3.3kW Technical Specifications V3")

# Dig deeper only if needed
search_files(pattern="*Plugin*brochure*.pdf", target="files", path="~/Downloads")
search_files(pattern="*invoice*.pdf", target="files", path="~", limit=30)
```

## Filesystem Plan (emit once, then execute)

```text
Filesystem Plan
Need: <what to find or change>
Primary tool: locate_file (find intents) | search_files (coding / dig deeper)
Scope ladder: cwd → ~/Downloads|Desktop|Documents → ~ → / (only if needed)
File types: <pdf, xlsx, md, …>
Ranking: <locate confidence | newest mtime | version in name | exact title>
Shortlist size: <N, typically 1–5>
```

## Todo checklist

1. Commit filesystem plan
2. Locate candidates (`locate_file`, then escalate only if needed)
3. Rank / shortlist
4. Open top candidates (`read_file` / OCR skill if needed)
5. Compare or act
6. Verify result
7. Done

## Example reasoning

> "Find the latest Plugin charger brochure."

```text
Need brochure PDF → locate_file(query="Plugin charger brochure")
→ if empty, search_files under ~/Downloads|Desktop|Documents
→ rank by confidence/mtime → open top → return
```

## Final deliverable

1. Answer to the user request.
2. **Artifacts** — paths used, with one-line rationale.
3. Explicit gaps if budget ran out or files were missing.

## Do not

- Alternate raw `search_files` / `terminal` find-grep loops for a single find intent.
- Stay in `.` when the user clearly means files elsewhere on the machine.
- Start with full-disk `/` before trying home folders.
- Recursively open every match from a broad search.
- Use `terminal` `find`/`grep` when `locate_file` or `search_files` suffices.
- Keep exploring after verification succeeded.
