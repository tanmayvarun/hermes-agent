"""MetaAction.SEARCH owns find-among-many; ACT commits after chosen."""

from __future__ import annotations

from plugin.agent.capabilities.search_episode import (
    complete_search_choice,
    meta_referent_search_signals,
    start_search_episode,
)
from plugin.agent.executive.meta_action import MetaAction, MetaChoice, MetaContext
from plugin.agent.executive.meta_consultation import sanitize_meta_choice
from plugin.agent.runtime.state import ExecutionState


def test_meta_action_search_exists_and_may_actuate():
    from plugin.agent.executive.meta_action import MetaChoice

    choice = MetaChoice(MetaAction.SEARCH, "find among many")
    assert choice.may_actuate
    assert MetaAction.SEARCH.value == "search"
    assert MetaAction.SEARCH in list(MetaAction)


def test_sanitize_rewrites_act_to_search_when_referent_search_owed():
    ctx = MetaContext(
        referent_search_needed=True,
        search_episode_incomplete=True,
        search_episode_complete=False,
    )
    choice = sanitize_meta_choice(
        {"meta_action": "act", "why": "open row", "confidence": 0.9},
        ctx,
    )
    assert choice is not None
    assert choice.action is MetaAction.SEARCH
    assert "search" in choice.reason.lower() or "contract" in choice.reason.lower()


def test_sanitize_allows_act_when_search_complete():
    ctx = MetaContext(
        referent_search_needed=False,
        search_episode_incomplete=False,
        search_episode_complete=True,
        has_grounded_action=True,
    )
    choice = sanitize_meta_choice(
        {"meta_action": "act", "why": "open chosen", "confidence": 0.9},
        ctx,
    )
    assert choice is not None
    assert choice.action is MetaAction.ACT


def test_sanitize_keeps_housekeeping_act_under_search_owed():
    from plugin.agent.executive.meta_situation import MetaSituation

    ctx = MetaContext(
        referent_search_needed=True,
        search_episode_incomplete=True,
    )
    sit = MetaSituation(
        blockers={"storage_pressure": True},
        housekeeping_capabilities=[{"name": "relieve_host_storage"}],
    )
    choice = sanitize_meta_choice(
        {
            "meta_action": "act",
            "capability": "relieve_host_storage",
            "why": "storage",
            "confidence": 0.8,
        },
        ctx,
        situation=sit,
    )
    assert choice is not None
    assert choice.action is MetaAction.ACT
    assert choice.capability == "relieve_host_storage"


def test_referent_search_signals_needed_on_reach_source():
    state = ExecutionState()
    goal = type(
        "G",
        (),
        {"contact": "Pallavi", "link_query": "zarooratwala", "target_contact": "Tanmay"},
    )()
    sig = meta_referent_search_signals(
        state,
        phase="reach_source",
        source_chat_open=False,
        surface="chat_list",
        goal=goal,
    )
    assert sig["needed"] is True
    assert sig["complete"] is False


def test_referent_search_signals_reads_goal_state_fields():
    """Workspace GoalState uses subject/query — must still arm needed (live 165649)."""
    from plugin.agent.executive.workspace import GoalState

    state = ExecutionState()
    gs = GoalState(
        kind="whatsapp_forward_message",
        subject="Pallavi",
        query="zarooratwala",
        destination="Tanmay",
    )
    sig = meta_referent_search_signals(
        state,
        phase="open_source",
        source_chat_open=False,
        surface="chat_list",
        goal=gs,
    )
    assert sig["needed"] is True
    assert sig["contact"] == "Pallavi"
    assert sig["link_query"] == "zarooratwala"


def test_referent_search_signals_complete_clears_needed():
    state = ExecutionState()
    start_search_episode(state, referent="zarooratwala", query="zarooratwala", status="ranking")
    complete_search_choice(state, chosen_label="https://www.zarooratwala.com/")
    goal = type(
        "G",
        (),
        {"contact": "Pallavi", "link_query": "zarooratwala", "target_contact": "Tanmay"},
    )()
    sig = meta_referent_search_signals(
        state,
        phase="reach_source",
        source_chat_open=False,
        surface="search",
        goal=goal,
    )
    assert sig["complete"] is True
    assert sig["needed"] is False


