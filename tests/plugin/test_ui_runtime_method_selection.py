"""Stage A goldens: TUI→AgentRuntime cutover, availability ⊥ quality, resumable ASK."""

from __future__ import annotations

from typing import Any, Optional, Sequence

import pytest

from plugin.agent.executive.intention_frame import MethodSpec
from plugin.agent.executive.method_availability import (
    MethodAvailability,
    MethodReadiness,
    evaluate_method_availability,
    should_ask_for_precondition,
)
from plugin.agent.executive.method_providers import (
    TaskInterpretation,
    clear_method_providers,
    discover_methods,
    register_method_provider,
)
from plugin.agent.ingress import (
    ExecutionConstraints,
    SessionRef,
    TaskIngress,
    TaskRequest,
    semantic_task_fingerprint,
)
from plugin.agent.runtime.agent_runtime import AgentRuntime
from plugin.agent.runtime.session_store import reset_session_store
from plugin.agent.runtime.state import RuntimeState
from plugin.agent.runtime.turn_result import TurnStatus


@pytest.fixture(autouse=True)
def _clean_providers_and_sessions():
    clear_method_providers()
    reset_session_store()
    yield
    clear_method_providers()
    reset_session_store()


class _CatalogProvider:
    def __init__(self, specs: Sequence[MethodSpec]):
        self.specs = list(specs)

    def discover(
        self,
        interpretation: TaskInterpretation,
        *,
        constraints: Optional[ExecutionConstraints] = None,
    ) -> Sequence[MethodSpec]:
        if "forward_message" not in interpretation.desired_effects and (
            "forward" not in interpretation.goal_kind
        ):
            # Still return for synthetic tests that set effects explicitly.
            if interpretation.desired_effects:
                return list(self.specs)
            return list(self.specs)
        return list(self.specs)


def _web_ready_missing_auth() -> MethodSpec:
    return MethodSpec(
        id="structured_web_forward",
        capability="forward_message",
        substrate="browser",
        provider="test_web",
        preconditions=["authenticated_integration"],
        readiness=MethodReadiness.READY.value,
        reliability=0.92,
        latency=0.2,
        risk=0.15,
        cost=0.2,
        user_interference=0.1,
        semantic_precision=0.9,
    )


def _web_unimplemented() -> MethodSpec:
    return MethodSpec(
        id="whatsapp_web_forward",
        capability="forward_message",
        substrate="browser",
        provider="whatsapp_web",
        preconditions=["authenticated_whatsapp_web"],
        readiness=MethodReadiness.UNAVAILABLE.value,
        reliability=0.95,
        latency=0.15,
        risk=0.1,
        cost=0.15,
        user_interference=0.05,
        semantic_precision=0.95,
    )


def _computer_use() -> MethodSpec:
    return MethodSpec(
        id="native_computer_use_forward",
        capability="forward_message",
        substrate="computer_use",
        provider="native_ui",
        preconditions=[],
        readiness=MethodReadiness.READY.value,
        reliability=0.55,
        latency=0.7,
        risk=0.55,
        cost=0.6,
        user_interference=0.85,
        semantic_precision=0.55,
    )


def test_all_tui_user_turns_enter_agent_runtime_before_legacy_conversation_routing() -> None:
    calls = {"n": 0}

    def runner(msg, **kwargs):
        calls["n"] += 1
        return {"final_response": f"echo:{msg}"}

    rt = AgentRuntime(runtime_state=RuntimeState())
    req = TaskIngress.normalize(
        TaskRequest(
            user_turn="hello there",
            session=SessionRef("tui-sess-1"),
            client_context={"client": "tui"},
        )
    )
    result = rt.handle_turn(req, conversation_runner=runner)
    assert result.status == TurnStatus.LEGACY_DELEGATED
    assert calls["n"] == 1
    assert result.acceptance_trace.get("session_id") == "tui-sess-1"
    assert result.acceptance_trace.get("client") == "tui"


