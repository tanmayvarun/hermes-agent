"""Housekeeping capabilities: staged cleanup + meta act+capability wiring."""

from __future__ import annotations

from plugin.agent.capabilities.base import CapabilityRequest
from plugin.agent.capabilities.catalog import realized_verbs, spec_by_name
from plugin.agent.capabilities.dispatch import can_dispatch, dispatch
from plugin.agent.capabilities.housekeeping import (
    admissible_housekeeping_capabilities,
    blockers_from_features,
    is_meta_housekeeping_verb,
)
from plugin.agent.executive.meta_action import MetaAction, MetaContext
from plugin.agent.executive.meta_consultation import (
    meta_context_packet,
    sanitize_meta_choice,
)
from plugin.agent.executive.meta_situation import MetaSituation
from plugin.agent.runtime.recovery import _load_disk_cleanup_library, perform_storage_cleanup


def test_housekeeping_verbs_are_realized_and_dispatchable():
    assert "relieve_host_storage" in realized_verbs()
    assert "recover_blocked_app" in realized_verbs()
    assert can_dispatch("relieve_host_storage")
    assert can_dispatch("recover_blocked_app")
    assert spec_by_name("relieve_host_storage").requires_geometry is False


def test_blockers_and_admissible_shortlist_under_storage_pressure():
    blockers = blockers_from_features(
        {
            "extras": {
                "storage_pressure": True,
                "system_warnings": ["Storage is too full"],
                "dialogs": ["Exit WhatsApp"],
            }
        }
    )
    assert blockers["storage_pressure"] is True
    assert blockers["exit_cta_visible"] is True
    caps = admissible_housekeeping_capabilities(blockers)
    names = [c["name"] for c in caps]
    assert names[0] == "relieve_host_storage"
    assert "recover_blocked_app" in names
    assert is_meta_housekeeping_verb("relieve_host_storage")


def test_meta_sanitize_prefers_relieve_under_storage_pressure():
    sit = MetaSituation(
        blockers={"storage_pressure": True, "system_warnings": ["Storage is too full"]},
        housekeeping_capabilities=[
            {"name": "relieve_host_storage", "why": "free space"},
            {"name": "recover_blocked_app", "why": "relaunch"},
        ],
    )
    ctx = MetaContext(has_grounded_action=False)
    choice = sanitize_meta_choice(
        {
            "meta_action": "act",
            "capability": "compose_search_query",
            "why": "search",
            "confidence": 0.9,
        },
        ctx,
        situation=sit,
    )
    assert choice is not None
    assert choice.action is MetaAction.ACT
    assert choice.capability == "relieve_host_storage"

    kept = sanitize_meta_choice(
        {
            "meta_action": "act",
            "capability": "relieve_host_storage",
            "why": "cleanup low importance first",
            "confidence": 0.95,
        },
        ctx,
        situation=sit,
    )
    assert kept is not None
    assert kept.capability == "relieve_host_storage"


def test_meta_packet_includes_blockers_and_housekeeping():
    sit = MetaSituation(
        blockers={"storage_pressure": True, "system_warnings": ["Storage is too full"]},
        housekeeping_capabilities=[{"name": "relieve_host_storage", "why": "free space"}],
    )
    packet = meta_context_packet(MetaContext(), situation=sit)
    assert "blockers" in packet
    assert packet["blockers"]["storage_pressure"] is True
    assert packet["options"]["housekeeping_capabilities"][0]["name"] == "relieve_host_storage"


def test_staged_cleanup_stops_when_headroom_already_met(monkeypatch):
    import plugin.agent.runtime.recovery as recovery

    class FakeLib:
        @staticmethod
        def resolve_headroom_target(*, evidence=None, text="", default_bytes=0):
            return 100

        @staticmethod
        def relieve_until_headroom(
            *, target_free_bytes=None, evidence=None, reason="", volume_path="/"
        ):
            return {
                "deleted": 0,
                "empty_dirs": 0,
                "freed": 0,
                "errors": [],
                "stages": [],
                "stopped_early": True,
                "stop_reason": "headroom_already_met",
                "target_free_bytes": target_free_bytes,
                "free_before": 999,
                "free_after": 999,
                "headroom_met": True,
            }

        @staticmethod
        def analyze_low_risk_cleanup_targets(**_):
            return {
                "reason": "t",
                "evidence": [],
                "candidates": [],
                "total_size": 0,
                "total_size_human": "0",
                "low_risk_count": 0,
                "low_risk_human": "0",
                "sources": {},
                "notes": [],
            }

    monkeypatch.setattr(recovery, "_load_disk_cleanup_library", lambda: FakeLib())
    result = perform_storage_cleanup(
        reason="test",
        evidence=[r"\bstorage full\b"],
        staged=True,
    )
    assert result.disk_cleanup["headroom_met"] is True
    assert result.disk_cleanup["stop_reason"] == "headroom_already_met"
    assert result.disk_cleanup["stages"] == []


