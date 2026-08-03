"""Object permanence is applied where perception is committed, not in the task.

``_apply_layer_permanence`` runs after the world critic accepts a reading. Given
a fresh reading that is only the Forward menu, it must carry the conversation
forward (occluded) using the prior document as memory, and restore the flat
``open_conversation`` so even flat consumers see the chat is still open.
"""

import os
from types import SimpleNamespace

import pytest

from plugin.agent.unified_cognition import UnifiedProposal, _apply_layer_permanence


@pytest.fixture
def layered_on(monkeypatch):
    monkeypatch.setenv("HERMES_LAYERED_PERCEPTION", "1")
    yield


def _prior_conversation():
    return {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "objects": [{"id": "o1", "kind": "message", "text": "check zarooratwala.com", "matches_goal": True, "point": [10, 20]}],
        "layers": [
            {
                "role": "container",
                "name": "Pallavi",
                "state": "active",
                "objects": [{"id": "o1", "kind": "message", "text": "check zarooratwala.com", "matches_goal": True, "point": [10, 20]}],
            }
        ],
    }


def test_menu_reading_carries_the_conversation_occluded(layered_on):
    accepted = {
        "surface": "context_menu",
        "open_conversation": "",
        "objects": [{"id": "m1", "kind": "menu_item", "text": "Forward", "point": [30, 40]}],
        "layers": [],
    }
    execution_state = SimpleNamespace(unified_world_document=accepted)
    proposal = UnifiedProposal(
        world_model=accepted,
        observed_state={"surface": "context_menu", "open_conversation": ""},
        visible_objects=list(accepted["objects"]),
    )

    _apply_layer_permanence(execution_state, proposal, _prior_conversation())

    doc = execution_state.unified_world_document
    roles = [l["role"] for l in doc["layers"]]
    assert roles == ["container", "action_menu"]
    assert doc["layers"][0]["state"] == "occluded"
    assert doc["layers"][1]["state"] == "active"
    # flat field restored so downstream (and the binder bridge) see permanence
    assert doc["open_conversation"] == "Pallavi"
    # the goal message survives occlusion, and the menu item is also clickable
    texts = {o["text"] for o in doc["objects"]}
    assert "check zarooratwala.com" in texts and "Forward" in texts


def test_flag_off_is_a_no_op(monkeypatch):
    monkeypatch.setenv("HERMES_LAYERED_PERCEPTION", "0")
    accepted = {"surface": "context_menu", "open_conversation": "", "objects": [], "layers": []}
    execution_state = SimpleNamespace(unified_world_document=accepted)
    proposal = UnifiedProposal(world_model=accepted, observed_state={"surface": "context_menu"})

    _apply_layer_permanence(execution_state, proposal, _prior_conversation())

    assert execution_state.unified_world_document["layers"] == []
    assert execution_state.unified_world_document["open_conversation"] == ""


def test_model_emitted_layers_are_normalized_not_ignored(layered_on):
    accepted = {
        "surface": "context_menu",
        "open_conversation": "",
        "objects": [],
        "layers": [
            {"role": "conversation", "name": "Pallavi", "state": "active", "objects": [{"kind": "message", "text": "hi", "point": [1, 1]}]},
            {"role": "context_menu", "state": "active", "objects": [{"kind": "menu_item", "text": "Forward", "point": [2, 2]}]},
        ],
    }
    execution_state = SimpleNamespace(unified_world_document=accepted)
    proposal = UnifiedProposal(world_model=accepted, observed_state={"surface": "context_menu"})

    _apply_layer_permanence(execution_state, proposal, {})

    doc = execution_state.unified_world_document
    # invariant enforced: base occluded, only the menu active
    assert doc["layers"][0]["role"] == "container" and doc["layers"][0]["state"] == "occluded"
    assert doc["layers"][1]["role"] == "action_menu" and doc["layers"][1]["state"] == "active"
    assert doc["open_conversation"] == "Pallavi"
