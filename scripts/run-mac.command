#!/usr/bin/env bash
# run-mac.command — Launch FlightGear + AI ATC sidecar (macOS)
#
# Double-click this file in Finder or run it from Terminal.
# Finder double-click requires the script to be chmod +x (done at creation).
#
# Prerequisites:
#   - FlightGear 2024.1.5+ installed (fgfs on PATH or adjust FGFS below)
#   - Python venv created: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
#   - .env containing: GEMINI_API_KEY=<your-key>
#
# Usage:
#   ./scripts/run-mac.command [fg-extra-args...]
#
# Any arguments passed to this script are forwarded to fgfs after the defaults.

set -euo pipefail

# Change to the repo root (works when double-clicked from Finder).
cd "$(dirname "$0")/.."
REPO="$(pwd)"

# --- Configurable paths ------------------------------------------------------
FGFS="${FGFS:-fgfs}"           # Override with: FGFS=/Applications/FlightGear.app/Contents/MacOS/fgfs
ADDON_PATH="${REPO}/addon"
FG_TELNET_PORT=5501
FG_HTTP_PORT=8080
# -----------------------------------------------------------------------------

echo "==> Repo: ${REPO}"
echo "==> Addon: ${ADDON_PATH}"

# Launch FlightGear in the background.
# --telnet=5501  : property/telnet server (--props=5501 is the legacy alias)
# --httpd=8080   : HTTP property server (used by some tooling)
echo "==> Starting FlightGear..."
"${FGFS}" \
    --addon="${ADDON_PATH}" \
    --telnet="${FG_TELNET_PORT}" \
    --httpd="${FG_HTTP_PORT}" \
    "$@" &
FG_PID=$!
echo "    FlightGear PID: ${FG_PID}"

# Give FlightGear a moment to start its telnet server before connecting.
echo "==> Waiting 10 seconds for FlightGear telnet server..."
sleep 10

# Launch the sidecar (foreground — Ctrl-C stops it cleanly via SIGINT).
echo "==> Starting sidecar..."
"${REPO}/.venv/bin/python" -m sidecar.main

# If the sidecar exits, kill FlightGear too.
echo "==> Sidecar exited; stopping FlightGear..."
kill "${FG_PID}" 2>/dev/null || true
