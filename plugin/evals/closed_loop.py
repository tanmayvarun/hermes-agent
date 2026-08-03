"""Level 4: did the run finish the job, and where did it stop if not.

An aggregate completion rate hides stage-specific regressions -- a change that
opens the source chat twice as reliably and then never finds the message looks
flat. So completion is broken into the stages of the forward, and a run is
credited with the furthest stage it reached.

Input is the run's own JSONL log rather than a re-execution: these are live
macOS runs against a real WhatsApp, and replaying them is not something an
offline eval can do honestly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

# In order. A run reaching stage n is credited with every stage before it.
STAGES: Sequence[str] = (
    "opened_correct_conversation",
    "found_target_object",
    "opened_forward_surface",
    "selected_destination",
    "committed_send",
    "verified_completion",
)


@dataclass
class RunOutcome:
    run: str
    stages: Dict[str, bool] = field(default_factory=dict)
    steps: int = 0
    model_calls: int = 0
    failed_actions: int = 0
    replans: int = 0
    completed: bool = False
    # Stage flags before the ladder was enforced, kept so a signal that fires
    # out of order is visible rather than merely discarded.
    claimed_stages: Dict[str, bool] = field(default_factory=dict)
    # A run that declared success without the verifier agreeing. This is the
    # number that must never rise: a false success is worse than a failure,
    # because nothing downstream goes looking for the message that never sent.
    false_success: bool = False
    reason: str = ""

    @property
    def furthest_stage(self) -> str:
        reached = ""
        for stage in STAGES:
            if self.stages.get(stage):
                reached = stage
            else:
                break
        return reached

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run": self.run,
            "stages": {stage: bool(self.stages.get(stage)) for stage in STAGES},
            "claimed_stages": {stage: bool(self.claimed_stages.get(stage)) for stage in STAGES},
            "furthest_stage": self.furthest_stage,
            "steps": self.steps,
            "model_calls": self.model_calls,
            "failed_actions": self.failed_actions,
            "replans": self.replans,
            "completed": self.completed,
            "false_success": self.false_success,
            "reason": self.reason[:200],
        }


def _records(path: Path) -> Iterable[Dict[str, Any]]:
    try:
        with path.open() as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        return


def analyse_run(path: str | Path, *, destination: str = "", source: str = "", query: str = "") -> RunOutcome:
    """Reconstruct how far one run got from what it logged."""
    file = Path(path)
    outcome = RunOutcome(run=file.stem)
    source = source.lower()
    destination = destination.lower()
    query = query.lower()
    verified = False
    claimed = False

    for record in _records(file):
        kind = str(record.get("kind") or "")
        if kind == "whatsapp_forward_message":
            source = source or str(record.get("source_contact") or "").lower()
            destination = destination or str(record.get("target_contact") or "").lower()
            query = query or str(record.get("link_query") or "").lower()
        elif kind == "step":
            outcome.steps += 1
        elif kind == "decision_engine":
            outcome.model_calls += 1
        elif kind in {"no_progress_replan", "semantic_repeat_replan"}:
            outcome.replans += 1
        elif kind == "execution":
            if record.get("ok") is False:
                outcome.failed_actions += 1
            step = record.get("plan_step") or {}
            family = str(step.get("action_family") or "").lower()
            text = str(step.get("text") or "").lower()
            target = str(step.get("semantic_target") or "").lower()
            if family == "commit_irreversible" or text in {"send"}:
                outcome.stages["committed_send"] = True
            if destination and family in {"resolve_entity", "open_entity", "select_forward_target"}:
                if destination in text or destination in target:
                    outcome.stages["selected_destination"] = True
        elif kind in {"post_world_patch", "post_transition_settled_view", "observation_fused"}:
            open_now = str(record.get("open_conversation") or "").lower()
            if source and open_now and source in open_now:
                outcome.stages["opened_correct_conversation"] = True
            # A stage is only reached when the screen says so. Crediting the
            # action that attempts it counts every failed right-click as
            # progress, which is how a stalled run looks half finished.
            screen = str(record.get("screen") or record.get("whatsapp_screen") or "").lower()
            if screen in {"context_menu", "message_menu", "forward_picker", "forward_dialog"}:
                outcome.stages["opened_forward_surface"] = True
        elif kind == "world_patch":
            for entity in record.get("entities") or []:
                if not isinstance(entity, dict):
                    continue
                if query and query in str(entity.get("label") or "").lower():
                    outcome.stages["found_target_object"] = True
        elif kind == "verification":
            if record.get("passed"):
                verified = True
        elif kind == "goal_status":
            if record.get("succeeded"):
                claimed = True
                outcome.reason = str(record.get("reason") or "")
        elif kind == "run_end":
            if record.get("ok"):
                claimed = True
            outcome.reason = outcome.reason or str(record.get("detail") or "")

    outcome.stages["verified_completion"] = verified and outcome.stages.get("committed_send", False)
    # Stages are a ladder, not a checklist. A destination cannot have been
    # chosen on a picker that never opened, so a later flag without its
    # predecessor is evidence the signal fired on an attempt rather than an
    # outcome, and crediting it would make a stalled run look half finished.
    outcome.claimed_stages = {s: bool(outcome.stages.get(s)) for s in STAGES}
    blocked = False
    for stage in STAGES:
        if blocked or not outcome.stages.get(stage):
            blocked = True
            outcome.stages[stage] = False
    outcome.completed = bool(outcome.stages.get("verified_completion"))
    outcome.false_success = bool(claimed and not outcome.completed)
    return outcome


def analyse_runs(paths: Sequence[str | Path], **kwargs: Any) -> List[RunOutcome]:
    return [analyse_run(path, **kwargs) for path in paths]


def summarize(outcomes: Sequence[RunOutcome]) -> Dict[str, Any]:
    """Completion broken down by stage, plus the cost of getting there."""
    total = len(outcomes)
    if not total:
        return {"runs": 0}
    reached = {stage: sum(1 for o in outcomes if o.stages.get(stage)) for stage in STAGES}
    completed = [o for o in outcomes if o.completed]
    steps = sorted(o.steps for o in completed) or sorted(o.steps for o in outcomes)
    return {
        "runs": total,
        "completion_rate": round(len(completed) / total, 4),
        "false_success_rate": round(sum(1 for o in outcomes if o.false_success) / total, 4),
        "stage_reach_rate": {k: round(v / total, 4) for k, v in reached.items()},
        "furthest_stage_counts": _counts(o.furthest_stage or "none" for o in outcomes),
        "median_steps": steps[len(steps) // 2] if steps else None,
        "mean_model_calls": round(sum(o.model_calls for o in outcomes) / total, 2),
        "mean_failed_actions": round(sum(o.failed_actions for o in outcomes) / total, 2),
        "mean_replans": round(sum(o.replans for o in outcomes) / total, 2),
    }


def _counts(values: Iterable[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def recent_runs(directory: str | Path, limit: int = 12) -> List[Path]:
    base = Path(directory)
    files = sorted(base.glob("forward_zarooratwala_live_*.jsonl"))
    return files[-limit:]
