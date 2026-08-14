"""Stage A goldens (post merge-blocker fixes): frontier authority, dispatch, ASK permission."""

from __future__ import annotations

from typing import Any, Optional, Sequence

import pytest

from types import SimpleNamespace

from plugin.agent.composition import (
    compose_domain_adapters,
    composition_diagnostics,
    reset_composition_for_tests,
)
from plugin.agent.executive.intention_frame import MethodSpec, ScoringPolicy, score_method
from plugin.agent.executive.method_availability import (
    MethodAvailability,
    MethodReadiness,
    evaluate_method_availability,
)
from plugin.agent.executive.method_providers import (
    TaskInterpretation,
    clear_method_providers,
    discover_methods,
    register_method_provider,
)
from plugin.agent.providers.computer_use import ensure_computer_use_provider_registered
from plugin.agent.runtime.session_store import get_or_create_session
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
    assert second.acceptance_trace.get("availability") == "temporarily_unavailable"
    assert cu.calls == 1
    sess = get_or_create_session("prereq-fail")
    assert "structured_web_forward" in sess.blocked_method_ids
    assert "structured_web_forward" not in sess.declined_method_ids
    assert "authenticated_integration" in sess.failed_preconditions


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
    def _obs(**kwargs):
        return lambda: SimpleNamespace(nodes=[])

    def _exe(**kwargs):
        class _E:
            def execute(self, step):
                from plugin.executor.ghost import ExecResult

                return ExecResult(ok=True, backend="test", message="ok")

        return _E()

    diag = ensure_computer_use_provider_registered(
        force_runnable=True,
        observe_builder=_obs,
        execute_builder=_exe,
    )
    assert diag["runnable"] is True
    assert diag["provider_registered"] is True
    assert diag["executor_registered"] is True
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


def test_forced_composed_substrate_dispatches_without_tui_injection() -> None:
    """Forced substrate plumbing: TUI does not inject observe/execute."""

    def _obs(**kwargs):
        return lambda: SimpleNamespace(nodes=[])

    def _exe(**kwargs):
        class _E:
            def execute(self, step):
                from plugin.executor.ghost import ExecResult

                return ExecResult(ok=True, backend="test", message="ok")

        return _E()

    diag = ensure_computer_use_provider_registered(
        force_runnable=True,
        observe_builder=_obs,
        execute_builder=_exe,
    )
    assert diag.get("ok") is True
    assert diag["provider_registered"] is True

    seen = {"observe": False, "execute": False}

    def fake_closed_loop(runtime, goal, *, observe=None, execute=None, **kwargs):
        seen["observe"] = observe is not None
        seen["execute"] = execute is not None
        return SimpleNamespace(ok=True, reason="composed_ok", iterations=1)

    rt = AgentRuntime(runtime_state=RuntimeState())
    result = rt.handle_turn(
        _forward_req("prod-cu"),
        # TUI-like: no observe/execute — only closed_loop stub for unit isolation.
        execution_context={"closed_loop": fake_closed_loop},
    )
    assert seen["observe"] and seen["execute"]
    assert "observe_execute_not_provided" not in str(result.message or "")
    assert "computer_use_substrate_not_composed" not in str(result.message or "")
    assert result.selected_substrate == "computer_use"
    assert result.acceptance_trace.get("dispatched_executor") is True
    payload = result.legacy_result or {}
    if isinstance(payload, dict):
        assert payload.get("bindings_source") == "composed_substrate"
        assert payload.get("dispatched") is True


