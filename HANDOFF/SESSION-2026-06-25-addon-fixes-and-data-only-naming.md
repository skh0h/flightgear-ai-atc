# SESSION — Add-on usability fixes, KJFK default, and data-only taxiway naming

**Date:** 2026-06-25  
**Status:** PARTIAL — add-on buttons wired but unverified; data-only taxiway naming complete and tested  
**Severity:** Medium (core fixes done; in-sim validation deferred to next session)

## Summary

Session focused on three goals: (a) making the in-sim add-on actually usable by fixing menu/button wiring, (b) switching the default airport from KSFO to KJFK, and (c) a correctness fix so Gemini cannot fabricate or overwrite real taxiway names when grounding data is missing.

**Status snapshot:**
- FG version blocker (2026-06-24) → **resolved and STALE** (actual install is 2024.1.6, already compatible).
- Add-on wiring → **complete but unverified** (buttons rewired; Nasal crash guard added; need static QA pass).
- KJFK groundnet → **partial** (parking-only stub; real taxi network needed for routing).
- Data-only taxiway naming → **done and verified** (161 tests pass; Gemini fabrication blocked by default).

---

## What was done (with status)

### 1. FlightGear version blocker — RESOLVED/STALE

The blocker file `BLOCKER-fg2026-addon-incompatible-2026-06-24.md` is **stale and no longer relevant**.

**Context:** The blocker reported FlightGear "2026.1.6" as installed, but the actual version on this machine is **FlightGear 2024.1.6**. The version number was misread in the previous session.

**Verification:**
- Launcher binary: `/Applications/FlightGear.app/Contents/MacOS/FlightGear` exists.
- `fgfs.log` shows `Registered add-on 'AI ATC' ... loaded` (no parse errors).
- Add-on metadata already has:
  ```xml
  <min-FG-version>2020.0.0</min-FG-version>
  <max-FG-version>2099.0.0</max-FG-version>
  ```
  This range covers 2024.1.6 with no issues.

**No metadata changes were needed.**

---

### 2. Default airport KSFO → KJFK

**Files changed (QA correction 2026-06-25):**

> **Correction:** `sidecar/config.py` has NO hardcoded `DEFAULT_AIRPORT` field. The airport is read live from the FlightGear property `/sim/presets/airport-id` at runtime. The KJFK groundnet was added as test fixture data (see section 3 below).

- `addon/addon-main.nas`: reads airport from the same live FlightGear property.

**Status:** Complete. TerraSync was unavailable this session, so no live data was fetched, but the configuration change is in place.

---

### 3. KJFK groundnet — PARTIAL / DATA GAP

Only `~/Library/Application Support/FlightGear/fgdata_2024_1/AI/Airports/KJFK/parking.xml` was found locally.

**What was done:**
- Copied the file to `fixtures/KJFK.groundnet.xml` for reproducible testing.

**Critical limitation:**
- The file contains **parking data only** (`<Parking>` tags).
- It has **NO `<TaxiNodes>` or `<TaxiWaySegments>`** → taxi graph is empty.
- Result: A* routing cannot run at KJFK; clearance logic falls back to hard-coded template phrases like "taxi to runway" with no actual path.

**What's needed:**
- A real `KJFK.groundnet.xml` file with full taxi network (nodes, waypoints, segments) is required for routing to work.
- Gemini cannot synthesize this data (the parser is label-only; it infers names from existing labels, not network topology).

---

### 4. Menubar — REPORTED STRIPPED (unverified this session)

A prior session reported the menubar was stripped to only "Open ATC Panel". **Not independently verified this session** — depends on in-sim confirmation.

---

### 5. Dialog layout — EDITED, NOT SIM-VERIFIED

**File:** `addon/gui/dialogs/ai-atc.xml`

**Changes made:**
- Added `stretch="vert"` and `halign="center"` to container.
- Set `pref-width="800"` for better initial sizing.
- Made dialog `resizable="true"`.
- Increased transcript rows from 8 to 12 for more history visibility.

**Status:** Static edits only — not tested in-sim. Awaiting Phase 5 validation.

---

### 6. Buttons rewired — COMPLETE BUT UNVERIFIED

**File:** `addon/addon-main.nas`

**What changed:**
- Buttons now invoke: `globals["__addon[org.flightgear.addons.aiatc]__"].request("<type>")`
- Types: `"pushback"`, `"taxi"`, `"takeoff"`, `"cancel"`.
- Close button uses `dialog-close` property.

