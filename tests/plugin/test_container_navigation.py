"""Content-hit ≠ container identity; NAVIGATION_MISMATCH after wrong open."""

from __future__ import annotations

from plugin.agent.capabilities.search_episode import (
    exclude_role_rejected_candidates,
    reject_navigation_mismatch_candidate,
)
from plugin.agent.decision_consultation import (
    DecisionBrief,
    NavigationInfo,
    TaskState,
    _stamp_open_navigation_semantics,
    sanitize_decision,
)
from plugin.agent.executive.intention_frame import FailureClass
from plugin.agent.procedures.forward_message import (
    action_open_semantics,
    looks_like_content_evidence_hit,
    looks_like_container_open_target,
)
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.world_critic import _label_looks_like_menu_verb


def test_content_hit_does_not_imply_container_identity():
    hit = "You: https://www.zarooratwala.com/?utm_source=ig..."
    assert looks_like_content_evidence_hit(target=hit) is True
    assert looks_like_container_open_target(target=hit) is False
    sem = action_open_semantics(
        "open_entity",
        phase="OPEN_SOURCE",
        target=hit,
        target_kind="search_result",
    )
    assert sem["is_navigation"] is True
    assert sem.get("content_hit_not_container") is True
    assert sem["target_role"] == ""  # click is not a container claim
    assert "source_container" in sem["establishes_roles"]


def test_navigation_mismatch_recovery_does_not_retry_same_method():
    from plugin.agent.executive.intention_frame import (
        FailureClass,
        Intention,
        IntentionFrame,
        MethodOutcome,
        RecoveryAction,
        recommend_recovery,
    )

    frame = IntentionFrame(
        intention=Intention(id="i1", objective="open source", success_predicate="p")
    )
    assert (
        recommend_recovery(
            frame,
            failure_class=FailureClass.NAVIGATION_MISMATCH.value,
            method_outcome=MethodOutcome.UNEXPECTED_EFFECT.value,
        )
        == RecoveryAction.RETURN_TO_EXECUTIVE.value
    )


def test_search_hit_opening_wrong_container_is_navigation_mismatch():
    """Stamp types the open so settle can classify NAVIGATION_MISMATCH."""
    from plugin.agent.decision_consultation import DecisionOutcome

    brief = DecisionBrief(
        goal={"contact": "Pallavi", "source_query": "zarooratwala"},
        world={
            "surface": "search",
            "objects": [
                {
                    "id": "r1",
                    "kind": "search_result",
                    "text": "You: https://www.zarooratwala.com/",
                }
            ],
            "forward_task": {"derived_phase": "OPEN_SOURCE"},
        },
        task_state=TaskState(phase="reach_source", source_chat_open=False),
        capabilities=["open_entity", "observe"],
        meta_action="act",
    )
    outcome = DecisionOutcome(
        ok=True,
        capability="open_entity",
        target="You: https://www.zarooratwala.com/",
        why="search complete; explore/open chosen hypothesis",
        realization="search_commit_chosen",
    )
    typed = _stamp_open_navigation_semantics(outcome, brief)
    assert typed.legacy_semantics is False
    assert typed.action_is_navigation is True
    assert "source_container" in typed.establishes_roles
    assert FailureClass.NAVIGATION_MISMATCH.value == "navigation_mismatch"


def test_wrong_transition_invalidates_candidate_for_context_establishment():
    state = ExecutionState()
    state.search_episode = {
        "status": "complete",
        "chosen_label": "You: https://www.zarooratwala.com/",
        "chosen_id": "r1",
        "role": "content",
        "retrieval_complete": True,
    }
    out = reject_navigation_mismatch_candidate(
        state,
        click_label="You: https://www.zarooratwala.com/",
        observed_container="ZarooratWala - Fresh Groceries Delivered",
        required_container="Pallavi",
        candidate_id="r1",
    )
    assert out.get("rejected") is True
    ep = state.search_episode
    assert "You: https://www.zarooratwala.com/" in (ep.get("role_rejected_labels") or [])
    surviving = exclude_role_rejected_candidates(
        [
            {
                "id": "r1",
                "label": "You: https://www.zarooratwala.com/",
                "text": "You: https://www.zarooratwala.com/",
            }
        ],
        ep,
    )
    assert surviving == []


def test_same_navigation_mismatch_is_not_retried_without_new_evidence():
    brief = DecisionBrief(
        goal={"contact": "Pallavi", "source_query": "zarooratwala"},
        world={"surface": "search", "objects": []},
        task_state=TaskState(phase="reach_source", source_chat_open=False),
        capabilities=["open_entity", "observe", "reveal_actions"],
        meta_action="act",
        search_episode={
            "status": "ranking",
            "role_rejected_labels": ["You: https://www.zarooratwala.com/"],
            "role_rejected_reasons": [
                "navigation_mismatch:expected='Pallavi':observed='ZarooratWala'"
            ],
        },
    )
    rejected = sanitize_decision(
        {
            "capability": "open_entity",
            "target": "You: https://www.zarooratwala.com/",
            "why": "retry same hit",
            "confidence": 0.9,
        },
        brief,
    )
    assert rejected.ok is False
    assert "NAVIGATION_MISMATCH" in rejected.why


