"""Characterization of ``run_goal_closed_loop``.

The executive-runtime migration refactors the loop in place. These tests do not
assert that the loop is *right*; they freeze what it observably *does* — the
decision sequence, how often it perceives per iteration, and how it terminates —
so that a slice which changes behaviour has to say so out loud.

Golden traces live in ``tests/plugin/goldens/control_loop``. Re-bless with::

    HERMES_UPDATE_GOLDENS=1 pytest tests/plugin/test_control_loop_characterization.py

and review the diff as part of the slice.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest

from plugin.agent.action import Action
from plugin.agent.controller import run_goal_closed_loop
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import RuntimeState
from plugin.executor.ghost import ExecResult
from plugin.experiments.logger import EventLogger
from plugin.perception.observation import AxNode, Observation

GOLDEN_DIR = Path(__file__).parent / "goldens" / "control_loop"


# ---------------------------------------------------------------- scripted UI


def _node(
    role: str,
    name: str,
    *,
    value: str = "",
    description: str = "",
    focused: bool = False,
    bbox: Tuple[float, float, float, float] = (0.0, 0.0, 120.0, 32.0),
) -> AxNode:
    attributes: Dict[str, Any] = {}
    if focused:
        attributes["focused"] = True
        attributes["AXFocused"] = True
    return AxNode(
        role=role,
        name=name,
        description=description,
        value=value or None,
        bbox=bbox,
        attributes=attributes,
    )


def _chat_list() -> List[AxNode]:
    return [
        _node("AXTextField", "Search", bbox=(10, 10, 220, 28)),
        _node("AXButton", "Chats", bbox=(10, 50, 220, 28)),
        _node("AXButton", "Aakash", bbox=(10, 90, 220, 44)),
        _node("AXButton", "ZarooratWala", bbox=(10, 140, 220, 44)),
    ]


def _search_focused(query: str = "") -> List[AxNode]:
    return [
        _node("AXTextField", "Search", value=query, focused=True, bbox=(10, 10, 220, 28)),
        _node("AXButton", "Chats", bbox=(10, 50, 220, 28)),
    ]


def _search_results(query: str, result: str) -> List[AxNode]:
    return [
        _node("AXTextField", "Search", value=query, focused=True, bbox=(10, 10, 220, 28)),
        _node("AXButton", result, bbox=(10, 90, 220, 44)),
    ]


def _conversation(contact: str) -> List[AxNode]:
    return [
        _node("AXStaticText", f"Messages in chat with {contact}", bbox=(300, 10, 500, 24)),
        _node("AXStaticText", "https://zarooratwala.com/charger", bbox=(320, 120, 400, 40)),
        _node("AXTextField", "Compose message", bbox=(300, 700, 500, 32)),
        _node("AXButton", "Voice call", bbox=(880, 10, 40, 24)),
        _node("AXButton", "Video call", bbox=(930, 10, 40, 24)),
    ]


def _context_menu(contact: str) -> List[AxNode]:
    return _conversation(contact) + [
        _node("AXMenuItem", "Reply", bbox=(400, 160, 160, 28)),
        _node("AXMenuItem", "Forward", bbox=(400, 190, 160, 28)),
        _node("AXMenuItem", "Copy", bbox=(400, 220, 160, 28)),
    ]


def _forward_picker(destination: str) -> List[AxNode]:
    return [
        _node("AXStaticText", "Forward to", bbox=(400, 60, 200, 24)),
        _node("AXTextField", "Search", focused=True, bbox=(400, 90, 240, 28)),
        _node("AXButton", destination, bbox=(400, 130, 240, 44)),
        _node("AXButton", "Aakash", bbox=(400, 180, 240, 44)),
    ]


def _ringing(contact: str) -> List[AxNode]:
    return [
        _node("AXStaticText", f"Calling {contact}", bbox=(400, 100, 200, 24)),
        _node("AXButton", "End call", bbox=(500, 600, 80, 40)),
    ]


Frame = Callable[[], List[AxNode]]
Transition = Callable[[Action, str], Optional[str]]


@dataclass
class ScriptedApp:
    """A tiny surface state machine driven by executed actions."""

    surfaces: Dict[str, Frame]
    transition: Transition
    surface: str
    app_name: str = "WhatsApp"
    observe_calls: int = 0
    executed: List[Action] = field(default_factory=list)
    execute_ok: bool = True

    def observe(self) -> Observation:
        self.observe_calls += 1
        nodes = self.surfaces[self.surface]()
        return Observation(
            timestamp=float(self.observe_calls),
            app_name=self.app_name,
            window_name=self.app_name,
            nodes=nodes,
            ax_tree=None,
            source="characterization",
            coverage=1.0,
        )

    def execute(self, step: Action) -> ExecResult:
        self.executed.append(step)
        if not self.execute_ok:
            return ExecResult(ok=False, backend="scripted", message=f"refused {step.action}")
        nxt = self.transition(step, self.surface)
        if nxt and nxt in self.surfaces:
            self.surface = nxt
        return ExecResult(ok=True, backend="scripted", message=f"ok {step.action}")


# ------------------------------------------------------------------- tracing


def _target_of(step: Dict[str, Any]) -> str:
    return str(step.get("semantic_target") or step.get("text") or "")


def _describe(step: Optional[Dict[str, Any]]) -> Dict[str, str]:
    step = step or {}
    return {
        "family": str(step.get("action_family") or ""),
        "action": str(step.get("action") or ""),
        "target": _target_of(step),
    }


def _trace_from_log(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Reduce a run log to the few facts the loop contract is made of."""
    per_iteration: Dict[int, Dict[str, Any]] = {}

    def slot(step: Any) -> Dict[str, Any]:
        try:
            key = int(step)
        except (TypeError, ValueError):
            key = 0
        if key not in per_iteration:
            per_iteration[key] = {
                "iteration": key,
                "observations": 0,
                "decisions": [],
                "executions": [],
                "outcomes": [],
            }
        return per_iteration[key]

    for event in events:
        kind = str(event.get("kind") or "")
        entry = slot(event.get("step"))
        if kind in {"observation", "post_observation"}:
            entry["observations"] += 1
        elif kind == "planner_decision":
            entry["decisions"].append(_describe(event.get("decision")))
        elif kind == "execution":
            entry["executions"].append(
                {**_describe(event.get("plan_step")), "ok": bool(event.get("ok"))}
            )
        elif kind == "transition_eval":
            attempt = event.get("attempt") or {}
            entry["outcomes"].append(str(attempt.get("outcome") or ""))

    iterations = [per_iteration[key] for key in sorted(per_iteration)]
    return {
        "iterations": iterations,
        "decision_families": [d["family"] for it in iterations for d in it["decisions"]],
    }


