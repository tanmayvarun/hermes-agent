#!/usr/bin/env bash
# Structural gates for named flow invariants (I1–I5).
# Mirrors ChargePe verify-flow-invariants.sh — fail closed if wiring drifts.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail() { echo "INVARIANT FAIL: $*" >&2; exit 1; }

RUNTIME="plugin/agent/runtime/agent_runtime.py"
TRACKER="plugin/agent/runtime/task_tracker.py"
INVARIANTS="plugin/agent/runtime/invariants.py"
SETUP="plugin/agent/executive/setup_blockers.py"
WA="plugin/agent/providers/whatsapp_gateway.py"
CU="plugin/agent/providers/computer_use.py"
FACTS="plugin/agent/runtime/task_facts.py"
SCHEMA="plugin/agent/runtime/schemas/task_status_vocab.json"

[[ -f "$RUNTIME" ]] || fail "missing $RUNTIME"
[[ -f "$INVARIANTS" ]] || fail "missing $INVARIANTS"
[[ -f "$FACTS" ]] || fail "missing $FACTS"
[[ -f "$SCHEMA" ]] || fail "missing $SCHEMA"

# I1 — settle path present
grep -q "tracker.settle" "$RUNTIME" || fail "I1: AgentRuntime must call tracker.settle"
grep -q "TaskOutcomeContractPolicy" "$RUNTIME" || fail "I1: settle must use TaskOutcomeContractPolicy"

# I2 — no WhatsApp domain imports in AgentRuntime
if grep -E "plugin\.agent\.apps\.whatsapp|providers\.whatsapp_gateway|hermes_cli\.whatsapp_pairing|identity_evidence\.whatsapp" "$RUNTIME"; then
  fail "I2: AgentRuntime must not import WhatsApp adapters"
fi

# I5 — ranking authority
grep -q "decide_methods" "$RUNTIME" || fail "I5: AgentRuntime must call decide_methods"

# I4 — setup blocker ASK evidence
grep -q 'ask_prerequisite' "$SETUP" || fail "I4: SetupBlocker.ask_evidence must set ask_prerequisite"
grep -q "CuSetupBlockerAskPolicy" "$RUNTIME" || fail "I4: AgentRuntime must use CuSetupBlockerAskPolicy for re-ASK skip"

# I3 — gateway reliability above CU
grep -q "reliability=0.88" "$WA" || fail "I3: WhatsApp gateway reliability must be 0.88"
grep -q "reliability=0.55" "$CU" || fail "I3: ComputerUse reliability must be 0.55"

# Facts re-export
grep -q "task_facts" "$TRACKER" || fail "task_tracker must import canonical task_facts"

echo "verify-flow-invariants: OK (I1–I5)"
