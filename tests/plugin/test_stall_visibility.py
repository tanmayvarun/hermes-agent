"""A run that is blocked must say what it is blocked on, while it is blocked.

The loop reports its cost per iteration, but only once the iteration ends, so
a call that hangs is invisible for exactly as long as it is the problem. These
cover the in-flight registry and the watchdog that reads it.
"""

from __future__ import annotations

import threading
import time

import pytest

from plugin.agent import controller
from plugin.agent.runtime import inflight


@pytest.fixture(autouse=True)
def _clean_registry():
    inflight.reset()
    yield
    inflight.reset()


class _RecordingLogger:
    """Minimal EventLogger stand-in that captures what the watchdog writes."""

    def __init__(self) -> None:
        self.records: list[dict] = []
        self._lock = threading.Lock()

    def log(self, kind, payload, *, status="ok", step=None):
        with self._lock:
            self.records.append({"kind": kind, "status": status, "step": step, **payload})
        return {}

    def stalled(self) -> list[dict]:
        with self._lock:
            return [r for r in self.records if r["kind"] == "stalled"]


def test_registry_reports_the_innermost_call_in_flight():
    assert inflight.current() is None
    with inflight.mark("reasoning:unified_cognition"):
        outer = inflight.current()
        assert outer is not None and outer[0] == "reasoning:unified_cognition"
        with inflight.mark("reasoning:content_object_resolution"):
            inner = inflight.current()
            assert inner is not None
            assert inner[0] == "reasoning:content_object_resolution"
        # The nested call finished; the outer one is still waiting.
        assert inflight.current()[0] == "reasoning:unified_cognition"
    assert inflight.current() is None


def test_registry_clears_the_entry_when_the_call_raises():
    with pytest.raises(RuntimeError):
        with inflight.mark("reasoning:boom"):
            raise RuntimeError("provider timed out")
    assert inflight.current() is None


def test_registry_reports_how_long_the_call_has_been_waiting():
    with inflight.mark("reasoning:slow"):
        time.sleep(0.05)
        label, waiting_s = inflight.current()
    assert label == "reasoning:slow"
    assert waiting_s >= 0.05


def test_watchdog_names_the_call_that_is_still_blocking(monkeypatch):
    monkeypatch.setattr(controller, "_STALL_POLL_S", 0.01)
    monkeypatch.setattr(controller, "_STALL_AFTER_S", 0.05)
    monkeypatch.setattr(controller, "_STALL_REPEAT_S", 0.05)

    log = _RecordingLogger()
    stop, thread = controller._start_stall_watchdog(log, {"iteration": 7})
    try:
        with inflight.mark("reasoning:content_object_resolution"):
            deadline = time.monotonic() + 3.0
            while not log.stalled() and time.monotonic() < deadline:
                time.sleep(0.01)
        stalls = log.stalled()
    finally:
        stop.set()
        if thread is not None:
            thread.join(timeout=2.0)

    assert stalls, "a call blocked past the threshold should be reported"
    first = stalls[0]
    assert first["in_flight"] == "reasoning:content_object_resolution"
    assert first["status"] == "warn"
    assert first["step"] == 7
    assert first["waiting_s"] >= 0.05


def test_watchdog_stays_quiet_when_nothing_is_blocked(monkeypatch):
    monkeypatch.setattr(controller, "_STALL_POLL_S", 0.01)
    monkeypatch.setattr(controller, "_STALL_AFTER_S", 0.05)

    log = _RecordingLogger()
    stop, thread = controller._start_stall_watchdog(log, {"iteration": 1})
    try:
        # A call that returns promptly is ordinary, not a stall.
        for _ in range(5):
            with inflight.mark("reasoning:fast"):
                pass
            time.sleep(0.01)
    finally:
        stop.set()
        if thread is not None:
            thread.join(timeout=2.0)

    assert log.stalled() == []


def test_watchdog_stops_reporting_once_the_run_ends(monkeypatch):
    monkeypatch.setattr(controller, "_STALL_POLL_S", 0.01)
    monkeypatch.setattr(controller, "_STALL_AFTER_S", 0.01)
    monkeypatch.setattr(controller, "_STALL_REPEAT_S", 0.01)

    log = _RecordingLogger()
    stop, thread = controller._start_stall_watchdog(log, {"iteration": 1})
    with inflight.mark("reasoning:hanging"):
        deadline = time.monotonic() + 3.0
        while not log.stalled() and time.monotonic() < deadline:
            time.sleep(0.01)
        stop.set()
        if thread is not None:
            thread.join(timeout=2.0)
        settled = len(log.stalled())
        # The call is still in flight, but the run is over: no more reports.
        time.sleep(0.1)
        assert len(log.stalled()) == settled


def test_watchdog_is_a_noop_without_a_logger():
    stop, thread = controller._start_stall_watchdog(None, {"iteration": 1})
    assert thread is None
    assert not stop.is_set()


def test_reasoning_consultations_register_themselves_as_in_flight():
    """The registry is only useful if the calls that stall actually mark
    themselves, so pin the wiring at the shared consultation boundary."""
    from plugin.agent.reasoning_consultation import consult_reasoning

    seen: list[str] = []

    def caller(**kwargs):  # noqa: ARG001
        active = inflight.current()
        seen.append(active[0] if active else "")
        raise RuntimeError("Request timed out.")

    with pytest.raises(RuntimeError):
        consult_reasoning(
            "content_object_resolution",
            [{"role": "user", "content": "which row?"}],
            caller=caller,
        )

    assert seen == ["reasoning:content_object_resolution"]
    # A call that blew up must not leave the loop looking permanently stalled.
    assert inflight.current() is None
