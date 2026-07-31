from __future__ import annotations

from pathlib import Path

import pytest

from plugin.experiments import logger as logger_mod
from plugin.experiments.logger import EventLogger


def test_event_logger_emits_run_relative_clock(monkeypatch, tmp_path):
    wall_times = iter([1000.0, 1000.5, 1001.0, 1001.5, 1002.0, 1002.5])
    mono_times = iter([100.0, 100.5, 101.0, 101.5, 102.0, 102.5])

    monkeypatch.setattr(logger_mod.time, "time", lambda: next(wall_times))
    monkeypatch.setattr(logger_mod.time, "monotonic", lambda: next(mono_times))

    log = EventLogger(tmp_path / "run.jsonl", also_console=False)

    first = log.log("step", {"name": "one"}, step=1)
    assert first["run_elapsed_s"] == pytest.approx(0.5)
    assert first["run_elapsed_ms"] == 500

    log.begin_run("demo goal")
    records = log.read_all()
    assert records[-1]["kind"] == "run_start"
    assert records[-1]["run_elapsed_s"] == pytest.approx(0.0)
    assert records[-1]["run_elapsed_ms"] == 0
    assert records[-1]["run_started_at"] == 1001.5

    second = log.log("step", {"name": "two"}, step=2)
    assert second["run_elapsed_s"] == pytest.approx(0.5)
    assert second["run_elapsed_ms"] == 500

    out = Path(tmp_path / "run.jsonl")
    assert out.exists()
