"""Compact fast-path prompt/packet/parse for local small VLMs."""

from __future__ import annotations

import json

from plugin.agent.unified_cognition import (
    _FAST_SYSTEM_PROMPT,
    _build_messages,
    _compact_fast_packet,
    _expand_fast_parsed,
    _is_fast_vlm_target,
    _parse_proposal,
    _repair_truncated_json,
)


def test_local_ollama_is_fast_target_cloud_is_not(monkeypatch):
    monkeypatch.setenv("HERMES_PERCEPTION_COMPACT", "1")
    assert _is_fast_vlm_target(
        {"provider": "ollama-remote", "model": "qwen3.5:4b", "source": "env:HERMES_PERCEPTION_FAST_MODEL"}
    )
    assert not _is_fast_vlm_target(
        {"provider": "ollama-cloud", "model": "qwen3.5:cloud", "source": "env:HERMES_PERCEPTION_ESCALATE_MODEL"}
    )
    assert not _is_fast_vlm_target(
        {"provider": "ollama-cloud", "model": "qwen3.5:397b", "source": "ranked"}
    )
    monkeypatch.setenv("HERMES_PERCEPTION_COMPACT", "0")
    assert not _is_fast_vlm_target(
        {"provider": "ollama-remote", "model": "qwen3.5:4b", "source": "env:HERMES_PERCEPTION_FAST_MODEL"}
    )


def test_compact_packet_strips_heavy_fields():
    packet = {
        "goal": {
            "operation": "whatsapp_forward_message",
            "source_conversation": "Pallavi",
            "source_query": "zarooratwala",
            "destination": "Tanmay",
            "description": "long essay " * 40,
        },
        "world_model": {"surface": "chat_list", "open_conversation": "", "objects": [{"id": "x"}] * 20},
        "observation": {
            "ax_evidence": [{"id": i, "name": f"n{i}", "role": "AXButton"} for i in range(30)],
            "sources": {"a": 1},
        },
        "allowed_actions": ["Click"] * 50,
        "affordance_frontier": {"huge": True},
        "last_action": {"family": "open_entity", "ok": True, "effect": "transition"},
    }
    compact = _compact_fast_packet(packet, phase="OPEN_SOURCE")
    assert "allowed_actions" not in compact
    assert "affordance_frontier" not in compact
    assert compact["phase"] == "OPEN_SOURCE"
    assert len(compact["observation"]["ax"]) <= 8
    assert "description" not in compact["goal"]
    compact_s = json.dumps(compact)
    assert len(compact_s) < len(json.dumps(packet)) / 2
    assert "Pallavi" in compact_s


def test_expand_fast_parsed_feeds_proposal():
    raw = {
        "surface": "chat_list",
        "objects": [
            {"id": "m1", "role": "row", "text": "Pallavi", "point": [10, 20], "match": 0.95}
        ],
        "actions": [{"family": "open_entity", "target": "m1", "score": 0.9}],
        "needs_more_evidence": False,
        "confidence": 0.88,
    }
    expanded = _expand_fast_parsed(raw, frame=3)
    proposal = _parse_proposal(expanded, frame=3)
    assert proposal.world_model["surface"] == "chat_list"
    assert proposal.visible_objects or proposal.world_model.get("objects")
    assert proposal.suggested_actions[0]["family"] == "open_entity"
    assert proposal.confidence == 0.88
    assert not proposal.missing_evidence


def test_repair_truncated_json_recovers_objects():
    truncated = (
        '{"surface":"search","objects":[{"id":"m1","role":"field","text":"Pallavi",'
        '"point":[10,20],"match":0.9},{"id":"m2","role":"message","text":"No results",'
        '"point":[30,40],"match"'
    )
    repaired = _repair_truncated_json(truncated)
    assert isinstance(repaired, dict)
    assert repaired.get("surface") == "search"
    assert isinstance(repaired.get("objects"), list)
    assert repaired["objects"][0]["text"] == "Pallavi"


def test_fast_build_messages_uses_tiny_system_prompt():
    packet = {
        "goal": {"operation": "whatsapp_forward_message", "source_conversation": "Pallavi"},
        "world_model": {"surface": "chat_list", "progress": {"phase": "OPEN_SOURCE"}},
        "observation": {"ax_evidence": []},
    }
    messages, size = _build_messages(
        packet,
        "",
        fast_path=True,
        phase="OPEN_SOURCE",
        data_url="data:image/jpeg;base64,xx",
        image_size=(640, 800),
    )
    assert messages[0]["content"] == _FAST_SYSTEM_PROMPT
    assert "affordance_frontier" not in messages[1]["content"][0]["text"]
    assert size == (640, 800)
