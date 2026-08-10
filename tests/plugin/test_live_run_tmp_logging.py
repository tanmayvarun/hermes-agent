"""Live forward logs go under /tmp/hermes-runs so relieve can reclaim them."""

from __future__ import annotations

import time
from pathlib import Path


def test_live_paths_prefer_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_LIVE_RUN_DIR", str(tmp_path / "hermes-runs"))
    from plugin.experiments.runs import live_paths as lp

    stamp = "20990101_000000"
    log = lp.forward_log_path(stamp)
    assert str(log).startswith(str(tmp_path / "hermes-runs"))
    assert log.name.startswith("forward_zarooratwala_live_")
    assert lp.ui_monitor_dir(stamp).name == "ui_monitor"


def test_host_temp_reclaims_stale_hermes_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_LIVE_RUN_DIR", str(tmp_path / "hermes-runs"))
    monkeypatch.setenv("HERMES_LIVE_RUN_KEEP_SECONDS", "120")
    root = tmp_path / "hermes-runs"
    stale = root / "oldstamp"
    fresh = root / "newstamp"
    stale.mkdir(parents=True)
    fresh.mkdir(parents=True)
    (stale / "forward_zarooratwala_live_oldstamp.jsonl").write_text("{}", encoding="utf-8")
    (fresh / "forward_zarooratwala_live_newstamp.jsonl").write_text("{}", encoding="utf-8")
    # Age the stale tree past the keep window.
    old = time.time() - 3600
    for p in (stale, stale / "forward_zarooratwala_live_oldstamp.jsonl"):
        Path(p).touch()
        import os

        os.utime(p, (old, old))

    from plugin.agent.runtime.recovery import _load_disk_cleanup_library

    lib = _load_disk_cleanup_library()
    monkeypatch.setattr(lib, "_resolve_host_temp_roots", lambda: [tmp_path])
    out = lib._cleanup_hermes_live_run_roots()
    assert out["deleted"] >= 1
    assert not stale.exists()
    assert fresh.exists()
