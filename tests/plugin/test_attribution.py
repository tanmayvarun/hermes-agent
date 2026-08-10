"""Causal failure attribution — independent reference / entity / actuation layers."""

from __future__ import annotations

from plugin.agent.action import Action
from plugin.agent.goal import Goal
from plugin.agent.transition.attribution import (
    EffectKind,
    FailureDomain,
    HypothesisLayers,
    attribute_transition,
    should_advance_reference_hypothesis,
)
from plugin.agent.transition.types import TransitionOutcome, TransitionResult


def test_start_call_center_none_implicates_actuation_not_reference():
    action = Action(action="Click", semantic_target="Call", action_family="start_call")
    tr = TransitionResult(changed=False, stabilized=True, change_score=0.0)
    attrib = attribute_transition(
        action=action,
        outcome=TransitionOutcome.NO_EFFECT.value,
        transition=tr,
        execution={"ok": True, "backend": "ax", "message": "click 'Voice Call' center=None code=0"},
        before_view={"open_conversation": "now… messages", "search_query": "Now"},
        after_view={"open_conversation": "now… messages", "search_query": "Now"},
        before_features={"resolution_confidence": 0.91, "query_matches_goal": True},
        after_features={"resolution_confidence": 0.91, "query_matches_goal": True},
        goal=Goal(kind="whatsapp_voice_call", contact="now group"),
    )
    assert attrib.effect_kind == EffectKind.MISSING_GEOMETRY.value
    assert attrib.likely_failure_domain == FailureDomain.ACTUATION.value
    assert attrib.affected_beliefs.reference_resolution == 0.0
    assert attrib.affected_beliefs.actuator_reliability < 0
    assert not attrib.implicates_reference


def test_call_no_effect_does_not_advance_search_hypothesis():
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    action = Action(action="Click", semantic_target="Call", action_family="start_call")
    attrib = attribute_transition(
        action=action,
        outcome=TransitionOutcome.NO_EFFECT.value,
        transition=TransitionResult(changed=False, change_score=0.0),
        execution={"ok": True, "backend": "ax", "message": "click center=None"},
        before_view={"search_query": "Now", "open_conversation": "now…"},
        after_view={"search_query": "Now", "open_conversation": "now…"},
        after_features={
            "query_matches_goal": True,
            "resolution_confidence": 0.91,
            "resolution_policy": "auto",
            "contact_candidates": [{"name": "Now…"}],
        },
        goal=goal,
    )
    layers = HypothesisLayers(reference_confidence=0.88, entity_confidence=0.91)
    layers.apply(attrib)
    assert not should_advance_reference_hypothesis(
        assessment=attrib,
        layers=layers,
        goal=goal,
        after_view={"search_query": "Now", "open_conversation": "now…"},
        after_features={
            "query_matches_goal": True,
            "resolution_confidence": 0.91,
            "resolution_policy": "auto",
            "contact_candidates": [{"name": "Now…"}],
        },
        hyp_index=0,
        n_hypotheses=2,
    )
    # Reference confidence unchanged by actuation failure
    assert layers.reference_confidence >= 0.85


def test_weak_resolution_after_landed_query_can_advance_reference():
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    action = Action(action="Type", semantic_target="Search", text="Now", action_family="type_query")
    attrib = attribute_transition(
        action=action,
        outcome=TransitionOutcome.NO_EFFECT.value,
        transition=TransitionResult(changed=True, change_score=0.2, reasons=["search_query_changed"]),
        execution={"ok": True, "backend": "ax", "message": "typed 'Now'"},
        before_view={"search_query": ""},
        after_view={"search_query": "Now", "open_conversation": ""},
        after_features={
            "query_matches_goal": True,
            "resolution_confidence": 0.2,
            "resolution_policy": "ask",
            "contact_candidates": [],
        },
        goal=goal,
    )
    # Force reference implication via empty candidates path
    assert attrib.implicates_reference or attrib.likely_failure_domain == FailureDomain.REFERENCE.value
    layers = HypothesisLayers(reference_confidence=0.5)
    layers.apply(attrib)
    ok = should_advance_reference_hypothesis(
        assessment=attrib,
        layers=layers,
        goal=goal,
        after_view={"search_query": "Now"},
        after_features={
            "query_matches_goal": True,
            "resolution_confidence": 0.2,
            "resolution_policy": "ask",
            "contact_candidates": [],
        },
        hyp_index=0,
        n_hypotheses=2,
    )
    assert ok


