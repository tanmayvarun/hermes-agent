from __future__ import annotations

from plugin.agent.transition.types import BranchStrategy
from plugin.experiments.strategic_search_rescue_eval import build_default_cases, run_strategic_search_rescue_eval


def test_strategic_search_rescue_eval_scores_rescue_strategy_with_precision_recall():
    cases = build_default_cases()

    def invoker(case):
        if case.case_id == "search_results_stalled_open_row":
            return BranchStrategy(
                strategy_id="case-1",
                preferred_family="open_contact",
                backtrack_family="type_query",
                avoid_families=["observe"],
                branch_hypothesis="open the source row instead of staying on the search loop",
                expected_surface="conversation",
                confidence=0.93,
                reason="search branch stalled; open the visible row",
            ), {"case_id": case.case_id}
        if case.case_id == "detail_panel_dead_end_refine_search":
            return BranchStrategy(
                strategy_id="case-2",
                preferred_family="type_query",
                backtrack_family="open_contact",
                avoid_families=["observe"],
                branch_hypothesis="refine the query rather than re-reading the detail panel",
                expected_surface="search_results",
                confidence=0.91,
                reason="detail panel is a dead end",
            ), {"case_id": case.case_id}
        if case.case_id == "false_call_chrome_backtrack_to_search":
            return BranchStrategy(
                strategy_id="case-3",
                preferred_family="dismiss",
                backtrack_family="type_query",
                avoid_families=["observe"],
                branch_hypothesis="call chrome is false and should be dismissed",
                expected_surface="search_results",
                confidence=0.89,
                reason="dismiss false positive call chrome",
            ), {"case_id": case.case_id}
        if case.case_id == "timeline_visible_open_source_message":
            return BranchStrategy(
                strategy_id="case-4",
                preferred_family="select_content",
                backtrack_family="type_query",
                avoid_families=["observe"],
                branch_hypothesis="source message is already visible and should be selected",
                expected_surface="conversation",
                confidence=0.95,
                reason="open the visible source message",
            ), {"case_id": case.case_id}
        return BranchStrategy(
            strategy_id="case-5",
            preferred_family="type_query",
            backtrack_family="open_contact",
            avoid_families=["observe"],
            branch_hypothesis="refine the search query to escape the stalled loop",
            expected_surface="search_results",
            confidence=0.9,
            reason="refine stalled search",
        ), {"case_id": case.case_id}

    summary = run_strategic_search_rescue_eval(cases, invoker=invoker)

    assert summary.case_count == len(cases)
    assert summary.preferred_family_accuracy == 1.0
    assert summary.backtrack_family_accuracy == 1.0
    assert summary.avoid_micro_precision == 1.0
    assert summary.avoid_micro_recall == 1.0
    assert summary.avoid_micro_f1 == 1.0
    assert summary.branch_hypothesis_match_rate > 0.5
    assert summary.expected_surface_match_rate == 1.0
    assert summary.mean_overall_score > 0.9
    assert all(case.expected_avoid_families == ["observe"] for case in cases)


def test_strategic_search_rescue_eval_penalizes_observe_thrash():
    cases = build_default_cases()[:1]

    def invoker(case):
        return BranchStrategy(
            strategy_id="bad",
            preferred_family="observe",
            backtrack_family="observe",
            avoid_families=[],
            branch_hypothesis="keep looking at the same stalled surface",
            expected_surface="search_results",
            confidence=0.2,
            reason="thrash on observe",
        ), {"case_id": case.case_id}

    summary = run_strategic_search_rescue_eval(cases, invoker=invoker)

    assert summary.preferred_family_accuracy == 0.0
    assert summary.backtrack_family_accuracy == 0.0
    assert summary.avoid_micro_f1 == 0.0
    assert summary.mean_overall_score < 0.5
