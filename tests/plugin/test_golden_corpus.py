"""Module-layered golden corpus v1 (zarooratwala-seeded)."""

from __future__ import annotations

import pytest

from plugin.evals.golden.schema import (
    GOLDEN_MODULES,
    GoldenCase,
    load_all_cases,
    load_manifest,
    load_module_cases,
)
from plugin.evals.golden.score import (
    score_actor_case,
    score_all,
    score_brain_actor_handoff_case,
    score_brain_case,
    score_critic_case,
    score_flow_case,
    score_meta_action_case,
    score_perceive_case,
    score_reflect_case,
    score_ui_case,
    summarize_golden,
)
from plugin.evals.golden.harvest_run import harvest_runs, list_run_logs
from plugin.evals.corpus import DEFAULT_CORPUS_DIR, load_fixtures
from plugin.evals.annotations import annotate, load_overrides


def _score_case(case: GoldenCase):
    fixtures = annotate(load_fixtures(DEFAULT_CORPUS_DIR), overrides=load_overrides())
    by_id = {f.id: f for f in fixtures}
    if case.module == "perceive":
        return score_perceive_case(case, by_id)
    if case.module == "critic":
        return score_critic_case(case)
    if case.module == "meta_action":
        return score_meta_action_case(case)
    if case.module == "brain":
        return score_brain_case(case)
    if case.module == "actor":
        return score_actor_case(case)
    if case.module == "brain_actor_handoff":
        return score_brain_actor_handoff_case(case)
    if case.module == "reflect":
        return score_reflect_case(case)
    if case.module == "flow":
        return score_flow_case(case)
    if case.module == "ui":
        return score_ui_case(case)
    raise AssertionError(f"unknown module {case.module}")


def _blocking_cases():
    gaps = set(load_manifest().get("known_gap_case_ids") or [])
    cases = []
    for module_cases in load_all_cases().values():
        for case in module_cases:
            if case.id not in gaps:
                cases.append(case)
    return cases


def test_manifest_and_modules_load():
    manifest = load_manifest()
    assert manifest.get("version") == "v1"
    assert manifest.get("frozen") is True
    assert manifest.get("eval_only") is True
    cases = load_all_cases()
    assert set(cases) == set(GOLDEN_MODULES)
    for module in GOLDEN_MODULES:
        assert len(cases[module]) >= 1, module
        assert manifest["modules"][module] == len(cases[module])


def test_critic_ax_chrome_case_passes():
    cases = load_module_cases("critic")
    trap = next(c for c in cases if "q_search" in c.id)
    score = score_critic_case(trap)
    assert score.passed, score.to_dict()


def test_brain_locate_after_open_passes():
    cases = load_module_cases("brain")
    hunt = next(c for c in cases if "locate" in c.id)
    score = score_brain_case(hunt)
    assert score.passed, score.to_dict()


def test_meta_surprise_is_reflect_not_verify():
    cases = load_module_cases("meta_action")
    case = next(c for c in cases if "surprise_is_reflect" in c.id or "needs_reflect" in c.id)
    score = score_meta_action_case(case)
    assert score.passed, score.to_dict()


def test_actor_refuse_picker_type_without_geometry():
    cases = load_module_cases("actor")
    case = next(c for c in cases if "without_geometry" in c.id)
    score = score_actor_case(case)
    assert score.passed, score.to_dict()


def test_brain_actor_handoff_picker_destination_filter():
    cases = load_module_cases("brain_actor_handoff")
    case = next(c for c in cases if "destination_filter" in c.id)
    score = score_brain_actor_handoff_case(case)
    assert score.passed, score.to_dict()


def test_live_132948_actuation_handoff_recovers_filter_point():
    """Perceptor had picker Search geometry; actuation used Cmd+F — handoff must bind point."""
    cases = load_module_cases("brain_actor_handoff")
    case = next(c for c in cases if "132948" in c.id and "recover_filter" in c.id)
    score = score_brain_actor_handoff_case(case)
    assert score.passed, score.to_dict()


def test_live_135732_actor_lands_brain_point_not_sidebar():
    """Brain point [1360,295]; live motor hit sidebar ~(199,242). Actor must use brain point."""
    cases = load_module_cases("actor")
    case = next(c for c in cases if "135732" in c.id)
    score = score_actor_case(case)
    assert score.passed, score.to_dict()


