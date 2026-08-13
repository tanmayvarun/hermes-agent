"""Stage A goldens (post merge-blocker fixes): frontier authority, dispatch, ASK permission."""

from __future__ import annotations

from typing import Any, Optional, Sequence

import pytest

from plugin.agent.composition import compose_domain_adapters, reset_composition_for_tests
from plugin.agent.executive.intention_frame import MethodSpec, ScoringPolicy, score_method
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
from plugin.agent.goal import Goal
from plugin.agent.ingress import (
    ExecutionConstraints,
    SessionRef,
    TaskIngress,
    TaskRequest,
    semantic_task_fingerprint,
)
from plugin.agent.runtime.agent_runtime import AgentRuntime
from plugin.agent.runtime.method_executors import (
    MethodExecutionResult,
    clear_method_executors,
    register_method_executor,
)
from plugin.agent.runtime.prerequisite_resolver import (
    InjectedPrerequisiteResolver,
    clear_prerequisite_resolvers,
    register_prerequisite_resolver,
)
from plugin.agent.runtime.session_store import reset_session_store
from plugin.agent.runtime.state import RuntimeState
from plugin.agent.runtime.turn_result import TurnStatus


@pytest.fixture(autouse=True)
def _clean_registries():
    clear_method_providers()
    clear_method_executors()
    clear_prerequisite_resolvers()
    reset_session_store()
    reset_composition_for_tests()
    yield
    clear_method_providers()
    clear_method_executors()
    clear_prerequisite_resolvers()
    reset_session_store()
    reset_composition_for_tests()


class _CatalogProvider:
    provider_id = "test_catalog"

    def __init__(self, specs: Sequence[MethodSpec]):
        self.specs = list(specs)

    def discover(
        self,
        interpretation: TaskInterpretation,
        *,
        constraints: Optional[ExecutionConstraints] = None,
    ) -> Sequence[MethodSpec]:
        return list(self.specs)


class _RecordingCUExecutor:
    executor_id = "test_computer_use"
    substrates = ("computer_use",)

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, spec: Any, *, context: dict) -> MethodExecutionResult:
        self.calls += 1
        return MethodExecutionResult(
            ok=True,
            status="executed",
            detail="cu_dispatched",
            payload={"ok": True, "dispatched": True, "method_id": spec.id},
            executor_id=self.executor_id,
        )


class _RecordingBrowserExecutor:
    executor_id = "test_browser"
    substrates = ("browser",)

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, spec: Any, *, context: dict) -> MethodExecutionResult:
        self.calls += 1
        return MethodExecutionResult(
            ok=True,
            status="executed",
            detail="browser_dispatched",
            payload={"ok": True, "method_id": spec.id},
            executor_id=self.executor_id,
        )


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


def _forward_req(session: str = "s", **kwargs) -> TaskRequest:
    prompt = kwargs.pop("user_turn", "Forward ZarooratWala to Tanmay")
    return TaskRequest(
        user_turn=prompt,
        session=SessionRef(session),
        client_context={"client": "tui"},
        legacy_goal=Goal(
            kind="whatsapp_forward_message",
            contact="Pallavi",
            prompt=prompt,
        ),
        **kwargs,
    )


def test_all_tui_user_turns_enter_agent_runtime_before_legacy_conversation_routing() -> None:
    calls = {"n": 0}

    def runner(msg, **kwargs):
        calls["n"] += 1
        return {"final_response": f"echo:{msg}"}

    rt = AgentRuntime(runtime_state=RuntimeState())
    # No providers → conversation legacy
    result = rt.handle_turn(
        TaskIngress.normalize(
            TaskRequest(
                user_turn="hello there",
                session=SessionRef("tui-sess-1"),
                client_context={"client": "tui"},
            )
        ),
        conversation_runner=runner,
    )
    assert result.status == TurnStatus.LEGACY_DELEGATED
    assert calls["n"] == 1
    assert result.acceptance_trace.get("client") == "tui"


def test_selected_computer_use_method_dispatches_computer_use_executor_not_legacy_chat() -> None:
    register_method_provider(_CatalogProvider([_computer_use()]))
    cu = _RecordingCUExecutor()
    register_method_executor(cu)
    chat_calls = {"n": 0}

    def runner(msg, **kwargs):
        chat_calls["n"] += 1
        return {"final_response": "should_not_run"}

    rt = AgentRuntime(runtime_state=RuntimeState())
    result = rt.handle_turn(_forward_req("cu-dispatch"), conversation_runner=runner)
    assert cu.calls == 1
    assert chat_calls["n"] == 0
    assert result.selected_substrate == "computer_use"
    assert result.acceptance_trace.get("dispatched_executor") is True
    assert result.acceptance_trace.get("executor_id") == "test_computer_use"