def test_open_contact_no_effect_without_reference_evidence_does_not_advance():
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    action = Action(action="Click", semantic_target="Now…", action_family="open_contact")
    attrib = attribute_transition(
        action=action,
        outcome=TransitionOutcome.NO_EFFECT.value,
        transition=TransitionResult(changed=False, change_score=0.0),
        execution={"ok": True, "backend": "ax", "message": "click center=None"},
        before_view={"search_query": "Now", "open_conversation": ""},
        after_view={"search_query": "Now", "open_conversation": ""},
        after_features={
            "query_matches_goal": True,
            "resolution_confidence": 0.91,
            "resolution_policy": "auto",
            "contact_candidates": [{"name": "Now…"}],
        },
        goal=goal,
    )
    assert attrib.likely_failure_domain == FailureDomain.ACTUATION.value
    layers = HypothesisLayers()
    assert not should_advance_reference_hypothesis(
        assessment=attrib,
        layers=layers,
        goal=goal,
        after_view={"search_query": "Now"},
        after_features={
            "query_matches_goal": True,
            "resolution_confidence": 0.91,
            "resolution_policy": "auto",
            "contact_candidates": [{"name": "Now…"}],
        },
        hyp_index=0,
        n_hypotheses=2,
    )


def test_controller_call_failure_does_not_mutate_reference_hypothesis(monkeypatch):
    """Regression: downstream Call NO_EFFECT must not advance Now → Now Group.

    Invariant: a downstream action failure must not invalidate an upstream belief
    unless the observation provides evidence against that belief.
    """
    import time
    from dataclasses import dataclass
    from typing import List

    from plugin.agent.controller import run_goal_closed_loop
    from plugin.agent.goal import GoalStatus
    from plugin.agent.runtime.state import RuntimeState
    from plugin.executor.ghost import ExecResult
    from plugin.perception.observation import AxNode, Observation
    from plugin.worldmodel.entities.entity import Entity
    from plugin.worldmodel.model import WorldPatch

    runtime = RuntimeState(active_task="call")
    runtime.world_model.active_app = "WhatsApp"
    for i, name in enumerate(["Voice Call", "Now…"], start=1):
        e = Entity(
            id=i,
            entity_type="button",
            label=name,
            semantic_role=name,
            role="AXButton",
            actions=["click"],
            attributes={"description": name},
            visible=True,
        )
        runtime.world_model.entities[i] = e
    runtime.world_model.tracker._entities = dict(runtime.world_model.entities)
    runtime.world_model.tracker._next_id = 3
    runtime.world_model.overlay_hints["open_conversation"] = "now… messages"
    runtime.world_model.overlay_hints["search_query"] = "Now"

    goal = Goal(kind="whatsapp_voice_call", contact="now group", require_contact_in_call=False)
    assert goal.search_text(0) == "Now"
    assert runtime.execution_state.search_hypothesis_index == 0

    monkeypatch.setattr(
        "plugin.agent.controller.evaluate_goal",
        lambda g, w: GoalStatus(succeeded=False, reason="not yet", evidence={}),
    )
    monkeypatch.setattr(
        "plugin.agent.transition.evaluator.evaluate_goal",
        lambda g, w: GoalStatus(succeeded=False, reason="not yet", evidence={}),
    )

    typed_texts: List[str] = []

    class _Eng:
        last_trace = None

        def define_action_step(self, goal, world, execution_state, **kwargs):
            from plugin.agent.decision import DecisionTrace

            cand = Action(
                action="Click",
                semantic_target="Call",
                action_family="start_call",
                rationale="test call",
            )
            if execution_state.is_prohibited(cand):
                chosen = Action(action="Observe", action_family="observe", rationale="fallback")
            else:
                chosen = cand
            self.last_trace = DecisionTrace(
                chosen={"action": chosen.action, "family": chosen.action_family}
            )
            return chosen

    @dataclass
    class _Exec:
        def execute(self, step: Action) -> ExecResult:
            if step.action_family == "type_query":
                typed_texts.append(step.text or "")
            return ExecResult(
                ok=True,
                backend="ax",
                message="click 'Voice Call' center=None code=0",
            )

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
        )

    monkeypatch.setattr(
        runtime.world_model,
        "ingest",
        lambda *a, **k: WorldPatch(
            retention=1.0,
            screen_id=1,
            screen_label="call",
            new_entity_ids=[],
            matched_ids=[1, 2],
            worldview_score={"overall": 0.9, "mean_belief": 0.9},
        ),
    )

    from plugin.agent.transition.types import TransitionResult

    def _no_change(**kwargs):
        return (
            TransitionResult(changed=False, stabilized=True, change_score=0.0, timed_out=True),
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
                    "contact_candidates": [{"name": "Now…", "confidence": 0.91}],
                },
            )

    monkeypatch.setattr("plugin.agent.controller.get_overlay", lambda app, world=None: _Overlay())

    run_goal_closed_loop(
        runtime,
        goal,
        observe=_observe,
        execute=_Exec(),
        max_iterations=4,
        settle_s=0.0,
        wait_fn=lambda s, r: None,
        engine=_Eng(),  # type: ignore[arg-type]
    )

    assert runtime.execution_state.search_hypothesis_index == 0, (
        "Call failure must not advance search hypothesis "
        f"(got index={runtime.execution_state.search_hypothesis_index})"
    )
    assert goal.search_text(runtime.execution_state.search_hypothesis_index) == "Now"
    assert "Now Group" not in typed_texts
    assert "now group" not in [t.lower() for t in typed_texts]

    attr = runtime.execution_state.last_attribution or {}
    assert attr.get("likely_failure_domain") == FailureDomain.ACTUATION.value
    beliefs = attr.get("affected_beliefs") or {}
    assert float(beliefs.get("reference_resolution") or 0) == 0.0
    assert runtime.execution_state.hypothesis_layers.reference_confidence >= 0.8


