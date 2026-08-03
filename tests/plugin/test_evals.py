"""Tests for the eval system itself.

An eval that scores wrongly is worse than no eval: it produces confident
numbers that send people to fix the wrong thing. These check the properties
that make the scores mean what the report says they mean -- ground truth stays
independent of the reply, a metric that could not score says so instead of
guessing, and the frozen corpus keeps its failure cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plugin.evals import metrics as M
from plugin.evals.annotations import (
    annotate,
    annotation_coverage,
    apply_override,
    derive_annotation,
    is_chrome_node,
    normalize_family,
)
from plugin.evals.closed_loop import STAGES, analyse_run, summarize
from plugin.evals.corpus import Fixture, bucket_of, load_fixtures, select_frames, traits_for
from plugin.evals.gates import GATES, blocking_failures, compare_to_baseline, run_gates


def _fixture(**over) -> Fixture:
    packet = {
        "goal": {
            "operation": "whatsapp_forward_message",
            "source_conversation": "Pallavi",
            "source_query": "zarooratwala",
            "destination": "Tanmay",
        },
        "observation": {
            "app": "WhatsApp",
            "ax_node_count": 2,
            "ax_content_node_count": 0,
            "ax_evidence": [
                {"id": 1, "role": "AXApplication", "label": "WhatsApp", "bounds": [0, 0, 0, 0]},
                {"id": 2, "role": "AXWindow", "label": "WhatsApp", "bounds": [0, 0, 100, 100]},
            ],
        },
    }
    packet.update(over.pop("packet", {}))
    base = {
        "id": "open_source/frame_0001",
        "phase": "open_source",
        "packet": packet,
        "response": {"world_model": {"surface": "chat_list"}, "confidence": 0.8},
        "shadow": {"wa_screen": "LIST"},
        "screenshot": {"recorded": True},
    }
    base.update(over)
    fixture = Fixture(**base)
    fixture.annotation = derive_annotation(fixture)
    return fixture


# --- the corpus keeps what makes it worth having -----------------------------


def test_the_frozen_corpus_still_covers_every_stage_of_the_forward():
    fixtures = load_fixtures()
    assert fixtures, "the committed corpus is empty; run python -m plugin.evals.harvest"
    phases = {f.phase for f in fixtures}
    for stage in ("open_source", "find_link", "open_forward", "select_destination"):
        assert stage in phases, f"no fixture covers {stage}, so a regression there scores nothing"


def test_a_harvest_keeps_the_failure_states_not_just_the_happy_path():
    frames = [
        {"frame": i, "packet": {"observation": {"ax_node_count": 40, "ax_content_node_count": 30}},
         "response": {"world_model": {"surface": "chat_list", "objects": [{"text": "Pallavi"}]}},
         "shadow_task_state": {"phase": "OPEN_SOURCE"}}
        for i in range(1, 40)
    ]
    starved = {
        "frame": 99,
        "packet": {"observation": {"ax_node_count": 2, "ax_content_node_count": 0}, "identical_readings_in_a_row": 3},
        "response": {"world_model": {"surface": "conversation"}},
        "shadow_task_state": {"phase": "FIND_LINK"},
    }
    picked = select_frames(frames + [starved], per_bucket=3, per_trait=2)
    assert any(f.get("frame") == 99 for f in picked), "the one starved frame was crowded out by the happy path"
    marks = traits_for(starved)
    assert "shell_only" in marks and "repeated_reading" in marks


def test_frames_from_the_old_packet_contract_are_left_out():
    legacy = {"frame": 1, "packet": {"task_state": {}, "current_observation": {}}, "response": {}}
    assert select_frames([legacy]) == []
    assert "legacy_packet" in traits_for(legacy)


def test_an_overlay_frame_is_bucketed_by_what_is_on_top():
    frame = {
        "frame": 5,
        "packet": {"observation": {}},
        "response": {"world_model": {"surface": "forward_picker"}},
        "shadow_task_state": {"phase": "FIND_LINK"},
    }
    assert bucket_of(frame) == "select_destination"


# --- ground truth stays independent of the reply -----------------------------


def test_ground_truth_never_takes_the_surface_from_the_reply_being_scored():
    fixture = _fixture(response={"world_model": {"surface": "forward_picker"}}, shadow={"wa_screen": "LIST"})
    assert fixture.annotation["surface"] == "chat_list"
    assert fixture.annotation["sources"]["surface"] == "shadow_fused"


def test_an_unsettled_field_is_reported_as_unlabelled_rather_than_guessed():
    fixture = _fixture(shadow={})
    assert "surface" in fixture.annotation["unlabelled"]
    assert "surface" not in fixture.annotation


def test_a_human_label_wins_and_is_marked_as_human():
    fixture = _fixture()
    merged = apply_override(fixture.annotation, {"id": fixture.id, "surface": "conversation", "note": "read the png"})
    assert merged["surface"] == "conversation"
    assert merged["sources"]["surface"] == "manual"
    assert "surface" not in merged["unlabelled"]
    assert merged["note"] == "read the png"


def test_coverage_reports_how_much_of_the_truth_is_actually_settled():
    settled = _fixture()
    unsettled = _fixture(shadow={})
    report = annotation_coverage([settled, unsettled])
    assert report["fixtures"] == 2
    assert report["rates"]["surface"] == 0.5


def test_the_committed_gold_labels_only_cover_frames_someone_looked_at():
    path = Path("plugin/evals/annotations/overrides.jsonl")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]
    assert rows, "no gold labels committed"
    for row in rows:
        assert row.get("note"), f"{row.get('id')} has no note saying what was seen on the screenshot"


# --- metrics measure what the report claims ----------------------------------


def test_sensing_recall_is_weighted_so_a_missing_search_field_cannot_be_averaged_away():
    fixture = _fixture()
    fixture.annotation["required_controls"] = [
        {"kind": "search_input", "weight": 10},
        {"kind": "decoration", "label": "WhatsApp", "weight": 1},
    ]
    result = M.ax_content_recall([fixture])
    # The decorative label is present and the critical control is not, so the
    # score must sit near zero rather than at one half.
    assert result.value is not None and result.value < 0.2


def test_application_chrome_is_told_apart_from_a_chat_whose_name_starts_the_same():
    assert is_chrome_node({"role": "AXMenuItem", "label": "Help"})
    assert not is_chrome_node({"role": "AXRow", "label": "Helping Hands - IITR 2013"})
    assert is_chrome_node({"role": "AXStaticText", "label": "Messages are end-to-end encrypted"})


def test_surface_accuracy_is_scored_only_where_a_human_confirmed_the_screen():
    derived = _fixture()
    gold = _fixture(id="open_source/frame_0002")
    gold.annotation = apply_override(gold.annotation, {"id": gold.id, "surface": "chat_list"})
    result = M.surface_accuracy([derived, gold])
    assert result.scored == 1, "a derived label must not be counted as accuracy ground truth"
    assert result.value == 1.0


def test_an_open_overlay_the_base_label_cannot_see_is_scored_against_the_overlay():
    fixture = _fixture(response={"world_model": {"surface": "context_menu"}})
    fixture.annotation["surface_state"] = {"sidebar": "search_results", "main": "conversation", "overlay": "context_menu"}
    assert M.overlay_detection([fixture]).value == 1.0
    fixture.response = {"world_model": {"surface": "conversation"}}
    assert M.overlay_detection([fixture]).value == 0.0


def test_a_metric_with_nothing_to_score_says_so_instead_of_returning_zero():
    fixture = _fixture()
    result = M.target_grounding_accuracy([fixture])
    assert result.value is None
    assert result.scored == 0 and result.skipped == 1


def test_the_ranking_metric_scores_intent_rather_than_the_word_the_model_used():
    assert normalize_family("click", "chat_list") == "open_entity"
    assert normalize_family("click", "conversation") == "select_content"
    assert normalize_family("right_click", "conversation") == "reveal_actions"
    fixture = _fixture(response={"world_model": {"surface": "chat_list"}, "next_action": {"family": "click"}})
    assert M.top_k_acceptable([fixture]).value == 1.0


def test_a_useful_move_ranked_second_still_counts_but_scores_a_lower_rank():
    fixture = _fixture(
        response={
            "world_model": {"surface": "chat_list"},
            "next_actions": [
                {"family": "commit_irreversible"},
                {"family": "compose_search_query"},
            ],
        }
    )
    result = M.top_k_acceptable([fixture])
    assert result.value == 1.0
    assert result.detail["mean_reciprocal_rank"] == 0.5


def test_choosing_a_thread_that_merely_contains_the_name_is_counted_as_capture():
    fixture = _fixture(
        response={"world_model": {"surface": "forward_picker"}, "next_action": {"family": "open_entity", "text": "Aakash <> Tanmay"}}
    )
    fixture.annotation["distractors"] = ["Aakash <> Tanmay"]
    assert M.distractor_capture_rate([fixture]).value == 1.0


def test_an_object_gesture_aimed_at_the_encryption_notice_is_a_violation():
    fixture = _fixture(
        response={
            "world_model": {"surface": "conversation"},
            "next_action": {"family": "hover", "target_label": "Messages are end-to-end encrypted"},
        }
    )
    assert M.object_scope_violations([fixture]).value == 1.0


def test_confidence_without_evidence_is_caught_and_honest_uncertainty_is_not():
    blind = _fixture(
        response={
            "world_model": {"surface": "conversation", "open_conversation": "Pallavi"},
            "observed_state": {"open_conversation": "Pallavi"},
            "confidence": 0.95,
        },
        screenshot={"recorded": False},
    )
    assert M.unsupported_confidence_rate([blind]).value == 1.0

    humble = _fixture(
        response={"world_model": {"surface": "chat_list"}, "confidence": 0.3},
        screenshot={"recorded": False},
    )
    assert M.unsupported_confidence_rate([humble]).value == 0.0


def test_a_thin_frame_answered_without_naming_a_gap_is_marked_dishonest():
    silent = _fixture(response={"world_model": {"surface": "chat_list"}, "confidence": 0.8})
    assert M.evidence_gap_honesty([silent]).value == 0.0
    speaking = _fixture(
        response={
            "world_model": {"surface": "chat_list"},
            "missing_evidence": ["search field not present in the AX tree"],
        }
    )
    assert M.evidence_gap_honesty([speaking]).value == 1.0


def test_a_broken_metric_cannot_take_the_rest_of_the_report_down_with_it(monkeypatch):
    def explode(_fixtures):
        raise RuntimeError("bad annotation")

    monkeypatch.setattr(M, "ALL_METRICS", (explode, M.chrome_pollution_rate))
    results = M.evaluate_all([_fixture()])
    assert len(results) == 2
    assert any(r.layer == "error" for r in results)
    assert any(r.name == "chrome_pollution_rate" and r.value == 1.0 for r in results)


# --- closed loop -------------------------------------------------------------


def _run_log(tmp_path: Path, records) -> Path:
    path = tmp_path / "forward_zarooratwala_live_test.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return path


def test_a_stage_is_not_credited_when_the_one_before_it_never_happened(tmp_path):
    log = _run_log(
        tmp_path,
        [
            {"kind": "whatsapp_forward_message", "source_contact": "Pallavi", "target_contact": "Tanmay", "link_query": "zarooratwala"},
            {"kind": "execution", "ok": True, "plan_step": {"action_family": "resolve_entity", "text": "Tanmay"}},
        ],
    )
    outcome = analyse_run(log)
    assert outcome.claimed_stages["selected_destination"] is True
    assert outcome.stages["selected_destination"] is False, "a picker that never opened cannot have had a recipient chosen"
    assert outcome.furthest_stage == ""


def test_a_run_that_declares_success_without_verification_is_a_false_success(tmp_path):
    log = _run_log(
        tmp_path,
        [
            {"kind": "whatsapp_forward_message", "source_contact": "Pallavi", "target_contact": "Tanmay"},
            {"kind": "goal_status", "succeeded": True, "reason": "assumed sent"},
        ],
    )
    outcome = analyse_run(log)
    assert outcome.completed is False
    assert outcome.false_success is True
    assert summarize([outcome])["false_success_rate"] == 1.0


def test_the_full_ladder_completes_only_with_a_verified_commit(tmp_path):
    log = _run_log(
        tmp_path,
        [
            {"kind": "whatsapp_forward_message", "source_contact": "Pallavi", "target_contact": "Tanmay", "link_query": "zarooratwala"},
            {"kind": "post_world_patch", "open_conversation": "Pallavi"},
            {"kind": "world_patch", "entities": [{"label": "zarooratwala.com/fresh"}]},
            {"kind": "post_world_patch", "screen": "forward_picker", "open_conversation": "Pallavi"},
            {"kind": "execution", "ok": True, "plan_step": {"action_family": "resolve_entity", "text": "Tanmay"}},
            {"kind": "execution", "ok": True, "plan_step": {"action_family": "commit_irreversible", "text": "Send"}},
            {"kind": "verification", "passed": True},
        ],
    )
    outcome = analyse_run(log)
    assert all(outcome.stages[stage] for stage in STAGES)
    assert outcome.completed and not outcome.false_success


# --- gates -------------------------------------------------------------------


def test_every_known_failure_is_still_fixed():
    failures = blocking_failures(run_gates())
    assert not failures, "\n".join(f"{f.name}: {f.detail}" for f in failures)


def test_each_gate_says_what_question_it_answers():
    for gate in GATES:
        assert gate.question.endswith("?"), f"{gate.name} does not state the question it settles"


def test_a_gate_that_raises_counts_as_a_failure_rather_than_a_pass():
    from plugin.evals.gates import Gate

    def boom():
        raise RuntimeError("no such module")

    result = Gate("explodes", "Does it?", boom).run()
    assert result.passed is False and "gate raised" in result.detail


def test_a_metric_that_slipped_past_its_limit_is_reported_in_the_right_direction():
    baseline = {"metrics": [
        {"name": "critical_cta_recall", "value": 0.90},
        {"name": "chrome_pollution_rate", "value": 0.10},
    ]}
    current = {"metrics": [
        {"name": "critical_cta_recall", "value": 0.85},
        {"name": "chrome_pollution_rate", "value": 0.11},
    ]}
    breaches = compare_to_baseline(current, baseline)
    assert [b["metric"] for b in breaches] == ["critical_cta_recall"], "a small rise in pollution is inside its gate"

    worse = {"metrics": [
        {"name": "critical_cta_recall", "value": 0.90},
        {"name": "chrome_pollution_rate", "value": 0.30},
    ]}
    assert [b["metric"] for b in compare_to_baseline(worse, baseline)] == ["chrome_pollution_rate"]


def test_an_improvement_never_reads_as_a_regression():
    baseline = {"metrics": [{"name": "unsupported_high_confidence_rate", "value": 0.20}]}
    current = {"metrics": [{"name": "unsupported_high_confidence_rate", "value": 0.00}]}
    assert compare_to_baseline(current, baseline) == []


def test_temporal_gate_catches_rising_belief_flips_and_phase_slides():
    from plugin.evals.gates import compare_temporal_to_baseline

    baseline = {
        "belief_flip_rate": 0.02,
        "unjustified_phase_regression_rate": 0.0,
        "surface_stability": 0.98,
        "object_identity_continuity": 0.97,
    }
    worse = {
        "belief_flip_rate": 0.20,  # up past its 0.05 gate
        "unjustified_phase_regression_rate": 0.10,  # up past its 0.02 gate
        "surface_stability": 0.80,  # down past its 0.05 gate
        "object_identity_continuity": 0.97,  # unchanged
    }
    breaches = {b["metric"] for b in compare_temporal_to_baseline(worse, baseline)}
    assert breaches == {
        "belief_flip_rate",
        "unjustified_phase_regression_rate",
        "surface_stability",
    }


def test_temporal_gate_lets_improvements_through():
    from plugin.evals.gates import compare_temporal_to_baseline

    baseline = {"belief_flip_rate": 0.20, "surface_stability": 0.80}
    better = {"belief_flip_rate": 0.00, "surface_stability": 0.99}
    assert compare_temporal_to_baseline(better, baseline) == []


# --- the report --------------------------------------------------------------


def test_the_report_runs_over_the_committed_corpus_and_separates_the_layers():
    from plugin.evals.run import build_report, render

    report = build_report()
    layers = {m["layer"] for m in report["metrics"]}
    for layer in ("observation", "structure", "affordance", "ranking", "uncertainty"):
        assert layer in layers, f"the {layer} layer produced no metric"
    assert "error" not in layers, [m for m in report["metrics"] if m["layer"] == "error"]
    text = render(report)
    assert "regression gates" in text and "[observation]" in text


def test_annotating_a_corpus_reads_the_outcome_from_the_frame_that_follows():
    first = _fixture(id="a", source={"frame": 1})
    second = _fixture(id="b", source={"frame": 2}, shadow={"wa_screen": "CONVERSATION"})
    annotate([second, first], overrides={})
    assert first.annotation["observed_next_surface"] == "conversation"
    assert "observed_next_surface" in second.annotation["unlabelled"]
