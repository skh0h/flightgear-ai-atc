# Fix "everything feels broken" + redesign the ATC panel (2026-06-25)

## Context

The in-sim **ATC Panel** goes **Idle → Processing → nothing**, the "backend does nothing," and "Gemini isn't working." After exploring the code and checking the live machine, **nothing in the core logic is actually broken** — the two halves were never being run together:

- The architecture is **Nasal add-on (thin in-sim UI/mailbox)** ↔ **Python sidecar (ALL ATC logic + Gemini)**, bridged over FlightGear's telnet property server on `:5501`.
- Live check found: **FlightGear was running, but telnet `:5501` was CLOSED, and the Python sidecar was NOT running.** The user confirmed they launch *"Just FlightGear"* (app icon), which omits `--telnet=5501` and never starts the sidecar.
- Therefore clicking a button runs `request()` in Nasal, which sets `/ai-atc/status = "processing"` **locally** and pulses `/ai-atc/request/trigger`. With no sidecar connected over telnet, nothing consumes the trigger or writes a response → "Processing" forever. "Gemini not working" is downstream of the same cause: the Gemini call lives in the sidecar, which was never up. A `.env` (69 bytes) exists, so the key is almost certainly already configured.

On top of the launch problem, the system **hides its own failures**, which is why it "feels broken" even when partially wired:
- The UI has **no watchdog and no "is the backend alive?" signal** — it hangs silently on Processing (`addon/addon-main.nas`).
- The sidecar **swallows exceptions**: on any error in `handle_trigger` it sets `status="error"` but **never writes a response**, so the UI never recovers (`sidecar/main.py:345-349`).
- The telnet bridge reads exactly one line per `get` with no guard against FlightGear's connection banner / `> ` prompt — a latent off-by-one that can make every read return garbage (`sidecar/fg_bridge.py:118-136`).
- Keybinding/menu set mailbox props directly, bypassing `request()` (no callsign auto-fill, inconsistent state) (`addon/addon-config.xml:29-34`).

**Intended outcome:** (1) make it *actually run* with one action and *show its state* so it feels smooth and never hangs; (2) redesign the panel into our own clean, information-rich layout *inspired by* (not copied from) the Red Griffin reference; (3) lay the staged path toward full gate-to-gate coverage (ground/departure now, arrival/approach next).

> **Copyright note:** Keep our own "AI ATC" identity. Do **not** reuse the "Red Griffin" name, its exact wording, layout, or any assets. The screenshot is functional/UX inspiration only.

---

## Stage 0 — Make it run & make it observable (THE priority; fixes "feels broken")

Goal: one action launches everything with telnet on, and the panel always tells the truth about backend state and never hangs.

**One-action launch (primary fix)**
- Treat **`scripts/run-mac.command`** as the blessed way to start (double-click in Finder, *not* the app icon). Harden it:
  - Auto-detect `FGFS` (default to `/Applications/FlightGear.app/Contents/MacOS/fgfs` if `fgfs` not on PATH).
  - Replace the fixed `sleep 10` with a **poll on telnet `:5501`** until open (or timeout) before starting the sidecar.
  - Tee sidecar output to `sidecar.log` so failures are inspectable.
- Update `README.md` quick-start to say "double-click `run-mac.command`" and stop using the app icon. (`scripts/run-windows.bat` gets the equivalent treatment.)

**Backend heartbeat + connection awareness (so the panel shows truth)**
- Sidecar: in `poll_loop` (`sidecar/main.py:372-394`) periodically write `/ai-atc/sidecar/heartbeat` (incrementing) and `/ai-atc/sidecar/mode` (`"ai"` | `"offline"`).
- Nasal (`addon/addon-main.nas`): a `maketimer` watches heartbeat staleness and drives a `/ai-atc/backend` status string: **"Connected (AI)" / "Connected (offline templates)" / "Not running — launch run-mac.command"**. Shown prominently in the panel.

**Never hang again (watchdog + error surfacing)**
- Nasal request watchdog: when `request()` fires, start an ~8s `maketimer`; if no `/ai-atc/response/ready` by then, revert `status` to `idle` and log `[atc] No response from backend — is the sidecar running?`.
- Nasal listener on `/ai-atc/status == "error"`: surface it in the log and reset to `idle`.
- Route the **keybinding and menu** through `request()` instead of setting props directly, so callsign auto-fill and state handling are consistent (`addon/addon-config.xml:29-34`, `addon/addon-menubar-items.xml`). Reuse the existing `request()` in `addon/addon-main.nas:42-54`.

