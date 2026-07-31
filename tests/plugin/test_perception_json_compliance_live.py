"""Live JSON-compliance eval for the perception prompt.

This is an opt-in smoke test for the real perception LLM path. It checks that
the live model responds with parseable JSON for the actual prompt shape used by
the WhatsApp forward flow.

Run:
    HERMES_LIVE_TESTS=1 pytest -q tests/plugin/test_perception_json_compliance_live.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def _load_user_env() -> None:
    env_file = Path.home() / ".hermes" / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_user_env()

LIVE = os.environ.get("HERMES_LIVE_TESTS") == "1"
OLLAMA_BASE_URL = os.environ.get("OLLAMA_REMOTE_BASE_URL", "").strip()

pytestmark = [
    pytest.mark.skipif(not LIVE, reason="live-only — set HERMES_LIVE_TESTS=1"),
    pytest.mark.skipif(not OLLAMA_BASE_URL, reason="OLLAMA_REMOTE_BASE_URL not configured"),
    pytest.mark.integration,
]


def _make_goal_world_view():
    from plugin.agent.goal import Goal
    from plugin.agent.features import StateFeatures
    from plugin.worldmodel.entities.entity import Entity
    from plugin.worldmodel.model import WorldModel

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
    )
    world = WorldModel()
    world.active_app = "WhatsApp"
    world.entities = {
        1: Entity(
            id=1,
            entity_type="button",
            semantic_role="Chats",
            label="Chats",
            role="AXButton",
            actions=["click"],
            visible=True,
            bounds=(20, 20, 100, 32),
        ),
        2: Entity(
            id=2,
            entity_type="textfield",
            semantic_role="Search",
            label="Search",
            role="AXTextField",
            actions=["click", "type"],
            visible=True,
            bounds=(20, 80, 220, 32),
        ),
        3: Entity(
            id=3,
            entity_type="static",
            semantic_role="Kulvinder Ji",
            label="Kulvinder Ji",
            role="AXStaticText",
            actions=[],
            visible=True,
            bounds=(20, 150, 240, 40),
        ),
    }
    world.tracker._entities = dict(world.entities)
    world.tracker._next_id = 4
    world.last_scene_graph = {
        "report": {"layout_confidence": 0.61, "affordance_entropy": 0.67},
        "attention": {"region_ids": ["sidebar"], "entity_ids": [1, 2, 3]},
        "regions": [{"kind": "sidebar"}],
    }
    view = {
        "app": "WhatsApp",
        "screen": "DIALOG",
        "search_query": "",
        "search_visible": True,
        "search_focused": False,
        "open_conversation": "Kulvinder Ji",
        "visible_contacts": ["Kulvinder Ji"],
        "blocking_overlay": False,
        "system_warnings": [],
    }
    features = StateFeatures(
        app="WhatsApp",
        screen_bucket="dialog",
        screen_kind="dialog",
        conversation_open=True,
        search_focused=False,
        worldview_score=0.82,
        mean_belief=0.91,
        extras={"resolution_policy": "observe"},
    )
    return goal, world, view, features


def test_live_perception_prompt_returns_parseable_json():
    from agent import auxiliary_client
    from plugin.agent.perception_synthesis import (
        _build_prompt,
        _extract_json_block,
        _extract_text,
        synthesize_perception,
    )

    goal, world, view, features = _make_goal_world_view()
    token = auxiliary_client.set_runtime_main(
        "ollama-remote",
        "qwen2.5:32b",
        base_url=OLLAMA_BASE_URL,
    )
    try:
        response = auxiliary_client.call_llm(
            task="perception",
            messages=_build_prompt(goal, world, view, features),
            temperature=0.1,
            max_tokens=512,
            timeout=120,
            main_runtime=auxiliary_client.get_runtime_main_snapshot(),
            extra_body={"format": "json"},
        )
        raw_text = _extract_text(response)
        parsed = _extract_json_block(raw_text)
        print("\n--- perception raw response ---")
        print(raw_text)
        print("--- end raw response ---\n")
        assert parsed is not None, f"model response was not parseable JSON: {raw_text!r}"
        for key in (
            "screen_type",
            "active_surface",
            "likely_next_family",
            "confidence",
        ):
            assert key in parsed, f"missing key {key!r} in parsed response: {json.dumps(parsed, ensure_ascii=False)}"

        summary = synthesize_perception(goal, world, view, features, worldview=0.82)
        assert summary is not None
        assert summary.screen_type
        assert summary.likely_next_family
    finally:
        auxiliary_client.reset_runtime_main(token)
