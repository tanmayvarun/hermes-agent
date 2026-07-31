"""Scene graph schema contracts — round-trip + representability of Voice failure."""

from __future__ import annotations

from plugin.worldmodel.scene import (
    ActionRisk,
    AffordanceDistribution,
    AffordanceHypothesis,
    AttentionSubgraph,
    ContextGraph,
    CounterfactualRollout,
    EdgeKind,
    RegionKind,
    RegionMembership,
    SceneEdge,
    SceneNodeRef,
    SceneUnderstandingReport,
    SemanticRegion,
    SideEffectClass,
    WorldGraph,
)


def test_semantic_region_round_trip():
    region = SemanticRegion(
        id="composer",
        kind=RegionKind.COMPOSER,
        bounds=(100.0, 900.0, 800.0, 120.0),
        confidence=0.91,
        entity_ids=[10, 11, 12],
        parent_region_id="conversation",
        label="Composer",
    )
    restored = SemanticRegion.from_dict(region.to_dict())
    assert restored.id == "composer"
    assert restored.kind is RegionKind.COMPOSER
    assert restored.bounds == (100.0, 900.0, 800.0, 120.0)
    assert restored.entity_ids == [10, 11, 12]
    assert restored.parent_region_id == "conversation"


def test_affordance_distribution_round_trip():
    dist = AffordanceDistribution(
        by_entity={
            42: [
                AffordanceHypothesis(
                    id="record_voice_message",
                    p=0.97,
                    region_id="composer",
                    entity_id=42,
                    evidence={"label": "Voice message"},
                ),
                AffordanceHypothesis(
                    id="start_voice_call",
                    p=0.01,
                    region_id="composer",
                    entity_id=42,
                ),
            ]
        }
    )
    restored = AffordanceDistribution.from_dict(dist.to_dict())
    hyps = restored.hypotheses_for(42)
    assert len(hyps) == 2
    assert hyps[0].id == "record_voice_message"
    assert hyps[0].p == 0.97
    assert hyps[1].id == "start_voice_call"


def test_world_graph_round_trip():
    graph = WorldGraph(
        regions=[
            SemanticRegion(id="header", kind=RegionKind.HEADER, confidence=0.8, entity_ids=[1]),
            SemanticRegion(id="composer", kind=RegionKind.COMPOSER, confidence=0.85, entity_ids=[42]),
            SemanticRegion(
                id="call_overlay",
                kind=RegionKind.FLOATING_MENU,
                confidence=0.9,
                entity_ids=[99],
                label="Call menu",
            ),
        ],
        context_graph=ContextGraph(
            nodes=[
                SceneNodeRef(kind="region", id="composer"),
                SceneNodeRef(kind="entity", id="42"),
                SceneNodeRef(kind="region", id="call_overlay"),
                SceneNodeRef(kind="entity", id="99"),
            ],
            edges=[
                SceneEdge(
                    kind=EdgeKind.CONTAINS,
                    source=SceneNodeRef(kind="region", id="composer"),
                    target=SceneNodeRef(kind="entity", id="42"),
                    confidence=0.95,
                ),
                SceneEdge(
                    kind=EdgeKind.PARENT_OF,
                    source=SceneNodeRef(kind="entity", id="42"),
                    target=SceneNodeRef(kind="entity", id="99"),
                    confidence=0.7,
                ),
                SceneEdge(
                    kind=EdgeKind.CONTAINS,
                    source=SceneNodeRef(kind="region", id="call_overlay"),
                    target=SceneNodeRef(kind="entity", id="99"),
                    confidence=0.95,
                ),
            ],
        ),
        memberships=[
            RegionMembership(
                entity_id=42,
                region_id="composer",
                relation="contained_by",
                confidence=0.95,
                evidence={"reason": "test"},
            )
        ],
        affordances=AffordanceDistribution(by_entity={}),
        risks=[
            ActionRisk(
                affordance_id="record_voice_message",
                side_effect_class=SideEffectClass.EXTERNAL,
                risk=0.85,
                expected_state_delta="recording_ui",
            ),
            ActionRisk(
                affordance_id="open_call_menu",
                side_effect_class=SideEffectClass.EXPLORE,
                risk=0.15,
                expected_state_delta="reveal_call_options",
            ),
        ],
        attention=AttentionSubgraph(
            region_ids=["header", "call_overlay"],
            entity_ids=[99],
            goal_kind="whatsapp_voice_call",
            residual_mass=0.05,
        ),
        report=SceneUnderstandingReport(
            layout_confidence=0.7,
            region_coverage=0.8,
            affordance_entropy=0.4,
            unassigned_entity_fraction=0.1,
            notes=["fixture"],
        ),
        source_patch_id="patch-1",
        app="WhatsApp",
    )
    restored = WorldGraph.from_dict(graph.to_dict())
    assert restored.app == "WhatsApp"
    assert restored.source_patch_id == "patch-1"
    assert len(restored.regions) == 3
    assert restored.regions[2].kind is RegionKind.FLOATING_MENU
    assert len(restored.context_graph.edges) == 3
    assert any(edge.kind is EdgeKind.PARENT_OF for edge in restored.context_graph.edges)
    assert len(restored.memberships) == 1
    assert restored.memberships[0].entity_id == 42
    assert restored.memberships[0].region_id == "composer"
    assert restored.attention is not None
    assert restored.attention.region_ids == ["header", "call_overlay"]
    assert restored.risks[0].side_effect_class is SideEffectClass.EXTERNAL
    assert restored.report.layout_confidence == 0.7


