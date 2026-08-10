"""Executive-calibration layer: were the executive's judgements any good?

The executive now records, every iteration, a `DecisionSufficiency` verdict and
a chosen meta-action (see ``executive_judgement`` events in the run log). The
other eval layers score perception; this one scores the *judgement* on top of
it, by correlating each verdict with what happened when the loop acted on it:

- sufficiency_precision       : when the executive said it was sufficient_to_act
                                and then acted, did the action land (ok +
                                non-regressive outcome)?
- act_success_rate            : of all ACT meta-actions, how many succeeded?
- meta_action_appropriateness : did the chosen meta-action match a simple
                                oracle (sufficient→act/verify, blocked→
                                perceive/probe/backtrack)?
- skip_safety                 : of the re-perceives the executive skipped (only
                                possible under HERMES_META_PERCEPTION), how many
                                were *not* followed by a surprising/failed
                                transition?

Like the temporal layer, this reads live run logs rather than replaying frames,
because the judgement is a property of the closed loop, not of a single frame.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

# Meta-actions that ask a question of the world (look-like), used to measure how
# efficiently the executive resolves its open questions.
_LOOK_ACTIONS = {"perceive", "explore"}

# Meta-actions that commit to the world rather than gather more evidence.
_ACT_LIKE = {"act"}
# Meta-actions that gather evidence rather than commit.
_LOOK_LIKE = {"perceive", "explore", "think", "ask", "wait", "delegate"}

# Transition outcomes (substring match) that mean the step did not cleanly
# advance: a skip or an "I can act" verdict in front of one of these is a
# calibration miss.
_BAD_OUTCOME_MARKERS = ("regress", "surprise", "fail", "block", "unexpected", "no_change")


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


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


def _bad_outcome(outcome: str) -> bool:
    outcome = _norm(outcome)
    return any(marker in outcome for marker in _BAD_OUTCOME_MARKERS)


@dataclass
class _Step:
    sufficient_to_act: bool = False
    meta_action: str = ""
    acted: bool = False
    execution_ok: bool = False
    outcome: str = ""
    skipped_perception: bool = False
    blocking: Tuple[str, ...] = ()
    world_changed: bool = False


@dataclass
class ExecutiveTrace:
    run: str
    judgements: int = 0
    act_calls: int = 0
    act_success: int = 0
    sufficient_acts: int = 0
    sufficient_act_success: int = 0
    meta_appropriate: int = 0
    skips: int = 0
    safe_skips: int = 0
    look_actions: int = 0
    redundant_reasks: int = 0
    distinct_questions: int = 0
    examples: List[str] = field(default_factory=list)

    @property
    def sufficiency_precision(self) -> float:
        if not self.sufficient_acts:
            return 1.0
        return round(self.sufficient_act_success / self.sufficient_acts, 4)

    @property
    def act_success_rate(self) -> float:
        if not self.act_calls:
            return 1.0
        return round(self.act_success / self.act_calls, 4)

    @property
    def meta_action_appropriateness(self) -> float:
        if not self.judgements:
            return 1.0
        return round(self.meta_appropriate / self.judgements, 4)

    @property
    def skip_safety(self) -> float:
        if not self.skips:
            return 1.0
        return round(self.safe_skips / self.skips, 4)

    @property
    def redundant_reask_rate(self) -> float:
        """Of all looks, how many re-asked a question already settled with no
        change since — the re-search failure the executive is meant to end."""
        if not self.look_actions:
            return 0.0
        return round(self.redundant_reasks / self.look_actions, 4)

    @property
    def probes_per_question(self) -> float:
        """Looks spent per distinct open question. Ideally near 1; high means the
        executive keeps looking at the same unknown."""
        if not self.distinct_questions:
            return 0.0
        return round(self.look_actions / self.distinct_questions, 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run": self.run,
            "judgements": self.judgements,
            "sufficiency_precision": self.sufficiency_precision,
            "act_success_rate": self.act_success_rate,
            "meta_action_appropriateness": self.meta_action_appropriateness,
            "skip_safety": self.skip_safety,
            "redundant_reask_rate": self.redundant_reask_rate,
            "probes_per_question": self.probes_per_question,
            "skips": self.skips,
            "examples": self.examples[:6],
        }


def _oracle_ok(step: _Step) -> bool:
    """Cheap ground truth for whether the meta-action was reasonable.

    Not a full policy — just the two clear cases: a sufficient verdict should
    lead to an act/verify, and a step that ends in a bad outcome should have
    been a look (perceive/probe/backtrack), not a blind act.
    """
    meta = _norm(step.meta_action)
    if step.sufficient_to_act:
        return meta in _ACT_LIKE
    return meta in _LOOK_LIKE


def analyse_executive(path: str | Path) -> ExecutiveTrace:
    """Correlate each recorded judgement with what the loop then did."""
    file = Path(path)
    trace = ExecutiveTrace(run=file.stem)
    steps: Dict[int, _Step] = {}

    def slot(step_key: Any) -> _Step:
        try:
            key = int(step_key)
        except (TypeError, ValueError):
            key = 0
        return steps.setdefault(key, _Step())

    for record in _records(file):
        kind = str(record.get("kind") or "")
        step = slot(record.get("step"))

        if kind == "executive_judgement":
            suff = record.get("sufficiency") or {}
            meta = record.get("meta_action") or {}
            step.sufficient_to_act = bool(suff.get("sufficient_to_act"))
            step.meta_action = _norm(meta.get("action"))
            step.blocking = tuple(
                _norm(item) for item in (suff.get("blocking_uncertainties") or []) if _norm(item)
            )
        elif kind == "perception_skipped":
            step.skipped_perception = True
        elif kind == "execution":
            step.acted = True
            step.execution_ok = bool(record.get("ok"))
        elif kind == "transition_eval":
            attempt = record.get("attempt") or {}
            step.outcome = _norm(attempt.get("outcome"))
            step.world_changed = _norm(attempt.get("outcome")) not in ("", "no_change")

    # Question-resolution efficiency: walk the steps in order, and count a look
    # as redundant when it re-asks the same blocking-uncertainty set as the last
    # look while the world has not changed in between.
    seen_questions: set = set()
    last_look_blocking: Tuple[str, ...] = ()
    world_moved_since_look = True
    for key in sorted(steps):
        step = steps[key]
        seen_questions.update(step.blocking)
        # The look decision is made *before* this step's outcome lands, so it is
        # judged against whether the world moved on prior steps.
        if _norm(step.meta_action) in _LOOK_ACTIONS:
            trace.look_actions += 1
            if step.blocking and step.blocking == last_look_blocking and not world_moved_since_look:
                trace.redundant_reasks += 1
                trace.examples.append(
                    f"step {key}: re-asked {list(step.blocking)[:2]} with no change since last look"
                )
            last_look_blocking = step.blocking or last_look_blocking
            world_moved_since_look = False
        # This step's outcome is what changed (or did not) before the next look.
        if step.world_changed:
            world_moved_since_look = True
    trace.distinct_questions = len(seen_questions)

    for key in sorted(steps):
        step = steps[key]
        if not step.meta_action and not step.acted and not step.skipped_perception:
            continue
        if step.meta_action:
            trace.judgements += 1
            if _oracle_ok(step):
                trace.meta_appropriate += 1
            else:
                trace.examples.append(
                    f"step {key}: sufficient={step.sufficient_to_act} meta={step.meta_action} "
                    f"outcome={step.outcome or 'n/a'}"
                )

        landed = step.execution_ok and not _bad_outcome(step.outcome)

        if step.meta_action in _ACT_LIKE:
            trace.act_calls += 1
            if landed:
                trace.act_success += 1

        if step.sufficient_to_act and step.acted:
            trace.sufficient_acts += 1
            if landed:
                trace.sufficient_act_success += 1

        if step.skipped_perception:
            trace.skips += 1
            # A skip is safe when the step it fronted did not end in a surprise
            # or failure (an unchanged, advancing world is exactly when skipping
            # a re-perceive is the right call).
            if not step.acted or landed or not step.outcome:
                trace.safe_skips += 1
            else:
                trace.examples.append(f"step {key}: skipped perceive then outcome={step.outcome}")

    return trace


def analyse_executive_runs(paths: Sequence[str | Path]) -> List[ExecutiveTrace]:
    return [analyse_executive(path) for path in paths]


def summarize_executive(traces: Sequence[ExecutiveTrace]) -> Dict[str, Any]:
    total = len(traces)
    if not total:
        return {"runs": 0}

    def _mean(getter) -> float:
        return round(sum(getter(t) for t in traces) / total, 4)

    return {
        "runs": total,
        "judgements": sum(t.judgements for t in traces),
        "sufficiency_precision": _mean(lambda t: t.sufficiency_precision),
        "act_success_rate": _mean(lambda t: t.act_success_rate),
        "meta_action_appropriateness": _mean(lambda t: t.meta_action_appropriateness),
        "skip_safety": _mean(lambda t: t.skip_safety),
        "redundant_reask_rate": _mean(lambda t: t.redundant_reask_rate),
        "probes_per_question": _mean(lambda t: t.probes_per_question),
        "runs_detail": [t.to_dict() for t in traces],
    }
