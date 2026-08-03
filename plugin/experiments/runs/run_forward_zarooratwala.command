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
export HERMES_PERCEPTION_LLM_MAX_TOKENS=2048
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
# Executive loop (meta-action dispatch + perception gate). This was opt-in only
# while perception was blocked (a chrome-only AX tree gave it nothing to ground,
# so it thrashed). That blocker is resolved: the vision model (qwen3.5:397b)
# perceives content again, so the executive loop now has real state to reason
# over and is on by default. Set HERMES_META_PERCEPTION=0 to disable.
: "${HERMES_META_PERCEPTION:=1}"
export HERMES_META_PERCEPTION
# Perceptor: the multimodal brain is off by default in code (it reroutes every
# decision path), so the live experiment turns it on. Unified cognition reasons
# over the screenshot; layered perception models overlays/occlusion; OCR recovers
# content from pixels when the AX tree is blind. These are the perceptor's best
# form — restore them here (the hard reset wiped them from this launcher).
: "${HERMES_UNIFIED_COGNITION:=1}"
: "${HERMES_LAYERED_PERCEPTION:=1}"
: "${HERMES_PERCEPTION_OCR:=1}"
export HERMES_UNIFIED_COGNITION
export HERMES_LAYERED_PERCEPTION
export HERMES_PERCEPTION_OCR
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
log_path="plugin/experiments/runs/forward_zarooratwala_live_${stamp}.jsonl"
console_path="plugin/experiments/runs/terminal_forward_zarooratwala_${stamp}_console.txt"
status_path="plugin/experiments/runs/terminal_forward_zarooratwala_${stamp}_status.txt"

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
} | tee -a "${console_path}"

./.venv/bin/python -c "from pathlib import Path; from plugin.experiments.run_forward_message import run_forward_message; ok, log = run_forward_message(log_path=Path('${log_path}'), prompt='find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi', source_contact='Kulvinder', target_contact='Pallavi', link_query='zarooratwala', max_iterations=100, max_stepcount=100); print(f'OK={ok} LOG=${log_path}')" 2>&1 | tee -a "${console_path}"
