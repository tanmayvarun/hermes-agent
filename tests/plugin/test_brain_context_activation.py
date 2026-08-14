"""Slice 1 goldens: ContextActivation before semantic commitment."""

from __future__ import annotations

import time

from plugin.agent.brain.context_activation import (
    activate_context,
    build_activation_signature,
)
from plugin.agent.goal import Goal
from plugin.agent.ingress import SessionRef, TaskIngress, TaskRequest
from plugin.agent.memory.bootstrap import open_local_memory
from plugin.agent.memory.pipeline import ContactObservation
from plugin.agent.memory.sources import FixtureSourceAdapter
from plugin.agent.memory.system import NoopMemorySystem
from plugin.agent.runtime.agent_runtime import AgentRuntime
from plugin.agent.runtime.session_store import reset_session_store
from plugin.agent.runtime.state import RuntimeState


def _pallavi_obs(now: float) -> list[ContactObservation]:
    return [
        ContactObservation(
            provider="whatsapp",
            external_id="W17",
            display_name="Pallavi",
            aliases=["Pallavi"],
            last_interaction_at=now - 3600,
            interaction_count_30d=180,
            frequency_known=True,
        ),
        ContactObservation(
            provider="whatsapp",
            external_id="W781",
            display_name="Pallavi PhonePe",
            aliases=["Pallavi PhonePe", "Pallavi"],
            last_interaction_at=now - 3 * 365 * 86400,
            interaction_count_30d=0,
            frequency_known=True,
        ),
    ]


def test_activation_signature_extracts_pallavi_and_whatsapp():
    sig = build_activation_signature("send hi to Pallavi on WhatsApp")
    assert "Pallavi" in sig.person_mentions
    assert "whatsapp" in sig.channel_cues
    assert any("send" in a for a in sig.action_cues)


def test_context_activation_admits_both_pallavis_without_commit(tmp_path):
    store, _ = open_local_memory(
        root=tmp_path / "mem",
        start_bootstrap=True,
        blocking_bootstrap=True,
        adapters=[
            FixtureSourceAdapter(
                source_name="fixture_wa",
                observations=_pallavi_obs(time.time()),
            )
        ],
    )
    try:
        goal = Goal(
            kind="whatsapp_forward_message",
            contact="Pallavi",
            message_body="hi",
            app="WhatsApp",
        )
        before_entity = goal.committed_entity_id
        before_channel = goal.committed_channel_id

        ws = activate_context(
            store,
            raw_turn="send hi to Pallavi on WhatsApp",
            session_ref="act-1",
        )
        names = {
            str(e.get("canonical_name") or "")
            for e in ws.retrieved_evidence
        }
        assert "Pallavi" in names
        assert any("PhonePe" in n for n in names)
        assert len(ws.active_context_refs) >= 2
        assert ws.bindings == []
        assert ws.metadata.get("activation_committed") is False
        assert ws.provisional_interpretation is not None
        assert ws.provisional_interpretation.interpretation_status == "provisional"
        assert any(
            r.get("entity_id") == "UNKNOWN"
            for r in ws.unresolved_references
        )
        # Activation must not mutate Goal commitments.
        assert goal.committed_entity_id == before_entity
        assert goal.committed_channel_id == before_channel
        trace = ws.activation_trace()
        assert trace["committed"] is False
        assert trace["evidence_count"] >= 2
    finally:
        store.close()


def test_context_activation_empty_memory_safe():
    ws = activate_context(
        NoopMemorySystem(),
        raw_turn="send hi to Pallavi on WhatsApp",
        session_ref="noop",
    )
    assert ws.retrieved_evidence == []
    assert ws.bindings == []
    assert ws.metadata.get("activation_status") == "skip_memory_not_local"
    assert ws.activation_trace()["committed"] is False


def test_agent_runtime_runs_activation_before_interpret(tmp_path):
    reset_session_store()
    store, _ = open_local_memory(
        root=tmp_path / "mem_rt",
        start_bootstrap=True,
        blocking_bootstrap=True,
        adapters=[
            FixtureSourceAdapter(
                source_name="fixture_wa",
                observations=_pallavi_obs(time.time()),
            )
        ],
    )
    try:
        from plugin.agent.executive import method_providers as mp

        original = list(mp._PROVIDERS)
        mp._PROVIDERS.clear()

        runtime = AgentRuntime(
            runtime_state=RuntimeState(),
            memory=store,
            task_request=TaskIngress.normalize(
                TaskRequest(
                    user_turn="send hi to Pallavi on WhatsApp",
                    session=SessionRef("brain-act-1"),
                    client_context={"client": "test"},
                )
            ),
        )
        turn = runtime.handle_turn(
            TaskRequest(
                user_turn="send hi to Pallavi on WhatsApp",
                session=SessionRef("brain-act-1"),
                client_context={"client": "test"},
            )
        )
        mp._PROVIDERS[:] = original

        trace = turn.acceptance_trace or {}
        act = trace.get("context_activation") or {}
        assert act.get("committed") is False
        assert act.get("evidence_count", 0) >= 2
        names = act.get("entity_names") or []
        assert any("Pallavi" == n or n.startswith("Pallavi") for n in names)
        # Recipient path may still commit; activation itself must not claim commit.
        assert "committed" in act and act["committed"] is False
    finally:
        store.close()
        reset_session_store()
