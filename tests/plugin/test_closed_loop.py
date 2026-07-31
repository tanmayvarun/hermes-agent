"""Closed-loop controller tests — planner re-entry, predicates, no fixed plan."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Dict, List, Optional
from types import SimpleNamespace

import pytest

from plugin.agent.controller import run_goal_closed_loop
from plugin.agent.action import Action as PlanStep
from plugin.agent.decision import decide as next_action
from plugin.agent.goal import Goal, evaluate_goal
from plugin.agent.predicates import SearchQueryEquals, CallStateIs, ContactResultVisible
from plugin.agent.runtime.state import ExecutionState, RuntimeState
from plugin.agent.task_binding import ForwardTaskState
from plugin.agent.transition.types import ContextualBelief, ExplorationBranch, InteractionContext
from plugin.agent.whatsapp_view import WhatsAppWorldView
from plugin.executor import ax_action
from plugin.executor.ghost import ExecResult
from plugin.perception.observation import AxNode, Observation
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel


def _obs(app: str, nodes: List[AxNode]) -> Observation:
    return Observation(
        timestamp=0.0,
        app_name=app,
        window_name=app,
        nodes=nodes,
        ax_tree=None,
        source="test",
        coverage=1.0,
    )


def _llm_response(payload: dict[str, object]):
    message = SimpleNamespace(content=json.dumps(payload), tool_calls=[])
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], usage=None, model="fake")


def _mock_perception_llm(monkeypatch):
    from agent import auxiliary_client

    def fake_call_llm(**kwargs):
        return _llm_response(
            {
                "screen_type": "conversation",
                "active_surface": "conversation",
                "likely_next_family": "open_contact",
                "likely_next_target": "Pallavi",
                "likely_next_text": "",
                "confidence": 0.6,
                "avoid_families": ["type_query"],
                "supporting_evidence": ["unit-test perception stub"],
                "contradictions": [],
                "needs_followup_observe": False,
            }
        )

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)
    token = auxiliary_client.set_runtime_main(
        "openrouter",
        "openai/gpt-oss-120b",
        base_url="https://openrouter.ai/api/v1",
    )
    return auxiliary_client, token


def _entity(
    eid: int,
    *,
    etype: str,
    label: str,
    role: str = "AXButton",
    value: str = "",
    focused: bool = False,
    description: str = "",
    bounds: tuple[float, float, float, float] = (0.0, 0.0, 64.0, 32.0),
) -> Entity:
    attrs: Dict = {}
    if value:
        attrs["value"] = value
    if description:
        attrs["description"] = description
    if focused:
        attrs["focused"] = True
        attrs["AXFocused"] = True
    return Entity(
        id=eid,
        entity_type=etype,
        semantic_role=label,
        label=label,
        role=role,
        actions=["click"] if etype == "button" else (["click", "type"] if etype == "textfield" else []),
        bounds=bounds,
        attributes=attrs,
        visible=True,
    )


def _seed_world(entities: List[Entity], app: str = "WhatsApp") -> WorldModel:
    wm = WorldModel()
    wm.active_app = app
    # Bypass tracker for deterministic unit tests
    wm.entities = {e.id: e for e in entities}
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = max(e.id for e in entities) + 1 if entities else 1
    return wm


@dataclass
class ScriptedExecutor:
    """Returns ok=True always; world advances via ScriptedObserver."""

    calls: List[PlanStep] = field(default_factory=list)
    fail_type_silently: bool = False  # pretend type ok but observer won't change query

    def execute(self, step: PlanStep) -> ExecResult:
        self.calls.append(step)
        if self.fail_type_silently and step.action.lower() == "type":
            return ExecResult(ok=True, backend="fake", message="fake type ok without UI change")
        return ExecResult(ok=True, backend="fake", message=f"ok {step.action}")


@dataclass
class ScriptedObserver:
    """Yields a sequence of worlds as Observations rebuilt from entity lists."""

    frames: List[List[Entity]]
    idx: int = 0
    app: str = "WhatsApp"

    def __call__(self) -> Observation:
        ents = self.frames[min(self.idx, len(self.frames) - 1)]
        self.idx += 1
        nodes = []
        for e in ents:
            nodes.append(
                AxNode(
                    role=e.role or "AXButton",
                    name=e.label,
                    description=e.semantic_role,
                    value=str(e.attributes.get("value") or None),
                    bbox=e.bounds,
                    attributes=dict(e.attributes),
                )
            )
        return _obs(self.app, nodes)


def test_whatsapp_view_search_query():
    wm = _seed_world(
        [
            _entity(1, etype="textfield", label="Search", role="AXTextField", value="Pallavi", focused=True),
            _entity(2, etype="button", label="Pallavi", role="AXButton"),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.search_query.lower() == "pallavi"
    assert view.screen in {"SEARCH", "SEARCH_RESULTS"}
    assert SearchQueryEquals("Pallavi").evaluate(wm).passed
    assert ContactResultVisible("Pallavi").evaluate(wm).passed


def test_planner_next_action_sequence_depends_on_world():
    """DecisionEngine picks from candidates using prior+value — world evidence wins."""
    from plugin.agent.decision import DecisionEngine
    from plugin.agent.policy.prior import PolicyPrior

    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")
    eng = DecisionEngine(prior=PolicyPrior.load())

    # List → Type
    wm = _seed_world(
        [
            _entity(1, etype="button", label="Chats"),
            _entity(2, etype="static", label="Search"),
            _entity(3, etype="button", label="Alice"),
        ]
    )
    a1 = next_action(goal, wm, ExecutionState(), worldview_score=1.0)
    # Force engine path consistency
    a1b = eng.decide(goal, wm, ExecutionState())
    assert a1 is not None and a1.action == "Type" and a1.text == "Pallavi"
    assert a1b is not None and a1b.action == "Type"

    # Search focused empty → Type
    wm2 = _seed_world(
        [
            _entity(1, etype="textfield", label="Search", role="AXTextField", value="", focused=True),
        ]
    )
    a2 = eng.decide(goal, wm2, ExecutionState())
    assert a2 is not None and a2.action == "Type" and a2.text == "Pallavi"

    # Query + contact → OpenContact
    wm3 = _seed_world(
        [
            _entity(1, etype="textfield", label="Search", role="AXTextField", value="Pallavi", focused=True),
            _entity(2, etype="button", label="Pallavi"),
        ]
    )
    a3 = eng.decide(goal, wm3, ExecutionState())
    assert a3 is not None and a3.action == "Click" and a3.semantic_target == "Pallavi"

    # Conversation + Voice call → StartVoiceCall
    wm4 = _seed_world(
        [
            _entity(1, etype="static", label="Messages in chat with Pallavi"),
            _entity(2, etype="textfield", label="Compose message", role="AXTextField"),
            _entity(3, etype="button", label="Voice call"),
        ]
    )
    a4 = eng.decide(goal, wm4, ExecutionState())
    assert a4 is not None and a4.action == "Click" and a4.semantic_target in {"Call", "Voice call"}

    # Ringing → None
    wm5 = _seed_world(
        [
            _entity(1, etype="button", label="End call", bounds=(900, 700, 80, 40)),
            _entity(2, etype="static", label="Calling Pallavi", bounds=(500, 100, 200, 30)),
        ]
    )
    a5 = eng.decide(goal, wm5, ExecutionState())
    assert a5 is None


def test_call_picker_branch_prefers_voice_over_observe():
    from plugin.agent.decision import DecisionEngine

    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")
    wm = _seed_world(
        [
            _entity(1, etype="static", label="Messages in chat with Pallavi"),
            _entity(2, etype="button", label="Video"),
            _entity(3, etype="button", label="Voice"),
            _entity(4, etype="button", label="Select people"),
        ]
    )

    ex = ExecutionState()
    ex.interaction_context = InteractionContext(
        selected_target="Pallavi",
        target_confidence=0.8,
        originating_world="w1",
        active_surface="call_picker",
        open_conversation=ContextualBelief(
            value=True,
            confidence=0.8,
            observability="not_currently_observable",
            last_confirmed_world="w1",
        ),
        reversible=True,
    )
    ex.exploration_branch = ExplorationBranch(
        origin_state="w1",
        entry_action="start_call:Call:",
        current_state="w2",
        active_surface="call_picker",
        last_surface="conversation",
        depth=2,
        active=True,
        newly_relevant_affordances=["initiate_voice", "select_participants"],
    )

    decision = DecisionEngine().decide(goal, wm, ex)

    assert decision is not None
    assert decision.action_family == "start_call"
    assert decision.semantic_target in {"Voice", "Voice call", "Call"}
    assert ex.exploration_branch.frontier
    assert ex.exploration_branch.frontier[0].action_family == "start_call"
    assert ex.exploration_branch.frontier[0].semantic_target in {"Voice", "Voice call", "Call"}


def test_revealed_forward_action_biases_next_branch_choice(monkeypatch):
    from plugin.agent.decision import DecisionEngine
    from plugin.agent.features import StateFeatures

    class FakeOverlay:
        def raw_view_dict(self, world):
            return {}

        def view_dict(self, world):
            return {}

        def features(self, world, goal, worldview_score=1.0):
            feats = StateFeatures(
                app="WhatsApp",
                screen_kind="conversation",
                screen_bucket="conversation",
                conversation_open=True,
                has_named_entity=True,
                goal_progress=0.35,
                worldview_score=worldview_score,
            )
            ft = ForwardTaskState()
            ft.predicates.source_conversation_open = True
            ft.predicates.source_conversation_visible = True
            ft.predicates.source_object_visible = True
            ft.predicates.source_object_selected = True
            ft.predicates.forward_surface_open = True
            ft.binding("source_object").status = "confirmed"
            ft.binding("source_object").resolved_entity_id = 1
            ft.binding("source_object").confidence = 0.9
            ft.derived_phase = "OPEN_FORWARD"
            feats.extras.update(
                {
                    "forward_phase": ft.derived_phase,
                    "forward_task": ft.to_dict(),
                    "active_surface": "conversation",
                    "branch_active": True,
                    "branch_affordances": ["ForwardMessage", "RevealHiddenActions"],
                    "open_conversation": "Kulvinder Ji",
                    "result_surface_visible": True,
                }
            )
            return feats

    monkeypatch.setattr("plugin.agent.decision.get_overlay", lambda app, world: FakeOverlay())

    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zarooratwala")
    wm = _seed_world(
        [
            _entity(1, etype="button", label="Forward"),
            _entity(2, etype="button", label="Reply"),
            _entity(3, etype="static", label="Zarooratwala"),
        ]
    )
    ex = ExecutionState()
    ex.exploration_branch = ExplorationBranch(
        active=True,
        active_surface="conversation",
        newly_relevant_affordances=["ForwardMessage"],
        depth=1,
    )

    decision = DecisionEngine().decide(goal, wm, ex)

    assert decision is not None
    assert decision.action_family == "forward_message"
    assert ex.exploration_branch.frontier
    assert ex.exploration_branch.frontier[0].action_family == "forward_message"


def test_closed_loop_planner_reentry_count(monkeypatch):
    """Planner invocations must be >= executed actions (re-entry each cycle)."""
    auxiliary_client, token = _mock_perception_llm(monkeypatch)
    runtime = RuntimeState()
    execu = ScriptedExecutor()
    phase = {"name": "list"}

    def observe() -> Observation:
        if phase["name"] == "list":
            ents = [
                _entity(1, etype="button", label="Chats"),
                _entity(2, etype="static", label="Search"),
            ]
        elif phase["name"] == "search":
            ents = [
                _entity(1, etype="textfield", label="Search", role="AXTextField", value="", focused=True),
            ]
        elif phase["name"] == "typed":
            ents = [
                _entity(1, etype="textfield", label="Search", role="AXTextField", value="Pallavi", focused=True),
                _entity(2, etype="button", label="Pallavi"),
            ]
        elif phase["name"] == "chat":
            ents = [
                _entity(1, etype="static", label="Messages in chat with Pallavi"),
                _entity(2, etype="textfield", label="Compose message", role="AXTextField"),
                _entity(3, etype="button", label="Voice call"),
            ]
        else:
            ents = [
                _entity(1, etype="button", label="End call"),
                _entity(2, etype="static", label="Calling Pallavi", role="AXStaticText"),
            ]
        return _obs(
            "WhatsApp",
            [
                AxNode(
                    role=e.role,
                    name=e.label,
                    description=e.semantic_role,
                    value=str(e.attributes.get("value") or "") or None,
                    attributes=dict(e.attributes),
                )
                for e in ents
            ],
        )

    class AdvancingExecutor(ScriptedExecutor):
        def execute(self, step: PlanStep) -> ExecResult:
            r = super().execute(step)
            # Advance world after successful action
            if step.action.lower() == "type":
                phase["name"] = "typed"
            elif step.action.lower() == "click" and step.semantic_target == "Search":
                phase["name"] = "search"
            elif step.action.lower() == "click" and step.semantic_target == "Pallavi":
                phase["name"] = "chat"
            elif step.action.lower() == "click" and step.semantic_target in {"Call", "Voice call"}:
                phase["name"] = "ringing"
            return r

    adv = AdvancingExecutor()
    try:
        result = run_goal_closed_loop(
            runtime,
            Goal(kind="whatsapp_voice_call", contact="Pallavi", require_contact_in_call=False),
            observe=observe,
            execute=adv,
            log=None,
            max_iterations=12,
            settle_s=0.0,
            wait_fn=lambda *_a, **_k: None,
        )
        assert runtime.execution_state.planner_invocations >= len(adv.calls)
        assert runtime.execution_state.planner_invocations >= 3
        assert len(adv.calls) >= 3
    finally:
        auxiliary_client.reset_runtime_main(token)


def test_verification_rejects_executor_ok_without_query():
    """ax_type returns ok but UI unchanged → NO_EFFECT → suppress retype thrash, try alternatives."""
    search_empty = [
        _entity(1, etype="textfield", label="Search", role="AXTextField", value="", focused=True),
    ]
    runtime = RuntimeState()
    runtime.world_model = _seed_world(search_empty)
    execu = ScriptedExecutor(fail_type_silently=True)

    def observe() -> Observation:
        # Always empty search — never lands query
        nodes = [
            AxNode(
                role="AXTextField",
                name="Search",
                description="Search",
                value="",
                attributes={"focused": True},
            )
        ]
        return _obs("WhatsApp", nodes)

    result = run_goal_closed_loop(
        runtime,
        Goal(kind="whatsapp_voice_call", contact="Pallavi"),
        observe=observe,
        execute=execu,
        max_iterations=5,
        settle_s=0.0,
        wait_fn=lambda *_a, **_k: None,
    )
    assert not result.ok
    type_calls = [c for c in execu.calls if c.action.lower() == "type"]
    # Transition loop: first Type → NO_EFFECT → suppress same action (no thrash)
    assert len(type_calls) >= 1
    assert len(type_calls) <= 2
    assert runtime.execution_state.planner_invocations >= 2
    # Experience should remember ineffective type
    assert runtime.execution_state.last_transition is not None
    assert runtime.execution_state.last_transition.get("outcome") in {
        "no_effect",
        "uncertain",
        "regression",
        "progress",
    }


def test_failed_transition_triggers_richer_reobserve_once():
    from plugin.agent.action import Action
    from plugin.agent.controller import _maybe_richer_reobserve_after_transition
    from plugin.agent import perception_cycle
    from plugin.agent.transition.types import TransitionAttempt, TransitionOutcome

    runtime = RuntimeState()
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder")
    runtime.world_model = _seed_world(
        [
            _entity(1, etype="textfield", label="Search", role="AXTextField", value="Kulvinder", focused=True),
        ]
    )
    after_view = {
        "screen": "SEARCH",
        "search_query": "Kulvinder",
        "open_conversation": "",
        "world_signature": "sig-1",
    }
    after_features = {
        "query_matches_goal": True,
        "search_query": "Kulvinder",
        "extras": {
            "forward_phase": "FIND_LINK",
            "open_conversation": "",
        },
    }
    decision = Action(action="Click", action_family="open_contact", semantic_target="Kulvinder Ji")
    attempt = TransitionAttempt(
        before_world_id="w0",
        after_world_id="w0",
        action_family="open_contact",
        outcome=TransitionOutcome.NO_EFFECT.value,
    )
    calls = {"n": 0}
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(perception_cycle, "synthesize_perception", lambda *args, **kwargs: None)

    def observe():
        calls["n"] += 1
        return Observation(
            timestamp=0.0,
            app_name="WhatsApp",
            window_name="WhatsApp",
            nodes=[
                AxNode(
                    role="AXStaticText",
                    name="Messages in chat with Kulvinder Ji",
                    description="Messages in chat with Kulvinder Ji",
                )
            ],
            screenshot_path="/tmp/richer.png",
            source="fallback",
            coverage=1.0,
        )

    richer_view, richer_features, _, used = _maybe_richer_reobserve_after_transition(
        runtime,
        goal,
        decision=decision,
        attempt=attempt,
        after_view=after_view,
        after_features=after_features,
        post_wv=0.6,
        observe=observe,
        log=None,
        iteration=1,
    )

    assert used is True
    assert calls["n"] == 1
    assert richer_view.get("open_conversation")
    assert richer_features.get("extras", {}).get("open_conversation")
    monkeypatch.undo()


def test_no_fixed_plan_skips_search_when_chat_open():
    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")
    ex = ExecutionState()
    wm = _seed_world(
        [
            _entity(1, etype="static", label="Messages in chat with Pallavi"),
            _entity(2, etype="textfield", label="Compose message", role="AXTextField"),
            _entity(3, etype="button", label="Voice call"),
        ]
    )
    step = next_action(goal, wm, ex)
    assert step is not None
    assert step.action == "Click"
    assert step.semantic_target in {"Call", "Voice call"}
    assert step.semantic_target != "Search"


def test_no_results_does_not_click_contact():
    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")
    ex = ExecutionState()
    wm = _seed_world(
        [
            _entity(1, etype="textfield", label="Search", role="AXTextField", value="Pallavi", focused=True),
            # no Pallavi button
            _entity(2, etype="static", label="No results found"),
        ]
    )
    step = next_action(goal, wm, ex)
    assert step is not None
    # Should Observe or retype — not Click Pallavi
    assert not (step.action == "Click" and step.semantic_target == "Pallavi")


def test_visible_search_result_row_is_explored_before_refinement():
    from plugin.agent.decision import DecisionEngine

    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    wm = _seed_world(
        [
            _entity(1, etype="textfield", label="Search", role="AXTextField", value="Now", focused=True),
            _entity(2, etype="button", label="Now…"),
            _entity(3, etype="button", label="Voice"),
        ]
    )
    ex = ExecutionState()
    decision = DecisionEngine().decide(goal, wm, ex)
    assert decision is not None
    assert decision.action_family == "open_contact"
    assert decision.semantic_target in {"Now…", "Now"}


def test_high_confidence_perception_promotes_open_contact_when_frontier_collapses(monkeypatch):
    from plugin.agent.decision import DecisionEngine
    from plugin.agent.perception_synthesis import PerceptionSynthesis

    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zarooratwala")
    wm = _seed_world([])
    ex = ExecutionState()

    def fake_synthesize_perception(*_args, **_kwargs):
        return PerceptionSynthesis(
            screen_type="list",
            active_surface="conversation",
            likely_next_family="open_contact",
            likely_next_target="Kulvinder Ji",
            likely_next_text="",
            confidence=0.88,
            supporting_evidence=["perception suggests opening the source conversation"],
            raw={"fake": True},
        )

    monkeypatch.setattr("plugin.agent.decision.synthesize_perception", fake_synthesize_perception)

    decision = DecisionEngine().decide(goal, wm, ex)
    assert decision is not None
    assert decision.action_family == "open_contact"
    assert decision.semantic_target == "Kulvinder Ji"


def test_perception_open_contact_beats_search_type_when_both_are_available(monkeypatch):
    from plugin.agent.decision import DecisionEngine
    from plugin.agent.perception_synthesis import PerceptionSynthesis

    goal = Goal(kind="whatsapp_voice_call", contact="Kulvinder")
    wm = _seed_world(
        [
            _entity(1, etype="textfield", label="Search", role="AXTextField", value="", focused=False),
            _entity(2, etype="button", label="Kulvinder Ji", role="AXButton"),
        ]
    )
    ex = ExecutionState()

    def fake_synthesize_perception(*_args, **_kwargs):
        return PerceptionSynthesis(
            screen_type="list",
            active_surface="conversation",
            likely_next_family="open_contact",
            likely_next_target="Kulvinder Ji",
            likely_next_text="",
            confidence=0.84,
            supporting_evidence=["perception prefers opening the contact row"],
            raw={"fake": True},
        )

    monkeypatch.setattr("plugin.agent.decision.synthesize_perception", fake_synthesize_perception)

    decision = DecisionEngine().decide(goal, wm, ex)
    assert decision is not None
    assert decision.action_family == "open_contact"
    assert decision.semantic_target == "Kulvinder Ji"


def test_empty_first_search_hypothesis_advances_to_next_hypothesis():
    """Confirmed empty after settled observe may advance spelling — not on type_query itself."""
    from plugin.agent.controller import _maybe_advance_search_hypothesis
    from plugin.agent.action import Action

    runtime = RuntimeState()
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    feats = {
        "query_matches_goal": True,
        "extras": {
            "resolution_policy": "ask",
            "resolution_confidence": 0.0,
            "contact_candidates": [],
            "search_result_rows": [],
            "result_surface_visible": False,
            "search_query": "Now",
        },
    }
    # type_query must NOT advance
    assert not _maybe_advance_search_hypothesis(
        runtime,
        goal,
        decision=Action(action="Type", text="Now", action_family="type_query"),
        after_view={"search_query": "Now"},
        after_features=feats,
        log=None,
        iteration=1,
        perception_settled=True,
    )
    # observe after confirmed empty MAY advance
    assert _maybe_advance_search_hypothesis(
        runtime,
        goal,
        decision=Action(action="Observe", action_family="observe"),
        after_view={"search_query": "Now"},
        after_features=feats,
        log=None,
        iteration=2,
        perception_settled=True,
    )
    assert runtime.execution_state.search_hypothesis_index >= 1


def test_search_results_surface_blocks_hypothesis_advance():
    from plugin.agent.controller import _maybe_advance_search_hypothesis
    from plugin.agent.action import Action
    from plugin.agent.features import StateFeatures

    runtime = RuntimeState()
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    runtime.execution_state.search_hypothesis_index = 0
    after_view = {"search_query": "Now", "screen": "SEARCH_RESULTS"}
    # Production shape: nested extras (StateFeatures.to_dict)
    after_features = StateFeatures(
        query_matches_goal=True,
        screen_bucket="search",
        extras={
            "resolution_policy": "ask",
            "resolution_confidence": 0.0,
            "contact_candidates": [],
            "result_surface_visible": True,
            "search_result_rows": ["Now…"],
            "search_query": "Now",
        },
    ).to_dict()
    advanced = _maybe_advance_search_hypothesis(
        runtime,
        goal,
        decision=Action(action="Type", semantic_target="Search", text="Now", action_family="type_query"),
        after_view=after_view,
        after_features=after_features,
        log=None,
        iteration=1,
        perception_settled=True,
    )
    assert advanced is False
    assert runtime.execution_state.search_hypothesis_index == 0


def test_end_call_with_chat_list_is_not_ringing():
    """Stale End Call AX node alongside chat list must not block the goal."""
    wm = _seed_world(
        [
            _entity(1, etype="button", label="End call"),
            _entity(2, etype="group", label="List of chats", role="AXGroup"),
            _entity(3, etype="button", label="Chats"),
            _entity(4, etype="static", label="Search"),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.call_state != "ringing"
    assert view.screen == "LIST"
    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")
    step = next_action(goal, wm, ExecutionState())
    assert step is not None
    assert step.action == "Type"
    assert step.text == "Pallavi"


def test_leftover_call_without_contact_is_not_success():
    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")
    wm = _seed_world(
        [
            _entity(1, etype="button", label="End call"),
            _entity(2, etype="static", label="Calling Someone Else"),
        ]
    )
    status = evaluate_goal(goal, wm)
    assert not status.succeeded
    step = next_action(goal, wm, ExecutionState())
    assert step is not None
    assert "end" in step.semantic_target.lower()


def test_ringing_with_contact_is_success():
    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")
    wm = _seed_world(
        [
            _entity(1, etype="button", label="End call"),
            _entity(2, etype="static", label="Calling Pallavi"),
        ]
    )
    status = evaluate_goal(goal, wm)
    assert status.succeeded


def test_electron_static_search_mirror_and_description_contact():
    """WhatsApp Electron: query as static title=Pallavi desc=Search; contact in button description."""
    wm = _seed_world(
        [
            _entity(1, etype="static", label="Pallavi", role="AXStaticText", description="Search"),
            _entity(
                2,
                etype="button",
                label="Hey, message, 2:14 PM",
                role="AXButton",
                description="Pallavi",
            ),
            _entity(3, etype="textfield", label="Compose message", role="AXTextField"),
            _entity(4, etype="button", label="Updates"),
            _entity(5, etype="button", label="Papaji"),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.search_query.lower() == "pallavi"
    assert view.screen == "SEARCH_RESULTS"
    assert any(c.lower() == "pallavi" for c in view.visible_contacts)
    assert SearchQueryEquals("Pallavi").evaluate(wm).passed
    assert ContactResultVisible("Pallavi").evaluate(wm).passed

    step = next_action(Goal(kind="whatsapp_voice_call", contact="Pallavi"), wm, ExecutionState())
    assert step is not None
    assert step.action == "Click"
    assert step.semantic_target == "Pallavi"


def test_composer_does_not_hide_search_overlay():
    wm = _seed_world(
        [
            _entity(1, etype="static", label="Pallavi", role="AXStaticText", description="Search"),
            _entity(2, etype="textfield", label="Compose message", role="AXTextField"),
            _entity(3, etype="static", label="Messages in chat with Papaji"),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.composer_visible
    assert view.search_query.lower() == "pallavi"
    assert view.screen != "CONVERSATION"
    assert view.screen == "SEARCH_RESULTS"


def test_soft_evidence_advances_to_click_contact(monkeypatch):
    """Executor proves typed query; post-view may miss it — soft hint still opens contact."""
    auxiliary_client, token = _mock_perception_llm(monkeypatch)
    from plugin.agent.controller import parse_typed_query_evidence

    evidence = "typed 'Pallavi' … evidence=\"AXStaticText title='Pallavi' desc='Search'\""
    assert parse_typed_query_evidence(evidence, "Pallavi").lower() == "pallavi"

    runtime = RuntimeState()
    execu = ScriptedExecutor()
    phase = {"name": "list"}

    def observe() -> Observation:
        if phase["name"] == "list":
            ents = [
                _entity(1, etype="button", label="Chats"),
                _entity(2, etype="static", label="Search"),
            ]
        elif phase["name"] == "typed_missing_query":
            # Ingest loses query (no search mirror) but contact row is description-based
            ents = [
                _entity(1, etype="textfield", label="Compose message", role="AXTextField"),
                _entity(
                    2,
                    etype="button",
                    label="Hey, message, 2:14 PM",
                    description="Pallavi",
                ),
            ]
        elif phase["name"] == "chat":
            ents = [
                _entity(1, etype="static", label="Messages in chat with Pallavi"),
                _entity(2, etype="textfield", label="Compose message", role="AXTextField"),
                _entity(3, etype="button", label="Voice call"),
            ]
        else:
            ents = [
                _entity(1, etype="button", label="End call"),
                _entity(2, etype="static", label="Calling Pallavi"),
            ]
        return _obs(
            "WhatsApp",
            [
                AxNode(
                    role=e.role,
                    name=e.label,
                    description=str(e.attributes.get("description") or ""),
                    value=str(e.attributes.get("value") or "") or None,
                    attributes=dict(e.attributes),
                )
                for e in ents
            ],
        )

    class SoftEvidenceExecutor(ScriptedExecutor):
        def execute(self, step: PlanStep) -> ExecResult:
            self.calls.append(step)
            if step.action.lower() == "type":
                phase["name"] = "typed_missing_query"
                return ExecResult(
                    ok=True,
                    backend="ax",
                    message="typed 'Pallavi' evidence=\"AXStaticText title='Pallavi' desc='Search'\"",
                )
            if step.action.lower() == "click" and step.semantic_target == "Pallavi":
                phase["name"] = "chat"
            elif step.action.lower() == "click" and step.semantic_target in {"Call", "Voice call"}:
                phase["name"] = "ringing"
            return ExecResult(ok=True, backend="fake", message=f"ok {step.action}")

    adv = SoftEvidenceExecutor()
    try:
        result = run_goal_closed_loop(
            runtime,
            Goal(kind="whatsapp_voice_call", contact="Pallavi", require_contact_in_call=False),
            observe=observe,
            execute=adv,
            log=None,
            max_iterations=12,
            settle_s=0.0,
            wait_fn=lambda *_a, **_k: None,
        )
        assert result.ok, (result, [c.__dict__ for c in adv.calls])
        click_contact = [c for c in adv.calls if c.action == "Click" and c.semantic_target == "Pallavi"]
        assert click_contact, [c.__dict__ for c in adv.calls]
        type_calls = [c for c in adv.calls if c.action.lower() == "type"]
        assert len(type_calls) <= 1
    finally:
        auxiliary_client.reset_runtime_main(token)


def test_contact_ranking_prefers_exact_and_flags_ambiguity():
    from plugin.agent.whatsapp_view import rank_contact_candidates, resolve_contact_entity

    wm = _seed_world(
        [
            _entity(1, etype="button", label="Plugin Support Bot", description="Plugin Support Bot"),
            _entity(2, etype="button", label="Plugin Support", description="Plugin Support"),
            _entity(3, etype="button", label="Pallavi", description="Pallavi"),
        ]
    )
    ranked = rank_contact_candidates(wm, "plugin support")
    assert ranked
    assert ranked[0]["name"].lower() == "plugin support"
    # Clear exact winner
    ent = resolve_contact_entity(wm, "Plugin Support")
    assert ent is not None and "plugin support" in (ent.label or "").lower()

    # Near-tie ambiguity
    wm2 = _seed_world(
        [
            _entity(1, etype="button", label="Support Team A", description="Support Team A"),
            _entity(2, etype="button", label="Support Team B", description="Support Team B"),
        ]
    )
    assert resolve_contact_entity(wm2, "Support Team") is None
    assert len(rank_contact_candidates(wm2, "Support Team")) >= 2


def test_resolve_contact_prefers_button_not_search_mirror():
    from plugin.agent.whatsapp_view import resolve_contact_entity
    from plugin.experiments.call_pallavi import find_action_target

    wm = _seed_world(
        [
            _entity(1, etype="static", label="Pallavi", role="AXStaticText", description="Search"),
            _entity(
                2,
                etype="button",
                label="Pallavi",
                role="AXButton",
                description="Pallavi",
            ),
            _entity(3, etype="button", label="Pallavi Ather Gen3", description="Pallavi Ather Gen3"),
        ]
    )
    # Give search mirror top-bar-ish bounds; contact row lower
    wm.entities[1].bounds = (100.0, 50.0, 80.0, 20.0)
    wm.entities[2].bounds = (40.0, 220.0, 300.0, 48.0)
    wm.entities[3].bounds = (40.0, 280.0, 300.0, 48.0)
    ent = resolve_contact_entity(wm, "Pallavi")
    assert ent is not None and ent.id == 2
    ent2 = find_action_target(wm, "Pallavi", "click")
    assert ent2 is not None and ent2.id == 2


def test_normalize_preserves_description():
    from plugin.worldmodel.entities.normalize import normalize_node

    node = AxNode(
        role="AXButton",
        name="Hey, message, 2:14 PM",
        description="Pallavi",
        value=None,
        attributes={},
    )
    ent = normalize_node(node, 1)
    assert ent.label.startswith("Hey")
    assert ent.attributes.get("description") == "Pallavi"


def test_log_ordering_phases(tmp_path):
    from plugin.experiments.logger import EventLogger

    list_ui = [_entity(1, etype="static", label="Search"), _entity(2, etype="button", label="Chats")]
    search_ui = [_entity(1, etype="textfield", label="Search", role="AXTextField", value="", focused=True)]
    typed = [
        _entity(1, etype="textfield", label="Search", role="AXTextField", value="Pallavi", focused=True),
        _entity(2, etype="button", label="Pallavi"),
    ]
    chat = [
        _entity(1, etype="static", label="Messages in chat with Pallavi"),
        _entity(2, etype="textfield", label="Compose message", role="AXTextField"),
        _entity(3, etype="button", label="Voice call"),
    ]
    ringing = [_entity(1, etype="button", label="End call"), _entity(2, etype="static", label="Calling")]

    seq = {"i": 0}
    frames = [list_ui, search_ui, search_ui, typed, typed, chat, chat, ringing, ringing]

    def observe() -> Observation:
        ents = frames[min(seq["i"], len(frames) - 1)]
        seq["i"] += 1
        return _obs(
            "WhatsApp",
            [
                AxNode(
                    role=e.role,
                    name=e.label,
                    value=str(e.attributes.get("value") or "") or None,
                    attributes=dict(e.attributes),
                )
                for e in ents
            ],
        )

    log = EventLogger(tmp_path / "closed.jsonl", also_console=False)
    runtime = RuntimeState()
    run_goal_closed_loop(
        runtime,
        Goal(kind="whatsapp_voice_call", contact="Pallavi"),
        observe=observe,
        execute=ScriptedExecutor(),
        log=log,
        max_iterations=10,
        settle_s=0.0,
        wait_fn=lambda *_a, **_k: None,
    )
    kinds = []
    for line in (tmp_path / "closed.jsonl").read_text().splitlines():
        import json

        kinds.append(json.loads(line).get("kind"))
    # Must see the closed-loop cycle kinds
    for required in (
        "observation",
        "world_patch",
        "goal_status",
        "decision_engine",
        "planner_decision",
        "execution",
        "post_observation",
        "post_world_patch",
        "verification",
    ):
        assert required in kinds, f"missing {required} in {kinds}"


def test_worldview_score_on_ingest():
    from plugin.worldmodel.score import compute_worldview_score

    wm = WorldModel()
    nodes = [
        AxNode(role="AXButton", name="Pallavi", description="Pallavi"),
        AxNode(role="AXTextField", name="Search", value="Pallavi"),
    ]
    obs = _obs("WhatsApp", nodes)
    patch = wm.ingest(obs)
    assert patch.worldview_score is not None
    assert 0.0 <= patch.worldview_score["overall"] <= 1.0
    assert wm.last_worldview_score.get("overall") == patch.worldview_score["overall"]


def test_fuse_single_source_agreement():
    from plugin.perception.fusion.fuse import fuse_observations
    from plugin.perception.sources.base import ObservationBundle

    nodes = [
        AxNode(role="AXButton", name="Pallavi", bbox=(10, 100, 200, 40)),
        AxNode(role="AXTextField", name="Search", bbox=(10, 40, 200, 30)),
    ]
    obs = _obs("WhatsApp", nodes)
    obs.source = "pyobjc_ax"
    bundle = ObservationBundle(source_id="pyobjc_ax", observation=obs, coverage_self=1.0)
    fused, report = fuse_observations([bundle], app="WhatsApp")
    assert len(fused.nodes) == 2
    assert report.agreement >= 0.5
    assert "fusion" in (fused.meta or {})


def test_ax_type_refuses_label_only_search_surface(monkeypatch):
    calls = {"paste": 0, "cgevent": 0}

    monkeypatch.setattr(ax_action, "ax_available", lambda: True)
    monkeypatch.setattr(ax_action, "_activate_app", lambda _app: None)
    monkeypatch.setattr(ax_action, "_open_search_ui", lambda _app, bounds=None: "Cmd+F search shortcut")
    monkeypatch.setattr(ax_action, "_find_search_text_field", lambda _app: (None, ""))
    monkeypatch.setattr(ax_action, "_find_element", lambda *_a, **_k: None)

    def _forbid_paste(*_a, **_k):
        calls["paste"] += 1
        raise AssertionError("clipboard fallback should not run without a confirmed editable field")

    def _forbid_cgevent(*_a, **_k):
        calls["cgevent"] += 1
        raise AssertionError("CGEvent fallback should not run without a confirmed editable field")

    monkeypatch.setattr(ax_action, "_paste_via_clipboard", _forbid_paste)
    monkeypatch.setattr(ax_action, "_type_via_cgevent", _forbid_cgevent)

    result = ax_action.ax_type("WhatsApp", "Kulvinder", into="Search")

    assert not result.ok
    assert "editable field" in result.message.lower()
    assert calls == {"paste": 0, "cgevent": 0}
