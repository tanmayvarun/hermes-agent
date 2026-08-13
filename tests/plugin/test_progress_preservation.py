"""Scoped invalidation: preserve earned patient progress; absence ≠ contradiction."""

from __future__ import annotations

from plugin.agent.capabilities.search_episode import meta_referent_search_signals
from plugin.agent.decision_consultation import (
    DecisionBrief,
    DecisionOutcome,
    TaskState,
    _content_search_locate_outcome,
    _earned_patient_ref,
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


def _earned_content_episode(label: str = "https://www.zarooratwala.com/") -> dict:
    return {
        "status": "complete",
        "role": "content",
        "chosen_label": label,
        "retrieval_complete": True,
        "choice_confidence": "provisional",
        "selection_path": "rank",
    }


def test_reveal_failure_preserves_established_patient():
    """Earned retrieval patient survives reveal failure — no locate reseal."""
    brief = DecisionBrief(
        goal={
            "source_conversation": "Alice",
            "source_query": "zarooratwala",
            "link_query": "zarooratwala",
        },
        world=_patient_doc(),
        capabilities=["locate_content", "reveal_actions", "select_content"],
        meta_action="search",
        task_state=TaskState(
            phase="act_on_content",
            source_chat_open=True,
            content_located=True,
            content_visible=True,
        ),
        search_episode=_earned_content_episode(),
        reveal_episode_failed=True,
    )
    assert _patient_content_established(brief) is True
    assert _earned_patient_ref(brief) == "https://www.zarooratwala.com/"
    prior = DecisionOutcome(
        ok=True,
        capability="reveal_actions",
        target="https://www.zarooratwala.com/",
        why="reveal after patient earned",
        confidence=0.9,
    )
    seal = _content_search_locate_outcome(brief, prior=prior)
    assert seal is None, "reveal failure must not reseal locate while patient earned"


def test_mere_query_visibility_does_not_establish_patient():
    """document_locates / phase alone must not invent patient commitment."""
    brief = DecisionBrief(
        goal={"source_query": "zarooratwala", "link_query": "zarooratwala"},
        world=_patient_doc(),
        capabilities=["locate_content", "reveal_actions"],
        meta_action="search",
        task_state=TaskState(
            phase="act_on_content",
            source_chat_open=True,
            content_located=False,
            content_visible=True,
        ),
    )
    assert _patient_content_established(brief) is False
    seal = _content_search_locate_outcome(brief)
    assert seal is not None
    assert seal.capability == "locate_content"


def test_failed_context_menu_repairs_affordance_before_retrieval():
    """Meta: reveal fail + earned patient ref → affordance repair, not SEARCH."""
    choice = sanitize_meta_choice(
        {"meta_action": "search", "why": "content unpaid", "confidence": 0.9},
        MetaContext(
            address_known=True,
            referent_search_needed=False,
            reveal_episode_failed=True,
            reveal_prefer_capability="select_content",
            established_patient_ref="https://www.zarooratwala.com/",
        ),
    )
    assert choice is not None
    assert choice.action is MetaAction.ACT
    assert choice.scores.get("forbid_search") == 1.0
    assert choice.scores.get("affordance_repair") == 1.0
    assert choice.scores.get("established_patient_ref") == 1.0


def test_reveal_failed_without_earned_patient_does_not_suppress_search():
    """Generic reveal_failed alone must not forbid SEARCH."""
    choice = sanitize_meta_choice(
        {"meta_action": "search", "why": "still hunting", "confidence": 0.9},
        MetaContext(
            address_known=True,
            referent_search_needed=True,
            reveal_episode_failed=True,
            established_patient_ref="",
        ),
    )
    assert choice is not None
    assert choice.action is MetaAction.SEARCH


def test_patient_temporarily_not_visible_preserves_semantic_binding():
    """Scroll-away absence must not erase earned patient / re-arm locate."""
    brief = DecisionBrief(
        goal={
            "source_conversation": "Alice",
            "source_query": "zarooratwala",
            "link_query": "zarooratwala",
        },
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
            phase="act_on_content",
            source_chat_open=True,
            content_located=True,
            content_visible=False,
        ),
        search_episode=_earned_content_episode(),
    )
    assert _patient_content_established(brief) is True
    seal = _content_search_locate_outcome(brief)
    assert seal is None