def test_compose_domain_adapters_computer_use_characterization() -> None:
    """Real composition root: diagnostics always present; READY only if runnable."""
    reset_composition_for_tests()
    compose_domain_adapters()
    diags = composition_diagnostics()
    cu = [d for d in diags if d.get("event") == "computer_use_composition"]
    assert cu, "computer_use_composition diagnostic must always be emitted"
    d = cu[-1]
    assert "ok" in d
    assert "reason" in d or d.get("exception")
    wa = [x for x in diags if x.get("event") == "whatsapp_gateway_composition"]
    assert wa, "whatsapp_gateway_composition diagnostic must always be emitted"
    assert "ok" in wa[-1]
    specs, _ = discover_methods(
        TaskInterpretation(
            user_turn="Forward ZarooratWala to Tanmay",
            goal_kind="whatsapp_forward_message",
            desired_effects=["forward_message"],
        )
    )
    cu_specs = [s for s in specs if s.id == "native_computer_use_forward"]
    wa_specs = [s for s in specs if s.id == "whatsapp_gateway_forward"]
    if d.get("ok") and d.get("runnable"):
        assert d.get("provider_registered") is True
        assert d.get("executor_registered") is True
        assert cu_specs
        assert all(str(s.readiness) == "ready" for s in cu_specs)
    else:
        assert d.get("provider_registered") in (False, None)
        assert not cu_specs
    if wa[-1].get("ok") and wa[-1].get("ready"):
        assert wa[-1].get("provider_registered") is True
        assert wa_specs
        assert all(str(s.readiness) == "ready" for s in wa_specs)
    else:
        assert not wa_specs


def test_computer_use_composition_failure_is_diagnosed(monkeypatch) -> None:
    def _boom(**kwargs):
        raise RuntimeError("compose_boom")

    monkeypatch.setattr(
        "plugin.agent.providers.computer_use.ensure_computer_use_provider_registered",
        _boom,
    )
    reset_composition_for_tests()
    compose_domain_adapters()
    diags = composition_diagnostics()
    cu = [d for d in diags if d.get("event") == "computer_use_composition"]
    assert cu
    assert cu[-1].get("ok") is False
    assert "compose_boom" in str(cu[-1].get("exception") or "")


def test_computer_use_substrate_does_not_default_app_to_whatsapp() -> None:
    from plugin.agent.runtime.computer_use_substrate import ComputerUseSubstrate

    sub = ComputerUseSubstrate(runnable=True, reason="test")
    assert not hasattr(sub, "app_default") or getattr(sub, "app_default", "") == ""
    goal = type("G", (), {"app": ""})()
    bindings = sub.bind(
        {
            "runtime_state": RuntimeState(),
            "goal": goal,
            "log": None,
        }
    )
    assert bindings.get("app") == ""


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


def _whatsapp_gateway_missing_link() -> MethodSpec:
    return MethodSpec(
        id="whatsapp_gateway_forward",
        capability="forward_message",
        substrate="whatsapp_gateway",
        provider="whatsapp_gateway",
        preconditions=["whatsapp_linked"],
        readiness=MethodReadiness.READY.value,
        reliability=0.88,
        latency=0.45,
        risk=0.35,
        cost=0.35,
        user_interference=0.35,
        semantic_precision=0.8,
    )


def test_whatsapp_gateway_ready_missing_link_asks_before_computer_use() -> None:
    register_method_provider(
        _CatalogProvider([_whatsapp_gateway_missing_link(), _computer_use()])
    )
    register_method_executor(_RecordingCUExecutor())
    result = AgentRuntime(runtime_state=RuntimeState()).handle_turn(
        _forward_req("wa-ask")
    )
    assert result.status == TurnStatus.WAITING_FOR_USER
    assert result.acceptance_trace.get("missing_precondition") == "whatsapp_linked"
    # Domain-neutral ASK copy when no resolver ask_prompt is registered.
    assert "whatsapp_linked" in (result.question or "")


