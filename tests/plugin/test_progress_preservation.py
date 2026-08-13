"""Scoped invalidation: interaction failure must not erase established patient."""

from __future__ import annotations

from plugin.agent.capabilities.search_episode import meta_referent_search_signals
from plugin.agent.decision_consultation import (
    DecisionBrief,
    DecisionOutcome,
    TaskState,
    _content_search_locate_outcome,
    _patient_content_established,
)
from plugin.agent.executive.meta_action import MetaAction, MetaContext
from plugin.agent.executive.meta_consultation import sanitize_meta_choice
from plugin.agent.runtime.state import ExecutionState


def _patient_doc(query: str = "zarooratwala") -> dict:
    return {
        "surface": "conversation",
        "open_conversation": "Alice",
        "objects": [
            {
                "id": "msg_link_1",
                "kind": "link",
                "text": f"https://www.{query}.com/",
                "matches_goal": True,
            }
        ],
    }


def test_reveal_failure_preserves_established_patient():
    brief = DecisionBrief(
        goal={"source_query": "zarooratwala", "link_query": "zarooratwala"},
        world=_patient_doc(),
        capabilities=["locate_content", "reveal_actions", "select_content"],
        meta_action="search",
        task_state=TaskState(
            phase="act_on_content",
            source_chat_open=True,
            content_located=False,
            content_visible=True,
        ),
        reveal_episode_failed=True,
    )
    assert _patient_content_established(brief) is True
    prior = DecisionOutcome(
        ok=True,
        capability="reveal_actions",
        target="https://www.zarooratwala.com/",
        why="reveal after patient visible",
        confidence=0.9,
    )
    seal = _content_search_locate_outcome(brief, prior=prior)
    assert seal is None, "reveal failure must not reseal locate while patient known"


def test_failed_context_menu_repairs_affordance_before_retrieval():
    """Meta contract: SEARCH after reveal fail + patient known → affordance repair."""
    choice = sanitize_meta_choice(
        {"meta_action": "search", "why": "content unpaid", "confidence": 0.9},
        MetaContext(
            address_known=True,
            referent_search_needed=False,
            reveal_episode_failed=True,
            reveal_prefer_capability="select_content",
        ),
    )
    assert choice is not None
    assert choice.action is MetaAction.ACT
    assert choice.scores.get("forbid_search") == 1.0
    assert choice.scores.get("affordance_repair") == 1.0


def test_patient_disappeared_allows_retrieval_regression():
    """Only contradictory absence re-arms locate / SEARCH content debt."""
    brief = DecisionBrief(
        goal={"source_query": "zarooratwala", "link_query": "zarooratwala"},
        world={
            "surface": "conversation",
            "open_conversation": "Alice",
            "objects": [
                {"id": "m1", "kind": "message", "text": "hello", "matches_goal": False}
            ],
        },
        capabilities=["locate_content", "observe"],
        meta_action="search",
        task_state=TaskState(
            phase="hunt_content",
            source_chat_open=True,
            content_located=False,
            content_visible=False,
        ),
    )
    assert _patient_content_established(brief) is False
    seal = _content_search_locate_outcome(brief)
    assert seal is not None
    assert seal.capability == "locate_content"

    goal = type(
        "G",
        (),
        {
            "contact": "Alice",
            "link_query": "zarooratwala",
            "target_contact": "Bob",
        },
    )()
    state = ExecutionState()
    sig = meta_referent_search_signals(
        state,
        phase="hunt_content",
        source_chat_open=True,
        surface="conversation",
        goal=goal,
        content_located=False,
        document=brief.world,
    )
    assert sig["needed"] is True


def test_surface_change_invalidates_grounding_not_identity():
    """Patient still on-screen after overlay dismiss → keep identity, no locate."""
    # Context menu dismissed → conversation surface, URL still present.
    brief = DecisionBrief(
        goal={"source_query": "zarooratwala", "link_query": "zarooratwala"},
        world=_patient_doc(),
        capabilities=["locate_content", "reveal_actions", "select_content"],
        meta_action="search",
        task_state=TaskState(
            phase="act_on_content",
            source_chat_open=True,
            content_located=False,
            content_visible=True,
            referent_selected=False,  # grounding lost with overlay
        ),
        reveal_episode_failed=True,
    )
    assert _patient_content_established(brief) is True
    assert brief.task_state.referent_selected is False
    seal = _content_search_locate_outcome(
        brief,
        prior=DecisionOutcome(
            ok=False,
            capability="reveal_actions",
            target="https://www.zarooratwala.com/",
            why="context_menu absent",
        ),
    )
    assert seal is None

    goal = type(
        "G",
        (),
        {
            "contact": "Alice",
            "link_query": "zarooratwala",
            "target_contact": "Bob",
        },
    )()
    sig = meta_referent_search_signals(
        ExecutionState(),
        phase="act_on_content",
        source_chat_open=True,
        surface="conversation",
        goal=goal,
        content_located=False,
        document=brief.world,
    )
    assert sig["needed"] is False, "on-screen patient clears SEARCH debt"


def test_visible_patient_clears_content_search_debt_without_content_located_flag():
    goal = type(
        "G",
        (),
        {
            "contact": "Alice",
            "link_query": "zarooratwala",
            "target_contact": "Bob",
        },
    )()
    sig = meta_referent_search_signals(
        ExecutionState(),
        phase="hunt_content",
        source_chat_open=True,
        surface="conversation",
        goal=goal,
        content_located=False,
        document=_patient_doc(),
    )
    assert sig["needed"] is False
