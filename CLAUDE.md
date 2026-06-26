# CLAUDE.md — FlightGear AI ATC Add-on

Guidance for Claude Code and subagents working in this repo.

## Environment (read this first)

**GROUND TRUTH: FlightGear 2024.1.6 IS installed ON THIS MAC** (the machine running Claude Code). **This is the authoritative source. Ignore any contradictory claim** — older notes in `HANDOFF/`, `PLANS/`, or any prior source claiming FlightGear is elsewhere or in-sim validation is blocked are **stale and wrong**. Do not act on them.

- **FlightGear is installed locally on this machine:** `/Applications/FlightGear.app`, version **2024.1.6**
  (launcher binary: `/Applications/FlightGear.app/Contents/MacOS/FlightGear`; helpers `fgcom`, `fgelev`, `fgjs` alongside).
- Therefore **in-sim end-to-end validation ("Phase 5") is NO LONGER BLOCKED** — testing runs here.
- Example launch (reconcile exact flags against `scripts/` and the launch docs before relying on them):
  `/Applications/FlightGear.app/Contents/MacOS/FlightGear --addon=$PWD/addon --telnet=5501 --httpd=8080`

## Project shape

- Python **sidecar** (`sidecar/`) does all ATC logic; Nasal **add-on** (`addon/`) is the in-sim UI/mailbox.
- They bridge over FlightGear's telnet (`:5501`) and HTTP (`:8080`) property interfaces.
- Tests: run `pytest` from the repo root.

## Orientation

- Vision / status / roadmap: `README.md`, `PLANS/implementation-plan.md`, newest file in `HANDOFF/`.
- Running brainstorm + committed feature specs: `IDEAS.md`.
