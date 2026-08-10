"""Brain owns tool scheduling: meta before decide/actor; no auto-perceive."""

from __future__ import annotations

import time

from plugin.agent.action import Action
from plugin.agent.controller import run_goal_closed_loop
from plugin.agent.executive.meta_action import MetaAction, MetaChoice
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal, GoalStatus
from plugin.agent.perception_cycle import PerceptionSnapshot
from plugin.agent.runtime.state import RuntimeState
from plugin.experiments.logger import EventLogger
from plugin.perception.observation import AxNode, Observation
from plugin.worldmodel.model import WorldPatch


class _FakeExec:
    def __init__(self):
        self.calls = []

    def execute(self, decision):
        self.calls.append(decision)

        class _R:
            ok = True
            backend = "test"
            message = "ok"

        return _R()


def _observe():
    return Observation(
        timestamp=time.time(),
        app_name="WhatsApp",
        window_name="WhatsApp",
        source="test",
        nodes=[AxNode(role="AXButton", name="Chats", description="Chats")],
        meta={},
    )


def _snapshot(
    *,
    worldview: float = 0.9,
    needs_reobserve: bool = False,
    retention: float = 1.0,
) -> PerceptionSnapshot:
    return PerceptionSnapshot(
        observation=_observe(),
        patch=WorldPatch(
            retention=retention,
            screen_id=1,
            screen_label="list",
            new_entity_ids=[],
            matched_ids=[],
            worldview_score={"overall": worldview, "mean_belief": worldview},
            conflicts=[],
            needs_reobserve=needs_reobserve,
            fusion={},
            belief_updates=[],
        ),
        view={"screen": "LIST", "search_query": "", "open_conversation": "", "call_state": ""},
        features={
            "screen_bucket": "list",
            "query_matches_goal": False,
            "extras": {},
        },
        worldview=worldview,
    )


class _Overlay:
    def __init__(self, snapshot: PerceptionSnapshot):
        self._snapshot = snapshot

    def view_dict(self, world):
        return dict(self._snapshot.view)

    def features(self, world, goal, worldview_score=1.0):
        return StateFeatures(
            app="WhatsApp",
            screen_bucket="list",
            query_matches_goal=False,
            worldview_score=worldview_score,
            extras={},
        )


def _patch_loop_basics(monkeypatch, *, snapshot: PerceptionSnapshot, perceive_calls: list):
    monkeypatch.setenv("HERMES_META_PERCEPTION", "1")

    def _refresh(*_a, **_k):
        perceive_calls.append((_k.get("action_label") or "refresh", time.time()))
        return snapshot

    monkeypatch.setattr("plugin.agent.controller.refresh_perception", _refresh)
    monkeypatch.setattr(
        "plugin.agent.controller.get_overlay",
        lambda app, world=None: _Overlay(snapshot),
    )
    monkeypatch.setattr(
        "plugin.agent.controller.evaluate_goal",
        lambda g, w: GoalStatus(succeeded=False, reason="not yet", evidence={}),
    )
    monkeypatch.setattr(
        "plugin.agent.controller._multimodal_look",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "plugin.agent.controller.target_app_obscured",
        lambda *_a, **_k: False,
    )


def test_meta_perceive_runs_before_any_decision_engine(tmp_path, monkeypatch):
    runtime = RuntimeState(active_task="look first")
    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")
    decide_calls = {"n": 0}
    perceive_calls: list = []
    snapshot = _snapshot(needs_reobserve=True, worldview=0.5)

    class _Eng:
        last_trace = None

        def define_action_step(self, goal, world, execution_state, **kwargs):
            decide_calls["n"] += 1
            return Action(action="Click", action_family="open_contact", semantic_target="Pallavi")

    _patch_loop_basics(monkeypatch, snapshot=snapshot, perceive_calls=perceive_calls)
    monkeypatch.setattr(
        "plugin.agent.controller._actuation_available",
        lambda *a, **k: False,
    )

    log = EventLogger(tmp_path / "meta_first.jsonl", also_console=False, run_id="mf")
    exec_ = _FakeExec()
    run_goal_closed_loop(
        runtime,
        goal,
        observe=_observe,
        execute=exec_,
        log=log,
        max_iterations=2,
        settle_s=0.0,
        wait_fn=lambda *_a, **_k: None,
        engine=_Eng(),  # type: ignore[arg-type]
    )
    events = log.read_all()
    kinds = [e.get("kind") for e in events]
    assert "executive_judgement" in kinds
    assert "meta_action_phase" in kinds
    j = kinds.index("executive_judgement")
    m = kinds.index("meta_action_phase")
    assert m > j
    handling = next(
        str(e.get("handling") or "")
        for e in events
        if e.get("kind") == "meta_action_phase"
    )
    assert handling.startswith("brain_tool:perceive") or handling.startswith("brain_tool:reflect")
    assert "decision_engine" not in kinds[: m + 1]
    assert decide_calls["n"] == 0
    assert exec_.calls == []
    # Bootstrap + brain-scheduled look(s).
    labels = [c[0] for c in perceive_calls]
    assert any(lbl == "meta_perceive" or lbl.startswith("meta_") for lbl in labels)


