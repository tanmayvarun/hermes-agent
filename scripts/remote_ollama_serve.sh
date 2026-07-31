#!/usr/bin/env bash
# Start Ollama on a remote Ubuntu host over SSH, bind it for external clients,
# and optionally pre-pull one or more models before serving.
#
# Usage:
#   SSH_HOST=1.2.3.4 SSH_USER=root SSH_PASS=... ./scripts/remote_ollama_serve.sh
#
# Optional env:
#   SSH_PORT=22
#   OLLAMA_PORT=11434
#   OLLAMA_HOST_BIND=0.0.0.0
#   OLLAMA_ORIGINS=*
#   OLLAMA_MODELS="qwen3:235b"
#   SSH_KEY=~/.ssh/id_rsa         # if set, use key auth instead of password
#   SSH_CONNECT_TIMEOUT=10
#
# The script is intentionally non-destructive. It expects Ollama to already be
# installed on the remote host; if the binary or model pull fails, it exits with
# a non-zero status instead of trying to guess an install flow.

set -euo pipefail

SSH_HOST="${SSH_HOST:-}"
SSH_USER="${SSH_USER:-root}"
SSH_PORT="${SSH_PORT:-22}"
SSH_PASS="${SSH_PASS:-}"
SSH_KEY="${SSH_KEY:-}"
SSH_CONNECT_TIMEOUT="${SSH_CONNECT_TIMEOUT:-10}"

OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OLLAMA_HOST_BIND="${OLLAMA_HOST_BIND:-0.0.0.0}"
OLLAMA_ORIGINS="${OLLAMA_ORIGINS:-*}"
OLLAMA_MODELS="${OLLAMA_MODELS:-}"

if [[ -z "$SSH_HOST" ]]; then
  echo "SSH_HOST is required" >&2
  exit 2
fi

SSH_OPTS=(
  -p "$SSH_PORT"
  -o "ConnectTimeout=$SSH_CONNECT_TIMEOUT"
  -o "ServerAliveInterval=15"
  -o "ServerAliveCountMax=3"
  -o "StrictHostKeyChecking=accept-new"
)

if [[ -n "$SSH_KEY" ]]; then
  SSH_OPTS+=(-i "$SSH_KEY")
else
  if [[ -z "$SSH_PASS" ]]; then
    echo "Set SSH_PASS or SSH_KEY" >&2
    exit 2
  fi
  if ! command -v sshpass >/dev/null 2>&1; then
    echo "sshpass is required for password auth, or set SSH_KEY" >&2
    exit 2
  fi
fi

REMOTE_SETUP=$(cat <<EOF
set -euo pipefail
if [ "$(id -u)" -eq 0 ]; then
  _APT_GET="apt-get"
  _UFW="ufw"
else
  _APT_GET="sudo -n apt-get"
  _UFW="sudo -n ufw"
fi
if ! command -v screen >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1 || command -v sudo >/dev/null 2>&1; then
    ${_APT_GET} update
    ${_APT_GET} install -y screen
  else
    echo "screen is not installed and apt-get is unavailable" >&2
    exit 3
  fi
fi
if ! command -v ollama >/dev/null 2>&1; then
  echo "ollama binary not found on remote host" >&2
  exit 3
fi
if command -v ufw >/dev/null 2>&1; then
  ${_UFW} allow ${OLLAMA_PORT}/tcp || true
fi
if screen -list | grep -q "[[:space:]]ollama[[:space:]]"; then
  screen -S ollama -X quit || true
fi
screen -dmS ollama bash -lc '
  export OLLAMA_HOST="${OLLAMA_HOST_BIND}:${OLLAMA_PORT}"
  export OLLAMA_ORIGINS="${OLLAMA_ORIGINS}"
  exec ollama serve
'
sleep 2
if ! screen -list | grep -q "[[:space:]]ollama[[:space:]]"; then
  echo "failed to start ollama screen session" >&2
  exit 4
fi
if [ -n "${OLLAMA_MODELS}" ]; then
  IFS=, read -r -a MODELS <<< "${OLLAMA_MODELS}"
  for model in "${MODELS[@]}"; do
    model="\${model//[$'\\t\\r\\n ']/}"
    [ -z "\$model" ] && continue
    ollama pull "\$model"
  done
fi
echo "OLLAMA_READY"
ollama list
EOF
)

if [[ -n "$SSH_KEY" ]]; then
  ssh "${SSH_OPTS[@]}" "${SSH_USER}@${SSH_HOST}" "bash -lc $(printf '%q' "$REMOTE_SETUP")"
else
  sshpass -p "$SSH_PASS" ssh "${SSH_OPTS[@]}" "${SSH_USER}@${SSH_HOST}" "bash -lc $(printf '%q' "$REMOTE_SETUP")"
fi
