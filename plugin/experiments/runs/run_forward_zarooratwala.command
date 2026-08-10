#!/bin/bash
set -euo pipefail

cd "/Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent"

if [ -f ".env" ]; then
  set -a
  # Load project env so the auxiliary chain sees the remote Ollama box.
  . "./.env"
  set +a
fi

unset OLLAMA_REMOTE_BASE_URL
: "${HERMES_MODEL:=gpt-oss:120b}"
: "${HERMES_INFERENCE_MODEL:=gpt-oss:120b}"
: "${HERMES_PERCEPTION_MODEL:=gpt-oss:120b}"
: "${HERMES_DECISION_MODEL:=gpt-oss:120b}"
: "${HERMES_DECISION_HIGH_RISK_MODEL:=gpt-oss:120b}"
: "${HERMES_INFERENCE_PROVIDER:=ollama-cloud}"
: "${HERMES_TUI_PROVIDER:=ollama-cloud}"
: "${HERMES_PERCEPTION_PROVIDER:=ollama-cloud}"
: "${HERMES_DECISION_PROVIDER:=ollama-cloud}"
: "${HERMES_DECISION_HIGH_RISK_PROVIDER:=ollama-cloud}"
export HERMES_MAX_TOKENS=4096
# Fast perception path: small local VLM first (think off, ROI, tiny JSON);
# escalate to cloud vision only on low confidence / needs_more_evidence.
: "${HERMES_PERCEPTION_LLM_MAX_TOKENS:=250}"
export HERMES_PERCEPTION_LLM_MAX_TOKENS
: "${HERMES_PERCEPTION_COMPACT:=1}"
export HERMES_PERCEPTION_COMPACT
: "${HERMES_PERCEPTION_THINK:=0}"
export HERMES_PERCEPTION_THINK
# Cloud vision remains the escalate SoT (override .env pins to 120b/text).
HERMES_PERCEPTION_MODEL="${HERMES_PERCEPTION_VISION_MODEL:-qwen3.5:cloud}"
HERMES_PERCEPTION_PROVIDER=ollama-cloud
export HERMES_MODEL
export HERMES_INFERENCE_MODEL
export HERMES_PERCEPTION_MODEL
export HERMES_DECISION_MODEL
export HERMES_DECISION_HIGH_RISK_MODEL
export HERMES_INFERENCE_PROVIDER
export HERMES_TUI_PROVIDER
export HERMES_PERCEPTION_PROVIDER
export HERMES_DECISION_PROVIDER
export HERMES_DECISION_HIGH_RISK_PROVIDER
export HERMES_AUXILIARY_PROVIDER_POLICY=ollama-only
: "${HERMES_FORWARD_STRICT_PERCEPTION:=1}"
: "${HERMES_FORWARD_PERCEPTION_SOURCE_TIMEOUT_SECONDS:=30}"
: "${HERMES_FORWARD_STRICT_PERCEPTION_RETRIES:=3}"
: "${HERMES_PERCEPTION_LLM_TIMEOUT_SECONDS:=240}"
: "${HERMES_PERCEPTION_PROMPT_SHAPE:=balanced}"
: "${HERMES_DECISION_TIMEOUT:=60}"
: "${HERMES_DECISION_HIGH_RISK_TIMEOUT:=60}"
: "${HERMES_DECISION_SELECTOR_TIMEOUT_SECONDS:=60}"
: "${HERMES_DECISION_HIGH_RISK_SELECTOR_TIMEOUT_SECONDS:=60}"
: "${HERMES_SELECTOR_STRICT:=1}"
: "${HERMES_META_PERCEPTION:=1}"
export HERMES_META_PERCEPTION
: "${HERMES_UNIFIED_COGNITION:=1}"
: "${HERMES_LAYERED_PERCEPTION:=1}"
: "${HERMES_PERCEPTION_OCR:=1}"
# Phase ROI @ 640 — bench win (~−62% vs full-frame 397B path).
: "${HERMES_PERCEPTION_ROI:=phase}"
: "${HERMES_UNIFIED_IMAGE_MAX_WIDTH:=640}"
: "${HERMES_PERCEPTION_ESCALATE_MODEL:=qwen3.5:cloud}"
# Pinned fast winner from model sweep (override with env if sweep picks another).
: "${HERMES_PERCEPTION_FAST_MODEL:=qwen3.5:4b}"
: "${HERMES_PERCEPTION_FAST_BASE_URL:=http://127.0.0.1:11434/v1}"
export HERMES_UNIFIED_COGNITION
export HERMES_LAYERED_PERCEPTION
export HERMES_PERCEPTION_OCR
export HERMES_PERCEPTION_ROI
export HERMES_UNIFIED_IMAGE_MAX_WIDTH
export HERMES_PERCEPTION_ESCALATE_MODEL
export HERMES_PERCEPTION_FAST_MODEL
export HERMES_PERCEPTION_FAST_BASE_URL
# Foreground persistence: take the app back, don't wait for it. A call or a
# notification steals the foreground mid-task and every synthetic click after
# that lands in whatever window took it, so the agent raises WhatsApp itself,
# every iteration it finds it gone, uncapped — the interruptions this answers
# recur by nature. Off by default in code so headless control-loop tests (whose
# frontmost app is the test runner) never engage it.
: "${HERMES_FOREGROUND_GATE:=1}"
export HERMES_FOREGROUND_GATE
# Commit gate: verify the target immediately before acting. Perception is ~60s
# stale by the time an action lands (measured: 35-76s), so a coordinate resolved
# from that frame is a claim about the past. This re-reads the target rectangle
# and refuses the click when it no longer holds what the decision chose. Off by
# default in code because it reads the live screen.
: "${HERMES_ACTION_GUARD:=1}"
export HERMES_ACTION_GUARD
# World critic's appeal court. The deterministic rules settle the ordinary frame
# for free; this is consulted only for a change they cannot account for — an
# object inventory rewritten with no action to explain it, or a surface jump the
# hand-written topology table does not know about. Off by default in code so no
# offline test reaches for a model.
: "${HERMES_CRITIC_COHERENCE:=1}"
export HERMES_CRITIC_COHERENCE
# Wall-clock budget for the whole goal. The machine config says 900s, which cut
# the previous run off at 917s having just opened the source conversation — the
# forward, destination pick and send never got a turn. A convergence test has to
# be allowed to finish, otherwise the result measures the budget rather than the
# agent.
: "${HERMES_GOAL_RUN_TIMEOUT_SECONDS:=2700}"
export HERMES_GOAL_RUN_TIMEOUT_SECONDS
export HERMES_FORWARD_STRICT_PERCEPTION
export HERMES_FORWARD_PERCEPTION_SOURCE_TIMEOUT_SECONDS
export HERMES_FORWARD_STRICT_PERCEPTION_RETRIES
export HERMES_PERCEPTION_LLM_TIMEOUT_SECONDS
export HERMES_PERCEPTION_PROMPT_SHAPE
export HERMES_DECISION_TIMEOUT
export HERMES_DECISION_HIGH_RISK_TIMEOUT
export HERMES_DECISION_SELECTOR_TIMEOUT_SECONDS
export HERMES_DECISION_HIGH_RISK_SELECTOR_TIMEOUT_SECONDS
export HERMES_SELECTOR_STRICT

