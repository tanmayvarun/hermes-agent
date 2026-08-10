"""Unit tests for evidence / hypothesis / belief types."""

from __future__ import annotations

import time
import json
from types import SimpleNamespace

from plugin.perception.evidence import Evidence, EvidenceRef, ObservationEvent
from plugin.perception.hypothesis import EntityHypothesis, hypothesis_key
from plugin.perception.fusion.engine import FusionEngine
from plugin.perception.fusion.referee import FusionReferee
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


def test_assembly_keeps_nodes_from_both_sources_without_rivalry():
    """Assembly concatenates; it does not score agreement between sources.

    Exact duplicates (same role/name/bbox) collapse once; distinct labels from
    either source all survive. No agreement threshold, no preferred source.
    """
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
        [
            bund("pyobjc_ax", ["Search", "Pallavi"]),
            bund("screen2ax", ["Search", "Kulvinder Ji"]),
        ],
        app="WhatsApp",
    )
    labels = {e.label for e in frame.entities}
    assert labels == {"Search", "Pallavi", "Kulvinder Ji"}
    assert frame.report.agreement is None
    assert frame.report.needs_reobserve is False
    assert frame.report.meta["fusion_mode"] == "assemble"
    obs = frame.to_observation()
    assert {n.name for n in obs.nodes} == labels
    assert obs.meta.get("fusion", {}).get("fusion_mode") == "assemble"


def test_assembly_never_calls_the_referee(monkeypatch):
    """Multi-source assemble must not ask an LLM which source is true."""
    from plugin.perception.fusion.referee import FusionReferee
    from plugin.perception.observation import AxNode, Observation
    from plugin.perception.sources.base import ObservationBundle

    def fail_if_called(*_a, **_k):
        raise AssertionError("fusion referee must not run on the assemble path")

    monkeypatch.setattr(FusionReferee, "decide", fail_if_called)

    engine = FusionEngine()
    bundles = [
        ObservationBundle(
            source_id="pyobjc_ax",
            observation=Observation(
                timestamp=0,
                app_name="WhatsApp",
                window_name="Main",
                nodes=[AxNode(role="AXSearchField", name="Search", bbox=(10.0, 10.0, 120.0, 24.0))],
                source="pyobjc_ax",
                coverage=1.0,
            ),
            coverage_self=1.0,
        ),
        ObservationBundle(
            source_id="screen2ax",
            observation=Observation(
                timestamp=0,
                app_name="WhatsApp",
                window_name="Main",
                nodes=[AxNode(role="AXStaticText", name="Kulvinder Ji", bbox=(10.0, 40.0, 200.0, 28.0))],
                source="screen2ax",
                coverage=0.9,
            ),
            coverage_self=0.9,
        ),
    ]
    frame = engine.fuse_bundles(bundles, app="WhatsApp")
    assert len(frame.entities) == 2
    assert "llm_referee" not in frame.report.meta


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


def test_assembly_skips_degraded_empty_stubs_but_keeps_healthy_nodes():
    """Timeout/empty stubs must not erase a healthy source's nodes."""
    from plugin.perception.observation import AxNode, Observation
    from plugin.perception.sources.base import ObservationBundle

    healthy = ObservationBundle(
        source_id="pyobjc_ax",
        observation=Observation(
            timestamp=0,
            app_name="WhatsApp",
            window_name="Main",
            nodes=[
                AxNode(role="AXSearchField", name="Search", bbox=(10.0, 10.0, 140.0, 28.0)),
                AxNode(role="AXStaticText", name="Kulvinder Ji", bbox=(10.0, 40.0, 200.0, 28.0)),
            ],
            source="pyobjc_ax",
        ),
        coverage_self=1.0,
        degraded=False,
    )
    degraded = ObservationBundle(
        source_id="macapptree",
        observation=Observation(
            timestamp=0,
            app_name="WhatsApp",
            window_name="Main",
            nodes=[],
            source="macapptree",
            coverage=0.0,
            degraded=True,
        ),
        coverage_self=0.0,
        degraded=True,
    )

    frame = FusionEngine().fuse_bundles([healthy, degraded], app="WhatsApp")
    assert len(frame.entities) == 2
    assert frame.report.agreement is None
    assert frame.report.needs_reobserve is False
    assert frame.report.meta["fusion_mode"] == "assemble"
    assert frame.report.meta["healthy_source_count"] == 1
    assert "macapptree" in frame.report.meta["ignored_sources"]
    assert "llm_referee" not in frame.report.meta


def test_assembly_uses_raw_nodes_not_interpreter_output(monkeypatch):
    """Even if an interpreter would return nothing, the raw nodes are kept.

    Rival fusion used to interpret then fall back; assembly reads the nodes
    the source already produced.
    """
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
    assert frame.entities[0].role == "AXButton"
