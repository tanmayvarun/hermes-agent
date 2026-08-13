"""SEARCH hypothesis ranking — role-conditioned explore-order (not weight tuning)."""

from __future__ import annotations

from plugin.agent.capabilities.search_episode import (
    advance_search_with_candidates,
    filter_search_candidates,
    start_search_episode,
)
from plugin.agent.capabilities.search_hypothesis import (
    hypothesis_ledger_entries,
    interpret_search_candidate,
    legacy_soft_rank_scores,
    rank_search_hypotheses,
)
from plugin.agent.decision_consultation import (
    DecisionBrief,
    TaskState,
    _open_entity_target_from_brief,
)
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.source_query_binding import evaluate_source_object_match


def _frozen_inventory():
    """Representative search-surface inventory (frozen world — ranker isolation)."""
    return [
        {
            "id": "echo",
            "kind": "search_result",
            "label": "Alice invoice Alice",
            "text": "invoice Alice",
            "matches_goal": False,
            "sender": "Alice",
        },
        {
            "id": "direct",
            "kind": "search_result",
            "label": "Alice https://www.acme.com/invoice.pdf Acme Invoice",
            "text": "https://www.acme.com/invoice.pdf Acme Invoice",
            "matches_goal": True,
            "sender": "Alice",
        },
        {
            "id": "related",
            "kind": "search_result",
            "label": "Alice https://www.instagram.com/acme?igsh=1",
            "text": "https://www.instagram.com/acme?igsh=1",
            "matches_goal": True,
            "sender": "Alice",
        },
        {
            "id": "you",
            "kind": "search_result",
            "label": "You: https://www.acme.com/invoice.pdf",
            "text": "You: https://www.acme.com/invoice.pdf",
            "matches_goal": True,
            "sender": "You",
        },
        {
            "id": "unknown",
            "kind": "search_result",
            "label": "https://www.acme.com/invoice.pdf",
            "text": "https://www.acme.com/invoice.pdf",
            "matches_goal": True,
        },
    ]


def test_direct_object_beats_merely_related_object():
    ranked = rank_search_hypotheses(
        _frozen_inventory(),
        query="acme",
        expected_container="Alice",
        expected_originator="Alice",
        role="content",
    )
    ids = [r["id"] for r in ranked]
    assert ids[0] == "direct"
    assert ids.index("direct") < ids.index("related")


def test_relation_contradiction_demotes_lexical_perfect_match():
    ranked = rank_search_hypotheses(
        _frozen_inventory(),
        query="acme",
        expected_container="Alice",
        expected_originator="Alice",
        role="content",
    )
    ids = [r["id"] for r in ranked]
    assert ids.index("direct") < ids.index("you")
    you = next(r for r in ranked if r["id"] == "you")
    assert "explicit_self_vs_required_sender" in (
        you.get("interpretation") or {}
    ).get("contradictions", [])


def test_unknown_evidence_not_contradiction_still_explorable():
    ranked = rank_search_hypotheses(
        _frozen_inventory(),
        query="acme",
        expected_container="Alice",
        expected_originator="Alice",
        role="content",
    )
    unk = next(r for r in ranked if r["id"] == "unknown")
    interp = unk["interpretation"]
    assert "sender_unknown" in interp["unknowns"]
    assert "explicit_self_vs_required_sender" not in interp["contradictions"]
    assert interp["exploration_value"]["explorable"] is True
    # Unknown ranks below known-Alice direct, above self contradiction.
    ids = [r["id"] for r in ranked]
    assert ids.index("direct") < ids.index("unknown") < ids.index("you")


def test_query_echo_not_patient_content():
    ranked = rank_search_hypotheses(
        _frozen_inventory(),
        query="acme invoice",
        expected_container="Alice",
        expected_originator="Alice",
        role="content",
    )
    ids = [r["id"] for r in ranked]
    assert "echo" not in ids or ids.index("direct") < ids.index("echo")


def test_same_lexical_match_stronger_relation_evidence_wins():
    ranked = rank_search_hypotheses(
        [
            {
                "id": "alice",
                "label": "invoice.pdf",
                "text": "invoice.pdf",
                "kind": "message_bubble",
                "sender": "Alice",
                "matches_goal": True,
            },
            {
                "id": "unk",
                "label": "invoice.pdf",
                "text": "invoice.pdf",
                "kind": "message_bubble",
                "matches_goal": True,
            },
        ],
        query="invoice",
        expected_container="Alice",
        expected_originator="Alice",
        role="content",
    )
    assert [r["id"] for r in ranked][:2] == ["alice", "unk"]