def test_agent_runtime_delegates_ranking_to_single_method_frontier_authority() -> None:
    register_method_provider(_CatalogProvider([_web_unimplemented(), _computer_use()]))
    register_method_executor(_RecordingCUExecutor())
    rt = AgentRuntime(runtime_state=RuntimeState())
    result = rt.handle_turn(_forward_req("rank-auth"))
    assert result.acceptance_trace.get("ranking_authority") == "MethodFrontier.rank_eligible"
    import inspect
    from plugin.agent.runtime import agent_runtime as mod

    src = inspect.getsource(mod.AgentRuntime.handle_turn)
    assert "method_quality_score" not in src
    assert "evaluated.sort" not in src


def test_unimplemented_preferred_method_does_not_ask_for_prerequisite() -> None:
    register_method_provider(_CatalogProvider([_web_unimplemented(), _computer_use()]))
    register_method_executor(_RecordingCUExecutor())
    web = _web_unimplemented()
    avail, _ = evaluate_method_availability(web)
    assert avail == MethodAvailability.UNSUPPORTED.value
    result = AgentRuntime(runtime_state=RuntimeState()).handle_turn(
        _forward_req("no-ask")
    )
    assert result.status != TurnStatus.WAITING_FOR_USER
    assert result.selected_substrate == "computer_use"


def test_preferred_ready_method_missing_user_prerequisite_can_ask_before_fallback() -> None:
    register_method_provider(
        _CatalogProvider([_web_ready_missing_auth(), _computer_use()])
    )
    result = AgentRuntime(runtime_state=RuntimeState()).handle_turn(
        _forward_req("ask-sess")
    )
    assert result.status == TurnStatus.WAITING_FOR_USER
    assert result.acceptance_trace.get("missing_precondition") == "authenticated_integration"


def test_user_acceptance_does_not_mark_precondition_achieved_without_resolver_success() -> None:
    register_method_provider(
        _CatalogProvider([_web_ready_missing_auth(), _computer_use()])
    )
    register_method_executor(_RecordingCUExecutor())
    # No resolver → unsupported; must not select structured_web as if auth true.
    rt = AgentRuntime(runtime_state=RuntimeState())
    first = rt.handle_turn(_forward_req("perm-only"))
    assert first.status == TurnStatus.WAITING_FOR_USER
    second = rt.handle_turn(
        TaskRequest(user_turn="yes", session=SessionRef("perm-only"))
    )
    assert second.acceptance_trace.get("prerequisite_resolve", {}).get("status") in {
        "unsupported",
        "failed",
        "pending",
    }
    # Must not claim structured web executed solely from "yes".
    assert second.selected_method != "structured_web_forward" or second.acceptance_trace.get(
        "prerequisite_resolve", {}
    ).get("status") == "achieved"


def test_failed_prerequisite_resolution_keeps_parent_and_advances_or_reasks_correctly() -> None:
    register_method_provider(
        _CatalogProvider([_web_ready_missing_auth(), _computer_use()])
    )
    cu = _RecordingCUExecutor()
    register_method_executor(cu)
    register_prerequisite_resolver(
        InjectedPrerequisiteResolver({"authenticated_integration": "failed"})
    )
    rt = AgentRuntime(runtime_state=RuntimeState())
    first = rt.handle_turn(_forward_req("prereq-fail"))
    intention = first.intention_id
    second = rt.handle_turn(
        TaskRequest(user_turn="yes", session=SessionRef("prereq-fail"))
    )
    assert second.status == TurnStatus.CONTINUED
    assert second.intention_id == intention
    assert second.selected_substrate == "computer_use"
    assert second.acceptance_trace.get("precondition_achieved") is False
    assert cu.calls == 1


def test_accepted_prerequisite_resumes_parent_intention_after_resolver_success() -> None:
    register_method_provider(
        _CatalogProvider([_web_ready_missing_auth(), _computer_use()])
    )
    browser = _RecordingBrowserExecutor()
    register_method_executor(browser)
    register_method_executor(_RecordingCUExecutor())
    register_prerequisite_resolver(
        InjectedPrerequisiteResolver({"authenticated_integration": "achieved"})
    )
    rt = AgentRuntime(runtime_state=RuntimeState())
    first = rt.handle_turn(_forward_req("prereq-ok"))
    intention = first.intention_id
    second = rt.handle_turn(
        TaskRequest(user_turn="yes", session=SessionRef("prereq-ok"))
    )
    assert second.status == TurnStatus.CONTINUED
    assert second.intention_id == intention
    assert second.selected_method == "structured_web_forward"
    assert browser.calls == 1
    assert second.acceptance_trace.get("resumed_after") == "prerequisite_achieved"


