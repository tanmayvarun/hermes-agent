"""EffectStatus UNKNOWN after locate (live 185549) — contracts + review fixes."""

from __future__ import annotations

from plugin.agent.capabilities.locate_content import (
    classify_locate_effect_status,
    extract_locate_effect_verify_answer,
    locate_verify_can_establish_absence,
    note_locate_outcome,
    prefer_next_locate_realization,
    resolve_locate_effect_after_visual_verify,
    resolve_locate_effect_verification,
    same_locate_unresolved,
)
from plugin.agent.decision_consultation import (
    DecisionBrief,
    TaskState,
    _content_search_locate_outcome,
)
from plugin.agent.executive.intention_frame import (
    MethodOutcome,
    MethodStatus,
    active_intention_frame,
)
from plugin.agent.executive.meta_action import MetaAction, MetaContext, select_meta_action
from plugin.agent.executive.meta_consultation import sanitize_meta_choice
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.source_query_binding import evaluate_source_object_match


def test_execution_ok_effect_unknown_requires_verification_before_retry():
    state = ExecutionState()
    info = note_locate_outcome(
        state,
        query="zarooratwala",
        ok=True,
        found=False,
        realization="native_find",
        message="queried via find; accessibility text unavailable, screen must be read",
    )
    assert info.get("effect_status") == "unknown"
    assert info.get("classify_reason") == "observation_substrate_blind"
    assert state.locate_effect_verify_owed is True
    assert state.last_locate_effect_status == "unknown"
    iframe = active_intention_frame(state)
    assert iframe is not None
    assert iframe.pending_effect_verification is True
    assert any(
        a.method_outcome == MethodOutcome.EFFECT_UNCERTAIN.value for a in iframe.attempts
    )
    assert same_locate_unresolved(state, query="zarooratwala")


def test_observable_negative_locate_is_not_achieved_not_unknown():
    """Trustworthy empty result must not arm visual-verify debt."""
    classified = classify_locate_effect_status(
        ok=True,
        found=False,
        message="scanned 12 screenful(s) without a match; budget reached",
        exhausted=False,
    )
    assert classified["effect_status"] == "not_achieved"
    state = ExecutionState()
    info = note_locate_outcome(
        state,
        query="zarooratwala",
        ok=True,
        found=False,
        realization="scroll_scan",
        message="scanned 12 screenful(s) without a match; budget reached",
        exhausted=False,
    )
    assert info.get("effect_status") == "not_achieved"
    assert state.locate_effect_verify_owed is False
    assert state.last_locate_effect_status == "not_achieved"


def test_exhausted_search_does_not_request_visual_verification():
    state = ExecutionState()
    info = note_locate_outcome(
        state,
        query="zarooratwala",
        ok=True,
        found=False,
        realization="scroll_scan",
        message="surface stopped changing after 3 screenful(s); no match",
        exhausted=True,
    )
    assert info.get("effect_status") == "not_achieved"
    assert info.get("classify_reason") == "search_domain_exhausted"
    assert state.locate_effect_verify_owed is False
    iframe = active_intention_frame(state)
    assert iframe is not None
    assert iframe.pending_effect_verification is False
    st = iframe.method_frontier.status_of("locate_scroll_scan")
    assert st == MethodStatus.INEFFECTIVE.value


def test_same_search_method_same_context_not_replayed_while_effect_unresolved():
    state = ExecutionState()
    note_locate_outcome(
        state,
        query="zarooratwala",
        ok=True,
        found=False,
        realization="native_find",
        message="queried via find; accessibility text unavailable, screen must be read",
    )
    brief = DecisionBrief(
        goal={"source_query": "zarooratwala", "link_query": "zarooratwala"},
        world={"surface": "conversation", "open_conversation": "Pallavi"},
        capabilities=["locate_content", "observe"],
        meta_action="search",
        task_state=TaskState(
            phase="hunt_content",
            source_chat_open=True,
            content_located=False,
        ),
    )
    seal = _content_search_locate_outcome(brief, execution_state=state)
    assert seal is None, "must not reseal identical locate while effect UNKNOWN"


def test_ax_blind_search_can_fall_back_to_visual_verification():
    state = ExecutionState()
    note_locate_outcome(
        state,
        query="zarooratwala",
        ok=True,
        found=False,
        realization="native_find",
        message="accessibility text unavailable",
    )
    choice = select_meta_action(
        MetaContext(
            locate_effect_verify_owed=True,
            awaiting_verification=True,
            has_grounded_action=False,
        )
    )
    assert choice.action is MetaAction.PERCEIVE
    sanitized = sanitize_meta_choice(
        {"meta_action": "search", "why": "query unpaid", "confidence": 0.9},
        MetaContext(locate_effect_verify_owed=True),
    )
    assert sanitized is not None and sanitized.action is MetaAction.PERCEIVE


