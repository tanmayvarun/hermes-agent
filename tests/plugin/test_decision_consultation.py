"""The decision-maker chooses a capability over the accepted world, not a script."""

from __future__ import annotations

from typing import Any, Dict, List

from plugin.agent.decision_consultation import (
    DecisionBrief,
    _ground_choice_on_world,
    _perceptor_geometry_for_choice,
    apply_decision_consultation,
    build_decision_brief,
    consult_decision,
    navigation_options,
    sanitize_decision,
    task_state_from_context,
)
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.unified_cognition import UnifiedProposal


def _goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )


def _features(**extras: Any) -> StateFeatures:
    base = {"app_content_node_count": 0}
    base.update(extras)
    return StateFeatures(
        conversation_open=bool(extras.get("conversation_open")),
        extras=base,
    )


def test_brief_carries_world_task_navigation_and_goal():
    doc = {
        "surface": "search",
        "open_conversation": "",
        "objects": [{"text": "Pallavi", "kind": "contact"}],
    }
    brief = build_decision_brief(_goal(), world_document=doc, features=_features())
    packet = brief.to_packet()
    assert packet["goal"]["source_conversation"] == "Pallavi"
    assert packet["world_model"]["surface"] == "search"
    assert packet["task_state"]["phase"] == "reach_source"
    assert "reachable_surfaces" in packet["navigation"]
    assert "resolve_entity" in packet["allowed_capabilities"]
    assert "Pallavi" in packet["visible_candidates"]


def test_brief_carries_the_registry_disclosure_view():
    """The packet exposes a progressive-disclosure view of the registry, not a
    bare verb list: a relevant shortlist plus the family taxonomy and counts."""
    doc = {"surface": "search", "objects": [{"text": "Pallavi", "kind": "contact"}]}
    brief = build_decision_brief(_goal(), world_document=doc, features=_features())
    disclosure = brief.to_packet()["capability_disclosure"]
    assert disclosure["relevant"], "a situation shortlist must be offered"
    assert disclosure["installed_count"] >= disclosure["relevant_count"]
    assert isinstance(disclosure["families"], dict) and disclosure["families"]


def test_situation_facts_gate_the_registry_ordering():
    """When candidates are visible, candidate/entity facts hold, so the picker
    verbs the situation satisfies are ranked ahead of ones that cannot run."""
    from plugin.agent.decision_consultation import TaskState, situation_facts

    state = TaskState(phase="reach_source", open_conversation="Pallavi", source_chat_open=True)
    facts = situation_facts(state, candidates=["Pallavi", "Pallavi Gen3"], goal={"source_conversation": "Pallavi"})
    assert "candidate_set" in facts
    assert "addressable_entity" in facts
    assert "task_evidence" in facts


def test_navigation_forbids_sidebar_search_on_picker():
    nav = navigation_options("forward_picker", "destination_filter")
    assert "compose_search_query" in nav.forbidden
    assert "open_search" in nav.forbidden


def test_navigation_lists_reachable_surfaces_from_conversation():
    nav = navigation_options("conversation", "in_chat_or_composer")
    assert "context_menu" in nav.reachable
    assert "reveal_actions" in nav.reachable["context_menu"]
    assert not nav.forbidden


def test_task_state_wrong_source_open_is_not_hunt_phase():
    state = task_state_from_context(
        _goal(),
        world_document={"surface": "conversation", "open_conversation": "Pallavi Ather Gen3"},
        features=_features(conversation_open=True),
    )
    assert state.source_chat_open is False
    assert state.phase == "reach_source"


def test_task_state_matching_source_open_is_hunt_phase():
    state = task_state_from_context(
        _goal(),
        world_document={"surface": "conversation", "open_conversation": "Pallavi"},
        features=_features(conversation_open=True),
    )
    assert state.source_chat_open is True
    assert state.phase == "hunt_content"


def test_task_state_clears_stale_filter_geometry_outside_reach_source():
    """Live 125715: Search stash must not survive into conversation/menu phases."""
    from plugin.agent.runtime.state import ExecutionState

    exec_state = ExecutionState()
    exec_state.last_filter_geometry = {
        "target_label": "Search",
        "target_point": [160.0, 106.0],
        "geometry_source": "ax_evidence",
    }
    task_state_from_context(
        _goal(),
        world_document={"surface": "conversation", "open_conversation": "Pallavi"},
        features=_features(conversation_open=True),
        execution_state=exec_state,
    )
    assert exec_state.last_filter_geometry is None


def test_sanitize_rejects_unknown_and_forbidden_capabilities():
    brief = build_decision_brief(
        _goal(),
        world_document={
            "surface": "forward_picker",
            "focused_field_role": "destination_filter",
            "objects": [{"text": "Tanmay"}],
        },
        features=_features(),
    )
    assert not sanitize_decision({"capability": "teleport"}, brief).ok
    assert not sanitize_decision({"capability": "compose_search_query"}, brief).ok
    assert sanitize_decision({"capability": "resolve_entity", "target": "Tanmay"}, brief).ok


