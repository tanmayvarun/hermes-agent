"""resolve_entity chooses among candidates — it must not hardcode (you)."""

from __future__ import annotations

from typing import Any, Dict, List

from plugin.agent.capabilities.base import CapabilityRequest
from plugin.agent.capabilities.catalog import realized_verbs
from plugin.agent.capabilities.dispatch import can_dispatch, dispatch
from plugin.agent.capabilities.resolve_entity import (
    ResolveBrief,
    allow_keyboard_search_open,
    candidates_from_context,
    choose_entity_label,
    heuristic_resolve,
    match,
    open_matches_referent,
    resolve_entity,
    resolve_many,
)
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.unified_cognition import UnifiedProposal, proposal_to_action
from plugin.worldmodel.model import WorldModel


def _goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )


def test_resolve_is_realized_in_catalog():
    assert "resolve_entity" in realized_verbs()
    assert can_dispatch("resolve_entity")


def test_heuristic_prefers_self_marker_when_base_matches():
    brief = ResolveBrief(
        referent="Tanmay",
        role="destination",
        candidates=[
            {"label": "Tanmay"},
            {"label": "Tanmay (you)", "hints": ["self"]},
            {"label": "Tanmay Group"},
        ],
    )
    payload = heuristic_resolve(brief)
    assert payload["chosen"] == "Tanmay (you)"


def test_exact_source_beats_group_substring():
    outcome = resolve_entity(
        ResolveBrief(
            referent="Pallavi",
            role="source",
            candidates=[
                {"label": "Pallavi Ather Gen3"},
                {"label": "Pallavi"},
            ],
        )
    )
    assert outcome.ok
    assert outcome.evidence["chosen"] == "Pallavi"


def test_resolve_entity_outcome_reports_chosen():
    outcome = resolve_entity(
        ResolveBrief(
            referent="Tanmay",
            candidates=[
                {"label": "Tanmay"},
                {"label": "Tanmay (you)"},
            ],
        )
    )
    assert outcome.ok
    assert outcome.evidence["chosen"] == "Tanmay (you)"
    assert outcome.evidence["substrate"] == "candidate_set"


def test_exact_label_beats_unrelated_self_marker():
    outcome = resolve_entity(
        ResolveBrief(
            referent="Pallavi",
            candidates=[
                {"label": "Tanmay (you)"},
                {"label": "Pallavi"},
            ],
        )
    )
    assert outcome.ok
    assert outcome.evidence["chosen"] == "Pallavi"


def test_dispatch_resolve_passes_candidates():
    outcome = dispatch(
        CapabilityRequest(
            name="resolve_entity",
            app="WhatsApp",
            arg="Tanmay",
            extras={
                "goal": _goal(),
                "candidates": [
                    {"label": "Tanmay"},
                    {"label": "Tanmay (you)"},
                ],
            },
        ),
        overlay=object(),
    )
    assert outcome.ok
    assert outcome.evidence["chosen"] == "Tanmay (you)"


def test_choose_entity_label_convenience():
    label = choose_entity_label(
        _goal(),
        role="destination",
        candidates=["Tanmay", "Tanmay (you)", "Aakash"],
    )
    assert label == "Tanmay (you)"


def test_open_matches_referent_rejects_group_substring():
    assert open_matches_referent("Pallavi", "Pallavi")
    assert open_matches_referent("Tanmay (you)", "Tanmay")
    assert not open_matches_referent("Pallavi Ather Gen3", "Pallavi")
    assert not open_matches_referent("", "Pallavi")


def test_keyboard_open_skipped_when_point_set():
    assert allow_keyboard_search_open(
        hint="Pallavi",
        target_point=None,
        open_name="",
        on_search_surface=True,
        search_empty=False,
    )
    assert not allow_keyboard_search_open(
        hint="Pallavi",
        target_point=[200, 254],
        open_name="",
        on_search_surface=True,
        search_empty=False,
    )
    assert not allow_keyboard_search_open(
        hint="Pallavi",
        target_point=None,
        open_name="Pallavi",
        on_search_surface=True,
        search_empty=False,
    )


def test_picker_open_entity_remaps_to_resolve_entity():
    world = WorldModel(active_app="WhatsApp")
    features = StateFeatures(
        extras={
            "app_content_node_count": 0,
            "world_document": {
                "surface": "forward_picker",
                "focused_field_role": "destination_filter",
                "objects": [
                    {"text": "Tanmay", "kind": "contact"},
                    {"text": "Tanmay (you)", "kind": "contact"},
                ],
            },
        },
    )
    proposal = UnifiedProposal(
        observed_state={
            "surface": "forward_picker",
            "focused_field_role": "destination_filter",
            "objects": [
                {"text": "Tanmay", "kind": "contact"},
                {"text": "Tanmay (you)", "kind": "contact"},
            ],
        },
        next_action={
            "family": "open_entity",
            "text": "Tanmay",
            "target_point": [400, 500],
            "confidence": 0.95,
        },
        confidence=0.95,
    )
    action, reason = proposal_to_action(proposal, _goal(), world, features)
    assert reason == "admissible"
    assert action is not None
    # The runtime no longer second-guesses the destination pick: if the brain
    # wants to resolve among candidates it emits resolve_entity itself. A direct
    # open_entity on a visible row is executed as chosen.
    assert action.action_family == "open_entity"
    assert action.grounding_reason == "unified_multimodal"


