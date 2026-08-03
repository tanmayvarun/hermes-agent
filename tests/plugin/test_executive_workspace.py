"""The workspace is the one place task state lives, and commit is the only door."""

from __future__ import annotations

import pytest

from plugin.agent.action import Action
from plugin.agent.executive.workspace import (
    AttemptRecord,
    Claim,
    ExecutiveWorkspace,
    GoalState,
    Intent,
    TransitionRecord,
    WorkspaceProposal,
    attempts_from_legacy,
    phase_ladder_for,
)
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import ExecutionState


def _workspace(kind: str = "whatsapp_forward_message") -> ExecutiveWorkspace:
    return ExecutiveWorkspace(goal=GoalState(kind=kind, subject="ZarooratWala", destination="Pallavi"))


def test_judgement_records_cognitive_mode_and_is_deliberative_on_a_new_goal():
    """cognitive_mode is not just logged — the first judgement of a run has no
    prior meta-action, so new_goal fires and the mode is deliberative, and both
    the mode and the triggers that produced it are recorded on the state."""
    from plugin.agent.executive.hierarchy import DELIBERATIVE
    from plugin.agent.executive.sync import assess_executive_judgement, bind_goal

    state = ExecutionState()
    bind_goal(state, Goal(kind="whatsapp_forward_message", contact="ZarooratWala", target_contact="Pallavi"))

    assess_executive_judgement(state, has_grounded_action=False)

    assert state.last_cognitive_mode == DELIBERATIVE
    assert "new_goal" in (state.last_mode_triggers or [])


def test_a_reading_becomes_a_claim_with_provenance():
    ws = _workspace()
    ws.commit(
        WorkspaceProposal(
            source="perception",
            frame=3,
            surface="conversation",
            open_conversation="ZarooratWala",
            confidence=0.8,
            evidence="header band",
        )
    )
    claim = ws.open_conversation_claim
    assert ws.open_conversation == "ZarooratWala"
    assert claim.source == "perception"
    assert claim.frame == 3
    assert claim.evidence == "header band"


def test_an_empty_reading_cannot_wipe_an_open_conversation_from_inside_it():
    ws = _workspace()
    ws.commit(WorkspaceProposal(source="perception", surface="conversation", open_conversation="ZarooratWala"))
    verdict = ws.commit(
        WorkspaceProposal(source="perception", surface="forward_picker", open_conversation="")
    )
    assert ws.open_conversation == "ZarooratWala"
    assert "open_conversation" in verdict.rejected_fields


def test_an_empty_reading_with_no_surface_is_not_evidence_of_a_close():
    ws = _workspace()
    ws.commit(WorkspaceProposal(source="perception", surface="conversation", open_conversation="Pallavi"))
    verdict = ws.commit(WorkspaceProposal(source="task_state", open_conversation=""))
    assert ws.open_conversation == "Pallavi"
    assert "open_conversation" in verdict.rejected_fields


def test_a_close_observed_from_the_chat_list_is_accepted():
    ws = _workspace()
    ws.commit(WorkspaceProposal(source="perception", surface="conversation", open_conversation="Pallavi"))
    verdict = ws.commit(WorkspaceProposal(source="perception", surface="chat_list", open_conversation=""))
    assert ws.open_conversation == ""
    assert verdict.accepted("open_conversation")


def test_replacing_one_open_conversation_with_another_counts_as_a_flip():
    ws = _workspace()
    ws.commit(WorkspaceProposal(source="perception", surface="conversation", open_conversation="Pallavi"))
    ws.commit(WorkspaceProposal(source="perception", surface="conversation", open_conversation="Aakash"))
    assert ws.belief_flips == 1
    assert ws.open_conversation == "Aakash"


def test_phase_advances_along_the_ladder():
    ws = _workspace()
    for phase in ("reach_source", "hunt_content", "act_on_content"):
        ws.commit(WorkspaceProposal(source="task_state", phase=phase, surface="conversation"))
    assert ws.phase == "act_on_content"
    assert ws.phase_regressions == 0