def test_sanitize_rejects_locate_outside_source_chat():
    brief = build_decision_brief(
        _goal(),
        world_document={"surface": "conversation", "open_conversation": "Pallavi Ather Gen3"},
        features=_features(conversation_open=True),
    )
    decided = sanitize_decision(
        {"capability": "locate_content", "target": "zarooratwala"}, brief
    )
    assert not decided.ok
    assert "source chat" in decided.why


def test_sanitize_rejects_commit_before_commit_phase():
    brief = build_decision_brief(
        _goal(),
        world_document={"surface": "chat_list"},
        features=_features(),
    )
    assert not sanitize_decision({"capability": "commit_irreversible", "target": "Send"}, brief).ok


class _FakeChooser:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self.payload = payload
        self.packets: List[Dict[str, Any]] = []

    def choose(self, system: str, packet: Dict[str, Any]) -> Dict[str, Any]:
        self.packets.append(packet)
        assert "task_state" in packet
        assert "navigation" in packet
        assert "world_model" in packet
        assert "goal" in packet
        return self.payload


def test_llm_choice_is_used_when_valid():
    brief = build_decision_brief(
        _goal(),
        world_document={
            "surface": "search",
            "objects": [{"text": "Pallavi"}, {"text": "Pallavi Ather Gen3"}],
        },
        features=_features(),
    )
    chooser = _FakeChooser({"capability": "resolve_entity", "target": "Pallavi", "why": "row"})
    decided = consult_decision(brief, chooser=chooser)
    assert decided.ok
    assert decided.capability == "resolve_entity"
    assert decided.realization == "llm_decision"
    assert "heuristic_suggestion" not in chooser.packets[0]


def test_invalid_llm_choice_declines_to_observe():
    brief = build_decision_brief(
        _goal(),
        world_document={"surface": "chat_list", "objects": []},
        features=_features(),
    )
    decided = consult_decision(brief, chooser=_FakeChooser({"capability": "nonsense"}))
    assert decided.ok
    assert decided.realization == "llm_required_miss"
    assert decided.capability == "observe"


def test_rejected_llm_choice_retries_once_with_feedback():
    brief = build_decision_brief(
        _goal(),
        world_document={"surface": "chat_list", "objects": []},
        features=_features(),
    )

    class _RetryChooser:
        def __init__(self) -> None:
            self.packets: List[Dict[str, Any]] = []

        def choose(self, system: str, packet: Dict[str, Any]) -> Dict[str, Any]:
            self.packets.append(packet)
            if len(self.packets) == 1:
                return {"capability": "invoke_affordance", "target": "Forward", "why": "bad"}
            return {"capability": "compose_search_query", "target": "", "why": "search"}

    chooser = _RetryChooser()
    decided = consult_decision(brief, chooser=chooser)
    assert decided.ok
    assert decided.capability == "compose_search_query"
    assert decided.realization == "llm_decision_retry"
    assert len(chooser.packets) == 2
    assert "prior_rejection" in chooser.packets[1]


def _proposal(surface: str, family: str, **state: Any) -> UnifiedProposal:
    observed = {"surface": surface}
    observed.update(state)
    return UnifiedProposal(
        observed_state=observed,
        world_model={"surface": surface, **state},
        next_action={"family": family, "text": "Pallavi", "target_point": [200, 254]},
        confidence=0.9,
    )


class _State:
    def __init__(self, document: Dict[str, Any]) -> None:
        self.unified_world_document = document
        self.focused_field_role = str(document.get("focused_field_role") or "")
        self.last_plan_step = None
        self.search_attempt_log: List[Dict[str, Any]] = []


def test_compose_search_on_conversation_grounds_search_field_not_contact():
    """Live 095344: surface=conversation + target Pallavi must bind Search."""
    document = {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "objects": [
            {
                "id": "search_field",
                "kind": "search_field",
                "text": "Search",
                "point": [150, 90],
            },
            {
                "id": "900000",
                "kind": "contact",
                "text": "Pallavi",
                "matches_goal": True,
                "point": [2127, 363],
            },
        ],
    }
    grounded = _ground_choice_on_world(
        document, "compose_search_query", "Pallavi"
    )
    assert grounded.get("target_id") == "search_field"
    assert grounded.get("target_point") == [150, 90]
    assert "search" in str(grounded.get("target_label") or "").lower()
    assert grounded.get("target_id") != "900000"