def test_ui_adapter_does_not_choose_execution_substrate() -> None:
    """Client context label must not appear as selected_substrate."""
    register_method_provider(_CatalogProvider([_computer_use()]))
    rt = AgentRuntime(runtime_state=RuntimeState())
    req = TaskRequest(
        user_turn="Forward ZarooratWala link from Pallavi to Tanmay",
        session=SessionRef("s"),
        client_context={"client": "tui"},
    )
    # Force interpretation effects via legacy goal-like provider match.
    from plugin.agent.goal import Goal

    req.legacy_goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        prompt=req.user_turn,
    )
    result = rt.handle_turn(req)
    assert result.selected_substrate == "computer_use"
    assert result.selected_substrate != "tui"
    assert result.acceptance_trace.get("client") == "tui"


def test_same_task_request_and_constraints_yield_same_method_frontier() -> None:
    register_method_provider(_CatalogProvider([_web_unimplemented(), _computer_use()]))
    constraints = ExecutionConstraints()
    tui = TaskIngress.normalize(
        TaskRequest(
            user_turn="Forward the link to Tanmay",
            session=SessionRef("shared"),
            client_context={"client": "tui", "supports_rich_ui": True},
            constraints=constraints,
            legacy_goal=__import__("plugin.agent.goal", fromlist=["Goal"]).Goal(
                kind="whatsapp_forward_message", contact="Pallavi", prompt="Forward the link to Tanmay"
            ),
        )
    )
    desktop = TaskIngress.normalize(
        TaskRequest(
            user_turn="Forward the link to Tanmay",
            session=SessionRef("shared"),
            client_context={"client": "desktop", "supports_rich_ui": False},
            constraints=constraints,
            legacy_goal=tui.legacy_goal,
        )
    )
    assert semantic_task_fingerprint(tui) == semantic_task_fingerprint(desktop)
    r1 = AgentRuntime(runtime_state=RuntimeState()).handle_turn(tui)
    r2 = AgentRuntime(runtime_state=RuntimeState()).handle_turn(desktop)
    assert r1.selected_method == r2.selected_method
    assert r1.selected_substrate == r2.selected_substrate
    assert [m["id"] for m in r1.acceptance_trace["candidate_methods"]] == [
        m["id"] for m in r2.acceptance_trace["candidate_methods"]
    ]


def test_unimplemented_preferred_method_does_not_ask_for_prerequisite() -> None:
    register_method_provider(_CatalogProvider([_web_unimplemented(), _computer_use()]))
    web = _web_unimplemented()
    avail, reason = evaluate_method_availability(web)
    assert avail == MethodAvailability.UNSUPPORTED.value
    assert "implementation" in reason
    assert not should_ask_for_precondition(
        preferred_spec=web,
        preferred_availability=avail,
        best_available_quality=0.1,
    )
    rt = AgentRuntime(runtime_state=RuntimeState())
    from plugin.agent.goal import Goal

    result = rt.handle_turn(
        TaskRequest(
            user_turn="Forward ZarooratWala to Tanmay",
            session=SessionRef("no-ask"),
            legacy_goal=Goal(
                kind="whatsapp_forward_message",
                contact="Pallavi",
                prompt="Forward ZarooratWala to Tanmay",
            ),
        )
    )
    assert result.status != TurnStatus.WAITING_FOR_USER
    assert result.selected_substrate == "computer_use"
    cands = result.acceptance_trace["candidate_methods"]
    web_c = next(c for c in cands if c["id"] == "whatsapp_web_forward")
    assert web_c["availability"] == MethodAvailability.UNSUPPORTED.value


def test_preferred_ready_method_missing_user_prerequisite_can_ask_before_fallback() -> None:
    register_method_provider(
        _CatalogProvider([_web_ready_missing_auth(), _computer_use()])
    )
    rt = AgentRuntime(runtime_state=RuntimeState())
    from plugin.agent.goal import Goal

    result = rt.handle_turn(
        TaskRequest(
            user_turn="Forward ZarooratWala to Tanmay",
            session=SessionRef("ask-sess"),
            legacy_goal=Goal(
                kind="whatsapp_forward_message",
                contact="Pallavi",
                prompt="Forward ZarooratWala to Tanmay",
            ),
        )
    )
    assert result.status == TurnStatus.WAITING_FOR_USER
    assert "prerequisite" in (result.question or "").lower() or result.question
    assert result.acceptance_trace.get("missing_precondition") == "authenticated_integration"