def test_unjustified_phase_regression_is_refused():
    ws = _workspace()
    ws.commit(WorkspaceProposal(source="task_state", phase="choose_destination"))
    verdict = ws.commit(WorkspaceProposal(source="model", phase="reach_source"))
    assert ws.phase == "choose_destination"
    assert "phase" in verdict.rejected_fields
    assert ws.phase_regressions == 0


def test_a_regression_the_screen_justifies_is_accepted_and_counted():
    ws = _workspace()
    ws.commit(WorkspaceProposal(source="task_state", phase="choose_destination"))
    verdict = ws.commit(
        WorkspaceProposal(
            source="task_state",
            phase="reach_source",
            allow_phase_regression=True,
            surface="chat_list",
        )
    )
    assert ws.phase == "reach_source"
    assert verdict.accepted("phase")
    assert ws.phase_regressions == 1


def test_a_goal_with_no_registered_ladder_accepts_any_phase():
    ws = _workspace(kind="filesystem_find")
    assert phase_ladder_for("filesystem_find") == ()
    ws.commit(WorkspaceProposal(source="domain", phase="scanning"))
    ws.commit(WorkspaceProposal(source="domain", phase="listing"))
    assert ws.phase == "listing"


def test_attempts_are_append_only_and_deduplicated():
    ws = _workspace()
    attempt = AttemptRecord(kind="search", action="type_query", text="charger", outcome="no_results")
    ws.commit(WorkspaceProposal(source="search", attempts=[attempt]))
    ws.commit(WorkspaceProposal(source="search", attempts=[attempt]))
    assert len(ws.attempts) == 1
    ws.commit(
        WorkspaceProposal(
            source="search",
            attempts=[AttemptRecord(kind="search", action="type_query", text="charger", outcome="one_result")],
        )
    )
    assert len(ws.attempts) == 2


def test_attempts_are_bounded():
    ws = _workspace()
    for i in range(80):
        ws.commit(
            WorkspaceProposal(
                source="execution",
                attempts=[AttemptRecord(kind="action", action="click", target=f"row-{i}")],
            )
        )
    assert len(ws.attempts) == 32
    assert ws.attempts[-1].target == "row-79"


def test_transitions_record_where_the_screen_went():
    ws = _workspace()
    ws.commit(
        WorkspaceProposal(
            source="transition",
            transitions=[
                TransitionRecord(
                    action="Click",
                    family="open_contact",
                    before_surface="chat_list",
                    after_surface="conversation",
                    outcome="progress",
                    progress_delta=0.3,
                )
            ],
        )
    )
    assert [t.after_surface for t in ws.transitions] == ["conversation"]


def test_intent_and_budgets_commit_through_the_same_door():
    ws = _workspace()
    ws.commit(
        WorkspaceProposal(
            source="executive",
            intent=Intent(objective="open the source chat", completion_predicate="conversation==ZarooratWala"),
            budgets={"max_steps": 12, "steps_used": 3},
        )
    )
    assert ws.intention.objective == "open the source chat"
    assert ws.budgets.steps_left == 9


def test_every_commit_is_explained():
    ws = _workspace()
    ws.commit(WorkspaceProposal(source="perception", surface="conversation", open_conversation="Pallavi"))
    ws.commit(WorkspaceProposal(source="model", surface="conversation", open_conversation=""))
    reasons = [d.reason for verdict in ws.commit_log for d in verdict.decisions]
    assert any("refuse to wipe" in reason for reason in reasons)


def test_legacy_search_entries_translate():
    records = attempts_from_legacy([{"q": "charger", "outcome": "no_results"}])
    assert records[0].kind == "search"
    assert records[0].text == "charger"


# ------------------------------------------------- ExecutionState migration