def test_apply_brain_choice_on_picker_grounds_from_world_objects():
    document = {
        "surface": "forward_picker",
        "focused_field_role": "destination_filter",
        "objects": [
            {"id": "row-1", "text": "Tanmay", "point": [10, 20]},
            {"text": "Tanmay (you)"},
        ],
    }
    proposal = _proposal("forward_picker", "type_query")
    features = _features()
    trace = apply_decision_consultation(
        proposal,
        _goal(),
        features=features,
        execution_state=_State(document),
        chooser=_FakeChooser({"capability": "resolve_entity", "target": "Tanmay"}),
    )
    assert trace["applied"] is True
    assert proposal.next_action["family"] == "resolve_entity"
    assert proposal.next_action["text"] == "Tanmay"
    assert proposal.next_action["target_id"] == "row-1"
    assert proposal.next_action["target_point"] == [10, 20]
    assert "perceptor_family" not in features.extras["decision_consultation"]
    assert "affordance_frontier" in build_decision_brief(
        _goal(), world_document=document, features=features, execution_state=_State(document)
    ).to_packet()


def test_apply_grounds_pointer_family_from_accepted_objects():
    document = {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "objects": [
            {
                "id": 7,
                "kind": "message_bubble",
                "text": "https://www.zarooratwala.com/order",
                "matches_goal": True,
                "point": [200, 254],
            }
        ],
    }
    proposal = _proposal("conversation", "reveal_actions")
    # last_locate_query alone is not content_located (185549); found/achieved required.
    trace = apply_decision_consultation(
        proposal,
        _goal(),
        features=_features(
            conversation_open=True,
            last_locate_query="zarooratwala",
            last_locate_found=True,
            last_locate_effect_status="achieved",
        ),
        execution_state=_State(document),
        chooser=_FakeChooser(
            {
                "capability": "reveal_actions",
                "target": "https://www.zarooratwala.com/order",
            }
        ),
    )
    assert trace["applied"] is True
    assert proposal.next_action["target_point"] == [200, 254]
    assert str(proposal.next_action["target_id"]) == "7"


def test_apply_sets_observe_when_brain_asks_to_look_again():
    document = {"surface": "forward_picker", "focused_field_role": "destination_filter"}
    proposal = _proposal("forward_picker", "type_query")
    trace = apply_decision_consultation(
        proposal,
        _goal(),
        features=_features(),
        execution_state=_State(document),
        chooser=_FakeChooser({"capability": "observe"}),
    )
    assert trace["applied"] is True
    assert proposal.next_action["family"] == "observe"


def test_perceptor_cta_point_survives_brain_over_stale_world_document():
    """Live 011358: perceptor had Pallavi at [167,175]; stale accepted doc still
    had pre-search [167,497]; brain wipe+reground opened Ather at ~[223,273].
    Same-family open_entity must carry the perceptor CTA point to the actor.
    """
    stale_doc = {
        "surface": "chat_list",
        "objects": [
            {
                "id": "chat_pallavi",
                "kind": "chat_row",
                "text": 'Pallavi Reacted ❤️ to "https://photos.app.goo.g...',
                "point": [167, 497],
                "matches_goal": True,
            },
            {
                "id": "raman",
                "kind": "chat_row",
                "text": "Raman achha ye hai...",
                "point": [167, 702],
                "matches_goal": False,
            },
        ],
    }
    fresh_wm = {
        "surface": "chat_list",
        "objects": [
            {
                "id": "chat_pallavi_top",
                "kind": "chat_row",
                "text": 'Pallavi Reacted ❤️ to "https://photos.app.goo.g...',
                "point": [167, 175],
                "matches_goal": True,
            },
            {
                "id": "ather",
                "kind": "chat_row",
                "text": "Pallavi Ather Gen3 Swytchd Tousif created this group",
                "point": [167, 245],
                "matches_goal": False,
            },
        ],
    }
    proposal = UnifiedProposal(
        observed_state={"surface": "chat_list"},
        world_model=fresh_wm,
        next_action={
            "family": "open_entity",
            "text": "Click top Pallavi chat row",
            "target_label": 'Pallavi Reacted ❤️ to "https://photos.app.goo.g...',
            "target_id": "chat_pallavi_top",
            "target_point": [167, 175],
        },
        confidence=0.93,
    )
    # Post-search chat_list: search already typed, so open_entity is allowed.
    apply_decision_consultation(
        proposal,
        _goal(),
        features=_features(search_query="zarooratwala Pallavi"),
        execution_state=_State(stale_doc),
        chooser=_FakeChooser(
            {
                "capability": "open_entity",
                "target": "Click top Pallavi chat row",
                "confidence": 0.93,
            }
        ),
    )
    assert proposal.next_action["family"] == "open_entity"
    assert proposal.next_action["target_point"] == [167.0, 175.0]
    assert proposal.next_action.get("geometry_source") == "perceptor"
    assert proposal.next_action.get("target_id") == "chat_pallavi_top"
    # Must not latch the neighboring group row or the stale pre-search Y.
    assert proposal.next_action["target_point"] != [167, 245]
    assert proposal.next_action["target_point"] != [167, 497]