def test_ask_returns_waiting_state_and_resumes_same_intention_on_next_turn() -> None:
    register_method_provider(
        _CatalogProvider([_web_ready_missing_auth(), _computer_use()])
    )
    rt = AgentRuntime(runtime_state=RuntimeState())
    from plugin.agent.goal import Goal

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        prompt="Forward ZarooratWala to Tanmay",
    )
    sess = SessionRef("resume-sess")
    first = rt.handle_turn(
        TaskRequest(user_turn=goal.prompt, session=sess, legacy_goal=goal)
    )
    assert first.status == TurnStatus.WAITING_FOR_USER
    intention = first.intention_id
    second = rt.handle_turn(
        TaskRequest(user_turn="no", session=sess, legacy_goal=goal)
    )
    assert second.status == TurnStatus.CONTINUED
    assert second.intention_id == intention
    assert second.selected_substrate == "computer_use"
    assert second.acceptance_trace.get("resumed_after") == "user_declined"


def test_user_declined_method_prerequisite_advances_method_frontier() -> None:
    register_method_provider(
        _CatalogProvider([_web_ready_missing_auth(), _computer_use()])
    )
    rt = AgentRuntime(runtime_state=RuntimeState())
    from plugin.agent.goal import Goal

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        prompt="Forward message",
    )
    sess = SessionRef("decline-sess")
    rt.handle_turn(TaskRequest(user_turn=goal.prompt, session=sess, legacy_goal=goal))
    result = rt.handle_turn(TaskRequest(user_turn="not now", session=sess, legacy_goal=goal))
    assert result.selected_method == "native_computer_use_forward"
    # Declined method must not be re-asked within scope.
    again = rt.handle_turn(
        TaskRequest(user_turn=goal.prompt, session=sess, legacy_goal=goal)
    )
    assert again.status != TurnStatus.WAITING_FOR_USER
    assert again.selected_method == "native_computer_use_forward"


def test_accepted_prerequisite_resumes_parent_intention() -> None:
    register_method_provider(
        _CatalogProvider([_web_ready_missing_auth(), _computer_use()])
    )
    rt = AgentRuntime(runtime_state=RuntimeState())
    from plugin.agent.goal import Goal

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        prompt="Forward message",
    )
    sess = SessionRef("accept-sess")
    first = rt.handle_turn(
        TaskRequest(user_turn=goal.prompt, session=sess, legacy_goal=goal)
    )
    intention = first.intention_id
    second = rt.handle_turn(TaskRequest(user_turn="yes", session=sess, legacy_goal=goal))
    assert second.status == TurnStatus.CONTINUED
    assert second.intention_id == intention
    assert second.selected_method == "structured_web_forward"
    assert second.acceptance_trace.get("resumed_after") == "user_accepted_prerequisite"


def test_forced_substrate_via_execution_constraints_not_harness_branch() -> None:
    register_method_provider(
        _CatalogProvider([_web_ready_missing_auth(), _computer_use()])
    )
    # Even with READY web missing auth, forced CU forbids browser and skips ASK
    # when CU is the only allowed substrate with AVAILABLE readiness.
    # Web becomes FORBIDDEN_BY_CONSTRAINT; CU AVAILABLE → select CU, no ASK.
    rt = AgentRuntime(runtime_state=RuntimeState())
    from plugin.agent.goal import Goal

    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        prompt="Forward message",
    )
    result = rt.handle_turn(
        TaskRequest(
            user_turn=goal.prompt,
            session=SessionRef("force-cu"),
            legacy_goal=goal,
            constraints=ExecutionConstraints(
                allowed_substrates=("computer_use",),
                forced_substrate="computer_use",
            ),
        )
    )
    assert result.status != TurnStatus.WAITING_FOR_USER
    assert result.selected_substrate == "computer_use"
    web = next(
        c
        for c in result.acceptance_trace["candidate_methods"]
        if c["id"] == "structured_web_forward"
    )
    assert web["availability"] == MethodAvailability.FORBIDDEN_BY_CONSTRAINT.value


def test_agent_runtime_has_no_whatsapp_forward_branch_source() -> None:
    import inspect
    from plugin.agent.runtime import agent_runtime as mod

    src = inspect.getsource(mod.AgentRuntime.handle_turn)
    assert "whatsapp" not in src.lower()
    assert "forward_message" not in src
    assert "zarooratwala" not in src.lower()
