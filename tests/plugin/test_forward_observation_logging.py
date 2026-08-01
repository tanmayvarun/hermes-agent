from __future__ import annotations

import json

import pytest

from plugin.experiments.live_observe import format_raw_observation_trace
from plugin.agent.perception_cycle import apply_observation
from plugin.agent.reasoning_consultation import ReasoningConsultationResult
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import RuntimeState
from plugin.perception.fusion.fuse import observe_fused_frame
from plugin.perception.observation import AxNode, Observation
from plugin.perception.sources.base import ObservationBundle, timed_observe


def test_raw_observation_trace_includes_message_like_rows():
    obs = Observation(
        timestamp=0.0,
        app_name="WhatsApp",
        window_name="Kulvinder Ji",
        source="pyobjc_ax",
        coverage=0.91,
        degraded=False,
        nodes=[
            AxNode(role="AXStaticText", name="Your message, Link, https://example.com", description="", value=None),
            AxNode(role="AXStaticText", name="message, Thanks will see if it works fine", description="", value=None),
            AxNode(role="AXButton", name="Search", description="", value="Kulvinder"),
        ],
    )

    trace = format_raw_observation_trace(obs, max_nodes=3, max_message_like=2)

    assert "app='WhatsApp'" in trace
    assert "window='Kulvinder Ji'" in trace
    assert "message_like=" in trace
    assert "Your message, Link, https://example.com" in trace
    assert "message, Thanks will see if it works fine" in trace
    assert "raw_nodes=" in trace
    assert "role=AXButton" in trace


def test_timed_observe_attaches_raw_summary():
    def _fn(_app: str) -> Observation:
        return Observation(
            timestamp=0.0,
            app_name="WhatsApp",
            window_name="Chat",
            source="dummy",
            coverage=1.0,
            degraded=False,
            nodes=[
                AxNode(role="AXStaticText", name="message, Hello there", description="", value=None),
            ],
        )

    bundle = timed_observe("dummy", _fn, "WhatsApp")

    assert "raw_summary" in bundle.raw_meta
    assert "message, Hello there" in bundle.raw_meta["raw_summary"]


def test_observe_fused_frame_traces_each_source_bundle():
    class _Source:
        def __init__(self, source_id: str, label: str) -> None:
            self.source_id = source_id
            self._label = label

        def observe(self, app: str) -> ObservationBundle:
            obs = Observation(
                timestamp=0.0,
                app_name=app,
                window_name="Chat",
                source=self.source_id,
                coverage=1.0,
                degraded=False,
                nodes=[AxNode(role="AXStaticText", name=self._label, description="", value=None)],
            )
            return ObservationBundle(
                source_id=self.source_id,
                observation=obs,
                latency_ms=1.0,
                coverage_self=1.0,
                degraded=False,
                raw_meta={"raw_summary": f"raw:{self._label}"},
            )

    traces: list[tuple[str, str]] = []

    def _trace(source_id: str, bundle: ObservationBundle) -> None:
        traces.append((source_id, bundle.raw_meta.get("raw_summary", "")))

    frame = observe_fused_frame(
        "WhatsApp",
        sources=[_Source("pyobjc_ax", "message, one"), _Source("macapptree", "message, two")],
        secondary=True,
        source_timeout_s=2.0,
        trace_bundle=_trace,
    )

    assert len(frame.entities) >= 0
    assert traces == [("pyobjc_ax", "raw:message, one"), ("macapptree", "raw:message, two")]