def test_world_container_contradiction_clears_task_container_binding():
    """task_state.source_chat_open must follow authoritative open_conversation."""
    from plugin.agent.decision_consultation import task_state_from_context
    from types import SimpleNamespace

    goal = SimpleNamespace(
        contact="Pallavi",
        link_query="zarooratwala",
        target_contact="Tanmay",
        originator="",
    )
    # Document says ZarooratWala — must not report Pallavi source open.
    ts = task_state_from_context(
        goal,
        world_document={
            "surface": "conversation",
            "open_conversation": "ZarooratWala - Fresh Groceries Delivered",
        },
        features=SimpleNamespace(
            conversation_open=True,
            extras={},
        ),
    )
    assert ts.source_chat_open is False
    assert "ZarooratWala" in ts.open_conversation


def test_reveal_requires_verified_source_container():
    brief = DecisionBrief(
        goal={"contact": "Pallavi", "source_query": "zarooratwala"},
        world={
            "surface": "conversation",
            "open_conversation": "ZarooratWala - Fresh Groceries Delivered",
        },
        task_state=TaskState(
            phase="hunt_content",
            source_chat_open=False,
            open_conversation="ZarooratWala - Fresh Groceries Delivered",
            content_located=False,
        ),
        capabilities=["reveal_actions", "open_entity", "observe"],
        meta_action="act",
        navigation=NavigationInfo(surface="conversation"),
    )
    out = sanitize_decision(
        {
            "capability": "reveal_actions",
            "target": "You: https://www.zarooratwala.com/",
            "why": "forward",
            "confidence": 0.95,
        },
        brief,
    )
    assert out.ok is False
    assert (
        "verified source container" in out.why
        or "foreign_open" in out.why
    )


def test_forwarded_badge_is_not_forward_affordance():
    assert _label_looks_like_menu_verb("• Forwarded") is False
    assert _label_looks_like_menu_verb("Forwarded") is False
    assert _label_looks_like_menu_verb("Forward") is True
    brief = DecisionBrief(
        goal={"contact": "Pallavi", "source_query": "zarooratwala"},
        world={"surface": "conversation", "open_conversation": "Pallavi"},
        task_state=TaskState(
            phase="act_on_content",
            source_chat_open=True,
            open_conversation="Pallavi",
            content_located=True,
        ),
        capabilities=["invoke_affordance", "reveal_actions", "observe"],
        meta_action="act",
        navigation=NavigationInfo(surface="conversation"),
    )
    out = sanitize_decision(
        {
            "capability": "invoke_affordance",
            "target": "• Forwarded",
            "why": "forward",
            "confidence": 0.9,
        },
        brief,
    )
    assert out.ok is False
    assert "metadata" in out.why or "Forwarded" in out.why


def test_foreign_container_locus_forbids_reveal():
    """Defense in depth: locus_contract blocks patient caps on foreign open."""
    from plugin.agent.capabilities.locus_contract import wrong_locus_forbidden

    brief = DecisionBrief(
        goal={"contact": "Pallavi", "source_query": "zarooratwala"},
        world={
            "surface": "conversation",
            "open_conversation": "ZarooratWala - Fresh Groceries Delivered",
        },
        task_state=TaskState(
            phase="hunt_content",
            source_chat_open=False,
            open_conversation="ZarooratWala - Fresh Groceries Delivered",
        ),
        capabilities=["reveal_actions", "observe"],
        meta_action="act",
        navigation=NavigationInfo(surface="conversation"),
    )
    bad, why, _ = wrong_locus_forbidden("reveal_actions", brief=brief)
    assert bad is True
    assert "foreign_open" in why
    out = sanitize_decision(
        {
            "capability": "reveal_actions",
            "target": "You: https://www.zarooratwala.com/",
            "why": "forward",
            "confidence": 0.9,
        },
        brief,
    )
    assert out.ok is False


def test_forwarded_startswith_forward_is_not_picker_verb():
    """Picker dest-gate must not treat Forwarded as Forward via startswith."""
    brief = DecisionBrief(
        goal={
            "contact": "Pallavi",
            "destination": "Tanmay",
            "target_contact": "Tanmay",
            "source_query": "zarooratwala",
        },
        world={"surface": "forward_picker", "open_conversation": ""},
        task_state=TaskState(
            phase="choose_destination",
            source_chat_open=True,
            open_conversation="Pallavi",
        ),
        capabilities=["invoke_affordance", "observe"],
        meta_action="act",
        navigation=NavigationInfo(surface="forward_picker"),
    )
    # If Forwarded were treated as a forward verb, sanitize would demand
    # destination selection. Provenance badges must fall through / fail cleanly
    # as non-verbs (metadata reject or not dest-selected for true Forward).
    out = sanitize_decision(
        {
            "capability": "invoke_affordance",
            "target": "Forwarded",
            "why": "forward",
            "confidence": 0.9,
        },
        brief,
    )
    assert out.ok is False
    assert "destination not selected" not in out.why
    assert "metadata" in out.why or "Forwarded" in out.why