def test_still_unobservable_does_not_mark_method_ineffective():
    state = ExecutionState()
    note_locate_outcome(
        state,
        query="zarooratwala",
        ok=True,
        found=False,
        realization="native_find",
        message="accessibility text unavailable, screen must be read",
    )
    resolve_locate_effect_verification(
        state,
        content_located=False,
        query_visible=False,
        still_unobservable=True,
    )
    iframe = active_intention_frame(state)
    assert iframe is not None
    st = iframe.method_frontier.status_of("locate_native_find")
    assert st == MethodStatus.UNTRIED.value, "lack of observability ≠ method fails"
    assert "locate_native_find" in iframe.method_frontier.currently_ineligible
    assert "locate_scroll_scan" in iframe.method_frontier.eligible_methods()


def test_high_coverage_without_explicit_negative_remains_unknown():
    """Capped inventory omission + good coverage must not invent NOT_ACHIEVED."""
    state = ExecutionState()
    note_locate_outcome(
        state,
        query="zarooratwala",
        ok=True,
        found=False,
        realization="native_find",
        message="accessibility text unavailable, screen must be read",
    )
    state.unified_world_document = {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "objects": [
            {
                "id": "m1",
                "kind": "message_bubble",
                "text": "hey, free later?",
                "matches_goal": False,
            }
        ],
    }
    state.last_unified_proposal = {
        "coverage": 0.9,
        "evidence_gaps": [],
        "model": "vision",
        "confidence": 0.9,
    }
    claim = extract_locate_effect_verify_answer(
        state, document=state.unified_world_document
    )
    assert claim["answer"] == "unknown"
    quality = locate_verify_can_establish_absence(
        state,
        document=state.unified_world_document,
        multimodal_ok=True,
        proposal_model="vision",
    )
    assert quality["sufficient"] is False
    out = resolve_locate_effect_after_visual_verify(
        state,
        query_visible=False,
        multimodal_ok=True,
        proposal_model="vision",
        document=state.unified_world_document,
    )
    assert out.get("effect_status") == "unknown"
    iframe = active_intention_frame(state)
    assert iframe is not None
    assert iframe.method_frontier.status_of("locate_native_find") == (
        MethodStatus.UNTRIED.value
    )


def test_explicit_locate_negative_with_good_evidence_becomes_not_achieved():
    """Explicit NO + trustworthy observation → NOT_ACHIEVED."""
    state = ExecutionState()
    note_locate_outcome(
        state,
        query="zarooratwala",
        ok=True,
        found=False,
        realization="native_find",
        message="accessibility text unavailable, screen must be read",
    )
    state.unified_world_document = {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "objects": [
            {
                "id": "m1",
                "kind": "message_bubble",
                "text": "hey, free later?",
                "matches_goal": False,
            }
        ],
        "source_query_not_surfaced": True,
        "locate_effect_answer": "no",
    }
    state.last_unified_proposal = {
        "coverage": 0.9,
        "evidence_gaps": [],
        "model": "vision",
        "confidence": 0.85,
    }
    quality = locate_verify_can_establish_absence(
        state,
        document=state.unified_world_document,
        multimodal_ok=True,
        proposal_model="vision",
    )
    assert quality["sufficient"] is True
    assert quality["answer"] == "no"
    out = resolve_locate_effect_after_visual_verify(
        state,
        query_visible=False,
        multimodal_ok=True,
        proposal_model="vision",
        document=state.unified_world_document,
    )
    assert out.get("effect_status") == "not_achieved"
    assert state.last_locate_effect_status == "not_achieved"
    assert state.locate_effect_verify_owed is False
    iframe = active_intention_frame(state)
    assert iframe is not None
    assert iframe.method_frontier.status_of("locate_native_find") == (
        MethodStatus.INEFFECTIVE.value
    )


