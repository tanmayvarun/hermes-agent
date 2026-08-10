"""Per-golden evals for zarooratwala perception-confirm failure corpus.

Every confirm golden gets multiple checks: golden scorer + direct actor execution
contract (status, backend, no motor, live reason fragments).
"""

from __future__ import annotations

import pytest

from plugin.agent.actor import (
    STALE_PRECONDITION,
    RecordingMotor,
    exec_backend_for_actor_result,
    execute_actor,
)
from plugin.evals.golden.schema import load_module_cases
from plugin.evals.golden.score import (
    _apply_perception_confirm_fixture,
    _brief_from_gold_input,
    score_actor_case,
)

_CONFIRM_CASES = [
    c for c in load_module_cases("actor") if "confirm" in c.id and "perception_confirm" in (c.input or {})
]


def _confirm_ids():
    return [c.id for c in _CONFIRM_CASES]


@pytest.mark.parametrize("case_id", _confirm_ids())
def test_perception_confirm_golden_score_passes(case_id: str):
    case = next(c for c in _CONFIRM_CASES if c.id == case_id)
    score = score_actor_case(case)
    assert score.passed, score.to_dict()
    # Multi-check coverage: every named gold field that was set must have a check.
    check_names = {c["name"] for c in score.checks}
    gold = case.gold or {}
    if gold.get("message_contains_all"):
        assert "message_contains_all" in check_names
        assert next(c for c in score.checks if c["name"] == "message_contains_all")["passed"]
    if gold.get("reason_contains_all"):
        assert next(c for c in score.checks if c["name"] == "reason_contains_all")["passed"]
    if gold.get("motor_must_be_empty"):
        assert next(c for c in score.checks if c["name"] == "motor_must_be_empty")["passed"]
    if gold.get("confirm_state"):
        assert next(c for c in score.checks if c["name"] == "confirm_state")["passed"]
    if gold.get("exec_backend"):
        assert next(c for c in score.checks if c["name"] == "exec_backend")["passed"]


@pytest.mark.parametrize("case_id", _confirm_ids())
def test_perception_confirm_golden_actor_refuses_without_motor(case_id: str):
    case = next(c for c in _CONFIRM_CASES if c.id == case_id)
    brief = _brief_from_gold_input(dict((case.input or {}).get("brief") or {}))
    motor = RecordingMotor()
    restore, _ = _apply_perception_confirm_fixture(case.input or {})
    try:
        outcome = execute_actor(brief, motor=motor)
    finally:
        if restore is not None:
            restore()

    assert not outcome.ok
    assert outcome.status == STALE_PRECONDITION
    assert exec_backend_for_actor_result(outcome) == STALE_PRECONDITION
    assert motor.calls == []
    assert "perception_invalid" in (outcome.message or "").lower()

    fixture = (case.input or {}).get("perception_confirm") or {}
    expect_state = str(fixture.get("state") or "")
    got = (outcome.evidence or {}).get("perception_confirm") or {}
    assert isinstance(got, dict)
    assert got.get("valid") is False
    if expect_state:
        assert str(got.get("state") or "") == expect_state

    # Live reason tokens must survive into the actor refusal message / evidence.
    for needle in (case.gold or {}).get("reason_contains_all") or []:
        blob = f"{outcome.message} {got.get('reason', '')}".lower()
        assert str(needle).lower() in blob, (case_id, needle, blob)


def test_all_four_zarooratwala_confirm_failure_goldens_present():
    ids = set(_confirm_ids())
    expected = {
        "actor/live_152420_confirm_focus_disturbed_wrong_ocr",
        "actor/live_153356_confirm_focus_disturbed_list_scrolled",
        "actor/live_041742_confirm_surface_lost_cursor_foreground",
        "actor/live_045430_confirm_invalid_empty_ocr_zarooratwala_row",
    }
    assert expected <= ids, f"missing {expected - ids}"


def test_152420_wrong_ocr_keeps_found_ala_token():
    case = next(c for c in _CONFIRM_CASES if "152420" in c.id)
    score = score_actor_case(case)
    assert score.passed, score.to_dict()
    brief = _brief_from_gold_input(dict(case.input["brief"]))
    motor = RecordingMotor()
    restore, _ = _apply_perception_confirm_fixture(case.input)
    try:
        out = execute_actor(brief, motor=motor)
    finally:
        restore()
    assert "ala" in out.message.lower()
    assert "zarooratwala" in (brief.label or "").lower()


def test_153356_list_scroll_refuses_singing_under_video_call_point():
    case = next(c for c in _CONFIRM_CASES if "153356" in c.id)
    score = score_actor_case(case)
    assert score.passed, score.to_dict()
    assert case.input["brief"]["point"] == [227, 387]
    restore, _ = _apply_perception_confirm_fixture(case.input)
    try:
        out = execute_actor(
            _brief_from_gold_input(case.input["brief"]), motor=RecordingMotor()
        )
    finally:
        restore()
    assert "gn singing" in out.message.lower()
    assert (out.evidence or {}).get("perception_confirm", {}).get("state") == "focus_disturbed"


def test_041742_cursor_interrupt_is_surface_lost():
    case = next(c for c in _CONFIRM_CASES if "041742" in c.id)
    score = score_actor_case(case)
    assert score.passed, score.to_dict()
    assert case.gold.get("confirm_state") == "surface_lost"
    restore, _ = _apply_perception_confirm_fixture(case.input)
    try:
        out = execute_actor(
            _brief_from_gold_input(case.input["brief"]), motor=RecordingMotor()
        )
    finally:
        restore()
    assert "cursor" in out.message.lower()
    assert (out.evidence or {}).get("perception_confirm", {}).get("state") == "surface_lost"


def test_045430_empty_ocr_zarooratwala_row_refuses():
    case = next(c for c in _CONFIRM_CASES if "045430" in c.id)
    score = score_actor_case(case)
    assert score.passed, score.to_dict()
    restore, _ = _apply_perception_confirm_fixture(case.input)
    try:
        out = execute_actor(
            _brief_from_gold_input(case.input["brief"]), motor=RecordingMotor()
        )
    finally:
        restore()
    assert "found no text" in out.message.lower()
    assert "zarooratwala.com link message" in (case.input["brief"].get("label") or "").lower()