def test_sanitize_remaps_right_click_to_reveal_actions():
    brief = build_decision_brief(
        _goal(),
        world_document={"surface": "conversation", "open_conversation": "Pallavi"},
        features=_features(conversation_open=True, timeline_query_hit=True),
    )
    decided = sanitize_decision(
        {"capability": "right_click", "target": "zarooratwala.com", "why": "menu"},
        brief,
    )
    assert decided.ok
    assert decided.capability == "reveal_actions"


def test_right_click_perceptor_geometry_carries_to_reveal_actions():
    geo = _perceptor_geometry_for_choice(
        {
            "family": "right_click",
            "target": "zarooratwala message edge",
            "target_point": [3317, 939],
            "target_id": None,
        },
        "reveal_actions",
        "https://www.zarooratwala.com/",
    )
    assert geo.get("target_point") == [3317.0, 939.0]


def test_sanitize_requires_compose_before_open_when_link_unresolved():
    brief = build_decision_brief(
        _goal(),
        world_document={
            "surface": "chat_list",
            "objects": [{"text": "Pallavi - zarooratwala Pallavi", "matches_goal": True}],
        },
        features=_features(),
    )
    rejected = sanitize_decision(
        {"capability": "open_entity", "target": "Pallavi"}, brief
    )
    assert not rejected.ok
    assert "compose_search_query" in rejected.why
    assert sanitize_decision({"capability": "compose_search_query", "target": ""}, brief).ok


def test_sanitize_compose_first_even_when_surface_misread_as_conversation():
    """Live 030941: empty open + surface=conversation still skipped search."""
    brief = build_decision_brief(
        _goal(),
        world_document={
            "surface": "conversation",
            "open_conversation": "",
            "objects": [{"text": "Pallavi - JI zarooratwala Pallavi", "matches_goal": True}],
        },
        features=_features(conversation_open=True),
    )
    assert brief.task_state.phase == "reach_source"
    assert brief.task_state.source_chat_open is False
    rejected = sanitize_decision(
        {"capability": "open_entity", "target": "Pallavi - JI zarooratwala Pallavi"},
        brief,
    )
    assert not rejected.ok
    assert "compose_search_query" in rejected.why


def test_sanitize_rejects_reopen_row_when_source_open_and_link_unlocated():
    """Live 031605: leftover open Pallavi → open_entity preview instead of locate."""
    brief = build_decision_brief(
        _goal(),
        world_document={
            "surface": "conversation",
            "open_conversation": "Pallavi",
            "objects": [{"text": "Pallavi - zarooratwala Pallavi", "matches_goal": True}],
        },
        features=_features(conversation_open=True),
    )
    assert brief.task_state.source_chat_open is True
    assert brief.task_state.phase == "hunt_content"
    rejected = sanitize_decision(
        {"capability": "open_entity", "target": "Pallavi - zarooratwala Pallavi"},
        brief,
    )
    assert not rejected.ok
    assert "locate_content" in rejected.why
    assert sanitize_decision(
        {"capability": "locate_content", "target": "zarooratwala"}, brief
    ).ok


