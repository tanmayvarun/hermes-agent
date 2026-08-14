"""Named flow invariants (ChargePe-style IDs) as pure policy objects.

Invariant IDs are stable; architecture tests + ``scripts/verify-flow-invariants.sh``
enforce that production wiring still delegates to these policies / seams.
"""

from __future__ import annotations

from typing import Any, Mapping

from plugin.agent.runtime.task_facts import (
    PHASE_AWAITING_USER,
    PHASE_FINISHING,
    STATUS_WAITING_FOR_USER,
    phase_for_final_status,
)

# ---------------------------------------------------------------------------
# I1 — Task outcome contract: every handle_turn exit settles the tracker
# ---------------------------------------------------------------------------

INVARIANT_I1_TASK_OUTCOME_SETTLE = "I1"


class TaskOutcomeContractPolicy:
    """I1: settle phase + forbid double-settle semantics helpers."""

    INVARIANT_ID = INVARIANT_I1_TASK_OUTCOME_SETTLE

    @staticmethod
    def phase_for_status(final_status: str) -> str:
        return phase_for_final_status(final_status)

    @staticmethod
    def should_settle(already_settled: bool) -> bool:
        return not bool(already_settled)

    @staticmethod
    def awaiting_user_phase(final_status: str) -> bool:
        return str(final_status or "") == STATUS_WAITING_FOR_USER


# ---------------------------------------------------------------------------
# I2 — AgentRuntime must stay domain-substrate free (no WA branches)
# ---------------------------------------------------------------------------

INVARIANT_I2_NO_DOMAIN_IN_RUNTIME = "I2"

# Tokens that must not appear as imports / call sites in AgentRuntime core.
AGENT_RUNTIME_FORBIDDEN_IMPORT_NEEDLES: tuple[str, ...] = (
    "plugin.agent.apps.whatsapp",
    "plugin.agent.providers.whatsapp_gateway",
    "hermes_cli.whatsapp_pairing",
    "identity_evidence.whatsapp",
    "procedures.forward_message",
)


class AgentRuntimeDomainIsolationPolicy:
    """I2: AgentRuntime must not import WhatsApp / forward adapters."""

    INVARIANT_ID = INVARIANT_I2_NO_DOMAIN_IN_RUNTIME

    @staticmethod
    def forbidden_needles() -> tuple[str, ...]:
        return AGENT_RUNTIME_FORBIDDEN_IMPORT_NEEDLES

    @staticmethod
    def source_violates(source: str) -> list[str]:
        src = source or ""
        return [n for n in AGENT_RUNTIME_FORBIDDEN_IMPORT_NEEDLES if n in src]


# ---------------------------------------------------------------------------
# I3 — MethodFrontier: WhatsApp gateway preferred over Computer Use
# ---------------------------------------------------------------------------

INVARIANT_I3_GATEWAY_BEFORE_CU = "I3"

WHATSAPP_GATEWAY_RELIABILITY_FLOOR = 0.88
COMPUTER_USE_RELIABILITY_CEILING = 0.55


class MethodFrontierWaGatewayFirstPolicy:
    """I3: gateway reliability must strictly exceed computer_use for forwards."""

    INVARIANT_ID = INVARIANT_I3_GATEWAY_BEFORE_CU

    @staticmethod
    def gateway_beats_computer_use(
        *, gateway_reliability: float, computer_use_reliability: float
    ) -> bool:
        return float(gateway_reliability) > float(computer_use_reliability)

    @staticmethod
    def defaults_ok() -> bool:
        return MethodFrontierWaGatewayFirstPolicy.gateway_beats_computer_use(
            gateway_reliability=WHATSAPP_GATEWAY_RELIABILITY_FLOOR,
            computer_use_reliability=COMPUTER_USE_RELIABILITY_CEILING,
        )


# ---------------------------------------------------------------------------
# I4 — Setup blockers must recover via ask_prerequisite (not silent CU burn)
# ---------------------------------------------------------------------------

INVARIANT_I4_SETUP_BLOCKER_ASK = "I4"


class CuSetupBlockerAskPolicy:
    """I4: SetupBlocker.ask_evidence must drive ASK, not CU thrash."""

    INVARIANT_ID = INVARIANT_I4_SETUP_BLOCKER_ASK

    @staticmethod
    def evidence_is_ask_prerequisite(evidence: Mapping[str, Any]) -> bool:
        if not isinstance(evidence, Mapping):
            return False
        return str(evidence.get("fallback") or "").strip() == "ask_prerequisite" and bool(
            str(evidence.get("ask_precondition") or "").strip()
        )

    @staticmethod
    def should_skip_reask(
        *,
        precondition: str,
        precondition_facts: Mapping[str, Any],
    ) -> bool:
        """If the fact is already true this session, do not re-ASK."""
        pre = str(precondition or "").strip()
        if not pre:
            return False
        return bool(precondition_facts.get(pre))


# ---------------------------------------------------------------------------
# I5 — Ranking authority stays on MethodFrontier (decide_methods)
# ---------------------------------------------------------------------------

INVARIANT_I5_RANKING_AUTHORITY = "I5"

AGENT_RUNTIME_REQUIRED_RANKING_NEEDLES: tuple[str, ...] = (
    "decide_methods",
    "tracker.settle",
)


class RankingAuthorityPolicy:
    """I5: handle_turn must delegate ranking and always settle."""

    INVARIANT_ID = INVARIANT_I5_RANKING_AUTHORITY

    @staticmethod
    def required_needles() -> tuple[str, ...]:
        return AGENT_RUNTIME_REQUIRED_RANKING_NEEDLES

    @staticmethod
    def missing_from_source(source: str) -> list[str]:
        src = source or ""
        return [n for n in AGENT_RUNTIME_REQUIRED_RANKING_NEEDLES if n not in src]


# ---------------------------------------------------------------------------
# Helpers used by architecture tests
# ---------------------------------------------------------------------------

ALL_INVARIANT_IDS: tuple[str, ...] = (
    INVARIANT_I1_TASK_OUTCOME_SETTLE,
    INVARIANT_I2_NO_DOMAIN_IN_RUNTIME,
    INVARIANT_I3_GATEWAY_BEFORE_CU,
    INVARIANT_I4_SETUP_BLOCKER_ASK,
    INVARIANT_I5_RANKING_AUTHORITY,
)


def settle_phase_for_turn_status(turn_status: str) -> str:
    """I1 presentation of settle phase from a turn status string."""
    from plugin.agent.runtime.task_facts import final_status_from_turn

    final = final_status_from_turn(turn_status)
    phase = TaskOutcomeContractPolicy.phase_for_status(final)
    if phase == PHASE_AWAITING_USER:
        return PHASE_AWAITING_USER
    return PHASE_FINISHING
