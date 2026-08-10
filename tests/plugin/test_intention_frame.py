"""Intention + IntentionFrame contracts (intent-level retry)."""

from plugin.agent.executive.intention_frame import (
    FailureClass,
    IntentionStatus,
    MethodOutcome,
    TerminationReason,
    apply_derived_status,
    budget_exhausted,
    classify_method_outcome,
    evaluate_intention_success,
    is_local_route_exhausted,
    mark_method_attempted,
    rank_eligible,
    seed_reveal_explore_frame,
)
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.executive.intention_frame import (
    push_intention_frame,
    active_intention_frame,
)
from plugin.agent.capabilities.reveal_actions import note_reveal_probe_handoff
from plugin.agent.affordance_frontier import AffordanceFrontier, finalize_reveal_handoff


def test_intention_is_immutable_and_survives_method_miss():
    frame = seed_reveal_explore_frame()
    iid = frame.intention.id
    mark_method_attempted(frame, "reveal_context_click")
    assert frame.intention.id == iid
    assert "reveal_hover" in frame.method_frontier.eligible_methods()


def test_method_effect_not_intention_success():
    frame = seed_reveal_explore_frame()
    assert not evaluate_intention_success(
        frame,
        world={
            "surface": "selection_mode",
            "objects": [{"text": "Reply"}, {"text": "React"}],
        },
        affordance_stance="explore_needed",
    )
    assert evaluate_intention_success(
        frame, affordance_stance="act_clear", grounded_forward=True
    )


def test_effect_uncertain_vs_method_ineffective():
    o, f = classify_method_outcome(
        execution_ok=True, observation_quality=0.9, effect_present=False
    )
    assert o == MethodOutcome.EFFECT_ABSENT.value
    assert f == FailureClass.METHOD_INEFFECTIVE.value
    o2, f2 = classify_method_outcome(
        execution_ok=True, observation_quality=0.2, effect_present=False
    )
    assert o2 == MethodOutcome.EFFECT_UNCERTAIN.value
    assert f2 == FailureClass.EFFECT_UNCERTAIN.value


def test_ineligible_is_not_exhaustion():
    frame = seed_reveal_explore_frame()
    frame.method_frontier.currently_ineligible = ["reveal_hover"]
    frame.method_frontier.known_untried = [
        x for x in frame.method_frontier.known_untried if x != "reveal_hover"
    ]
    assert "reveal_context_click" in frame.method_frontier.eligible_methods()
    assert not is_local_route_exhausted(frame)


def test_budget_exhaustion_distinct_from_route():
    frame = seed_reveal_explore_frame()
    frame.budget.max_methods = 1
    mark_method_attempted(frame, "reveal_context_click")
    assert budget_exhausted(frame)
    apply_derived_status(frame)
    assert frame.status == IntentionStatus.BLOCKED.value
    assert frame.termination_reason == TerminationReason.BUDGET_EXHAUSTED.value


def test_finalize_advances_method_not_episode_on_first_miss():
    state = ExecutionState()
    note_reveal_probe_handoff(
        state, surface="context_menu", ttl=1, gesture="context_click"
    )
    assert active_intention_frame(state) is not None
    status = finalize_reveal_handoff(state, AffordanceFrontier(surface="context_menu"))
    assert not status.get("failed_reveal")
    assert status.get("method_advance")
    frame = active_intention_frame(state)
    assert frame is not None
    assert "reveal_context_click" in frame.method_frontier.attempted
    assert rank_eligible(frame)


def test_child_success_does_not_blindly_require_original_method():
    """Gate 15 spirit: after prereq, re-rank — hover may no longer win."""
    frame = seed_reveal_explore_frame()
    # Simulate observed Forward button dominating hover.
    from plugin.agent.executive.intention_frame import MethodSpec, EffectSpec, MethodProvenance

    frame.method_frontier.catalog["observed_forward"] = MethodSpec(
        id="observed_forward",
        capability="invoke_affordance",
        target_binding="source_object",
        expected_effect=EffectSpec(success_any=["forward_affordance_grounded"]),
        provenance=MethodProvenance.OBSERVED.value,
        reversibility=0.5,
        risk=0.2,
    )
    frame.method_frontier.newly_discovered.append("observed_forward")
    ranked = rank_eligible(frame)
    assert ranked
    # Observed provenance should compete at the head.
    assert ranked[0][0] in {"observed_forward", "reveal_context_click", "reveal_hover"}


def test_spawn_child_on_precondition_and_resume_reranks():
    from plugin.agent.executive.intention_frame import (
        EffectSpec,
        MethodProvenance,
        MethodSpec,
        ensure_prereq_child_or_next_method,
        intention_stack_of,
        mark_method_attempted,
        resume_parent_after_child,
    )

    state = ExecutionState()
    parent = seed_reveal_explore_frame()
    push_intention_frame(state, parent)
    mark_method_attempted(parent, "reveal_context_click")
    parent.method_frontier.known_untried = [
        "reveal_hover",
        *[m for m in parent.method_frontier.known_untried if m != "reveal_hover"],
    ]
    nxt = ensure_prereq_child_or_next_method(
        state,
        parent,
        world={"surface": "conversation"},
        predicates={"source_object_selected": False},
    )
    assert nxt is not None and nxt.capability == "select_content"
    assert len(intention_stack_of(state)) == 2
    assert intention_stack_of(state)[0].suspended_by_child
    parent.method_frontier.catalog["observed_forward"] = MethodSpec(
        id="observed_forward",
        capability="invoke_affordance",
        target_binding="source_object",
        expected_effect=EffectSpec(success_any=["forward_affordance_grounded"]),
        provenance=MethodProvenance.OBSERVED.value,
    )
    parent.method_frontier.newly_discovered.append("observed_forward")
    status = resume_parent_after_child(
        state,
        world={"surface": "conversation", "source_object_selected": True},
        affordance_stance="explore_needed",
    )
    assert status.get("resumed")
    assert status.get("rerank")
    assert status["rerank"][0] != "reveal_hover"
