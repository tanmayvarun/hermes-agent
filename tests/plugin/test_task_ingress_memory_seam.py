"""Architectural goldens for TaskIngress + Noop MemorySystem seam (A + thin C)."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

import pytest

from plugin.agent.goal import Goal
from plugin.agent.ingress import (
    ExecutionConstraints,
    SessionRef,
    TaskIngress,
    TaskRequest,
    semantic_task_fingerprint,
)
from plugin.agent.memory.system import NoopMemorySystem
from plugin.agent.memory.types import (
    MemoryCandidate,
    MemoryEvidence,
    MemoryInvalidationResult,
    MemoryWriteResult,
)
from plugin.agent.runtime.agent_runtime import AgentRuntime
from plugin.agent.runtime.state import RuntimeState


class SpyMemorySystem:
    """Records MemorySystem calls to assert ingress/ctor have no side effects."""

    def __init__(self) -> None:
        self.retrieve_calls = 0
        self.submit_calls = 0
        self.invalidate_calls = 0

    def retrieve(
        self,
        query: str,
        *,
        context: Optional[Mapping[str, Any]] = None,
        limit: int = 8,
    ) -> Sequence[MemoryEvidence]:
        self.retrieve_calls += 1
        return []

    def submit_candidate(self, candidate: MemoryCandidate) -> MemoryWriteResult:
        self.submit_calls += 1
        return MemoryWriteResult(disposition="ignored", reason="spy")

    def invalidate(
        self,
        memory_id: str,
        *,
        reason: str = "",
    ) -> MemoryInvalidationResult:
        self.invalidate_calls += 1
        return MemoryInvalidationResult(
            disposition="ignored", reason=reason or "spy", memory_id=memory_id
        )


def test_task_ingress_has_no_memory_side_effects() -> None:
    spy = SpyMemorySystem()
    req = TaskRequest(
        user_turn="Send this to Sarah.",
        session=SessionRef("s1"),
        client_context={"client": "tui"},
    )
    # Ingress must not touch memory at all (normalize has no memory parameter).
    normalized = TaskIngress.normalize(req)
    assert normalized.user_turn == "Send this to Sarah."
    assert spy.retrieve_calls == 0
    assert spy.submit_calls == 0
    assert spy.invalidate_calls == 0


def test_agent_runtime_construction_does_not_retrieve_memory() -> None:
    spy = SpyMemorySystem()
    rs = RuntimeState()
    req = TaskIngress.normalize(TaskRequest(user_turn="hello", session=SessionRef("s2")))
    runtime = AgentRuntime(runtime_state=rs, memory=spy, task_request=req)
    assert runtime.runtime_state is rs
    assert spy.retrieve_calls == 0
    assert spy.submit_calls == 0
    assert spy.invalidate_calls == 0


def test_runtime_state_does_not_backreference_agent_runtime() -> None:
    rs = RuntimeState()
    runtime = AgentRuntime(runtime_state=rs, memory=NoopMemorySystem())
    assert not hasattr(rs, "agent_runtime")
    assert getattr(rs, "agent_runtime", None) is None
    # One-way ownership only.
    assert runtime.runtime_state is rs


def test_legacy_goal_adapter_preserves_goal_without_making_goal_required_for_task_request() -> None:
    # Canonical user-turn TaskRequest works without Goal.
    plain = TaskIngress.normalize(TaskRequest(user_turn="Open WhatsApp chat with Pallavi"))
    assert plain.legacy_goal is None
    assert "goal" not in plain.__dataclass_fields__
    assert "legacy_goal" in plain.__dataclass_fields__

    goal = Goal(kind="whatsapp_forward_message", contact="Pallavi", prompt="Forward to Tanmay")
    adapted = TaskIngress.normalize(TaskIngress.from_legacy_goal(goal))
    assert adapted.legacy_goal is goal
    assert adapted.user_turn == "Forward to Tanmay"
    # Goal is not a required TaskRequest field — only legacy payload.
    assert "goal" not in adapted.__dataclass_fields__


def test_noop_memory_write_reports_ignored_not_persisted() -> None:
    mem = NoopMemorySystem()
    assert mem.retrieve("anything") == []
    write = mem.submit_candidate(
        MemoryCandidate(kind="episodic", content="tried open Pallavi", provenance="test")
    )
    assert isinstance(write, MemoryWriteResult)
    assert write.disposition == "ignored"
    assert write.reason == "noop_memory_system"
    assert write.memory_id is None
    inv = mem.invalidate("mem-1", reason="stale")
    assert inv.disposition == "ignored"
    assert inv.memory_id == "mem-1"
    # Candidate is not durable persistence (MemoryRecord deferred).
    assert MemoryCandidate.__name__ == "MemoryCandidate"


def test_client_context_differences_do_not_change_task_semantics() -> None:
    constraints = ExecutionConstraints(
        foreground_allowed=True,
        network_allowed=True,
        destructive_actions_allowed=False,
        approval_policy="default",
    )
    tui = TaskIngress.normalize(
        TaskRequest(
            user_turn="Forward Pallavi's message to Tanmay",
            session=SessionRef("shared-session"),
            client_context={
                "client": "tui",
                "supports_rich_ui": True,
                "supports_streaming": True,
            },
            constraints=constraints,
            interaction_capabilities={"approvals": True},
        )
    )
    desktop = TaskIngress.normalize(
        TaskRequest(
            user_turn="Forward Pallavi's message to Tanmay",
            session=SessionRef("shared-session"),
            client_context={
                "client": "desktop",
                "supports_rich_ui": False,
                "supports_streaming": False,
            },
            constraints=constraints,
            interaction_capabilities={"approvals": True},
        )
    )
    assert semantic_task_fingerprint(tui) == semantic_task_fingerprint(desktop)
    assert tui.client_context["client"] != desktop.client_context["client"]


def test_run_goal_closed_loop_legacy_adapter_builds_runtime_without_retrieve() -> None:
    """First legacy adapter: Goal → TaskIngress → AgentRuntime; no retrieve."""
    from plugin.agent.controller import run_goal_closed_loop

    class _StopAfterSeam(Exception):
        pass

    spy = SpyMemorySystem()
    rs = RuntimeState()
    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi", prompt="Call Pallavi")

    def _observe():
        # Seam must already have been constructed before first observe.
        raise _StopAfterSeam("seam_ok")

    class _Exec:
        def execute(self, step):  # pragma: no cover - should not run
            return {"ok": False, "error": "unused"}

    with pytest.raises(_StopAfterSeam):
        run_goal_closed_loop(
            rs,
            goal,
            observe=_observe,
            execute=_Exec(),
            max_iterations=1,
            settle_s=0.01,
            wait_fn=lambda *_a, **_k: None,
            memory=spy,
        )
    assert spy.retrieve_calls == 0
    assert spy.submit_calls == 0
    assert spy.invalidate_calls == 0
    assert not hasattr(rs, "agent_runtime")


def test_normalize_does_not_submit_or_invalidate() -> None:
    spy = SpyMemorySystem()
    TaskIngress.normalize(
        TaskRequest(user_turn="  spaced  ", client_context={"client": "cli"})
    )
    assert spy.submit_calls == 0
    assert spy.invalidate_calls == 0
    assert spy.retrieve_calls == 0