def test_search_attempt_log_is_a_view_of_the_workspace():
    state = ExecutionState()
    state.record_search_attempt("charger", "no_results")
    state.record_search_attempt("zarooratwala", "one_result")
    assert [entry["q"] for entry in state.search_attempt_log] == ["charger", "zarooratwala"]
    assert [a.text for a in state.workspace.attempts_of("search")] == ["charger", "zarooratwala"]


def test_search_attempt_log_has_no_second_store_to_drift_from():
    state = ExecutionState()
    state.record_search_attempt("charger", "no_results")
    state.workspace._attempts.clear()
    assert state.search_attempt_log == []


def test_executed_actions_land_in_the_workspace():
    state = ExecutionState()
    state.record(
        Action(action="Click", semantic_target="Pallavi", action_family="open_contact"),
        {"ok": True, "message": "clicked"},
    )
    attempts = state.workspace.attempts_of("action")
    assert [(a.action, a.target) for a in attempts] == [("open_contact", "Pallavi")]
    assert attempts[0].outcome.startswith("ok:")
    assert state.workspace.budgets.steps_used == 1


def test_the_world_document_renders_the_workspace_attempt():
    from plugin.agent.world_document import empty_document

    state = ExecutionState()
    state.unified_world_document = empty_document()
    state.record(
        Action(action="Click", semantic_target="Forward", action_family="forward_message"),
        {"ok": False, "message": "menu closed"},
    )
    attempts = state.unified_world_document["attempts"]
    assert attempts[-1]["action"] == "forward_message"
    assert attempts[-1]["result"].startswith("failed:")


def test_binding_a_goal_gives_the_workspace_its_ladder():
    from plugin.agent.executive.sync import bind_goal

    state = ExecutionState()
    bind_goal(state, Goal(kind="whatsapp_forward_message", contact="ZarooratWala", target_contact="Pallavi"))
    assert state.workspace.goal.subject == "ZarooratWala"
    assert state.workspace.ladder()[0] == "reach_source"


# ----------------------------------------------------------------- beliefs


def _fact(value: str, confidence: float) -> Claim:
    return Claim(value=value, confidence=confidence)


def test_a_new_fact_is_accepted_and_readable():
    ws = _workspace()
    ws.commit(WorkspaceProposal(source="perception", frame=1, facts={"active_app": _fact("WhatsApp", 0.9)}))
    assert ws.fact_value("active_app") == "WhatsApp"
    assert ws.fact("active_app").source == "perception"
    assert ws.contradictions == []


def test_the_same_value_reinforces_without_a_contradiction():
    ws = _workspace()
    ws.commit(WorkspaceProposal(source="perception", frame=1, facts={"surface": _fact("chat_list", 0.6)}))
    ws.commit(WorkspaceProposal(source="perception", frame=2, facts={"surface": _fact("chat_list", 0.9)}))
    assert ws.fact_value("surface") == "chat_list"
    assert ws.fact("surface").confidence == 0.9  # kept the more confident reading
    assert ws.contradictions == []


def test_an_empty_reading_never_erases_a_known_fact():
    ws = _workspace()
    ws.commit(WorkspaceProposal(source="perception", frame=1, facts={"call_state": _fact("ringing", 0.8)}))
    ws.commit(WorkspaceProposal(source="perception", frame=2, facts={"call_state": _fact("", 0.9)}))
    assert ws.fact_value("call_state") == "ringing"


def test_a_more_confident_conflict_flips_the_belief_and_is_recorded():
    ws = _workspace()
    ws.commit(WorkspaceProposal(source="shadow", frame=1, facts={"surface": _fact("chat_list", 0.5)}))
    ws.commit(WorkspaceProposal(source="vision", frame=2, facts={"surface": _fact("conversation", 0.9)}))
    assert ws.fact_value("surface") == "conversation"
    assert ws.belief_flips == 1
    contradiction = ws.contradictions[-1]
    assert contradiction.key == "surface"
    assert contradiction.prior == "chat_list"
    assert contradiction.proposed == "conversation"
    assert contradiction.resolution == "took_proposed"