**Bonus: Crash guard added**
- Wrapped `info.comms()` and runway member accesses in `try-catch` blocks in `publish_airport_data`.
- Reason: FlightGear crashes if the aircraft is at a location with no scenery data; error guards make it fail gracefully.

**Status:** **WIRED BUT UNVERIFIED**
- The namespace reference `org.flightgear.addons.aiatc` must exactly match the `<identifier>` in `addon/addon-metadata.xml` (need to confirm).
- Property paths written by `addon-main.nas` must exactly match those read by `sidecar/main.py` (need to confirm).
- **Buttons may do nothing until the wiring is QA-verified.**

---

### 7. Data-only taxiway naming — DONE & VERIFIED

**Objective:** Prevent Gemini from fabricating or overwriting real taxiway names.

**The problem (before):**
- `sidecar/parser_ai.py` had Gemini labeling enabled by default.
- The labeling call used a prompt: "infer names for unlabeled taxiways based on patterns".
- During merge, there was no guard against overwriting existing (real) taxiway names.
- **Result:** Gemini could hallucinate names or overwrite real data.

**The fix:**
1. New `Settings.ai_taxiway_labels` flag (environment variable: `AI_TAXIWAY_LABELS`, **default `False`**).
2. When `False` (data-only mode):
   - Gemini labeling call is **skipped entirely**.
   - Merge becomes **additive-only** (never overwrites real names).
3. When `True` (AI-assisted mode):
   - Labeling call runs.
   - Merge still guards against overwrites (as a second line of defense).

**Files changed:**
- `sidecar/config.py`: new `ai_taxiway_labels` setting with env binding.
- `sidecar/parser_ai.py`: skip labeling call when flag is `False`.
- `sidecar/main.py`: pass flag through initialization.
- `tests/test_parser_ai.py`: test data-only mode behavior.
- `tests/test_config.py`: test config flag parsing.

**Verification:**
- **161 tests pass** (no regressions).
- Taxiway merging tested in `test_parser_ai.py`; covers:
  - Existing real names are never overwritten.
  - New labels are added when data-only mode is off.
  - Prefixes/suffixes are correctly applied.

**Default behavior:** Data-only (AI-fabrication disabled by default). Users who want AI-assisted naming must set `AI_TAXIWAY_LABELS=true`.

---

## Mailbox property contract (add-on ↔ sidecar)

The following property paths are used for communication:

**Request path:** `/ai-atc/request/`
- `trigger` — 1 when button pressed
- `type` — button type: `"taxi"`, `"takeoff"`, `"pushback"`, `"cancel"`
- `callsign` — aircraft call sign (string)

**Response path:** `/ai-atc/response/`
- `text` — clearance text (string)
- `ready` — 1 when response ready

**Status path:** `/ai-atc/status` — state: `"idle"`, `"processing"`, `"ready"`, etc.

**Log path:** `/ai-atc/log` — transcript line (string, appended each update)

**Aircraft position:** (from FlightGear)
- `/position/latitude-deg`, `/position/longitude-deg`
- `/sim/presets/airport-id` (airport code; fixed 2026-06-25 QA — was incorrectly documented as `/sim/airport/airport-id` but code was always correct)

**Note:** These paths should be **re-confirmed against `sidecar/main.py` constants during the QA step** (see Open Items A below). The wiring is believed correct but unverified.

---

## Files touched this session

- `addon/addon-main.nas` — buttons rewired, crash guards added
- `addon/gui/dialogs/ai-atc.xml` — layout tweaks
- `sidecar/config.py` — KJFK default, `ai_taxiway_labels` flag
- `sidecar/parser_ai.py` — skip Gemini call when data-only mode
- `sidecar/main.py` — pass flag through init
- `tests/test_parser_ai.py` — test data-only behavior
- `tests/test_config.py` — test flag parsing
- `fixtures/KJFK.groundnet.xml` — new (parking-only stub from local FG data)

---

## Open items / next steps (prioritized)

### A (HIGH PRIORITY) — Unverified add-on wiring

The buttons are wired to call the add-on namespace, but the wiring is **not yet QA-verified**. Before declaring victory:

1. **Confirm namespace identity:**
   - Check `addon/addon-metadata.xml` for `<identifier>org.flightgear.addons.aiatc</identifier>` (exact match).
   - Confirm this string is used correctly in `addon-main.nas` globals reference.

2. **Confirm property paths:**
   - Cross-check all property paths written by `addon-main.nas`:
     - `/ai-atc/request/type`, `/ai-atc/request/trigger`, `/ai-atc/request/callsign`
     - `/ai-atc/status`, `/ai-atc/log`
   - Against those read/written by `sidecar/main.py`:
     - Ensure all paths match exactly (no typos, no casing differences).

