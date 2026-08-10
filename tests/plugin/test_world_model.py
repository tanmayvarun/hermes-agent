"""Plugin World Model POC tests — offline fixtures, no Accessibility required."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from plugin.agent.decision import DecisionEngine
from plugin.agent.goal import Goal, evaluate_goal
from plugin.agent.runtime.recovery import (
    maybe_cleanup_for_storage_pressure,
    _load_disk_cleanup_library,
    perform_storage_cleanup,
    recover_after_unexpected,
)
from plugin.agent.runtime.state import RuntimeState
from plugin.agent.apps.whatsapp import WhatsAppOverlay
from plugin.experiments.harness import FIXTURES, run_scorecard
from plugin.perception.observation import AxNode, Observation
from plugin.perception.macos.accessibility.observer import FixtureObserver
from plugin.perception.macos.accessibility.tree_parse import count_nodes, parse_macapptree_node
from plugin.worldmodel._no_llm import FORBIDDEN, assert_no_llm_imports
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.entities.identity import IdentityTracker
from plugin.worldmodel.entities.normalize import entities_from_observation
from plugin.worldmodel.model import WorldModel
from plugin.worldmodel.persistence.store import WorldStore


def test_fixture_observe_summary():
    obs = FixtureObserver(FIXTURES / "whatsapp_conversation.json").observe()
    assert obs.app_name == "WhatsApp"
    assert len(obs.nodes) >= 5
    yaml = obs.summary_yaml()
    assert "WhatsApp" in yaml
    assert "Nodes:" in yaml


def test_entity_normalize_and_identity_retention():
    obs = FixtureObserver(FIXTURES / "whatsapp_conversation.json").observe()
    ents = entities_from_observation(obs)
    assert any(e.semantic_role == "Search" for e in ents)
    tracker = IdentityTracker()
    tracker.seed(ents)
    # scroll churn
    for n in obs.nodes:
        x, y, w, h = n.bbox
        n.bbox = (x, y + 8, w, h)
    ents2 = entities_from_observation(obs)
    result = tracker.update(ents2)
    assert result.retention >= 0.80


def test_screen_sequence_and_nav_graph():
    wm = WorldModel()
    labels = []
    for name, action in [
        ("whatsapp_conversation.json", None),
        ("whatsapp_search.json", "open_search"),
        ("whatsapp_chat.json", "open_chat"),
        ("whatsapp_call.json", "call"),
    ]:
        patch = wm.ingest(FixtureObserver(FIXTURES / name).observe(), action=action)
        labels.append(patch.screen_label)
    assert labels[0] == "conversation"
    assert labels[1] == "search"
    assert labels[2] in {"chat", "conversation"}
    assert labels[3] == "call"
    assert len(wm.transitions.transitions) >= 3
    mermaid = wm.navigation_graph.to_mermaid()
    assert "flowchart" in mermaid


def test_planner_whatsapp_call():
    """Without unified, decide Observes — no legacy open_contact fallthrough."""
    from plugin.agent.runtime.state import ExecutionState

    wm = WorldModel()
    wm.ingest(FixtureObserver(FIXTURES / "whatsapp_conversation.json").observe())
    a = DecisionEngine().define_action_step(
        Goal(kind="whatsapp_voice_call", contact="Pallavi"),
        wm,
        ExecutionState(),
    )
    assert a is not None
    assert a.action_family == "observe"
    assert "unified_declined_no_legacy_fallthrough" in (a.rationale or "")


def test_recovery_replans_without_restart(monkeypatch):
    from plugin.agent import perception_cycle

    monkeypatch.setattr(perception_cycle, "synthesize_perception", lambda *args, **kwargs: None)
    rt = RuntimeState(active_task="Call Pallavi on WhatsApp")
    rt.world_model.ingest(FixtureObserver(FIXTURES / "whatsapp_conversation.json").observe())
    unexpected = FixtureObserver(FIXTURES / "whatsapp_call.json").observe()
    result = recover_after_unexpected(rt, unexpected, goal=rt.active_task)
    assert result.recovered
    assert result.new_action is None or result.new_action.action in {"Click", "Type", "Observe"}
    assert rt.execution_state.step == 0


def test_storage_pressure_cleanup_triggers_once(monkeypatch):
    rt = RuntimeState(active_task="Use WhatsApp")
    cleanup_calls = []

    monkeypatch.setattr(
        "plugin.agent.runtime.recovery.perform_storage_cleanup",
        lambda *, reason, evidence, analysis=None: cleanup_calls.append((reason, tuple(evidence))) or type(
            "R",
            (),
            {
                "triggered": True,
                "reason": reason,
                "evidence": list(evidence),
                "disk_cleanup": {"deleted": 3, "empty_dirs": 1, "freed": 1024},
                "environments_cleaned": 2,
                "to_dict": lambda self: {
                    "triggered": True,
                    "reason": reason,
                    "evidence": list(evidence),
                    "disk_cleanup": {"deleted": 3, "empty_dirs": 1, "freed": 1024},
                    "environments_cleaned": 2,
                },
            },
        )(),
    )

    first = maybe_cleanup_for_storage_pressure(
        rt,
        view={"screen": "CONVERSATION", "dialogs": ["Storage full"], "search_query": ""},
        features={},
        reason_hint="storage full dialog",
    )
    second = maybe_cleanup_for_storage_pressure(
        rt,
        view={"screen": "CONVERSATION", "dialogs": ["Storage full"], "search_query": ""},
        features={},
        reason_hint="storage full dialog",
    )
    assert first is not None
    assert first.triggered
    assert second is None
    assert cleanup_calls == [("storage full dialog", (r"\bstorage full\b",))]


def test_storage_pressure_cleanup_triggers_from_perception_llm(monkeypatch):
    rt = RuntimeState(active_task="Use WhatsApp")
    cleanup_calls = []

    monkeypatch.setattr(
        "plugin.agent.runtime.recovery.perform_storage_cleanup",
        lambda *, reason, evidence, analysis=None: cleanup_calls.append((reason, tuple(evidence))) or type(
            "R",
            (),
            {
                "triggered": True,
                "reason": reason,
                "evidence": list(evidence),
                "disk_cleanup": {"deleted": 3, "empty_dirs": 1, "freed": 1024},
                "environments_cleaned": 2,
                "to_dict": lambda self: {
                    "triggered": True,
                    "reason": reason,
                    "evidence": list(evidence),
                    "disk_cleanup": {"deleted": 3, "empty_dirs": 1, "freed": 1024},
                    "environments_cleaned": 2,
                },
            },
        )(),
    )

    first = maybe_cleanup_for_storage_pressure(
        rt,
        view={"screen": "LIST", "search_query": ""},
        features={
            "perception_llm": {
                "screen_type": "dialog",
                "active_surface": "storage_warning_dialog",
                "likely_next_family": "dismiss",
                "supporting_evidence": ["Storage is too full"],
                "contradictions": ["screen_bucket reports LIST"],
            }
        },
        reason_hint="storage warning via perception llm",
    )

    assert first is not None
    assert first.triggered
    assert cleanup_calls == [
        (
            "storage warning via perception llm",
            (r"\bstorage is too full\b", r"\btoo full\b", "perception_llm:storage_dialog"),
        )
    ]


def test_whatsapp_storage_warning_exposes_blocking_overlay_and_triggers_cleanup(monkeypatch):
    world = WorldModel(active_app="WhatsApp", last_window_name="WhatsApp")
    world.entities = {
        1: Entity(
            id=1,
            entity_type="static",
            semantic_role="storage warning",
            label="Storage is too full",
            bounds=(100.0, 100.0, 320.0, 48.0),
            visible=True,
            enabled=True,
            attributes={"description": "To keep using WhatsApp on this device, free up space."},
        ),
        2: Entity(
            id=2,
            entity_type="button",
            semantic_role="exit",
            label="Exit WhatsApp",
            bounds=(100.0, 500.0, 280.0, 42.0),
            visible=True,
            enabled=True,
        ),
    }
    view = WhatsAppOverlay().view_dict(world)
    assert view["blocking_overlay"] is False
    assert view["system_warnings"]
    assert view["screen"] == "LIST"

    cleanup_calls = []
    monkeypatch.setattr(
        "plugin.agent.runtime.recovery.perform_storage_cleanup",
        lambda *, reason, evidence, analysis=None: cleanup_calls.append((reason, tuple(evidence))) or type(
            "R",
            (),
            {
                "triggered": True,
                "reason": reason,
                "evidence": list(evidence),
                "disk_cleanup": {"deleted": 1, "empty_dirs": 0, "freed": 255},
                "environments_cleaned": 0,
                "to_dict": lambda self: {
                    "triggered": True,
                    "reason": reason,
                    "evidence": list(evidence),
                    "disk_cleanup": {"deleted": 1, "empty_dirs": 0, "freed": 255},
                    "environments_cleaned": 0,
                },
            },
        )(),
    )

    rt = RuntimeState(active_task="Use WhatsApp")
    result = maybe_cleanup_for_storage_pressure(rt, view=view, reason_hint="whatsapp storage full")
    assert result is not None and result.triggered
    assert cleanup_calls == [
        ("whatsapp storage full", (r"\bstorage is too full\b", r"\btoo full\b"))
    ]


def test_storage_cleanup_merges_host_temp_and_hermes_cleanup(monkeypatch):
    class FakeLib:
        @staticmethod
        def quick():
            return {"deleted": 2, "empty_dirs": 1, "freed": 100, "errors": ["a"]}

        @staticmethod
        def quick_host_temp():
            return {"deleted": 3, "empty_dirs": 4, "freed": 900, "errors": ["b"]}

    monkeypatch.setattr(
        "plugin.agent.runtime.recovery._load_disk_cleanup_library",
        lambda: FakeLib(),
    )

    result = perform_storage_cleanup(
        reason="storage pressure test",
        evidence=[r"\bstorage full\b"],
    )
    assert result.disk_cleanup["deleted"] == 5
    assert result.disk_cleanup["empty_dirs"] == 5
    assert result.disk_cleanup["freed"] == 1000
    assert result.disk_cleanup["errors"] == ["a", "b"]


def test_storage_cleanup_carries_analysis_forward(monkeypatch):
    monkeypatch.setattr(
        "plugin.agent.runtime.recovery._analyze_storage_cleanup_targets",
        lambda **_: {
            "reason": "storage pressure test",
            "evidence": [r"\bstorage full\b"],
            "candidates": [],
            "total_size": 123,
            "total_size_human": "123.0 B",
            "low_risk_count": 2,
            "low_risk_human": "123.0 B",
            "sources": {"tracked": 2},
            "notes": ["analysis-only"],
        },
    )

    result = perform_storage_cleanup(
        reason="storage pressure test",
        evidence=[r"\bstorage full\b"],
    )
    assert result.analysis["low_risk_count"] == 2
    assert result.analysis["sources"] == {"tracked": 2}
    assert result.to_dict()["analysis"]["notes"] == ["analysis-only"]


def test_degenerate_observation_holds_last_good_world():
    wm = WorldModel()
    healthy = wm.ingest(FixtureObserver(FIXTURES / "whatsapp_chat.json").observe())
    entity_count = len(wm.entities)
    screen_label = wm.current_screen.label if wm.current_screen else ""
    healthy_score = dict(wm.last_worldview_score)

    degenerate = Observation(
        timestamp=healthy_score.get("freshness_s", 0.0) or 0.0,
        app_name="WhatsApp",
        window_name="WhatsApp",
        nodes=[AxNode(role="AXWindow", name="", description="", bbox=(0.0, 0.0, 0.0, 0.0))],
        source="pyobjc",
        coverage=0.0,
        degraded=True,
    )
    patch = wm.ingest(degenerate)

    assert patch.held_last_good_world is True
    assert len(wm.entities) == entity_count
    assert wm.current_screen is not None
    assert wm.current_screen.label == screen_label
    assert float(wm.last_worldview_score.get("overall", 0.0)) == float(healthy_score.get("overall", 0.0))
    assert not bool(wm.last_worldview_score.get("degraded", True))


def test_chrome_only_observation_holds_last_good_world():
    wm = WorldModel()
    healthy = wm.ingest(FixtureObserver(FIXTURES / "whatsapp_chat.json").observe())
    entity_count = len(wm.entities)
    screen_label = wm.current_screen.label if wm.current_screen else ""
    healthy_score = dict(wm.last_worldview_score)

    chrome_only = Observation(
        timestamp=healthy_score.get("freshness_s", 0.0) or 0.0,
        app_name="WhatsApp",
        window_name="WhatsApp",
        nodes=[
            AxNode(role="AXApplication", name="WhatsApp"),
            AxNode(role="AXWindow", name="WhatsApp"),
            AxNode(role="AXMenuBar", name=""),
            AxNode(role="AXMenuBarItem", name="Apple"),
            AxNode(role="AXMenuBarItem", name="Call"),
            AxNode(role="AXMenuItem", name="About This Mac"),
            AxNode(role="AXMenuItem", name="System Settings, 1 update"),
            AxNode(role="AXButton", name=""),
        ],
        source="pyobjc_ax",
        coverage=0.95,
    )
    patch = wm.ingest(chrome_only)

    assert patch.held_last_good_world is True
    assert len(wm.entities) == entity_count
    assert wm.current_screen is not None
    assert wm.current_screen.label == screen_label
    assert float(wm.last_worldview_score.get("overall", 0.0)) == float(healthy_score.get("overall", 0.0))
    assert bool(wm.last_worldview_score.get("held_last_good_world", False))


def test_single_node_observation_marks_worldview_needs_reobserve():
    wm = WorldModel(active_app="WhatsApp")
    patch = wm.ingest(
        Observation(
            timestamp=0.0,
            app_name="WhatsApp",
            window_name="WhatsApp",
            nodes=[AxNode(role="AXUnknown", name="AXUnknown")],
            source="pyobjc_ax",
            coverage=0.1,
        )
    )

    assert patch.needs_reobserve is True
    assert patch.worldview_score is not None
    assert patch.worldview_score["needs_reobserve"] is True
    assert patch.worldview_score["overall"] <= 0.2


def test_chrome_only_score_exposes_task_sufficiency_flags():
    wm = WorldModel(active_app="WhatsApp")
    patch = wm.ingest(
        Observation(
            timestamp=0.0,
            app_name="WhatsApp",
            window_name="WhatsApp",
            nodes=[
                AxNode(role="AXApplication", name="WhatsApp"),
                AxNode(role="AXWindow", name="WhatsApp"),
                AxNode(role="AXMenuBar", name=""),
                AxNode(role="AXMenuBarItem", name="File"),
                AxNode(role="AXMenuItem", name="Quit"),
            ],
            source="pyobjc_ax",
            coverage=0.95,
        )
    )

    components = patch.worldview_score.get("components") or {}
    assert components.get("chrome_only_node_count", 0) >= 1
    assert components.get("task_sufficient") is False
    assert patch.needs_reobserve is True


def test_disk_cleanup_loader_falls_back_without_namespace(monkeypatch):
    monkeypatch.delitem(sys.modules, "hermes_plugins.disk_cleanup.disk_cleanup", raising=False)
    monkeypatch.delitem(sys.modules, "hermes_plugins.disk_cleanup", raising=False)
    monkeypatch.delitem(sys.modules, "hermes_plugins", raising=False)

    import plugin.agent.runtime.recovery as recovery_mod

    monkeypatch.setattr(
        recovery_mod.importlib,
        "import_module",
        lambda *_: (_ for _ in ()).throw(ModuleNotFoundError()),
    )

    mod = _load_disk_cleanup_library()
    assert hasattr(mod, "quick")


def test_sqlite_persistence(tmp_path: Path):
    wm = WorldModel()
    wm.ingest(FixtureObserver(FIXTURES / "whatsapp_chat.json").observe())
    store = WorldStore(tmp_path / "world.sqlite")
    store.save_entities(wm.entities)
    store.save_screens(wm.screens.screens)
    loaded = store.load_entities()
    assert len(loaded) == len(wm.entities)
    store.close()


def test_worldmodel_has_no_llm_imports():
    root = Path(__file__).resolve().parents[2] / "plugin" / "worldmodel"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert_no_llm_imports(text)
        for bad in FORBIDDEN:
            assert f"import {bad}" not in text
            assert f"from {bad}" not in text


def test_scorecard_kill_gate(monkeypatch):
    from plugin.agent import perception_cycle

    monkeypatch.setattr(perception_cycle, "synthesize_perception", lambda *args, **kwargs: None)
    card = run_scorecard()
    assert card.kill_gate_pass, card.notes
    assert card.entity_tracking >= 0.80
    assert card.screen_classification >= 0.95
    # e2e harness scores Observe-on-decline (no legacy Type fallthrough)
    assert card.e2e_whatsapp_call >= 0.90


def test_hermes_world_tools_register():
    import tools.plugin_world_tool  # noqa: F401
    from tools.registry import registry
    from toolsets import resolve_toolset

    for name in (
        "world_state",
        "world_observe",
        "world_plan",
        "world_act",
        "world_recover",
        "plugin_call_whatsapp",
    ):
        assert name in registry._tools
    # Included in mainstream hermes-cli defaults (no -t plugin_world required)
    cli_tools = resolve_toolset("hermes-cli")
    assert "plugin_call_whatsapp" in cli_tools


def test_cli_observe_fixture(capsys, tmp_path, monkeypatch):
    from plugin.cli import main
    import plugin.cli as cli_mod

    monkeypatch.setattr(cli_mod, "_default_log_dir", lambda: tmp_path / "logs")
    rc = main(["observe", "--fixture", str(FIXTURES / "whatsapp_conversation.json")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "WhatsApp" in out
    assert "Nodes:" in out


def test_launch_uses_open_not_applescript(monkeypatch):
    from plugin.perception.macos.launch import launch_app

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class P:
            returncode = 0
            stdout = ""
            stderr = ""

        return P()

    monkeypatch.setattr("plugin.perception.macos.launch.subprocess.run", fake_run)
    monkeypatch.setattr("plugin.perception.macos.launch.shutil.which", lambda _: "/usr/bin/open")
    result = launch_app("WhatsApp")
    assert result.ok
    assert calls[0][:3] == ["open", "-a", "WhatsApp"]
    assert not any("osascript" in c or "tell application" in " ".join(c) for c in calls)


def test_permissions_checklist_mentions_accessibility():
    from plugin.perception.macos.launch import permissions_checklist

    text = permissions_checklist()
    assert "Accessibility" in text
    assert "Screen Recording" in text
    assert "NOT USED" in text
