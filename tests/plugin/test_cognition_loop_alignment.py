"""The perceive -> critique -> decide loop, and what closes it.

Each test here pins one link in that loop:

- a predicted transition that does not happen is a *surprise*, not a shrug;
- the failure that caused it reaches the perceptor on the very next look;
- looking again is budgeted, so an unmoving world cannot absorb the whole run;
- what the runtime measured updates the action topology, not just the document;
- a stalled branch asks which branch to try next rather than retreating blindly.

These are the links that were missing or one-way before, which is how the agent
could re-click a control it had already proven inert.
"""

from __future__ import annotations

from plugin.agent.affordance_frontier import (
    STATUS_LATENT,
    STATUS_OBSERVED,
    Affordance,
    AffordanceFrontier,
)
from plugin.agent.controller import (
    _consume_surprise,
    _expected_transition_absent,
    _last_action_surprised,
)
from plugin.agent.executive.hierarchy import decision_ladder
from plugin.agent.executive.meta_action import (
    REPERCEPTION_RELOOK_CAP,
    MetaAction,
    MetaContext,
    reperception_exhausted,
)
from plugin.agent.executive.strategic_search import plan_branches
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.transition.types import (
    BranchStrategy,
    ExplorationBranch,
    FrontierAction,
)
from plugin.agent.world_critic import (
    note_topology_evidence,
    reconcile_frontier,
)


def _state_after_noop(*, prediction=None, expectation=None) -> ExecutionState:
    """A state where the last action ran cleanly and the world did not move."""
    state = ExecutionState()
    state.last_attribution = {
        "action_family": "open_entity",
        "effect_kind": "no_transition",
        "outcome": "no_effect",
        "evidence": {"change_score": 0.0},
    }
    state.last_transition = {"prediction": prediction or {}}
    if expectation is not None:
        state.unified_last_expectation = expectation
    return state


# --- surprise: a transition that did not happen is evidence --------------------


def test_ax_settle_noop_is_not_executive_surprise():
    """AX settle no-transition is diagnostic; executive re-perceives instead.

    Motor ok + must_executive_reperceive drives the next look. AX regression /
    no_effect must not force VERIFY or rival the multimodal SoT.
    """
    state = _state_after_noop(prediction={"predicted_outcome": "ConversationOpen(Kulvinder Ji)"})
    state.last_action = "open_entity"
    assert _expected_transition_absent(state)
    assert not _last_action_surprised(state)
    state.must_executive_reperceive = True
    from plugin.agent.controller import _awaiting_verification

    assert _awaiting_verification(state)


def test_motor_fail_attribution_is_executive_surprise():
    state = ExecutionState()
    state.last_action = "open_entity"
    state.last_attribution = {
        "outcome": "no_effect",
        "effect_kind": "no_transition",
        "belief_authority": "motor",
        "evidence": {"executor_ok": False, "attempted": True},
    }
    assert _last_action_surprised(state)


def test_a_no_op_we_never_predicted_anything_about_is_not_a_surprise():
    """Re-perceiving an unchanged world we made no claim about teaches nothing.

    That is the stale case, which backtracking handles; treating it as surprise
    would buy a look that cannot pay for itself.
    """
    state = _state_after_noop(prediction={})
    assert not _expected_transition_absent(state)
    assert not _last_action_surprised(state)


def test_the_unified_expectation_still_marks_absent_transition():
    """Expectation is still detected for diagnostics; it is not executive surprise."""
    state = _state_after_noop(expectation={"surface": "conversation"})
    assert _expected_transition_absent(state)
    assert not _last_action_surprised(state)


def test_an_action_that_never_landed_does_not_condemn_the_world():
    """Missing geometry is a runtime failure, not a claim about the app."""
    state = _state_after_noop(prediction={"predicted_outcome": "ConversationOpen"})
    state.last_attribution["effect_kind"] = "missing_geometry"
    state.last_attribution["outcome"] = "no_effect"
    assert not _expected_transition_absent(state)


def test_consuming_motor_surprise_lets_the_next_frame_act():
    """Consume stamps verified so a motor surprise does not loop forever."""
    state = ExecutionState()
    state.last_action = "open_entity"
    state.last_attribution = {
        "outcome": "no_effect",
        "effect_kind": "no_transition",
        "belief_authority": "motor",
        "evidence": {"executor_ok": False},
    }
    assert _last_action_surprised(state)
    _consume_surprise(state)
    assert not _last_action_surprised(state)


