"""Unit tests for evidence / hypothesis / belief types."""

from __future__ import annotations

import time
import json
from types import SimpleNamespace

from plugin.perception.evidence import Evidence, EvidenceRef, ObservationEvent
from plugin.perception.hypothesis import EntityHypothesis, hypothesis_key
from plugin.perception.fusion.engine import FusionEngine
from plugin.perception.fusion.referee import FusionReferee, FusionRefereeDecision
from plugin.worldmodel.belief import Belief, belief_from_evidence


def test_observation_event_from_bundle_like():
    class Obs:
        timestamp = 1.0
        app_name = "WhatsApp"
        window_name = "WhatsApp"
        nodes = [1, 2]
        screenshot_path = None
        meta = {}
        source = "pyobjc_ax"

    class Bundle:
        source_id = "pyobjc_ax"
        observation = Obs()
        latency_ms = 12.5
        degraded = False
        coverage_self = 0.9

    ev = ObservationEvent.from_bundle(Bundle())
    assert ev.sensor == "pyobjc_ax"
    assert ev.payload["node_count"] == 2
    assert ev.confidence >= 0.9
    assert "sensor" in ev.to_dict()


def test_hypothesis_key_stable():
    k1 = hypothesis_key("AXButton", "Search", (100.0, 200.0, 40.0, 20.0))
    k2 = hypothesis_key("AXButton", "Search", (105.0, 208.0, 40.0, 20.0))
    assert k1 == k2
    h = EntityHypothesis.make(role="AXButton", label="Search", bounds=(100, 200, 40, 20), source="ax", confidence=0.9)
    assert h.key == k1
    assert h.to_dict()["label"] == "Search"


def test_belief_blend_agree_and_conflict():
    a = Belief(value=True, confidence=0.8)
    b = a.blend(True, 0.7, source="macapptree", prop="visible")
    assert b.value is True
    assert b.confidence >= a.confidence

    c = Belief(value=True, confidence=0.6)
    d = c.blend(False, 0.9, source="vision", prop="visible")
    assert d.value is False
    assert d.confidence < 0.9
    assert len(d.evidence) >= 1


def test_belief_from_evidence():
    ev = Evidence(entity_key="k", property="label", value="Pallavi", confidence=0.95, source="pyobjc_ax")
    b = belief_from_evidence(ev)
    assert b.value == "Pallavi"
    assert b.confidence == 0.95
    ref = EvidenceRef.from_evidence(ev)
    assert ref.source == "pyobjc_ax"


def test_fusion_engine_merges_dual_ax_hypotheses():
    from plugin.perception.fusion.engine import FusionEngine
    from plugin.perception.observation import AxNode, Observation
    from plugin.perception.sources.base import ObservationBundle

    def bund(sid, labels):
        nodes = [
            AxNode(role="AXButton", name=n, bbox=(10.0, 20.0 + i * 30, 100.0, 20.0))
            for i, n in enumerate(labels)
        ]
        return ObservationBundle(
            source_id=sid,
            observation=Observation(timestamp=0, app_name="W", window_name="", nodes=nodes, source=sid),
            coverage_self=0.9,
        )

    frame = FusionEngine().fuse_bundles(
        [bund("pyobjc_ax", ["Search", "Pallavi"]), bund("macapptree", ["Search", "Pallavi"])],
        app="WhatsApp",
    )
    assert len(frame.entities) == 2
    assert frame.report.agreement >= 0.9
    obs = frame.to_observation()
    assert len(obs.nodes) == 2
    wm_patch_entities = obs.meta.get("fusion", {})
    assert "agreement" in wm_patch_entities


def test_ingest_preserves_beliefs_and_soft_keeps():
    from plugin.perception.fusion.engine import FusionEngine
    from plugin.perception.observation import AxNode, Observation
    from plugin.perception.sources.base import ObservationBundle
    from plugin.worldmodel.model import WorldModel

    nodes = [AxNode(role="AXButton", name="Search", bbox=(10, 20, 100, 20))]
    b = ObservationBundle(
        source_id="pyobjc_ax",
        observation=Observation(timestamp=0, app_name="W", window_name="", nodes=nodes, source="pyobjc_ax"),
        coverage_self=1.0,
    )
    frame = FusionEngine().fuse_bundles([b], app="W")
    wm = WorldModel()
    patch = wm.ingest_fused_frame(frame)
    assert patch.worldview_score
    assert any(e.beliefs for e in wm.entities.values())
    # Second frame empty-ish — soft keep
    empty = ObservationBundle(
        source_id="pyobjc_ax",
        observation=Observation(timestamp=1, app_name="W", window_name="", nodes=[], source="pyobjc_ax"),
        coverage_self=0.0,
        degraded=True,
    )
    frame2 = FusionEngine().fuse_bundles([empty], app="W")
    wm.ingest_fused_frame(frame2)
    # Search may still be hypothesized for a few miss frames
    assert wm.last_worldview_score is not None


