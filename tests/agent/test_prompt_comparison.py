from __future__ import annotations

import json

from agent.prompt_comparison import (
    PromptComparisonCase,
    PromptComparisonReport,
    PromptVariantSpec,
    compare_prompt_variants,
)


def test_prompt_comparison_ranks_better_variant_higher():
    cases = [
        PromptComparisonCase(
            case_id="case-1",
            description="first case",
            input_payload={"goal": "find chat"},
            expected={"answer": "A"},
        ),
        PromptComparisonCase(
            case_id="case-2",
            description="second case",
            input_payload={"goal": "open source message"},
            expected={"answer": "B"},
        ),
    ]
    variants = [
        PromptVariantSpec(variant_id="compact", name="compact", user_prompt="You are a strict assistant."),
        PromptVariantSpec(variant_id="balanced", name="balanced", user_prompt="You are a strict assistant with more context."),
    ]

    def invoker(variant: PromptVariantSpec, case: PromptComparisonCase):
        if variant.variant_id == "compact" and case.case_id == "case-2":
            payload = {"answer": "A", "confidence": 0.5}
            return {"choices": [{"message": {"content": json.dumps(payload)}, "finish_reason": "stop"}]}
        payload = {"answer": case.expected["answer"], "confidence": 0.95}
        return {"choices": [{"message": {"content": json.dumps(payload)}, "finish_reason": "stop"}]}

    report: PromptComparisonReport = compare_prompt_variants(variants, cases, invoker)
    compact = next(item for item in report.summaries if item.variant_id == "compact")
    balanced = next(item for item in report.summaries if item.variant_id == "balanced")

    assert report.best_variant_id() == "balanced"
    assert balanced.accuracy > compact.accuracy
    assert balanced.avg_score > compact.avg_score
    assert report.comparison() is not None
    assert report.comparison().winner_variant_id == "balanced"