# --- history: the failed attempt reaches the next look -------------------------


def test_the_perceptor_sees_the_failure_on_the_very_first_surprise():
    """The look that must diagnose the first failure needs the first failure.

    This used to be withheld until a second surprise, so the agent had to fail
    twice before it was allowed to reason about failing once.
    """
    from plugin.agent.unified_cognition import _last_action_report

    state = _state_after_noop(prediction={"predicted_outcome": "ConversationOpen"})
    state.note_surprise(
        {
            "iteration": 3,
            "action": "OpenEntity",
            "family": "open_entity",
            "effect": "no_transition",
        }
    )
    report = _last_action_report(None, state)

    assert report.get("recent_surprises"), "one surprise is already worth reporting"
    assert report["recent_surprises"][0]["effect"] == "no_transition"


# --- budget: looking again is not free -----------------------------------------


def test_relooks_are_exhausted_once_the_budget_is_spent():
    state = ExecutionState()
    assert not reperception_exhausted(state)
    state.consecutive_surprise_relooks = REPERCEPTION_RELOOK_CAP
    assert reperception_exhausted(state)


def test_consume_surprise_clears_sticky_prediction_error():
    """Live 123727: REFLECT must consume surprise or meta reflects forever."""
    from plugin.agent.controller import _consume_surprise, _last_action_surprised

    state = ExecutionState()
    state.last_prediction_error = {
        "matched": False,
        "predicted": "ConversationOpen",
        "observed": "LIST",
    }
    state.last_attribution = {
        "belief_authority": "motor",
        "effect_kind": "no_transition",
        "outcome": "no_effect",
    }
    assert _last_action_surprised(state) is True
    _consume_surprise(state)
    assert _last_action_surprised(state) is False
    assert state.last_prediction_error.get("consumed_by_reflect") is True
    assert state.last_attribution.get("effect_kind") == "verified"


def test_a_spent_relook_budget_stops_looking_and_broadens_the_search():
    """Re-reading a world that will not move has to stop paying eventually.

    While re-looks remain, a surprise wins REFLECT (look + explain). Once they
    are spent the same surprise must not keep winning — *unless* post-act debt
    is still unpaid (that debt is hard; see test below / live 033711).
    """
    ctx = MetaContext(awaiting_verification=True, last_action_surprised=True)
    assert decision_ladder(ctx).action is MetaAction.PERCEIVE

    spent = MetaContext(
        awaiting_verification=True,
        last_action_surprised=True,
        reperception_exhausted=True,
        branch_stale=True,
    )
    assert decision_ladder(spent).action is MetaAction.THINK

    # Unpaid motor write: still rung-1 PERCEIVE even with exhausted surprise budget.
    unpaid = MetaContext(
        awaiting_verification=True,
        post_action_look_owed=True,
        last_action_surprised=False,
        reperception_exhausted=True,
        branch_stale=True,
        has_grounded_action=True,
    )
    assert decision_ladder(unpaid).action is MetaAction.PERCEIVE


# --- topology: what was measured updates what can be done ----------------------


def test_a_control_measured_inert_is_withdrawn_from_the_next_frontier():
    """The frontier is rebuilt every frame, so it needs the critic's memory.

    Without this the control the runtime just proved dead is handed back to the
    perceptor as a live option on the very next look.
    """
    state = ExecutionState()
    note_topology_evidence(
        state,
        last_action_family="open_entity",
        last_target="Kulvinder Ji",
        effect_kind="no_transition",
        surface="search",
    )
    frontier = AffordanceFrontier(
        surface="search",
        observed_actions=[
            Affordance(id="a", family="open_entity", status=STATUS_OBSERVED, target_label="Kulvinder Ji"),
            Affordance(id="b", family="open_entity", status=STATUS_OBSERVED, target_label="Pallavi"),
        ],
    )
    reconcile_frontier(frontier, document={"surface": "search"}, execution_state=state)

    live = {a.target_label for a in frontier.observed_actions}
    assert live == {"Pallavi"}
    # Withdrawn *with its reason*, so the model learns rather than silently
    # losing an option it can see on screen.
    assert frontier.excluded_actions
    assert "inert" in frontier.excluded_actions[0]["reason"]


def test_an_action_that_never_landed_condemns_nothing():
    state = ExecutionState()
    assert (
        note_topology_evidence(
            state,
            last_action_family="open_entity",
            last_target="Pallavi",
            effect_kind="missing_geometry",
            surface="search",
        )
        is None
    )
    assert not state.dead_affordances


