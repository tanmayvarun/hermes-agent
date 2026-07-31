"""Trace invariants for premature search-hypothesis advance (offline, no AX)."""

from __future__ import annotations

import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "premature_hyp_advance.jsonl"


def _load_events():
    if not FIXTURE.exists():
        return []
    return [json.loads(line) for line in FIXTURE.read_text().splitlines() if line.strip()]


def test_fixture_marks_promising_type_then_blocked_or_no_same_step_advance():
    """
    Synthetic trace: type_query → promising_unresolved must not be followed by
    empty_search_result_set advance on the same step.
    """
    events = _load_events()
    assert events, "fixture missing"
    by_step: dict = {}
    for e in events:
        step = e.get("step")
        by_step.setdefault(step, []).append(e)

    for step, evs in by_step.items():
        kinds = [e.get("kind") for e in evs]
        if "transition_eval" in kinds and "search_hypothesis_advance" in kinds:
            te = next(e for e in evs if e.get("kind") == "transition_eval")
            adv = next(e for e in evs if e.get("kind") == "search_hypothesis_advance")
            if te.get("outcome") == "promising_unresolved" and te.get("action_family") == "type_query":
                assert adv.get("trigger") != "empty_search_result_set", (
                    f"step {step}: advanced empty_search on promising type_query"
                )
        # Prefer seeing explicit block events in corrected controller traces
        for e in evs:
            if e.get("kind") == "search_hypothesis_advance":
                assert e.get("after_features", {}).get("resolution_policy") is not None or e.get(
                    "trigger"
                ) != "empty_search_result_set"


def test_live_bug_pattern_document():
    """Document the bad pattern that the fixture encodes for regression."""
    events = _load_events()
    type_then_advance = False
    for i, e in enumerate(events):
        if e.get("kind") == "transition_eval" and e.get("outcome") == "promising_unresolved":
            # Look ahead for advance with null policy (historical bug)
            for nxt in events[i : i + 5]:
                if nxt.get("kind") == "search_hypothesis_advance_blocked":
                    type_then_advance = False
                    break
                if (
                    nxt.get("kind") == "search_hypothesis_advance"
                    and nxt.get("trigger") == "empty_search_result_set"
                    and (nxt.get("after_features") or {}).get("resolution_policy") is None
                ):
                    type_then_advance = True
    # Fixture should include the corrected block event, not the bug
    assert type_then_advance is False
