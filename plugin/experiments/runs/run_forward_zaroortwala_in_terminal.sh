#!/bin/bash
# Live: find zarooratwala link from Kulvinder and forward to Pallavi
set -u
cd /Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent || exit 1
export PATH="/Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent/.venv/bin:$PATH"
export PYTHONPATH="/Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent"
RUN_DIR="plugin/experiments/runs"
mkdir -p "$RUN_DIR"
STAMP=$(date +%Y%m%d_%H%M%S)
CONSOLE="$RUN_DIR/terminal_forward_zarooratwala_${STAMP}_console.txt"
STATUS="$RUN_DIR/terminal_forward_zarooratwala_${STAMP}_status.txt"
PROMPT='find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi'
LOG_JSONL="$RUN_DIR/forward_zarooratwala_live_${STAMP}.jsonl"
export LOG_JSONL

{
  echo "=== host=$(ps -o comm= -p $PPID) pid=$$ TIMESTAMP=$STAMP ==="
  echo "=== which python: $(which python) ==="
  echo "=== prompt: $PROMPT ==="

  python - <<'PY'
try:
    from ApplicationServices import AXIsProcessTrusted
except Exception as exc:
    print(f"AX check unavailable: {exc}")
    raise SystemExit(42)

if not AXIsProcessTrusted():
    print("LIVE BLOCKED: this process is not Accessibility-trusted.")
    raise SystemExit(42)

print("AXIsProcessTrusted= True — continuing")
PY
  WAIT_EC=$?
  if [ "$WAIT_EC" -eq 42 ]; then
    echo "EXIT_CODE=42"
    echo 42 > "$STATUS"
    exit 42
  fi

  open -a WhatsApp
  sleep 1.5

  echo "=== starting forward-message live ==="
  python - <<'PY'
import os
from pathlib import Path
from plugin.experiments.run_forward_message import run_forward_message

prompt = "find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi"
ok, log = run_forward_message(
    log_path=Path(os.environ["LOG_JSONL"]),
    prompt=prompt,
    source_contact="Kulvinder",
    target_contact="Pallavi",
    link_query="zarooratwala",
)
print()
print(f"=== DONE ok={ok} live=True ===")
print(f"JSONL: {log.path}")
print(f"Summary: {log.path.with_suffix('.md')}")
raise SystemExit(0 if ok else 1)
PY
  EC=$?
  echo "EXIT_CODE=$EC"
  echo "$EC" > "$STATUS"
} 2>&1 | tee "$CONSOLE"

sleep 1
exit "$(cat "$STATUS" 2>/dev/null || echo 1)"
