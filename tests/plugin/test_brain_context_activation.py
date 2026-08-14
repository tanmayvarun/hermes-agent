"""Slice 1B goldens: persistent workspace, activation feeds interpretation."""

from __future__ import annotations

import time

from plugin.agent.brain.context_activation import (
    activate_context,
    build_activation_signature,
    consultation_context_from_workspace,
)
from plugin.agent.brain.workspace import BrainWorkspace
from plugin.agent.executive.method_providers import interpret_task_request
from plugin.agent.goal import Goal
from plugin.agent.ingress import SessionRef, TaskIngress, TaskRequest
from plugin.agent.memory.bootstrap import open_local_memory
from plugin.agent.memory.pipeline import ContactObservation
from plugin.agent.memory.sources import FixtureSourceAdapter
from plugin.agent.memory.system import NoopMemorySystem
from plugin.agent.runtime.agent_runtime import AgentRuntime
from plugin.agent.runtime.session_store import get_or_create_session, reset_session_store
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


def test_mentions_are_role_neutral():
    sig = build_activation_signature("find Pallavi's email")
    ws = activate_context(NoopMemorySystem(), raw_turn="find Pallavi's email")
    assert ws.unresolved_references
    assert all(r.get("role") == "unknown" for r in ws.unresolved_references)
    assert ws.desired_effects == []  # activation must not write desired_effects
    assert "find" in " ".join(sig.action_cues) or sig.action_cues  # cue ok


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
        names = {str(e.get("canonical_name") or "") for e in ws.retrieved_evidence}
        assert "Pallavi" in names
        assert any("PhonePe" in n for n in names)
        assert len(ws.active_context_refs) >= 2
        assert ws.bindings == []
        assert ws.desired_effects == []
        assert ws.metadata.get("activation_committed") is False
        assert all(r.get("role") == "unknown" for r in ws.unresolved_references)
        assert goal.committed_entity_id == before_entity
        assert goal.committed_channel_id == before_channel
        assert ws.activation_trace()["committed"] is False
    finally:
        store.close()


def test_context_activation_empty_memory_safe():
    ws = activate_context(
        NoopMemorySystem(),
        raw_turn="send hi to Pallavi on WhatsApp",
        session_ref="noop",
    )
    assert ws.bindings == []
    assert ws.desired_effects == []
    assert ws.metadata.get("activation_status") in {
        "ok",
        "no_cues",
        "skip_no_retrieve",
    }
    # Noop has retrieve() but returns []; structured path skipped → protocol path ok/empty
    assert ws.activation_trace()["committed"] is False


def test_workspace_persists_across_turns_and_does_not_clear_bindings(tmp_path):
    store, _ = open_local_memory(
        root=tmp_path / "mem_persist",
        start_bootstrap=True,
        blocking_bootstrap=True,
        adapters=[
            FixtureSourceAdapter(
                source_name="wa",
                observations=_pallavi_obs(time.time()),
            )
        ],
    )
    try:
        ws = BrainWorkspace(session_ref="persist")
        ws.bindings = [{"role": "recipient", "entity_id": "ent:keep"}]
        ws.desired_effects = ["send_message"]  # pre-existing brain field — leave alone

        ws = activate_context(
            store,
            raw_turn="send hi to Pallavi on WhatsApp",
            workspace=ws,
            working_context={"client": "test"},
        )
        assert ws.bindings == [{"role": "recipient", "entity_id": "ent:keep"}]
        assert ws.desired_effects == ["send_message"]  # activation did not rewrite

        ws2 = activate_context(
            store,
            raw_turn="send Pallavi the deck",
            workspace=ws,
        )
        assert ws2 is ws
        assert ws2.bindings[0]["entity_id"] == "ent:keep"
        assert "Pallavi" in (ws2.working_context.get("recent_entity_names") or [])
    finally:
        store.close()


def test_l1_session_context_outranks_global_personal_salience(tmp_path):
    """recent_explicit_session_context_outranks_global_personal_salience"""
    store, _ = open_local_memory(
        root=tmp_path / "mem_l1",
        start_bootstrap=True,
        blocking_bootstrap=True,
        adapters=[
            FixtureSourceAdapter(
                source_name="wa",
                observations=_pallavi_obs(time.time()),
            )
        ],
    )
    try:
        # Resolve PhonePe entity id from store
        phonepe = next(
            e
            for e in store.find_entities_by_name("Pallavi")
            if "PhonePe" in (e.canonical_name or "")
        )
        ws = BrainWorkspace(session_ref="l1")
        ws.working_context = {
            "recent_entity_id": phonepe.entity_id,
            "recent_entity_name": "Pallavi PhonePe",
            "recent_entity_names": ["Pallavi PhonePe"],
            "recent_topics": ["PhonePe"],
            "recent_projects": ["PhonePe"],
        }
        ws = activate_context(
            store,
            raw_turn="send Pallavi the deck",
            workspace=ws,
        )
        assert ws.retrieved_evidence
        top = ws.retrieved_evidence[0]
        assert "PhonePe" in str(top.get("canonical_name") or "")
        assert top.get("salience") in {"l1", "l1_boosted"}

        # Same prompt without L1 → sister Pallavi more globally salient in ranking
        ws_b = activate_context(
            store,
            raw_turn="send Pallavi the deck",
            session_ref="global",
        )
        names_b = [e.get("canonical_name") for e in ws_b.retrieved_evidence[:3]]
        assert "Pallavi" in names_b

        # Interpretation notes differ because activated context differs
        req = TaskRequest(user_turn="send Pallavi the deck")
        interp_a = interpret_task_request(req, brain_workspace=ws)
        interp_b = interpret_task_request(req, brain_workspace=ws_b)
        assert interp_a.notes.get("activated_context")
        assert interp_b.notes.get("activated_context")
        assert interp_a.notes.get("l1_preferred_entity") == "Pallavi PhonePe"
        assert interp_a.notes.get("top_hypothesis", {}).get("canonical_name") != (
            interp_b.notes.get("top_hypothesis", {}).get("canonical_name")
        ) or interp_a.notes.get("hypothesis_salience") != interp_b.notes.get(
            "hypothesis_salience"
        )
    finally:
        store.close()