def _run_scenario(
    app: ScriptedApp,
    goal: Goal,
    tmp_path: Path,
    *,
    max_iterations: int = 8,
) -> Dict[str, Any]:
    log = EventLogger(tmp_path / "run.jsonl", also_console=False, run_id="characterization")
    runtime = RuntimeState()
    raised: Optional[BaseException] = None
    result = None
    try:
        result = run_goal_closed_loop(
            runtime,
            goal,
            observe=app.observe,
            execute=app,
            log=log,
            max_iterations=max_iterations,
            settle_s=0.0,
            wait_fn=lambda *_a, **_k: None,
        )
    except Exception as exc:  # the loop escaping is itself part of the contract
        raised = exc
    trace = _trace_from_log(log.read_all())
    if raised is not None:
        trace["result"] = {"raised": f"{type(raised).__name__}: {raised}"}
    else:
        trace["result"] = {
            "ok": bool(result.ok),
            "reason": str(result.reason or ""),
            "iterations": int(result.iterations or 0),
        }
    trace["executed"] = [
        {
            "action": step.action,
            "family": step.action_family,
            "target": step.semantic_target or step.text,
        }
        for step in app.executed
    ]
    trace["final_surface"] = app.surface
    return trace


def _assert_golden(name: str, trace: Dict[str, Any]) -> None:
    path = GOLDEN_DIR / f"{name}.json"
    rendered = json.dumps(trace, indent=2, sort_keys=True) + "\n"
    if os.getenv("HERMES_UPDATE_GOLDENS", "").strip() in {"1", "true", "yes"}:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        return
    assert path.is_file(), (
        f"missing golden {path}; re-bless with HERMES_UPDATE_GOLDENS=1 and review the diff"
    )
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert json.loads(rendered) == expected, (
        f"control-loop behaviour changed for {name}. If the change is intended, re-bless "
        f"with HERMES_UPDATE_GOLDENS=1 and explain the diff in the slice."
    )


