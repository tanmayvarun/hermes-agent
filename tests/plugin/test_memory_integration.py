"""Integration goldens: startup bootstrap, adapters, pre-MethodFrontier binding."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from plugin.agent.goal import Goal
from plugin.agent.ingress import SessionRef, TaskIngress, TaskRequest
from plugin.agent.memory.bootstrap import (
    MemoryBootstrapCoordinator,
    MemoryBootstrapState,
    open_local_memory,
)
from plugin.agent.memory.pipeline import ContactObservation
from plugin.agent.memory.recipient_binding import resolve_recipient_before_methods
from plugin.agent.memory.sources import FixtureSourceAdapter, SourceObservationBatch
from plugin.agent.memory.system import NoopMemorySystem
from plugin.agent.runtime.agent_runtime import AgentRuntime
from plugin.agent.runtime.session_store import reset_session_store
from plugin.agent.runtime.state import RuntimeState
from plugin.agent.runtime.turn_result import TurnStatus


def _pallavi_obs(now: float) -> list[ContactObservation]:
    return [
        ContactObservation(
            provider="whatsapp",
            external_id="W17",
            display_name="Pallavi",
            aliases=["Pallavi"],
            last_interaction_at=now - 3600,
            interaction_count_7d=40,
            interaction_count_30d=180,
            interaction_count_180d=900,
            active_days_30d=28,
            frequency_known=True,
        ),
        ContactObservation(
            provider="whatsapp",
            external_id="W781",
            display_name="Pallavi PhonePe",
            aliases=["Pallavi PhonePe", "Pallavi"],
            last_interaction_at=now - 3 * 365 * 86400,
            interaction_count_7d=0,
            interaction_count_30d=0,
            interaction_count_180d=1,
            active_days_30d=0,
            frequency_known=True,
        ),
    ]


def test_hermes_startup_opens_local_memory_and_runs_incremental_day0_bootstrap(tmp_path):
    adapter = FixtureSourceAdapter(
        source_name="fixture_wa",
        observations=_pallavi_obs(time.time()),
    )
    store, coord = open_local_memory(
        root=tmp_path / "mem",
        start_bootstrap=True,
        blocking_bootstrap=True,
        adapters=[adapter],
    )
    try:
        assert store.get_bootstrap_state() in {
            MemoryBootstrapState.INTERACTION_READY.value,
            MemoryBootstrapState.FULLY_CAUGHT_UP.value,
            MemoryBootstrapState.IDENTITY_READY.value,
        }
        ents = store.find_entities_by_name("Pallavi")
        assert len(ents) >= 2
        # Distinct entities for distinct WhatsApp identities
        sids = store._conn.execute(
            "SELECT COUNT(*) AS c FROM source_identities"
        ).fetchone()["c"]
        assert sids >= 2
    finally:
        store.close()


def test_realistic_whatsapp_source_observations_create_distinct_pallavi_entities(
    tmp_path,
):
    store, _ = open_local_memory(
        root=tmp_path / "mem2",
        start_bootstrap=False,
        adapters=[],
    )
    try:
        coord = MemoryBootstrapCoordinator(
            store=store,
            adapters=[
                FixtureSourceAdapter(
                    source_name="wa",
                    observations=_pallavi_obs(time.time()),
                )
            ],
        )
        summary = coord.run_incremental(blocking=True)
        assert "wa" in summary["adapters"]
        names = {e.canonical_name for e in store.find_entities_by_name("Pallavi")}
        assert "Pallavi" in names
        assert any("PhonePe" in n for n in names)
        # Aggregates favor active Pallavi
        active = next(e for e in store.find_entities_by_name("Pallavi") if e.canonical_name == "Pallavi")
        stale = next(e for e in store.find_entities_by_name("Pallavi") if "PhonePe" in e.canonical_name)
        a = store.get_aggregate("user:local", active.entity_id, scope=active.scope)
        b = store.get_aggregate("user:local", stale.entity_id, scope=stale.scope)
        assert a and b
        assert a.count_30d > b.count_30d
    finally:
        store.close()


def test_tui_send_message_resolves_recipient_from_memory_before_method_selection(
    tmp_path,
):
    reset_session_store()
    adapter = FixtureSourceAdapter(
        source_name="fixture_wa",
        observations=_pallavi_obs(time.time()),
    )
    store, _ = open_local_memory(
        root=tmp_path / "mem3",
        start_bootstrap=True,
        blocking_bootstrap=True,
        adapters=[adapter],
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
                    session=SessionRef("mem-int-1"),
                    client_context={"client": "test"},
                )
            ),
        )
        turn = runtime.handle_turn(
            TaskRequest(
                user_turn="send hi to Pallavi on WhatsApp",
                session=SessionRef("mem-int-1"),
                client_context={"client": "test"},
            )
        )
        mp._PROVIDERS[:] = original

        # High-margin fixture must resolve — ASK is a failure here.
        assert turn.status != TurnStatus.WAITING_FOR_USER
        trace = turn.acceptance_trace or {}
        rr = trace.get("recipient_resolution") or {}
        assert rr.get("status") == "proceed"
        assert rr.get("entity_id")
        assert rr.get("channel_external_id") == "W17"
        goal = getattr(turn.interpretation, "goal", None)
        assert goal is not None
        assert goal.committed_entity_id
        assert goal.committed_channel_id == "W17"
    finally:
        store.close()
        reset_session_store()


def test_recipient_resolution_commits_channel_identity_to_goal(tmp_path):
    store, _ = open_local_memory(
        root=tmp_path / "mem4",
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
            recipient="Pallavi",
            target_contact="Pallavi",
            message_body="hi",
            app="WhatsApp",
        )
        rr = resolve_recipient_before_methods(
            store,
            goal=goal,
            desired_effects=["forward_message"],
            channel="whatsapp",
        )
        assert rr.status == "proceed"
        assert goal.committed_entity_id
        assert goal.committed_channel_id == "W17"
        assert "PhonePe" not in (goal.committed_display_name or "")
    finally:
        store.close()


def test_whatsapp_auth_required_does_not_become_identity_ready(tmp_path):
    from plugin.agent.memory.sources import SourceObservationBatch, SourceScanDisposition

    class AuthRequiredAdapter:
        source_name = "whatsapp_bridge"

        def scan(self, cursor=None):
            return SourceObservationBatch(
                observations=[],
                disposition=SourceScanDisposition.AUTH_REQUIRED,
                metadata={"skipped": True},
            )

    store, coord = open_local_memory(
        root=tmp_path / "mem_auth",
        start_bootstrap=True,
        blocking_bootstrap=True,
        adapters=[AuthRequiredAdapter()],
    )
    try:
        assert store.get_bootstrap_state() == MemoryBootstrapState.AUTH_REQUIRED.value
        assert store.get_bootstrap_state() != MemoryBootstrapState.IDENTITY_READY.value
    finally:
        store.close()


def test_unread_not_mapped_to_frequency_in_bridge_adapter(monkeypatch):
    """Adapter must not invent interaction_count from unread_count."""
    import io
    import json
    from plugin.agent.memory.sources import (
        SourceScanDisposition,
        WhatsAppBridgeSourceAdapter,
    )

    payload = {
        "contacts": [
            {
                "provider": "whatsapp",
                "external_id": "W99",
                "display_name": "Ignored Group",
                "aliases": ["Ignored Group"],
                "last_interaction_at": None,
                "unread_count": 40,
                "interaction_count_7d": None,
                "interaction_count_30d": None,
                "interaction_count_180d": None,
                "active_days_30d": None,
            }
        ],
        "cursor": "wa:done",
        "indexed": 1,
    }

    class _Resp:
        def read(self):
            return json.dumps(payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: _Resp(),
    )
    batch = WhatsAppBridgeSourceAdapter().scan(None)
    assert batch.disposition == SourceScanDisposition.SUCCESS
    assert len(batch.observations) == 1
    obs = batch.observations[0]
    assert obs.interaction_count_30d == 0
    assert obs.frequency_known is False
    assert obs.metadata.get("unread_count") == 40


def test_noop_memory_skips_resolution_without_blocking():
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        message_body="hi",
    )
    rr = resolve_recipient_before_methods(
        NoopMemorySystem(),
        goal=goal,
        desired_effects=["forward_message"],
    )
    assert rr.status == "skip"
    assert not goal.committed_entity_id


def test_recency_only_without_frequency_still_resolves_high_margin_pallavi(tmp_path):
    """Day-0 WhatsApp often lacks real frequency; recency alone must still work."""
    now = time.time()
    obs = [
        ContactObservation(
            provider="whatsapp",
            external_id="W17",
            display_name="Pallavi",
            aliases=["Pallavi"],
            last_interaction_at=now - 3600,
            frequency_known=False,
        ),
        ContactObservation(
            provider="whatsapp",
            external_id="W781",
            display_name="Pallavi PhonePe",
            aliases=["Pallavi PhonePe", "Pallavi"],
            last_interaction_at=now - 3 * 365 * 86400,
            frequency_known=False,
        ),
    ]
    store, _ = open_local_memory(
        root=tmp_path / "mem_recency",
        start_bootstrap=True,
        blocking_bootstrap=True,
        adapters=[FixtureSourceAdapter(source_name="wa", observations=obs)],
    )
    try:
        goal = Goal(
            kind="whatsapp_forward_message",
            contact="Pallavi",
            message_body="hi",
            app="WhatsApp",
        )
        rr = resolve_recipient_before_methods(
            store,
            goal=goal,
            desired_effects=["send_message"],
            channel="whatsapp",
        )
        assert rr.status == "proceed"
        assert rr.channel_external_id == "W17"
        assert goal.committed_channel_id == "W17"
    finally:
        store.close()


def test_fixture_adapter_scan_idempotent_with_cursor():
    adapter = FixtureSourceAdapter(
        source_name="f",
        observations=_pallavi_obs(time.time()),
    )
    batch1 = adapter.scan(None)
    assert len(batch1.observations) == 2
    batch2 = adapter.scan(batch1.next_cursor)
    assert batch2.observations == []
