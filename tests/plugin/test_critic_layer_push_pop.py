"""Critic layer push/pop + permanence when HERMES_LAYERED_PERCEPTION is on."""

from __future__ import annotations

import pytest

from plugin.agent.world_critic import critique_world_proposal


@pytest.fixture
def layered_on(monkeypatch):
    monkeypatch.setenv("HERMES_LAYERED_PERCEPTION", "1")
    yield


def test_overlay_proposal_restores_occluded_container(layered_on):
    prior = {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "objects": [
            {
                "id": "m1",
                "kind": "message",
                "text": "zarooratwala",
                "point": [10, 20],
                "matches_goal": True,
            }
        ],
        "layers": [
            {
                "role": "container",
                "name": "Pallavi",
                "state": "active",
                "objects": [
                    {
                        "id": "m1",
                        "kind": "message",
                        "text": "zarooratwala",
                        "point": [10, 20],
                        "matches_goal": True,
                    }
                ],
            }
        ],
    }
    proposal = {
        "surface": "context_menu",
        "open_conversation": "",
        "objects": [
            {"id": "a1", "kind": "menu_item", "text": "Forward", "point": [30, 40]}
        ],
        "layers": [
            {
                "role": "action_menu",
                "name": "message actions",
                "state": "active",
                "objects": [
                    {
                        "id": "a1",
                        "kind": "menu_item",
                        "text": "Forward",
                        "point": [30, 40],
                    }
                ],
            }
        ],
    }
    verdict = critique_world_proposal(
        prior, proposal, last_action="reveal_actions", observed_surface="context_menu"
    )
    doc = verdict.accepted_document
    roles = [l["role"] for l in (doc.get("layers") or [])]
    assert "container" in roles and "action_menu" in roles
    container = next(l for l in doc["layers"] if l["role"] == "container")
    assert container["state"] == "occluded"
    assert doc.get("open_conversation") == "Pallavi"
    assert any(d.field == "layers" for d in verdict.decisions)


def test_layers_flag_off_skips_layer_decision(monkeypatch):
    monkeypatch.setenv("HERMES_LAYERED_PERCEPTION", "0")
    verdict = critique_world_proposal(
        {"surface": "conversation", "open_conversation": "Pallavi"},
        {
            "surface": "context_menu",
            "objects": [{"text": "Forward", "kind": "menu_item", "point": [1, 2]}],
        },
        last_action="reveal_actions",
    )
    assert not any(d.field == "layers" for d in verdict.decisions)
