"""Hermes adapter — world_* tools so planner talks to WorldModel, not raw AX."""

from __future__ import annotations

import json
import threading
from typing import Any, Dict, Optional

from plugin.agent.decision import DecisionEngine
from plugin.agent.goal import Goal
from plugin.agent.runtime.recovery import recover_after_unexpected
from plugin.agent.runtime.state import RuntimeState
from plugin.executor.ghost import get_executor
from plugin.experiments.logger import EventLogger
from plugin.perception.macos.accessibility.observer import FixtureObserver, get_observer
from plugin.perception.macos.fusion.coverage import maybe_recover_with_screen2ax
from pathlib import Path

_lock = threading.Lock()
_runtime: Optional[RuntimeState] = None
_logger: Optional[EventLogger] = None
_engine = DecisionEngine(selector_enabled=True)


def _goal_from_text(goal_text: str) -> Goal:
    return Goal.infer_from_text(goal_text)


def _rt() -> RuntimeState:
    global _runtime, _logger
    with _lock:
        if _runtime is None:
            _runtime = RuntimeState()
        if _logger is None:
            _logger = EventLogger(Path.home() / ".hermes" / "plugin" / "logs" / "hermes_world.jsonl")
        return _runtime


def handle_world_state(args: Dict[str, Any], **kwargs: Any) -> str:
    rt = _rt()
    return json.dumps(rt.world_model.summary(), indent=2)


def handle_world_observe(args: Dict[str, Any], **kwargs: Any) -> str:
    rt = _rt()
    fixture = args.get("fixture")
    app = args.get("app")
    if fixture:
        obs = FixtureObserver(Path(fixture)).observe(app=app)
    else:
        try:
            obs = get_observer(with_screenshot=False).observe(app=app)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})
    obs = maybe_recover_with_screen2ax(obs)
    action = args.get("action")
    patch = rt.world_model.ingest(obs, action=action, target_entity_id=args.get("target_entity_id"))
    _rt()
    log = _logger
    if log:
        log.observation({"app": obs.app_name, "nodes": len(obs.nodes), "source": obs.source})
        log.world_patch({"screen": patch.screen_label, "retention": patch.retention})
    return json.dumps(
        {
            "ok": True,
            "app": obs.app_name,
            "window": obs.window_name,
            "nodes": len(obs.nodes),
            "screen": patch.screen_label,
            "retention": patch.retention,
            "summary": rt.world_model.summary(),
        },
        indent=2,
    )


def handle_world_plan(args: Dict[str, Any], **kwargs: Any) -> str:
    rt = _rt()
    goal = args.get("goal") or rt.active_task or "Call Pallavi on WhatsApp"
    rt.active_task = goal
    goal_obj = _goal_from_text(goal)
    action = _engine.decide(goal_obj, rt.world_model, rt.execution_state)
    payload = None if action is None else action.__dict__
    if _logger:
        _logger.planner_decision({"goal": goal_obj.description, "action": payload})
    return json.dumps({"goal": goal_obj.description, "action": payload}, indent=2)


def handle_world_act(args: Dict[str, Any], **kwargs: Any) -> str:
    rt = _rt()
    action = (args.get("action") or "click").lower()
    semantic = args.get("semantic") or args.get("target") or ""
    text = args.get("text") or ""
    dry_run = bool(args.get("dry_run", True))
    entity_id = args.get("target_entity_id")
    ent = None
    if entity_id is not None:
        try:
            ent = rt.world_model.entities.get(int(entity_id))
        except Exception:
            ent = None
    if ent is None and semantic:
        ent = rt.world_model.find_entity(semantic)
    ex = get_executor(dry_run=dry_run, app=rt.world_model.active_app or "WhatsApp")
    if action == "type":
        into = semantic or (ent.label if ent is not None else None)
        result = ex.type_text(text, into=into)
    elif action == "hover":
        if ent is None:
            return json.dumps({"ok": False, "error": f"entity not found: {semantic}"})
        result = ex.hover(ent)
    elif action in {"context_click", "right_click"}:
        if ent is None:
            return json.dumps({"ok": False, "error": f"entity not found: {semantic}"})
        result = ex.context_click(ent)
    elif action == "press":
        result = ex.press(text or "return")
    elif action == "scroll":
        result = ex.scroll()
    else:
        if ent is None:
            return json.dumps({"ok": False, "error": f"entity not found: {semantic}"})
        result = ex.click(ent)
    rt.execution_state.last_action = action
    rt.execution_state.last_target_id = ent.id if ent else None
    rt.execution_state.last_result = result.__dict__
    rt.execution_state.step += 1
    if _logger:
        _logger.execution(result.__dict__)
    return json.dumps(result.__dict__)


