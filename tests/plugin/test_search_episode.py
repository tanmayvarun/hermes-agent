"""Search episode: query → filter/rank before commit."""

from __future__ import annotations

from plugin.agent.capabilities.search_episode import (
    filter_search_candidates,
    note_find_stage_outcome,
    search_continue_capability,
    start_search_episode,
    unique_fitting_candidate,
)
from plugin.agent.decision_consultation import (
    DecisionBrief,
    TaskState,
    apply_decision_consultation,
)
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.unified_cognition import UnifiedProposal


def test_echo_demoted_when_url_fit_exists():
    rows = [
        {"label": "Pallavi: You: zarooratwala Pallavi (Yesterday)", "matches_goal": True},
        {"label": "zarooratwala.com", "matches_goal": True},
        {"label": "Pallavi", "matches_goal": False},
    ]
    filtered = filter_search_candidates(
        rows,
        referent="zarooratwala",
        query="zarooratwala",
        evidence_tokens=["zarooratwala", "Pallavi"],
    )
    labels = [r["label"] for r in filtered]
    assert "zarooratwala.com" in labels
    assert not any("You: zarooratwala" in lab for lab in labels)


def test_unique_fit_completes_and_opens():
    state = ExecutionState()
    brief = DecisionBrief(
        goal={
            "source_conversation": "Pallavi",
            "source_query": "zarooratwala",
            "destination": "Tanmay",
        },
        world={
            "surface": "search",
            "objects": [
                {
                    "id": "row1",
                    "kind": "chat_row",
                    "text": "Pallavi https://www.zarooratwala.com/?x=1",
                    "matches_goal": True,
                    "sender": "Pallavi",
                }
            ],
        },
        task_state=TaskState(
            phase="reach_source",
            search_query="zarooratwala",
            source_chat_open=False,
        ),
        capabilities=["open_entity", "resolve_entity", "observe", "search"],
    )
    cap, tgt, why = search_continue_capability(state, brief)
    assert cap == "open_entity"
    assert "zarooratwala.com" in tgt.lower()
    assert state.search_episode and state.search_episode.get("status") == "complete"


def test_unique_self_authored_vs_required_sender_does_not_auto_commit():
    """You: URL with required Pallavi originator is a hard relation contradiction."""
    state = ExecutionState()
    brief = DecisionBrief(
        goal={
            "source_conversation": "Pallavi",
            "source_query": "zarooratwala",
            # Typed sent_by — must not be invented from source_conversation alone.
            "originator": "Pallavi",
        },
        world={
            "surface": "search",
            "objects": [
                {
                    "id": "row1",
                    "kind": "chat_row",
                    "text": "You: https://www.zarooratwala.com/?x=1",
                    "matches_goal": True,
                }
            ],
        },
        task_state=TaskState(
            phase="reach_source",
            search_query="zarooratwala",
        ),
        capabilities=["open_entity", "resolve_entity", "observe", "search"],
    )
    cap, tgt, why = search_continue_capability(state, brief)
    assert cap != "open_entity" or "you:" not in (tgt or "").lower()
    assert state.search_episode
    assert state.search_episode.get("status") in {"exhausted", "ranking", "failed"}


def test_multi_candidate_does_not_open_echo():
    state = ExecutionState()
    start_search_episode(
        state,
        role="content",
        referent="zarooratwala",
        query="zarooratwala",
        status="ranking",
    )
    brief = DecisionBrief(
        goal={
            "source_conversation": "Pallavi",
            "source_query": "zarooratwala",
        },
        world={
            "surface": "search",
            "objects": [
                {
                    "text": "Pallavi: You: zarooratwala Pallavi (Yesterday)",
                    "matches_goal": True,
                },
                {"text": "https://www.zarooratwala.com/fresh", "matches_goal": True},
                {"text": "Zarooratwala Shop", "matches_goal": True},
            ],
        },
        task_state=TaskState(
            phase="reach_source",
            search_query="zarooratwala",
        ),
        capabilities=["open_entity", "resolve_entity", "observe", "search"],
        search_episode=dict(state.search_episode or {}),
    )
    cap, tgt, _why = search_continue_capability(state, brief)
    assert cap in {"open_entity", "resolve_entity", "search"}
    if cap == "open_entity":
        assert "you: zarooratwala" not in tgt.lower()
        assert "zarooratwala.com" in tgt.lower() or "http" in tgt.lower()