stamp="${HERMES_RUN_STAMP:-$(python3 -c 'import time; print(time.strftime("%Y%m%d_%H%M%S")+"_"+str(time.time_ns()))')}"
# Bulky live artifacts under /tmp/hermes-runs so relieve_host_storage's host_temp
# stage can reclaim them (hermes- prefix). Repo runs/ keeps only tiny pointers.
LIVE_RUN_ROOT="${HERMES_LIVE_RUN_DIR:-/tmp/hermes-runs}"
LIVE_RUN_DIR="${LIVE_RUN_ROOT}/${stamp}"
mkdir -p "${LIVE_RUN_DIR}"
log_path="${LIVE_RUN_DIR}/forward_zarooratwala_live_${stamp}.jsonl"
console_path="${LIVE_RUN_DIR}/terminal_forward_zarooratwala_${stamp}_console.txt"
status_path="${LIVE_RUN_DIR}/terminal_forward_zarooratwala_${stamp}_status.txt"
printf '%s\n' "${stamp}" > "plugin/experiments/runs/latest_live_stamp.txt"
printf '%s\n' "${LIVE_RUN_DIR}" > "plugin/experiments/runs/latest_live_dir.txt"
printf '%s\n' "${stamp}" > /tmp/hermes_active_forward_stamp.txt
export HERMES_LIVE_RUN_DIR="${LIVE_RUN_ROOT}"
export HERMES_RUN_STAMP="${stamp}"

# Freeze production perception packets for the semantic eval curriculum.
ROOT="$(pwd)"
export HERMES_PERCEPTOR_RECORD_DIR="${HERMES_PERCEPTOR_RECORD_DIR:-${ROOT}/plugin/experiments/fixtures/perceptor/live_${stamp}}"
export HERMES_PERCEPTION_EVAL_CANDIDATES_DIR="${HERMES_PERCEPTION_EVAL_CANDIDATES_DIR:-${ROOT}/plugin/evals/perception_semantic/eval_candidates}"
mkdir -p "$HERMES_PERCEPTOR_RECORD_DIR" "$HERMES_PERCEPTION_EVAL_CANDIDATES_DIR"

# mvn-test equivalent: goldens + gates + focused pytest must be green before
# burning a live run. No skip env — red evals always refuse launch.
# Launchers that already ran a green check may export HERMES_EVAL_PREFLIGHT_DONE=1.
if [ "${HERMES_EVAL_PREFLIGHT_DONE:-0}" != "1" ]; then
  echo "=== eval package check (preflight) ===" | tee -a "${console_path:-/dev/null}"
  # Capture check output into the run console so Terminal.app refusals are diagnosable.
  if ! ./.venv/bin/python -m plugin.evals.check 2>&1 | tee -a "${console_path:-/dev/null}"; then
    {
      echo "status=eval_check_failed"
      echo "stamp=${stamp}"
      echo "message=plugin.evals.check failed — refuse live launch"
    } > "${status_path}"
    echo "REFUSING live launch: package eval check failed" >&2
    exit 1
  fi
  export HERMES_EVAL_PREFLIGHT_DONE=1
fi

{
  echo "status=launching"
  echo "stamp=${stamp}"
  echo "log_path=${log_path}"
  echo "console_path=${console_path}"
  echo "cwd=$(pwd)"
} > "${status_path}"
{
  echo "=== launch start ${stamp} ==="
  echo "log_path=${log_path}"
  echo "console_path=${console_path}"
  echo "status_path=${status_path}"
  echo "perceptor_record=${HERMES_PERCEPTOR_RECORD_DIR}"
  echo "eval_candidates=${HERMES_PERCEPTION_EVAL_CANDIDATES_DIR}"
} | tee -a "${console_path}"

./.venv/bin/python -c "from pathlib import Path; from plugin.experiments.run_forward_message import run_forward_message; ok, log = run_forward_message(log_path=Path('${log_path}'), prompt='find the zarooratwala link sent to pallavi on whatsapp and forward to tanmay', source_contact='Pallavi', target_contact='Tanmay', link_query='zarooratwala', max_iterations=100, max_stepcount=100); print(f'OK={ok} LOG=${log_path}')" 2>&1 | tee -a "${console_path}"