def test_continue_hermes_work_activates_project_context_not_recipient_role():
    ws = activate_context(
        NoopMemorySystem(),
        raw_turn="continue the Hermes work",
        working_context={"recent_project": "Hermes", "recent_projects": ["Hermes"]},
    )
    sig = ws.activation_signature or {}
    assert "Hermes" in (sig.get("project_topic_cues") or sig.get("lexical_cues") or [])
    assert "project" in (sig.get("semantic_cues") or [])
    assert all(r.get("role") == "unknown" for r in ws.unresolved_references)
    assert not any(r.get("role") == "recipient" for r in ws.unresolved_references)
    # L1 project evidence present
    assert any(
        e.get("ref_kind") == "project" or "Hermes" in str(e.get("canonical_name") or "")
        for e in ws.retrieved_evidence
    )


def test_interpret_consumes_activated_context(tmp_path):
    store, _ = open_local_memory(
        root=tmp_path / "mem_interp",
        start_bootstrap=True,
        blocking_bootstrap=True,
        adapters=[
            FixtureSourceAdapter(
                source_name="wa",
                observations=_pallavi_obs(time.time()),
            )
        ],
    )
    try:
        ws = activate_context(
            store,
            raw_turn="send hi to Pallavi on WhatsApp",
            working_context={
                "recent_entity_name": "Pallavi PhonePe",
                "recent_entity_names": ["Pallavi PhonePe"],
            },
        )
        req = TaskRequest(user_turn="send hi to Pallavi on WhatsApp")
        interp = interpret_task_request(req, brain_workspace=ws)
        ctx = interp.notes.get("activated_context") or {}
        assert ctx.get("top_evidence")
        assert interp.notes.get("l1_preferred_entity") == "Pallavi PhonePe"
        # Goal not committed by interpret from activation alone
        assert not getattr(interp.goal, "committed_entity_id", None)
    finally:
        store.close()


def test_agent_runtime_reuses_session_workspace(tmp_path):
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
        sid = "brain-act-persist"
        session = get_or_create_session(sid)
        session.brain_workspace = BrainWorkspace(session_ref=sid)
        session.brain_workspace.bindings = [{"role": "recipient", "entity_id": "E_KEEP"}]
        session.brain_workspace.working_context = {
            "recent_entity_name": "Pallavi PhonePe",
            "recent_entity_names": ["Pallavi PhonePe"],
        }

        runtime = AgentRuntime(
            runtime_state=RuntimeState(),
            memory=store,
            task_request=TaskIngress.normalize(
                TaskRequest(
                    user_turn="send Pallavi the deck",
                    session=SessionRef(sid),
                    client_context={"client": "test"},
                )
            ),
        )
        turn = runtime.handle_turn(
            TaskRequest(
                user_turn="send Pallavi the deck",
                session=SessionRef(sid),
                client_context={"client": "test"},
            )
        )
        mp._PROVIDERS[:] = original

        ws = session.brain_workspace
        assert ws is not None
        assert ws.bindings[0]["entity_id"] == "E_KEEP"
        # Activation must not have wiped bindings or authored desired_effects
        assert any(b.get("entity_id") == "E_KEEP" for b in ws.bindings)
        # desired_effects remain whatever brain/interpret owns (empty until later slices)
        assert isinstance(ws.desired_effects, list)

        trace = turn.acceptance_trace or {}
        act = trace.get("context_activation") or {}
        assert act.get("committed") is False
        assert act.get("l1_recent_entity") == "Pallavi PhonePe"
        # Interpretation consumed activation
        notes = getattr(turn.interpretation, "notes", None) or {}
        assert notes.get("activated_context") or (trace.get("goal_interpretation"))
        # Prefer checking interpretation notes when present on turn
        if turn.interpretation is not None:
            assert (turn.interpretation.notes or {}).get("activated_context")
            assert (turn.interpretation.notes or {}).get("l1_preferred_entity") == (
                "Pallavi PhonePe"
            )
    finally:
        store.close()
        reset_session_store()


def test_consultation_context_projection():
    ws = BrainWorkspace()
    ws.retrieved_evidence = [
        {
            "ref": "E1",
            "canonical_name": "Pallavi PhonePe",
            "final_score": 1.0,
            "salience": "l1",
            "ref_kind": "entity",
        }
    ]
    ws.working_context = {"recent_entity_name": "Pallavi PhonePe"}
    ws.hypotheses = [{"entity_id": "E1", "canonical_name": "Pallavi PhonePe"}]
    ctx = consultation_context_from_workspace(ws)
    assert ctx["entity_names"] == ["Pallavi PhonePe"]
    assert ctx["working_context"]["recent_entity_name"] == "Pallavi PhonePe"
