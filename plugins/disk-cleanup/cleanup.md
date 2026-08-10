# cleanup.md — host relieve preferences

Edit this file under `$HERMES_HOME/cleanup.md` to control what
`relieve_host_storage` may reclaim when an app (e.g. WhatsApp) reports
storage pressure. Safer destinations run first; riskier ones never run
unless you explicitly enable them.

## Escalation ladder

Stages run in order and stop once the app-quoted free-space need (or
default headroom) is met:

1. `tracked` — Hermes-tracked disposables + empty dirs under HERMES_HOME
2. `host_temp` — `/tmp/hermes-*` and other known disposable temp prefixes
3. `host_cache` — recreatable roots under `~/Library/Caches` and Xcode caches
4. `app_caches` — **browser/app cache-style folders only** (see below)

Never auto-touched (even if listed under deny for clarity):

- `~/Downloads`
- Docker VM / image data
- Documents, Desktop, Photos libraries
- Browser profile databases (Cookies, Login Data, History, Bookmarks, IndexedDB)

## enabled

- tracked
- host_temp
- host_cache
- app_caches

## app_caches

Recreatable caches inside heavy apps. Prefer Chrome support *cache*
subfolders over wiping a whole profile.

allow:

- chrome
- chromium
- brave
- edge
- firefox

# Optional heavier caches (off by default — uncomment to enable):
# - slack
# - discord
# - spotify

deny:

- downloads
- docker
- documents
- photos
- indexeddb
- cookies
- history
- extensions