def test_whatsapp_link_pending_surfaces_qr_ui_hints() -> None:
    from plugin.agent.runtime.prerequisite_resolver import PrerequisiteResolveResult

    class _QrPendingResolver:
        def resolve(
            self,
            precondition: str,
            *,
            permission_granted: bool,
            context: Optional[dict] = None,
        ):
            if precondition != "whatsapp_linked":
                return PrerequisiteResolveResult(
                    status="unsupported", precondition=precondition, detail="not_owned"
                )
            return PrerequisiteResolveResult(
                status="pending",
                precondition=precondition,
                detail="awaiting_qr_scan",
                evidence={
                    "kind": "whatsapp_link_device",
                    "pairing_id": "pair-test",
                    "status": "waiting",
                    "qr_payload": "https://wa.me/qr/TESTPAYLOAD",
                },
                user_message=(
                    "Scan this QR with WhatsApp → Linked devices → Link a device."
                ),
            )

    register_method_provider(
        _CatalogProvider([_whatsapp_gateway_missing_link(), _computer_use()])
    )
    register_method_executor(_RecordingCUExecutor())
    register_prerequisite_resolver(_QrPendingResolver())
    rt = AgentRuntime(runtime_state=RuntimeState())
    first = rt.handle_turn(_forward_req("wa-qr"))
    assert first.status == TurnStatus.WAITING_FOR_USER
    second = rt.handle_turn(TaskRequest(user_turn="yes", session=SessionRef("wa-qr")))
    assert second.status == TurnStatus.WAITING_FOR_USER
    assert second.ui_hints.get("kind") == "whatsapp_link_device"
    assert second.ui_hints.get("qr_payload") == "https://wa.me/qr/TESTPAYLOAD"
    assert "Scan this QR" in (second.message or "")


def test_decline_whatsapp_link_falls_back_to_computer_use() -> None:
    register_method_provider(
        _CatalogProvider([_whatsapp_gateway_missing_link(), _computer_use()])
    )
    cu = _RecordingCUExecutor()
    register_method_executor(cu)
    rt = AgentRuntime(runtime_state=RuntimeState())
    rt.handle_turn(_forward_req("wa-decline"))
    result = rt.handle_turn(
        TaskRequest(user_turn="not now", session=SessionRef("wa-decline"))
    )
    assert result.selected_method == "native_computer_use_forward"
    assert cu.calls == 1


def test_valid_linked_creds_skip_ask_even_when_bridge_offline(monkeypatch) -> None:
    """Phone already linked (real Baileys account on disk) → no Link ASK; continue."""
    from plugin.agent.providers import whatsapp_gateway as wag

    monkeypatch.setattr(
        "hermes_cli.whatsapp_pairing.is_whatsapp_live", lambda **_k: False
    )
    monkeypatch.setattr(
        "hermes_cli.whatsapp_pairing.is_whatsapp_linked", lambda **_k: True
    )
    monkeypatch.setattr(
        "hermes_cli.whatsapp_pairing.linked_account_from_session",
        lambda **_k: ("918600900337:33@s.whatsapp.net", "Me", "918600900337"),
    )
    monkeypatch.setattr(
        "hermes_cli.whatsapp_pairing.bridge_available", lambda: (True, "ok")
    )
    monkeypatch.setattr(
        "hermes_cli.whatsapp_pairing.probe_bridge_connection",
        lambda **_k: (False, "connection_refused"),
    )
    monkeypatch.setattr(
        "hermes_cli.whatsapp_pairing.ensure_whatsapp_bridge_running",
        lambda **_k: (False, "connection_refused"),
    )
    register_method_provider(wag.WhatsAppGatewayMethodProvider(ready=True, reason="ok"))
    register_prerequisite_resolver(wag.WhatsAppLinkPrerequisiteResolver())
    register_method_provider(_CatalogProvider([_computer_use()]))
    register_method_executor(wag.WhatsAppGatewayForwardExecutor())
    cu = _RecordingCUExecutor()
    register_method_executor(cu)

    result = AgentRuntime(runtime_state=RuntimeState()).handle_turn(
        _forward_req(
            "wa-already-linked",
            user_turn="Find the zarooratwala link sent to Kulvinder and forward it to Pallavi",
        )
    )
    assert result.status != TurnStatus.WAITING_FOR_USER
    assert result.acceptance_trace.get("missing_precondition") is None
    assert not (result.question or "")
    assert result.selected_method == "native_computer_use_forward"
    assert cu.calls == 1


