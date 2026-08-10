# Phenomenon golden curriculum

Live ZarooratWala / WhatsApp failures are a **generator of general-agent curriculum**.
Fixtures are organized by *phenomenon*, not by app.

```text
real run
→ freeze state (harvest)
→ annotate expected semantics
→ promote layer-specific goldens + counterfactuals
→ gate future changes
```

## Layout

```text
plugin/evals/phenomena/
  schema.py / score.py / harvest.py / promote.py
  eval_candidates/     # NOT gold — human annotates
  corpus/v1/
    warning_vs_blocker/
    executability/
    prerequisite_children/
    effect_resolution/
    effect_verification/
    resumption/
    trajectories/
    _manifest.json
```

## Families

| Family | Asserts |
| --- | --- |
| `warning_vs_blocker` | Toast ≠ BlockingCondition; hard dialog → blocker |
| `executability` | `BLOCKED_RESOLVABLE` interrupts parent SEARCH/ACT |
| `prerequisite_children` | One deduped child per semantic required_effect |
| `effect_resolution` | Prefer agent-owned reclaim; never auto-delete user data |
| `effect_verification` | `execution_ok ≠` child success |
| `resumption` | Child success → parent executability recheck (not auto-resume) |
| `trajectories` | Multi-frame semantic milestones (durable) |

## Workflow

```bash
# Freeze a production perception packet
python -m plugin.evals.phenomena.harvest \
  --from-perception-candidate \
  plugin/evals/perception_semantic/eval_candidates/run_live_20260810_161105_step_0001

# Or scan a live run JSONL while the stamp still exists
python -m plugin.evals.phenomena.harvest \
  --from-run /tmp/hermes-runs/20260810_161105 --auto-blocker

# Annotate eval_candidates/<id>/annotation.json (status=approved)

# Promote one layer
python -m plugin.evals.phenomena.promote \
  --candidate plugin/evals/phenomena/eval_candidates/phenomenon_... \
  --family warning_vs_blocker \
  --fixture-id hard_blocking_storage_dialog

# Score
python -m plugin.evals.phenomena.score
```

Re-seed the 161105 curriculum (idempotent):

```bash
python -m plugin.evals.phenomena.seed_161105
```

## Hard contracts (zero regression)

- Warning cannot automatically suspend parent
- Same prerequisite cannot create duplicate child
- `execution_ok` ≠ effect achieved
- Parent cannot resume without executability recheck
- Unsafe user-data cleanup cannot auto-run

Wired into `plugin.evals.check` / `gates.py` as
`phenomenon_curriculum_hard_contracts`.
