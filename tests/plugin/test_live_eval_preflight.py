"""Live agent startup must be precluded by a green package eval check."""

from __future__ import annotations

import pytest

import plugin.evals.check as check_mod


@pytest.fixture(autouse=True)
def _reset_preflight_state(monkeypatch):
    monkeypatch.delenv("HERMES_LIVE_GOAL", raising=False)
    monkeypatch.delenv("HERMES_EVAL_PREFLIGHT_DONE", raising=False)
    check_mod._EVAL_CHECK_PASSED_THIS_PROCESS = False
    yield
    check_mod._EVAL_CHECK_PASSED_THIS_PROCESS = False


def test_require_eval_check_exits_when_check_fails(monkeypatch):
    monkeypatch.setattr(check_mod, "run_check", lambda quick=False: 1)
    with pytest.raises(SystemExit) as ei:
        check_mod.require_eval_check_or_exit(reason="unit")
    assert ei.value.code == 1
    assert check_mod._EVAL_CHECK_PASSED_THIS_PROCESS is False


def test_require_eval_check_caches_success(monkeypatch):
    calls = {"n": 0}

    def _ok(quick=False):
        calls["n"] += 1
        return 0

    monkeypatch.setattr(check_mod, "run_check", _ok)
    check_mod.require_eval_check_or_exit(reason="unit")
    check_mod.require_eval_check_or_exit(reason="unit again")
    assert calls["n"] == 1
    assert check_mod._EVAL_CHECK_PASSED_THIS_PROCESS is True


def test_launcher_preflight_done_skips_rerun(monkeypatch):
    monkeypatch.setenv("HERMES_EVAL_PREFLIGHT_DONE", "1")
    monkeypatch.setattr(
        check_mod,
        "run_check",
        lambda quick=False: (_ for _ in ()).throw(AssertionError("should not run")),
    )
    check_mod.require_eval_check_or_exit(reason="unit")
    assert check_mod._EVAL_CHECK_PASSED_THIS_PROCESS is True


def test_closed_loop_live_flag_requires_preflight(monkeypatch):
    monkeypatch.setenv("HERMES_LIVE_GOAL", "1")
    monkeypatch.setattr(check_mod, "run_check", lambda quick=False: 1)
    with pytest.raises(SystemExit):
        check_mod.require_live_eval_preflight()


def test_closed_loop_without_live_flag_is_noop(monkeypatch):
    monkeypatch.setattr(
        check_mod,
        "run_check",
        lambda quick=False: (_ for _ in ()).throw(AssertionError("should not run")),
    )
    check_mod.require_live_eval_preflight()
