"""Live WhatsApp high-risk selector evals.

These are opt-in smoke tests for the actual cloud selector path. They stay
skipped in normal CI and only run when the user explicitly enables live
tests.

Run:
    HERMES_LIVE_TESTS=1 pytest -q tests/plugin/test_whatsapp_high_risk_selector_live.py

The module loads ``~/.hermes/.env`` at import time so a locally stored
``OPENROUTER_API_KEY`` is visible before the test body runs.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

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
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")

pytestmark = [
    pytest.mark.skipif(not LIVE, reason="live-only — set HERMES_LIVE_TESTS=1"),
    pytest.mark.skipif(not OPENROUTER_KEY, reason="OPENROUTER_API_KEY not configured"),
]

from plugin.agent.apps.whatsapp import WhatsAppOverlay
from plugin.agent.decision import DecisionEngine
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import ExecutionState
from plugin.worldmodel.capability import build_capability_graph
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel
from plugin.worldmodel.scene.reconstruct import reconstruct_world_graph


def _entity(
    eid: int,
    *,
    etype: str = "button",
    label: str,
    bounds=(0.0, 0.0, 40.0, 40.0),
    description: str = "",
    value: str = "",
    role: Optional[str] = None,
    actions: Optional[List[str]] = None,
) -> Entity:
    attrs: Dict[str, object] = {}
    if description:
        attrs["description"] = description
    if value:
        attrs["value"] = value
    return Entity(
        id=eid,
        entity_type=etype,
        semantic_role=label,
        label=label,
        role=role or ("AXTextField" if etype == "textfield" else "AXButton"),
        bounds=bounds,
        actions=actions if actions is not None else (["click"] if etype in {"button", "link"} else ["click", "type"] if etype == "textfield" else []),
        attributes=attrs,
        visible=True,
    )


def _seed(entities: List[Entity]) -> WorldModel:
    wm = WorldModel()
    wm.active_app = "WhatsApp"
    wm.entities = {e.id: e for e in entities}
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = max(e.id for e in entities) + 1 if entities else 1
    wm.overlay_hints = {}
    return wm


def _emit_trace(label: str, engine: DecisionEngine, decision) -> None:
    trace = engine.last_trace.selector if engine.last_trace else None
    payload = {
        "label": label,
        "decision": None if decision is None else engine.last_trace.chosen,
        "selector": trace,
        "selector_confidence": None if engine.last_trace is None else engine.last_trace.selector_confidence,
    }
    sys.__stdout__.write("\n=== LIVE WHATSAPP HIGH-RISK EVAL ===\n")
    sys.__stdout__.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    sys.__stdout__.write("\n")
    sys.__stdout__.flush()


def _call_goal() -> Goal:
    return Goal(kind="whatsapp_voice_call", contact="now group")


def _forward_goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
    )


def test_live_high_risk_call_selector_prefers_voice_over_video_and_participants():
    goal = _call_goal()
    entities = [
        _entity(1, label="Now...", etype="static", bounds=(900, 20, 180, 34), actions=[]),
        _entity(2, label="Voice", etype="button", bounds=(860, 100, 120, 36)),
        _entity(3, label="Video", etype="button", bounds=(860, 140, 120, 36)),
        _entity(4, label="Select people", etype="button", bounds=(860, 180, 160, 36)),
        _entity(5, label="Voice message", etype="button", bounds=(960, 920, 48, 40)),
    ]
    wm = _seed(entities)
    wm_graph = reconstruct_world_graph(list(wm.entities.values()), app="WhatsApp")
    wm.last_scene_graph = wm_graph.to_dict()
    wm.last_capability_graph = build_capability_graph(
        wm_graph,
        list(wm.entities.values()),
        goal=goal,
        capability_hints=WhatsAppOverlay().capability_hints(goal),
    ).to_dict()

    from agent.auxiliary_client import call_llm

    engine = DecisionEngine(selector_enabled=True, selector_caller=call_llm)
    decision = engine.define_action_step(goal, wm, ExecutionState())
    _emit_trace("call-picker", engine, decision)

    assert decision is not None
    assert decision.action_family == "start_call"
    assert decision.capability_type == "InitiateVoiceCall"
    assert engine.last_trace is not None
    assert engine.last_trace.selector_confidence >= engine.irreversible_action_confidence_threshold()


def test_live_high_risk_forward_selector_prefers_source_content_over_forward_chrome():
    goal = _forward_goal()
    entities = [
        _entity(1, label="Kulvinder Ji", etype="static", bounds=(900, 20, 180, 34), actions=[]),
        _entity(2, label="Your message, Link, https://www.zarooratwala.com/abc", etype="link", bounds=(920, 420, 300, 60)),
        _entity(3, label="Forward", etype="button", bounds=(900, 140, 100, 36)),
        _entity(4, label="Type a message", etype="textfield", bounds=(700, 900, 600, 40)),
    ]
    wm = _seed(entities)
    wm.overlay_hints["forward_task"] = {
        "bindings": {
            "source_conversation": {
                "name": "source_conversation",
                "constraints": {"name": "Kulvinder"},
                "candidate_entity_ids": [],
                "resolved_entity_id": 1,
                "confidence": 0.95,
                "status": "confirmed",
                "evidence": ["open_conversation='Kulvinder Ji'"],
            },
            "source_object": {
                "name": "source_object",
                "constraints": {
                    "content_tokens": ["zarooratwala"],
                    "types": ["link", "message"],
                    "container_binding": "source_conversation",
                },
                "candidate_entity_ids": [2],
                "resolved_entity_id": 2,
                "confidence": 0.75,
                "status": "provisional",
                "evidence": ["prior entity_id=2 still visible among 1"],
            },
            "destination": {
                "name": "destination",
                "constraints": {"name": "Pallavi"},
                "candidate_entity_ids": [],
                "resolved_entity_id": None,
                "confidence": 0.0,
                "status": "unresolved",
                "evidence": [],
            },
        },
        "predicates": {
            "source_conversation_open": True,
            "source_object_visible": True,
            "source_object_selected": True,
            "forward_surface_open": False,
            "destination_picker_visible": False,
            "destination_selected": False,
            "forward_completed": False,
        },
        "derived_phase": "OPEN_FORWARD",
    }
    wm_graph = reconstruct_world_graph(list(wm.entities.values()), app="WhatsApp")
    wm.last_scene_graph = wm_graph.to_dict()
    wm.last_capability_graph = build_capability_graph(
        wm_graph,
        list(wm.entities.values()),
        goal=goal,
        capability_hints=WhatsAppOverlay().capability_hints(goal),
    ).to_dict()

    from agent.auxiliary_client import call_llm

    engine = DecisionEngine(selector_enabled=True, selector_caller=call_llm)
    decision = engine.define_action_step(goal, wm, ExecutionState())
    _emit_trace("forward-source-binding", engine, decision)

    assert decision is not None
    assert decision.action_family == "select_content"
    assert decision.capability_type in {"SelectContent", "ForwardMessage"}
    assert engine.last_trace is not None
    assert engine.last_trace.selector_confidence >= engine.irreversible_action_confidence_threshold()