**Sidecar robustness (always reply, log loudly, survive telnet quirks)**
- In `handle_trigger` exception path (`sidecar/main.py:345-349`): still write a user-facing `RESP_TEXT` (e.g. "Stand by — unable to process that request."), set `RESP_READY=1`, and reset `STATUS="idle"`, so the UI always recovers; keep the detailed `_log.exception`.
- Harden `FGTelnetBridge` (`sidecar/fg_bridge.py`): consume FlightGear's initial banner on connect, drain stray `> ` prompt lines before parsing a `get` reply, and **raise `BridgeError` on peer-close mid-read** instead of returning partial bytes (`_readline`, lines 118-127). Verify against the live sim.
- Add **`python -m sidecar.main --selftest`**: checks Gemini connectivity using the `.env` key (prints AI vs offline) and optionally round-trips one telnet property — a one-command health check (extends the existing `argparse` in `sidecar/main.py:409-421`).
- Re-publish airport data on airport change: Nasal listener on `/sim/presets/airport-id` re-runs `publish_airport_data()` and clears stale `runway[n]` nodes (`addon/addon-main.nas:58-109,131-132`).

**Critical files:** `scripts/run-mac.command`, `addon/addon-main.nas`, `addon/addon-config.xml`, `addon/addon-menubar-items.xml`, `sidecar/main.py`, `sidecar/fg_bridge.py`, `README.md`.

---

## Stage 1 — Redesign the panel (original, inspired by the reference)

Rebuild `addon/gui/dialogs/ai-atc.xml` as a richer **standard FlightGear dialog** (PUI — reliable; a translucent Canvas/HUD overlay is noted as optional later polish):

- **Header:** our "AI ATC" title + current airport ICAO and name (from `airportinfo()`).
- **Info block (live):** nearest/controlling station + COM frequency; aircraft state (on ground / distance to field); current phase; and the **Backend status line** from Stage 0 (Connected AI / Connected offline / Not running).
- **Frequency list:** ground / tower / atis / approach / departure — data already published by `publish_airport_data()` into `/ai-atc/airport/freq/*`.
- **Buttons grouped by phase:** Ground/Departure (Pushback, Taxi, Takeoff) now; Arrival/Approach group added in Stage 2.
- **Transcript log**, **About**, **Close**.

**Critical files:** `addon/gui/dialogs/ai-atc.xml` (+ small supporting props in `addon/addon-main.nas`).

---

## Stage 2 — Arrival/approach functions (toward all-phases coverage)

Extend the sidecar with new request types so the panel covers arrivals, mirroring the reference's capabilities under our own design:

- New `req_type` values handled in `handle_trigger` and `_build_clearance`: `approach`, `ils`, `airfield_in_sight`, `radio_check`.
- Each gets an **offline template** in `sidecar/phraseology.py` plus the existing **Gemini online path** (reuse `phrase_online` / `phrase_offline` fallback at `sidecar/phraseology.py:96-116`).
- Compute distance/bearing to the field from `/position/*` + airport coords (position reads already exist in `handle_trigger`, `sidecar/main.py:332-333`).
- Wire the new buttons into the redesigned panel's Arrival/Approach group.

**Critical files:** `sidecar/main.py`, `sidecar/phraseology.py`, `addon/gui/dialogs/ai-atc.xml`, plus tests in `tests/`.

---

## Stage 3 — Airspace/CTR + traffic awareness (future)

Per the committed spec in `IDEAS.md` (airport configuration + traffic sequencing): position-relative-to-airspace ("inside / flying to"), CTR entry requests, and read-only AI-traffic sequencing via `/ai/models/`. Larger; deferred until Stages 0–2 are solid in-sim.

---

## Verification (end-to-end, on this machine)

FlightGear 2024.1.6 is installed locally, so this is testable here.

1. **Backend health:** `cd "<repo>" && .venv/bin/python -m sidecar.main --selftest` → prints "Gemini: AI" (key works) or "offline", and telnet round-trip OK.
2. **Unit tests:** `pytest` from repo root (current suite ~105 tests must stay green; add tests for the new exception-path reply, heartbeat, watchdog, bridge banner/prompt handling, and new request types).
3. **Full in-sim run:** double-click `scripts/run-mac.command` (NOT the app icon). Open the **AI ATC** panel:
   - Panel shows **Backend: Connected (AI)** within a couple seconds.
   - Click **Taxi** → status goes Processing → a real clearance appears in the log and is spoken via TTS, status returns to Idle.
   - Kill the sidecar mid-session → within ~8s the panel shows **Not running** and any in-flight request unhangs with a clear message (proves the watchdog/heartbeat).
4. **Airport change:** switch airports in-sim → frequency/runway display updates (no stale data).

## Execution note

Implementation will be delegated to specialized agents (Engineer for Nasal/Python/XML changes, QA for the verification gate above). Stage 0 is the priority and independently shippable; Stages 1–2 follow; Stage 3 is future.