def test_participant_header_is_not_source_identity():
    """Group membership CSV must not count as opening the contact (live 214626)."""
    from plugin.agent.capabilities.resolve_entity import open_matches_referent

    assert open_matches_referent("Pallavi, Papaji, Rekha, You", "Pallavi") is False
    assert open_matches_referent("Pallavi", "Pallavi") is True


def test_content_hunt_search_owed_when_source_open_but_query_unpaid():
    """Container open ≠ content found — SEARCH still owns unpaid link_query."""
    state = ExecutionState()
    goal = type(
        "G",
        (),
        {"contact": "Pallavi", "link_query": "zarooratwala", "target_contact": "Tanmay"},
    )()
    sig = meta_referent_search_signals(
        state,
        phase="hunt_content",
        source_chat_open=True,
        surface="conversation",
        goal=goal,
        content_located=False,
    )
    assert sig["needed"] is True
    sig_done = meta_referent_search_signals(
        state,
        phase="hunt_content",
        source_chat_open=True,
        surface="conversation",
        goal=goal,
        content_located=True,
    )
    assert sig_done["needed"] is False


def test_sanitize_rewrites_search_to_backtrack_when_retreat_owed():
    """Empty/zero-progress find must leave the branch before re-SEARCH."""
    ctx = MetaContext(
        referent_search_needed=True,
        search_episode_failed=True,
        search_retreat_owed=True,
        search_episode_complete=False,
    )
    choice = sanitize_meta_choice(
        {"meta_action": "search", "why": "try again", "confidence": 0.9},
        ctx,
    )
    assert choice is not None
    assert choice.action is MetaAction.EXPLORE
    assert "contract" in choice.reason.lower() or "progress" in choice.reason.lower()


def test_sanitize_does_not_force_search_while_retreat_owed():
    ctx = MetaContext(
        referent_search_needed=True,
        search_episode_failed=True,
        search_retreat_owed=True,
        search_episode_incomplete=False,
        search_episode_complete=False,
    )
    choice = sanitize_meta_choice(
        {"meta_action": "act", "why": "open something", "confidence": 0.9},
        ctx,
    )
    assert choice is not None
    assert choice.action is MetaAction.ACT


def test_empty_find_fails_episode_and_sets_retreat():
    from plugin.agent.capabilities.search_episode import (
        fail_search_episode,
        start_search_episode,
    )

    state = ExecutionState()
    start_search_episode(
        state, referent="Pallavi", query="zarooratwala Pallavi", status="retrieving"
    )
    ep = fail_search_episode(state, reason="empty_candidate_set")
    assert ep["status"] == "failed"
    assert state.search_retreat_owed is True
    assert state.last_search_progress and state.last_search_progress.get("empty")
    sig = meta_referent_search_signals(
        state,
        phase="reach_source",
        source_chat_open=False,
        surface="chat_list",
        goal=type("G", (), {"contact": "Pallavi", "link_query": "zarooratwala"})(),
    )
    assert sig["failed"] is True
    assert sig["retreat_owed"] is True


def test_decision_under_search_meta_forbids_open():
    from plugin.agent.decision_consultation import (
        DecisionBrief,
        TaskState,
        sanitize_decision,
    )

    # Include open_entity in the list so sanitize hits the SEARCH forbid gate
    # (not merely "unknown capability").
    brief = DecisionBrief(
        goal={"source_conversation": "Pallavi", "source_query": "zarooratwala"},
        world={"surface": "search", "objects": [{"text": "Pallavi"}]},
        task_state=TaskState(phase="reach_source", search_query="zarooratwala"),
        capabilities=[
            "compose_search_query",
            "resolve_entity",
            "observe",
            "open_entity",
        ],
        candidates=["Pallavi"],
        meta_action="search",
        search_episode={"status": "ranking", "candidate_count": 2},
    )
    rejected = sanitize_decision(
        {"capability": "open_entity", "target": "Pallavi", "why": "click"},
        brief,
    )
    assert not rejected.ok
    assert "search meta" in rejected.why.lower() or "forbids" in rejected.why.lower()


