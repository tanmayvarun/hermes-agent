"""Scene-understanding schemas — hierarchical world graph contracts.

These types are the Stage 3–9 *product* of perception (see
``plugin/experiments/SCENE_UNDERSTANDING_LLD.md``). This package defines
serialization only; no layout reconstruction or controller wiring yet.
"""

from __future__ import annotations

from plugin.worldmodel.scene.types import (
    ActionRisk,
    ActiveCognitiveSubgraph,
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
from plugin.worldmodel.scene.reconstruct import (
    reconstruct_world_graph,
    region_id_for_entity,
    region_ids_for_entity,
    region_kind_for_entity,
    region_kinds_for_entity,
)
from plugin.worldmodel.scene.affordances import (
    attention_score_delta,
    enrich_world_graph,
    preferred_regions_for_goal,
)
from plugin.worldmodel.scene.focus import attach_active_cognitive_subgraph, build_active_cognitive_subgraph

__all__ = [
    "ActionRisk",
    "ActiveCognitiveSubgraph",
    "AffordanceDistribution",
    "AffordanceHypothesis",
    "AttentionSubgraph",
    "ContextGraph",
    "CounterfactualRollout",
    "EdgeKind",
    "RegionKind",
    "RegionMembership",
    "SceneEdge",
    "SceneNodeRef",
    "SceneUnderstandingReport",
    "SemanticRegion",
    "SideEffectClass",
    "WorldGraph",
    "attach_active_cognitive_subgraph",
    "build_active_cognitive_subgraph",
    "reconstruct_world_graph",
    "region_id_for_entity",
    "region_ids_for_entity",
    "region_kind_for_entity",
    "region_kinds_for_entity",
    "attention_score_delta",
    "enrich_world_graph",
    "preferred_regions_for_goal",
]
