"""Vision must be able to drive the task when accessibility publishes nothing.

WhatsApp exposes roughly two AX nodes: an application and a window. Everything
the task depends on -- which conversation is open, which messages are on screen
-- exists only in the pixels. Before this bridge the perceptor's reading was
used to choose a single action and then discarded, so the phase machine kept
demanding a conversation that was already open and the agent undid its own
progress by going back to search.
"""

from types import SimpleNamespace

from plugin.agent.apps.whatsapp import build_forward_task_state
from plugin.agent.goal import Goal
from plugin.agent.unified_cognition import (
    UnifiedProposal,
    materialize_vision_entities,
    publish_scene_to_world,
    reproject_unified_reading,
)
from plugin.agent.whatsapp_view import WhatsAppWorldView, is_vision_entity
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel


def _goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )


def _conversation_reading(confidence: float = 0.95) -> UnifiedProposal:
    return UnifiedProposal(
        observed_state={
            "surface": "conversation",
            "open_conversation": "Pallavi",
            "target_object_visible": True,
        },
        next_action={"family": "right_click", "target_point": [900, 500]},
        visible_objects=[
            {"kind": "message", "text": "OTP is 4821 do not share", "point": [900, 300]},
            {
                "kind": "message",
                "text": "Check this out zarooratwala.com fresh groceries delivered",
                "point": [900, 500],
                "matches_goal": True,
            },
        ],
        confidence=confidence,
    )


def _blind_world() -> WorldModel:
    """A world with only the chrome AX actually gives us."""
    world = WorldModel(active_app="WhatsApp")
    world.entities[1] = Entity(id=1, entity_type="unknown", semantic_role="app", label="WhatsApp")
    world.entities[2] = Entity(id=2, entity_type="window", semantic_role="window", label="WhatsApp")
    return world


def _apply(world: WorldModel, reading: UnifiedProposal) -> None:
    materialize_vision_entities(world, reading)
    publish_scene_to_world(world, reading)


def test_blind_ax_alone_cannot_see_the_conversation():
    world = _blind_world()
    view = WhatsAppWorldView.from_world_model(world)
    assert view.screen == "UNKNOWN"
    assert not view.open_conversation
    assert view.conversation_messages == []


def test_vision_reading_makes_the_conversation_visible_to_the_runtime():
    world = _blind_world()
    _apply(world, _conversation_reading())

    view = WhatsAppWorldView.from_world_model(world)
    assert view.screen == "CONVERSATION"
    assert view.open_conversation == "Pallavi"
    assert [row["text"] for row in view.conversation_messages] == [
        "OTP is 4821 do not share",
        "Check this out zarooratwala.com fresh groceries delivered",
    ]


def test_phase_advances_past_opening_a_conversation_that_is_already_open():
    """The regression that made the agent destroy its own progress."""
    world = _blind_world()
    goal = _goal()

    before = build_forward_task_state(
        goal, world, WhatsAppWorldView.from_world_model(world), leftover=False
    )
    assert before.derive_phase(leftover=False) == "OPEN_SOURCE"

    _apply(world, _conversation_reading())
    after = build_forward_task_state(
        goal, world, WhatsAppWorldView.from_world_model(world), leftover=False
    )
    assert after.derive_phase(leftover=False) != "OPEN_SOURCE"
    assert after.predicates.source_conversation_open is True


def test_goal_relevant_message_binds_to_a_clickable_object():
    """Perceive the conversation, read the messages, bind the relevant one."""
    world = _blind_world()
    _apply(world, _conversation_reading())

    state = build_forward_task_state(
        _goal(), world, WhatsAppWorldView.from_world_model(world), leftover=False
    )
    binding = state.binding("source_object")
    assert binding.resolved_entity_id is not None
    assert state.predicates.source_object_visible is True

    bound = world.entities[binding.resolved_entity_id]
    assert "zarooratwala" in bound.label.lower()
    x, y, w, h = bound.bounds
    assert (x + w / 2, y + h / 2) == (900.0, 500.0)


