#!/usr/bin/env bash
# Launch Hermes TUI, with an optional WhatsApp QR link step first.
set -euo pipefail

export PATH="/Users/tanmayvarun/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

clear
cat <<'EOF'
┌─────────────────────────────────────────────────────────┐
│                   Hermes Agent Launcher                 │
└─────────────────────────────────────────────────────────┘

WhatsApp is currently not linked on this Mac.

  1) Link WhatsApp (QR) then start TUI
  2) Start TUI only (skip WhatsApp)
  3) Link WhatsApp only (no TUI)
  q) Quit

EOF

printf "Choose [1/2/3/q]: "
read -r choice

link_whatsapp() {
  echo
  echo "Starting WhatsApp pairing…"
  echo "On your phone: WhatsApp → Settings → Linked Devices → Link a Device"
  echo "Scan the QR code shown next."
  echo
  hermes whatsapp
  echo
  echo "After pairing, start/restart the gateway so WhatsApp stays connected:"
  echo "  hermes gateway install   # once"
  echo "  hermes gateway restart"
  echo
}

start_tui() {
  echo
  echo "Starting Hermes Terminal UI…"
  exec hermes --tui
}

case "${choice:-}" in
  1)
    link_whatsapp
    start_tui
    ;;
  2)
    start_tui
    ;;
  3)
    link_whatsapp
    printf "Press Enter to close…"
    read -r _
    ;;
  q|Q)
    exit 0
    ;;
  *)
    echo "Unknown choice. Starting TUI only."
    start_tui
    ;;
esac