# -------------------------------------------------------- scripted perceptor


def _message_text(messages: List[Any]) -> str:
    for message in reversed(messages or []):
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    return str(part.get("text") or "")
    return ""


def _read_screen(payload: Dict[str, Any]) -> Dict[str, str]:
    """Answer the screen-understanding question from the payload the loop sent."""
    goal = payload.get("goal") or {}
    evidence = payload.get("evidence") or {}
    labels = [
        str((entity or {}).get("label") or "").lower()
        for entity in (evidence.get("visible_entities") or [])
    ]

    def has(fragment: str) -> bool:
        return any(fragment in label for label in labels)

    contact = str(goal.get("contact") or "")
    destination = str(goal.get("target_contact") or "")
    kind = str(goal.get("kind") or "")

    if has("end call") or has("calling "):
        return {"surface": "call", "family": "observe", "target": ""}
    if has("forward to"):
        return {"surface": "forward_picker", "family": "select_forward_target", "target": destination}
    if has("forward") and has("reply"):
        return {"surface": "context_menu", "family": "forward_message", "target": "Forward"}
    if has("messages in chat with"):
        if kind == "whatsapp_forward_message":
            return {
                "surface": "conversation",
                "family": "select_content",
                "target": str(goal.get("link_query") or "link"),
            }
        return {"surface": "conversation", "family": "start_call", "target": "Voice call"}
    if destination and has(destination.lower()) and has("search"):
        return {"surface": "search_results", "family": "open_contact", "target": destination}
    if contact and has(contact.lower()) and has("search"):
        return {"surface": "search_results", "family": "open_contact", "target": contact}
    if has("chats"):
        return {"surface": "chat_list", "family": "type_query", "target": "Search"}
    return {"surface": "unknown", "family": "observe", "target": ""}


def _scripted_call_llm(**kwargs):
    """Deterministic stand-in for the perception model.

    Only the screen-understanding call is answered; every other consultation
    reports itself unavailable, which is the degraded path the loop already
    handles. The answer is derived from the payload the loop actually sent, so
    the real prompt-building and parsing code stays under test.
    """
    from types import SimpleNamespace

    text = _message_text(kwargs.get("messages") or [])
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        payload = None
    if not isinstance(payload, dict) or "screen" not in payload:
        raise RuntimeError("characterization harness answers screen understanding only")

    reading = _read_screen(payload)
    goal = payload.get("goal") or {}
    body = {
        "screen_type": reading["surface"],
        "active_surface": reading["surface"],
        "likely_next_family": reading["family"],
        "likely_next_target": reading["target"],
        "likely_next_text": str(goal.get("contact") or "") if reading["family"] == "type_query" else "",
        "confidence": 0.7,
        "avoid_families": [],
        "supporting_evidence": ["scripted characterization perceptor"],
        "contradictions": [],
        "needs_followup_observe": False,
    }
    message = SimpleNamespace(content=json.dumps(body), tool_calls=[])
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], usage=None, model="characterization")


# ------------------------------------------------------------------ fixtures