def test_a_less_confident_conflict_keeps_the_prior_but_is_still_recorded():
    ws = _workspace()
    ws.commit(WorkspaceProposal(source="vision", frame=1, facts={"surface": _fact("conversation", 0.9)}))
    ws.commit(WorkspaceProposal(source="shadow", frame=2, facts={"surface": _fact("chat_list", 0.4)}))
    assert ws.fact_value("surface") == "conversation"  # prior held
    assert ws.contradictions[-1].resolution == "kept_prior"
    assert ws.unresolved_contradictions == []  # every contradiction is resolved one way or the other


def test_facts_and_contradictions_appear_in_the_snapshot():
    ws = _workspace()
    ws.commit(WorkspaceProposal(source="vision", frame=1, facts={"surface": _fact("conversation", 0.9)}))
    ws.commit(WorkspaceProposal(source="shadow", frame=2, facts={"surface": _fact("chat_list", 0.95)}))
    snap = ws.to_dict()
    assert snap["facts"]["surface"]["value"] == "chat_list"
    assert snap["contradictions"]
    assert snap["belief_flips"] == 1


def test_commit_beliefs_helper_drops_empty_values_and_arbitrates():
    from plugin.agent.executive.sync import commit_beliefs

    state = ExecutionState()
    commit_beliefs(state, source="perception", facts={"active_app": ("WhatsApp", 0.9), "surface": ""})
    assert state.workspace.fact_value("active_app") == "WhatsApp"
    # The empty surface was dropped before proposal, so no surface fact exists.
    assert state.workspace.fact("surface") is None


def test_a_fact_defaults_to_observed_status():
    ws = _workspace()
    ws.commit(WorkspaceProposal(source="perception", frame=1, facts={"surface": _fact("chat_list", 0.6)}))
    assert ws.fact("surface").status == "observed"


def test_a_facts_epistemic_status_is_carried_through_arbitration():
    ws = _workspace()
    ws.commit(
        WorkspaceProposal(
            source="model",
            frame=1,
            facts={"target_below_fold": Claim(value="likely", confidence=0.5, status="predicted")},
        )
    )
    assert ws.fact("target_below_fold").status == "predicted"


def test_an_invalid_status_falls_back_to_observed():
    ws = _workspace()
    ws.commit(
        WorkspaceProposal(
            source="model",
            frame=1,
            facts={"surface": Claim(value="chat_list", confidence=0.6, status="nonsense")},
        )
    )
    assert ws.fact("surface").status == "observed"


def test_commit_beliefs_helper_threads_status():
    from plugin.agent.executive.sync import commit_beliefs

    state = ExecutionState()
    commit_beliefs(state, source="model", facts={"below_fold": "likely"}, status="inferred")
    assert state.workspace.fact("below_fold").status == "inferred"


# ------------------------------------------------ goal contract (constraints)


def test_binding_a_goal_seeds_its_contract_into_the_workspace():
    from plugin.agent.executive.sync import bind_goal

    state = ExecutionState()
    bind_goal(state, Goal(kind="whatsapp_forward_message", contact="ZarooratWala", target_contact="Pallavi"))
    contract = state.workspace.goal
    # The task contract — what "done" means and what must hold — lives in the
    # one authoritative record, not only in a task-specific state object.
    assert contract.success_conditions
    assert any("irreversible" in c for c in contract.constraints)


def test_an_unknown_goal_has_an_empty_contract():
    from plugin.agent.executive.workspace import goal_contract_for

    assert goal_contract_for("filesystem_find") == {}


