# Task Controller

Universal execution discipline for Hermes domain controllers (research,
filesystem, coding, …). Budgets and stop conditions are enforced in hooks;
skills only supply domain procedure.

## Enable

```bash
hermes plugins enable task-controller
```

```yaml
plugins:
  enabled:
    - task-controller
  entries:
    task-controller:
      budgets:
        web_search: 5
        web_extract: 4
        locate_file: 2
        search_files: 15
        read_file: 40
        write_file: 20
        patch: 20
        terminal: 30
        browser_navigate: 8
        tool_calls: 60
      auto_dispatch_locate: true   # Task Controller → LocateFileCapability
```

Set `TASK_CONTROLLER_AUTO_LOCATE=0` to disable locate auto-dispatch.

Legacy flat keys `max_web_search` / `max_web_extract` still work.

## Env overrides

| Variable | Default | Meaning |
|----------|---------|---------|
| `TASK_CONTROLLER_MAX_WEB_SEARCH` | 5 | Cap per user turn |
| `TASK_CONTROLLER_MAX_WEB_EXTRACT` | 4 | Cap per user turn |
| `TASK_CONTROLLER_MAX_TOOL_CALLS` | 60 | Global tool-call backstop |
| `TASK_CONTROLLER_DISABLE` | off | Disable the plugin |

## Domain skills

| Skill | Role |
|-------|------|
| `web-research` | Research Controller |
| `filesystem-workspace` | Filesystem Controller |