def test_reflect_repair_open_entity_is_rewritten_to_compose_first():
    """Live 031818: reflect_repair overrode sanitize; post-gate must restore compose."""
    from plugin.agent.decision_consultation import apply_decision_consultation
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.unified_cognition import UnifiedProposal

    document = {
        "surface": "chat_list",
        "open_conversation": "",
        "objects": [
            {
                "id": "search_field",
                "kind": "search_field",
                "text": "Search",
                "point": [150, 90],
            },
            # Preview text only — no actuatable geometry. An actuatable source
            # chat_row may open despite unpaid link_query (live 145943); this
            # golden keeps the compose-first path for non-actuatable previews.
            {
                "id": "pallavi_preview",
                "text": "Pallavi - zarooratwala Pallavi",
                "matches_goal": True,
            },
        ],
    }
    proposal = UnifiedProposal(
        observed_state={"surface": "chat_list"},
        world_model=document,
        next_action={},
        suggested_actions=[
            {
                "family": "open_entity",
                "text": "Pallavi",
                "target_point": [2176, 173],
            }
        ],
        confidence=0.9,
    )
    state = ExecutionState()
    state.unified_world_document = document
    state.perception_mode = "reflect"
    state.last_surprise_explanation = {
        "cause": "motor_miss",
        "recommended_next": "retry_with_corrected_geometry",
        "detail": "Re-issue open on Pallavi",
        "confidence": 0.9,
        "authoritative": True,
        "repair": {"kind": "retry_with_corrected_geometry", "capability": "open_entity", "target": "Pallavi"},
    }

    class _ForceOpen:
        def choose(self, system: str, packet: dict) -> dict:
            return {
                "capability": "compose_search_query",
                "target": "",
                "why": "search first",
                "confidence": 0.9,
            }

    # Even if reflect repair tries to force open_entity, compose-first wins.
    # Simulate repair by monkeypatching after consult via chooser that opens —
    # apply_surprise_explanation will rewrite when explanation is authoritative.
    class _OpenChooser:
        def choose(self, system: str, packet: dict) -> dict:
            return {
                "capability": "open_entity",
                "target": "Pallavi - zarooratwala Pallavi",
                "why": "row",
                "confidence": 0.9,
            }

    # First: sanitize alone rejects open; consultation retries to observe/compose.
    # Drive repair path: chooser returns observe, then surprise explanation forces open.
    class _ObserveThenRepair:
        def choose(self, system: str, packet: dict) -> dict:
            return {"capability": "observe", "target": "", "why": "look", "confidence": 0.5}

    # Patch apply_surprise_explanation to force open_entity like live 031818.
    import plugin.agent.decision_consultation as dc
    import plugin.agent.brain as brain_mod

    real_apply = brain_mod.apply_surprise_explanation

    def _force_open(outcome, execution_state, *, features=None):
        from plugin.agent.decision_consultation import DecisionOutcome

        return DecisionOutcome(
            ok=True,
            capability="open_entity",
            target="Pallavi - zarooratwala Pallavi",
            why="reflect repair retry_with_corrected_geometry",
            confidence=0.85,
            realization="reflect_repair:retry_with_corrected_geometry",
        )

    brain_mod.apply_surprise_explanation = _force_open
    try:
        trace = apply_decision_consultation(
            proposal,
            _goal(),
            features=_features(),
            execution_state=state,
            chooser=_ObserveThenRepair(),
        )
    finally:
        brain_mod.apply_surprise_explanation = real_apply

    assert proposal.next_action.get("family") == "compose_search_query"
    assert "sanitize_compose_first" in str(trace.get("realization") or "")
    # Must bind Search — never the matches_goal chat row (095344).
    assert proposal.next_action.get("target_id") == "search_field"
    assert proposal.next_action.get("target_point") == [150, 90]


def test_sanitize_allows_open_after_search_typed():
    brief = build_decision_brief(
        _goal(),
        world_document={"surface": "chat_list", "objects": [{"text": "Pallavi"}]},
        features=_features(search_query="zarooratwala Pallavi"),
    )
    decided = sanitize_decision(
        {"capability": "open_entity", "target": "Pallavi"}, brief
    )
    assert decided.ok


def test_reveal_on_search_rewrites_to_open_entity_not_observe():
    """Live 131221: right_click/reveal on search must become open_entity, not Observe."""
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.unified_cognition import UnifiedProposal

    document = {
        "surface": "search",
        "open_conversation": "",
        "focused_field_role": "sidebar_search",
        "objects": [
            {
                "id": "obj_msg_link_1",
                "kind": "chat_row",
                "text": "Pallavi https://www.zarooratwala.com/?...",
                "point": [308, 355],
                "matches_goal": True,
                "sender": "Pallavi",
            },
            {
                "id": "obj_msg_link_2",
                "kind": "chat_row",
                "text": "https://www.instagram.com/zarooratwala?...",
                "point": [308, 630],
                "matches_goal": False,
            },
        ],
    }
    proposal = UnifiedProposal(
        observed_state={"surface": "search"},
        world_model=document,
        next_action={
            "family": "right_click",
            "text": "obj_msg_link_1",
            "target_point": [308, 355],
            "confidence": 0.95,
        },
        confidence=0.9,
    )

    class _RevealChooser:
        def choose(self, system: str, packet: dict) -> dict:
            return {
                "capability": "reveal_actions",
                "target": "Pallavi https://www.zarooratwala.com/?...",
                "why": "right-click for Forward",
                "confidence": 0.95,
            }

    state = ExecutionState()
    state.search_attempt_log  # touch
    try:
        state.record_search_attempt("zarooratwala Pallavi", "typed")
    except Exception:
        pass
    trace = apply_decision_consultation(
        proposal,
        _goal(),
        features=_features(search_query="zarooratwala Pallavi", wa_screen="SEARCH"),
        execution_state=state,
        chooser=_RevealChooser(),
    )
    assert proposal.next_action.get("family") == "open_entity", proposal.next_action
    realization = str(trace.get("realization") or "")
    assert any(
        token in realization
        for token in (
            "sanitize_open_first",
            "search_results_open",
            "search_commit_chosen",
            "search_continue",
            "llm_required_open_first",
        )
    ), realization
    assert "zarooratwala.com" in str(proposal.next_action.get("text") or "").lower() or (
        "zarooratwala.com"
        in str(proposal.next_action.get("target_label") or "").lower()
    )


