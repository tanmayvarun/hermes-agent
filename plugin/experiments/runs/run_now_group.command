#!/bin/bash
# Launch Services wrapper: open this file so Terminal owns the child process.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec /bin/bash "$SCRIPT_DIR/run_now_group_in_terminal.sh"