@pytest.fixture(autouse=True)
def deterministic_runtime(monkeypatch, tmp_path):
    """No network, no learned state carried between runs."""
    monkeypatch.setenv("HERMES_UNIFIED_COGNITION", "0")
    monkeypatch.setenv("HERMES_DECISION_LLM", "0")
    monkeypatch.setenv("HERMES_DECISION_CONSULTATION", "0")
    monkeypatch.setenv("HERMES_PERCEPTOR_RECORD_DIR", "")

    from agent import auxiliary_client

    monkeypatch.setattr(auxiliary_client, "call_llm", _scripted_call_llm)
    token = auxiliary_client.set_runtime_main(
        "openrouter",
        "characterization/model",
        base_url="https://openrouter.ai/api/v1",
    )

    from plugin.agent import decision as decision_module
    from plugin.agent import trajectory_memory as trajectory_module
    from plugin.agent.policy import events as policy_events
    from plugin.agent.policy import prior as prior_module
    from plugin.agent.resolver import memory as resolver_memory

    store = tmp_path / "stores"
    store.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(trajectory_module, "DEFAULT_TRAJECTORY_MEMORY_PATH", store / "trajectory.jsonl")
    monkeypatch.setattr(resolver_memory, "DEFAULT_MEMORY_PATH", store / "resolution.jsonl")
    monkeypatch.setattr(policy_events, "DEFAULT_EVENTS", store / "policy_events.jsonl")
    monkeypatch.setattr(prior_module, "DEFAULT_STORE", store / "policy_prior.json")
    monkeypatch.setattr(trajectory_module, "_DEFAULT_TRAJECTORY_MEMORY", None, raising=False)
    monkeypatch.setattr(resolver_memory, "_DEFAULT_MEMORY", None, raising=False)
    monkeypatch.setattr(decision_module, "_DEFAULT_ENGINE", None, raising=False)
    yield
    auxiliary_client.reset_runtime_main(token)
    decision_module._DEFAULT_ENGINE = None
    trajectory_module._DEFAULT_TRAJECTORY_MEMORY = None
    resolver_memory._DEFAULT_MEMORY = None


# ----------------------------------------------------------------- scenarios


def _forward_app() -> ScriptedApp:
    surfaces: Dict[str, Frame] = {
        "chat_list": _chat_list,
        "search": lambda: _search_focused(""),
        "search_typed": lambda: _search_results("ZarooratWala", "ZarooratWala"),
        "conversation": lambda: _conversation("ZarooratWala"),
        "context_menu": lambda: _context_menu("ZarooratWala"),
        "forward_picker": lambda: _forward_picker("Pallavi"),
        "sent": lambda: _conversation("Pallavi"),
    }

    def transition(step: Action, surface: str) -> Optional[str]:
        action = (step.action or "").lower()
        target = (step.semantic_target or "").lower()
        if action == "type":
            return "search_typed"
        if action == "contextclick":
            return "context_menu"
        if action != "click":
            return None
        if target == "search":
            return "search"
        if surface == "context_menu" and target == "forward":
            return "forward_picker"
        if surface == "forward_picker" and target in {"pallavi", "send"}:
            return "sent"
        if "zarooratwala" in target:
            return "conversation"
        return None

    return ScriptedApp(surfaces=surfaces, transition=transition, surface="chat_list")


def _call_app() -> ScriptedApp:
    surfaces: Dict[str, Frame] = {
        "chat_list": _chat_list,
        "search": lambda: _search_focused(""),
        "search_typed": lambda: _search_results("Pallavi", "Pallavi"),
        "conversation": lambda: _conversation("Pallavi"),
        "ringing": lambda: _ringing("Pallavi"),
    }

    def transition(step: Action, surface: str) -> Optional[str]:
        action = (step.action or "").lower()
        target = (step.semantic_target or "").lower()
        if action == "type":
            return "search_typed"
        if action != "click":
            return None
        if target == "search":
            return "search"
        if target == "pallavi":
            return "conversation"
        if target in {"call", "voice call", "audio call"}:
            return "ringing"
        return None

    return ScriptedApp(surfaces=surfaces, transition=transition, surface="chat_list")


def _frozen_app() -> ScriptedApp:
    """Every action is accepted and nothing ever changes."""
    return ScriptedApp(
        surfaces={"chat_list": _chat_list},
        transition=lambda _step, _surface: None,
        surface="chat_list",
    )


def _oscillating_app() -> ScriptedApp:
    surfaces: Dict[str, Frame] = {
        "chat_list": _chat_list,
        "search": lambda: _search_focused(""),
    }

    def transition(_step: Action, surface: str) -> Optional[str]:
        return "search" if surface == "chat_list" else "chat_list"

    return ScriptedApp(surfaces=surfaces, transition=transition, surface="chat_list")