def test_observe_on_search_promotes_ranked_not_thrash():
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    doc = {
        "surface": "search",
        "objects": [
            {
                "id": "row1",
                "kind": "chat_row",
                "text": "Pallavi https://www.zarooratwala.com/?...",
                "point": [308, 355],
                "matches_goal": True,
                "sender": "Pallavi",
            }
        ],
    }

    class _Observe:
        def choose(self, system: str, packet: dict) -> dict:
            return {
                "capability": "observe",
                "target": "",
                "why": "model_requested_observe",
                "confidence": 0.4,
            }

    proposal = UnifiedProposal(
        observed_state={"surface": "search"},
        world_model=dict(doc),
        next_action={},
        confidence=0.9,
    )
    state = ExecutionState()
    state.unified_world_document = dict(doc)
    apply_decision_consultation(
        proposal,
        goal,
        features=StateFeatures(extras={"wa_screen": "SEARCH", "search_query": "zarooratwala"}),
        chooser=_Observe(),
        execution_state=state,
    )
    assert proposal.next_action.get("family") == "open_entity"
    assert "zarooratwala" in str(proposal.next_action.get("text") or "").lower()


def test_unique_fitting_helper():
    rows = [{"label": "https://www.zarooratwala.com/a"}]
    u = unique_fitting_candidate(
        rows, referent="zarooratwala", evidence_tokens=["zarooratwala"]
    )
    assert u is not None


def test_committed_query_with_search_empty_fails_episode():
    """Generic empty find closes the episode so meta must retreat (not re-compose)."""
    from plugin.agent.capabilities.search_episode import (
        ensure_search_episode_from_brief,
        start_search_episode,
    )

    state = ExecutionState()
    start_search_episode(
        state,
        referent="Pallavi",
        query="zarooratwala Pallavi",
        status="retrieving",
    )
    brief = DecisionBrief(
        goal={
            "source_conversation": "Pallavi",
            "source_query": "zarooratwala",
        },
        world={"surface": "chat_list", "search_empty": True, "objects": []},
        task_state=TaskState(
            phase="reach_source",
            search_query="zarooratwala Pallavi",
            search_empty=True,
        ),
        capabilities=["compose_search_query", "observe"],
    )
    ep = ensure_search_episode_from_brief(state, brief)
    assert ep.get("status") == "failed"
    assert ep.get("fail_reason") == "empty_candidate_set"
    assert state.search_retreat_owed is True


def test_branch_fitness_empty_find_no_goal_evidence():
    from plugin.agent.capabilities.branch_fitness import compute_branch_fitness
    from plugin.agent.goal import Goal

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        link_query="zarooratwala",
        target_contact="Tanmay",
    )
    fit = compute_branch_fitness(
        {
            "surface": "chat_list",
            "search_empty": True,
            "search_query": "zarooratwala Pallavi",
            "objects": [],
        },
        goal=goal,
    )
    assert fit["admissible"] is False
    assert "empty_find_no_goal_evidence" in fit["reasons"]


def test_stale_compose_search_does_not_arm_retreat():
    """Live 202457: Chrome stole focus; compose refused — not a failed find."""
    state = ExecutionState()
    start_search_episode(
        state,
        role="source",
        referent="Pallavi",
        query="",
        status="querying",
        reason="compose_pending",
    )
    note_find_stage_outcome(
        state,
        family="compose_search_query",
        ok=False,
        message=(
            "perception_invalid: refused stale click on 'Search': "
            "'Google Chrome' holds the foreground, not 'WhatsApp'"
        ),
    )
    assert state.search_retreat_owed is False
    ep = state.search_episode or {}
    assert ep.get("status") != "failed"
