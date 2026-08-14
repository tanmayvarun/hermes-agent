"""Architecture tests for named flow invariants (I1–I5).

Source-scanning gates — complements ``scripts/verify-flow-invariants.sh``.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import plugin.agent.runtime.agent_runtime as agent_runtime_mod
from plugin.agent.executive.setup_blockers import SetupBlocker
from plugin.agent.runtime.invariants import (
    ALL_INVARIANT_IDS,
    AgentRuntimeDomainIsolationPolicy,
    CuSetupBlockerAskPolicy,
    MethodFrontierWaGatewayFirstPolicy,
    RankingAuthorityPolicy,
    TaskOutcomeContractPolicy,
)
from plugin.agent.runtime.task_facts import (
    PHASE_AWAITING_USER,
    STATUS_WAITING_FOR_USER,
    vocab_schema,
)

ROOT = Path(__file__).resolve().parents[2]


def test_invariant_catalog_stable():
    assert ALL_INVARIANT_IDS == ("I1", "I2", "I3", "I4", "I5")


def test_i1_task_outcome_contract_policy():
    assert TaskOutcomeContractPolicy.should_settle(False) is True
    assert TaskOutcomeContractPolicy.should_settle(True) is False
    assert (
        TaskOutcomeContractPolicy.phase_for_status(STATUS_WAITING_FOR_USER)
        == PHASE_AWAITING_USER
    )


def test_i1_agent_runtime_settles_via_policy():
    src = Path(agent_runtime_mod.__file__).read_text(encoding="utf-8")
    assert "TaskOutcomeContractPolicy" in src
    assert "tracker.settle" in src
    handle_src = inspect.getsource(agent_runtime_mod.AgentRuntime.handle_turn)
    assert "TaskOutcomeContractPolicy.should_settle" in handle_src
    assert "tracker.settle" in handle_src


def test_i2_agent_runtime_has_no_whatsapp_imports():
    src = Path(agent_runtime_mod.__file__).read_text(encoding="utf-8")
    violations = AgentRuntimeDomainIsolationPolicy.source_violates(src)
    assert violations == [], f"I2 violations: {violations}"


def test_i3_gateway_reliability_beats_computer_use():
    assert MethodFrontierWaGatewayFirstPolicy.defaults_ok()
    wa = (ROOT / "plugin/agent/providers/whatsapp_gateway.py").read_text(encoding="utf-8")
    cu = (ROOT / "plugin/agent/providers/computer_use.py").read_text(encoding="utf-8")
    assert "reliability=0.88" in wa
    assert "reliability=0.55" in cu


def test_i4_setup_blocker_ask_evidence_shape():
    blocker = SetupBlocker(
        id="welcome",
        app="WhatsApp",
        title="Welcome",
        body="Finish WhatsApp setup",
    )
    evidence = blocker.ask_evidence()
    assert CuSetupBlockerAskPolicy.evidence_is_ask_prerequisite(evidence)
    assert CuSetupBlockerAskPolicy.should_skip_reask(
        precondition="desktop_app_ready",
        precondition_facts={"desktop_app_ready": True},
    )
    assert not CuSetupBlockerAskPolicy.should_skip_reask(
        precondition="desktop_app_ready",
        precondition_facts={},
    )
    runtime_src = Path(agent_runtime_mod.__file__).read_text(encoding="utf-8")
    assert "CuSetupBlockerAskPolicy.should_skip_reask" in runtime_src


def test_i5_ranking_authority_needles_present():
    src = Path(agent_runtime_mod.__file__).read_text(encoding="utf-8")
    missing = RankingAuthorityPolicy.missing_from_source(src)
    assert missing == [], f"I5 missing: {missing}"
    handle_src = inspect.getsource(agent_runtime_mod.AgentRuntime.handle_turn)
    assert "method_quality_score" not in handle_src
    assert "evaluated.sort" not in handle_src


def test_task_status_vocab_schema_checked_in():
    schema_path = ROOT / "plugin/agent/runtime/schemas/task_status_vocab.json"
    on_disk = json.loads(schema_path.read_text(encoding="utf-8"))
    assert on_disk == vocab_schema()
    assert "error_code_messages" in on_disk
    assert on_disk["error_codes"] == list(on_disk["error_code_messages"].keys())


def test_error_code_mapper_module_present():
    path = ROOT / "plugin/agent/runtime/error_codes.py"
    src = path.read_text(encoding="utf-8")
    assert "def resolve_user_message" in src
    assert "def client_error_payload" in src
    runtime = Path(agent_runtime_mod.__file__).read_text(encoding="utf-8")
    assert "infer_error_code" in runtime
    assert "error_code=" in runtime
