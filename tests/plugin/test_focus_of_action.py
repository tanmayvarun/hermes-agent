"""The perceptor's focus-of-action reading: object permanence and layer hierarchy.

Covers the structured ``app → layer → region → focus object`` reading, the
object-permanence anchor (``belongs_to_task``/``presence``) that lets the brain
notice the task surface has vanished behind a foreign app, and the adapter that
pulls the pieces out of the live perception state.
"""

from __future__ import annotations

from plugin.agent.focus_of_action import (
    OCCLUDED,
    PRESENT,
    compute_focus_of_action,
    focus_of_action_from_perception,
)


class _Goal:
    def __init__(self, app="WhatsApp", link_query="ZarooratWala", contact="Kulvinder", target_contact="Pallavi"):
        self.app = app
        self.link_query = link_query
        self.contact = contact
        self.target_contact = target_contact
        self.kind = "whatsapp_forward_message"


def test_focus_reads_the_layer_hierarchy_and_the_goal_object():
    """The reading is a hierarchy, not a flat surface: it names the active layer,
    the attended region, and the single goal-relevant object with permanence."""
    layers = [
        {"role": "container", "name": "Kulvinder Ji", "state": "occluded", "objects": [{"text": "hi"}]},
        {"role": "action_menu", "name": "", "state": "active", "objects": [{"text": "Forward"}]},
    ]
    foa = compute_focus_of_action(
        goal=_Goal(),
        application="\u200eWhatsApp",  # macOS bidi mark must not break the match
        layers=layers,
        region_kind="floating_menu",
        focus_label="ZarooratWala video link",
        focus_object_id="42",
    )
    assert foa.app == "WhatsApp"  # the invisible mark is stripped for display
    assert foa.belongs_to_task is True
    assert foa.presence == PRESENT
    assert foa.active_layer_role == "action_menu"
    assert foa.region.kind == "floating_menu"
    assert foa.focus_object is not None
    assert foa.focus_object.matches_goal is True
    assert foa.focus_object.object_id == "42"
    # The occluded container is still in the reading — object permanence.
    assert any(l["role"] == "container" and l["state"] == "occluded" for l in foa.layers)


def test_a_foreign_foreground_app_is_flagged_as_not_the_task_surface():
    """When the eyes are on YouTube mid-task, the reading must say so: the app is
    not the task app, the surface is no longer present, and the audit summary
    explains the drift so a developer is not misled by a cheerful re-description."""
    foa = compute_focus_of_action(goal=_Goal(), application="YouTube", layers=[], focus_label="")
    assert foa.belongs_to_task is False
    assert foa.presence == OCCLUDED
    assert foa.focus_object is None
    assert "not the task app" in foa.summary
    assert "youtube" in foa.summary.lower()


def test_presence_fails_open_when_the_app_is_unknown():
    """A missing app reading must never fabricate a vanished surface."""
    foa = compute_focus_of_action(goal=_Goal(), application="", layers=[])
    assert foa.belongs_to_task is True
    assert foa.presence == PRESENT


def test_focus_object_that_does_not_match_goal_is_marked():
    foa = compute_focus_of_action(
        goal=_Goal(),
        application="WhatsApp",
        layers=[{"role": "list", "state": "active", "objects": []}],
        focus_label="Some unrelated contact",
    )
    assert foa.focus_object is not None
    assert foa.focus_object.matches_goal is False
    assert "does not match goal" in foa.summary


class _World:
    def __init__(self, scene_graph=None, active_app="WhatsApp"):
        self.last_scene_graph = scene_graph
        self.active_app = active_app


class _State:
    def __init__(self, doc=None):
        self.unified_world_document = doc


def test_adapter_reads_layers_from_the_unified_document_and_region_from_the_scene():
    """The adapter prefers the permanence-merged layer stack the unified path
    persists, and resolves the attended region kind from the scene graph."""
    doc = {
        "layers": [
            {"role": "container", "name": "Kulvinder Ji", "state": "active", "objects": [{"text": "x"}]},
        ]
    }
    scene = {
        "regions": [{"id": "r1", "kind": "timeline"}, {"id": "r2", "kind": "sidebar"}],
        "attention": {"region_ids": ["r1"], "entity_ids": []},
    }
    foa = focus_of_action_from_perception(
        goal=_Goal(),
        world=_World(scene_graph=scene),
        view={"surface": "conversation"},
        execution_state=_State(doc=doc),
        application="WhatsApp",
    )
    assert foa.active_layer_role == "container"
    assert foa.active_layer_name == "Kulvinder Ji"
    assert foa.region.kind == "timeline"


def test_adapter_degrades_to_the_flat_view_without_a_unified_document():
    """No unified document → a one-layer stack from the flat view still yields
    a reading rather than an empty one."""
    foa = focus_of_action_from_perception(
        goal=_Goal(),
        world=_World(scene_graph=None),
        view={"surface": "search"},
        execution_state=_State(doc=None),
        application="WhatsApp",
    )
    assert foa.app == "WhatsApp"
    assert foa.active_layer_role  # a layer was derived from the flat view
