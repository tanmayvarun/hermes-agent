"""Semantic perception harness — cross-surface contamination family."""

import json
from pathlib import Path

from plugin.evals.perception_semantic.harvest_failure import (
    harvest_from_golden,
    write_candidate_bundle,
)
from plugin.evals.perception_semantic.metamorphic import expand_family
from plugin.evals.perception_semantic.projector import assert_production_projector
from plugin.evals.perception_semantic.promote import promote_candidate
from plugin.evals.perception_semantic.schema import DEFAULT_CASES_DIR, load_cases
from plugin.evals.perception_semantic.score import score_corpus, score_case


def test_seed_case_loads_and_passes():
    cases = load_cases()
    assert cases
    seed = next(c for c in cases if "source_1_dest_0" in c.id)
    scores = score_case(seed)
    assert scores
    assert all(s.passed for s in scores)


def test_metamorphic_family_zero_contamination():
    seed = next(c for c in load_cases() if "source_1_dest_0" in c.id)
    family = expand_family(seed)
    assert len(family) >= 5
    report = score_corpus(family)
    assert report["failed"] == 0
    assert report["cross_surface_contamination_rate"] == 0.0


def test_production_projector_includes_ownership_contract():
    seed = next(c for c in load_cases() if "source_1_dest_0" in c.id)
    pr = assert_production_projector(seed)
    assert pr["ok"]
    assert pr["meta"]["has_surface_ownership_addendum"]
    assert pr["meta"]["has_perception_objective"]


def test_harvest_from_golden_writes_architect_bundle(tmp_path: Path):
    golden = (
        DEFAULT_CASES_DIR
        / "cross_surface"
        / "whatsapp_forward_picker_source_1_dest_0.json"
    )
    out = harvest_from_golden(golden, out_root=tmp_path)
    for name in (
        "candidate.json",
        "annotation.json",
        "model_input.json",
        "ax.json",
        "executive_context.json",
        "model_output.json",
        "transition.json",
    ):
        assert (out / name).is_file(), name
    ax = json.loads((out / "ax.json").read_text())
    assert ax["count"] >= 1
    ann = json.loads((out / "annotation.json").read_text())
    assert ann["status"] == "promoted"
    assert "cross_surface_selection" in ann["phenomena"]


def test_promote_requires_annotation(tmp_path: Path):
    cand = write_candidate_bundle(
        tmp_path / "run_test_step_0001",
        candidate_id="run_test_step_0001",
        packet={
            "goal": {"destination": "Tanmay"},
            "observation": {
                "app": "WhatsApp",
                "active_interaction_surface": "forward_picker",
                "ax_evidence": [{"id": 1, "label": "Search"}],
            },
        },
        model_output={},
        source={"kind": "unit_test", "step": 1},
    )
    try:
        promote_candidate(cand, fixtures_root=tmp_path / "fixtures", dry_run=True)
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert "surfaces" in str(exc)