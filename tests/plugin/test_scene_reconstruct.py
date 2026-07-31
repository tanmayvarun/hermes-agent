"""Generic Stage 3–7 scene understanding — geometry regions + affordance/attention."""

from __future__ import annotations

from plugin.agent.goal import Goal
from plugin.agent.runtime.state import RuntimeState
from plugin.perception.observation import AxNode, Observation
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel
from plugin.worldmodel.scene.affordances import build_affordance_distribution
from plugin.worldmodel.scene import (
    RegionKind,
    RegionMembership,
    attention_score_delta,
    enrich_world_graph,
    preferred_regions_for_goal,
    reconstruct_world_graph,
    region_ids_for_entity,
    region_kind_for_entity,
    region_kinds_for_entity,
    SemanticRegion,
    WorldGraph,
)
from plugin.agent.perception_cycle import build_view_features


def _ent(
    eid: int,
    *,
    label: str,
    bounds: tuple,
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
        actions=["click"] if entity_type == "button" else ["type"] if entity_type == "textfield" else [],
        bounds=bounds,
        visible=True,
        attributes=dict(attrs),
    )


def _generic_conversation_layout():
    """Layout with no product-specific labels — OptionA/B/C cluster vs bottom field."""
    return [
        _ent(1, label="Item1", bounds=(20, 40, 80, 30), entity_type="static"),
        _ent(2, label="Item2", bounds=(20, 100, 200, 40)),
        _ent(3, label="Title", bounds=(400, 40, 160, 36), entity_type="static"),
        _ent(4, label="Action", bounds=(900, 40, 48, 36)),
        # Compact floating cluster (mid-upper)
        _ent(10, label="OptionA", bounds=(860, 90, 140, 32)),
        _ent(11, label="OptionB", bounds=(860, 130, 140, 32)),
        _ent(12, label="OptionC", bounds=(860, 170, 160, 32)),
        _ent(20, label="Body", bounds=(420, 400, 200, 40), entity_type="static"),
        # Bottom composer band — neutral labels
        _ent(
            30,
            label="Input",
            bounds=(400, 920, 500, 40),
            entity_type="textfield",
            role="AXTextField",
        ),
        _ent(31, label="Mic", bounds=(960, 920, 48, 40)),
        _ent(32, label="Extra", bounds=(350, 920, 40, 40)),
    ]


def test_geometry_regions_without_app_vocabulary():
    graph = reconstruct_world_graph(_generic_conversation_layout(), app="SomeApp")
    kinds = {r.kind for r in graph.regions}
    assert RegionKind.COMPOSER in kinds
    assert RegionKind.FLOATING_MENU in kinds
    assert region_kind_for_entity(graph, 31) is RegionKind.COMPOSER
    assert region_kind_for_entity(graph, 10) is RegionKind.FLOATING_MENU
    assert "geometry_ax_generic_v1" in graph.report.notes


def test_same_stem_labels_diverge_by_region_only():
    """Kill-gate: identical stem labels still separate by geometry alone."""
    entities = [
        _ent(1, label="Nav", bounds=(20, 40, 80, 30), entity_type="static"),
        _ent(2, label="Row", bounds=(20, 100, 200, 40)),
        _ent(3, label="Title", bounds=(400, 40, 160, 36), entity_type="static"),
        _ent(10, label="Voice", bounds=(860, 90, 140, 32)),
        _ent(11, label="Video", bounds=(860, 130, 140, 32)),
        _ent(12, label="More", bounds=(860, 170, 160, 32)),
        _ent(
            30,
            label="Field",
            bounds=(400, 920, 500, 40),
            entity_type="textfield",
            role="AXTextField",
        ),
        _ent(31, label="Voice message", bounds=(960, 920, 48, 40)),
    ]
    graph = reconstruct_world_graph(entities, app="")
    assert region_kind_for_entity(graph, 10) is RegionKind.FLOATING_MENU
    assert region_kind_for_entity(graph, 31) is RegionKind.COMPOSER