def test_live_011358_perceptor_brain_actor_keeps_pallavi_row():
    """Pipeline: fresh chat_row@[167,175] must survive brain over stale doc; not Ather."""
    cases = load_module_cases("brain_actor_handoff")
    case = next(c for c in cases if "011358" in c.id and "perceptor_brain_actor" in c.id)
    score = score_brain_actor_handoff_case(case)
    assert score.passed, score.to_dict()


def test_reflect_discovery_geometry_mismatch():
    """Packet must expose intended vs landed so wrong_target can be discovered."""
    cases = load_module_cases("reflect")
    case = next(c for c in cases if "discovery_inputs_geometry_mismatch" in c.id)
    score = score_reflect_case(case)
    assert score.passed, score.to_dict()


def test_reflect_brain_consumes_corrected_point():
    """Consumption-only: authoritative corrected_point re-grounds (not discovery)."""
    cases = load_module_cases("reflect")
    case = next(c for c in cases if "brain_consumes_corrected_point" in c.id)
    score = score_reflect_case(case)
    assert score.passed, score.to_dict()


def test_reflect_brain_consumes_block_repeat():
    cases = load_module_cases("reflect")
    case = next(c for c in cases if "brain_consumes_wrong_target_blocks_repeat" in c.id)
    score = score_reflect_case(case)
    assert score.passed, score.to_dict()


def test_live_145239_reflect_diagnosis_seed_partial_transition():
    """Background AXPress Forward → selection chrome; seed must follow toolbar Forward."""
    cases = load_module_cases("reflect")
    case = next(c for c in cases if "145239" in c.id and "partial_transition" in c.id)
    score = score_reflect_case(case)
    assert score.passed, score.to_dict()


def test_live_145239_brain_overrides_observe_with_toolbar_forward():
    cases = load_module_cases("reflect")
    case = next(c for c in cases if "145239" in c.id and "overrides_observe" in c.id)
    score = score_reflect_case(case)
    assert score.passed, score.to_dict()


def test_live_145239_flow_reflect_repair_to_toolbar_forward():
    """Cross-module: finalize diagnosis + brain must not stay on Observe."""
    cases = load_module_cases("flow")
    case = next(c for c in cases if "145239" in c.id and "picker_miss" in c.id)
    score = score_flow_case(case)
    assert score.passed, score.to_dict()


@pytest.mark.parametrize("case_id", [c.id for c in _blocking_cases()])
def test_each_blocking_golden_passes(case_id: str):
    """Every non-gap golden is its own regression pin — failure names the case."""
    gaps = set(load_manifest().get("known_gap_case_ids") or [])
    assert case_id not in gaps
    case = next(c for cs in load_all_cases().values() for c in cs if c.id == case_id)
    score = _score_case(case)
    assert score.passed, score.to_dict()


def test_score_all_blocking_cases_green():
    report = score_all()
    gaps = set(load_manifest().get("known_gap_case_ids") or [])
    assert report["cases_total"] >= 40
    for module, block in (report.get("modules") or {}).items():
        for fail in block.get("failures") or []:
            assert fail.get("case_id") in gaps, (module, fail)


def test_golden_v1_gate_passes():
    from plugin.evals.gates import run_gates

    results = {g.name: g for g in run_gates()}
    gate = results["golden_v1_modules_pass"]
    assert gate.passed, gate.detail


def test_014321_act_intention_flow_is_blocking():
    cases = load_module_cases("flow")
    case = next(c for c in cases if "014321" in c.id and "act_intention" in c.id)
    assert case.id not in set(load_manifest().get("known_gap_case_ids") or [])
    assert score_flow_case(case).passed


def test_summarize_golden_matches_score_all():
    a = summarize_golden()
    b = score_all()
    assert a["mean_accuracy"] == b["mean_accuracy"]
    assert a["cases_total"] == b["cases_total"]


def test_harvest_runs_smoke(tmp_path):
    runs = list_run_logs("plugin/experiments/runs", limit=2)
    if not runs:
        return
    index = harvest_runs("plugin/experiments/runs", str(tmp_path / "cand"), limit=2)
    assert index["runs_scanned"] >= 1
    assert (tmp_path / "cand" / "_index.json").is_file()


def test_promote_dry_run_from_draft(tmp_path):
    from plugin.evals.golden.promote import main as promote_main

    case_path = tmp_path / "case.json"
    case_path.write_text(
        '{"id":"flow/tmp_promote_dry","module":"flow","source":"draft","input":{"flow":"act_intention_reperceive"},"gold":{}}',
        encoding="utf-8",
    )
    assert promote_main(["--case", str(case_path), "--dry-run"]) == 0
