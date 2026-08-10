# disk-cleanup

Auto-tracks and cleans up ephemeral files created during Hermes Agent
sessions — test scripts, temp outputs, cron logs, and (on storage pressure)
staged host/app caches. Hermes-owned disposables stay under `$HERMES_HOME`
and `/tmp/hermes-*`; the relieve ladder can also clear recreatable browser
cache folders per user preferences in `$HERMES_HOME/cleanup.md`.

Originally contributed by [@LVT382009](https://github.com/LVT382009) as a
skill in PR #12212.  Ported to the plugin system so the behaviour runs
automatically via `post_tool_call` and `on_session_end` hooks — the agent
never needs to remember to call a tool.

## How it works

| Hook | Behaviour |
|---|---|
| `post_tool_call` | When `write_file` / `terminal` / `patch` creates a file matching `test_*`, `tmp_*`, or `*.test.*` inside `HERMES_HOME`, track it silently as `test` / `temp` / `cron-output`. |
| `on_session_end` | If any test files were auto-tracked during this turn, run `quick` cleanup (no prompts). |

Deletion rules (same as the original PR):

| Category | Threshold | Confirmation |
|---|---|---|
| `test` | every session end | Never |
| `temp` | >7 days since tracked | Never |
| `cron-output` | >14 days since tracked | Never |
| empty dirs under HERMES_HOME | always | Never |
| `research` | >30 days, beyond 10 newest | Always (deep only) |
| `chrome-profile` | >14 days since tracked | Always (deep only) |
| files >500 MB | never auto | Always (deep only) |

## Slash command

```
/disk-cleanup status                     # breakdown + top-10 largest
/disk-cleanup dry-run                    # preview without deleting
/disk-cleanup quick                      # run safe cleanup now
/disk-cleanup deep                       # quick + list items needing prompt
/disk-cleanup track <path> <category>    # manual tracking
/disk-cleanup forget <path>              # stop tracking
```

## Relieving storage pressure (`relieve_host_storage`)

When an app reports "storage is too full", cleanup runs an escalation ladder
and stops once the quoted free-space need is met:

1. Hermes tracked disposables
2. Host temp (`/tmp/hermes-*`, live-run artifacts)
3. Host caches (`~/Library/Caches`, Xcode derived data)
4. **App caches** — Chrome/Brave/Edge/Firefox *cache-style* folders only
   (e.g. `Service Worker`, `GPUCache`, `Code Cache`). Never Downloads,
   Docker, Documents, Cookies, History, IndexedDB, or Extensions.

Preferences live in **`$HERMES_HOME/cleanup.md`** (seeded from this plugin's
`cleanup.md` on first use). Edit that file to enable/disable stages or
allow/deny apps (Slack/Discord/Spotify stay off until uncommented).

## Safety

- `is_safe_path()` rejects anything outside `HERMES_HOME` or `/tmp/hermes-*`
  for tracked Hermès disposables; host/app cache stages use explicit allowlists
- Windows mounts (`/mnt/c` etc.) are rejected
- The state directory `$HERMES_HOME/disk-cleanup/` is itself excluded
- `$HERMES_HOME/logs/`, `memories/`, `sessions/`, `skills/`, `plugins/`,
  `cleanup.md`, and config files are never tracked
- Backup/restore is scoped to `tracked.json` — the plugin never touches
  agent logs
- Atomic writes: `.tmp` → backup → rename