def test_staged_cleanup_runs_low_importance_stages_in_order(monkeypatch):
    lib = _load_disk_cleanup_library()
    calls = []
    # free_bytes: start low; stay low through first stage; jump after host_temp.
    free_seq = {"n": 0, "vals": [10, 10, 5_000_000_000]}

    def fake_free(path="/"):
        i = min(free_seq["n"], len(free_seq["vals"]) - 1)
        free_seq["n"] += 1
        return free_seq["vals"][i]

    monkeypatch.setattr(lib, "free_bytes", fake_free)
    monkeypatch.setattr(
        lib,
        "quick",
        lambda: calls.append("tracked_disposables")
        or {"deleted": 1, "empty_dirs": 0, "freed": 100, "errors": []},
    )
    monkeypatch.setattr(
        lib,
        "_cleanup_host_temp_roots",
        lambda: calls.append("host_temp")
        or {"deleted": 1, "empty_dirs": 0, "freed": 200, "errors": []},
    )
    monkeypatch.setattr(
        lib,
        "_cleanup_host_cache_roots",
        lambda: calls.append("host_cache")
        or {"deleted": 1, "empty_dirs": 0, "freed": 300, "errors": []},
    )

    out = lib.relieve_until_headroom(target_free_bytes=1_000_000_000, reason="test")
    assert calls[0] == "tracked_disposables"
    assert "host_temp" in calls
    assert "host_cache" not in calls  # stopped once headroom met after temp
    assert out["headroom_met"] is True
    assert out["stages"][0]["stage"] == "tracked_disposables"


def test_relieve_capability_dispatches(monkeypatch):
    monkeypatch.setattr(
        "plugin.agent.runtime.recovery.perform_storage_cleanup",
        lambda **kwargs: type(
            "R",
            (),
            {
                "triggered": True,
                "reason": kwargs.get("reason"),
                "evidence": list(kwargs.get("evidence") or []),
                "analysis": {},
                "disk_cleanup": {
                    "freed": 500,
                    "stages": [{"stage": "tracked_disposables"}],
                    "headroom_met": True,
                    "stop_reason": "headroom_met",
                    "free_after": 999,
                    "target_free_bytes": 100,
                },
                "environments_cleaned": 0,
            },
        )(),
    )
    outcome = dispatch(
        CapabilityRequest(
            name="relieve_host_storage", app="WhatsApp", extras={"reason": "test"}
        ),
        overlay=None,
    )
    assert outcome.ok
    assert outcome.capability == "relieve_host_storage"
    assert outcome.evidence.get("headroom_met") is True


def test_parse_required_free_bytes_from_whatsapp_copy():
    lib = _load_disk_cleanup_library()
    required = lib.parse_required_free_bytes(
        text="To keep using WhatsApp, free up at least 204.34 MB of space."
    )
    assert required is not None
    assert 200 * 1024 * 1024 < required < 210 * 1024 * 1024
    free_now = 480 * 1024 * 1024
    target = lib.resolve_headroom_target(
        text="free up at least 204.34 MB",
        default_bytes=512 * 1024 * 1024,
        free_now=free_now,
    )
    # App ask is incremental reclaim, not an absolute free-space floor.
    assert target > free_now
    assert target >= free_now + required


def test_after_relieve_soft_prefers_recover():
    sit = MetaSituation(
        blockers={
            "storage_pressure": True,
            "system_warnings": ["Storage is too full"],
            "last_housekeeping": "relieve_host_storage",
        },
        housekeeping_capabilities=[
            {"name": "relieve_host_storage", "why": "free space"},
            {"name": "recover_blocked_app", "why": "relaunch"},
        ],
    )
    choice = sanitize_meta_choice(
        {
            "meta_action": "act",
            "why": "storage still up",
            "confidence": 0.9,
        },
        MetaContext(),
        situation=sit,
    )
    assert choice is not None
    assert choice.action is MetaAction.ACT
    assert choice.capability == "recover_blocked_app"

    recover = sanitize_meta_choice(
        {
            "meta_action": "act",
            "capability": "recover_blocked_app",
            "why": "exit and relaunch",
            "confidence": 0.9,
        },
        MetaContext(),
        situation=sit,
    )
    assert recover is not None
    assert recover.action is MetaAction.ACT
    assert recover.capability == "recover_blocked_app"


def test_relieve_uses_observation_text_for_required_free(monkeypatch):
    captured = {}

    def fake_cleanup(**kwargs):
        captured.update(kwargs)
        return type(
            "R",
            (),
            {
                "triggered": True,
                "reason": kwargs.get("reason"),
                "evidence": list(kwargs.get("evidence") or []),
                "analysis": {},
                "disk_cleanup": {
                    "freed": 1,
                    "stages": [{"stage": "tracked_disposables"}],
                    "headroom_met": False,
                    "stop_reason": "stages_exhausted",
                    "free_before": 100,
                    "free_after": 101,
                    "target_free_bytes": 200,
                },
                "environments_cleaned": 0,
            },
        )()

    monkeypatch.setattr(
        "plugin.agent.runtime.recovery.perform_storage_cleanup",
        fake_cleanup,
    )
    outcome = dispatch(
        CapabilityRequest(
            name="relieve_host_storage",
            app="WhatsApp",
            extras={
                "reason": "storage",
                "observation_texts": [
                    "Storage is too full",
                    "free up at least 11.88 MB of space",
                ],
                "evidence": [r"\bstorage is too full\b"],
            },
        ),
        overlay=None,
    )
    assert outcome.ok
    assert "11.88" in str(captured.get("headroom_text") or "")
    assert outcome.evidence.get("required_free_bytes") is not None
    assert 11 * 1024 * 1024 < int(outcome.evidence["required_free_bytes"]) < 13 * 1024 * 1024