def handle_world_recover(args: Dict[str, Any], **kwargs: Any) -> str:
    rt = _rt()
    fixture = args.get("fixture")
    if fixture:
        obs = FixtureObserver(Path(fixture)).observe()
    else:
        obs = get_observer(with_screenshot=False).observe(args.get("app"))
    result = recover_after_unexpected(rt, obs, goal=args.get("goal") or rt.active_task or "")
    return json.dumps(
        {
            "recovered": result.recovered,
            "message": result.message,
            "action": None if not result.new_action else result.new_action.__dict__,
        },
        indent=2,
    )


WORLD_STATE_SCHEMA = {
    "name": "world_state",
    "description": "Read Plugin WorldModel summary (no screenshots/AX). Use for GUI tasks.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

WORLD_OBSERVE_SCHEMA = {
    "name": "world_observe",
    "description": "Observe macOS UI via macapptree, patch the WorldModel.",
    "parameters": {
        "type": "object",
        "properties": {
            "app": {"type": "string"},
            "fixture": {"type": "string", "description": "Offline fixture path"},
            "action": {"type": "string", "description": "Last action label for transition learning"},
            "target_entity_id": {"type": "integer"},
        },
    },
}

WORLD_PLAN_SCHEMA = {
    "name": "world_plan",
    "description": "Return the next decision snapshot from WorldModel.",
    "parameters": {
        "type": "object",
        "properties": {"goal": {"type": "string"}},
        "required": ["goal"],
    },
}

WORLD_ACT_SCHEMA = {
    "name": "world_act",
    "description": "Execute action via Ghost OS (AX) against a semantic entity in the WorldModel.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["click", "hover", "context_click", "right_click", "type", "press", "scroll"]},
                "semantic": {"type": "string"},
                "target_entity_id": {"type": "integer"},
                "text": {"type": "string"},
                "dry_run": {"type": "boolean"},
            },
            "required": ["action"],
        },
}

WORLD_RECOVER_SCHEMA = {
    "name": "world_recover",
    "description": "Observe unexpected UI, patch WorldModel, replan without restarting the task.",
    "parameters": {
        "type": "object",
        "properties": {
            "goal": {"type": "string"},
            "app": {"type": "string"},
            "fixture": {"type": "string"},
        },
    },
}

PLUGIN_CALL_WHATSAPP_SCHEMA = {
    "name": "plugin_call_whatsapp",
    "description": (
        "Place a WhatsApp macOS call via the Plugin Accessibility world-model "
        "(observe→patch→decide→act). Pass the exact contact name the user asked for. "
        "Call this tool directly — do NOT use execute_code or invent hermes_tools imports. "
        "Do NOT use Hermes messaging gateways. Requires Accessibility on Terminal/iTerm. "
        "If multiple contacts match, the tool returns candidates for confirmation instead of guessing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "contact": {
                "type": "string",
                "description": (
                    "User reference string (required). Example: 'Pallavi', 'plugin support', "
                    "'now group'. May include type words like 'group'."
                ),
            },
            "target_name": {
                "type": "string",
                "description": (
                    "Optional interpreted display name from Hermes/LLM (e.g. 'Now' for 'now group'). "
                    "When set with target_kind, skips rule-based interpretation."
                ),
            },
            "target_kind": {
                "type": "string",
                "description": "Optional entity kind: contact | group | community.",
            },
            "live": {
                "type": "boolean",
                "description": "True = real WhatsApp GUI (default True). False = fixture dry-run.",
            },
            "hangup": {
                "type": "boolean",
                "description": "Hang up after ringing is verified (default True).",
            },
        },
        "required": ["contact"],
    },
}


