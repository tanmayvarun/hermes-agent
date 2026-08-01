"""Capability graph + grounding contract tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import plugin.agent.decision as decision_mod
from plugin.agent.decision import DecisionEngine
from plugin.agent.features import StateFeatures
from plugin.agent.apps.whatsapp import WhatsAppOverlay
from plugin.agent.goal import Goal
from plugin.agent.policy.candidates import _latent_probe_candidates
from plugin.agent.transition.evaluator import TransitionEvaluator
from plugin.agent.transition.types import ProgressAssessment, TransitionOutcome
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.transition.evaluator import assess_progress
from plugin.worldmodel.capability import (
    CapabilityGraph,
    build_capability_graph,
    grounded_action_for_capability,
    project_capability_graph,
)
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.scene.affordances import build_affordance_distribution
from plugin.worldmodel.scene.reconstruct import reconstruct_world_graph
from plugin.worldmodel.scene.types import RegionKind, SemanticRegion, WorldGraph


def _ent(
    eid: int,
    *,
    label: str,
    bounds: tuple[float, float, float, float],
    entity_type: str = "button",
    role: str = "AXButton",
    **attrs,
) -> Entity:
    return Entity(
        id=eid,
        entity_type=entity_type,
        semantic_role=label,
        label=label,
        role=role,
        actions=["click"] if entity_type == "button" else (["type"] if entity_type == "textfield" else []),
        bounds=bounds,
        visible=True,
        attributes=dict(attrs),
    )


def test_capability_graph_extracts_voice_call_capabilities():
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    entities = [
        _ent(1, label="Messages in chat with now group", bounds=(400, 20, 280, 40), entity_type="static"),
        _ent(2, label="Voice", bounds=(860, 100, 120, 36)),
        _ent(3, label="Video", bounds=(860, 140, 120, 36)),
        _ent(4, label="Select people", bounds=(860, 180, 160, 36)),
    ]
    graph = reconstruct_world_graph(entities, app="WhatsApp")
    cap_graph = build_capability_graph(graph, entities, goal=goal)

    selected = cap_graph.select_for_goal(goal)
    assert selected is not None
    assert selected.type == "InitiateVoiceCall"
    assert selected.capability_id
    assert any(node.type == "RevealCommunicationOptions" for node in cap_graph.nodes.values()) or any(
        node.type == "InitiateVoiceCall" for node in cap_graph.nodes.values()
    )

    grounded = grounded_action_for_capability(selected, entities=entities, graph=graph)
    assert grounded.entity_id in {2, 4, 3, 1}
    assert grounded.capability_type == "InitiateVoiceCall"


def test_header_title_does_not_broadcast_call_capability():
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    entities = [
        _ent(1, label="Messages in chat with now group", bounds=(400, 20, 280, 40), entity_type="static"),
        _ent(2, label="Search", bounds=(20, 40, 220, 36), entity_type="textfield", role="AXTextField"),
    ]
    graph = reconstruct_world_graph(entities, app="WhatsApp")
    cap_graph = build_capability_graph(graph, entities, goal=goal)

    entity1_caps = [cap for cap in cap_graph.nodes.values() if 1 in cap.provider_entities]
    assert all(cap.type not in {"InitiateVoiceCall", "InitiateVideoCall", "SelectParticipants"} for cap in entity1_caps)


def test_menu_chrome_does_not_generate_content_capabilities():
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zarooratwala")
    entities = [
        _ent(1, label="WhatsApp", bounds=(0, 0, 120, 28), entity_type="menu", role="AXMenuBar"),
        _ent(2, label="File", bounds=(8, 0, 44, 24), entity_type="menu", role="AXMenuItem"),
        _ent(3, label="Edit", bounds=(54, 0, 44, 24), entity_type="menu", role="AXMenuItem"),
        _ent(4, label="Search", bounds=(20, 40, 220, 36), entity_type="textfield", role="AXTextField"),
    ]
    graph = reconstruct_world_graph(entities, app="WhatsApp")
    cap_graph = build_capability_graph(graph, entities, goal=goal)

    menu_caps = [
        cap.type
        for cap in cap_graph.nodes.values()
        if any(pid in {1, 2, 3} for pid in cap.provider_entities)
    ]
    assert menu_caps == []


def test_long_video_call_cta_is_not_open_conversation():
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    entities = [
        _ent(1, label="Start video call with Pallavi", bounds=(860, 100, 260, 44), entity_type="button"),
        _ent(2, label="Messages in chat with now group", bounds=(400, 20, 280, 40), entity_type="static"),
    ]
    graph = reconstruct_world_graph(entities, app="WhatsApp")
    cap_graph = build_capability_graph(graph, entities, goal=goal)

    entity1_caps = [cap for cap in cap_graph.nodes.values() if 1 in cap.provider_entities]
    assert any(cap.type == "InitiateVideoCall" for cap in entity1_caps)
    assert all(cap.type != "OpenConversation" for cap in entity1_caps)


def test_search_grounding_rejects_settings_chrome_and_prefers_search_field():
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zaroortwala")
    entities = [
        _ent(1, label="Search", bounds=(20, 40, 220, 36), entity_type="textfield", role="AXTextField"),
        _ent(2, label="Settings", bounds=(860, 20, 120, 36), entity_type="button", role="AXButton"),
    ]
    graph = WorldGraph(
        regions=[
            SemanticRegion(id="sidebar", kind=RegionKind.SIDEBAR, entity_ids=[1, 2], confidence=0.9),
        ],
        app="WhatsApp",
    )
    cap = CapabilityGraph.from_dict(
        {
            "nodes": {
                "SearchConversation:2:sidebar": {
                    "capability_id": "SearchConversation:2:sidebar",
                    "type": "SearchConversation",
                    "confidence": 0.74,
                    "provider_entities": [2],
                    "provider_regions": ["sidebar"],
                    "predicted_transition": "surface search results",
                    "risk": 0.1,
                    "reversibility": True,
                    "evidence": {"entity_label": "Settings", "region_kind": "sidebar"},
                    "visible": True,
                    "parent_capability_id": "",
                }
            },
            "edges": [],
            "frontier": [],
            "goal_kind": goal.kind,
            "goal_capability_ids": ["SearchConversation:2:sidebar"],
            "interaction_graph": graph.context_graph.to_dict(),
        }
    )

    grounded = grounded_action_for_capability(cap.nodes["SearchConversation:2:sidebar"], entities=entities, graph=graph)

    assert grounded.entity_id == 1
    assert grounded.reason in {"provider_region", "provider_entity"}
    assert grounded.capability_type == "SearchConversation"


def test_projected_capability_graph_keeps_active_scope_and_drops_noise():
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zaroortwala")
    graph = CapabilityGraph.from_dict(
        {
            "nodes": {
                "SearchConversation:1:sidebar": {
                    "capability_id": "SearchConversation:1:sidebar",
                    "type": "SearchConversation",
                    "confidence": 0.8,
                    "provider_entities": [1],
                    "provider_regions": ["sidebar"],
                    "predicted_transition": "surface search results",
                    "risk": 0.1,
                    "reversibility": True,
                    "evidence": {"entity_label": "Search", "region_kind": "sidebar"},
                    "visible": True,
                    "parent_capability_id": "",
                },
                "RevealHiddenActions:2:header": {
                    "capability_id": "RevealHiddenActions:2:header",
                    "type": "RevealHiddenActions",
                    "confidence": 0.56,
                    "provider_entities": [2],
                    "provider_regions": ["header"],
                    "predicted_transition": "reveal hidden actions",
                    "risk": 0.12,
                    "reversibility": True,
                    "evidence": {"entity_label": "Noise Row", "region_kind": "header"},
                    "visible": True,
                    "parent_capability_id": "",
                },
            },
            "edges": [],
            "frontier": [],
            "goal_kind": goal.kind,
            "goal_capability_ids": ["SearchConversation:1:sidebar"],
            "interaction_graph": {},
        }
    )

    projected = project_capability_graph(
        graph,
        active_entity_ids=[1],
        focus_region_ids=["sidebar"],
        goal=goal,
    )

    assert "SearchConversation:1:sidebar" in projected.nodes
    assert "RevealHiddenActions:2:header" not in projected.nodes
    assert projected.goal_capability_ids == ["SearchConversation:1:sidebar"]


def test_latent_probe_candidates_stay_within_active_scope():
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zarooratwala")
    entities = [
        _ent(1, label="Zarooratwala", bounds=(760, 450, 160, 40), entity_type="static"),
        _ent(2, label="Share", bounds=(1420, 430, 120, 36), entity_type="button"),
    ]
    graph = reconstruct_world_graph(entities, app="WhatsApp")
    cap_graph = CapabilityGraph.from_dict(
        {
            "nodes": {
                "RevealHiddenActions:1:main": {
                    "capability_id": "RevealHiddenActions:1:main",
                    "type": "RevealHiddenActions",
                    "confidence": 0.82,
                    "provider_entities": [1],
                    "provider_regions": ["main"],
                    "predicted_transition": "surface latent actions",
                    "risk": 0.1,
                    "reversibility": True,
                    "evidence": {"entity_label": "Zarooratwala", "region_kind": "main"},
                    "visible": True,
                    "parent_capability_id": "",
                },
                "RevealHiddenActions:2:sidebar": {
                    "capability_id": "RevealHiddenActions:2:sidebar",
                    "type": "RevealHiddenActions",
                    "confidence": 0.9,
                    "provider_entities": [2],
                    "provider_regions": ["sidebar"],
                    "predicted_transition": "surface latent actions",
                    "risk": 0.1,
                    "reversibility": True,
                    "evidence": {"entity_label": "Share", "region_kind": "sidebar"},
                    "visible": True,
                    "parent_capability_id": "",
                },
            },
            "edges": [],
            "frontier": [],
            "goal_kind": goal.kind,
            "goal_capability_ids": [],
            "interaction_graph": graph.context_graph.to_dict(),
        }
    )

    features = StateFeatures(
        app="WhatsApp",
        screen_bucket="conversation",
        conversation_open=True,
        call_available=False,
        query_matches_goal=True,
        has_named_entity=True,
        extras={
            "active_surface": "conversation",
            "branch_active": True,
            "capability_graph": cap_graph.to_dict(),
            "active_cognitive_subgraph": {
                "active_entity_ids": [1],
                "focus_region_ids": ["main"],
                "excluded_region_ids": [],
            },
        },
    )

    probes = _latent_probe_candidates(goal, graph, features)
    assert probes
    assert all(p.target_entity_id == 1 for p in probes)
    assert all(p.semantic_target.lower() == "zarooratwala" for p in probes)


def test_decision_engine_returns_grounded_capability_id():
    wm_entities = [
        _ent(1, label="Messages in chat with now group", bounds=(400, 20, 280, 40), entity_type="static"),
        _ent(2, label="Voice", bounds=(860, 100, 120, 36)),
        _ent(3, label="Search", bounds=(20, 40, 220, 36), entity_type="textfield", role="AXTextField"),
    ]
    wm_graph = reconstruct_world_graph(wm_entities, app="WhatsApp")

    from plugin.worldmodel.model import WorldModel

    wm = WorldModel()
    wm.active_app = "WhatsApp"
    wm.entities = {e.id: e for e in wm_entities}
    wm.last_scene_graph = wm_graph.to_dict()
    wm.last_capability_graph = build_capability_graph(wm_graph, wm_entities, goal=Goal(kind="whatsapp_voice_call", contact="now group")).to_dict()

    ex = ExecutionState()
    goal = Goal(kind="whatsapp_voice_call", contact="now group")

    def fake_synthesize_perception(*args, **kwargs):
        return SimpleNamespace(
            screen_type="conversation",
            active_surface="conversation",
            likely_next_family="start_call",
            likely_next_target="Voice",
            confidence=0.82,
        )

    def fake_select_action_with_llm(*args, **kwargs):
        scored_candidates = args[3]
        chosen = next(
            (cand for cand in scored_candidates if cand.action_family == "start_call"),
            next((cand for cand in scored_candidates if cand.action_family != "observe"), scored_candidates[0]),
        )
        return chosen, {"confidence": 0.84, "task": kwargs.get("task")}

    decision_mod_synthesize = decision_mod.synthesize_perception
    decision_mod_select = decision_mod.select_action_with_llm
    decision_mod.synthesize_perception = fake_synthesize_perception
    decision_mod.select_action_with_llm = fake_select_action_with_llm
    try:
        decision = DecisionEngine(selector_enabled=True).decide(goal, wm, ex)
    finally:
        decision_mod.synthesize_perception = decision_mod_synthesize
        decision_mod.select_action_with_llm = decision_mod_select

    assert decision is not None
    assert decision.capability_id
    assert decision.capability_type in {"InitiateVoiceCall", "SearchConversation", "OpenConversation"}
    if decision.action_family == "start_call":
        assert decision.target_entity_id is not None


def test_decision_engine_allows_single_content_candidate_to_hit_selector():
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="india coffee house")
    wm_entities = [
        _ent(1, label="Messages in chat with Kulvinder Ji", bounds=(400, 20, 280, 40), entity_type="static"),
        _ent(2, label="Search", bounds=(20, 40, 220, 36), entity_type="textfield", role="AXTextField"),
    ]
    wm_graph = reconstruct_world_graph(wm_entities, app="WhatsApp")

    from plugin.worldmodel.model import WorldModel

    wm = WorldModel()
    wm.active_app = "WhatsApp"
    wm.entities = {e.id: e for e in wm_entities}
    wm.last_scene_graph = wm_graph.to_dict()
    wm.last_capability_graph = build_capability_graph(wm_graph, wm_entities, goal=goal).to_dict()

    captured = {}

    def fake_select_action_with_llm(*args, **kwargs):
        captured.update(kwargs)
        scored_candidates = args[3]
        chosen = next((cand for cand in scored_candidates if cand.action_family != "observe"), scored_candidates[0])
        return chosen, {"task": kwargs.get("task"), "confidence": 0.81}

    decision_mod_select = decision_mod.select_action_with_llm
    decision_mod.select_action_with_llm = fake_select_action_with_llm
    try:
        decision = DecisionEngine(selector_enabled=True).decide(goal, wm, ExecutionState())
    finally:
        decision_mod.select_action_with_llm = decision_mod_select

    assert captured["task"] == "decision"
    assert decision is not None


def test_transition_progress_reports_capability_delta():
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    before = CapabilityGraph.from_dict(
        {
            "nodes": {
                "RevealCommunicationOptions:1:header": {
                    "capability_id": "RevealCommunicationOptions:1:header",
                    "type": "RevealCommunicationOptions",
                    "confidence": 0.6,
                    "provider_entities": [1],
                    "provider_regions": ["header"],
                    "predicted_transition": "reveal secondary call controls",
                    "risk": 0.1,
                    "reversibility": True,
                    "evidence": {},
                    "visible": True,
                    "parent_capability_id": "",
                }
            },
            "edges": [],
            "frontier": [],
            "goal_kind": goal.kind,
            "goal_capability_ids": ["RevealCommunicationOptions:1:header"],
            "interaction_graph": {},
        }
    )
    after = CapabilityGraph.from_dict(
        {
            "nodes": {
                "RevealCommunicationOptions:1:header": {
                    "capability_id": "RevealCommunicationOptions:1:header",
                    "type": "RevealCommunicationOptions",
                    "confidence": 0.6,
                    "provider_entities": [1],
                    "provider_regions": ["header"],
                    "predicted_transition": "reveal secondary call controls",
                    "risk": 0.1,
                    "reversibility": True,
                    "evidence": {},
                    "visible": True,
                    "parent_capability_id": "",
                },
                "InitiateVoiceCall:2:header": {
                    "capability_id": "InitiateVoiceCall:2:header",
                    "type": "InitiateVoiceCall",
                    "confidence": 0.9,
                    "provider_entities": [2],
                    "provider_regions": ["header"],
                    "predicted_transition": "move into ringing/call state",
                    "risk": 0.2,
                    "reversibility": False,
                    "evidence": {},
                    "visible": True,
                    "parent_capability_id": "RevealCommunicationOptions:1:header",
                },
            },
            "edges": [],
            "frontier": [],
            "goal_kind": goal.kind,
            "goal_capability_ids": ["InitiateVoiceCall:2:header"],
            "interaction_graph": {},
        }
    )
    assessment = assess_progress(
        goal=goal,
        before_view={"screen": "CONVERSATION"},
        after_view={"screen": "LIST"},
        before_features={"capability_graph": before.to_dict()},
        after_features={"capability_graph": after.to_dict()},
    )

    assert "InitiateVoiceCall" in assessment.new_capabilities
    assert assessment.predicted_transition
    assert assessment.observed_transition
    assert assessment.confidence_delta > 0


def test_message_like_timeline_entity_exposes_latent_probe_affordances():
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zarooratwala")
    entities = [
        _ent(1, label="Kulvinder Ji", bounds=(540, 18, 180, 36), entity_type="static"),
        _ent(2, label="Search", bounds=(20, 48, 220, 36), entity_type="textfield", role="AXTextField"),
        _ent(3, label="Message bubble: Zarooratwala", bounds=(620, 300, 360, 64), entity_type="button"),
        _ent(4, label="Message bubble: another row", bounds=(620, 390, 360, 64), entity_type="button"),
        _ent(5, label="Composer", bounds=(540, 920, 360, 40), entity_type="textfield", role="AXTextField"),
    ]
    graph = WorldGraph(
        regions=[
            SemanticRegion(id="sidebar", kind=RegionKind.SIDEBAR, entity_ids=[2], confidence=0.9),
            SemanticRegion(id="timeline", kind=RegionKind.TIMELINE, entity_ids=[3, 4], confidence=0.95),
            SemanticRegion(id="composer", kind=RegionKind.COMPOSER, entity_ids=[5], confidence=0.88),
        ],
        app="WhatsApp",
    )
    dist = build_affordance_distribution(graph, entities)

    probes = {hyp.id for hyp in dist.by_entity.get(3, [])}
    assert "probe_hover" in probes
    assert "probe_context_menu" in probes


def test_probe_hover_success_is_promising_unresolved():
    evaluator = TransitionEvaluator()
    assessment = ProgressAssessment(
        execution_succeeded=True,
        meaningful_change=True,
        state_understood=True,
        goal_progress="promising",
        newly_relevant_affordances=["probe_hover", "select_item"],
        context_preserved=True,
        branch_reversible=True,
        contradiction_evidence=[],
        irreversible_risk_delta=0.1,
    )

    outcome = evaluator._classify(  # noqa: SLF001 - regression test for branch classification
        assessment,
        transition=None,
        changed=True,
        change_score=0.28,
        action_family="probe_hover",
    )

    assert outcome == TransitionOutcome.PROMISING_UNRESOLVED


def test_composer_voice_message_is_not_grounded_as_call_capability():
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    entities = [
        _ent(10, label="Voice message", bounds=(960, 920, 48, 40), entity_type="button"),
        _ent(11, label="Voice", bounds=(860, 100, 120, 36)),
    ]
    graph = reconstruct_world_graph(entities, app="WhatsApp")
    cap_graph = build_capability_graph(
        graph,
        entities,
        goal=goal,
        capability_hints=WhatsAppOverlay().capability_hints(goal),
    )

    composer_caps = [cap for cap in cap_graph.nodes.values() if 10 in cap.provider_entities]
    overlay_caps = [cap for cap in cap_graph.nodes.values() if 11 in cap.provider_entities]

    assert all(cap.type != "InitiateVoiceCall" for cap in composer_caps)
    assert any(cap.type == "InitiateVoiceCall" for cap in overlay_caps)


def test_decision_engine_uses_llm_selector_to_choose_the_right_call_cta():
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    entities = [
        _ent(10, label="Voice message", bounds=(960, 920, 48, 40), entity_type="button"),
        _ent(11, label="Voice", bounds=(860, 100, 120, 36)),
        _ent(12, label="Video", bounds=(860, 140, 120, 36)),
        _ent(13, label="Select people", bounds=(860, 180, 160, 36)),
    ]
    wm_graph = reconstruct_world_graph(entities, app="WhatsApp")

    from plugin.worldmodel.model import WorldModel

    wm = WorldModel()
    wm.active_app = "WhatsApp"
    wm.entities = {e.id: e for e in entities}
    wm.last_scene_graph = wm_graph.to_dict()
    wm.last_capability_graph = build_capability_graph(
        wm_graph,
        entities,
        goal=goal,
        capability_hints=WhatsAppOverlay().capability_hints(goal),
    ).to_dict()

    calls = {}

    def fake_selector(**kwargs):
        calls["kwargs"] = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"choice": "Voice", "confidence": 0.99, "reason": "header voice call"}'
                    )
                )
            ]
        )

    decision = DecisionEngine(selector_caller=fake_selector).decide(goal, wm, ExecutionState())

    assert calls
    assert decision is not None
    assert decision.semantic_target == "Voice"
    assert decision.capability_type == "InitiateVoiceCall"
    assert decision.target_entity_id == 11
    assert decision.grounding_reason


def test_decision_engine_blocks_low_confidence_irreversible_actions():
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    entities = [
        _ent(10, label="Voice", bounds=(860, 100, 120, 36)),
        _ent(11, label="Video", bounds=(860, 140, 120, 36)),
    ]
    wm_graph = reconstruct_world_graph(entities, app="WhatsApp")

    from plugin.worldmodel.model import WorldModel

    wm = WorldModel()
    wm.active_app = "WhatsApp"
    wm.entities = {e.id: e for e in entities}
    wm.last_scene_graph = wm_graph.to_dict()
    wm.last_capability_graph = build_capability_graph(
        wm_graph,
        entities,
        goal=goal,
        capability_hints=WhatsAppOverlay().capability_hints(goal),
    ).to_dict()

    def fake_selector(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"choice": "Voice", "confidence": 0.3, "reason": "not sure"}'
                    )
                )
            ]
        )

    decision = DecisionEngine(selector_enabled=True, selector_caller=fake_selector).decide(goal, wm, ExecutionState())

    assert decision is not None
    assert decision.action_family == "observe"
    assert decision.grounding_reason == "blocked_below_irreversible_threshold"
    assert DecisionEngine(selector_enabled=True, selector_caller=fake_selector).irreversible_action_confidence_threshold() == 0.7


def test_decision_engine_allows_selector_to_veto_single_risky_forward_action():
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zarooratwala")
    entities = [
        _ent(1, label="Messages in chat with Kulvinder Ji", bounds=(400, 20, 280, 40), entity_type="static"),
        _ent(2, label="Your message, Link, https://example.com", bounds=(860, 100, 220, 48), entity_type="link"),
        _ent(3, label="Forward", bounds=(900, 140, 100, 36)),
    ]
    wm_graph = reconstruct_world_graph(entities, app="WhatsApp")

    from plugin.worldmodel.model import WorldModel

    wm = WorldModel()
    wm.active_app = "WhatsApp"
    wm.entities = {e.id: e for e in entities}
    wm.last_scene_graph = wm_graph.to_dict()
    wm.last_capability_graph = build_capability_graph(
        wm_graph,
        entities,
        goal=goal,
        capability_hints=WhatsAppOverlay().capability_hints(goal),
    ).to_dict()

    def fake_selector(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"choice": "observe", "confidence": 0.96, "reason": "need more evidence"}'
                    )
                )
            ]
        )

    decision = DecisionEngine(selector_enabled=True, selector_caller=fake_selector).decide(goal, wm, ExecutionState())

    assert decision is not None
    assert decision.action_family == "observe"


def test_decision_engine_strict_selector_mode_raises_on_llm_exhaustion(monkeypatch):
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    entities = [
        _ent(10, label="Voice", bounds=(860, 100, 120, 36)),
        _ent(11, label="Video", bounds=(860, 140, 120, 36)),
    ]
    wm_graph = reconstruct_world_graph(entities, app="WhatsApp")

    from plugin.worldmodel.model import WorldModel
    from agent.auxiliary_client import LLMProviderExhaustedError

    wm = WorldModel()
    wm.active_app = "WhatsApp"
    wm.entities = {e.id: e for e in entities}
    wm.last_scene_graph = wm_graph.to_dict()
    wm.last_capability_graph = build_capability_graph(
        wm_graph,
        entities,
        goal=goal,
        capability_hints=WhatsAppOverlay().capability_hints(goal),
    ).to_dict()

    def fake_selector(**kwargs):
        raise LLMProviderExhaustedError("selector timed out")

    monkeypatch.setenv("HERMES_SELECTOR_STRICT", "1")
    with pytest.raises(LLMProviderExhaustedError):
        DecisionEngine(selector_enabled=True, selector_caller=fake_selector).decide(goal, wm, ExecutionState())


def test_decision_engine_overrules_selector_observe_when_open_search_is_better():
    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")
    entities = [
        _ent(1, label="Search", bounds=(20, 40, 220, 36), entity_type="textfield", role="AXTextField"),
        _ent(2, label="Chats", bounds=(40, 200, 220, 40), entity_type="static"),
    ]
    wm_graph = reconstruct_world_graph(entities, app="WhatsApp")

    from plugin.worldmodel.model import WorldModel

    wm = WorldModel()
    wm.active_app = "WhatsApp"
    wm.entities = {e.id: e for e in entities}
    wm.last_scene_graph = wm_graph.to_dict()
    wm.last_capability_graph = build_capability_graph(
        wm_graph,
        entities,
        goal=goal,
        capability_hints=WhatsAppOverlay().capability_hints(goal),
    ).to_dict()

    def fake_selector(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"choice": "observe", "confidence": 0.95, "reason": "stall"}'
                    )
                )
            ]
        )

    decision = DecisionEngine(selector_enabled=True, selector_caller=fake_selector).decide(goal, wm, ExecutionState())

    assert decision is not None
    assert decision.action_family != "observe"
    assert decision.action_family in {"open_search", "type_query"}


def test_decision_engine_routes_irreversible_actions_through_high_risk_selector():
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    entities = [
        _ent(10, label="Voice message", bounds=(960, 920, 48, 40), entity_type="button"),
        _ent(11, label="Voice", bounds=(860, 100, 120, 36)),
        _ent(12, label="Video", bounds=(860, 140, 120, 36)),
        _ent(13, label="Select people", bounds=(860, 180, 160, 36)),
    ]
    wm_graph = reconstruct_world_graph(entities, app="WhatsApp")

    from plugin.worldmodel.model import WorldModel

    wm = WorldModel()
    wm.active_app = "WhatsApp"
    wm.entities = {e.id: e for e in entities}
    wm.last_scene_graph = wm_graph.to_dict()
    wm.last_capability_graph = build_capability_graph(
        wm_graph,
        entities,
        goal=goal,
        capability_hints=WhatsAppOverlay().capability_hints(goal),
    ).to_dict()

    captured = {}

    def fake_select_action_with_llm(*args, **kwargs):
        captured.update(kwargs)
        scored_candidates = args[3]
        chosen = next((cand for cand in scored_candidates if cand.action_family == "start_call"), scored_candidates[0])
        chosen.target_entity_id = chosen.target_entity_id or 11
        return chosen, {"task": kwargs.get("task"), "confidence": 0.99}

    decision_mod_select = decision_mod.select_action_with_llm
    decision_mod.select_action_with_llm = fake_select_action_with_llm
    try:
        decision = DecisionEngine().decide(goal, wm, ExecutionState())
    finally:
        decision_mod.select_action_with_llm = decision_mod_select

    assert captured["task"] == "decision_high_risk"
    assert captured["call_kwargs"]["reasoning_config"]["effort"] == "high"
    assert decision is not None
    assert decision.action_family == "start_call"
    assert decision.capability_type == "InitiateVoiceCall"