def test_observe_on_search_results_promotes_to_open_entity():
    """Live 131221: Observe while matches_goal search rows are visible must open."""
    from plugin.agent.unified_cognition import UnifiedProposal

    document = {
        "surface": "search",
        "objects": [
            {
                "id": "row1",
                "kind": "search_result",
                "text": "Pallavi - https://www.zarooratwala.com/",
                "point": [207, 360],
                "matches_goal": True,
                "sender": "Pallavi",
            }
        ],
    }
    proposal = UnifiedProposal(
        observed_state={"surface": "search"},
        world_model=document,
        next_action={"family": "observe", "confidence": 0.4},
        confidence=0.4,
    )

    class _ObserveChooser:
        def choose(self, system: str, packet: dict) -> dict:
            return {
                "capability": "observe",
                "target": "",
                "why": "model_requested_observe",
                "confidence": 0.4,
            }

    trace = apply_decision_consultation(
        proposal,
        _goal(),
        features=_features(wa_screen="SEARCH", search_query="zarooratwala"),
        chooser=_ObserveChooser(),
    )
    assert proposal.next_action.get("family") == "open_entity", proposal.next_action
    realization = str(trace.get("realization") or "")
    assert any(
        token in realization
        for token in ("search_results_open", "search_commit_chosen", "search_continue")
    ), realization


def test_sanitize_rejects_invoke_on_non_url_link_query_text():
    brief = build_decision_brief(
        _goal(),
        world_document={"surface": "conversation", "open_conversation": "Pallavi"},
        features=_features(conversation_open=True, timeline_query_hit=True),
    )
    rejected = sanitize_decision(
        {
            "capability": "invoke_affordance",
            "target": "zarooratwala Pallavi 12:33 AM",
            "why": "click message",
        },
        brief,
    )
    assert not rejected.ok
    assert "non-URL" in rejected.why
    assert sanitize_decision(
        {"capability": "reveal_actions", "target": "https://www.zarooratwala.com/?"},
        brief,
    ).ok


def test_compose_binds_stashed_filter_geometry_when_frontier_lacks_actuators():
    """Live 123746: perception-stashed AX/OCR Search binds even if frontier is thin."""
    from plugin.agent.runtime.state import ExecutionState

    document = {
        "surface": "chat_list",
        "objects": [
            {
                "id": "pallavi_row",
                "kind": "chat_row",
                "text": "Pallavi",
                "matches_goal": True,
                "point": [2176, 173],
            }
        ],
    }
    state = ExecutionState()
    state.unified_world_document = document
    # Frontier only has the chat row (AX Search never made actuators).
    state.last_affordance_frontier = {
        "surface": "chat_list",
        "observed_actions": [
            {"family": "open_entity", "target_label": "Pallavi", "target_id": "pallavi_row"}
        ],
    }
    state.last_filter_geometry = {
        "target_label": "Search",
        "target_point": [160.0, 106.0],
        "bounds": [127.0, 98.5, 66.8, 16.6],
        "coordinate_space": "screen",
        "geometry_source": "ax_evidence",
        "kind": "search_field",
        "target_id": 14,
    }
    proposal = UnifiedProposal(
        observed_state={"surface": "chat_list"},
        world_model=document,
        next_action={},
        confidence=0.9,
    )

    class _ComposeChooser:
        def choose(self, system: str, packet: dict) -> dict:
            return {
                "capability": "compose_search_query",
                "target": "",
                "why": "search",
                "confidence": 0.9,
            }

    apply_decision_consultation(
        proposal,
        _goal(),
        features=_features(),
        execution_state=state,
        chooser=_ComposeChooser(),
    )
    assert proposal.next_action.get("family") == "compose_search_query"
    assert proposal.next_action.get("target_point") == [160.0, 106.0]
    assert proposal.next_action.get("target_id") != "pallavi_row"


def test_compose_binds_ax_frontier_search_when_vlm_objects_are_only_rows():
    """Live 123746: AX Q Search on frontier must ground compose; never chat_row."""
    from plugin.agent.runtime.state import ExecutionState

    document = {
        "surface": "chat_list",
        "open_conversation": "",
        "objects": [
            {
                "id": "pallavi_row",
                "kind": "chat_row",
                "text": "Pallavi",
                "matches_goal": True,
                "point": [2176, 173],
            },
            {
                "id": "tanmay_row",
                "kind": "chat_row",
                "text": "Tanmay",
                "point": [2176, 240],
            },
        ],
    }
    state = ExecutionState()
    state.unified_world_document = document
    state.last_affordance_frontier = {
        "surface": "chat_list",
        "observed_actions": [
            {
                "family": "compose_search_query",
                "target_label": "Q Search",
                "target_id": 14,
                "actuators": [
                    {"type": "coordinate_click", "point": [160, 106], "confidence": 0.9}
                ],
            }
        ],
    }
    proposal = UnifiedProposal(
        observed_state={"surface": "chat_list"},
        world_model=document,
        next_action={},
        confidence=0.9,
    )

    class _ComposeChooser:
        def choose(self, system: str, packet: dict) -> dict:
            return {
                "capability": "compose_search_query",
                "target": "",
                "why": "search for Pallavi",
                "confidence": 0.9,
            }

    trace = apply_decision_consultation(
        proposal,
        _goal(),
        features=_features(),
        execution_state=state,
        chooser=_ComposeChooser(),
    )
    assert proposal.next_action.get("family") == "compose_search_query"
    assert proposal.next_action.get("target_point") == [160.0, 106.0]
    assert "search" in str(proposal.next_action.get("target_label") or "").lower()
    assert proposal.next_action.get("target_id") != "pallavi_row"
    assert "geometry_required_missing" not in str(trace.get("realization") or "")