def test_executor_ensures_bridge_before_falling_through(monkeypatch) -> None:
    """Linked + /health down → ensure daemon; if it comes up, continue (not re-ASK)."""
    from plugin.agent.providers import whatsapp_gateway as wag

    probes = {"n": 0}

    def _probe(**_k):
        probes["n"] += 1
        # First probe down; after ensure, up.
        if probes["n"] == 1:
            return False, "connection_refused"
        return True, "connected"

    ensure_calls = {"n": 0}

    def _ensure(**_k):
        ensure_calls["n"] += 1
        return True, "connected"

    monkeypatch.setattr("hermes_cli.whatsapp_pairing.is_whatsapp_linked", lambda **_k: True)
    monkeypatch.setattr(
        "hermes_cli.whatsapp_pairing.linked_account_from_session",
        lambda **_k: ("918600900337:33@s.whatsapp.net", "Me", "918600900337"),
    )
    monkeypatch.setattr(
        "hermes_cli.whatsapp_pairing.probe_bridge_connection", _probe
    )
    monkeypatch.setattr(
        "hermes_cli.whatsapp_pairing.ensure_whatsapp_bridge_running", _ensure
    )

    ex = wag.WhatsAppGatewayForwardExecutor()
    result = ex.execute(
        SimpleNamespace(id="whatsapp_gateway_forward"),
        context={
            "goal": SimpleNamespace(
                link_query="ZarooratWala",
                contact="Pallavi",
                target_contact="Tanmay",
            )
        },
    )
    assert ensure_calls["n"] == 1
    assert result.ok is False
    assert result.status == "search_unsupported"
    assert (result.payload or {}).get("fallback") == "next_method"


def test_unlinked_creds_ask_before_computer_use_when_bridge_offline(monkeypatch) -> None:
    """No real linked account → ASK before falling through to Computer Use."""
    from plugin.agent.providers import whatsapp_gateway as wag

    monkeypatch.setattr(
        "hermes_cli.whatsapp_pairing.is_whatsapp_live", lambda **_k: False
    )
    monkeypatch.setattr(
        "hermes_cli.whatsapp_pairing.is_whatsapp_linked", lambda **_k: False
    )
    monkeypatch.setattr(
        "hermes_cli.whatsapp_pairing.bridge_available", lambda: (True, "ok")
    )
    register_method_provider(wag.WhatsAppGatewayMethodProvider(ready=True, reason="ok"))
    register_prerequisite_resolver(wag.WhatsAppLinkPrerequisiteResolver())
    register_method_provider(_CatalogProvider([_computer_use()]))
    cu = _RecordingCUExecutor()
    register_method_executor(cu)

    result = AgentRuntime(runtime_state=RuntimeState()).handle_turn(
        _forward_req(
            "wa-unlinked",
            user_turn="Find the zarooratwala link sent to Kulvinder and forward it to Pallavi",
        )
    )
    assert result.status == TurnStatus.WAITING_FOR_USER
    assert result.acceptance_trace.get("missing_precondition") == "whatsapp_linked"
    assert "WhatsApp" in (result.question or "")
    assert cu.calls == 0


