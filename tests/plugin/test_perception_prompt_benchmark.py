from __future__ import annotations

import json

from plugin.experiments.perception_prompt_benchmark import (
    build_default_cases,
    run_perception_prompt_benchmark,
)
from plugin.experiments.model_benchmark import ModelCandidateSpec


def test_perception_prompt_benchmark_ranks_balanced_over_compact():
    candidates = [ModelCandidateSpec(name="qwen2.5:32b", provider="ollama-remote", model="qwen2.5:32b")]
    cases = build_default_cases()

    def invoker(candidate, case, shape):
        if shape == "compact" and case.case_id == "startup_search_entry":
            payload = {
                "screen_type": "list",
                "active_surface": "contact list",
                "likely_next_family": "click",
                "likely_next_target": "Pallavi",
                "likely_next_text": "",
                "confidence": 0.9,
                "avoid_families": [],
                "supporting_evidence": ["trimmed prompt drifted"],
                "contradictions": [],
                "needs_followup_observe": False,
            }
            return {"choices": [{"message": {"content": json.dumps(payload)}, "finish_reason": "length"}]}
        payload = {
            "screen_type": case.expected_screen_type or "list",
            "active_surface": case.expected_active_surface or "contact list",
            "likely_next_family": case.expected_family or "click",
            "likely_next_target": case.expected_target or "Kulvinder Ji",
            "likely_next_text": case.expected_text or "",
            "confidence": 0.95,
            "avoid_families": [],
            "supporting_evidence": ["balanced prompt retained key context"],
            "contradictions": [],
            "needs_followup_observe": False,
        }
        return {"choices": [{"message": {"content": json.dumps(payload)}, "finish_reason": "stop"}]}

    report = run_perception_prompt_benchmark(candidates, cases=cases, shapes=["compact", "balanced"], invoker=invoker)
    compact = next(item for item in report.shape_summaries if item.prompt_shape == "compact")
    balanced = next(item for item in report.shape_summaries if item.prompt_shape == "balanced")

    assert balanced.accuracy > compact.accuracy
    assert balanced.parseable_rate >= compact.parseable_rate
    assert balanced.complete_json_rate >= compact.complete_json_rate

    startup_compact = next(
        result
        for result in report.case_results
        if result.case_id == "startup_search_entry" and result.prompt_shape == "compact"
    )
    startup_balanced = next(
        result
        for result in report.case_results
        if result.case_id == "startup_search_entry" and result.prompt_shape == "balanced"
    )
    assert not startup_compact.target_match
    assert startup_balanced.target_match
