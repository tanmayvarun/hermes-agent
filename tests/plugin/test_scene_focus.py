from __future__ import annotations

from plugin.agent.goal import Goal
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.scene.focus import attach_active_cognitive_subgraph, build_active_cognitive_subgraph
from plugin.worldmodel.scene.types import RegionKind, SemanticRegion, WorldGraph


def _goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
    )


def _graph() -> WorldGraph:
    return WorldGraph(
        regions=[
            SemanticRegion(id="sidebar", kind=RegionKind.SIDEBAR, entity_ids=[1], confidence=0.92),
            SemanticRegion(id="timeline", kind=RegionKind.TIMELINE, entity_ids=[2], confidence=0.98),
            SemanticRegion(id="composer", kind=RegionKind.COMPOSER, entity_ids=[3], confidence=0.88),
        ],
        app="WhatsApp",
    )


def _entities() -> list[Entity]:
    return [
        Entity(
            id=1,
            entity_type="static",
            semantic_role="Kulvinder Ji",
            label="Kulvinder Ji",
            role="AXStaticText",
            visible=True,
        ),
        Entity(
            id=2,
            entity_type="static",
            semantic_role="ZarooratWala – Fresh Groceries Delivered",
            label="ZarooratWala – Fresh Groceries Delivered",
            role="AXStaticText",
            visible=True,
        ),
        Entity(
            id=3,
            entity_type="textfield",
            semantic_role="Message",
            label="Message",
            role="AXTextField",
            visible=True,
        ),
    ]


def test_build_active_cognitive_subgraph_prioritizes_conversation_scope():
    graph = _graph()
    ents = _entities()

    active = build_active_cognitive_subgraph(
        graph,
        ents,
        goal=_goal(),
        view={"screen": "CONVERSATION", "open_conversation": "Kulvinder Ji"},
        world_id="screen-1",
    )

    assert active.phase == "conversation"
    assert "timeline" in active.focus_region_ids
    assert "sidebar" not in active.focus_region_ids
    assert 2 in active.active_entity_ids
    assert active.confidence > 0.0


def test_attach_active_cognitive_subgraph_round_trips_through_world_graph():
    graph = _graph()
    ents = _entities()

    attached = attach_active_cognitive_subgraph(
        graph,
        ents,
        goal=_goal(),
        view={"screen": "CONVERSATION", "open_conversation": "Kulvinder Ji"},
        world_id="screen-1",
    )
    raw = attached.to_dict()
    restored = WorldGraph.from_dict(raw)

    assert restored.active_subgraph is not None
    assert restored.active_subgraph.phase == "conversation"
    assert restored.attention is not None
    assert restored.attention.region_ids


def test_attach_active_cognitive_subgraph_preserves_split_surface_state():
    graph = _graph()
    ents = _entities()

    attached = attach_active_cognitive_subgraph(
        graph,
        ents,
        goal=_goal(),
        view={"screen": "SEARCH_RESULTS", "search_query": "Kulvinder", "visible_contacts": ["Kulvinder Ji"]},
        world_id="screen-2",
    )
    raw = attached.to_dict()
    restored = WorldGraph.from_dict(raw)

    assert restored.surface_state is not None
    assert restored.surface_state.base_surface in {"whatsapp_main_window", "whatsapp"}
    assert restored.surface_state.sidebar_surface in {"search_results", "search"}
    assert restored.surface_state.main_surface in {"conversation", "search_results"}
