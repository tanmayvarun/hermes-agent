"""The decision-maker chooses a capability over the accepted world, not a script."""

from __future__ import annotations

from typing import Any, Dict, List

from plugin.agent.decision_consultation import (
    DecisionBrief,
    apply_decision_consultation,
    build_decision_brief,
    consult_decision,
    heuristic_decision,
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


def test_heuristic_picks_resolve_on_picker():
    brief = build_decision_brief(
        _goal(),
        world_document={
            "surface": "forward_picker",
            "focused_field_role": "destination_filter",
            "objects": [{"text": "Tanmay (you)"}, {"text": "Tanmay"}],
        },
        features=_features(),
    )
    decided = heuristic_decision(brief)
    assert decided.capability == "resolve_entity"
    assert decided.target == "Tanmay"


def test_heuristic_hunts_only_in_matching_source_chat():
    brief = build_decision_brief(
        _goal(),
        world_document={"surface": "conversation", "open_conversation": "Pallavi"},
        features=_features(conversation_open=True),
    )
    decided = heuristic_decision(brief)
    assert decided.capability == "locate_content"
    assert decided.target == "zarooratwala"


def test_heuristic_composes_when_no_candidates_visible():
    brief = build_decision_brief(
        _goal(),
        world_document={"surface": "chat_list", "objects": []},
        features=_features(),
    )
    decided = heuristic_decision(brief)
    assert decided.capability == "compose_search_query"


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
    assert chooser.packets[0]["heuristic_suggestion"]["capability"]


def test_invalid_llm_choice_falls_back_to_heuristic():
    brief = build_decision_brief(
        _goal(),
        world_document={"surface": "chat_list", "objects": []},
        features=_features(),
    )
    decided = consult_decision(brief, chooser=_FakeChooser({"capability": "nonsense"}))
    assert decided.ok
    assert decided.realization == "heuristic_after_llm_miss"
    assert decided.capability == "compose_search_query"


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


def test_apply_overrides_perceptor_action_on_picker():
    document = {
        "surface": "forward_picker",
        "focused_field_role": "destination_filter",
        "objects": [{"text": "Tanmay"}, {"text": "Tanmay (you)"}],
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
    assert features.extras["decision_consultation"]["perceptor_family"] == "type_query"


def test_apply_keeps_perceptor_grounding_for_same_pointer_family():
    document = {"surface": "conversation", "open_conversation": "Pallavi"}
    proposal = _proposal("conversation", "reveal_actions")
    proposal.next_action["target_id"] = 7
    trace = apply_decision_consultation(
        proposal,
        _goal(),
        features=_features(conversation_open=True, last_locate_query="zarooratwala"),
        execution_state=_State(document),
        chooser=_FakeChooser({"capability": "reveal_actions", "target": "zarooratwala"}),
    )
    assert trace["applied"] is True
    assert proposal.next_action["target_point"] == [200, 254]
    assert proposal.next_action["target_id"] == 7


def test_apply_leaves_action_alone_when_decision_says_observe():
    document = {"surface": "forward_picker", "focused_field_role": "destination_filter"}
    proposal = _proposal("forward_picker", "type_query")
    trace = apply_decision_consultation(
        proposal,
        _goal(),
        features=_features(),
        execution_state=_State(document),
        chooser=_FakeChooser({"capability": "observe"}),
    )
    assert trace["applied"] is False
    assert proposal.next_action["family"] == "type_query"
