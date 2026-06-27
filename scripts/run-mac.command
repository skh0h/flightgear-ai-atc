#!/usr/bin/env bash
# run-mac.command — Launch FlightGear + AI ATC sidecar (macOS)
#
# Double-click this file in Finder or run it from Terminal.
# Finder double-click requires the script to be chmod +x (done at creation).
#
# Prerequisites:
#   - FlightGear 2024.1.5+ installed (default /Applications/FlightGear.app, or fgfs on PATH)
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
# Auto-detect fgfs: prefer PATH, fall back to the standard macOS app bundle.
if command -v fgfs >/dev/null 2>&1; then
    FGFS="${FGFS:-fgfs}"
else
    FGFS="${FGFS:-/Applications/FlightGear.app/Contents/MacOS/fgfs}"
fi
ADDON_PATH="${REPO}/addon"
FG_TELNET_PORT=5501
FG_HTTP_PORT=8080
TELNET_TIMEOUT=120   # seconds to wait for FlightGear telnet before giving up
LOG_FILE="${REPO}/sidecar.log"
# -----------------------------------------------------------------------------

echo "==> Repo: ${REPO}"
echo "==> Addon: ${ADDON_PATH}"
echo "==> Using fgfs: ${FGFS}"

if [ ! -x "${FGFS}" ] && ! command -v "${FGFS}" >/dev/null 2>&1; then
    echo "ERROR: FlightGear executable not found at '${FGFS}'."
    echo "       Install FlightGear or set FGFS=/path/to/fgfs and re-run."
    exit 1
fi

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

# Poll telnet :5501 until it accepts connections (better than a fixed sleep).
echo "==> Waiting for FlightGear telnet server on port ${FG_TELNET_PORT} (timeout ${TELNET_TIMEOUT}s)..."
ELAPSED=0
while ! nc -z localhost "${FG_TELNET_PORT}" 2>/dev/null; do
    if [ "${ELAPSED}" -ge "${TELNET_TIMEOUT}" ]; then
        echo "ERROR: Timed out waiting for FlightGear telnet after ${TELNET_TIMEOUT}s."
        kill "${FG_PID}" 2>/dev/null || true
        exit 1
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done
echo "    Telnet ready after ${ELAPSED}s."

# Launch the sidecar, tee-ing output to sidecar.log so failures are inspectable.
echo "==> Starting sidecar (log: ${LOG_FILE})..."
"${REPO}/.venv/bin/python" -m sidecar.main 2>&1 | tee "${LOG_FILE}"

# If the sidecar exits, kill FlightGear too.
echo "==> Sidecar exited; stopping FlightGear..."
kill "${FG_PID}" 2>/dev/null || true
