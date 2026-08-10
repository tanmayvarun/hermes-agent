"""Phenomenon curriculum corpus (live-seeded, counterfactual variants)."""

from __future__ import annotations

from plugin.evals.phenomena.harvest import (
    harvest_perception_candidate,
    write_candidate_bundle,
)
from plugin.evals.phenomena.schema import (
    PHENOMENON_FAMILIES,
    load_all_fixtures,
    load_manifest,
)
from plugin.evals.phenomena.score import blocking_failures, score_all, score_fixture


def test_manifest_covers_all_families():
    man = load_manifest()
    assert not man.get("error"), man
    families = man.get("families") or {}
    for fam in PHENOMENON_FAMILIES:
        assert fam in families, fam
        assert int(families[fam]) >= 1, fam


def test_all_phenomenon_fixtures_pass():
    report = score_all()
    assert report["total"] >= 10
    fails = blocking_failures(report)
    assert not fails, fails


def test_hard_blocking_storage_is_from_live_161105():
    by = load_all_fixtures()
    cases = {f.fixture_id: f for f in by["warning_vs_blocker"]}
    fix = cases["hard_blocking_storage_dialog"]
    assert fix.source_run == "20260810_161105"
    assert "Storage is too full" in "\n".join(fix.observation_texts)
    scored = score_fixture(fix)
    assert scored.passed, scored.checks


def test_warning_counterfactual_does_not_block():
    by = load_all_fixtures()
    fix = next(
        f
        for f in by["warning_vs_blocker"]
        if f.fixture_id == "nonblocking_low_storage_warning"
    )
    scored = score_fixture(fix)
    assert scored.passed, scored.checks


def test_harvest_writes_annotation_stub(tmp_path):
    dest = write_candidate_bundle(
        candidate_id="phenomenon_test_storage",
        stamp="20260810_161105",
        step=1,
        app="WhatsApp",
        observation_texts=[
            "Storage is too full",
            "free up at least 175.81 MB",
        ],
        out_root=tmp_path,
    )
    ann = (dest / "annotation.json").read_text(encoding="utf-8")
    assert "environmental_blocker" in ann
    assert "blocked_resolvable" in ann
    assert (tmp_path / "_index.json").is_file()


def test_harvest_from_perception_candidate_161105(tmp_path):
    src = (
        "plugin/evals/perception_semantic/eval_candidates/"
        "run_live_20260810_161105_step_0001"
    )
    from pathlib import Path

    if not Path(src).is_dir():
        return
    dest = harvest_perception_candidate(Path(src), out_root=tmp_path)
    assert (dest / "ax.json").is_file()
    assert (dest / "observation_texts.json").is_file()
    texts = (dest / "observation_texts.json").read_text(encoding="utf-8")
    assert "Storage is too full" in texts