def test_apply_observation_emits_raw_and_fused_trace():
    def _fake_consult_reasoning(task, messages, **kwargs):
        call_kwargs = kwargs.get("call_kwargs") or {}
        payload = {
            "screen_type": "conversation",
            "active_surface": "conversation",
            "likely_next_family": "open_contact",
            "likely_next_target": "Kulvinder Ji",
            "likely_next_text": "",
            "confidence": 0.82,
            "avoid_families": ["type_query"],
            "supporting_evidence": ["stubbed perception for logging test"],
            "contradictions": [],
            "needs_followup_observe": False,
        }
        return ReasoningConsultationResult(
            task=task,
            messages=[dict(msg) for msg in messages],
            raw_response=json.dumps(payload),
            parsed=dict(payload),
            confidence=float(payload["confidence"]),
            abstained=False,
            reason="stub",
            timeout_s=float(call_kwargs.get("timeout") or 0.0),
            max_tokens=int(call_kwargs.get("max_tokens") or 0),
            provider=str(call_kwargs.get("provider") or ""),
            model=str(call_kwargs.get("model") or ""),
            base_url=str(call_kwargs.get("base_url") or ""),
        )

    import plugin.agent.perception_synthesis as perception_synthesis

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(perception_synthesis, "consult_reasoning", _fake_consult_reasoning)
    runtime = RuntimeState(active_task="test")
    runtime.world_model.active_app = "WhatsApp"
    goal = Goal(kind="whatsapp_forward_message", contact="Pallavi")
    obs = Observation(
        timestamp=0.0,
        app_name="WhatsApp",
        window_name="Kulvinder Ji",
        source="pyobjc_ax",
        coverage=1.0,
        degraded=False,
        nodes=[
            AxNode(role="AXStaticText", name="message, zarooratwala link", description="", value=None),
        ],
    )
    events: list[tuple[str, dict]] = []

    def _log_fn(*, phase: str, payload: dict, status: str = "ok", iteration: int = 0) -> None:
        events.append((phase, payload))

    snap = apply_observation(runtime, goal, obs, action_label="observe", log_fn=_log_fn, iteration=3)

    assert snap.observation is obs
    phases = [phase for phase, _ in events]
    assert "observation_raw" in phases
    assert "observation_fused" in phases
    raw_payload = next(payload for phase, payload in events if phase == "observation_raw")
    fused_payload = next(payload for phase, payload in events if phase == "observation_fused")
    assert "raw_trace" in raw_payload
    assert "zarooratwala link" in raw_payload["raw_trace"]
    assert fused_payload["action_label"] == "observe"
    monkeypatch.undo()


def test_apply_observation_emits_human_readable_perception_summary():
    def _fake_consult_reasoning(task, messages, **kwargs):
        call_kwargs = kwargs.get("call_kwargs") or {}
        payload = {
            "screen_type": "conversation",
            "active_surface": "conversation",
            "likely_next_family": "open_contact",
            "likely_next_target": "Kulvinder Ji",
            "likely_next_text": "",
            "confidence": 0.82,
            "avoid_families": ["type_query"],
            "supporting_evidence": ["stubbed perception for logging test"],
            "contradictions": [],
            "needs_followup_observe": False,
        }
        return ReasoningConsultationResult(
            task=task,
            messages=[dict(msg) for msg in messages],
            raw_response=json.dumps(payload),
            parsed=dict(payload),
            confidence=float(payload["confidence"]),
            abstained=False,
            reason="stub",
            timeout_s=float(call_kwargs.get("timeout") or 0.0),
            max_tokens=int(call_kwargs.get("max_tokens") or 0),
            provider=str(call_kwargs.get("provider") or ""),
            model=str(call_kwargs.get("model") or ""),
            base_url=str(call_kwargs.get("base_url") or ""),
        )

    import plugin.agent.perception_synthesis as perception_synthesis

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(perception_synthesis, "consult_reasoning", _fake_consult_reasoning)
    runtime = RuntimeState(active_task="test")
    runtime.world_model.active_app = "WhatsApp"
    goal = Goal(kind="whatsapp_forward_message", contact="Pallavi")
    obs = Observation(
        timestamp=0.0,
        app_name="WhatsApp",
        window_name="Kulvinder Ji",
        source="pyobjc_ax",
        coverage=1.0,
        degraded=False,
        nodes=[
            AxNode(role="AXStaticText", name="message, zarooratwala link", description="", value=None),
        ],
    )
    events: list[tuple[str, dict]] = []

    def _log_fn(*, phase: str, payload: dict, status: str = "ok", iteration: int = 0) -> None:
        events.append((phase, payload))

    snap = apply_observation(runtime, goal, obs, action_label="observe", log_fn=_log_fn, iteration=4)

    assert snap.observation is obs
    phases = [phase for phase, _ in events]
    assert "perception_summary" in phases
    summary_payload = next(payload for phase, payload in events if phase == "perception_summary")
    assert "message" in summary_payload
    assert "detail" in summary_payload
    assert "text" in summary_payload
    assert "confidence" in summary_payload
    assert "screen_type" in summary_payload
    assert isinstance(summary_payload["text"], str)
    monkeypatch.undo()
