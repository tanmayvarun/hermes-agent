"""EffectStatus UNKNOWN after locate (live 185549) — contracts + review fixes."""

from __future__ import annotations

from plugin.agent.capabilities.locate_content import (
    MACOS_FIND,
    LocateContent,
    LocateRequest,
    classify_locate_effect_status,
    default_realizations,
    extract_locate_effect_verify_answer,
    locate_method_context,
    locate_skip_realizations,
    locate_verify_can_establish_absence,
    note_locate_outcome,
    prefer_next_locate_realization,
    refresh_locate_method_frontier,
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
from plugin.agent.source_query_binding import (
    document_establishes_locate_patient,
    document_locates_source_query,
    evaluate_source_object_match,
    text_establishes_locate_patient,
)


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


def test_high_coverage_without_explicit_negative_exhausts_attempt():
    """Paid visual verify without patient ≠ world-level NOT_ACHIEVED.

    Inventory omission must not invent absence, but the equivalent
    native_find@state attempt is information-exhausted so SEARCH advances.
    """
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
    # Do not invent world-level absence from inventory omission.
    assert out.get("effect_status") == "unknown"
    assert out.get("verification") == "verified_no_progress"
    iframe = active_intention_frame(state)
    assert iframe is not None
    assert iframe.method_frontier.status_of("locate_native_find") == (
        MethodStatus.INEFFECTIVE.value
    )
    assert prefer_next_locate_realization(state) == "scroll_scan"
    ledger = state.locate_attempt_ledger
    assert ledger[-1].get("effect_after_verification") == "not_observed"


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


def test_unknown_effect_requires_verification_before_retry():
    """AX-blind native_find must not reseal until verification is paid."""
    state = ExecutionState()
    note_locate_outcome(
        state,
        query="zarooratwala",
        ok=True,
        found=False,
        realization="native_find",
        message="accessibility text unavailable, screen must be read",
    )
    assert same_locate_unresolved(state, query="zarooratwala") is True
    assert prefer_next_locate_realization(state) == ""
    brief = DecisionBrief(
        goal={"source_query": "zarooratwala", "link_query": "zarooratwala"},
        world={"surface": "conversation", "open_conversation": "Pallavi"},
        capabilities=["locate_content", "observe"],
        meta_action="search",
        task_state=TaskState(source_chat_open=True, content_located=False),
    )
    assert _content_search_locate_outcome(brief, execution_state=state) is None


def test_verified_no_progress_exhausts_equivalent_attempt():
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
        "objects": [{"id": "m1", "kind": "message_bubble", "text": "hey"}],
    }
    state.last_unified_proposal = {
        "coverage": 0.92,
        "confidence": 0.9,
        "model": "vision",
        "evidence_gaps": [],
    }
    out = resolve_locate_effect_after_visual_verify(
        state,
        query_visible=False,
        multimodal_ok=True,
        proposal_model="vision",
        document=state.unified_world_document,
    )
    assert out.get("verification") == "verified_no_progress"
    iframe = active_intention_frame(state)
    assert iframe is not None
    assert iframe.method_frontier.status_of("locate_native_find") == (
        MethodStatus.INEFFECTIVE.value
    )
    assert "native_find" in locate_skip_realizations(state, query="zarooratwala")


def test_state_change_can_reenable_previously_exhausted_method():
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
        "objects": [{"id": "m1", "kind": "message_bubble", "text": "hey"}],
    }
    state.last_unified_proposal = {
        "coverage": 0.9,
        "confidence": 0.9,
        "model": "vision",
        "evidence_gaps": [],
    }
    resolve_locate_effect_after_visual_verify(
        state,
        query_visible=False,
        multimodal_ok=True,
        proposal_model="vision",
        document=state.unified_world_document,
    )
    iframe = active_intention_frame(state)
    assert iframe is not None
    assert iframe.method_frontier.status_of("locate_native_find") == (
        MethodStatus.INEFFECTIVE.value
    )
    # Scroll changes locate world token → MethodContext changes → re-enable.
    note_locate_outcome(
        state,
        query="zarooratwala",
        ok=True,
        found=False,
        realization="scroll_scan",
        message="revealed a screenful; accessibility text unavailable, screen must be read",
        surface_changed=True,
    )
    reactivated = refresh_locate_method_frontier(state, query="zarooratwala")
    assert "locate_native_find" in reactivated
    assert iframe.method_frontier.status_of("locate_native_find") == (
        MethodStatus.UNTRIED.value
    )
    # Context fingerprint moved with the scroll token.
    ctx = locate_method_context(state, query="zarooratwala")
    assert "tok=1" in ctx.signature() or "tok=1" in str(ctx.overlay)


