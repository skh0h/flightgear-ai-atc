# FlightGear AI ATC — Consolidated Plan, Vision & Backlog (V1a)

**Date:** 2026-06-24
**Consolidates:** V1 (implementation plan), V2 (expanded vision & roadmap), and V3 (groundnet finding & feature backlog) into one document, with overlapping material reconciled and de-duplicated. Where V2 supersedes V1 (TTS backend, read transport, cross-platform scope), the V2 decision is recorded as authoritative.

---

## Table of Contents

1. [Context & Goals](#1-context--goals)
2. [Confirmed Decisions](#2-confirmed-decisions)
3. [Architecture](#3-architecture)
4. [Implementation Phases](#4-implementation-phases)
5. [Critical Files](#5-critical-files)
6. [Groundnet Taxiway Naming Finding](#6-groundnet-taxiway-naming-finding)
7. [Implementation Status — Parking → Takeoff Runway](#7-implementation-status--parking--takeoff-runway)
8. [Feature Roadmap & Backlog](#8-feature-roadmap--backlog)
9. [Priority Matrix](#9-priority-matrix)
10. [Staging Recommendation](#10-staging-recommendation)
11. [Guardrails & Lessons Learned](#11-guardrails--lessons-learned)
12. [Reuse, References & Prior Art](#12-reuse-references--prior-art)
13. [Verification](#13-verification)
14. [Open Questions](#14-open-questions)

---

## 1. Context & Goals

**Goal:** Build an AI-powered Air Traffic Control add-on for FlightGear 2024.1.5 that gives **specific, real instructions** (e.g., "taxi to runway 28R via A, B, hold short of 28R") instead of the generic instructions produced by the existing **Red Griffin ATC** add-on.

**The problem with what exists:** Red Griffin ATC is a rule-based Nasal add-on with hardcoded, generic phraseology and **no taxi routing** (the author was blocked because Nasal can't reach FlightGear's ground-network data in-process). It has no traffic awareness and stale, non-standard phraseology.

**Intended outcome:** An add-on that uses **Gemini when online** for rich/natural phraseology and for interpreting airport data, and **falls back to deterministic code when offline**. Airport "pictures" (parking + named taxiway graph + runway links + frequencies) are derived once per airport and **cached locally** so offline sessions still get specific instructions.

**Key design principle — "AI when possible, code when not":** every capability has both an AI path (online, easy/rich) and a code path (offline, reliable). The code path also sanity-checks the AI path.

---

## 2. Confirmed Decisions

### Milestone Strategy
Finish the documented **V1** first — complete Phases 2→3→4 (airport picture pipeline → A\* routing + phraseology → telnet/Nasal bridge + TTS) to a working in-sim taxi-clearance demo. **Do NOT pull voice-input/STT or AI-traffic sequencing into V1.** Tier-1/Tier-2 features layer on top after V1 is complete and shipped.

### Interaction Model
Listen + menu replies (Red Griffin style). **No microphone/speech-to-text in v1.**

### Codebase & Repo
- New add-on; download Red Griffin and **extract only its skeleton for reference** (it's GPLv3).
- Fresh start in `~/Documents/FlightGear Add-on`, new branch, **private** GitHub repo `skh0h/flightgear-ai-atc`.
- **Git authorship:** commits authored by `skh0h <samuelkhoh84@gmail.com>`, no Co-Authored-By trailer.

### Data
Use both an **AI parser** (Gemini reads `groundnet.xml` + `airportinfo` → structured "picture") and a **code parser** (deterministic fallback). Same cached schema.

### Machines
Develop on this Mac (no FlightGear here); **sync via GitHub** to the other Mac (has FlightGear 2024.1.5 + Red Griffin) for in-sim testing.

### Cross-Platform Support *(V2 — supersedes V1's Mac-only assumption)*
Target **Mac AND Windows**. The Python sidecar is already cross-platform (Python + FlightGear HTTP/telnet behave identically on both). The previously Mac-specific TTS piece is resolved via a pluggable TTS backend (below).

**Action:** Ship launch scripts for both OSes (`.command`/shell for Mac, `.bat`/PowerShell for Windows); no installer yet.

### Sidecar Language
Python.

### TTS / Voice UX Strategy *(V2 — supersedes V1's "macOS `say`")*

**Text Display (Priority 1):** ATC reply must be shown as **TEXT prominently at the TOP** of the dialog, plus a voice picker offering ~10–20 selectable voices.

**Engine Strategy:** All TTS engines sit behind a swappable `tts.py` backend (ABC interface):

| Engine | Why | Trade-offs |
|--------|-----|-----------|
| **Piper** (PRIMARY) | Free, offline, neural quality, first-class Windows + Mac support | Best practicality default |
| **Kokoro** | Higher quality than Piper, better naturalness | Heavier model, wants GPU for responsiveness |
| **Cloud** (ElevenLabs / Google / Azure) | Highest quality | Requires API key, per-use cost, network latency |
| **OS-native** | Zero-setup fallback | `say` on Mac, SAPI5 on Windows (robotic) |
| ~~Festival / eSpeak / Flite~~ | Rejected | Pre-neural, robotic, poor Windows support |

**One-liner:** Piper = best default; Kokoro = best free upgrade; ElevenLabs = best if paying.

### Read Transport (Sidecar ↔ FlightGear) *(V2 — refines V1's "telnet for everything")*
- Use the **FlightGear HTTP JSON API** (`--httpd`) for ~10 Hz state reads (property polling). Telnet is ~5 commands/sec — too slow for high-frequency updates.
- Use **telnet / Nasal only for writes** (clearances, frequency changes).
- **Enhancement option:** WebSocket `/PropertyListener` for push-style property-change events (instead of polling). Deferred to Phase 2+ if latency becomes a blocker.

### Architecture Guardrail: Python-Authoritative Clearance State *(V2)*
Keep the **clearance state machine in Python**. Gemini generates language and phrasing only; it is **never** the authority on what was actually cleared (altitude, runway, squawk, controller position). Rationale and supporting research are in [§11 Guardrails](#11-guardrails--lessons-learned).

### Gemini Integration
Python `google-genai` SDK; model **Gemini 2.5 Flash** for phraseology (fast/cheap), optionally **2.5 Pro** for the one-time groundnet parse. Use **structured output (`response_schema`)** so the picture/phraseology come back as validated JSON. API key from `GEMINI_API_KEY` in a **gitignored `.env`**. Offline detection via a lightweight connectivity probe + exception handling → automatic fallback to code parser + template phraseology. **At implementation time, confirm the current `google-genai` package name and live model IDs against Google's official docs before pinning versions** (the API evolves).

---

## 3. Architecture

Two components, both deployed to the FlightGear machine:

1. **Nasal add-on** (thin, runs *inside* FlightGear) — provides a menu + log dialog (listen + menu replies), exposes a small property "mailbox" under `/ai-atc/`, and forwards menu requests. It does **not** contain ATC logic.
2. **Python sidecar** (separate process, same machine) — does all the work: Gemini calls, `groundnet.xml`/`airportinfo` parsing, A\* taxi routing, phraseology, caching, offline fallback, and pluggable TTS output.

**Bridge:** FlightGear launched with the property/telnet server (`--props=5501`), the HTTP JSON API (`--httpd`) for high-frequency reads, and `--addon=…/addon`. The sidecar reads aircraft state via the HTTP API, subscribes to `/ai-atc/request`, computes a response, writes `/ai-atc/response/text` via telnet, and speaks it. The Nasal add-on listens on `/ai-atc/response/text` to update the log.

```
FlightGear (other machine)                      Python sidecar (same machine)
  Nasal add-on  ── /ai-atc/* mailbox ──┐
  /position, /orientation, /velocities │  HTTP   ┌─ fg_bridge (reads via HTTP, writes via telnet)
  /instrumentation/comm[0]/…           ├──:8080──┤─ gemini_client (online)  ──► Gemini API
  /sim/presets/airport-id              │  telnet ├─ parser_ai / parser_code ──► "picture"
                                       ├──:5501──┤─ cache (SQLite, per ICAO+hash)
  log dialog ◄── /ai-atc/response/text ┘         ├─ routing (A* on taxi graph)
                                                 ├─ phraseology (AI online / templates offline)
  audio ◄──────────── TTS backend ◄──────────────┴─ tts (Piper primary; OS-native fallback)
```

### Airport "picture" schema (cached locally, JSON in SQLite)
```
{ icao, source: "ai"|"code", generated_at, groundnet_hash,
  parking:   [{id, name, type, lat, lon, heading}],
  nodes:     [{index, lat, lon, on_runway, hold_point}],
  segments:  [{begin, end, name, pushback}],
  runways:   [{id, thr_lat, thr_lon, heading, length, ils_freq, entry_nodes:[…]}],
  frequencies: {ground, tower, atis, approach, departure, …},
  taxi_graph:  <adjacency built from nodes+segments for pathfinding> }
```
`groundnet.xml` structure to parse: `<parkingList><Parking …/>`, `<TaxiNodes><node index lat lon isOnRunway holdPointType/>`, `<TaxiWaySegments><arc begin end name isPushBackRoute/>`. Taxiway **names** live on `<arc>` and may be empty for some airports — the AI parser infers/labels these; the code path degrades to generic "taxiway"/node-based directions. (See [§6](#6-groundnet-taxiway-naming-finding) for the measured naming distribution and the sparse-name suppression refinement.)

### Taxi routing
Build graph from nodes+segments → nearest node to the gate is the start, runway-entry/hold nodes are targets → **A\*** (great-circle heuristic) → node path → collapse consecutive same-name arcs into an ordered taxiway list → phraseology ("via A, B, hold short of 28R").

---

## 4. Implementation Phases

**Phase 0 — Repo & scaffolding. (DONE)** Fresh branch `main`; project layout (`sidecar/`, `addon/`, `tests/`, `fixtures/`, `docs/`); `.gitignore`; `README.md`; `docs/ARCHITECTURE.md`. Private GitHub repo `skh0h/flightgear-ai-atc` created and pushed.

**Phase 1 — Sidecar skeleton + Gemini.** `venv` + `requirements.txt` (`google-genai`, `python-dotenv`). `config.py` (.env, settings), `gemini_client.py` (structured-output call + offline detection), basic logging. Smoke test: one structured Gemini call.

**Phase 2 — Airport "picture" pipeline.** Download Red Griffin (SourceForge) + obtain a sample `groundnet.xml` (e.g., KSFO) as a committed test fixture. `parser_code.py` (deterministic `xml.etree` parse + airportinfo), `parser_ai.py` (Gemini → picture), `cache.py` (SQLite, keyed by ICAO + groundnet hash), `airport_picture.py` (dataclasses/schema). AI output cross-checked against code output. Unit tests on the fixture.

**Phase 3 — Routing + phraseology.** `routing.py` (graph + A\*, gate→runway), `phraseology.py` (Gemini online + templates offline). Unit tests for routing on the fixture.

**Phase 4 — FlightGear bridge + Nasal add-on.** `fg_bridge.py` (HTTP reads + telnet writes: get/set/subscribe), `main.py` (event loop), `tts.py` (pluggable backend, Piper primary; OS-native fallback). Nasal add-on built from the Red Griffin skeleton: `addon-metadata.xml`, `addon-main.nas` (`main`/`unload`, init `/ai-atc/` mailbox, menu wiring, listener on `/ai-atc/response/text`), `addon-menubar-items.xml`, `addon-config.xml`, `gui/dialogs/ai-atc.xml`.

**Phase 5 — End-to-end on the FlightGear Mac.** Sync via GitHub. Launch FG with `--addon` + `--props=5501` + `--httpd`; start sidecar; spawn at an airport; request taxi via menu; confirm a spoken/logged route naming real taxiways. Verify offline mode (disable network → cached picture + templates still produce a route). Iterate.

---

## 5. Critical Files

```
~/Documents/FlightGear Add-on/
├── sidecar/
│   ├── main.py            # event loop + FG bridge orchestration
│   ├── fg_bridge.py       # HTTP reads (:8080) + telnet writes (:5501)
│   ├── gemini_client.py   # Gemini structured-output calls + offline detection
│   ├── airport_picture.py # picture schema / dataclasses
│   ├── parser_code.py     # deterministic groundnet.xml + airportinfo parser (offline path)
│   ├── parser_ai.py       # Gemini-based parser (online path)
│   ├── routing.py         # taxi graph + A* (gate → runway)
│   ├── runway_selection.py# wind-based departure-runway selection + parking→runway glue
│   ├── phraseology.py     # AI phrasing (online) + templates (offline)
│   ├── cache.py           # SQLite picture cache (ICAO + groundnet hash)
│   ├── tts.py             # pluggable TTS (Piper primary; OS-native fallback)
│   └── config.py          # .env loading, settings
├── addon/
│   ├── addon-metadata.xml
│   ├── addon-main.nas
│   ├── addon-menubar-items.xml
│   ├── addon-config.xml
│   └── gui/dialogs/ai-atc.xml
├── tests/                 # pytest: parser_code, routing, runway_selection, cache, phraseology
├── fixtures/              # sample groundnet.xml (KSFO) + sample airportinfo
├── requirements.txt
├── .env.example           # GEMINI_API_KEY=  (real .env is gitignored)
├── .gitignore
├── README.md
└── docs/ARCHITECTURE.md
```

---

## 6. Groundnet Taxiway Naming Finding

### The Forum Claim
A FlightGear forum reviewer asserted that groundnet XML files don't contain taxiway letters, so the add-on could only degrade to "taxi to runway XX" without intermediate taxiway names.

### Verification Against KSFO Fixture
Verified against the committed `fixtures/KSFO.groundnet.xml` — the claim is **partially true but misleading**:

**Schema:** The `<arc>` (taxiway segment) element *does* have a `name` attribute.
```xml
<arc begin="1234" end="5678" name="A" isPushBackRoute="0"/>
```

**Data distribution in KSFO:**
- **Total arcs:** 3,131
- **Named arcs:** 150 total
  - Real taxiway letters (A–G): **107 (3.4%)**
  - Generic placeholders ("Route", "Startup Location"): **43 (1.4%)**
- **Empty/unnamed arcs:** 2,981 (95.2%)

**Spatial pattern:** The named arcs **cluster at runway entries and major intersections** — exactly where ATC would invoke taxiway names. This is the sweet spot for phraseology clarity.

### Parser Graceful Degradation
The design **already handles sparse naming** with three tiers:
1. **Tier 1 (Online):** Use real names where present; `parser_ai.py` uses a Gemini prompt to infer/label empty segments from groundnet geometry when online.
2. **Tier 2 (Offline, named):** Fall back to inferred names from the cached picture if names were labeled on a prior online session.
3. **Tier 3 (Offline, sparse):** If the path is only sparsely named, `phraseology.py` conditionally omits the `via` clause, degrading to "taxi to runway 28L" alone.

### Verdict & Refinement
**Keep named-taxiway routing; do not abandon it.** The design is sound.

**Refinement to adopt — sparse-name suppression:** suppress the `via` clause when the traced route contains too few named segments. ("taxi via Bravo" with no surrounding context is more confusing than "taxi to runway 28L" alone.)
- **Gate the clause on a coverage threshold:** e.g., ≥ 3 named segments in the path, OR names covering > 30% of path length (by arc count).
- **Rationale:** Low coverage triggers more pilot confusion than zero names; the threshold prevents one-off names from polluting the instruction.
- **Implementation:** In `phraseology.py`, measure named/total arc ratio on the routed path and only include `via` if the threshold is met.

---

## 7. Implementation Status — Parking → Takeoff Runway

**Status: HALF COMPLETE.** Core routing logic and phraseology integration are working. Runway-data availability and in-sim end-to-end testing remain incomplete.

### DONE (working on tree, not yet committed)
- **New module `sidecar/runway_selection.py`** with:
  - `headwind_component(runway_heading, wind_dir, wind_kt)` — scores a runway against wind; computes crosswind and headwind components.
  - `select_departure_runway(picture, *, wind_dir=None, wind_kt=None)` — selects the active departure runway by best headwind and least crosswind. Wind is an input parameter (pure/testable). Graceful fallback: longer runway when wind is absent.
  - `start_node_for_position(picture, lat, lon, *, parking_id=None)` — resolves the aircraft's gate/parking or lat–lon to a start graph node. Prefers parking ID (already a valid graph node via its pushback arc).
  - `on_runway_node_for_position(picture, lat, lon)` — finds the nearest on-runway node.
  - `runway_entry_node(picture, runway)` — finds the hold-short/entry node for the selected runway.
  - `taxi_to_runway(picture, callsign, lat, lon, *, wind_dir=None, wind_kt=None, parking_id=None)` — end-to-end glue: selects runway → resolves start node → resolves runway-entry node → invokes existing A\* (`route_taxiways`) → generates clearance via existing phraseology. Reuses existing routing/phraseology; does not duplicate A\*.
- **Graceful degradation preserved:** when the routed path has no named taxiway segments, clearance degrades to "taxi to runway XX" with no `via` clause (existing contract honored).
- **Test coverage:** `tests/test_runway_selection.py` with 17 new tests, all passing. Full suite: 105 passed, 0 failed.

### Remaining to complete
1. **Runway data not available from groundnet XML alone.** `Runway` objects come from FlightGear's in-sim `airportinfo` at runtime, not from `groundnet.xml`. Parsing `fixtures/KSFO.groundnet.xml` alone yields `picture.runways == []`. Consequence: `select_departure_runway` and `runway_entry_node` are unit-tested only with synthetic runway inputs — the wind-based selection path is **not exercised end-to-end** against the committed fixture or in-sim.
2. **In-sim verification needed.** Run inside FlightGear (or construct a runway-populated `AirportPicture`) to confirm runway selection + entry-node resolution work with real runway data, including that `runway_entry_node` correctly maps the selected runway end to a real hold-short/entry graph node.
3. **Main-flow integration.** Currently the runway is supplied by Nasal (`REQ_RUNWAY`). To auto-select in the sidecar, wire `select_departure_runway` / `taxi_to_runway` into the main event loop instead of requiring Nasal to pass one.
4. **Live wind/METAR source not wired.** `wind_dir` / `wind_kt` must currently be passed in by the caller. Completing the feature means fetching live wind from METAR (aviationweather.gov) and feeding it into `select_departure_runway` — this connects to the "METAR-driven runway selection" top-priority item ([§8](#8-feature-roadmap--backlog)).
5. **Sparse-name suppression refinement** ([§6](#6-groundnet-taxiway-naming-finding)) remains documented-only and not yet implemented in `phraseology.py`.

---

## 8. Feature Roadmap & Backlog

*This section merges the V2 feature tiers and the V3 backlog into one list, grouped by priority. The condensed master ranking is in [§9 Priority Matrix](#9-priority-matrix).*

### Top Priorities (recommended next work, after V1 stabilizes)

#### 1. METAR-Driven Runway Selection *(High Impact / Low Effort)*
Wind + per-aircraft crosswind limit + runway heading determine the active runway; stops ATC assigning a runway into a strong tailwind. V1 assigns runways deterministically; in real operations wind drives selection, and an aircraft can reject a runway whose crosswind exceeds its certified limit.
**Integration:** Fetch METAR from `aviationweather.gov`; extract wind dir/speed. Compute crosswind per runway. Compare to aircraft type (read `/sim/aircraft-id`); look up certified crosswind limit from a simple CSV or Gemini. Filter eligible runways; prefer the longest if both are viable. *(The `runway_selection.py` work in [§7](#7-implementation-status--parking--takeoff-runway) is the half-built foundation for this.)*

#### 2. Callsign + Aircraft-Type Personalization *(High Impact / Low Effort)*
Read `/sim/multiplay/callsign` and `/sim/aircraft-id`, inject into Gemini prompts so ATC calls are personalized (e.g., "N12345, taxi to runway 28L") and aircraft-type appropriate. Immersion: "aircraft" → "Citation X" is a big difference; payware tools do this — table stakes.
**Integration:** Add callsign + aircraft type to the `phraseology.py` Gemini system prompt; add type-specific crosswind/runway filters in runway selection.

#### 3. Replay / Regression Testing from Session Captures *(High Impact / Medium Effort)*
Record property snapshots + ATC exchanges to JSONL per session; add a `--replay` mode that runs routing/phraseology against golden files with no FlightGear running. Safety net so the next refactor doesn't break a shipped phrase/route.
**Integration:** Extend the `main.py` event loop to log all state snapshots + requests/responses to a session JSONL; add `--replay <session.jsonl>` to replay requests and compare output against golden responses (or log diffs).

#### 4. Phraseology Grading + Debrief *(High Impact / Medium Effort)*
Log pilot selections vs. correct ICAO phrasing; generate a scored end-of-session debrief (e.g., "you read back 'roger' instead of 'wilco'", "you violated hold-short by 50 ft"). **No payware ATC tool does pilot grading** — a real differentiator that turns the add-on into a training tool.
**Integration:** Score pilot readback against expected ICAO format (Gemini structured-output rubric); store grade + feedback in the session log; synthesize a debrief dialog at session end. Optional: export a learner logbook entry.

#### 5. SID Assignment from Filed Route *(High Impact / Medium Effort)*
Read `/autopilot/route-manager/`, derive the departure procedure (FAA CIFP or Gemini+Search), validate against the active runway. Real IFR clearance always includes a SID (or "no SID"); this closes the clearance-delivery gap.
**Integration:** Parse route-manager waypoints → departure fix; Gemini + Google Search to fetch the runway-specific SID from FAA CIFP (US) or derive it (non-US); validate against active runway; inject into clearance: "Cleared as filed via [SID], climb 2000."

### Foundational ATC Features *(from the V2 tiers — partly delivered by V1)*

| Feature | What it does | Key integration point |
|---------|-----------|----------------------|
| **IFR Clearance Delivery** | Pilot calls for clearance; proper C-D-A-F-S phraseology (clearance limit, departure, altitude, frequency, squawk); readback required. *The single feature that makes it feel like real IFR.* | Detect Delivery/Ground frequency via COM1 poll; read aircraft type from `/sim/aircraft-id` |
| **Taxi Instructions w/ Groundnet Routing** | Parse groundnet XML, build node graph, shortest path (parking → runway hold-short), progressive taxi string. *Delivered by V1 Phases 2–3; KSFO fixture in place.* | Groundnet XML loader; A\* pathfinding; real-time aircraft position |
| **ATIS from Live METAR** | Fetch METAR (aviationweather.gov), Gemini generates phonetic ATIS with info code (Alpha, Bravo…), broadcast on ATIS frequency. Cheap, high realism. | HTTP fetch + Gemini; ATIS frequency polling from airport freq data |

### Strong Immersion *(moderate effort)*

| Feature | What it does | Complexity |
|---------|-----------|----------------------|
| **Voice I/O Loop** | Faster-Whisper (STT) + Silero VAD (push-to-talk) + Piper/Kokoro (TTS); optionally inject audio through FGCom-mumble on the tuned frequency. *Biggest single immersion driver.* | Deferred out of V1; needs audio capture + Mumble integration |
| **Departure / Approach Handoffs** | Detect climb-through altitude or top-of-descent; issue "contact Departure/Approach on …"; confirm via newly tuned frequency. | Read `/sim/autopilot/settings/target-altitude`; compare to current; trigger at threshold |
| **Arrival Sequencing & Vectoring** | ~30 nm out, issue vectors/speed/intercept; reads `/ai/models/aircraft[n]` to build a basic traffic picture. Addresses the sequencing gap. | AI/MP property space; distance/bearing calc; simple priority queue |
| **Non-Standard Request Handling** | Pure LLM value: "unable assigned altitude, request FL280", weather deviations, etc. | LLM flexibility + Python approval layer; no new integration |

### Later / Nice-to-Have
- **Controller Personality Profiles** — terse Center vs. chatty tower via Gemini system prompt.
- **Emergency Handling** — MAYDAY / PAN-PAN with priority handling and vectors to nearest airport.
- **Readback-Error Correction** — detect wrong altitude/runway in pilot readback, issue correction.

### Other Backlog Ideas *(grouped by theme)*

**Data & Environment**
- **NOTAM injection into the taxi graph** — remove closed segments and relay NOTAMs in context ("taxiway A is closed, taxi via B instead"). Needs a NOTAM parser + sidecar integration.
- **SIGMET/AIRMET weather-deviation advisory relay** — fetch SIGMETs; if significant weather intersects the route, offer a deviation advisory. Needs a weather API + geospatial logic.
- **FAA CIFP procedure database** — authoritative SID/STAR/approach text; Gemini fallback for non-US. Reduces reliance on Gemini inference.
- **D-ATIS real-world active runway** — fetch D-ATIS, extract active runway to validate against computed runway. Adds real-world ground truth.

**Taxi & Movement**
- **Conditional/progressive taxi monitoring** — auto-issue the next segment at hold-short points via position polling; extends the single upfront clearance into a reactive sequence.
- **Missed-approach/go-around detection** — altitude+VS+groundspeed signature detection; re-sequence traffic if the pilot goes around.
- **Graceful reconnect + clearance-state persistence** — SQLite session state across FG restarts; resume clearance state without re-filing.

**UX & Safety**
- **ATIS information-code cycling** — persist the ATIS info code (Alpha, Bravo, …) per airport; advance only on material METAR change.
- **Readback training mode** — inject a deliberate error (e.g., wrong runway) in readback; check whether the pilot catches it.
- **Sidecar health dashboard** — localhost FastAPI page: FG connection status, cache hit/miss rate, Gemini latency, active TTS voice, session log.
- **Accessibility** — high-contrast/large-font dialog + plain-text transcript file; keyboard-only ATC shortcuts.
- **Logbook integration** — write machine-readable `logbook.json` per session (callsign, airport, runway, SID, duration, grade).

**Tower & Multi-Aircraft**
- **Tower mode: multi-aircraft sequencing** — use `/ai/models/aircraft[n]` to build a traffic picture; sequence multiple AI aircraft for landing/departure. Addresses the biggest Red Griffin gap.
- **Shared-cockpit ATC radio assignment** — captain/FO active-seat gating; only the active pilot can request a clearance.

**Immersion polish**
- **Route ATC audio through FGCom-mumble** — inject synthesized voice on the tuned frequency so it comes through the in-sim radio spatially, not as detached system audio.
- **Radio-quality effects** — static/squelch/clipping on TTS output; pairs with controller personalities.
- **Frequency tuning IS the trigger** — poll COM1, map MHz → controller position (GND/TWR/APP…) from airport freq data to select controller + persona.
- **VFR advisory mode** — traffic advisories, pattern/circuit work as a second mode beyond IFR; a payware differentiator.

---

## 9. Priority Matrix

| Idea | Impact | Effort | Priority | Rationale |
|------|--------|--------|----------|-----------|
| **METAR-driven runway selection** | High | Low | **1 (Top)** | Wind logic is real-world essential; low effort; unblocks aircraft-type filters. |
| **Callsign + aircraft-type personalization** | High | Low | **2 (Top)** | Immersion multiplier; minimal code; immediate payoff. |
| **Replay/regression testing** | High | Medium | **3 (Top)** | Safety net for future refactors; golden-file pattern is proven. |
| **Phraseology grading + debrief** | High | Medium | **4 (Top)** | **No payware ATC tool does this**; training differentiator; Gemini-native scoring. |
| **SID assignment from filed route** | High | Medium | **5 (Top)** | IFR completeness; closes clearance-delivery gap; moderate CIFP integration. |
| Tower mode: multi-aircraft sequencing | High | High | 6 | Biggest Red Griffin gap; highest impact; deferred to Phase 2+. |
| Conditional/progressive taxi monitoring | Medium | Medium | 7 | Extends single clearance into reactive sequence; nice-to-have after V1. |
| NOTAM injection + graph closure | Medium | Medium | 8 | Realism; moderate integration; lower urgency than wind/SID. |
| Readback training mode | Medium | Medium | 9 | Teaching feature; requires Gemini error injection; good post-V1 add-on. |
| FAA CIFP procedure database | Medium | Medium | 10 | Reduces Gemini reliance; authoritative source; deferred if Gemini inference works. |
| Missed-approach/go-around detection | Medium | Medium | 11 | Safety + sequencing; altitude signature logic; good Phase 2 feature. |
| Sidecar health dashboard | Medium | Low | 12 | Observability; FastAPI page; good post-V1 ops tool. |
| SIGMET/AIRMET weather deviations | Medium | High | 13 | Realism; requires geospatial logic; deferred. |
| Graceful reconnect + state persistence | Low | Low | 14 | Convenience; quick SQLite session storage; nice-to-have. |
| ATIS info-code cycling | Low | Low | 15 | Realism; low effort; nice-to-have detail. |
| Logbook integration | Low | Low | 16 | Training log; JSON export; low priority. |
| Shared-cockpit ATC assignment | Low | Medium | 17 | Multiplayer edge case; deferred. |
| Accessibility (high-contrast, keyboard shortcuts) | Medium | Medium | 18 | Broadens user base; separate effort stream. |
| D-ATIS real-world active runway | Low | Medium | 19 | Real-world ground truth; deferred. |

---

## 10. Staging Recommendation

**Phase 1 (Current):** Complete V1 — taxi routing + phraseology + telnet/Nasal bridge + TTS. A taxi-clearance demo end-to-end (aircraft startup → parking clearance received) proves all integration layers work and establishes the data-pipe, TTS, and state-machine patterns that later features reuse.

**Phase 2 (Recommended Next):** Sequence the five top-priority ideas in order — (1) METAR-driven runway selection, (2) callsign + aircraft-type personalization, (3) replay/regression testing, (4) phraseology grading + debrief, (5) SID assignment. Each is self-contained and doesn't block the others. Completing these five raises the add-on from a proof-of-concept to a credible alternative to payware ATC tools.

**Phase 3+:** Backlog items and tower mode as engineering capacity allows.

**Why finish V1 first:** completeness (proves the full stack), credibility (ships a working feature set before adding complexity), and foundation (V1's data-pipe/TTS/state-machine patterns are reused by everything after).

---

## 11. Guardrails & Lessons Learned

### Keep the LLM out of safety-critical decisions
An arxiv study found LLM ATC agents routinely **violate their own separation rules** when they hold the authoritative state. Hence the **Python-authoritative clearance state machine** ([§2](#2-confirmed-decisions)): Gemini generates *language*; Python enforces *rules* and remains the sole authority on what was actually cleared (altitude, runway, squawk, controller position). This mirrors the BeyondATC pattern and makes the system **auditable** — a human can review what was cleared vs. what Gemini said. Closest prior art: `fgatc` (bartacruz) — a Python sidecar with Dijkstra groundnet routing.

### Design around SayIntentions.AI's pain points
- **STT mis-hears** → implement a readback confirmation loop.
- **Readback errors go uncaught** → explicit validation before applying a clearance.
- **Server latency** → local fallback / offline Piper as the default.
- **Implausible runway selection** → filter by wind direction + runway status from METAR + active runways (the METAR-driven runway selection feature).

---

## 12. Reuse, References & Prior Art

### Reuse (don't reinvent)
- **Red Griffin skeleton** (SourceForge) — copy the add-on layout, `addon-main.nas` `main(addon)`/`unload(addon)` shape, and dialog XML conventions only.
- **FlightGear Nasal built-ins** for the thin add-on: `setlistener`, `maketimer`, `props`, and `airportinfo()`/`.comms()`/`.runway()` for any in-sim data fetch. Most logic stays in the Python sidecar.
- **FlightGear HTTP JSON API** (`--httpd`) for high-frequency reads; **telnet/property protocol** (`get`/`set`/`subscribe`) for writes in `fg_bridge.py`.
- **Pluggable TTS** — Piper (primary); OS-native (`say` / SAPI5) as zero-setup fallback.

### Prior art & existing projects
- **fgatc** (bartacruz, GitHub) — closest prior art: Python sidecar, Dijkstra groundnet routing, frequency-filtered AI ATC.
- **ATC-pie / OpenRadar** — community ATC tools (put the USER in the controller seat; multiplayer-oriented).
- **FGCom-mumble** — community radio/VoIP layer; supports audio injection on a frequency.
- **BeyondATC** (MSFS) — the LLM-as-informational-layer pattern this design follows.
- **SayIntentions.AI** — full IFR+VFR AI ATC; source of the "lessons learned" pain points.

### FlightGear integration references
- HTTP JSON Properties API (`--httpd`), telnet property-set commands, AI/MP aircraft properties, FG-MCP Server (wiki.flightgear.org), Nasal `airportinfo()` for runway/freq/parking data.

### Data-pipe note (design early)
Frequencies, runway thresholds, and parking/gate positions must reach the sidecar via Nasal `airportinfo()` + `/position` props. Phase 2–3 routing depends on this pipe being in place.

---

## 13. Verification

### Local (this Mac, no FlightGear)
- `pytest tests/` — parser (code path on the committed `groundnet.xml` fixture), routing (gate→runway produces a valid ordered taxiway list), runway selection, cache (write/read/hash-invalidation), phraseology templates.
- Run the sidecar against a **mock property server** with canned aircraft state; confirm a request produces correct response text and a TTS invocation.
- Gemini calls mocked in tests; one live structured-output smoke test gated behind `GEMINI_API_KEY`.

### On the FlightGear Mac (in-sim, via GitHub sync)
- Launch `fgfs --addon=…/addon --props=5501 --httpd=8080`; start `python sidecar/main.py`.
- Spawn at an airport with groundnet data (e.g., KSFO); use the menu to request taxi; confirm the spoken + logged instruction names **real** taxiways and a valid route to the assigned runway.
- **Offline test:** disable network → confirm the cached picture + template phraseology still produce a specific route (graceful degradation).

### Near-term hygiene (small, actionable now)
- [ ] Add `pydantic` to `requirements.txt` (used in tests, needed by every Phase 2 model; currently missing).
- [ ] `git add fixtures/KSFO.groundnet.xml` (committed to disk but untracked).
- [ ] Add cross-platform launch scripts (Mac `.command`/shell + Windows `.bat`/PowerShell).
- [ ] Design the Nasal → sidecar data pipe early (frequencies via `airportinfo()`, runway thresholds, parking position).

---

## 14. Open Questions

- **CIFP data source:** license FAA CIFP (annual subscription) or rely on Gemini + Search API to infer SIDs? Gemini is fast/free but less authoritative; CIFP is authoritative but costs money.
- **Crosswind CSV:** where do we source aircraft certified crosswind limits — a curated CSV, or Gemini inference from type name?
- **Grading rubric:** which ICAO readback errors trigger deductions (wrong altitude? wrong runway? wrong phonetics?)? Define a simple rubric.

### Future phases (not in v1)
- Microphone / speech-to-text ("talk to ATC").
- Traffic awareness & sequencing via `/ai/models/` (the biggest Red Griffin gap).
- Real-world procedure enrichment (SIDs/STARs) via Gemini + Google Search grounding.
- Higher-quality neural TTS voices (swap into `tts.py`).
