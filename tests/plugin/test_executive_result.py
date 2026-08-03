"""Tests for the CapabilityResult envelope and its adapters."""

from plugin.agent.capabilities.base import CapabilityOutcome
from plugin.agent.executive.result import (
    CapabilityResult,
    Observation,
    commit_result_beliefs,
    from_capability_outcome,
    from_unified_proposal,
)
from plugin.agent.unified_cognition import UnifiedProposal


def test_status_is_normalised_to_the_allowed_set():
    assert CapabilityResult(status="weird").status == "failed"
    assert CapabilityResult(status="").status == "failed"
    assert CapabilityResult(status="partial").status == "partial"


def test_ok_is_true_for_success_and_partial_only():
    assert CapabilityResult(status="success").ok is True
    assert CapabilityResult(status="partial").ok is True
    assert CapabilityResult(status="blocked").ok is False
    assert CapabilityResult(status="failed").ok is False


def test_capability_outcome_success_maps_to_success():
    outcome = CapabilityOutcome(ok=True, capability="open_entity", message="opened", evidence={"opened": True})
    result = from_capability_outcome(outcome)
    assert result.status == "success"
    assert result.capability == "open_entity"
    assert result.missing_information == []


def test_capability_outcome_blocked_is_detected():
    outcome = CapabilityOutcome(ok=False, capability="commit_irreversible", message="blocked by gate", evidence={})
    assert from_capability_outcome(outcome).status == "blocked"


def test_capability_outcome_failure_reports_missing_info():
    outcome = CapabilityOutcome(ok=False, capability="locate_content", message="not found", evidence={})
    result = from_capability_outcome(outcome)
    assert result.status == "failed"
    assert result.missing_information == ["not found"]


def test_unified_proposal_becomes_observations_and_actions():
    proposal = UnifiedProposal(
        observed_state={"surface": "chat_list", "open_conversation": ""},
        belief_updates=[{"predicate": "active_app", "value": "WhatsApp", "confidence": 0.9}],
        next_actions=[{"action": "Type", "semantic_target": "Search"}],
        missing_evidence=["target row"],
        coverage=0.9,
        confidence=0.8,
        scene_summary="chat list",
    )
    result = from_unified_proposal(proposal)
    assert result.capability == "perception"
    assert result.status == "success"
    # Empty observed values are dropped; non-empty ones become observations.
    claims = {o.claim: o.value for o in result.observations}
    assert claims == {"surface": "chat_list"}
    assert result.proposed_belief_updates["active_app"][0] == "WhatsApp"
    assert result.proposed_actions == [{"action": "Type", "semantic_target": "Search"}]
    assert "target row" in result.missing_information


def test_low_coverage_proposal_is_partial():
    proposal = UnifiedProposal(observed_state={}, coverage=0.1, confidence=0.2)
    assert from_unified_proposal(proposal).status == "partial"


class _FakeState:
    def __init__(self):
        self.iteration = 3
        self.committed = None

    # commit_result_beliefs -> commit_beliefs -> workspace_of; give it no
    # workspace so the call is a safe no-op we can still exercise.


def test_commit_result_beliefs_is_safe_without_a_workspace():
    result = CapabilityResult(
        capability="perception",
        observations=[Observation(claim="surface", value="chat_list", confidence=0.8)],
    )
    commit_result_beliefs(_FakeState(), result)  # must not raise
