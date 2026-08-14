"""Tests for prompt-as-task TaskTracker."""

from __future__ import annotations

import time

from plugin.agent.runtime.task_tracker import (
    PHASE_EXECUTING,
    STATUS_COMPLETED,
    STATUS_WAITING_FOR_USER,
    TaskTracker,
    final_status_from_turn,
    reset_task_tracker_for_tests,
)


def test_tracker_start_phase_settle_duration():
    reset_task_tracker_for_tests()
    t = TaskTracker(throttle_s=0)
    events = []
    rec = t.start(
        task_request_id="abc123",
        session_id="sess1",
        prompt="send hi to pallavi on whatsapp",
        on_update=events.append,
    )
    assert rec.status == "running"
    assert rec.phase == "interpreting"
    assert events and events[-1]["task_request_id"] == "abc123"

    t.note_phase("abc123", PHASE_EXECUTING, on_update=events.append, force=True)
    assert t.get("abc123").phase == PHASE_EXECUTING

    time.sleep(0.02)
    settled = t.settle(
        "abc123",
        status=STATUS_WAITING_FOR_USER,
        summary="Needs link",
        on_update=events.append,
    )
    assert settled is not None
    assert settled.status == STATUS_WAITING_FOR_USER
    assert settled.duration_ms is not None and settled.duration_ms >= 0
    payload = t.complete_payload("abc123")
    assert payload["final_status"] == STATUS_WAITING_FOR_USER
    assert payload["duration_ms"] == settled.duration_ms


def test_final_status_from_turn_mapping():
    assert final_status_from_turn("waiting_for_user") == STATUS_WAITING_FOR_USER
    assert final_status_from_turn("failed") == "failed"
    assert final_status_from_turn("legacy_delegated") == STATUS_COMPLETED
    assert final_status_from_turn("completed", interrupted=True) == "interrupted"


def test_throttle_skips_rapid_phase_emits():
    reset_task_tracker_for_tests()
    t = TaskTracker(throttle_s=10.0)
    events = []
    t.start(task_request_id="t1", session_id="s", prompt="hi", on_update=events.append)
    n0 = len(events)
    t.note_phase("t1", "executing", on_update=events.append)
    # Throttled — no new event
    assert len(events) == n0
    t.note_phase("t1", "computer_use", on_update=events.append, force=True)
    assert len(events) == n0 + 1
