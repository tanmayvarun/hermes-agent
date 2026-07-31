#!/bin/bash
# Live: find the Google Maps share link for India Coffee House HSR Layout and share with Pallavi
set -u
cd /Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent || exit 1
export PATH="/Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent/.venv/bin:$PATH"
export PYTHONPATH="/Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent"
RUN_DIR="plugin/experiments/runs"
mkdir -p "$RUN_DIR"
STAMP=$(date +%Y%m%d_%H%M%S)
CONSOLE="$RUN_DIR/terminal_forward_google_maps_share_${STAMP}_console.txt"
STATUS="$RUN_DIR/terminal_forward_google_maps_share_${STAMP}_status.txt"
PROMPT='find the google maps share link of india coffee house hsr layout and share with pallavi'

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

  echo "=== starting forward-message live ==="
  python - <<'PY'
from pathlib import Path
from plugin.experiments.run_forward_message import run_forward_message

prompt = "find the google maps share link of india coffee house hsr layout and share with pallavi"
ok, log = run_forward_message(
    log_path=Path("plugin/experiments/runs/forward_google_maps_share_live.jsonl"),
    prompt=prompt,
    source_contact="Kulvinder",
    target_contact="Pallavi",
    link_query="india coffee house hsr layout",
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