def test_counterfactual_stub_round_trip():
    roll = CounterfactualRollout(
        affordance_id="record_voice_message",
        predicted_delta="recording_ui",
        advances_goal=False,
        confidence=0.8,
    )
    restored = CounterfactualRollout.from_dict(roll.to_dict())
    assert restored.advances_goal is False
    assert restored.affordance_id == "record_voice_message"


def test_same_label_composer_vs_overlay_distinct_affordances():
    """Schema must express the Voice / Voice-message failure mode.

    Same lexical label family under different regions → different affordance ids.
    Reconstruction is future work; representability is required now.
    """
    # Entity 10: "Voice" / mic in composer
    # Entity 11: "Voice" / mic in call overlay (floating_menu)
    composer = SemanticRegion(
        id="composer",
        kind=RegionKind.COMPOSER,
        bounds=(100, 900, 800, 120),
        confidence=0.9,
        entity_ids=[10],
    )
    overlay = SemanticRegion(
        id="call_overlay",
        kind=RegionKind.FLOATING_MENU,
        bounds=(200, 80, 280, 160),
        confidence=0.92,
        entity_ids=[11],
        label="Call dropdown",
    )
    affordances = AffordanceDistribution(
        by_entity={
            10: [
                AffordanceHypothesis(
                    id="record_voice_message",
                    p=0.97,
                    region_id="composer",
                    entity_id=10,
                    evidence={"ax_label": "Voice message", "region_kind": "composer"},
                ),
                AffordanceHypothesis(
                    id="start_voice_call",
                    p=0.01,
                    region_id="composer",
                    entity_id=10,
                ),
            ],
            11: [
                AffordanceHypothesis(
                    id="start_voice_call",
                    p=0.94,
                    region_id="call_overlay",
                    entity_id=11,
                    evidence={"ax_label": "Voice", "region_kind": "floating_menu"},
                ),
                AffordanceHypothesis(
                    id="record_voice_message",
                    p=0.02,
                    region_id="call_overlay",
                    entity_id=11,
                ),
            ],
        }
    )
    graph = WorldGraph(
        regions=[composer, overlay],
        context_graph=ContextGraph(
            edges=[
                SceneEdge(
                    kind=EdgeKind.CONTAINS,
                    source=SceneNodeRef(kind="region", id="composer"),
                    target=SceneNodeRef(kind="entity", id="10"),
                ),
                SceneEdge(
                    kind=EdgeKind.CONTAINS,
                    source=SceneNodeRef(kind="region", id="call_overlay"),
                    target=SceneNodeRef(kind="entity", id="11"),
                ),
            ]
        ),
        affordances=affordances,
        attention=AttentionSubgraph(
            region_ids=["call_overlay"],
            entity_ids=[11],
            goal_kind="whatsapp_voice_call",
        ),
        app="WhatsApp",
    )

    restored = WorldGraph.from_dict(graph.to_dict())
    composer_hyps = restored.affordances.hypotheses_for(10)
    overlay_hyps = restored.affordances.hypotheses_for(11)

    assert composer_hyps[0].region_id == "composer"
    assert overlay_hyps[0].region_id == "call_overlay"
    assert composer_hyps[0].region_id != overlay_hyps[0].region_id

    # Dominant affordances diverge despite same label family
    assert composer_hyps[0].id == "record_voice_message"
    assert overlay_hyps[0].id == "start_voice_call"
    assert composer_hyps[0].id != overlay_hyps[0].id

    # Call-goal attention excludes composer entity
    assert restored.attention is not None
    assert 10 not in restored.attention.entity_ids
    assert 11 in restored.attention.entity_ids