def test_incomplete_visual_verify_absent_remains_unknown():
    """Degenerate / reuse look cannot convert absence into NOT_ACHIEVED."""
    state = ExecutionState()
    note_locate_outcome(
        state,
        query="zarooratwala",
        ok=True,
        found=False,
        realization="native_find",
        message="accessibility text unavailable, screen must be read",
    )
    state.unified_world_document = {"surface": "conversation", "open_conversation": "Pallavi"}
    state.last_unified_proposal = {
        "coverage": 0.2,
        "evidence_gaps": ["needs_more_evidence"],
        "model": "phash_reuse",
    }
    quality = locate_verify_can_establish_absence(
        state,
        document=state.unified_world_document,
        multimodal_ok=True,
        proposal_model="phash_reuse",
    )
    assert quality["sufficient"] is False
    out = resolve_locate_effect_after_visual_verify(
        state,
        query_visible=False,
        multimodal_ok=True,
        proposal_model="phash_reuse",
        document=state.unified_world_document,
    )
    assert out.get("effect_status") == "unknown"
    assert state.last_locate_effect_status == "unknown"
    iframe = active_intention_frame(state)
    assert iframe is not None
    assert iframe.method_frontier.status_of("locate_native_find") == (
        MethodStatus.UNTRIED.value
    )
    assert "locate_native_find" in iframe.method_frontier.currently_ineligible


def test_query_text_in_input_control_cannot_bind_content_role():
    gm = evaluate_source_object_match(
        text="zarooratwala lasawe",
        kind="draft",
        query="zarooratwala",
        container_open="Pallavi",
        expected_container="Pallavi",
        role="composer",
        perception_matches_goal=True,
    )
    assert gm.query_match is True
    assert gm.role_compatible is False
    assert gm.binding_eligible is False


def test_relevant_object_without_query_identity_cannot_bind_source_object():
    gm = evaluate_source_object_match(
        text="https://www.instagram.com/reel/abc123/",
        kind="message_bubble",
        query="zarooratwala",
        container_open="Pallavi",
        expected_container="Pallavi",
        expected_originator="Pallavi",
        perception_matches_goal=True,
    )
    assert gm.query_match is False
    assert gm.binding_eligible is False
    assert "url_host_contradicts_query" in gm.contradictions or not gm.semantic_query_match


def test_matches_goal_alone_cannot_authorize_source_object_action():
    """Recall bool must not authorize binding / act targeting."""
    obj = {
        "id": "draft1",
        "kind": "draft",
        "role": "composer",
        "text": "zarooratwala lasawe",
        "matches_goal": True,
        "point": [100, 900],
    }
    gm = evaluate_source_object_match(
        text=str(obj["text"]),
        kind=str(obj["kind"]),
        query="zarooratwala",
        container_open="Pallavi",
        expected_container="Pallavi",
        role=str(obj["role"]),
        perception_matches_goal=bool(obj["matches_goal"]),
    )
    assert obj["matches_goal"] is True  # recall may remain
    assert gm.binding_eligible is False
    # No binding-eligible patient among matches_goal-only objects.
    eligible = []
    for candidate in (obj,):
        g = evaluate_source_object_match(
            text=str(candidate["text"]),
            kind=str(candidate["kind"]),
            query="zarooratwala",
            container_open="Pallavi",
            expected_container="Pallavi",
            role=str(candidate.get("role") or ""),
            perception_matches_goal=bool(candidate.get("matches_goal")),
        )
        if g.binding_eligible:
            eligible.append(candidate["id"])
    assert eligible == []


def test_failed_visual_verification_advances_via_method_frontier():
    state = ExecutionState()
    note_locate_outcome(
        state,
        query="zarooratwala",
        ok=True,
        found=False,
        realization="native_find",
        message="accessibility text unavailable, screen must be read",
    )
    resolve_locate_effect_verification(
        state,
        content_located=False,
        query_visible=False,
        still_unobservable=True,
    )
    assert state.locate_effect_verify_owed is False
    # Frontier chooses among remaining eligible methods (catalog: scroll_scan).
    assert prefer_next_locate_realization(state) == "scroll_scan"
    assert same_locate_unresolved(state, query="zarooratwala") is False
    brief = DecisionBrief(
        goal={"source_query": "zarooratwala", "link_query": "zarooratwala"},
        world={"surface": "conversation", "open_conversation": "Pallavi"},
        capabilities=["locate_content", "observe"],
        meta_action="search",
        task_state=TaskState(
            phase="hunt_content",
            source_chat_open=True,
            content_located=False,
        ),
    )
    seal = _content_search_locate_outcome(brief, execution_state=state)
    assert seal is not None
    assert seal.capability == "locate_content"
    assert "MethodFrontier" in seal.why or "scroll_scan" in (seal.why + seal.realization)


def test_locate_attempt_ledger_records_epistemic_memory():
    state = ExecutionState()
    note_locate_outcome(
        state,
        query="zarooratwala",
        ok=True,
        found=False,
        realization="native_find",
        message="accessibility text unavailable",
    )
    resolve_locate_effect_verification(state, still_unobservable=True)
    ledger = state.locate_attempt_ledger
    assert ledger
    assert ledger[-1]["method_id"] == "locate_native_find"
    assert ledger[-1].get("verification") == "still_unobservable"