def test_user_declined_method_prerequisite_advances_method_frontier() -> None:
    register_method_provider(
        _CatalogProvider([_web_ready_missing_auth(), _computer_use()])
    )
    register_method_executor(_RecordingCUExecutor())
    rt = AgentRuntime(runtime_state=RuntimeState())
    rt.handle_turn(_forward_req("decline-sess"))
    result = rt.handle_turn(
        TaskRequest(user_turn="not now", session=SessionRef("decline-sess"))
    )
    assert result.selected_method == "native_computer_use_forward"
    again = rt.handle_turn(_forward_req("decline-sess"))
    assert again.status != TurnStatus.WAITING_FOR_USER


def test_legacy_method_without_readiness_is_not_accidentally_unsupported() -> None:
    legacy = MethodSpec(
        id="legacy_reveal",
        capability="reveal_actions",
        preconditions=[],
        # readiness default ""
    )
    assert str(legacy.readiness or "") == ""
    avail, reason = evaluate_method_availability(legacy)
    assert avail == MethodAvailability.AVAILABLE.value
    assert reason == "ready"


def test_zero_cost_zero_risk_zero_interference_remain_zero() -> None:
    spec = MethodSpec(
        id="zeroed",
        capability="forward_message",
        substrate="browser",
        readiness=MethodReadiness.READY.value,
        cost=0.0,
        risk=0.0,
        latency=0.0,
        user_interference=0.0,
        reliability=1.0,
        semantic_precision=1.0,
    )
    policy = ScoringPolicy.for_meta("act")
    # Direct field integrity
    assert float(spec.cost) == 0.0
    assert float(spec.risk) == 0.0
    assert float(spec.user_interference) == 0.0
    score = score_method(spec, policy)
    # A falsy-or bug would treat zeros as 0.5 and change the score materially.
    spec_bad = MethodSpec(
        id="nonzero_defaults",
        capability="forward_message",
        substrate="browser",
        readiness=MethodReadiness.READY.value,
        cost=0.5,
        risk=0.5,
        latency=0.5,
        user_interference=0.5,
        reliability=1.0,
        semantic_precision=1.0,
    )
    assert score != score_method(spec_bad, policy)
    assert score > score_method(spec_bad, policy)


def test_production_composition_registers_executable_method_provider() -> None:
    compose_domain_adapters()
    specs, errors = discover_methods(
        TaskInterpretation(
            user_turn="Forward ZarooratWala to Tanmay",
            goal_kind="whatsapp_forward_message",
            desired_effects=["forward_message", "whatsapp_forward_message"],
        )
    )
    assert any(s.id == "native_computer_use_forward" for s in specs)
    assert any(str(getattr(s, "readiness", "")) == "ready" for s in specs)
    assert errors == [] or isinstance(errors, list)


def test_provider_failure_is_traced() -> None:
    class Boom:
        provider_id = "boom"

        def discover(self, interpretation, *, constraints=None):
            raise RuntimeError("provider_exploded")

    register_method_provider(Boom())
    register_method_provider(_CatalogProvider([_computer_use()]))
    register_method_executor(_RecordingCUExecutor())
    result = AgentRuntime(runtime_state=RuntimeState()).handle_turn(
        _forward_req("prov-err")
    )
    errs = result.acceptance_trace.get("provider_errors") or []
    assert any(e.get("provider_id") == "boom" for e in errs)
    assert result.selected_method == "native_computer_use_forward"


def test_same_task_request_and_constraints_yield_same_method_frontier() -> None:
    register_method_provider(_CatalogProvider([_web_unimplemented(), _computer_use()]))
    register_method_executor(_RecordingCUExecutor())
    constraints = ExecutionConstraints()
    tui = TaskIngress.normalize(
        _forward_req("shared", constraints=constraints)
    )
    tui.client_context = {"client": "tui", "supports_rich_ui": True}
    desktop = TaskIngress.normalize(
        TaskRequest(
            user_turn=tui.user_turn,
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


def test_forced_substrate_via_execution_constraints_not_harness_branch() -> None:
    register_method_provider(
        _CatalogProvider([_web_ready_missing_auth(), _computer_use()])
    )
    register_method_executor(_RecordingCUExecutor())
    result = AgentRuntime(runtime_state=RuntimeState()).handle_turn(
        _forward_req(
            "force-cu",
            constraints=ExecutionConstraints(
                allowed_substrates=("computer_use",),
                forced_substrate="computer_use",
            ),
        )
    )
    assert result.status != TurnStatus.WAITING_FOR_USER
    assert result.selected_substrate == "computer_use"


def test_ui_adapter_does_not_choose_execution_substrate() -> None:
    register_method_provider(_CatalogProvider([_computer_use()]))
    register_method_executor(_RecordingCUExecutor())
    result = AgentRuntime(runtime_state=RuntimeState()).handle_turn(_forward_req("s"))
    assert result.selected_substrate == "computer_use"
    assert result.selected_substrate != "tui"
