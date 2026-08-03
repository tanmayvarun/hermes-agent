"""Temporal-consistency eval layer over run logs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from plugin.evals.temporal import (
    analyse_temporal,
    summarize_temporal,
)


def _write(tmp_path: Path, records: List[Dict[str, Any]]) -> Path:
    path = tmp_path / "run.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records))
    return path


def _surface(screen: str, open_conv: str = "") -> Dict[str, Any]:
    return {"kind": "post_world_patch", "screen": screen, "open_conversation": open_conv}


def _phase(name: str) -> Dict[str, Any]:
    return {"kind": "forward_task", "forward_phase": name}


def test_a_steady_run_scores_perfectly(tmp_path):
    path = _write(
        tmp_path,
        [
            _surface("chat_list"),
            _surface("search_results"),
            _surface("conversation", "pallavi"),
            _surface("conversation", "pallavi"),
        ],
    )
    trace = analyse_temporal(path)
    assert trace.surface_stability == 1.0
    assert trace.belief_flip_rate == 0.0
    assert trace.object_identity_continuity == 1.0


def test_surface_oscillation_is_penalised(tmp_path):
    path = _write(
        tmp_path,
        [
            _surface("search_results"),
            _surface("conversation"),
            _surface("search_results"),  # A -> B -> A
        ],
    )
    trace = analyse_temporal(path)
    assert trace.surface_oscillations == 1
    assert trace.surface_stability < 1.0


def test_belief_that_reverts_is_a_flip(tmp_path):
    path = _write(
        tmp_path,
        [
            _surface("conversation", "pallavi"),
            _surface("conversation", "group thread"),
            _surface("conversation", "pallavi"),  # belief A -> B -> A
        ],
    )
    trace = analyse_temporal(path)
    assert trace.belief_flips == 1
    assert trace.belief_flip_rate > 0.0


def test_empty_open_conversation_is_not_a_belief_flip(tmp_path):
    path = _write(
        tmp_path,
        [
            _surface("conversation", "pallavi"),
            _surface("search_results", ""),  # unknown, not a claim
            _surface("conversation", "pallavi"),
        ],
    )
    trace = analyse_temporal(path)
    assert trace.belief_flips == 0


def test_an_id_relabelled_breaks_identity_continuity(tmp_path):
    path = _write(
        tmp_path,
        [
            {"kind": "world_patch", "entities": [{"id": 7, "label": "charger link"}]},
            {"kind": "world_patch", "entities": [{"id": 7, "label": "something else"}]},
        ],
    )
    trace = analyse_temporal(path)
    assert trace.identity_breaks == 1
    assert trace.object_identity_continuity < 1.0


def test_phase_regression_without_a_surface_change_is_unjustified(tmp_path):
    path = _write(
        tmp_path,
        [
            _surface("forward_picker"),
            _phase("pick_dest"),
            _surface("forward_picker"),  # same surface
            _phase("open_source"),  # slid all the way back with no screen change
        ],
    )
    trace = analyse_temporal(path)
    assert trace.unjustified_regressions == 1
    assert trace.unjustified_phase_regression_rate > 0.0


def test_phase_regression_with_a_surface_change_is_justified(tmp_path):
    path = _write(
        tmp_path,
        [
            _surface("forward_picker"),
            _phase("pick_dest"),
            _surface("chat_list"),  # the screen really did move back
            _phase("open_source"),
        ],
    )
    trace = analyse_temporal(path)
    assert trace.unjustified_regressions == 0


def test_forward_phase_advance_is_not_a_regression(tmp_path):
    path = _write(
        tmp_path,
        [
            _surface("chat_list"),
            _phase("open_source"),
            _surface("conversation"),
            _phase("find_link"),
        ],
    )
    trace = analyse_temporal(path)
    assert trace.unjustified_regressions == 0
    assert trace.phase_transitions == 1


def test_summary_averages_across_runs(tmp_path):
    steady = _write(tmp_path, [_surface("a"), _surface("a")])
    trace = analyse_temporal(steady)
    summary = summarize_temporal([trace, trace])
    assert summary["runs"] == 2
    assert summary["surface_stability"] == 1.0
    assert "runs_detail" in summary


def test_missing_file_yields_an_empty_trace(tmp_path):
    trace = analyse_temporal(tmp_path / "nope.jsonl")
    assert trace.frames == 0
    assert trace.surface_stability == 1.0
