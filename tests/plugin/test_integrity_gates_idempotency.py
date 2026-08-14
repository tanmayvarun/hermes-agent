"""Unit tests for integrity gates + executor idempotency."""

from __future__ import annotations

from plugin.agent.runtime.executor_idempotency import (
    ExecutorIdempotencyGuard,
    make_effect_key,
    reset_executor_idempotency_for_tests,
)
from plugin.agent.runtime.integrity_gates import (
    ComputerUseReadyGate,
    GatewaySessionWritableGate,
    WhatsAppIdentityResolvedGate,
)
from plugin.agent.runtime.method_executors import MethodExecutionResult
from plugin.agent.runtime.task_facts import ERROR_AUTH_REQUIRED, ERROR_SETUP_BLOCKED


def test_computer_use_ready_gate_blocks_setup_blocker():
    d = ComputerUseReadyGate.require_ready(setup_blocker_id="welcome")
    assert not d.ok
    assert d.error_code == ERROR_SETUP_BLOCKED
    assert d.fallback == "ask_prerequisite"


def test_computer_use_ready_gate_ok_when_unknown():
    assert ComputerUseReadyGate.require_ready().ok


def test_whatsapp_identity_gate_asks_when_unlinked():
    d = WhatsAppIdentityResolvedGate.require_linked(linked=False)
    assert not d.ok
    assert d.error_code == ERROR_AUTH_REQUIRED
    assert d.ask_precondition == "whatsapp_linked"


def test_gateway_session_writable_gate():
    assert not GatewaySessionWritableGate.require_writable(session_id="", task_request_id="t").ok
    assert GatewaySessionWritableGate.require_writable(
        session_id="s", task_request_id="t"
    ).ok


def test_idempotency_guard_replays_success():
    reset_executor_idempotency_for_tests()
    guard = ExecutorIdempotencyGuard()
    key = make_effect_key(
        task_request_id="tid1",
        effect="whatsapp_gateway_send",
        parts=("jid@s.whatsapp.net", "hello"),
    )
    first = MethodExecutionResult(
        ok=True,
        status="sent",
        detail="ok",
        payload={"chat_id": "jid"},
        executor_id="wa",
    )
    guard.remember_success(key, first)
    prior = guard.lookup(key)
    assert prior is not None
    replay = guard.mark_replay(prior)
    assert replay.ok
    assert replay.payload.get("idempotent_replay") is True

    # Failures are not memoized
    key2 = make_effect_key(task_request_id="tid1", effect="x", parts=("a",))
    guard.remember_success(
        key2, MethodExecutionResult(ok=False, status="failed", executor_id="wa")
    )
    assert guard.lookup(key2) is None