def test_compose_binds_ax_entity_search_without_frontier_actuators():
    """WorldModel entity Q Search bounds bind when frontier actuators are absent."""
    from plugin.agent.runtime.state import ExecutionState
    from plugin.worldmodel.entities.entity import Entity
    from plugin.worldmodel.model import WorldModel

    document = {
        "surface": "chat_list",
        "objects": [
            {
                "id": "pallavi_row",
                "kind": "chat_row",
                "text": "Pallavi",
                "matches_goal": True,
                "point": [2176, 173],
            }
        ],
    }
    state = ExecutionState()
    state.unified_world_document = document
    world = WorldModel()
    world.entities[14] = Entity(
        id=14,
        entity_type="static",
        semantic_role="status_bar",
        label="Q Search",
        role="AXStaticText",
        bounds=(127.0, 98.5, 66.8, 16.6),
    )
    state.world_model = world
    proposal = UnifiedProposal(
        observed_state={"surface": "chat_list"},
        world_model=document,
        next_action={},
        confidence=0.9,
    )

    class _ComposeChooser:
        def choose(self, system: str, packet: dict) -> dict:
            return {
                "capability": "compose_search_query",
                "target": "",
                "why": "search",
                "confidence": 0.9,
            }

    apply_decision_consultation(
        proposal,
        _goal(),
        features=_features(),
        execution_state=state,
        chooser=_ComposeChooser(),
    )
    assert proposal.next_action.get("family") == "compose_search_query"
    point = proposal.next_action.get("target_point")
    assert isinstance(point, list) and len(point) == 2
    assert abs(point[0] - (127.0 + 66.8 / 2.0)) < 0.5
    assert abs(point[1] - (98.5 + 16.6 / 2.0)) < 0.5
    assert proposal.next_action.get("target_id") != "pallavi_row"


def test_compose_still_demotes_when_no_search_geometry_anywhere():
    """Without AX/OCR Search, geometry_required_missing → observe (095344 invent closed)."""
    from plugin.agent.runtime.state import ExecutionState

    document = {
        "surface": "chat_list",
        "objects": [
            {
                "id": "pallavi_row",
                "kind": "chat_row",
                "text": "Pallavi",
                "matches_goal": True,
                "point": [2176, 173],
            }
        ],
    }
    state = ExecutionState()
    state.unified_world_document = document
    proposal = UnifiedProposal(
        observed_state={"surface": "chat_list"},
        world_model=document,
        next_action={},
        confidence=0.9,
    )

    class _ComposeChooser:
        def choose(self, system: str, packet: dict) -> dict:
            return {
                "capability": "compose_search_query",
                "target": "",
                "why": "search",
                "confidence": 0.9,
            }

    trace = apply_decision_consultation(
        proposal,
        _goal(),
        features=_features(),
        execution_state=state,
        chooser=_ComposeChooser(),
    )
    assert proposal.next_action.get("family") == "observe"
    assert "geometry_required_missing" in str(trace.get("realization") or "")


def test_reconcile_rejects_cross_pane_perceptor_point():
    from plugin.agent.decision_consultation import _reconcile_perceptor_with_inventory

    out = _reconcile_perceptor_with_inventory(
        {"target_point": [1233, 241], "target_label": "example.com"},
        {"target_point": [310, 240]},
        {
            "objects": [
                {
                    "id": "msg1",
                    "text": "https://example.com/x",
                    "point": [1233, 241],
                    "bounds": [1100, 200, 400, 80],
                }
            ]
        },
    )
    assert out.get("geometry_source") == "inventory"
    assert out.get("geometry_rejected_cross_pane") is True
    assert abs(float(out["target_point"][0]) - 1233) < 1.0