def test_act_turn_capability_only_after_meta_act(tmp_path, monkeypatch):
    runtime = RuntimeState(active_task="act after meta")
    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")
    decide_calls = {"n": 0}
    perceive_calls: list = []
    snapshot = _snapshot()
    order: list[str] = []

    class _Eng:
        last_trace = None

        def define_action_step(self, goal, world, execution_state, **kwargs):
            decide_calls["n"] += 1
            order.append("define_action")
            return Action(
                action="Observe",
                action_family="observe",
                semantic_target="",
            )

    _patch_loop_basics(monkeypatch, snapshot=snapshot, perceive_calls=perceive_calls)
    monkeypatch.setattr(
        "plugin.agent.controller._actuation_available",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        "plugin.agent.controller.assess_executive_judgement",
        lambda *a, **k: (
            type("S", (), {"to_dict": lambda self: {}, "sufficient_to_act": True})(),
            MetaChoice(MetaAction.ACT, "test act", {"act": 1.0}),
        ),
    )

    log = EventLogger(tmp_path / "meta_act.jsonl", also_console=False, run_id="ma")
    run_goal_closed_loop(
        runtime,
        goal,
        observe=_observe,
        execute=_FakeExec(),
        log=log,
        max_iterations=1,
        settle_s=0.0,
        wait_fn=lambda *_a, **_k: None,
        engine=_Eng(),  # type: ignore[arg-type]
    )
    events = log.read_all()
    kinds = [e.get("kind") for e in events]
    handling = next(
        str(e.get("handling") or "")
        for e in events
        if e.get("kind") == "meta_action_phase"
    )
    assert handling == "brain_tool:act"
    assert kinds.index("executive_judgement") < kinds.index("meta_action_phase")
    assert decide_calls["n"] == 1
    assert order == ["define_action"]
    # Bootstrap only — ACT does not schedule a look.
    assert [c[0] for c in perceive_calls] == ["observe"] or len(perceive_calls) == 1


def test_no_auto_perceive_when_meta_is_act_on_stable_world(tmp_path, monkeypatch):
    """Stable ACT-ready world: reuse snap; no look unless brain says PERCEIVE."""
    runtime = RuntimeState(active_task="stable act")
    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")
    perceive_calls: list = []
    snapshot = _snapshot(worldview=0.95, needs_reobserve=False)

    class _Eng:
        last_trace = None

        def define_action_step(self, goal, world, execution_state, **kwargs):
            return Action(
                action="Observe",
                action_family="observe",
                semantic_target="",
            )

    _patch_loop_basics(monkeypatch, snapshot=snapshot, perceive_calls=perceive_calls)
    monkeypatch.setattr(
        "plugin.agent.controller._actuation_available",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        "plugin.agent.controller.assess_executive_judgement",
        lambda *a, **k: (
            type("S", (), {"to_dict": lambda self: {}, "sufficient_to_act": True})(),
            MetaChoice(MetaAction.ACT, "stable act", {"act": 1.0}),
        ),
    )

    log = EventLogger(tmp_path / "no_auto.jsonl", also_console=False, run_id="na")
    run_goal_closed_loop(
        runtime,
        goal,
        observe=_observe,
        execute=_FakeExec(),
        log=log,
        max_iterations=2,
        settle_s=0.0,
        wait_fn=lambda *_a, **_k: None,
        engine=_Eng(),  # type: ignore[arg-type]
    )
    events = log.read_all()
    reused = [e for e in events if e.get("kind") == "perception_reused"]
    forced = [e for e in events if e.get("kind") == "perception_forced"]
    assert forced == []
    assert len(reused) >= 1
    assert len(perceive_calls) == 1
    assert not any(e.get("kind") == "worldview_low" for e in events)