def test_ranking_does_not_equal_binding():
    ranked = rank_search_hypotheses(
        _frozen_inventory(),
        query="acme",
        expected_container="Alice",
        expected_originator="Alice",
        role="content",
    )
    top = ranked[0]
    # Explore order set; commit still RoleBinder's job.
    assert top["interpretation"]["commit_readiness"]["advisory_only"] is True
    # Related Instagram must not be binding_eligible.
    related = next(r for r in ranked if r["id"] == "related")
    gm = evaluate_source_object_match(
        text=related["text"],
        kind="message_bubble",
        query="acme",
        container_open="Alice",
        expected_container="Alice",
        expected_originator="Alice",
        sender="Alice",
        perception_matches_goal=True,
    )
    assert gm.binding_eligible is False


def test_binder_authority_high_rank_does_not_write_resolved_entity():
    state = ExecutionState()
    start_search_episode(
        state,
        role="content",
        referent="acme",
        query="acme",
        evidence_tokens=["Alice", "acme"],
    )
    advance_search_with_candidates(
        state,
        _frozen_inventory(),
        referent="acme",
        query="acme",
        evidence_tokens=["Alice", "acme"],
    )
    assert getattr(state, "resolved_entity_id", None) in (None, "", 0)
    assert "hypothesis_ledger" in (state.search_episode or {})


def test_open_entity_preserves_search_chosen_label():
    brief = DecisionBrief(
        goal={"source_conversation": "Alice", "source_query": "acme"},
        world={
            "surface": "search",
            "objects": [
                {
                    "id": "b",
                    "text": "https://www.instagram.com/acme",
                    "kind": "search_result",
                    "matches_goal": True,
                },
                {
                    "id": "a",
                    "text": "https://www.acme.com/invoice.pdf",
                    "kind": "search_result",
                    "matches_goal": True,
                },
            ],
        },
        search_episode={
            "status": "complete",
            "chosen_label": "https://www.acme.com/invoice.pdf",
        },
        task_state=TaskState(phase="reach_source"),
        capabilities=["open_entity"],
    )
    assert _open_entity_target_from_brief(brief) == "https://www.acme.com/invoice.pdf"


def test_omitted_candidate_is_recall_failure_not_rank_blame():
    # Correct inbound missing from inventory — Rank@K N/A; Recall@K miss.
    inventory = [c for c in _frozen_inventory() if c["id"] != "direct"]
    ranked = rank_search_hypotheses(
        inventory,
        query="acme",
        expected_container="Alice",
        expected_originator="Alice",
        role="content",
    )
    assert all(r["id"] != "direct" for r in ranked)
    recall_at_k = any(r["id"] == "direct" for r in ranked)
    assert recall_at_k is False


def test_frozen_world_old_vs_new_ranking_separates_ties():
    inv = _frozen_inventory()
    legacy = legacy_soft_rank_scores(
        inv, query="acme", evidence_tokens=["Alice", "acme"]
    )
    # Legacy collapses URL hits to the same score band.
    top_legacy_scores = [s for s, _ in legacy[:3]]
    assert len(set(int(s) for s in top_legacy_scores)) <= 2

    ranked = rank_search_hypotheses(
        inv,
        query="acme",
        expected_container="Alice",
        expected_originator="Alice",
        role="content",
    )
    assert ranked[0]["id"] == "direct"
    assert ranked[0]["id"] != "you"
    assert ranked[0]["id"] != "related"


def test_hypothesis_ledger_mandatory_fields():
    ranked = rank_search_hypotheses(
        _frozen_inventory(),
        query="acme",
        expected_container="Alice",
        expected_originator="Alice",
        role="content",
    )
    ledger = hypothesis_ledger_entries(ranked)
    assert ledger
    row = ledger[0]
    for key in (
        "candidate_id",
        "evidence_vector",
        "contradictions",
        "unknowns",
        "rank_reason",
        "rank_position",
        "selected_for_exploration",
        "rejected_reason",
    ):
        assert key in row


def test_filter_search_candidates_uses_hypothesis_rank():
    out = filter_search_candidates(
        _frozen_inventory(),
        referent="acme",
        query="acme",
        evidence_tokens=["Alice", "acme"],
        expected_originator="Alice",
        expected_container="Alice",
        role="content",
    )
    assert out[0]["id"] == "direct"
    assert "interpretation" in out[0]