def test_vision_entities_never_run_through_accessibility_heuristics():
    """A message body must not be mistaken for a conversation header.

    The AX view builder reads labels positionally; handed a vision entity it
    named the OTP message as the open conversation.
    """
    world = _blind_world()
    _apply(world, _conversation_reading())

    assert any(is_vision_entity(e) for e in world.entities.values())
    view = WhatsAppWorldView.from_world_model_raw(world)
    assert not view.open_conversation
    assert view.conversation_messages == []


def test_the_model_reading_stands_even_when_accessibility_has_content():
    """The runtime does not get to pick which account of the screen is true.

    Suppressing the reading whenever AX reported anything failed on partial
    evidence: a surface publishing one stale row counted as working
    accessibility and hid the only source that could actually see. The model
    receives both and has already reconciled them.
    """
    world = _blind_world()
    world.entities[3] = Entity(
        id=3, entity_type="cell", semantic_role="message", label="a stale AX message row",
        bounds=(100.0, 200.0, 300.0, 40.0),
    )
    reading = _conversation_reading()
    assert materialize_vision_entities(world, reading) == 2
    _apply(world, reading)

    view = WhatsAppWorldView.from_world_model(world)
    assert view.open_conversation == "Pallavi"


def test_a_hesitant_reading_is_still_the_model_reading():
    """Low confidence is information for the model, not a runtime veto.

    Discarding the reading below a threshold left the runtime with no account
    of the screen at all, which is strictly worse than an uncertain one. The
    confidence travels with the reading so the model can revisit it next frame.
    """
    world = _blind_world()
    _apply(world, _conversation_reading(confidence=0.4))

    view = WhatsAppWorldView.from_world_model(world)
    assert view.screen == "CONVERSATION"
    assert view.open_conversation == "Pallavi"


def _persisted_conversation_document() -> dict:
    """The accepted world document unified cognition carries between steps."""
    return {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "objects": [
            {"kind": "message", "text": "OTP is 4821 do not share", "point": [900, 300]},
            {
                "kind": "message",
                "text": "Check this out zarooratwala.com fresh groceries delivered",
                "point": [900, 500],
                "matches_goal": True,
            },
        ],
        "confidence": 0.9,
    }


def test_reprojecting_the_persisted_reading_survives_a_blind_ax_ingest():
    """The core fix: the reading is authoritative *between* model calls.

    A fresh accessibility ingest rebuilds the world as chrome-only (WhatsApp),
    which used to wipe the last unified reading and make the phase machine
    oscillate. Re-projecting the persisted document restores the scene without a
    new model call, so the symbolic view and forward-task predicates stay put.
    """
    world = _blind_world()  # simulate the world right after an empty AX ingest
    exec_state = SimpleNamespace(
        unified_world_document=_persisted_conversation_document(),
        unified_point_scale=1.0,
    )

    created = reproject_unified_reading(world, exec_state)
    assert created == 2

    view = WhatsAppWorldView.from_world_model(world)
    assert view.screen == "CONVERSATION"
    assert view.open_conversation == "Pallavi"

    state = build_forward_task_state(_goal(), world, view, leftover=False)
    assert state.predicates.source_conversation_open is True
    assert state.predicates.source_object_visible is True
    assert state.derive_phase(leftover=False) != "OPEN_SOURCE"


def test_reprojection_is_a_noop_without_a_persisted_reading():
    world = _blind_world()
    assert reproject_unified_reading(world, SimpleNamespace()) == 0
    assert reproject_unified_reading(world, SimpleNamespace(unified_world_document={})) == 0
    view = WhatsAppWorldView.from_world_model(world)
    assert not view.open_conversation


def test_each_frame_replaces_the_previous_vision_entities():
    """Stale objects must not pile up as the screen scrolls."""
    world = _blind_world()
    _apply(world, _conversation_reading())
    first = {e.id for e in world.entities.values() if is_vision_entity(e)}
    assert len(first) == 2

    scrolled = UnifiedProposal(
        observed_state={"surface": "conversation", "open_conversation": "Pallavi"},
        next_action={"family": "scroll"},
        visible_objects=[{"kind": "message", "text": "a later message", "point": [900, 400]}],
        confidence=0.9,
    )
    _apply(world, scrolled)

    remaining = [e for e in world.entities.values() if is_vision_entity(e)]
    assert [e.label for e in remaining] == ["a later message"]
