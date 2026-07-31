# Task-Aware Model Routing

Hermes now has a central routing layer for selecting models by task family
instead of treating all model calls the same.

## Why this exists

The agent uses different kinds of models for different jobs:

- `chat_runtime` needs deep planning, synthesis, and strong instruction
  following.
- `computer_use` needs faster iterative loops and should stay in a smaller
  model band.

The router merges the currently active models from:

- authenticated provider catalogs
- self-hosted / plugin providers such as remote Ollama

and then ranks the candidates for the requested task.

## Current profiles

- `chat_runtime`
  - preferred floor: `100B`
  - prefers larger models
  - requires tool-call capability

- `computer_use`
  - preferred band: `14B..32B`
  - prefers smaller/faster models
  - requires tool-call capability

Relay/backstop providers that require browser login, such as ChatGPT or
Google-backed assistants, are not part of the direct model ranking above.
They belong to the separate assistant-relay fallback layer documented in
`docs/design/assistant-relay-backups.md`. That layer is only entered after the
primary model paths fail or fail quality checks.

## Central API

The code path lives in `hermes_cli/model_routing.py` and exposes:

- `get_task_profile(task)`
- `rank_task_models(task, ...)`
- `select_task_model_ids(task, ...)`
- `select_task_model_subset(task, ...)`

These helpers are intended to be reused by the runtime, picker, and any
future evaluation or benchmark harnesses that need task-specific routing.