def handle_plugin_call_whatsapp(args: Dict[str, Any], **kwargs: Any) -> str:
    """High-level Call-on-WhatsApp entry — do not invent gateway adapters."""
    from plugin.experiments.call_pallavi import run_call_pallavi

    contact = (args.get("contact") or "").strip()
    if not contact:
        return json.dumps(
            {
                "ok": False,
                "error": "contact is required",
                "hint": "Call plugin_call_whatsapp(contact='Name', live=true, hangup=true) as a native tool.",
            },
            indent=2,
        )
    live = bool(args.get("live", True))
    hangup = bool(args.get("hangup", True))
    target_name = str(args.get("target_name") or "").strip()
    target_kind = str(args.get("target_kind") or "").strip()
    goal = f"Call {contact} on WhatsApp"
    log_path = Path.home() / ".hermes" / "plugin" / "logs" / (
        f"call_{contact.lower().replace(' ', '_')}_{'live' if live else 'fixture'}.jsonl"
    )
    try:
        ok, log = run_call_pallavi(
            log_path=log_path,
            live=live,
            hangup=hangup,
            contact=contact,
            goal=goal,
            target_name=target_name,
            target_kind=target_kind,
        )
    except Exception as e:
        return json.dumps(
            {
                "ok": False,
                "error": str(e),
                "contact": contact,
                "hint": (
                    "Run Hermes/plugin from Terminal.app or iTerm with Accessibility "
                    "enabled. Call plugin_call_whatsapp directly (not execute_code)."
                ),
            },
            indent=2,
        )
    # Surface ambiguity / failure details from last log if present
    detail = ""
    try:
        path = Path(log.path if hasattr(log, "path") else log_path)
        if path.is_file():
            for line in reversed(path.read_text(encoding="utf-8").splitlines()):
                if not line.strip():
                    continue
                ev = json.loads(line)
                if ev.get("kind") == "run_end":
                    detail = str(ev.get("detail") or ev.get("message") or "")
                    break
                if ev.get("kind") == "contact_low_confidence" or (
                    ev.get("kind") == "decision_engine"
                    and (ev.get("trace") or {}).get("features", {}).get("extras", {}).get(
                        "needs_confirmation"
                    )
                ):
                    extras = (ev.get("trace") or {}).get("features", {}).get("extras", {}) if ev.get("kind") == "decision_engine" else {}
                    cands = ev.get("candidates") or extras.get("contact_candidates")
                    conf = ev.get("confidence") if "confidence" in ev else extras.get("resolution_confidence")
                    return json.dumps(
                        {
                            "ok": False,
                            "contact": contact,
                            "needs_confirmation": True,
                            "resolution_confidence": conf,
                            "candidates": cands,
                            "message": (
                                f"Low confidence resolving {contact!r}. "
                                "Ask the user which exact name to call, then retry "
                                "plugin_call_whatsapp with that exact contact string "
                                "(confirmation trains Resolution Memory)."
                            ),
                            "log": str(path),
                        },
                        indent=2,
                    )
    except Exception:
        pass
    return json.dumps(
        {
            "ok": ok,
            "contact": contact,
            "live": live,
            "hangup": hangup,
            "log": str(log.path if hasattr(log, "path") else log_path),
            "message": (
                f"{'Succeeded' if ok else 'Failed'}: {goal}. "
                f"{detail} "
                f"See log for typed/AXValue/ringing evidence."
            ).strip(),
        },
        indent=2,
    )


def register_hermes_tools() -> None:
    from tools.registry import registry

    registry.register(
        name="world_state",
        toolset="plugin_world",
        schema=WORLD_STATE_SCHEMA,
        handler=handle_world_state,
        check_fn=lambda: True,
        requires_env=[],
        description=WORLD_STATE_SCHEMA["description"],
    )
    registry.register(
        name="world_observe",
        toolset="plugin_world",
        schema=WORLD_OBSERVE_SCHEMA,
        handler=handle_world_observe,
        check_fn=lambda: True,
        requires_env=[],
        description=WORLD_OBSERVE_SCHEMA["description"],
    )
    registry.register(
        name="world_plan",
        toolset="plugin_world",
        schema=WORLD_PLAN_SCHEMA,
        handler=handle_world_plan,
        check_fn=lambda: True,
        requires_env=[],
        description=WORLD_PLAN_SCHEMA["description"],
    )
    registry.register(
        name="world_act",
        toolset="plugin_world",
        schema=WORLD_ACT_SCHEMA,
        handler=handle_world_act,
        check_fn=lambda: True,
        requires_env=[],
        description=WORLD_ACT_SCHEMA["description"],
    )
    registry.register(
        name="world_recover",
        toolset="plugin_world",
        schema=WORLD_RECOVER_SCHEMA,
        handler=handle_world_recover,
        check_fn=lambda: True,
        requires_env=[],
        description=WORLD_RECOVER_SCHEMA["description"],
    )
    registry.register(
        name="plugin_call_whatsapp",
        toolset="plugin_world",
        schema=PLUGIN_CALL_WHATSAPP_SCHEMA,
        handler=handle_plugin_call_whatsapp,
        check_fn=lambda: True,
        requires_env=[],
        description=PLUGIN_CALL_WHATSAPP_SCHEMA["description"],
    )
