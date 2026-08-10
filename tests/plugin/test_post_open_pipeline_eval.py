"""Piecewise post-open pipeline: perception → critic → brain → AX chrome trap."""

from __future__ import annotations

from plugin.evals.annotations import annotate, load_overrides
from plugin.evals.corpus import DEFAULT_CORPUS_DIR, load_fixtures
from plugin.evals.post_open_pipeline import (
    PIPELINE_PAIRS,
    score_ax_chrome_trap,
    score_perception,
    summarize_post_open_pipeline,
    _proposal_from_response,
)


def test_ax_chrome_trap_isolates_search_title():
    """AX 'Q Search|' must not become accepted open_conversation."""
    score = score_ax_chrome_trap()
    assert "contaminated_ax_title_not_accepted_as_open" in {
        c.name for c in score.checks
    }
    # This is the live stall layer — fail loudly if critic adopts chrome.
    trap = next(c for c in score.checks if c.name == "contaminated_ax_title_not_accepted_as_open")
    assert trap.passed, trap.detail


def test_perception_piece_on_find_link_fixture():
    fixtures = annotate(load_fixtures(DEFAULT_CORPUS_DIR), overrides=load_overrides())
    by_id = {f.id: f for f in fixtures}
    after = by_id["find_link/frame_0059"]
    reading = _proposal_from_response(after.response)
    score = score_perception(
        after, reading, trajectory="t", expect_open="Pallavi"
    )
    assert score.score >= 0.6, score.to_dict()
    names = {c.name: c.passed for c in score.checks}
    assert names.get("surface_is_conversation")
    assert names.get("open_conversation_not_search_chrome")


def test_summarize_offline_smoke():
    fixtures = annotate(load_fixtures(DEFAULT_CORPUS_DIR), overrides=load_overrides())
    report = summarize_post_open_pipeline(fixtures)
    assert report["fixtures_scored"] == len(PIPELINE_PAIRS)
    assert "A_perception" in (report.get("piece_means") or {})
    assert "C_brain" in (report.get("piece_means") or {})
    assert "D_ax_chrome_trap" in (report.get("piece_means") or {})
    names = {m["name"] for m in report["metrics"]}
    assert "brain_locate_after_open" in names
    assert "ax_search_chrome_not_open_title" in names