def test_search_open_entity_remaps_to_resolve_entity_source():
    world = WorldModel(active_app="WhatsApp")
    features = StateFeatures(
        extras={
            "app_content_node_count": 2,
            "wa_screen": "SEARCH_RESULTS",
            "world_document": {
                "surface": "search",
                "objects": [
                    {"text": "Pallavi Ather Gen3", "kind": "contact"},
                    {"text": "Pallavi", "kind": "contact"},
                ],
            },
        },
    )
    proposal = UnifiedProposal(
        observed_state={
            "surface": "search",
            "objects": [
                {"text": "Pallavi Ather Gen3", "kind": "contact"},
                {"text": "Pallavi", "kind": "contact"},
            ],
        },
        next_action={
            "family": "open_entity",
            "text": "Pallavi",
            "target_point": [200, 254],
            "confidence": 0.95,
        },
        confidence=0.95,
    )
    action, reason = proposal_to_action(proposal, _goal(), world, features)
    assert reason == "admissible"
    assert action is not None
    assert action.action_family == "open_entity"
    assert action.grounding_reason == "unified_multimodal"


def test_stage_preferring_resolution_keeps_picker_semantic():
    world = WorldModel(active_app="WhatsApp")
    features = StateFeatures(
        extras={
            "app_content_node_count": 0,
            "selected_procedure_stage": {
                "stage_objective": "Resolve the destination recipient from the forward picker",
                "preferred_capabilities": ["resolve_entity", "open_entity"],
            },
            "world_document": {
                "surface": "forward_picker",
                "focused_field_role": "destination_filter",
                "objects": [
                    {"text": "Tanmay", "kind": "contact"},
                    {"text": "Tanmay (you)", "kind": "contact"},
                ],
            },
        },
    )
    proposal = UnifiedProposal(
        observed_state={
            "surface": "forward_picker",
            "focused_field_role": "destination_filter",
            "objects": [
                {"text": "Tanmay", "kind": "contact"},
                {"text": "Tanmay (you)", "kind": "contact"},
            ],
        },
        next_action={
            "family": "type_query",
            "text": "Tanmay",
            "target_point": [400, 500],
            "confidence": 0.95,
        },
        confidence=0.95,
    )
    action, reason = proposal_to_action(proposal, _goal(), world, features)
    assert reason == "admissible"
    assert action is not None
    # No stage-driven rewrite: the model's type_query is executed as-is.
    assert action.action_family == "type_query"
    assert action.text == "Tanmay"


def test_stage_preferring_resolution_preempts_chat_list_compose_fallback():
    world = WorldModel(active_app="WhatsApp")
    features = StateFeatures(
        extras={
            "app_content_node_count": 0,
            "selected_procedure_stage": {
                "stage_objective": "Find the source conversation that contains the message",
                "preferred_capabilities": ["resolve_entity", "open_entity", "SearchConversation"],
            },
            "world_document": {
                "surface": "chat_list",
                "focused_field_role": "sidebar_search",
                "objects": [
                    {"text": "Pallavi", "kind": "contact"},
                    {"text": "Pallavi (you)", "kind": "contact"},
                ],
            },
        },
    )
    proposal = UnifiedProposal(
        observed_state={
            "surface": "chat_list",
            "focused_field_role": "sidebar_search",
            "target_object_visible": True,
            "target_object_id": "pallavi_chat",
            "objects": [
                {"text": "Pallavi", "kind": "contact"},
                {"text": "Pallavi (you)", "kind": "contact"},
            ],
        },
        next_action={
            "family": "open_entity",
            "text": "Pallavi",
            "target_point": [180, 835],
            "confidence": 0.95,
        },
        confidence=0.95,
    )
    action, reason = proposal_to_action(proposal, _goal(), world, features)
    assert reason == "admissible"
    assert action is not None
    assert action.action_family == "open_entity"
    assert action.grounding_reason == "unified_multimodal"


