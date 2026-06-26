# SESSION — Root cause of "everything feels broken" + fix/redesign plan

**Date:** 2026-06-25
**Status:** DIAGNOSIS COMPLETE · PLAN WRITTEN · no code changed yet (planning session)
**Severity:** High-value finding (the headline bug is operational, not a logic bug)

## Summary

User reported the in-sim **ATC Panel** "feels broken": it goes **Idle → Processing → nothing**, "the backend does not seem to do anything," and "Gemini seems to be not working." They also want the panel redesigned to resemble the Red Griffin ATC reference screenshot, and to head toward full gate-to-gate coverage.

**Root cause (confirmed on the live machine): the two halves are never run together.**
The system is Nasal add-on (thin UI/mailbox) ↔ Python sidecar (ALL ATC logic + Gemini), bridged over FlightGear telnet `:5501`. The user launches **"Just FlightGear"** (app icon), which:
- does **not** pass `--telnet=5501` (telnet server off), and
- never starts the Python sidecar.

So clicking a button runs `request()` in `addon/addon-main.nas`, which sets `/ai-atc/status="processing"` **locally** and pulses `/ai-atc/request/trigger`. With nothing connected over telnet, nothing consumes the trigger or writes a response → "Processing" forever. "Gemini not working" is the same cause downstream (the Gemini call lives in the sidecar, which was never up). A `.env` (69 bytes) exists, so the key is almost certainly already set.

**Live evidence captured this session:** FlightGear was running (PID 88098) but `nc` to `localhost:5501` returned **closed**, and `pgrep -fl sidecar.main` found **nothing running**.

## Secondary issues found (why it "feels broken" even when partially wired)

- **UI hides failures:** no watchdog and no "backend alive?" signal in `addon/addon-main.nas` → silent hang on Processing.
- **Sidecar swallows exceptions:** `handle_trigger` exception path (`sidecar/main.py:345-349`) sets `status="error"` but **never writes a response** (no `RESP_TEXT`, no `RESP_READY`), so the UI never recovers; and `status="error"` has no Nasal listener to reset it.
- **Telnet bridge fragility:** `FGTelnetBridge._readline` (`sidecar/fg_bridge.py:118-127`) reads one line per `get` with no guard against FG's connection banner / `> ` prompt (latent off-by-one), and returns partial bytes on peer-close instead of raising `BridgeError`.
- **Keybinding/menu bypass `request()`** (`addon/addon-config.xml:29-34`): set props directly, so callsign auto-fill and consistent state are skipped.
- **Airport data published only once at load** (`addon/addon-main.nas:131-132`): stale runways/freqs after an airport change.

## User decisions (this session)

- **Launch:** "Just FlightGear" — confirmed the root cause above.
- **Panel scope:** use Red Griffin as a **reference for building all phases** (toward full gate-to-gate; staged).
- **Look & feel:** **inspired, not copied** — "I don't want to be sued for copyright. Just base it off of that." Keep our own "AI ATC" identity; no Red Griffin name/wording/layout/assets.

## The plan (written this session)

Full plan: **`PLANS/fix-and-redesign-plan-2026-06-25.md`** (the `~/.claude/plans/` mirror was blocked by GateGuard; the canonical copy is in `PLANS/`). Staged:

- **Stage 0 — make it run & observable (PRIORITY, ships alone):** harden `scripts/run-mac.command` (auto-detect `fgfs`, poll `:5501` before starting sidecar, tee `sidecar.log`); README quick-start = "double-click run-mac.command, not the app icon"; sidecar **heartbeat** (`/ai-atc/sidecar/heartbeat` + `/mode`) → panel **connection indicator** ("Connected (AI)" / "offline templates" / "Not running"); Nasal **request watchdog** (~8s) so it never hangs; `status=="error"` listener; route keybinding/menu through `request()`; sidecar **always replies even on error**; harden telnet bridge banner/prompt + peer-close; add **`python -m sidecar.main --selftest`** (Gemini + telnet health check); re-publish airport data on `/sim/presets/airport-id` change.
- **Stage 1 — redesign panel:** rebuild `addon/gui/dialogs/ai-atc.xml` as a clean, info-rich **PUI dialog** (airport header, live frequencies from `/ai-atc/airport/freq/*`, distance/position, backend status, phase-grouped buttons). Canvas/HUD translucent overlay = optional later polish.
- **Stage 2 — arrival/approach functions:** new `req_type`s (`approach`, `ils`, `airfield_in_sight`, `radio_check`) in `sidecar/main.py` + `sidecar/phraseology.py` (offline templates + existing Gemini path), wired to new buttons.
- **Stage 3 — airspace/CTR + traffic (future):** per `IDEAS.md` committed spec (position relative to airspace, CTR entry, read-only AI-traffic sequencing via `/ai/models/`).

## Relationship to prior session (`SESSION-2026-06-25-addon-fixes-and-data-only-naming.md`)

That session already **rewired the menu/buttons (unverified in-sim)**, added a Nasal crash guard, switched the **default airport to KJFK** (groundnet is a **parking-only stub** — real taxi network still needed for routing), and shipped **data-only taxiway naming** (Gemini fabrication blocked by default; `ai_taxiway_labels` defaults OFF). Net: the button wiring exists but has never been validated against a *running* backend — which is exactly the gap this session explains. Stage 0 makes that validation possible for the first time.

## Cost note (read)

This environment has a **`max-plan-cost-hook`** (`~/.claude/skills/learned/max-plan-cost-hook.md`) and cost tracking (`~/.claude/metrics/costs.jsonl`). Today's Opus 4.8 snapshots run **~$4–20 each** (very large cache-read context, 1.3M–2.8M tokens/turn); a prior handoff records a session reaching **~$260**. No literal alert fired, but **stay lean**: implement inline, avoid Workflow/agent fleets, don't re-read large files. (This session used 3 Explore agents for the diagnosis — fine for a one-off, but keep implementation inline.)

The **plan's own Gemini cost is low**: default `gemini-2.5-flash`, `ai_taxiway_labels` OFF, offline templates free, `--selftest` = one tiny call.

## Resume checklist (next session)

1. `cd "/Users/andrewkhoh/Documents/FlightGear Add-on"`; confirm `git rev-parse --show-toplevel` == this folder; `gh auth status` active = `skh0h`. Commit authorship: `skh0h <samuelkhoh84@gmail.com>`, **no** Co-Authored-By trailer. Pushing to `main` needs explicit user OK.
2. Read `PLANS/fix-and-redesign-plan-2026-06-25.md`. Implement **Stage 0 first** (it's independently shippable and fixes the "feels broken" experience).
3. Verify end-to-end: `.venv/bin/python -m sidecar.main --selftest` → `pytest` green → double-click `scripts/run-mac.command` → panel shows **Connected (AI)** → Taxi → real spoken clearance → Idle → kill sidecar mid-session → watchdog shows **Not running** within ~8s and unhangs.
4. Note: GateGuard fact-forcing gate intercepts the first `Bash` of a session and every `Write`/`Edit` (present 4 facts, retry succeeds). Do NOT disable it.