def _call_goal() -> Goal:
    return Goal(kind="whatsapp_voice_call", contact="Pallavi", require_contact_in_call=False)


def _forward_goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="ZarooratWala",
        target_contact="Pallavi",
        link_query="charger",
        prompt="Find the charger link from ZarooratWala on WhatsApp and forward it to Pallavi",
    )


def test_goal_already_satisfied(tmp_path):
    """The one scenario that terminates successfully today — guard it hardest."""
    app = _call_app()
    app.surface = "ringing"
    trace = _run_scenario(app, _call_goal(), tmp_path, max_iterations=4)
    assert trace["result"].get("ok") is True, trace["result"]
    _assert_golden("goal_satisfied", trace)


def test_happy_voice_call_path(tmp_path):
    app = _call_app()
    trace = _run_scenario(app, _call_goal(), tmp_path)
    _assert_golden("happy_voice_call", trace)


def test_happy_forward_path(tmp_path):
    app = _forward_app()
    trace = _run_scenario(app, _forward_goal(), tmp_path)
    _assert_golden("happy_forward", trace)


def test_no_progress_watchdog(tmp_path):
    app = _frozen_app()
    trace = _run_scenario(app, _call_goal(), tmp_path, max_iterations=6)
    _assert_golden("no_progress", trace)


def test_semantic_repeat_under_frozen_forward(tmp_path):
    app = _frozen_app()
    trace = _run_scenario(app, _forward_goal(), tmp_path, max_iterations=6)
    _assert_golden("semantic_repeat", trace)


def test_execute_failure(tmp_path):
    app = _call_app()
    app.execute_ok = False
    trace = _run_scenario(app, _call_goal(), tmp_path, max_iterations=6)
    _assert_golden("execute_failure", trace)


def test_oscillation(tmp_path):
    app = _oscillating_app()
    trace = _run_scenario(app, _call_goal(), tmp_path, max_iterations=6)
    _assert_golden("oscillation", trace)


def test_budget_exhaustion(tmp_path):
    app = _forward_app()
    trace = _run_scenario(app, _forward_goal(), tmp_path, max_iterations=2)
    _assert_golden("budget_exhaustion", trace)


def test_meta_perception_gate_skips_a_reperceive_without_crashing(tmp_path, monkeypatch):
    """With HERMES_META_PERCEPTION on, a static world triggers a skip.

    This is not a golden — the whole point of the flag is that it changes the
    trace. It only asserts that the meta-driven path runs to termination and
    that the executive actually elected to skip a re-perceive at least once
    (i.e. the gate is wired, not dead code).
    """
    monkeypatch.setenv("HERMES_META_PERCEPTION", "1")
    app = _frozen_app()
    log = EventLogger(tmp_path / "meta.jsonl", also_console=False, run_id="meta")
    runtime = RuntimeState()
    result = run_goal_closed_loop(
        runtime,
        _call_goal(),
        observe=app.observe,
        execute=app,
        log=log,
        max_iterations=6,
        settle_s=0.0,
        wait_fn=lambda *_a, **_k: None,
    )
    assert result is not None
    events = log.read_all()
    judged = [e for e in events if e.get("kind") == "executive_judgement"]
    skipped = [e for e in events if e.get("kind") == "perception_skipped"]
    assert judged, "executive judgement should be recorded every iteration"
    assert skipped, "a static world with the gate on should skip at least one re-perceive"


def test_executive_judgement_is_recorded_with_gate_off(tmp_path):
    """The judgement is always-on even when it does not drive perception."""
    app = _call_app()
    log = EventLogger(tmp_path / "judge.jsonl", also_console=False, run_id="judge")
    runtime = RuntimeState()
    run_goal_closed_loop(
        runtime,
        _call_goal(),
        observe=app.observe,
        execute=app,
        log=log,
        max_iterations=4,
        settle_s=0.0,
        wait_fn=lambda *_a, **_k: None,
    )
    events = log.read_all()
    judged = [e for e in events if e.get("kind") == "executive_judgement"]
    assert judged, "executive judgement should be recorded every iteration"
    first = judged[0]
    assert "sufficiency" in first and "meta_action" in first
    assert first["meta_perception_enabled"] is False