def test_fusion_referee_uses_live_main_runtime(monkeypatch):
    from agent import auxiliary_client

    seen = {}

    def fake_call_llm(**kwargs):
        seen["main_runtime"] = kwargs.get("main_runtime")
        seen["messages"] = kwargs.get("messages")
        message = SimpleNamespace(
            content=json.dumps(
                {
                    "action": "prefer_source",
                    "preferred_source_id": "pyobjc_ax",
                    "confidence": 0.91,
                    "reason": "pyobjc_ax has the richest usable structure",
                    "should_reobserve": False,
                }
            ),
            tool_calls=[],
        )
        choice = SimpleNamespace(message=message, finish_reason="stop")
        return SimpleNamespace(choices=[choice], usage=None, model="fake")

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)
    token = auxiliary_client.set_runtime_main(
        "ollama-remote",
        "qwen2.5:32b",
        base_url="http://ollama.test/v1",
    )
    try:
        decision = FusionReferee().decide(
            {
                "app": "WhatsApp",
                "window": "Main",
                "deterministic": {"entity_count": 0, "agreement": 0.0, "needs_reobserve": True},
                "sources": [
                    {
                        "source_id": "pyobjc_ax",
                        "node_count": 241,
                        "hypothesis_count": 219,
                        "coverage": 1.0,
                        "degraded": False,
                        "latency_ms": 442.0,
                        "top_labels": ["Search", "Kulvinder Ji"],
                        "top_roles": ["AXSearchField", "AXStaticText"],
                        "sample_nodes": [{"role": "AXSearchField", "label": "Search"}],
                    }
                ],
            }
        )
        assert decision.action == "prefer_source"
        assert decision.preferred_source_id == "pyobjc_ax"
        assert seen["main_runtime"] == {
            "provider": "ollama-remote",
            "model": "qwen2.5:32b",
            "base_url": "http://ollama.test/v1",
            "api_key": "",
            "api_mode": "",
            "auth_mode": "",
        }
        assert seen["messages"]
    finally:
        auxiliary_client.reset_runtime_main(token)


def test_fusion_engine_can_prefer_rich_source_when_deterministic_fusion_collapses(monkeypatch):
    from plugin.perception.observation import AxNode, Observation
    from plugin.perception.sources.base import ObservationBundle

    engine = FusionEngine()
    original_core = engine._fuse_hypotheses_core

    def fake_decide(self, payload):
        return FusionRefereeDecision(
            action="prefer_source",
            preferred_source_id="pyobjc_ax",
            confidence=0.94,
            reason="prefer the richer source",
            should_reobserve=False,
        )

    def fake_core(self, hyps, **kwargs):
        sources = kwargs.get("sources") or []
        if len(sources) > 1:
            return original_core(
                [],
                app=kwargs.get("app", ""),
                window=kwargs.get("window", ""),
                screenshot=kwargs.get("screenshot"),
                sources=sources,
                events=kwargs.get("events"),
                latencies_ms=kwargs.get("latencies_ms"),
                node_counts=kwargs.get("node_counts"),
                hypothesis_counts=kwargs.get("hypothesis_counts"),
            )
        return original_core(hyps, **kwargs)

    monkeypatch.setattr(FusionReferee, "decide", fake_decide)
    monkeypatch.setattr(FusionEngine, "_fuse_hypotheses_core", fake_core)

    rich_nodes = [
        AxNode(role="AXSearchField", name="Search", bbox=(10.0, 10.0, 140.0, 28.0)),
        AxNode(role="AXStaticText", name="Kulvinder Ji", bbox=(10.0, 40.0, 200.0, 28.0)),
    ]
    bundles = [
        ObservationBundle(
            source_id="pyobjc_ax",
            observation=Observation(timestamp=0, app_name="WhatsApp", window_name="Main", nodes=rich_nodes, source="pyobjc_ax"),
            coverage_self=1.0,
            degraded=False,
        ),
        ObservationBundle(
            source_id="macapptree",
            observation=Observation(timestamp=0, app_name="WhatsApp", window_name="Main", nodes=[], source="macapptree"),
            coverage_self=0.0,
            degraded=True,
        ),
    ]

    frame = engine.fuse_bundles(bundles, app="WhatsApp")
    assert len(frame.entities) == 2
    assert frame.report.primary_source == "pyobjc_ax"
    assert frame.report.meta["llm_referee"]["action"] == "prefer_source"
    assert frame.report.meta["llm_referee"]["preferred_source_id"] == "pyobjc_ax"


def test_fusion_engine_preserves_non_empty_source_when_interpreter_returns_empty(monkeypatch):
    from plugin.perception.interpreters.ax_tree import AxTreeInterpreter
    from plugin.perception.observation import AxNode, Observation
    from plugin.perception.sources.base import ObservationBundle

    engine = FusionEngine()
    monkeypatch.setattr(AxTreeInterpreter, "interpret", lambda self, bundle: [])

    bundle = ObservationBundle(
        source_id="pyobjc_ax",
        observation=Observation(
            timestamp=0,
            app_name="WhatsApp",
            window_name="Main",
            nodes=[AxNode(role="AXButton", name="", description="", value=None, bbox=(10.0, 20.0, 100.0, 24.0))],
            source="pyobjc_ax",
        ),
        coverage_self=1.0,
        degraded=False,
    )

    frame = engine.fuse_bundles([bundle], app="WhatsApp")
    assert len(frame.entities) == 1
    assert frame.entities[0].sources == ["pyobjc_ax"]
    assert frame.entities[0].beliefs["fallback_source"].value == "pyobjc_ax"