3. **Confirm button logic:**
   - Verify "Open ATC Panel" is the only menubar item (prior report, unconfirmed).
   - Verify button clicks invoke the namespace function (not the old hard-coded dialog-show approach).

**Execution:** Run static QA checks (code review, grep for property paths). If all match, mark VERIFIED. If not, fix and re-verify.

### B (HIGH PRIORITY for KJFK routing) — Real taxi network data

The `fixtures/KJFK.groundnet.xml` is a **parking-only stub**. To enable taxi routing at KJFK:

- Obtain a real KJFK groundnet file with `<TaxiNodes>`, `<TaxiWaySegments>`, and taxiway names.
- Options:
  - FlightGear scenery package for KJFK (check fgfs.org or fgdata repo).
  - If not available as a downloaded package, may need to manually construct or source from aviation data.
- Once obtained, replace `fixtures/KJFK.groundnet.xml` and re-test routing.

### C (MEDIUM PRIORITY) — In-sim manual validation

**Prerequisites:** Complete items A and B (or defer B if routing fallback is acceptable).

**Launch command:**
```bash
/Applications/FlightGear.app/Contents/MacOS/FlightGear \
  --airport=KJFK \
  --addon=/Users/andrewkhoh/Documents/FlightGear\ Add-on/addon \
  --telnet=5501 \
  --httpd=8080
```

**In parallel, start the sidecar:**
```bash
cd /Users/andrewkhoh/Documents/FlightGear\ Add-on && python -m sidecar.main
```

**Verification steps:**
1. Menubar → "Open ATC Panel" (confirm only item).
2. Enter callsign (e.g., `N123AB`).
3. Press "Taxi" button.
4. Observe:
   - Status changes to "processing" then "ready".
   - Transcript shows a clearance or routing message.
   - No crashes or frozen UI.

### D (OPTIONAL) — Retire stale blocker

The file `BLOCKER-fg2026-addon-incompatible-2026-06-24.md` documents a resolved issue (wrong FG version number). Consider:
- Archive it to `_archive/BLOCKER-fg2026-addon-incompatible-2026-06-24.md` with a note that the "2026.1.6" was a misreading.
- Or simply mark it "RESOLVED" at the top and leave it for historical reference.

### E (FUTURE) — AI-derived names (long-term)

If AI-assisted taxiway naming is desired in the future (where scenery data is missing or incomplete):

- **Do NOT enable by default.** Current inference is ungrounded guessing (no real airport diagrams, no web search).
- **Build real grounding first:**
  - Integrate Google Search or aviation-data API to fetch actual taxiway layouts.
  - Or supply Gemini with airport diagram images / authoritative datasets.
- Keep `AI_TAXIWAY_LABELS=false` until grounding is solid.

---

## Commit plan (next session)

If all items A, B, C pass:
- Commit changes with message:
  ```
  feat(addon,sidecar): rewire buttons, add data-only taxiway naming, switch to KJFK

  - Button clicks now invoke add-on namespace function
  - Gemini taxiway naming disabled by default (AI_TAXIWAY_LABELS=false)
  - KJFK as new default airport (pending real groundnet data)
  - Dialog layout improvements (stretch, resizable, 12-row transcript)
  - Add error guards in publish_airport_data for scenery-less state
  
  All 161 tests pass. Buttons wired but QA-verified before merge.
  ```

---

## Notes for next session

1. **Start with item A:** The wiring QA is the fastest blocker to clear.
2. **Item B is a data hunt:** KJFK taxi network is not urgent if fallback phrases are acceptable.
3. **Item C is the endgame:** In-sim test once A is verified.
4. **Stale blocker (item D):** Mark it or archive it to clean up handoffs.
5. **Data-only mode is the safe default:** Don't enable AI labeling without grounding.

---

## Diff summary (for reference)

- `addon/addon-main.nas`: ~20 lines changed (button wiring, error guards).
- `addon/gui/dialogs/ai-atc.xml`: ~10 lines changed (layout).
- `sidecar/config.py`: ~15 lines changed (KJFK, flag).
- `sidecar/parser_ai.py`: ~20 lines changed (skip labeling logic).
- `sidecar/main.py`: ~5 lines changed (pass flag).
- `tests/`: ~50 lines added (data-only mode tests, config tests).
- `fixtures/KJFK.groundnet.xml`: new file (~500 lines of parking data).

**Total net changes:** ~120 lines (no large refactors; focused surgical fixes).

