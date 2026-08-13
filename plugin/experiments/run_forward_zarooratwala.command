#!/bin/bash
# Live zarooratwala forward: eval preflight → agent startup → prompt.
# Same contract as "server must boot green before any API call."
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT="$(pwd)"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

export HERMES_LIVE_GOAL=1
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

# Prefer caller-provided stamp / live dir (/tmp) so bulky artifacts stay reclaimable.
STAMP="${HERMES_RUN_STAMP:-$(date +%Y%m%d_%H%M%S)}"
export HERMES_RUN_STAMP="$STAMP"
LIVE_ROOT="${HERMES_LIVE_RUN_DIR:-/tmp/hermes-runs}"
export HERMES_LIVE_RUN_DIR="$LIVE_ROOT"
LOG_DIR="${LIVE_ROOT}/${STAMP}"
mkdir -p "$LOG_DIR"

# Multi-pass affordance discovery: layered permanence under overlays.
export HERMES_LAYERED_PERCEPTION="${HERMES_LAYERED_PERCEPTION:-1}"
export HERMES_META_PERCEPTION="${HERMES_META_PERCEPTION:-1}"

# Freeze production perception packets for the semantic eval curriculum.
# Screenshots stay under experiments/fixtures (gitignored area); candidates
# land as screenshot+ax+executive_context+model_input/output bundles.
export HERMES_PERCEPTOR_RECORD_DIR="${HERMES_PERCEPTOR_RECORD_DIR:-${ROOT}/plugin/experiments/fixtures/perceptor/live_${STAMP}}"
export HERMES_PERCEPTION_EVAL_CANDIDATES_DIR="${HERMES_PERCEPTION_EVAL_CANDIDATES_DIR:-${ROOT}/plugin/evals/perception_semantic/eval_candidates}"
mkdir -p "$HERMES_PERCEPTOR_RECORD_DIR" "$HERMES_PERCEPTION_EVAL_CANDIDATES_DIR"

if [[ "${HERMES_EVAL_PREFLIGHT_DONE:-}" != "1" ]]; then
  echo "== package eval check (blocks launch on any failure)"
  "$PY" -m plugin.evals.check
  export HERMES_EVAL_PREFLIGHT_DONE=1
fi

export FORWARD_LOG="${LOG_DIR}/forward_zarooratwala_live_${STAMP}.jsonl"
export FORWARD_CONSOLE="${LOG_DIR}/terminal_forward_zarooratwala_${STAMP}_console.txt"
export FORWARD_STATUS="${LOG_DIR}/terminal_forward_zarooratwala_${STAMP}_status.txt"
# Override for relation probes, e.g. "sent to Pallavi" (recipient ≠ originator).
export FORWARD_PROMPT="${FORWARD_PROMPT:-Find the zarooratwala link from Pallavi on WhatsApp and forward it to Tanmay}"

printf 'status=launching\nstamp=%s\nlog_path=%s\nconsole_path=%s\ncwd=%s\n' \
  "$STAMP" "$FORWARD_LOG" "$FORWARD_CONSOLE" "$ROOT" > "$FORWARD_STATUS"

# Tiny repo pointers (not bulky logs).
mkdir -p "${ROOT}/plugin/experiments/runs"
printf '%s\n' "$STAMP" > "${ROOT}/plugin/experiments/runs/latest_live_stamp.txt"
printf '%s\n' "$LOG_DIR" > "${ROOT}/plugin/experiments/runs/latest_live_dir.txt"
printf '%s\n' "$STAMP" > /tmp/hermes_active_forward_stamp.txt

echo "== starting live forward agent  stamp=$STAMP log=$FORWARD_LOG layered=$HERMES_LAYERED_PERCEPTION"
echo "== perceptor record=$HERMES_PERCEPTOR_RECORD_DIR"
echo "== eval candidates=$HERMES_PERCEPTION_EVAL_CANDIDATES_DIR"
# Tee console so supervise can watch OK=/stall signals.
set +e
"$PY" -u -c "
from pathlib import Path
import os
from plugin.experiments.run_forward_message import run_forward_message

ok, _log = run_forward_message(
    log_path=Path(os.environ['FORWARD_LOG']),
    prompt=os.environ['FORWARD_PROMPT'],
    source_contact='Pallavi',
    target_contact='Tanmay',
    link_query='zarooratwala',
    max_iterations=100,
    # Soft step budget: compose+open+reveal recovery needs headroom beyond
    # config default 10 (live 125715 exhausted mid-menu relook/reflect).
    max_stepcount=int(os.environ.get('HERMES_MAX_STEPCOUNT', '40')),
)
raise SystemExit(0 if ok else 1)
" 2>&1 | tee "$FORWARD_CONSOLE"
rc=${PIPESTATUS[0]}
set -e
if [[ "$rc" -eq 0 ]]; then
  echo "OK=True LOG=$FORWARD_LOG" | tee -a "$FORWARD_CONSOLE"
  printf 'status=ok\nstamp=%s\n' "$STAMP" > "$FORWARD_STATUS"
else
  echo "OK=False LOG=$FORWARD_LOG" | tee -a "$FORWARD_CONSOLE"
  printf 'status=fail\nstamp=%s\n' "$STAMP" > "$FORWARD_STATUS"
fi
exit "$rc"