def test_a_domain_can_register_its_own_contract():
    from plugin.agent.executive.workspace import GoalState, register_goal_contract

    register_goal_contract(
        "slack_dm",
        success_conditions=("dm opened", "message sent"),
        constraints=("send is irreversible",),
    )
    seeded = GoalState.from_goal(Goal(kind="slack_dm"))
    assert seeded.success_conditions == ["dm opened", "message sent"]
    assert seeded.constraints == ["send is irreversible"]


# ------------------------------------------------------- object bindings


def test_a_resolved_binding_becomes_an_authoritative_fact():
    from plugin.agent.executive.sync import commit_bindings, has_resolved_binding

    state = ExecutionState()
    state.iteration = 4
    commit_bindings(
        state,
        bindings={
            "source_object": {"status": "resolved", "resolved_label": "the charger link", "confidence": 0.9},
            "destination_object": {"status": "unresolved"},
        },
    )
    assert state.workspace.fact_value("binding.source_object") == "the charger link"
    assert has_resolved_binding(state, "source_object")
    # An unresolved binding is represented by absence, not a fact that would flip.
    assert not has_resolved_binding(state, "destination_object")


def test_binding_status_maps_onto_epistemic_status():
    from plugin.agent.executive.sync import commit_bindings

    state = ExecutionState()
    commit_bindings(
        state,
        bindings={"source_object": {"status": "provisional", "resolved_entity_id": 42, "confidence": 0.7}},
    )
    claim = state.workspace.fact("binding.source_object")
    assert claim.value == "42"
    assert claim.status == "inferred"  # provisional is not yet observed


def test_a_provisional_binding_promoting_to_resolved_does_not_flip():
    from plugin.agent.executive.sync import commit_bindings

    state = ExecutionState()
    commit_bindings(
        state,
        bindings={"source_object": {"status": "provisional", "resolved_label": "charger link", "confidence": 0.6}},
    )
    commit_bindings(
        state,
        bindings={"source_object": {"status": "resolved", "resolved_label": "charger link", "confidence": 0.95}},
    )
    # Same value throughout: a status upgrade must not be recorded as a belief flip.
    assert state.workspace.belief_flips == 0
    assert state.workspace.fact("binding.source_object").status == "observed"


# --------------------------------------------------- goal-contract consultation


def _forward_contract_state() -> ExecutionState:
    from plugin.agent.executive.workspace import GoalState, goal_contract_for

    contract = goal_contract_for("whatsapp_forward_message")
    state = ExecutionState()
    state.workspace.goal = GoalState(
        kind="whatsapp_forward_message",
        success_conditions=list(contract["success_conditions"]),
        constraints=list(contract["constraints"]),
    )
    return state


def test_contract_status_is_empty_before_any_phase():
    from plugin.agent.executive.sync import contract_status

    state = _forward_contract_state()
    status = contract_status(state)
    # Nothing satisfied yet: every success condition is still pending.
    assert status["satisfied"] == []
    assert status["pending"] == status["success_conditions"]
    assert status["all_satisfied"] is False
    assert status["constraints"]  # the contract's constraints are surfaced


def test_contract_progress_tracks_phase_ladder():
    from plugin.agent.executive.sync import contract_status

    state = _forward_contract_state()
    state.workspace.commit(WorkspaceProposal(source="perception", phase="invoke_forward"))
    status = contract_status(state)
    # Mid-ladder: some conditions satisfied, some pending, not yet complete.
    assert status["satisfied"]
    assert status["pending"]
    assert status["all_satisfied"] is False


def test_contract_is_complete_at_the_terminal_phase():
    from plugin.agent.executive.sync import contract_status

    state = _forward_contract_state()
    state.workspace.commit(WorkspaceProposal(source="perception", phase="verified"))
    status = contract_status(state)
    assert status["pending"] == []
    assert status["all_satisfied"] is True


def test_contract_status_is_empty_without_a_contract():
    from plugin.agent.executive.sync import contract_status

    # A goal with no registered contract has nothing to consult.
    state = ExecutionState()
    assert contract_status(state).get("all_satisfied") in (False, None)
