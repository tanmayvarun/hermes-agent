#!/bin/bash
# Live Call "plugin support" under Terminal.app — waits until Accessibility is granted.
set -u
cd /Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent || exit 1
export PATH="/Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent/.venv/bin:$PATH"
export PYTHONPATH="/Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent"
RUN_DIR="plugin/experiments/runs"
mkdir -p "$RUN_DIR"
STAMP=$(date +%Y%m%d_%H%M%S)
CONSOLE="$RUN_DIR/terminal_plugin_support_${STAMP}_console.txt"
STATUS="$RUN_DIR/terminal_plugin_support_${STAMP}_status.txt"

{
  echo "=== host=$(ps -o comm= -p $PPID) pid=$$ TIMESTAMP=$STAMP ==="
  echo "=== which python: $(which python) ==="
  echo "=== contact: plugin support ==="

  python - <<'PY'
import time
from ApplicationServices import AXIsProcessTrusted, AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
from Cocoa import NSDictionary

print("AXIsProcessTrusted(initial)=", bool(AXIsProcessTrusted()))
if not AXIsProcessTrusted():
    opts = NSDictionary.dictionaryWithObject_forKey_(True, kAXTrustedCheckOptionPrompt)
    print("prompted, trusted_now=", bool(AXIsProcessTrustedWithOptions(opts)))
    print()
    print(">>> Enable Terminal (or iTerm) in System Settings → Privacy & Security → Accessibility")
    print(">>> Waiting up to 120s for AXIsProcessTrusted() == True …")
    deadline = time.time() + 120
    while time.time() < deadline:
        if AXIsProcessTrusted():
            print("AXIsProcessTrusted= True — continuing")
            break
        time.sleep(2)
    else:
        print("AXIsProcessTrusted= False — timed out")
        raise SystemExit(42)
else:
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

  echo "=== starting call-pallavi --live --contact 'plugin support' ==="
  python -m plugin call-pallavi --live --hangup --contact "plugin support"
  EC=$?
  echo "EXIT_CODE=$EC"
  echo "$EC" > "$STATUS"
} 2>&1 | tee "$CONSOLE"

sleep 1
exit "$(cat "$STATUS" 2>/dev/null || echo 1)"