def test_bridge_unavailable_executor_recovers_to_link_ask() -> None:
    class _DeadBridgeWA:
        executor_id = "whatsapp_gateway_forward"
        substrates = ("whatsapp_gateway",)

        def execute(self, spec: Any, *, context: dict) -> MethodExecutionResult:
            return MethodExecutionResult(
                ok=False,
                status="bridge_unavailable",
                detail="bridge down",
                payload={
                    "fallback": "ask_prerequisite",
                    "ask_precondition": "whatsapp_linked",
                    "ask_question": (
                        "I can do this over WhatsApp (preferred) once this device is linked."
                    ),
                },
                executor_id=self.executor_id,
            )

    wa_live = MethodSpec(
        id="whatsapp_gateway_forward",
        capability="forward_message",
        substrate="whatsapp_gateway",
        provider="whatsapp_gateway",
        preconditions=[],
        readiness=MethodReadiness.READY.value,
        reliability=0.88,
        latency=0.45,
        risk=0.35,
        cost=0.35,
        user_interference=0.35,
        semantic_precision=0.8,
    )
    register_method_provider(_CatalogProvider([wa_live, _computer_use()]))
    register_method_executor(_DeadBridgeWA())
    cu = _RecordingCUExecutor()
    register_method_executor(cu)
    result = AgentRuntime(runtime_state=RuntimeState()).handle_turn(
        _forward_req("wa-recover-ask")
    )
    assert result.status == TurnStatus.WAITING_FOR_USER
    assert result.acceptance_trace.get("executor_recover_ask") is True
    assert "WhatsApp" in (result.question or "")
    assert cu.calls == 0


def test_bridge_unavailable_after_link_falls_through_not_reask() -> None:
    """Post-scan pair-only leaves /health down — must not re-show QR; use CU."""

    class _DeadBridgeWA:
        executor_id = "whatsapp_gateway_forward"
        substrates = ("whatsapp_gateway",)

        def execute(self, spec: Any, *, context: dict) -> MethodExecutionResult:
            return MethodExecutionResult(
                ok=False,
                status="bridge_unavailable",
                detail="bridge down after pair",
                payload={
                    "fallback": "ask_prerequisite",
                    "ask_precondition": "whatsapp_linked",
                    "ask_question": "Link WhatsApp?",
                },
                executor_id=self.executor_id,
            )

    wa_live = MethodSpec(
        id="whatsapp_gateway_forward",
        capability="forward_message",
        substrate="whatsapp_gateway",
        provider="whatsapp_gateway",
        preconditions=[],
        readiness=MethodReadiness.READY.value,
        reliability=0.88,
        latency=0.45,
        risk=0.35,
        cost=0.35,
        user_interference=0.35,
        semantic_precision=0.8,
    )
    register_method_provider(_CatalogProvider([wa_live, _computer_use()]))
    register_method_executor(_DeadBridgeWA())
    cu = _RecordingCUExecutor()
    register_method_executor(cu)
    rt = AgentRuntime(runtime_state=RuntimeState())
    # Pretend link already achieved this session (scan completed).
    st = get_or_create_session("wa-post-link")
    st.precondition_facts["whatsapp_linked"] = True
    result = rt.handle_turn(_forward_req("wa-post-link"))
    assert result.status == TurnStatus.COMPLETED
    assert result.selected_method == "native_computer_use_forward"
    assert cu.calls == 1
    assert not (result.ui_hints or {}).get("qr_payload")


def test_whatsapp_qr_expired_falls_through_to_computer_use() -> None:
    from plugin.agent.runtime.prerequisite_resolver import PrerequisiteResolveResult

    class _ExpiredResolver:
        def resolve(
            self,
            precondition: str,
            *,
            permission_granted: bool,
            context: Optional[dict] = None,
        ):
            if precondition != "whatsapp_linked":
                return PrerequisiteResolveResult(
                    status="unsupported", precondition=precondition, detail="not_owned"
                )
            return PrerequisiteResolveResult(
                status="failed",
                precondition=precondition,
                detail="WhatsApp QR setup expired. Start a new setup.",
                evidence={
                    "kind": "whatsapp_link_device",
                    "status": "expired",
                    "pairing_id": "pair-expired",
                },
                failure_policy="fallback_next_method",
            )

    register_method_provider(
        _CatalogProvider([_whatsapp_gateway_missing_link(), _computer_use()])
    )
    cu = _RecordingCUExecutor()
    register_method_executor(cu)
    register_prerequisite_resolver(_ExpiredResolver())
    rt = AgentRuntime(runtime_state=RuntimeState())
    first = rt.handle_turn(_forward_req("wa-expire"))
    assert first.status == TurnStatus.WAITING_FOR_USER
    second = rt.handle_turn(TaskRequest(user_turn="yes", session=SessionRef("wa-expire")))
    assert second.selected_method == "native_computer_use_forward"
    assert cu.calls == 1
    assert second.acceptance_trace.get("resumed_after") == "prerequisite_failed_fallback"
    assert not (second.ui_hints or {}).get("qr_payload")


