#!/bin/bash
# Launch the Zarooratwala forward run through Launch Services, not Apple Events.
# We create a small wrapper .command so the child run gets a stable stamp and the
# resulting status/console files are deterministic.
set -euo pipefail

cd /Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent || exit 1

script_path="/Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent/plugin/experiments/runs/run_forward_zarooratwala.command"
stamp="$(date +%Y%m%d_%H%M%S)"
wrapper_path="/tmp/hermes_forward_zarooratwala_launch_${stamp}.command"
marker="/tmp/hermes_forward_zarooratwala_launch_${stamp}.txt"

{
  echo "launcher=$(basename "$0")"
  echo "script_path=$script_path"
  echo "wrapper_path=$wrapper_path"
  echo "cwd=$(pwd)"
  echo "ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$marker"

# Terminal.app starts a clean shell — pass preflight/recording hints explicitly.
PREFLIGHT="${HERMES_EVAL_PREFLIGHT_DONE:-0}"
cat > "$wrapper_path" <<EOF
#!/bin/bash
set -euo pipefail
export HERMES_RUN_STAMP="$stamp"
export HERMES_EVAL_PREFLIGHT_DONE="$PREFLIGHT"
exec "$script_path"
EOF
chmod +x "$wrapper_path"

echo "Launching via Launch Services: $wrapper_path"
echo "Launch marker: $marker"
open -a Terminal "$wrapper_path"
