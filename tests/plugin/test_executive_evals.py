"""Executive-calibration eval layer over run logs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from plugin.evals.executive import (
    analyse_executive,
    summarize_executive,
)


def _write(tmp_path: Path, records: List[Dict[str, Any]]) -> Path:
    path = tmp_path / "run.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records))
    return path


def _judge(step: int, *, sufficient: bool, meta: str, blocking=None) -> Dict[str, Any]:
    return {
        "kind": "executive_judgement",
        "step": step,
        "sufficiency": {
            "sufficient_to_act": sufficient,
            "blocking_uncertainties": list(blocking or []),
        },
        "meta_action": {"action": meta},
    }


def _exec(step: int, ok: bool = True) -> Dict[str, Any]:
    return {"kind": "execution", "step": step, "ok": ok}


def _outcome(step: int, outcome: str) -> Dict[str, Any]:
    return {"kind": "transition_eval", "step": step, "attempt": {"outcome": outcome}}


def _skip(step: int) -> Dict[str, Any]:
    return {"kind": "perception_skipped", "step": step}


def test_a_well_calibrated_run_scores_high(tmp_path):
    path = _write(
        tmp_path,
        [
            _judge(1, sufficient=True, meta="act"),
            _exec(1, ok=True),
            _outcome(1, "advanced"),
            _judge(2, sufficient=True, meta="act"),
            _exec(2, ok=True),
            _outcome(2, "advanced"),
        ],
    )
    trace = analyse_executive(path)
    assert trace.judgements == 2
    assert trace.sufficiency_precision == 1.0
    assert trace.act_success_rate == 1.0
    assert trace.meta_action_appropriateness == 1.0


def test_acting_when_insufficient_hurts_appropriateness(tmp_path):
    path = _write(
        tmp_path,
        [
            _judge(1, sufficient=False, meta="act"),
            _exec(1, ok=True),
            _outcome(1, "surprise"),
        ],
    )
    trace = analyse_executive(path)
    # meta was ACT while not sufficient -> the oracle marks it inappropriate.
    assert trace.meta_action_appropriateness == 0.0
    assert trace.examples


def test_sufficient_verdict_that_leads_to_a_failed_action_lowers_precision(tmp_path):
    path = _write(
        tmp_path,
        [
            _judge(1, sufficient=True, meta="act"),
            _exec(1, ok=False),
            _outcome(1, "failed"),
        ],
    )
    trace = analyse_executive(path)
    assert trace.sufficient_acts == 1
    assert trace.sufficient_act_success == 0
    assert trace.sufficiency_precision == 0.0
    assert trace.act_success_rate == 0.0


def test_perceive_when_blocked_is_appropriate(tmp_path):
    path = _write(
        tmp_path,
        [
            _judge(1, sufficient=False, meta="perceive"),
        ],
    )
    trace = analyse_executive(path)
    assert trace.meta_action_appropriateness == 1.0


def test_a_skip_before_a_clean_step_is_safe(tmp_path):
    path = _write(
        tmp_path,
        [
            _judge(1, sufficient=True, meta="act"),
            _skip(1),
            _exec(1, ok=True),
            _outcome(1, "advanced"),
        ],
    )
    trace = analyse_executive(path)
    assert trace.skips == 1
    assert trace.skip_safety == 1.0


def test_a_skip_before_a_surprise_is_unsafe(tmp_path):
    path = _write(
        tmp_path,
        [
            _judge(1, sufficient=True, meta="act"),
            _skip(1),
            _exec(1, ok=True),
            _outcome(1, "surprise"),
        ],
    )
    trace = analyse_executive(path)
    assert trace.skips == 1
    assert trace.skip_safety == 0.0
    assert trace.examples


def test_re_asking_a_settled_question_with_no_change_is_redundant(tmp_path):
    path = _write(
        tmp_path,
        [
            _judge(1, sufficient=False, meta="perceive", blocking=["source unresolved"]),
            _outcome(1, "no_change"),
            _judge(2, sufficient=False, meta="perceive", blocking=["source unresolved"]),
            _outcome(2, "no_change"),
        ],
    )
    trace = analyse_executive(path)
    assert trace.look_actions == 2
    assert trace.redundant_reasks == 1  # the second look re-asked with no change
    assert trace.redundant_reask_rate == 0.5
    assert trace.distinct_questions == 1


def test_a_look_after_the_world_changed_is_not_redundant(tmp_path):
    path = _write(
        tmp_path,
        [
            _judge(1, sufficient=False, meta="perceive", blocking=["source unresolved"]),
            _outcome(1, "advanced"),
            _judge(2, sufficient=False, meta="perceive", blocking=["source unresolved"]),
            _outcome(2, "no_change"),
        ],
    )
    trace = analyse_executive(path)
    assert trace.redundant_reasks == 0
    assert trace.redundant_reask_rate == 0.0


def test_empty_run_is_neutral(tmp_path):
    path = _write(tmp_path, [{"kind": "observation", "step": 1}])
    trace = analyse_executive(path)
    assert trace.judgements == 0
    assert trace.sufficiency_precision == 1.0
    assert trace.skip_safety == 1.0


def _mk(tmp_path: Path, name: str, records: List[Dict[str, Any]]) -> Path:
    path = tmp_path / f"{name}.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records))
    return path


def test_summary_aggregates_runs(tmp_path):
    good = analyse_executive(
        _mk(tmp_path, "good", [_judge(1, sufficient=True, meta="act"), _exec(1, True), _outcome(1, "advanced")])
    )
    bad = analyse_executive(
        _mk(tmp_path, "bad", [_judge(1, sufficient=False, meta="act"), _exec(1, True), _outcome(1, "surprise")])
    )
    summary = summarize_executive([good, bad])
    assert summary["runs"] == 2
    assert summary["judgements"] == 2
    assert 0.0 <= summary["meta_action_appropriateness"] <= 1.0
    assert summary["runs_detail"]
