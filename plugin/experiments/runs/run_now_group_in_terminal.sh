#!/bin/bash
# Live Call "now group" from a trusted terminal.
set -u
cd /Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent || exit 1
export PATH="/Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent/.venv/bin:$PATH"
export PYTHONPATH="/Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent"
RUN_DIR="plugin/experiments/runs"
mkdir -p "$RUN_DIR"
STAMP=$(date +%Y%m%d_%H%M%S)
CONSOLE="$RUN_DIR/terminal_now_group_${STAMP}_console.txt"
STATUS="$RUN_DIR/terminal_now_group_${STAMP}_status.txt"

{
  echo "=== host=$(ps -o comm= -p $PPID) pid=$$ TIMESTAMP=$STAMP ==="
  echo "=== which python: $(which python) ==="
  echo "=== contact: now group ==="

  python - <<'PY'
try:
    from ApplicationServices import AXIsProcessTrusted
except Exception as exc:
    print(f"AX check unavailable: {exc}")
    raise SystemExit(42)

if not AXIsProcessTrusted():
    print("LIVE BLOCKED: this process is not Accessibility-trusted.")
    print("Run the .command launcher from Terminal.app or iTerm after granting Accessibility to that host.")
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

  echo "=== starting call-pallavi --live --contact 'now group' ==="
  python -m plugin call-pallavi --live --hangup --contact "now group"
  EC=$?
  echo "EXIT_CODE=$EC"
  echo "$EC" > "$STATUS"
} 2>&1 | tee "$CONSOLE"

sleep 1
exit "$(cat "$STATUS" 2>/dev/null || echo 1)"