def test_related_visual_candidate_does_not_satisfy_patient_identity():
    ig = "https://www.instagram.com/zarooratwala.official/reel/abc/"
    # Soft locate may notice the brand token; patient establish must not.
    assert document_locates_source_query(
        {"objects": [{"kind": "message_bubble", "text": ig}]}, "zarooratwala"
    )
    assert text_establishes_locate_patient(ig, "zarooratwala") is False
    assert (
        document_establishes_locate_patient(
            {"objects": [{"kind": "message_bubble", "text": ig}]}, "zarooratwala"
        )
        is False
    )
    direct = "https://zarooratwala.com/offer"
    assert text_establishes_locate_patient(direct, "zarooratwala") is True


def test_failed_native_retrieval_switches_to_information_gaining_alternative():
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
        "objects": [{"id": "m1", "kind": "message_bubble", "text": "hey"}],
    }
    state.last_unified_proposal = {
        "coverage": 0.9,
        "confidence": 0.9,
        "model": "vision",
        "evidence_gaps": [],
    }
    resolve_locate_effect_after_visual_verify(
        state,
        query_visible=False,
        multimodal_ok=True,
        proposal_model="vision",
        document=state.unified_world_document,
    )
    prefer = prefer_next_locate_realization(state)
    assert prefer == "scroll_scan"
    skip = locate_skip_realizations(state, query="zarooratwala")
    assert "native_find" in skip

    class _Surf:
        def __init__(self) -> None:
            self.typed: list = []
            self.scrolls = 0
            self.find_field_open = False

        def activate(self, app: str) -> None:
            return None

        def key(self, chord) -> None:
            self.find_field_open = True

        def type_text(self, text: str) -> None:
            self.typed.append(text)

        def scroll(self, direction: str, amount: int) -> None:
            self.scrolls += 1

        def surface_text(self) -> str:
            return ""

        def surface_signature(self) -> str:
            return f"s{self.scrolls}"

        def text_input_focused(self) -> bool:
            return self.find_field_open

        def filter_field_ready(self) -> bool:
            return self.find_field_open

    surf = _Surf()
    outcome = LocateContent(realizations=default_realizations(find=MACOS_FIND)).locate(
        LocateRequest(
            query="zarooratwala",
            app="SomeChat",
            prefer_realization=prefer,
            skip_realizations=tuple(skip),
        ),
        surf,
    )
    assert outcome.realization == "scroll_scan"
    assert surf.typed == []
    assert surf.scrolls == 1


def test_exact_patient_after_ax_blind_earns_progress_without_method_switch():
    """Counterexample: paid verify that sees the direct patient → ACHIEVED."""
    state = ExecutionState()
    note_locate_outcome(
        state,
        query="zarooratwala",
        ok=True,
        found=False,
        realization="native_find",
        message="accessibility text unavailable, screen must be read",
    )
    doc = {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "objects": [
            {
                "id": "m1",
                "kind": "message_bubble",
                "text": "here https://zarooratwala.com/x",
            }
        ],
    }
    state.unified_world_document = doc
    state.last_unified_proposal = {
        "coverage": 0.95,
        "confidence": 0.92,
        "model": "vision",
        "evidence_gaps": [],
    }
    assert document_establishes_locate_patient(doc, "zarooratwala")
    out = resolve_locate_effect_after_visual_verify(
        state,
        query_visible=True,
        multimodal_ok=True,
        proposal_model="vision",
        document=doc,
    )
    assert out.get("effect_status") == "achieved"
    iframe = active_intention_frame(state)
    assert iframe is not None
    assert iframe.method_frontier.status_of("locate_native_find") == (
        MethodStatus.SUCCEEDED.value
    )
    # Do not force a retrieval-method switch after success.
    assert prefer_next_locate_realization(state) in {"", "scroll_scan"}
    if prefer_next_locate_realization(state) == "scroll_scan":
        # scroll may remain untried in the catalog; success must not exhaust native.
        assert iframe.method_frontier.status_of("locate_native_find") == (
            MethodStatus.SUCCEEDED.value
        )