def test_call_goal_attention_excludes_composer_mic():
    entities = _generic_conversation_layout()
    # Rename mic-like control for collision test
    entities = [
        e
        if e.id != 31
        else _ent(31, label="Voice message", bounds=e.bounds, entity_type="button")
        for e in entities
    ]
    entities = [
        e if e.id != 10 else _ent(10, label="Voice", bounds=e.bounds) for e in entities
    ]
    graph = reconstruct_world_graph(entities, app="Any")
    goal = Goal(kind="generic_voice_call", contact="alpha", app="Any")
    graph = enrich_world_graph(graph, entities, goal=goal)

    assert graph.attention is not None
    assert 10 in graph.attention.entity_ids
    assert 31 not in graph.attention.entity_ids
    assert preferred_regions_for_goal(goal.kind)[0] is RegionKind.FLOATING_MENU

    # Affordance mass: composer mic has no initiate_session; floating menu does
    composer_hyps = {h.id: h.p for h in graph.affordances.hypotheses_for(31)}
    overlay_hyps = {h.id: h.p for h in graph.affordances.hypotheses_for(10)}
    assert "initiate_session" not in composer_hyps or composer_hyps["initiate_session"] < 0.1
    assert overlay_hyps.get("initiate_session", 0) >= 0.4
    assert max(composer_hyps.get(k, 0) for k in ("send_message", "attach_media", "compose_text")) > 0.3

    delta_voice = attention_score_delta(graph, semantic_target="Voice", entities=entities)
    delta_msg = attention_score_delta(graph, semantic_target="Voice message", entities=entities)
    assert delta_voice > 0
    assert delta_msg < 0


def test_message_goal_prefers_composer():
    regions = preferred_regions_for_goal("send_message")
    assert regions[0] is RegionKind.COMPOSER


def test_membership_helpers_preserve_multiple_region_hypotheses():
    graph = WorldGraph(
        regions=[
            SemanticRegion(id="sidebar", kind=RegionKind.SIDEBAR, confidence=0.5, entity_ids=[1]),
            SemanticRegion(id="composer", kind=RegionKind.COMPOSER, confidence=0.4, entity_ids=[1]),
        ],
        memberships=[
            RegionMembership(
                entity_id=1,
                region_id="sidebar",
                relation="contained_by",
                confidence=0.9,
                evidence={"reason": "test"},
            ),
            RegionMembership(
                entity_id=1,
                region_id="composer",
                relation="overlaps",
                confidence=0.7,
                evidence={"reason": "test"},
            ),
        ],
    )

    assert region_kind_for_entity(graph, 1) is RegionKind.COMPOSER
    assert region_ids_for_entity(graph, 1) == ["composer", "sidebar"]
    assert region_kinds_for_entity(graph, 1) == [RegionKind.COMPOSER, RegionKind.SIDEBAR]


def test_affordances_keep_multiple_region_hypotheses():
    entity = _ent(1, label="Input", bounds=(400, 920, 500, 40), entity_type="textfield", role="AXTextField")
    graph = WorldGraph(
        regions=[
            SemanticRegion(id="composer", kind=RegionKind.COMPOSER, bounds=(350, 860, 650, 140), confidence=0.8, entity_ids=[1]),
            SemanticRegion(id="sidebar", kind=RegionKind.SIDEBAR, bounds=(0, 0, 360, 1080), confidence=0.5, entity_ids=[1]),
        ],
        memberships=[
            RegionMembership(
                entity_id=1,
                region_id="composer",
                relation="contained_by",
                confidence=0.92,
                evidence={"reason": "test"},
            ),
            RegionMembership(
                entity_id=1,
                region_id="sidebar",
                relation="overlaps",
                confidence=0.61,
                evidence={"reason": "test"},
            ),
        ],
    )

    dist = build_affordance_distribution(graph, [entity])
    hyps = dist.hypotheses_for(1)
    ids = {(h.id, h.region_id) for h in hyps}
    assert ("compose_text", "composer") in ids
    assert ("send_message", "composer") in ids
    assert ("search", "sidebar") in ids


def test_ingest_and_perception_cycle_attach_enriched_graph():
    wm = WorldModel()
    obs = Observation(
        timestamp=0.0,
        app_name="AnyApp",
        window_name="Win",
        nodes=[
            AxNode(role="AXStaticText", name="Item1", bbox=(20, 40, 80, 30)),
            AxNode(role="AXButton", name="OptionA", bbox=(860, 90, 140, 32)),
            AxNode(role="AXButton", name="OptionB", bbox=(860, 130, 140, 32)),
            AxNode(role="AXTextField", name="Input", bbox=(400, 920, 500, 40)),
            AxNode(role="AXButton", name="Mic", bbox=(960, 920, 48, 40)),
        ],
        source="test",
    )
    patch = wm.ingest(obs, action="observe")
    assert patch.scene_graph is not None
    kinds = {r["kind"] for r in patch.scene_graph["regions"]}
    assert "composer" in kinds
    assert "floating_menu" in kinds

    runtime = RuntimeState()
    runtime.world_model = wm
    goal = Goal(kind="generic_voice_call", contact="x", app="AnyApp")
    _, feats, _ = build_view_features(runtime, goal)
    extras = feats.get("extras") or {}
    assert extras.get("world_graph")
    assert extras.get("scene_attention_regions")
    assert "initiate_session" in str(extras.get("world_graph"))