def test_sanitize_blocks_same_content_act_when_reveal_unclosed():
    brief = DecisionBrief(
        goal={
            "operation": "whatsapp_forward_message",
            "source_conversation": "Pallavi",
            "source_query": "example",
            "destination": "Tanmay",
        },
        world={"surface": "conversation"},
        capabilities=["select_content", "reveal_actions", "observe"],
        meta_action="act",
        effect_closure={
            "incomplete_reveal": True,
            "fingerprint": "reveal_actions|https://example.com/x|580,234",
        },
        search_episode={
            "status": "complete",
            "chosen_label": "https://example.com/x",
        },
    )
    rejected = sanitize_decision(
        {
            "capability": "select_content",
            "target": "https://example.com/x",
            "why": "try again",
        },
        brief,
    )
    assert not rejected.ok
    assert "effect unclosed" in rejected.why


def test_sanitize_blocks_object_scoped_invoke_without_selected_referent():
    from plugin.agent.decision_consultation import TaskState

    brief = DecisionBrief(
        goal={
            "operation": "whatsapp_forward_message",
            "source_conversation": "Alice",
            "source_query": "example",
            "destination": "Bob",
        },
        world={"surface": "conversation"},
        capabilities=["invoke_affordance", "select_content", "observe"],
        meta_action="act",
        task_state=TaskState(
            phase="invoke_forward",
            source_chat_open=True,
            content_located=True,
            referent_selected=False,
            referent_binding_status="ambiguous",
            selection_consistent=True,
        ),
        search_episode={
            "status": "complete",
            "chosen_label": "https://example.com/x",
        },
    )
    rejected = sanitize_decision(
        {"capability": "invoke_affordance", "target": "Forward", "why": "toolbar"},
        brief,
    )
    assert not rejected.ok
    assert "ambiguous" in rejected.why or "selected referent" in rejected.why


def test_sanitize_allows_overlay_invoke_under_act_clear_despite_ambiguous_referent():
    """Live 173658: menu open + act_clear must not deadlock on sticky ambiguous."""
    from plugin.agent.decision_consultation import TaskState

    brief = DecisionBrief(
        goal={
            "operation": "whatsapp_forward_message",
            "source_conversation": "Alice",
            "source_query": "example",
            "destination": "Bob",
        },
        world={"surface": "context_menu"},
        capabilities=["invoke_affordance", "select_content", "observe"],
        meta_action="act",
        act_clear=True,
        affordance_stance="act_clear",
        task_state=TaskState(
            phase="invoke_forward",
            source_chat_open=True,
            content_located=True,
            referent_selected=False,
            referent_binding_status="ambiguous",
            selection_consistent=True,
        ),
        search_episode={
            "status": "complete",
            "chosen_label": "https://example.com/x",
        },
    )
    ok = sanitize_decision(
        {
            "capability": "invoke_affordance",
            "target": "Forward",
            "why": "menu",
            "confidence": 0.9,
        },
        brief,
    )
    assert ok.ok
    assert ok.capability == "invoke_affordance"


def test_sanitize_allows_forward_invoke_when_referent_selected():
    from plugin.agent.decision_consultation import TaskState

    brief = DecisionBrief(
        goal={
            "operation": "whatsapp_forward_message",
            "source_conversation": "Alice",
            "source_query": "example",
            "destination": "Bob",
        },
        world={"surface": "context_menu"},
        capabilities=["invoke_affordance", "select_content", "observe"],
        meta_action="act",
        task_state=TaskState(
            phase="invoke_forward",
            source_chat_open=True,
            content_located=True,
            referent_selected=True,
            referent_binding_status="provisional",
            selection_consistent=True,
        ),
        search_episode={
            "status": "complete",
            "chosen_label": "https://example.com/x",
        },
    )
    ok = sanitize_decision(
        {"capability": "invoke_affordance", "target": "Forward", "why": "menu", "confidence": 0.9},
        brief,
    )
    assert ok.ok
    assert ok.capability == "invoke_affordance"


def test_sanitize_blocks_reinvoke_when_referent_repair_owed():
    from plugin.agent.decision_consultation import TaskState

    brief = DecisionBrief(
        goal={
            "operation": "whatsapp_forward_message",
            "source_conversation": "Alice",
            "source_query": "example",
            "destination": "Bob",
        },
        world={"surface": "selection_mode"},
        capabilities=["invoke_affordance", "select_content", "observe"],
        meta_action="act",
        task_state=TaskState(
            phase="invoke_forward",
            source_chat_open=True,
            referent_selected=False,
            referent_binding_status="provisional",
            selection_consistent=False,
        ),
        effect_closure={
            "referent_repair_owed": True,
            "fingerprint": "invoke_affordance|Forward|1270,332",
        },
        search_episode={
            "status": "complete",
            "chosen_label": "https://example.com/x",
        },
    )
    rejected = sanitize_decision(
        {"capability": "invoke_affordance", "target": "Forward", "why": "retry"},
        brief,
    )
    assert not rejected.ok
    assert "referent" in rejected.why.lower() or "select" in rejected.why.lower()