def test_a_confirmed_reveal_promotes_the_controls_it_put_on_screen():
    """After a reveal lands, its controls are observed — not still 'latent'."""
    frontier = AffordanceFrontier(
        surface="context_menu",
        latent_actions=[
            Affordance(
                id="fwd",
                family="invoke_affordance",
                status=STATUS_LATENT,
                target_label="Forward",
            )
        ],
    )
    reconcile_frontier(
        frontier,
        document={
            "surface": "context_menu",
            "objects": [{"text": "Forward", "point": [10, 20], "id": 7}],
        },
        execution_state=ExecutionState(),
        last_action_family="reveal_actions",
    )

    assert {a.target_label for a in frontier.observed_actions} == {"Forward"}
    assert not frontier.latent_actions


# --- strategic search: which branch, in what order -----------------------------


def _branch_state() -> ExecutionState:
    state = ExecutionState()
    state.exploration_branch = ExplorationBranch(
        active=True,
        frontier=[
            FrontierAction(action_family="observe"),
            FrontierAction(action_family="locate_content", semantic_target="zarooratwala", tried=True),
            FrontierAction(action_family="open_entity", semantic_target="Kulvinder Ji"),
            FrontierAction(action_family="type_query", text="zaroorat"),
        ],
    )
    return state


def test_a_stale_branch_asks_where_to_go_rather_than_only_retreating():
    ctx = MetaContext(branch_stale=True)
    assert decision_ladder(ctx).action is MetaAction.THINK


def test_the_branch_plan_falls_back_to_the_frontier_untried_first(monkeypatch):
    """The model is an improvement on the ordering, never a requirement for one."""
    from plugin.agent import decision_selector

    def _unavailable(*_a, **_k):
        raise RuntimeError("reasoning model offline")

    monkeypatch.setattr(decision_selector, "select_branch_strategy_with_llm", _unavailable)
    plan = plan_branches(None, None, None, _branch_state())

    assert plan.source == "frontier"
    assert plan.ordered_families[0] == "open_entity"
    # Observe is never a branch: looking again is what we are retreating from.
    assert "observe" not in plan.ordered_families
    # The already-tried branch sinks below the untried ones.
    assert plan.ordered_families.index("locate_content") > plan.ordered_families.index("type_query")


def test_the_model_orders_the_branches_and_its_avoid_list_is_honoured(monkeypatch):
    from plugin.agent import decision_selector

    def _strategy(*_a, **_k):
        return (
            BranchStrategy(
                preferred_family="type_query",
                backtrack_family="open_entity",
                avoid_families=["locate_content"],
                branch_hypothesis="the row click is inert; search instead",
                confidence=0.8,
                reason="clicking the row has been measured to do nothing",
            ),
            {},
        )

    monkeypatch.setattr(decision_selector, "select_branch_strategy_with_llm", _strategy)
    plan = plan_branches(None, None, None, _branch_state())

    assert plan.source == "llm"
    assert plan.ordered_families == ["type_query", "open_entity"]
    assert plan.head == "type_query"
    assert "locate_content" not in plan.ordered_families


def test_branch_planning_needs_something_to_choose_between():
    """An ordering question over one option is not a question."""
    state = ExecutionState()
    state.exploration_branch = ExplorationBranch(
        active=True, frontier=[FrontierAction(action_family="open_entity")]
    )
    assert plan_branches(None, None, None, state).source in {"frontier", "none"}


# --- escalation: the branch-exhaustion signal is alive -------------------------


def test_no_progress_replans_reaches_the_escalation_check():
    """``should_escalate`` reads this from the feature layer, so it must arrive.

    The counter existed and was read, but nothing ever incremented it, so branch
    exhaustion could not fire however long the agent thrashed.
    """
    from plugin.agent.features import StateFeatures
    from plugin.agent.unified_cognition import should_escalate

    features = StateFeatures(extras={"no_progress_replans": 4})
    escalate, _reason = should_escalate(None, features, admissible=True)
    assert escalate


def test_the_controller_counts_a_replan_when_a_branch_stops_progressing():
    from types import SimpleNamespace

    from plugin.agent.controller import _note_no_progress_replan

    runtime = SimpleNamespace(execution_state=ExecutionState())
    assert _note_no_progress_replan(runtime) == 1
    assert _note_no_progress_replan(runtime) == 2
    assert runtime.execution_state.no_progress_replans == 2
