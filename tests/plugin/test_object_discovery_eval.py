from __future__ import annotations

from plugin.experiments.object_discovery_eval import build_synthetic_cases, run_object_discovery_eval


def test_object_discovery_eval_reports_precision_and_recall():
    summary = run_object_discovery_eval(use_llm=False, top_k=3)

    assert summary.case_count == len(build_synthetic_cases())
    assert summary.top_k == 3
    assert 0.0 <= summary.top1_accuracy <= 1.0
    assert 0.0 <= summary.micro_candidate_precision_at_k <= 1.0
    assert 0.0 <= summary.micro_candidate_recall_at_k <= 1.0
    assert 0.0 <= summary.micro_candidate_f1_at_k <= 1.0
    assert summary.top1_accuracy >= 0.5
    assert summary.micro_candidate_recall_at_k >= 0.5
    assert summary.cases
    assert any(case.candidate_recall_at_k > 0 for case in summary.cases)


def test_object_discovery_eval_case_filtering():
    cases = build_synthetic_cases()
    filtered = run_object_discovery_eval([cases[0]], use_llm=False, top_k=2)

    assert filtered.case_count == 1
    assert filtered.cases[0].case_id == cases[0].case_id
    assert filtered.top_k == 2
    assert filtered.cases[0].gold_entity_ids == cases[0].gold_entity_ids
