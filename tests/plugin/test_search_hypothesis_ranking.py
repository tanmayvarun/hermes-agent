"""SEARCH hypothesis ranking — role-conditioned explore-order (not weight tuning)."""

from __future__ import annotations


def _norm_absent_role(interp: dict) -> bool:
    rel = interp.get("relation_evidence") or {}
    # Ranker must not invent person/container from unordered evidence tokens.
    return not rel.get("container") and "John" not in str(rel.get("originator") or "")


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
    # Related Instagram ranks below direct brand host (goal-conditioned),
    # regardless of whether binder could accept path-supported evidence.
    related = next(r for r in ranked if r["id"] == "related")
    assert ranked[0]["id"] == "direct"
    assert related["interpretation"]["relevance"]["url_tier"] == 2
    assert top["interpretation"]["relevance"]["url_tier"] == 3


def test_binder_authority_high_rank_does_not_write_resolved_entity():
    state = ExecutionState()
    start_search_episode(
        state,
        role="content",
        referent="acme",
        query="acme",
        evidence_tokens=["Alice", "acme"],
        expected_originator="Alice",
        expected_container="Alice",
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


def test_untyped_evidence_tokens_do_not_assign_semantic_roles():
    """Unordered search evidence must not invent originator/container."""
    out = filter_search_candidates(
        [
            {
                "id": "hit",
                "label": "quarterly forecast notes",
                "kind": "search_result",
                "matches_goal": True,
            }
        ],
        referent="Project Phoenix",
        query="quarterly forecast",
        evidence_tokens=["forecast", "Project Phoenix", "John"],
        role="content",
    )
    interp = out[0]["interpretation"]
    # Without typed goal roles, expectations stay empty / UNKNOWN.
    assert interp["relation_evidence"].get("container") in ("", None)
    assert "sender_unknown" in interp["unknowns"]
    # Must not treat first non-query token ("forecast" / "John") as originator.
    assert _norm_absent_role(interp)


def test_instagram_can_be_direct_object_when_sought():
    ranked = rank_search_hypotheses(
        [
            {
                "id": "ig",
                "label": "Alice https://www.instagram.com/zarooratwala",
                "matches_goal": True,
                "sender": "Alice",
            },
            {
                "id": "site",
                "label": "Alice https://www.zarooratwala.com/",
                "matches_goal": True,
                "sender": "Alice",
            },
        ],
        query="zarooratwala",
        expected_container="Alice",
        expected_originator="Alice",
        # Typed sought platform — not inferred from free-form query text.
        sought_object="instagram",
        role="content",
    )
    assert ranked[0]["id"] == "ig"
    assert ranked[0]["interpretation"]["relevance"]["url_reason"] == "sought_platform_host"


def test_platform_word_in_query_does_not_imply_platform_object_type():
    raw = [
        {
            "id": "ig",
            "label": "Alice https://www.instagram.com/acme",
            "matches_goal": True,
            "sender": "Alice",
        }
    ]
    # Same raw candidates; only sought_object semantics change.
    untyped = rank_search_hypotheses(
        raw,
        query="report about Instagram growth",
        expected_container="Alice",
        expected_originator="Alice",
        sought_object="",
        role="content",
    )
    typed = rank_search_hypotheses(
        raw,
        query="report about Instagram growth",
        expected_container="Alice",
        expected_originator="Alice",
        sought_object="instagram",
        role="content",
    )
    assert untyped[0]["interpretation"]["relevance"]["url_reason"] != (
        "sought_platform_host"
    )
    assert typed[0]["interpretation"]["relevance"]["url_reason"] == (
        "sought_platform_host"
    )


def test_in_Alice_chat_does_not_imply_originator_Alice():
    """Container from source_conversation must not become expected_originator."""
    state = ExecutionState()
    brief = DecisionBrief(
        goal={
            "source_conversation": "Alice",
            "source_query": "invoice",
            # No typed originator — invoice may be self-sent or from another party.
        },
        world={
            "surface": "search",
            "objects": [
                {
                    "id": "you",
                    "kind": "search_result",
                    "text": "You: https://files.example/invoice.pdf",
                    "matches_goal": True,
                }
            ],
        },
        task_state=TaskState(phase="reach_source", search_query="invoice"),
        capabilities=["open_entity", "resolve_entity", "observe", "search"],
    )
    from plugin.agent.capabilities.search_episode import (
        ensure_search_episode_from_brief,
        search_episode_of,
    )

    ensure_search_episode_from_brief(state, brief)
    ep = search_episode_of(state) or {}
    assert ep.get("expected_container") == "Alice"
    assert ep.get("expected_originator") in ("", None)
    # Self-authored hit is explorable when originator is UNKNOWN (not contradicted).
    assert ep.get("status") in {"complete", "ranking"}
    if ep.get("status") == "complete":
        assert ep.get("role_resolved") is False


def test_self_sent_to_John_sets_container_John_originator_self():
    state = ExecutionState()
    brief = DecisionBrief(
        goal={
            "source_conversation": "John",
            "source_query": "link",
            "originator": "self",
        },
        world={
            "surface": "search",
            "objects": [
                {
                    "id": "you",
                    "kind": "search_result",
                    "text": "You: https://example.com/note",
                    "matches_goal": True,
                    "sender": "You",
                },
                {
                    "id": "john",
                    "kind": "search_result",
                    "text": "John: https://example.com/other",
                    "matches_goal": True,
                    "sender": "John",
                },
            ],
        },
        task_state=TaskState(phase="reach_source", search_query="link"),
        capabilities=["open_entity", "resolve_entity", "observe", "search"],
    )
    from plugin.agent.capabilities.search_episode import ensure_search_episode_from_brief
    from plugin.agent.role_binding import IdentityResolver
    from plugin.agent.source_query_binding import originator_matches

    ep = ensure_search_episode_from_brief(state, brief) or {}
    assert ep.get("expected_container") == "John"
    assert ep.get("expected_originator") == "self"
    # IdentityResolver owns self/You — not SEARCH pronoun heuristics.
    assert IdentityResolver.canonical_identity("You") == "self"
    assert IdentityResolver.values_same_identity("self", "You")
    assert originator_matches("You", "self")
    ranked = rank_search_hypotheses(
        [
            {
                "id": "you",
                "label": "You: https://example.com/note",
                "matches_goal": True,
                "sender": "You",
            },
            {
                "id": "john",
                "label": "John: https://example.com/other",
                "matches_goal": True,
                "sender": "John",
            },
        ],
        query="link",
        expected_container="John",
        expected_originator="self",
        role="content",
    )
    assert ranked[0]["id"] == "you"


def test_source_Alice_destination_Bob_search_container_is_Alice():
    """Destination must not become SEARCH expected_container."""
    state = ExecutionState()
    brief = DecisionBrief(
        goal={
            "source_conversation": "Alice",
            "destination": "Bob",
            "target_contact": "Bob",
            "contact": "Bob",  # ambiguous legacy field — must not win over source
            "source_query": "invoice",
            "originator": "Alice",
        },
        world={
            "surface": "search",
            "objects": [
                {
                    "id": "hit",
                    "kind": "search_result",
                    "text": "Alice https://example.com/invoice.pdf",
                    "matches_goal": True,
                    "sender": "Alice",
                }
            ],
        },
        task_state=TaskState(phase="reach_source", search_query="invoice"),
        capabilities=["open_entity", "resolve_entity", "observe", "search"],
    )
    from plugin.agent.capabilities.search_episode import ensure_search_episode_from_brief

    ep = ensure_search_episode_from_brief(state, brief) or {}
    assert ep.get("expected_container") == "Alice"
    assert ep.get("expected_originator") == "Alice"
    assert ep.get("expected_container") != "Bob"
    assert ep.get("container_provenance") == "typed"


def test_ambiguous_legacy_contact_without_source_role_is_not_authoritative_container():
    """Bare goal.contact must not silently become expected_container."""
    state = ExecutionState()
    brief = DecisionBrief(
        goal={
            "contact": "Charlie",
            "destination": "Dana",
            "source_query": "notes",
        },
        world={
            "surface": "search",
            "objects": [
                {
                    "id": "hit",
                    "kind": "search_result",
                    "text": "notes.pdf",
                    "matches_goal": True,
                }
            ],
        },
        task_state=TaskState(phase="reach_source", search_query="notes"),
        capabilities=["open_entity", "resolve_entity", "observe", "search"],
    )
    from plugin.agent.capabilities.search_episode import ensure_search_episode_from_brief

    ep = ensure_search_episode_from_brief(state, brief) or {}
    assert ep.get("expected_container") in ("", None)
    assert ep.get("legacy_source_candidate") == "Charlie"
    assert ep.get("container_provenance") == "legacy_provisional"


def test_strong_unknown_outranks_weaker_commit_ready():
    ranked = rank_search_hypotheses(
        [
            {
                "id": "strong_unk",
                "label": "https://www.acme.com/invoice.pdf",
                "matches_goal": True,
            },
            {
                "id": "weak_ready",
                "label": "Alice invoice notes",
                "matches_goal": True,
                "sender": "Alice",
            },
        ],
        query="acme",
        expected_container="Alice",
        expected_originator="Alice",
        role="content",
    )
    assert ranked[0]["id"] == "strong_unk"
    top = ranked[0]["interpretation"]
    weak = next(r for r in ranked if r["id"] == "weak_ready")["interpretation"]
    assert "sender_unknown" in top["unknowns"]
    # Bind-ready must not override stronger explore hypothesis via rank_key.
    assert top["rank_key"][1] > weak["rank_key"][1]


def test_no_search_choice_means_act_does_not_invent_one():
    brief = DecisionBrief(
        goal={"source_conversation": "Alice", "source_query": "acme"},
        world={
            "surface": "search",
            "objects": [
                {
                    "id": "a",
                    "text": "https://www.acme.com/invoice.pdf",
                    "matches_goal": True,
                },
                {
                    "id": "b",
                    "text": "https://www.instagram.com/acme",
                    "matches_goal": True,
                },
            ],
        },
        search_episode={
            "status": "ranking",
            "chosen_label": "",
            "explore_label": "",
        },
        task_state=TaskState(phase="reach_source"),
        capabilities=["open_entity"],
    )
    assert _open_entity_target_from_brief(brief) == ""


def test_unique_fit_is_provisional_not_role_resolved():
    state = ExecutionState()
    start_search_episode(
        state,
        role="content",
        referent="acme",
        query="acme",
        evidence_tokens=["Alice", "acme"],
        expected_originator="Alice",
        expected_container="Alice",
        status="ranking",
    )
    advance_search_with_candidates(
        state,
        [
            {
                "id": "only",
                "label": "https://www.acme.com/invoice.pdf",
                "matches_goal": True,
            }
        ],
        referent="acme",
        query="acme",
        evidence_tokens=["Alice", "acme"],
    )
    ep = state.search_episode or {}
    assert ep.get("status") == "complete"
    assert ep.get("choice_confidence") == "provisional"
    assert ep.get("retrieval_complete") is True
    assert ep.get("role_resolved") is False