def test_search_intent_result_stamped_on_episode():
    from plugin.agent.capabilities.search_episode import (
        SearchIntent,
        SearchResult,
        fail_search_episode,
        search_intent_from_episode,
        search_result_from_episode,
    )

    state = ExecutionState()
    start_search_episode(
        state, referent="Pallavi", query="zarooratwala Pallavi", space="ui_filter"
    )
    ep = state.search_episode or {}
    assert "intent" in ep and "result" in ep
    intent = search_intent_from_episode(ep)
    assert isinstance(intent, SearchIntent)
    assert intent.sought == "Pallavi"
    assert "zarooratwala" in intent.criteria
    fail_search_episode(state, reason="empty_candidate_set")
    result = search_result_from_episode(state.search_episode, exhausted=True)
    assert isinstance(result, SearchResult)
    assert result.exhausted is True
    assert result.unexplored_scopes
    assert "explored_scopes" in (result.coverage or {})


def test_sanitize_search_without_criteria_becomes_explore():
    choice = sanitize_meta_choice(
        {"meta_action": "search", "why": "how do I Forward?", "confidence": 0.9},
        MetaContext(search_has_criteria=False),
    )
    assert choice is not None
    assert choice.action is MetaAction.EXPLORE


def test_probe_parses_to_explore():
    choice = sanitize_meta_choice(
        {"meta_action": "explore", "why": "reveal menu", "confidence": 0.8},
        MetaContext(),
    )
    assert choice is not None
    assert choice.action is MetaAction.EXPLORE
    assert MetaChoice(MetaAction.EXPLORE, "x").may_actuate


def test_explore_meta_forbids_compose():
    from plugin.agent.decision_consultation import (
        DecisionBrief,
        TaskState,
        sanitize_decision,
    )

    brief = DecisionBrief(
        goal={"source_conversation": "Pallavi"},
        world={"surface": "conversation", "objects": []},
        task_state=TaskState(phase="act_on_content"),
        capabilities=["reveal_actions", "observe", "compose_search_query"],
        meta_action="explore",
    )
    rejected = sanitize_decision(
        {"capability": "compose_search_query", "target": "q", "why": "type"},
        brief,
    )
    assert not rejected.ok
    assert "explore" in rejected.why.lower()


def test_retrieve_ready_rewrites_search_to_act():
    choice = sanitize_meta_choice(
        {"meta_action": "search", "why": "open known chat", "confidence": 0.9},
        MetaContext(retrieve_ready=True, address_known=True),
    )
    assert choice is not None
    assert choice.action is MetaAction.ACT


def test_verify_folds_to_perceive():
    choice = sanitize_meta_choice(
        {"meta_action": "perceive", "why": "check done", "confidence": 0.8},
        MetaContext(),
    )
    assert choice is not None
    assert choice.action is MetaAction.PERCEIVE


def test_address_known_clears_search_needed_when_content_located():
    """content_located alone is not retrieve_ready — need SearchResult.chosen."""
    state = ExecutionState()
    goal = type(
        "G",
        (),
        {"contact": "Pallavi", "link_query": "zarooratwala", "target_contact": "Tanmay"},
    )()
    soft = meta_referent_search_signals(
        state,
        phase="hunt_content",
        source_chat_open=True,
        surface="conversation",
        goal=goal,
        content_located=True,
    )
    assert soft["address_known"] is True
    assert soft["retrieve_ready"] is False
    assert "intent" in soft and "result" in soft

    state.search_episode = {
        "status": "complete",
        "chosen_label": "https://example.com/x",
        "role": "content",
        "referent": "zarooratwala",
        "query": "zarooratwala",
    }
    sig = meta_referent_search_signals(
        state,
        phase="hunt_content",
        source_chat_open=True,
        surface="conversation",
        goal=goal,
        content_located=True,
    )
    assert sig["retrieve_ready"] is True
    assert sig["needed"] is False