def test_actuation_failure_triggers_world_exploration_not_intent_revision():
    """After Call NO_EFFECT: explore world (Observe), keep hyp index 0 / Now."""
    from plugin.agent.decision import DecisionEngine
    from plugin.agent.features import StateFeatures
    from plugin.agent.runtime.state import ExecutionState
    from plugin.worldmodel.entities.entity import Entity
    from plugin.worldmodel.model import WorldModel

    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    wm = WorldModel()
    wm.active_app = "WhatsApp"
    for i, name in enumerate(["Now…", "Voice Call", "Open call dropdown menu with Now…"], start=1):
        wm.entities[i] = Entity(
            id=i,
            entity_type="button",
            label=name,
            semantic_role=name,
            role="AXButton",
            actions=["click"],
            attributes={"description": name},
            visible=True,
        )
    wm.tracker._entities = dict(wm.entities)

    ex = ExecutionState()
    ex.search_hypothesis_index = 0
    ex.world_exploration_needed = True
    ex.hypothesis_layers.actuation_confidence = 0.3

    # Suppress the failed Call actuation key
    from plugin.agent.transition.experience import action_experience_key

    failed = Action(action="Click", semantic_target="Call", action_family="start_call")
    ex.state_experience.record_outcome("S", failed, TransitionOutcome.NO_EFFECT)
    ex.prohibited_actions[ex.action_key(failed)] = 3

    eng = DecisionEngine()
    # Patch overlay features via deciding with monkeypatch-less stub: set extras on features
    # by calling decide — need overlay. Use DecisionEngine with manual feature path:
    from plugin.agent.apps.whatsapp import WhatsAppOverlay

    feats = StateFeatures(
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
            "active_search_hypothesis": "Now",
            "search_hypothesis_index": 0,
            "world_exploration_needed": True,
            "actuation_weak": True,
            "contact_candidates": [{"name": "Now…"}],
        },
    )
    from plugin.agent.policy.candidates import enumerate_candidates

    cands = enumerate_candidates(goal, wm, feats, WhatsAppOverlay())
    families = {c.action_family for c in cands}
    assert "observe" in families
    assert "explore_chrome" in families or any("dropdown" in (c.semantic_target or "").lower() for c in cands)
    # Intent still Now — type_query if present must not be raw now group
    for c in cands:
        if c.action_family == "type_query":
            assert c.text == "Now"

    # Filter + score like DecisionEngine
    cands = ex.state_experience.filter_actions("S", cands)
    scored = []
    for cand in cands:
        if ex.is_prohibited(cand):
            continue
        from plugin.agent.policy.value import predicted_value_delta

        dv = predicted_value_delta(cand, feats, goal)
        ev = 0.7 if cand.action_family == "observe" else 0.0
        if cand.action_family == "explore_chrome":
            ev = 0.45
        if cand.action_family == "start_call":
            ev = -0.35
        if cand.action_family == "type_query":
            ev = -0.5
        scored.append((dv + ev, cand))
    scored.sort(key=lambda x: -x[0])
    best = scored[0][1]
    assert best.action_family in {"observe", "explore_chrome"}, best
    assert ex.search_hypothesis_index == 0
    assert goal.search_text(0) == "Now"


def test_type_progress_never_advances_reference_even_if_conf_zero():
    """Regression: typing Now with world progress must keep hyp at Now (not Now Group)."""
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    action = Action(action="Type", semantic_target="Search", text="Now", action_family="type_query")
    attrib = attribute_transition(
        action=action,
        outcome=TransitionOutcome.PROGRESS.value,
        transition=TransitionResult(changed=True, change_score=0.88, reasons=["search_query_changed"]),
        execution={"ok": True, "backend": "ax", "message": "typed 'Now'"},
        before_view={"search_query": "", "open_conversation": "papaji"},
        after_view={"search_query": "Now", "open_conversation": "papaji"},
        after_features={
            "query_matches_goal": True,
            "resolution_confidence": 0.0,
            "resolution_policy": "ask",
            "contact_candidates": [],
        },
        goal=goal,
    )
    assert attrib.likely_failure_domain != FailureDomain.REFERENCE.value
    assert float(attrib.affected_beliefs.reference_resolution) >= 0.0
    layers = HypothesisLayers(reference_confidence=0.88)
    assert not should_advance_reference_hypothesis(
        assessment=attrib,
        layers=layers,
        goal=goal,
        after_view={"search_query": "Now"},
        after_features={
            "query_matches_goal": True,
            "resolution_confidence": 0.0,
            "resolution_policy": "ask",
            "contact_candidates": [],
        },
        hyp_index=0,
        n_hypotheses=2,
    )