def test_whatsapp_pairing_error_keeps_ask_with_qr_ui() -> None:
    """Retryable pairing errors must not silently skip QR / jump to CU."""
    from plugin.agent.runtime.prerequisite_resolver import PrerequisiteResolveResult

    class _ErrorResolver:
        def resolve(
            self,
            precondition: str,
            *,
            permission_granted: bool,
            context: Optional[dict] = None,
        ):
            if precondition != "whatsapp_linked":
                return PrerequisiteResolveResult(
                    status="unsupported", precondition=precondition, detail="not_owned"
                )
            return PrerequisiteResolveResult(
                status="failed",
                precondition=precondition,
                detail="logged_out",
                evidence={
                    "kind": "whatsapp_link_device",
                    "status": "error",
                    "pairing_id": "pair-err",
                    "qr_payload": None,
                },
                failure_policy="keep_ask",
                user_message="Retry WhatsApp link setup.",
            )

    register_method_provider(
        _CatalogProvider([_whatsapp_gateway_missing_link(), _computer_use()])
    )
    cu = _RecordingCUExecutor()
    register_method_executor(cu)
    register_prerequisite_resolver(_ErrorResolver())
    rt = AgentRuntime(runtime_state=RuntimeState())
    first = rt.handle_turn(_forward_req("wa-err-keep"))
    assert first.status == TurnStatus.WAITING_FOR_USER
    second = rt.handle_turn(TaskRequest(user_turn="yes", session=SessionRef("wa-err-keep")))
    assert second.status == TurnStatus.WAITING_FOR_USER
    assert cu.calls == 0
    assert second.acceptance_trace.get("prerequisite_failed_kept_ask") is True
    assert (second.ui_hints or {}).get("kind") == "whatsapp_link_device"


def test_search_unsupported_falls_through_to_computer_use() -> None:
    class _SearchUnsupportedWA:
        executor_id = "whatsapp_gateway_forward"
        substrates = ("whatsapp_gateway",)

        def execute(self, spec: Any, *, context: dict) -> MethodExecutionResult:
            return MethodExecutionResult(
                ok=False,
                status="search_unsupported",
                detail="no history search",
                payload={"fallback": "next_method"},
                executor_id=self.executor_id,
            )

    wa_live = MethodSpec(
        id="whatsapp_gateway_forward",
        capability="forward_message",
        substrate="whatsapp_gateway",
        provider="whatsapp_gateway",
        preconditions=[],
        readiness=MethodReadiness.READY.value,
        reliability=0.88,
        latency=0.45,
        risk=0.35,
        cost=0.35,
        user_interference=0.35,
        semantic_precision=0.8,
    )
    register_method_provider(_CatalogProvider([wa_live, _computer_use()]))
    register_method_executor(_SearchUnsupportedWA())
    cu = _RecordingCUExecutor()
    register_method_executor(cu)
    result = AgentRuntime(runtime_state=RuntimeState()).handle_turn(
        _forward_req("wa-search-fallback")
    )
    assert result.status == TurnStatus.COMPLETED
    assert result.selected_method == "native_computer_use_forward"
    assert cu.calls == 1
    assert result.acceptance_trace.get("executor_fallback", {}).get("status") == (
        "search_unsupported"
    )
