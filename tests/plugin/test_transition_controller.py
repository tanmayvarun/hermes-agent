"""Controller transition loop — suppress NO_EFFECT instead of thrashing."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List

import pytest

from plugin.agent.action import Action
from plugin.agent.controller import resolve_step_budget, run_goal_closed_loop
from plugin.agent.controller import _transition_summary_from_attempt
from plugin.agent.controller import resolve_goal_run_timeout_seconds
from plugin.agent.controller import resolve_goal_no_progress_timeout_seconds
from plugin.agent.controller import _semantic_state_signature
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal, GoalStatus
from plugin.agent.runtime.state import RuntimeState
from plugin.agent.perception_cycle import PerceptionSnapshot
from plugin.executor.ghost import ExecResult
from plugin.perception.observation import AxNode, Observation
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldPatch
from plugin.worldmodel.model import WorldModel
from plugin.agent.transition.types import ExplorationBranch, FrontierAction


@dataclass
class _FakeExec:
    calls: List[str]

    def execute(self, step: Action) -> ExecResult:
        self.calls.append(f"{step.action_family}:{step.semantic_target}")
        return ExecResult(ok=True, backend="test", message=f"fake {step.semantic_target}")


def test_controller_suppresses_repeated_no_effect_call(monkeypatch):
    """Identical world after Call → NO_EFFECT → do not infinite-loop same Call."""
    runtime = RuntimeState(active_task="call")
    e = Entity(
        id=1,
        entity_type="button",
        label="Voice Call",
        semantic_role="Voice Call",
        role="AXButton",
        actions=["click"],
        attributes={"description": "Voice Call"},
        visible=True,
    )
    e2 = Entity(
        id=2,
        entity_type="button",
        label="Now…",
        semantic_role="Now…",
        role="AXButton",
        actions=["click"],
        attributes={"description": "Now…"},
        visible=True,
    )
    runtime.world_model.active_app = "WhatsApp"
    runtime.world_model.entities = {1: e, 2: e2}
    runtime.world_model.tracker._entities = dict(runtime.world_model.entities)
    runtime.world_model.tracker._next_id = 3
    runtime.world_model.overlay_hints["open_conversation"] = "now… messages"
    runtime.world_model.overlay_hints["search_query"] = "Now"

    goal = Goal(kind="whatsapp_voice_call", contact="now group", require_contact_in_call=False)

    monkeypatch.setattr(
        "plugin.agent.controller.evaluate_goal",
        lambda g, w: GoalStatus(succeeded=False, reason="not yet", evidence={}),
    )
    monkeypatch.setattr(
        "plugin.agent.transition.evaluator.evaluate_goal",
        lambda g, w: GoalStatus(succeeded=False, reason="not yet", evidence={}),
    )
    from types import SimpleNamespace
    from plugin.agent.transition.types import TransitionOutcome

    def _force_no_effect(*args, **kwargs):
        result = SimpleNamespace(
            outcome=TransitionOutcome.NO_EFFECT.value,
            attribution={
                "action_family": "start_call",
                "outcome": TransitionOutcome.NO_EFFECT.value,
                "effect_kind": "actuator_failed",
                "likely_failure_domain": "actuation",
                "belief_updates": [],
            },
            effect_kind="actuator_failed",
            reasons=[],
            prediction={},
        )
        result.to_dict = lambda: {
            "outcome": result.outcome,
            "attribution": result.attribution,
            "effect_kind": result.effect_kind,
            "reasons": result.reasons,
            "prediction": result.prediction,
        }
        return result

    monkeypatch.setattr("plugin.agent.controller.TransitionEvaluator.evaluate", _force_no_effect)

    class _Eng:
        last_trace = None

        def decide(self, goal, world, execution_state, **kwargs):
            from plugin.agent.decision import DecisionTrace

            exp = kwargs.get("state_experience") or execution_state.state_experience
            sig = kwargs.get("state_signature") or "S"
            cand = Action(
                action="Click",
                semantic_target="Call",
                action_family="start_call",
                rationale="test call",
            )
            alt = Action(action="Observe", action_family="observe", rationale="fallback")
            if exp is not None and exp.is_suppressed(sig, cand):
                chosen = alt
            else:
                chosen = cand
            self.last_trace = DecisionTrace(
                chosen={
                    "action": chosen.action,
                    "family": chosen.action_family,
                    "target": chosen.semantic_target,
                }
            )
            return chosen

    def _observe() -> Observation:
        return Observation(
            timestamp=time.time(),
            app_name="WhatsApp",
            window_name="WhatsApp",
            source="test",
            nodes=[
                AxNode(role="AXButton", name="Now…", description="Now…"),
                AxNode(role="AXButton", name="Voice Call", description="Voice Call"),
            ],
            meta={},
        )

    def _stable_ingest(obs, action=None, target_entity_id=None):
        return WorldPatch(
            retention=1.0,
            screen_id=1,
            screen_label="call",
            new_entity_ids=[],
            matched_ids=[1, 2],
            worldview_score={"overall": 0.9, "mean_belief": 0.9},
            conflicts=[],
            needs_reobserve=False,
            fusion={},
            belief_updates=[],
        )

    monkeypatch.setattr(runtime.world_model, "ingest", _stable_ingest)

    from plugin.agent.transition.types import TransitionResult

    def _no_change(**kwargs):
        return (
            TransitionResult(
                changed=False, stabilized=True, change_score=0.0, reasons=[], timed_out=True
            ),
            runtime.world_model,
            {
                "screen": "CONVERSATION",
                "search_query": "Now",
                "open_conversation": "now… messages",
                "call_state": "",
                "world_signature": "S",
                "visible_contacts": ["Now…"],
                "voice_call_available": True,
                "unexpected_dialogs": [],
            },
        )

    monkeypatch.setattr(
        "plugin.agent.controller.TransitionMonitor.wait_for_change_or_stability",
        lambda self, **kw: _no_change(),
    )

    class _Overlay:
        def view_dict(self, world):
            return {
                "screen": "CONVERSATION",
                "search_query": "Now",
                "open_conversation": "now… messages",
                "call_state": "",
                "world_signature": "S",
                "visible_contacts": ["Now…"],
                "voice_call_available": True,
                "unexpected_dialogs": [],
                "app_active": True,
            }

        def features(self, world, goal, worldview_score=1.0):
            from plugin.agent.features import StateFeatures

            return StateFeatures(
                app="WhatsApp",
                screen_bucket="conversation",
                conversation_open=True,
                call_available=True,
                query_matches_goal=True,
                has_named_entity=True,
                extras={
                    "resolution_policy": "auto",
                    "resolved_contact": "Now…",
                    "resolution_confidence": 0.91,
                },
            )

    monkeypatch.setattr("plugin.agent.controller.get_overlay", lambda app, world=None: _Overlay())

    ex = _FakeExec(calls=[])
    eng = _Eng()
    result = run_goal_closed_loop(
        runtime,
        goal,
        observe=_observe,
        execute=ex,
        max_iterations=6,
        settle_s=0.0,
        wait_fn=lambda s, r: None,
        engine=eng,  # type: ignore[arg-type]
    )

    call_execs = [c for c in ex.calls if c.startswith("start_call")]
    assert len(call_execs) <= 2, f"Call thrashed: {ex.calls}"
    assert result.ok is False
    assert getattr(runtime.execution_state, "last_transition_summary", None) is not None
    assert runtime.execution_state.last_transition_summary["outcome"] == "no_effect"
    assert runtime.execution_state.last_transition_summary["diagnosis"]["next_move"] == "try_sibling_or_reobserve"


def test_transition_summary_carries_confidence_delta():
    from types import SimpleNamespace

    attempt = SimpleNamespace(
        outcome="progress",
        progress_delta=0.24,
        change_score=0.31,
        prediction={"predicted_outcome": "progress"},
        prediction_error={},
        assessment={
            "goal_progress": "clear",
            "meaningful_change": True,
            "state_understood": True,
            "context_preserved": True,
            "branch_reversible": True,
            "newly_relevant_affordances": ["initiate_voice"],
            "contradiction_evidence": [],
            "notes": ["confidence moved"],
            "irreversible_risk_delta": 0.0,
            "confidence_delta": 0.42,
            "selected_capability_id": "cap-1",
            "selected_capability_type": "SearchConversation",
        },
        attribution={"likely_failure_domain": "none"},
        effect_kind="surface_change",
        action_family="open_search",
        reasons=["confidence moved"],
    )
    summary = _transition_summary_from_attempt(attempt)
    assert summary.confidence_delta == 0.42
    assert summary.diagnosis["confidence_delta"] == 0.42


def test_resolve_step_budget_uses_config_and_clamps_to_ceiling():
    assert resolve_step_budget(max_iterations=15, config={"agent": {"max_stepcount": 8}}) == 8
    assert resolve_step_budget(max_iterations=5, config={"agent": {"max_stepcount": 8}}) == 5
    assert resolve_step_budget(max_iterations=7, max_stepcount=3) == 3
    assert resolve_step_budget(max_iterations=7, max_stepcount=0) == 7


def test_resolve_goal_run_timeout_uses_config_and_goal_default(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.config.load_config_readonly",
        lambda: {"agent": {"goal_run_timeout_seconds": 123}},
    )
    assert resolve_goal_run_timeout_seconds(goal_kind="whatsapp_forward_message") == 123.0

    monkeypatch.setattr("hermes_cli.config.load_config_readonly", lambda: {})
    assert resolve_goal_run_timeout_seconds(goal_kind="whatsapp_forward_message") == 600.0
    assert resolve_goal_run_timeout_seconds(goal_kind="generic") == 900.0


def test_resolve_goal_no_progress_timeout_uses_config_and_goal_default(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.config.load_config_readonly",
        lambda: {"agent": {"goal_no_progress_timeout_seconds": 22}},
    )
    assert resolve_goal_no_progress_timeout_seconds(goal_kind="whatsapp_forward_message") == 22.0


def test_semantic_state_signature_tracks_surface_and_active_slice():
    base_view = {
        "screen": "CONVERSATION",
        "active_surface": "conversation",
        "open_conversation": "Kulvinder Ji",
        "call_state": "",
        "search_query": "Kulvinder",
        "surface_state": {
            "main_surface": "conversation",
            "sidebar_surface": "list",
            "detail_surface": "conversation",
        },
    }
    sig_a = _semantic_state_signature(
        view=base_view,
        features={
            "active_cognitive_subgraph": {
                "active_entity_ids": [1],
                "focus_region_ids": ["main"],
                "excluded_region_ids": [],
            }
        },
        world_id="world-1",
    )
    sig_b = _semantic_state_signature(
        view=base_view,
        features={
            "active_cognitive_subgraph": {
                "active_entity_ids": [2],
                "focus_region_ids": ["sidebar"],
                "excluded_region_ids": ["detail"],
            }
        },
        world_id="world-1",
    )
    assert sig_a != sig_b
    assert "screen=conversation" in sig_a
    assert "focus_regions=main" in sig_a


def test_execution_state_tracks_semantic_repeats():
    runtime = RuntimeState(active_task="repeat watch")
    assert runtime.execution_state.note_semantic_state("screen=conversation|surface=main") is False
    assert runtime.execution_state.semantic_repeat_count == 1
    assert runtime.execution_state.note_semantic_state("screen=conversation|surface=main") is False
    assert runtime.execution_state.semantic_repeat_count == 2
    assert runtime.execution_state.note_semantic_state("screen=conversation|surface=main") is True
    assert runtime.execution_state.semantic_repeat_count == 3


def test_stale_frontier_invalidation_clears_branch_and_sets_replan_hint():
    runtime = RuntimeState(active_task="repeat watch")
    branch = ExplorationBranch(active=True)
    branch.set_frontier(
        [
            FrontierAction(
                state_signature="state-1",
                action_key="click:reply",
                action_family="click",
                semantic_target="Reply",
                score=0.9,
            )
        ],
        state_signature="state-1",
    )
    runtime.execution_state.exploration_branch = branch

    from plugin.agent.controller import _invalidate_stale_frontier

    hint = _invalidate_stale_frontier(runtime, reason="unit_test", fallback="observe")

    assert hint == "click"
    assert runtime.execution_state.world_exploration_needed is True
    assert runtime.execution_state.state_experience.pending_backtrack_family == "click"
    assert runtime.execution_state.exploration_branch.active is False
    assert runtime.execution_state.exploration_branch.frontier == []
    assert runtime.execution_state.exploration_branch.frontier_state_signature == ""
    assert runtime.execution_state.exploration_branch.frontier_invalidations == 1


def test_resolve_goal_no_progress_timeout_uses_config_and_goal_default(monkeypatch):
    monkeypatch.setattr("hermes_cli.config.load_config_readonly", lambda: {})
    assert resolve_goal_no_progress_timeout_seconds(goal_kind="whatsapp_forward_message") == 30.0
    assert resolve_goal_no_progress_timeout_seconds(goal_kind="generic") == 45.0


def test_controller_honors_step_budget_without_early_termination(monkeypatch):
    runtime = RuntimeState(active_task="observe loop")
    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")

    class _Eng:
        last_trace = None

        def decide(self, goal, world, execution_state, **kwargs):
            return Action(action="Observe", action_family="observe", rationale="keep going")

    def _observe() -> Observation:
        return Observation(
            timestamp=time.time(),
            app_name="WhatsApp",
            window_name="WhatsApp",
            source="test",
            nodes=[
                AxNode(role="AXButton", name="Chats", description="Chats"),
            ],
            meta={},
        )

    snapshot = PerceptionSnapshot(
        observation=_observe(),
        patch=WorldPatch(
            retention=1.0,
            screen_id=1,
            screen_label="list",
            new_entity_ids=[],
            matched_ids=[],
            worldview_score={"overall": 0.95, "mean_belief": 0.95},
            conflicts=[],
            needs_reobserve=False,
            fusion={},
            belief_updates=[],
        ),
        view={
            "screen": "LIST",
            "search_query": "",
            "open_conversation": "",
            "call_state": "",
            "world_signature": "stable",
            "visible_contacts": ["Chats"],
        },
        features={
            "screen_bucket": "list",
            "query_matches_goal": False,
            "has_named_entity": False,
            "conversation_open": False,
            "call_available": False,
            "goal_progress": 0.0,
            "extras": {"resolution_policy": "auto"},
        },
        worldview=0.95,
    )

    class _Overlay:
        def view_dict(self, world):
            return dict(snapshot.view)

        def features(self, world, goal, worldview_score=1.0):
            return StateFeatures(
                app="WhatsApp",
                screen_bucket="list",
                query_matches_goal=False,
                has_named_entity=False,
                conversation_open=False,
                call_available=False,
                goal_progress=0.0,
                worldview_score=worldview_score,
                extras={"resolution_policy": "auto"},
            )

    monkeypatch.setattr("plugin.agent.controller.refresh_perception", lambda *a, **k: snapshot)
    monkeypatch.setattr("plugin.agent.controller.get_overlay", lambda app, world=None: _Overlay())
    monkeypatch.setattr(
        "plugin.agent.controller.evaluate_goal",
        lambda g, w: GoalStatus(succeeded=False, reason="not yet", evidence={}),
    )

    result = run_goal_closed_loop(
        runtime,
        goal,
        observe=_observe,
        execute=_FakeExec(calls=[]),
        max_iterations=10,
        max_stepcount=3,
        settle_s=0.0,
        wait_fn=lambda s, r: None,
        engine=_Eng(),  # type: ignore[arg-type]
    )

    assert result.ok is False
    assert result.reason == "Maximum step count reached"
    assert result.iterations == 3
    assert runtime.execution_state.iteration == 3


def test_controller_no_progress_watchdog_forces_replan(monkeypatch):
    runtime = RuntimeState(active_task="repeat watch")
    goal = Goal(kind="whatsapp_forward_message", contact="Pallavi", target_contact="Kulvinder")

    monkeypatch.setattr(
        "hermes_cli.config.load_config_readonly",
        lambda: {"agent": {"goal_no_progress_timeout_seconds": 5.0, "max_stepcount": 4}},
    )
    clock = iter([0.0, 10.0] + [10.0] * 20)
    monkeypatch.setattr("plugin.agent.controller.time.monotonic", lambda: next(clock))

    runtime.execution_state.exploration_branch = ExplorationBranch(active=True)
    runtime.execution_state.exploration_branch.set_frontier(
        [
            FrontierAction(
                state_signature="state-1",
                action_key="click:reply",
                action_family="click",
                semantic_target="Reply",
                score=0.8,
            )
        ],
        state_signature="state-1",
    )

    class _Eng:
        last_trace = None

        def decide(self, goal, world, execution_state, **kwargs):
            return Action(action="Observe", action_family="observe", rationale="keep going")

    def _observe() -> Observation:
        return Observation(
            timestamp=time.time(),
            app_name="WhatsApp",
            window_name="WhatsApp",
            source="test",
            nodes=[AxNode(role="AXButton", name="Chats", description="Chats")],
            meta={},
        )

    snapshot = PerceptionSnapshot(
        observation=_observe(),
        patch=WorldPatch(
            retention=1.0,
            screen_id=1,
            screen_label="list",
            new_entity_ids=[],
            matched_ids=[],
            worldview_score={"overall": 0.95, "mean_belief": 0.95},
            conflicts=[],
            needs_reobserve=False,
            fusion={},
            belief_updates=[],
        ),
        view={
            "screen": "LIST",
            "search_query": "",
            "open_conversation": "",
            "call_state": "",
            "world_signature": "stable",
            "visible_contacts": ["Chats"],
        },
        features={
            "screen_bucket": "list",
            "query_matches_goal": False,
            "has_named_entity": False,
            "conversation_open": False,
            "call_available": False,
            "goal_progress": 0.0,
            "extras": {"resolution_policy": "auto"},
        },
        worldview=0.95,
    )

    class _Overlay:
        def view_dict(self, world):
            return dict(snapshot.view)

        def features(self, world, goal, worldview_score=1.0):
            return StateFeatures(
                app="WhatsApp",
                screen_bucket="list",
                query_matches_goal=False,
                has_named_entity=False,
                conversation_open=False,
                call_available=False,
                goal_progress=0.0,
                worldview_score=worldview_score,
                extras={"resolution_policy": "auto"},
            )

    monkeypatch.setattr("plugin.agent.controller.refresh_perception", lambda *a, **k: snapshot)
    monkeypatch.setattr("plugin.agent.controller.get_overlay", lambda app, world=None: _Overlay())
    monkeypatch.setattr(
        "plugin.agent.controller.evaluate_goal",
        lambda g, w: GoalStatus(succeeded=False, reason="not yet", evidence={}),
    )

    result = run_goal_closed_loop(
        runtime,
        goal,
        observe=_observe,
        execute=_FakeExec(calls=[]),
        max_iterations=1,
        settle_s=0.0,
        wait_fn=lambda s, r: None,
        engine=_Eng(),  # type: ignore[arg-type]
    )

    assert result.ok is False
    assert runtime.execution_state.exploration_branch.active is False
    assert runtime.execution_state.exploration_branch.frontier_invalidations >= 1
    assert runtime.execution_state.state_experience.pending_backtrack_family == "click"


def test_controller_stops_when_goal_wall_clock_budget_expires(monkeypatch):
    runtime = RuntimeState(active_task="observe loop")
    goal = Goal(kind="whatsapp_forward_message", contact="Pallavi", target_contact="Kulvinder")

    monkeypatch.setattr(
        "hermes_cli.config.load_config_readonly",
        lambda: {"agent": {"goal_run_timeout_seconds": 5.0, "max_stepcount": 10}},
    )

    class _Eng:
        last_trace = None

        def decide(self, goal, world, execution_state, **kwargs):
            return Action(action="Observe", action_family="observe", rationale="keep going")

    def _observe() -> Observation:
        return Observation(
            timestamp=time.time(),
            app_name="WhatsApp",
            window_name="WhatsApp",
            source="test",
            nodes=[
                AxNode(role="AXButton", name="Chats", description="Chats"),
            ],
            meta={},
        )

    snapshot = PerceptionSnapshot(
        observation=_observe(),
        patch=WorldPatch(
            retention=1.0,
            screen_id=1,
            screen_label="list",
            new_entity_ids=[],
            matched_ids=[],
            worldview_score={"overall": 0.95, "mean_belief": 0.95},
            conflicts=[],
            needs_reobserve=False,
            fusion={},
            belief_updates=[],
        ),
        view={
            "screen": "LIST",
            "search_query": "",
            "open_conversation": "",
            "call_state": "",
            "world_signature": "stable",
            "visible_contacts": ["Chats"],
        },
        features={
            "screen_bucket": "list",
            "query_matches_goal": False,
            "has_named_entity": False,
            "conversation_open": False,
            "call_available": False,
            "goal_progress": 0.0,
            "extras": {"resolution_policy": "auto"},
        },
        worldview=0.95,
    )

    class _Overlay:
        def view_dict(self, world):
            return dict(snapshot.view)

        def features(self, world, goal, worldview_score=1.0):
            return StateFeatures(
                app="WhatsApp",
                screen_bucket="list",
                query_matches_goal=False,
                has_named_entity=False,
                conversation_open=False,
                call_available=False,
                goal_progress=0.0,
                worldview_score=worldview_score,
                extras={"resolution_policy": "auto"},
            )

    monkeypatch.setattr("plugin.agent.controller.refresh_perception", lambda *a, **k: snapshot)
    monkeypatch.setattr("plugin.agent.controller.get_overlay", lambda app, world=None: _Overlay())
    monkeypatch.setattr(
        "plugin.agent.controller.evaluate_goal",
        lambda g, w: GoalStatus(succeeded=False, reason="not yet", evidence={}),
    )

    class _FakeClock:
        def __init__(self):
            self.t = 0.0

        def monotonic(self):
            val = self.t
            self.t += 0.6
            return val

    clock = _FakeClock()
    monkeypatch.setattr("plugin.agent.controller.time.monotonic", clock.monotonic)

    result = run_goal_closed_loop(
        runtime,
        goal,
        observe=_observe,
        execute=_FakeExec(calls=[]),
        max_iterations=10,
        settle_s=0.0,
        wait_fn=lambda s, r: None,
        engine=_Eng(),  # type: ignore[arg-type]
    )

    assert result.ok is False
    assert result.reason == "goal wall-clock budget reached"
    assert result.iterations == 2
    assert runtime.execution_state.iteration == 2
    assert result.evidence["goal_run_timeout_s"] == 5.0


def test_perception_cycle_stall_demotes_observe():
    from plugin.agent.decision import DecisionEngine

    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")
    runtime = RuntimeState()
    runtime.execution_state.perception_cycle_stalled = True
    runtime.execution_state.perception_stall_count = 2
    runtime.execution_state.perception_incomplete = True

    wm = WorldModel()
    wm.active_app = "WhatsApp"
    wm.entities = {
        1: Entity(
            id=1,
            entity_type="button",
            label="Search",
            semantic_role="Search",
            role="AXButton",
            actions=["click"],
            attributes={"description": "Search"},
            visible=True,
        ),
        2: Entity(
            id=2,
            entity_type="button",
            label="Pallavi",
            semantic_role="Pallavi",
            role="AXButton",
            actions=["click"],
            attributes={"description": "Pallavi"},
            visible=True,
        ),
    }
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = 3

    step = DecisionEngine().decide(goal, wm, runtime.execution_state)
    assert step is not None
    assert step.action_family != "observe"