def test_retention_low_is_advisory_not_hard_look_debt(tmp_path, monkeypatch):
    """Live 094313: retention≈0.34 re-armed must_executive_reperceive every
    frame after ComposeSearchQuery, trapping meta in perceive forever.
    """
    runtime = RuntimeState(active_task="retention soft")
    runtime.execution_state.iteration = 1
    runtime.execution_state.last_action = "ComposeSearchQuery"
    runtime.execution_state.post_action_reperceive_pending = False
    runtime.execution_state.must_executive_reperceive = False
    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")
    perceive_calls: list = []
    # Low retention must not create hard look debt.
    snapshot = _snapshot(worldview=0.95, retention=0.20)

    class _Eng:
        last_trace = None

        def define_action_step(self, goal, world, execution_state, **kwargs):
            return Action(
                action="Observe",
                action_family="observe",
                semantic_target="",
            )

    _patch_loop_basics(monkeypatch, snapshot=snapshot, perceive_calls=perceive_calls)
    monkeypatch.setattr(
        "plugin.agent.controller._actuation_available",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        "plugin.agent.controller.assess_executive_judgement",
        lambda *a, **k: (
            type("S", (), {"to_dict": lambda self: {}, "sufficient_to_act": True})(),
            MetaChoice(MetaAction.ACT, "grounded after look", {"act": 1.0}),
        ),
    )

    log = EventLogger(tmp_path / "ret_soft.jsonl", also_console=False, run_id="rs")
    run_goal_closed_loop(
        runtime,
        goal,
        observe=_observe,
        execute=_FakeExec(),
        log=log,
        max_iterations=1,
        settle_s=0.0,
        wait_fn=lambda *_a, **_k: None,
        engine=_Eng(),  # type: ignore[arg-type]
        retention_floor=0.35,
    )
    events = log.read_all()
    assert any(e.get("kind") == "retention_low_signal" for e in events)
    ret = next(e for e in events if e.get("kind") == "retention_low_signal")
    assert ret.get("handling") == "meta_signal:advisory_perceive"
    assert runtime.execution_state.must_executive_reperceive is False
    assert "retention_low" in (
        getattr(runtime.execution_state, "perception_soft_signals", None) or []
    )
    handling = next(
        str(e.get("handling") or "")
        for e in events
        if e.get("kind") == "meta_action_phase"
    )
    assert handling == "brain_tool:act"


def test_must_executive_reperceive_is_meta_signal_not_forced_look(tmp_path, monkeypatch):
    runtime = RuntimeState(active_task="owed look")
    runtime.execution_state.last_action = "Click"
    runtime.execution_state.must_executive_reperceive = True
    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")
    perceive_calls: list = []
    snapshot = _snapshot(worldview=0.95)
    meta_actions: list = []

    class _Eng:
        last_trace = None

        def define_action_step(self, goal, world, execution_state, **kwargs):
            return Action(action="Observe", action_family="observe", semantic_target="")

    _patch_loop_basics(monkeypatch, snapshot=snapshot, perceive_calls=perceive_calls)

    real_assess = __import__(
        "plugin.agent.executive.sync", fromlist=["assess_executive_judgement"]
    ).assess_executive_judgement

    def _assess(*a, **k):
        suff, meta = real_assess(*a, **k)
        meta_actions.append(meta.action)
        return suff, meta

    monkeypatch.setattr("plugin.agent.controller.assess_executive_judgement", _assess)
    monkeypatch.setattr(
        "plugin.agent.controller._actuation_available",
        lambda *a, **k: True,
    )

    log = EventLogger(tmp_path / "owed.jsonl", also_console=False, run_id="ol")
    run_goal_closed_loop(
        runtime,
        goal,
        observe=_observe,
        execute=_FakeExec(),
        log=log,
        max_iterations=2,
        settle_s=0.0,
        wait_fn=lambda *_a, **_k: None,
        engine=_Eng(),  # type: ignore[arg-type]
    )
    events = log.read_all()
    assert not any(e.get("kind") == "perception_forced" for e in events)
    assert MetaAction.PERCEIVE in meta_actions or MetaAction.PERCEIVE in meta_actions
    labels = [c[0] for c in perceive_calls]
    assert any(lbl in {"meta_perceive", "meta_reflect", "meta_verify"} for lbl in labels)
    handling = next(
        str(e.get("handling") or "")
        for e in events
        if e.get("kind") == "meta_action_phase"
    )
    assert handling.startswith("brain_tool:perceive") or handling.startswith("brain_tool:reflect")
