"""The executive decides whether it can act, and whether looking again helps."""

from __future__ import annotations

from plugin.agent.executive.sufficiency import (
    STALE_OBSERVE_STREAK,
    SufficiencyInputs,
    assess_sufficiency,
)


def test_clean_frame_with_an_action_is_sufficient():
    verdict = assess_sufficiency(SufficiencyInputs(has_grounded_action=True))
    assert verdict.sufficient_to_act is True
    assert verdict.suppress_observe is False
    assert verdict.observe_has_value is False


def test_a_blocking_uncertainty_keeps_the_agent_looking():
    verdict = assess_sufficiency(
        SufficiencyInputs(blocking_uncertainties=["source_object_unresolved"])
    )
    assert verdict.sufficient_to_act is False
    assert verdict.observe_has_value is True
    assert verdict.suppress_observe is False
    assert verdict.needs_exploration is True
    assert "source_object_unresolved" in verdict.blocking_uncertainties


def test_a_blocking_uncertainty_beats_a_stale_streak():
    # The object may be off-screen, not absent: never suppress while hunting.
    verdict = assess_sufficiency(
        SufficiencyInputs(
            blocking_uncertainties=["source_object_unresolved"],
            identical_observe_streak=5,
        )
    )
    assert verdict.suppress_observe is False
    assert verdict.observe_has_value is True


def test_stale_observation_with_nothing_blocking_is_suppressed():
    verdict = assess_sufficiency(
        SufficiencyInputs(identical_observe_streak=STALE_OBSERVE_STREAK)
    )
    assert verdict.suppress_observe is True
    assert verdict.observe_has_value is False
    assert verdict.needs_exploration is True


def test_a_prior_suppression_sticks_until_change():
    verdict = assess_sufficiency(SufficiencyInputs(previously_suppressed=True))
    assert verdict.suppress_observe is True


def test_a_declared_gap_earns_one_more_look():
    verdict = assess_sufficiency(
        SufficiencyInputs(declared_evidence_gaps=["is the target below the fold?"])
    )
    assert verdict.observe_has_value is True
    assert verdict.suppress_observe is False


def test_a_declared_gap_does_not_override_a_stale_streak():
    verdict = assess_sufficiency(
        SufficiencyInputs(
            declared_evidence_gaps=["is the target below the fold?"],
            identical_observe_streak=STALE_OBSERVE_STREAK,
        )
    )
    assert verdict.suppress_observe is True


def test_thin_coverage_is_worth_another_look():
    verdict = assess_sufficiency(SufficiencyInputs(coverage=0.2, has_grounded_action=True))
    assert verdict.observe_has_value is True
    assert verdict.suppress_observe is False
    assert "coverage" in verdict.reason


def test_full_coverage_is_not_a_reason_to_re_observe():
    verdict = assess_sufficiency(SufficiencyInputs(coverage=1.0, has_grounded_action=True))
    assert verdict.sufficient_to_act is True
    assert verdict.observe_has_value is False


def test_the_verdict_explains_itself():
    verdict = assess_sufficiency(
        SufficiencyInputs(blocking_uncertainties=["destination_ambiguous"])
    )
    assert "destination_ambiguous" in verdict.reason
    assert verdict.to_dict()["reason"] == verdict.reason


def test_sufficient_verdict_names_the_actions_it_supports():
    verdict = assess_sufficiency(SufficiencyInputs(has_grounded_action=True, coverage=0.9))
    assert verdict.sufficient_for_which_actions  # non-empty
    assert verdict.confidence >= 0.6


def test_blocked_verdict_supports_no_actions_and_is_less_confident():
    verdict = assess_sufficiency(SufficiencyInputs(blocking_uncertainties=["where?"], coverage=0.9))
    assert verdict.sufficient_for_which_actions == []
    assert verdict.confidence <= 0.6


def test_confidence_tracks_coverage():
    thin = assess_sufficiency(SufficiencyInputs(coverage=0.1, has_grounded_action=True))
    full = assess_sufficiency(SufficiencyInputs(coverage=1.0, has_grounded_action=True))
    assert full.confidence > thin.confidence
    assert "sufficient_for_which_actions" in full.to_dict()
    assert "confidence" in full.to_dict()


# ------------------------------------------------- perceptor contract fields


def test_perceptor_parses_coverage_and_evidence_gaps():
    from plugin.agent.unified_cognition import _parse_proposal

    parsed = _parse_proposal(
        {
            "world_model": {"surface": "conversation"},
            "next_actions": [{"rank": 1, "family": "observe"}],
            "coverage": 0.4,
            "evidence_gaps": ["is the target message below the fold?"],
        },
        frame=3,
    )
    assert parsed.coverage == 0.4
    assert parsed.evidence_gaps == ["is the target message below the fold?"]
    assert parsed.to_dict()["coverage"] == 0.4


def test_perceptor_coverage_defaults_to_full_when_absent():
    from plugin.agent.unified_cognition import _parse_proposal

    parsed = _parse_proposal(
        {"world_model": {"surface": "search"}, "next_actions": []}, frame=1
    )
    assert parsed.coverage == 1.0
    assert parsed.evidence_gaps == []


def test_perceptor_coverage_is_clamped():
    from plugin.agent.unified_cognition import _parse_proposal

    hot = _parse_proposal({"world_model": {}, "coverage": 4.0}, frame=1)
    cold = _parse_proposal({"world_model": {}, "coverage": -2.0}, frame=1)
    assert hot.coverage == 1.0
    assert cold.coverage == 0.0