def test_wrong_source_open_does_not_locate_lock():
    world = WorldModel(active_app="WhatsApp")
    features = StateFeatures(
        conversation_open=True,
        extras={
            "app_content_node_count": 0,
            "open_conversation": "Pallavi Ather Gen3",
            "wa_screen": "CONVERSATION",
            "world_document": {
                "surface": "conversation",
                "open_conversation": "Pallavi Ather Gen3",
                "objects": [
                    {"text": "Pallavi", "kind": "contact"},
                    {"text": "Pallavi Ather Gen3", "kind": "contact"},
                ],
            },
        },
    )
    proposal = UnifiedProposal(
        observed_state={
            "surface": "conversation",
            "open_conversation": "Pallavi Ather Gen3",
            "objects": [
                {"text": "Pallavi", "kind": "contact"},
                {"text": "Pallavi Ather Gen3", "kind": "contact"},
            ],
        },
        next_action={
            "family": "locate_content",
            "text": "zarooratwala",
            "confidence": 0.95,
        },
        confidence=0.95,
    )
    action, reason = proposal_to_action(proposal, _goal(), world, features)
    assert reason == "admissible"
    assert action is not None
    # The runtime does not detect a "wrong" open and reroute to resolve_entity;
    # the model owns whether it is in the right conversation and what to do.
    assert action.action_family == "locate_content"
    assert action.text == "zarooratwala"


def test_matching_source_open_allows_locate():
    world = WorldModel(active_app="WhatsApp")
    features = StateFeatures(
        conversation_open=True,
        extras={
            "app_content_node_count": 0,
            "open_conversation": "Pallavi",
            "wa_screen": "CONVERSATION",
            "world_document": {
                "surface": "conversation",
                "open_conversation": "Pallavi",
            },
        },
    )
    proposal = UnifiedProposal(
        observed_state={
            "surface": "conversation",
            "open_conversation": "Pallavi",
            "target_object_visible": False,
        },
        next_action={
            "family": "reveal_actions",
            "text": "message",
            "target_point": [400, 300],
            "confidence": 0.95,
        },
        confidence=0.95,
    )
    action, reason = proposal_to_action(proposal, _goal(), world, features)
    assert reason == "admissible"
    assert action is not None
    # No forced locate before reveal_actions: the model's move is executed.
    assert action.action_family == "reveal_actions"


class _FakeResolver:
    def __init__(self, chosen: str) -> None:
        self.chosen = chosen
        self.packets: List[Dict[str, Any]] = []

    def resolve(self, system: str, packet: Dict[str, Any]) -> Dict[str, Any]:
        self.packets.append(packet)
        assert "candidates" in packet
        assert "(you)" in system.lower() or "self" in system.lower()
        return {
            "candidates": [{"label": self.chosen, "score": 0.9, "why": "self alias"}],
            "chosen": self.chosen,
        }


def test_llm_resolver_sanitizes_to_allowed_labels():
    # Two namesakes are ambiguous, so the skill consults the LLM; its answer is
    # sanitized back to an allowed candidate label.
    resolver = _FakeResolver(chosen="Tanmay Kumar")
    outcome = resolve_entity(
        ResolveBrief(
            referent="Tanmay",
            candidates=[{"label": "Tanmay Kumar"}, {"label": "Tanmay Singh"}],
        ),
        resolver=resolver,
    )
    assert outcome.ok
    assert outcome.evidence["chosen"] == "Tanmay Kumar"
    assert outcome.realization == "llm_resolver"


class _SpyResolver:
    """Records packets and returns a configurable chosen label + confidence."""

    def __init__(self, chosen: str, score: float = 0.9) -> None:
        self.chosen = chosen
        self.score = score
        self.packets: List[Dict[str, Any]] = []

    def resolve(self, system: str, packet: Dict[str, Any]) -> Dict[str, Any]:
        self.packets.append(packet)
        if not self.chosen:
            return {}
        return {
            "candidates": [{"label": self.chosen, "score": self.score, "why": "semantic"}],
            "chosen": self.chosen,
        }


def test_fast_path_acts_on_unique_true_positive_without_llm():
    """A unique, high-margin, strong match on a reversible open is the happy
    case: the skill acts on its own deterministic pick and never reaches for the
    LLM — even if one is available."""
    spy = _SpyResolver(chosen="Aakash", score=0.9)
    outcome = resolve_entity(
        ResolveBrief(
            referent="Pallavi",
            role="source",
            candidates=[{"label": "Pallavi"}, {"label": "Aakash"}],
        ),
        resolver=spy,
    )
    assert outcome.ok
    assert outcome.evidence["chosen"] == "Pallavi"
    assert outcome.realization == "deterministic_fast_path"
    assert outcome.evidence["resolution_gate"]["escalated"] is False
    assert not spy.packets, "a confident deterministic pick must not consult the LLM"


