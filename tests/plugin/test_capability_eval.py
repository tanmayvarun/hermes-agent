"""Capability evals must catch composition failures, not just vocabulary.

An eval that only asserts `locate_content in ALLOWED_ACTIONS` will green-pass a
system that still scrolls forever. Each test here either runs a scenario that
must pass, or injects a specific defect and asserts the matching check fails.
"""

from __future__ import annotations

from plugin.agent.capabilities.locate_content import LocateOutcome
from plugin.agent.unified_cognition import UnifiedProposal
from plugin.experiments.capability_eval import (
    evaluate_forward_scenarios,
    evaluate_forward_trajectories,
    evaluate_scenario,
    evaluate_trajectory,
    forward_scenarios,
    forward_trajectories,
    score_capability_choice,
    score_capability_gates,
    score_outcome_evidence_contract,
)


def _names(checks):
    return {c.name: c.passed for c in checks}


def test_all_forward_scenarios_pass_as_a_suite():
    report = evaluate_forward_scenarios()
    assert report["failed"] == [], report["failed"]
    assert report["passed"] == report["scenario_count"]


def test_each_scenario_has_required_pass_or_fail_expectations():
    """A scenario with neither require_pass nor require_fail asserts nothing."""
    for scenario in forward_scenarios():
        assert scenario.require_pass or scenario.require_fail, scenario.name


def test_scroll_hunt_defect_is_caught_by_name():
    scenario = next(s for s in forward_scenarios() if s.name == "hunting_by_scroll_is_caught")
    result = evaluate_scenario(scenario)
    assert result["ok"]
    assert result["checks"]["scroll_is_not_the_primary_hunt"] is False
    assert result["checks"]["hunt_prefers_locate_over_scroll"] is False


def test_early_destination_open_is_caught():
    scenario = next(s for s in forward_scenarios() if s.name == "hunting_opens_destination_early_is_caught")
    result = evaluate_scenario(scenario)
    assert result["ok"]
    assert result["checks"]["hunt_does_not_open_destination_early"] is False


def test_send_via_invoke_is_caught_in_choice_and_gate():
    scenario = next(s for s in forward_scenarios() if s.name == "menu_invoke_send_is_caught")
    result = evaluate_scenario(scenario)
    assert result["ok"]
    assert result["checks"]["invoke_refuses_irreversible_labels"] is False
    assert result["checks"]["send_goes_through_commit_not_invoke_or_bare_click"] is False
    # Gate path: dispatch must also refuse.
    assert result["checks"]["dispatch_blocks_irreversible_invoke"] is True


def test_send_via_bare_click_is_caught():
    scenario = next(s for s in forward_scenarios() if s.name == "send_via_bare_click_is_caught")
    result = evaluate_scenario(scenario)
    assert result["ok"]
    assert result["checks"]["send_goes_through_commit_not_invoke_or_bare_click"] is False


def test_locate_evidence_must_not_claim_relevance():
    checks = _names(
        score_outcome_evidence_contract(
            {
                "text_match_reachable": True,
                "surface_exhausted": False,
                "selected": True,  # defect
            },
            capability="locate_content",
        )
    )
    assert checks["evidence_does_not_claim_relevance"] is False


def test_locate_evidence_reports_reachability():
    checks = _names(
        score_outcome_evidence_contract(
            LocateOutcome(ok=True, realization="native_find", found=True, message="hit").as_evidence(),
            capability="locate_content",
        )
    )
    assert checks["locate_evidence_reports_reachability"] is True
    assert checks["evidence_does_not_claim_relevance"] is True


def test_commit_evidence_must_mark_irreversible():
    checks = _names(
        score_outcome_evidence_contract(
            {"substrate": "gated_target", "label": "Send"},
            capability="commit_irreversible",
        )
    )
    assert checks["commit_evidence_marks_irreversible"] is False


def test_commit_proposal_is_marked_not_reversible_by_gates():
    proposal = UnifiedProposal(
        observed_state={"surface": "forward_picker"},
        next_action={"family": "commit_irreversible", "text": "Send", "confidence": 0.95},
        confidence=0.95,
    )
    packet = {
        "goal": {
            "operation": "whatsapp_forward_message",
            "source_conversation": "Pallavi",
            "source_query": "zarooratwala",
            "destination": "Tanmay",
        },
        "allowed_actions": list(
            __import__("plugin.agent.unified_cognition", fromlist=["ALLOWED_ACTIONS"]).ALLOWED_ACTIONS
        ),
        "world_model": {},
        "observation": {},
    }
    checks = _names(score_capability_gates(proposal, packet))
    assert checks["commit_action_is_not_reversible"] is True
    assert checks["commit_proposal_is_admissible"] is True


def test_ungrounded_reveal_is_caught():
    proposal = UnifiedProposal(
        observed_state={
            "surface": "conversation",
            "open_conversation": "Pallavi",
            "target_object_visible": True,
        },
        world_model={
            "surface": "conversation",
            "open_conversation": "Pallavi",
            "objects": [{"text": "zarooratwala", "matches_goal": True, "point": [1, 2]}],
            "exhausted": [],
        },
        next_action={"family": "reveal_actions", "confidence": 0.9},  # no target
        confidence=0.9,
    )
    packet = {
        "goal": {
            "operation": "whatsapp_forward_message",
            "source_conversation": "Pallavi",
            "source_query": "zarooratwala",
            "destination": "Tanmay",
        },
        "allowed_actions": list(
            __import__("plugin.agent.unified_cognition", fromlist=["ALLOWED_ACTIONS"]).ALLOWED_ACTIONS
        ),
        "world_model": proposal.world_model,
        "observation": {},
    }
    checks = _names(score_capability_choice(proposal, packet))
    assert checks["entity_capability_is_grounded"] is False


def test_healthy_locate_while_hunting_passes_choice_checks():
    scenario = next(s for s in forward_scenarios() if s.name == "hunting_uses_locate")
    result = evaluate_scenario(scenario)
    assert result["ok"], result
    assert result["checks"]["hunt_prefers_locate_over_scroll"] is True
    assert result["checks"]["locate_carries_a_query"] is True


def test_all_forward_trajectories_pass_as_a_suite():
    report = evaluate_forward_trajectories()
    assert report["failed"] == [], report
    assert report["passed"] == report["trajectory_count"]


def test_happy_path_trajectory_covers_full_composition():
    traj = next(t for t in forward_trajectories() if t.name == "happy_path_forward")
    result = evaluate_trajectory(traj)
    assert result["ok"], result
    families = [s.family for s in traj.steps]
    assert families == [
        "open_entity",
        "locate_content",
        "select_content",
        "reveal_actions",
        "invoke_affordance",
        "open_entity",
        "commit_irreversible",
    ]
    assert result["transition_checks"]["send_does_not_precede_forward"] is True


def test_scroll_relapse_trajectory_is_expected_failure():
    traj = next(t for t in forward_trajectories() if t.name == "scroll_hunt_then_never_recovers")
    result = evaluate_trajectory(traj)
    assert traj.expect_failure
    assert result["ok"], result  # ok means the defect was caught
    assert any(not s["ok"] for s in result["steps"])


def test_send_before_forward_trajectory_is_caught():
    traj = next(t for t in forward_trajectories() if t.name == "send_before_forward_is_caught")
    result = evaluate_trajectory(traj)
    assert result["ok"], result
    assert result["transition_checks"]["send_does_not_precede_forward"] is False