def test_patient_grounding_lost_allows_reground():
    """Lost selection/geometry invalidates grounding, not semantic identity."""
    brief = DecisionBrief(
        goal={
            "source_conversation": "Alice",
            "source_query": "zarooratwala",
            "link_query": "zarooratwala",
        },
        world=_patient_doc(),
        capabilities=["locate_content", "reveal_actions", "select_content"],
        meta_action="search",
        task_state=TaskState(
            phase="act_on_content",
            source_chat_open=True,
            content_located=True,
            content_visible=True,
            referent_selected=False,
        ),
        search_episode=_earned_content_episode(),
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


def test_explicit_patient_identity_contradiction_allows_retrieval_regression():
    """Container change / content episode exhaustion re-arms locate."""
    brief = DecisionBrief(
        goal={
            "source_conversation": "Alice",
            "source_query": "zarooratwala",
            "link_query": "zarooratwala",
        },
        world={
            "surface": "conversation",
            "open_conversation": "Bob",  # container contradicted
            "objects": [],
        },
        capabilities=["locate_content", "observe"],
        meta_action="search",
        task_state=TaskState(
            phase="act_on_content",
            source_chat_open=True,
            content_located=True,
            open_conversation="Bob",
        ),
        search_episode={
            **_earned_content_episode(),
            "status": "exhausted",
            "fail_reason": "required_role_constraint_mismatch",
        },
    )
    assert _patient_content_established(brief) is False
    seal = _content_search_locate_outcome(brief)
    assert seal is not None
    assert seal.capability == "locate_content"


def test_visible_query_text_does_not_clear_content_search_debt():
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
    assert sig["needed"] is True
    assert not sig.get("content_retrieval_earned")


def test_earned_content_located_clears_search_debt():
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
        content_located=True,
        document=_patient_doc(),
    )
    assert sig["needed"] is False
    assert sig.get("content_retrieval_earned") is True


def test_reveal_failure_does_not_transfer_progress_to_similar_patient():
    """Earned patient A survives; visible similar B must not steal recovery."""
    patient_a = "https://www.zarooratwala.com/"
    patient_b = "https://www.instagram.com/zarooratwala"
    brief = DecisionBrief(
        goal={
            "source_conversation": "Alice",
            "source_query": "zarooratwala",
            "link_query": "zarooratwala",
        },
        world={
            "surface": "conversation",
            "open_conversation": "Alice",
            "objects": [
                {
                    "id": "msg_b",
                    "kind": "link",
                    "text": patient_b,
                    "matches_goal": True,
                }
            ],
        },
        capabilities=["locate_content", "reveal_actions", "select_content"],
        meta_action="search",
        task_state=TaskState(
            phase="act_on_content",
            source_chat_open=True,
            content_located=True,
            content_visible=True,
        ),
        search_episode=_earned_content_episode(patient_a),
        reveal_episode_failed=True,
    )
    assert _earned_patient_ref(brief) == patient_a
    assert _patient_content_established(brief) is True
    # Reveal failure on A must not reseal locate just because B is attractive.
    seal = _content_search_locate_outcome(
        brief,
        prior=DecisionOutcome(
            ok=False,
            capability="reveal_actions",
            target=patient_a,
            why="context_menu absent on A",
        ),
    )
    assert seal is None
    # Meta recovery stays scoped to A; B's visibility alone is not authority.
    choice = sanitize_meta_choice(
        {"meta_action": "search", "why": "B looks like query", "confidence": 0.9},
        MetaContext(
            address_known=True,
            referent_search_needed=False,
            reveal_episode_failed=True,
            reveal_prefer_capability="select_content",
            established_patient_ref=patient_a,
        ),
    )
    assert choice is not None
    assert choice.action is MetaAction.ACT
    assert choice.scores.get("established_patient_ref") == 1.0
    assert choice.scores.get("forbid_search") == 1.0