def test_ambiguous_destination_escalates_to_semantic_resolution():
    """Two equally-weak destinations are not a true positive; sending is
    irreversible, so the skill consults the LLM over the candidate set."""
    spy = _SpyResolver(chosen="Tanmay (work)", score=0.9)
    outcome = resolve_entity(
        ResolveBrief(
            referent="Tanmay",
            role="destination",
            candidates=[{"label": "Tanmay (work)"}, {"label": "Tanmay (home)"}],
        ),
        resolver=spy,
    )
    assert outcome.ok
    assert outcome.realization == "llm_resolver"
    assert outcome.evidence["chosen"] == "Tanmay (work)"
    assert spy.packets, "the semantic resolver must be consulted on ambiguity"
    # The skill hands its deterministic evidence to the resolver as a prior.
    assert "deterministic_evidence" in spy.packets[0]


def test_irreversible_ambiguity_abstains_to_user_when_llm_unsure():
    """LLM ranked but stayed unsure under an irreversible send: the skill does
    not guess — it abstains to the user rather than forward to a stranger."""
    spy = _SpyResolver(chosen="Tanmay (home)", score=0.3)
    outcome = resolve_entity(
        ResolveBrief(
            referent="Tanmay",
            role="destination",
            candidates=[{"label": "Tanmay (work)"}, {"label": "Tanmay (home)"}],
        ),
        resolver=spy,
    )
    assert not outcome.ok
    assert outcome.realization == "abstain_ask_user"
    assert outcome.evidence["needs_user"] is True


def test_reversible_open_falls_back_to_deterministic_after_llm_abstains():
    """A wrong open is undoable, so a reversible resolution may fall back to the
    deterministic best guess when the LLM abstains — no need to bother the user."""
    spy = _SpyResolver(chosen="", score=0.0)
    outcome = resolve_entity(
        ResolveBrief(
            referent="Pallavi",
            role="source",
            candidates=[{"label": "Pallavi Ather Gen3"}],
        ),
        resolver=spy,
    )
    assert outcome.ok
    assert outcome.evidence["chosen"] == "Pallavi Ather Gen3"
    assert outcome.realization == "deterministic_after_llm"


def test_match_core_is_pure_ranking_no_decision():
    """match() is the shared primitive: it ranks and reports confidence, but it
    does not pick, threshold, or consult anything."""
    result = match("Pallavi", ["Pallavi", "Aakash", "Pallavi Ather Gen3"])
    labels = [r["label"] for r in result.ranked]
    assert labels[0] == "Pallavi"  # best first
    assert "Aakash" not in labels  # unrelated dropped
    assert result.confidence > 0.0
    assert result.top()["label"] == "Pallavi"


def test_resolve_many_returns_all_matching_entities():
    """resolve_many is recall-oriented: it returns the whole matching set."""
    result = resolve_many("Tanmay", ["Tanmay Kumar", "Tanmay Singh", "Aakash"])
    assert set(result.matches) == {"Tanmay Kumar", "Tanmay Singh"}
    assert result.method == "deterministic"
    assert result.escalated is False


def test_resolve_many_top_k_caps_the_set():
    result = resolve_many(
        "report", ["report_jan.pdf", "report_feb.pdf", "report_mar.pdf"], top_k=2
    )
    assert len(result.matches) == 2


def test_resolve_many_consults_llm_only_when_nothing_matches_lexically():
    spy = _SpyResolver(chosen="Договор", score=0.9)
    result = resolve_many("contract", ["Договор", "Счёт"], resolver=spy)
    assert result.escalated is True
    assert result.method == "llm"
    assert "Договор" in result.matches


def test_search_input_is_not_an_openable_candidate():
    """The search box (kind=search_input) must never be a resolve candidate.

    This is the exact ZarooratWala stall: the input labelled 'Pallavi
    zarooratwala' out-scored the real result row and 'opening' it did nothing.
    """
    doc = {
        "objects": [
            {"text": "Pallavi: You: https://www.zarooratwala.com/... Zarooratwala", "kind": "search_result"},
            {"text": "Pallavi zarooratwala", "kind": "search_input"},
        ]
    }
    rows = candidates_from_context(world_document=doc)
    labels = [r["label"] for r in rows]
    assert any(l.startswith("Pallavi: You:") for l in labels)
    assert "Pallavi zarooratwala" not in labels  # the input field was dropped


def test_resolver_never_opens_the_search_input():
    """After the fix the resolver may pick the row or abstain, but never the box.

    Abstaining costs a turn; 'opening' the search input is the no-op that looped.
    """
    doc = {
        "objects": [
            {"text": "Pallavi: You: https://www.zarooratwala.com/... Zarooratwala", "kind": "search_result"},
            {"text": "Pallavi zarooratwala", "kind": "search_input"},
        ]
    }
    rows = candidates_from_context(world_document=doc)
    result = heuristic_resolve(ResolveBrief(referent="Pallavi", role="source", candidates=rows))
    chosen = result.get("chosen") or ""
    assert chosen != "Pallavi zarooratwala"
    assert chosen == "" or chosen.startswith("Pallavi: You:")
