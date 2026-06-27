# Ideas-to-Phases Roadmap — FlightGear AI ATC Add-on (2026-06-25)

## Purpose & How to Read This

This document organizes 62 ideas from `IDEAS.md` into a **10-phase shipping roadmap** for the FlightGear AI ATC add-on. Each phase is a coherent, shippable increment that respects dependency constraints and builds toward full gate-to-gate coverage.

**Current state (committed/in-progress):**
- ✅ Core architecture: Nasal add-on + Python sidecar (complete).
- ✅ Airport data pipeline: parser (code + AI), cache, `groundnet.xml` support.
- ✅ A\* taxi routing, basic phraseology (online via Gemini + offline templates).
- ✅ Gemini integration (structured output, offline fallback).
- ✅ TTS via macOS `say`, FG telnet bridge (`:5501`), session logging.
- ✅ Nasal add-on skeleton, menubar, dialogs, property mailbox.
- ✅ Wind-based runway auto-selection (#24), METAR fetch (#25 core).
- ✅ Personalization (callsign/preferred airport), replay harness, `AI_TAXIWAY_LABELS` flag.
- ✅ FG2026 metadata blocker **fixed in code** (uncommitted; Phase 0 unblocks this).

**Status legend:**
- **✅ Done** — Implemented and committed.
- **🟡 Committed/Next** — In-flight or on the active roadmap (Phase 0–1).
- **⚪ Future** — Planned for later phases (Phase 2+).
- **🔒 Out of Scope** — Deliberately deferred or blocked by architectural constraints.

---

## Blockers & Preconditions

**B1: FG2026 metadata incompatibility — RESOLVED in code, NOT pushed.**
- **Status:** Fixed but uncommitted in `addon/addon-metadata.xml`.
- **Impact:** Blocks all in-sim validation (Phase 5 of Phase 0); add-on won't load in FG 2026.
- **Unblock:** Commit + push the fix, verify in-sim with `scripts/run-mac.command`.

**B2: Telnet `:5501` not open by default (app-icon launch).**
- **Status:** Resolved by Stage 0 (#53) hardening `scripts/run-mac.command`.
- **Impact:** Sidecar can't connect; "feels broken."
- **Unblock:** Users double-click `run-mac.command` instead of the app icon.

**B3: Callsign never auto-fills.**
- **Status:** Keybinding/menu bypass `request()` (direct prop set).
- **Impact:** No callsign persistence, inconsistent state.
- **Unblock:** Stage 0 (#56) route all requests through `request()`.

**B4: Sidecar swallows exceptions silently.**
- **Status:** `handle_trigger` catches exceptions but never writes a response.
- **Impact:** UI hangs on error; no signal of failure.
- **Unblock:** Stage 0 (#57) always write `RESP_TEXT` + `RESP_READY` on exception.

**B5: `AI_TAXIWAY_LABELS` off (policy constraint).**
- **Status:** No authoritative real-world data source; Gemini fabricates taxiway names.
- **Impact:** Correct; deferred (not on roadmap).
- **Unblock:** Future grounding via real airport databases (Phase 8); currently not blocking.

**B6: AI aircraft cannot be commanded (FG architectural constraint).**
- **Status:** FlightGear doesn't expose `/ai/models/` write API to scripts.
- **Impact:** Can't move whole AI fleet; no "take-over" mode.
- **Unblock:** Mode A (user selects active runways) and Mode B (read-only sequencing) route around it; **permanently out of scope**.

---

## Phases

### Phase 0 — Unblock & Stabilize (ACTIVE SPRINT)

**Goal:** Make in-sim testing possible and observable. Fix "feels broken" (silent hangs, hidden errors, never-connected sidecar).

**Exit criteria / definition of done:**
- FG2026 metadata fix committed and in-sim verified.
- `run-mac.command` is the blessed launcher (telnet opens, sidecar starts, no silent hangs).
- Panel shows backend status (Connected/Offline/Not running) and never hangs on Processing.
- Sidecar always replies with user-facing text; exceptions don't swallow responses.
- Keybinding/menu unified through `request()`.
- Taxi request works end-to-end in-sim and names real taxiways.
- Tier 1b bug fixes (deterministic runway order, double-listener reload, nil guards, etc.) closed.

**Delivered ideas:**
- **B1 (infrastructure):** Commit FG2026 metadata fix + in-sim verify.
- **#53** — Harden `scripts/run-mac.command` (auto-detect FGFS, poll telnet, sidecar logging).
- **#54** — Sidecar heartbeat + backend status signal (Nasal listener on staleness).
- **#55** — Request watchdog (8s timeout, never hang on Processing).
- **#56** — Menu/keybinding → `request()` unification + callsign auto-fill.
- **#57** — Sidecar always replies on exception (user-facing text + recovery).
- **#58** — Telnet bridge hardening (banner drain, prompt drain, BridgeError on peer close).
- **#59** — `--selftest` flag (Gemini + telnet health check).
- **#60** — Airport-change listener (republish on `/sim/presets/airport-id` change).
- **Tier 1b:** All TODO.md bugs (version str, log growth cap, nil guards, deterministic runway order, bridge mid-read, WAL, METAR units, CACHE_DB_PATH, replay docstring, etc.).

**Key files touched:**
- `addon/addon-metadata.xml` (FG2026 fix).
- `addon/addon-main.nas` (heartbeat listener, watchdog, `request()` routing, airport-change listener).
- `addon/addon-config.xml` (menu/keybinding through `request()` not direct props).
- `addon/addon-menubar-items.xml` (same as above).
- `scripts/run-mac.command` (hardening).
- `sidecar/main.py` (exception recovery, heartbeat publish, airport-change re-publish, `--selftest`).
- `sidecar/fg_bridge.py` (banner/prompt drain, `BridgeError`).
- `sidecar/phraseology.py`, `cache.py`, `parser_ai.py` (Tier 1b fixes per TODO.md).
- `tests/` (watchdog, bridge, exception recovery, new request types).
- `README.md` (update quick-start: use `run-mac.command`).

**Dependencies:** None (all blocker-unblocking).

**Effort:** M (tooling + robustness, no new features).

---

### Phase 1 — Panel Redesign & Request Framework (Stage 1–2 from fix-and-redesign plan)

**Goal:** Replace the skeleton panel with a cohesive, information-rich design. Add arrival/approach request types so the system covers all flight phases.

**Exit criteria / definition of done:**
- New panel layout (header with airport + backend status, info block, frequency list, phase-grouped buttons, transcript log, About, Close).
- All ground & departure functions (Pushback, Taxi, Takeoff) wired and tested.
- Arrival/approach functions (Approach, ILS, Airfield in sight, Radio check) added to panel and sidecar.
- Offline templates for all new request types.
- Gemini online path leverages existing `phrase_online` infrastructure.
- Panel never shows stale runway/frequency data (re-publishes on airport change).
- End-to-end in-sim: request any phase → spoken clearance + log entry.

**Delivered ideas:**
- **#61** — Panel redesign (PUI dialog, richer layout, backend status, freq list, phase buttons).
- **#62** — Arrival/approach request types (approach, ils, airfield_in_sight, radio_check).

**Key files touched:**
- `addon/gui/dialogs/ai-atc.xml` (complete redesign).
- `addon/addon-main.nas` (publish state props for panel bindings).
- `sidecar/main.py` (handle new request types in `handle_trigger`).
- `sidecar/phraseology.py` (templates + Gemini calls for new types).
- `tests/` (unit tests for new request types, offline template fallback, Gemini mocking).

**Dependencies:** Phase 0 (backend heartbeat, exception recovery, airport-change listener).

**Effort:** M (XML + phraseology, new request types, panel state synchronization).

---

### Phase 2 — Airport Config & Traffic Sequencing (Mode A & B)

**Goal:** Enable user to configure active runways (Mode A) and see AI traffic sequencing (Mode B). Lay the foundation for multi-runway, traffic-aware operations.

**Exit criteria / definition of done:**
- Mode A: user selects active runways via config dialog (Runway.active field added).
- Runway selection filter applied to taxi routing (user → assigned active runway, not all).
- Mode B: sidecar reads AI traffic from `/ai/models/` property tree.
- AI traffic snapped to groundnet (nearest parking/node).
- Queue list UI in panel shows sequence (user at position N, next traffic in order).
- Both modes ground on Runway.active field being published.
- Integration test: spawn AI traffic at airport, request taxi, user gets correct sequencing.

**Delivered ideas:**
- **#50** — Mode A active/inactive runway config (dialog checkboxes + Runway.active field).
- **#51** — Mode B live traffic sequencing (read `/ai/models/`, snap to groundnet, order user).
- **#52** — Config panel UI (runways, queue display, traffic list).

**Key files touched:**
- `addon/gui/dialogs/ai-atc.xml` (config dialog, queue display).
- `addon/addon-main.nas` (Runway.active management, publish traffic list).
- `sidecar/main.py` (read `/ai/models/`, snap to groundnet, compute queue).
- `sidecar/airport_picture.py` (Runway schema: add .active field).
- `sidecar/routing.py` (filter by Runway.active).
- `tests/` (Mode A filtering, Mode B snapping + sequencing, queue order correctness).

**Dependencies:** Phase 0 (airport-change listener), Phase 1 (panel framework).

**Effort:** L (traffic telemetry + groundnet snapping is real work, but no Gemini complexity).

---

### Phase 3 — Emergencies & Abnormals

**Goal:** Add high-value, high-realism phraseology for abnormal situations (MAYDAY, go-around, fuel emergency, etc.). Low infrastructure; mostly phraseology + event triggers.

**Exit criteria / definition of done:**
- New request types: `mayday`, `pan_pan`, `gear_emergency`, `min_fuel`, `diversion`, `go_around`, `squawk_7500`, `squawk_7600`, `squawk_7700`.
- Each has offline template + Gemini online enrichment.
- Phraseology handler looks up nearest suitable airport (for diversion).
- Panel has Emergency button group.
- Integration test: trigger each emergency type, confirm spoken output + realistic routing.

**Delivered ideas:**
- **#15** — MAYDAY/PAN-PAN emergencies (phraseology + frequency handoff suggestion).
- **#16** — Squawk 7500/7600/7700 reactions (capture code, respond with guidance).
- **#17** — Abnormal ops (min-fuel/diversion/go-around/gear).
- **#18** — Gear fly-by (for checkride realism; depends on #17 structure).
- **#22** — Go-around runway occupied (if Mode B sees conflicting traffic, suggest alternate).
- **#40** — Guard 121.5 monitoring (acknowledge, don't auto-respond; informational).

**Key files touched:**
- `addon/gui/dialogs/ai-atc.xml` (Emergency button group).
- `addon/addon-main.nas` (squawk monitoring, event triggers).
- `sidecar/main.py` (new request types, nearest-airport lookup).
- `sidecar/phraseology.py` (emergency templates + Gemini calls).
- `tests/` (template completeness, nearest-airport correctness).

**Dependencies:** Phase 0 (exception recovery, request framework), Phase 1 (request type infrastructure).

**Effort:** M (phraseology-heavy; reuses existing routing + Gemini paths).

---

### Phase 4 — Session Memory & Personality

**Goal:** Make ATC feel alive and continuous. Remembers prior interactions, develops quirks, shifts mood. High ROI for low infra (session_log already exists).

**Exit criteria / definition of done:**
- Session memory wired to Gemini prompts (context includes recent session history).
- Personality engine: controller backstory + name generation, accent/style variation.
- Mood/fatigue drift: responses shift subtly over session length.
- Relief handoff: handoff controller, brief new one from session memory.
- Controller-of-the-day: LLM-generated backstory + voice quirk per session.
- Student/checkride mode: controller acknowledges readbacks, coaching available.
- Easter egg: quiet-night mode (after midnight local) has ambient chatter, reflective remarks.
- Integration test: 2+ hour session shows personality drift, remembers earlier clearances.

**Delivered ideas:**
- **#48** — Session memory/continuity (wire session_log to prompts; cheap, high ROI).
- **#2** — Personality engine (LLM controller backstory, accent, style).
- **#3** — Mood/fatigue drift (response tone shifts over session).
- **#5** — Relief handoff (hand off to new controller, brief from session log).
- **#32** — Student vs checkride modes (coach mode, readback enforcement).
- **#43** — LLM controller-of-the-day backstories (per-session generation).
- **#45** — Quiet-night easter eggs (ambient chatter, mood shift after midnight).

**Key files touched:**
- `sidecar/main.py` (wire session_log to Gemini context, controller state management).
- `sidecar/gemini_client.py` (prompt engineering: include session context, personality scaffolding).
- `sidecar/phraseology.py` (mood/fatigue variation in template selection).
- `sidecar/session_log.py` (expand to track controller state, handoff events).
- `addon/addon-main.nas` (mode selector: student/checkride/normal; readonly after-midnight flag).
- `tests/` (session context injection, personality consistency, mood drift over time).

**Dependencies:** Phase 0 (session_log access), Phase 1 (request framework for mode selection).

**Effort:** L (mostly prompt engineering + state tracking; reuses existing Gemini calls).

---

### Phase 5 — Voice Realism

**Goal:** Replace macOS `say` with multi-voice TTS (Piper), add STT (Whisper), radio static, stepped-on transmissions, PTT realism. Full voice realism pipeline.

**Exit criteria / definition of done:**
- Piper TTS replaces `say` (multiple voices: ground/tower/approach/ATIS).
- Whisper STT integrated: pilot can speak requests (if hardware available).
- Radio static/squelch (ambient noise, audio post-processing).
- Stepped-on transmissions (realistic overlap when pilot + ATC speak simultaneously).
- PTT/joystick support (push-to-talk not just menu clicks).
- Readback enforcement: ATC asks for readback, Whisper captures it, grades against expected format.
- Integration test: full voice loop (pilot speaks → Whisper → request → ATC response → Piper TTS + static).

**Delivered ideas:**
- **#27** — Whisper STT + Piper TTS (replaces macOS `say`; multi-voice setup).
- **#28** — Stepped-on transmissions (overlap realism).
- **#29** — Radio static/squelch (ambient noise, Doppler).
- **#30** — Readback enforcement (Whisper → grade against template).
- **#31** — PTT/joystick (hardware button presses, not just menu).

**Key files touched:**
- `sidecar/tts.py` (Piper integration, voice selection by frequency/role).
- `sidecar/main.py` (add STT listener, readback grading).
- `addon/addon-main.nas` (PTT binding, joystick input).
- `sidecar/phraseology.py` (readback templates for grading).
- `tests/` (Piper voice fallback, STT mock, readback grading logic).

**Dependencies:** Phase 1 (request framework; STT feeds into it), Phase 4 (personality influences voice selection).

**Effort:** XL (audio pipeline is complex; Piper, Whisper, audio synthesis, post-processing).

---

### Phase 6 — Living World / Traffic Depth

**Goal:** Multi-aircraft awareness, wake turbulence, LAHSO, intersection departures. Make the world feel populated and dynamic.

**Exit criteria / definition of done:**
- Traffic sequencing (build on Mode B): queue user with realistic separation.
- Wake turbulence warnings (heavy aircraft nearby → spacing guidance).
- LAHSO (Land and Hold Short Operations): sequence aircraft to co-use parallel runways.
- Intersection departures (depart from mid-runway taxiway, if aircraft weight allows).
- Ambient chatter: hear other aircraft on frequency (voice realism phase + Mode B traffic list).
- Go-around sequencing (if Mode B sees conflict, proactive go-around guidance).
- Integration test: 3+ aircraft at airport, user sequenced correctly, chatter realistic.

**Delivered ideas:**
- **#19** — Traffic sequencing (multi-aircraft coordination).
- **#20** — Wake turbulence (spacing guidance for heavy aircraft).
- **#21** — LAHSO/intersection departures (runway sharing, weight-based).
- **#23** — Ambient frequency chatter (cross-frequency awareness).

**Key files touched:**
- `sidecar/main.py` (multi-traffic sequencing, separation rules).
- `sidecar/routing.py` (intersection departure support, weight-based logic).
- `sidecar/phraseology.py` (separation/sequencing templates).
- `addon/addon-main.nas` (ambient chatter mixer, frequency simulation).
- `tests/` (sequencing correctness, wake turbulence separation, LAHSO logic).

**Dependencies:** Phase 0 (traffic read path), Phase 2 (Mode B), Phase 5 (voice/chatter).

**Effort:** XL (multi-aircraft coordination is complex; new routing constraints).

---

### Phase 7 — IFR & Full ATC Coverage

**Goal:** Instrument procedures, departure/arrival planning, holding patterns, navaids. Unlock realistic filed-flight IFR operations.

**Exit criteria / definition of done:**
- Per-position state machine (controller state tracking: pre-flight, taxi, departure, climb, cruise, descent, approach, landing).
- Gate-to-gate clearance: start at gate → pushback → taxi → takeoff → climb → cruise → descent → approach → landing → park.
- Navaid integration: read VOR/NDB/DME from FG navdb, include in clearances.
- Airways/direct-to/DME arcs: clearance includes standard routes, not just taxiway names.
- SIDs/STARs/approaches: consume CIFP data (X-Plane) or ARINC 424; phrase SID names + altitude restrictions.
- Holding patterns: ATC can place aircraft in hold, generate spiral descent, exit clearances.
- Full IFR clearance (CRAFT format): complete departure clearance in one transmission.
- Arrival clearance: expect/approach/descent clearance sequence.
- Flow control & EDCT: slot time management for busy airports.
- Integration test: file IFR flight plan, get full departure clearance, sequence through arrival, full gate-to-gate.

**Delivered ideas:**
- **#47** — Per-position controller state machine (cross-cutting architecture; prerequisite for #1).
- **#1** — Gate-to-gate chain (full flight coverage, state machine enabled).
- **#6** — Navaid integration (VOR/NDB/DME/ILS read from navdb).
- **#7** — Airways/direct-to/DME arcs (standard routing, not just taxiways).
- **#8** — SIDs/STARs/approaches (CIFP consumption, altitude restrictions).
- **#9** — Holding patterns (spiral descent, exit clearance).
- **#10** — Full IFR clearance (CRAFT format: clearance, squawk, altitude, routing, equipment).
- **#14** — Arrival clearance (expect/approach/descent sequence).
- **#44** — Flow control/ground stops/EDCT (capacity management).

**Key files touched:**
- `sidecar/main.py` (state machine, full clearance generation).
- `sidecar/routing.py` (navaid-aware routing, airways, DME arcs, procedures).
- `sidecar/phraseology.py` (SID/STAR/approach phrasing, CRAFT format).
- `sidecar/airport_picture.py` (extend schema: navaids, airways, CIFP data).
- `sidecar/parser_ai.py`, `parser_code.py` (navaid parsing, CIFP schema).
- `addon/addon-main.nas` (file-plan integration, state machine UI).
- `tests/` (state machine transitions, navaid correctness, CRAFT format validation).

**Dependencies:** Phase 0 (core stability), Phase 1 (request framework), Phase 2 (traffic awareness baseline for state machine context), Phase 5 (multi-request coherence).

**Effort:** XL (state machine is significant architecture; navaid data + airways routing is deep).

---

### Phase 8 — Grounding & Data Integrations

**Goal:** Real-world data sources: SimBrief flight plans, OpenAIP airspace, FAA NASR, X-Plane CIFP, FSS briefings. Maximum realism & accuracy.

**Exit criteria / definition of done:**
- SimBrief import: read filed plan, confirm route, fuel, alternates.
- Airspace class integration: know if inside Class A/B/C/D/E/G, enforce rules.
- OpenAIP/FAA NASR: special-use airspace (MOA, restricted, alert), display warnings.
- Airspace bust warning (Brasher): detect if user below minimum IFR altitude or in restricted airspace.
- VFR flight following: ATC tracks VFR aircraft, no clearance needed but frequency monitoring.
- UNICOM/CTAF uncontrolled fields: different phraseology (self-announce, no ATC sequencing).
- FSS briefings: gravity briefing, NOTAMs, TFRs, weather summary before departure.
- CIFP integration (if not in Phase 7): SID/STAR/approach procedures.
- Integration test: import plan → get airspace warnings → receive appropriate (class/CTAFversus ATC) guidance.

**Delivered ideas:**
- **#37** — SimBrief import (flight plan integration, fuel/alternate confirmation).
- **#11** — Airspace class entry (know A/B/C/D/E/G; enforce rules).
- **#12** — Special-use airspace (MOA, restricted, alert areas).
- **#13** — Airspace bust/Brasher warning (altitude violation + restricted airspace).
- **#8** — CIFP integration (if not in Phase 7; X-Plane format consumption).
- **#38** — UNICOM/CTAF (uncontrolled field handling, self-announce).
- **#39** — FSS briefings (gravity briefing, NOTAMs, TFRs).

**Key files touched:**
- `sidecar/main.py` (SimBrief API integration, airspace listening, FSS integration).
- `sidecar/airport_picture.py` (airspace schema, CIFP extension).
- `sidecar/parser_code.py`, `parser_ai.py` (OpenAIP/NASR parsing, if local cache).
- `sidecar/phraseology.py` (class-appropriate phrasing, UNICOM templates, FSS briefing format).
- `addon/addon-main.nas` (airspace warnings UI, flight-plan entry).
- `tests/` (airspace containment logic, airspace bust detection, class-appropriate phrasing).

**Dependencies:** Phase 0 (core stability), Phase 7 (IFR infrastructure for flight-plan integration).

**Effort:** XL (multiple external integrations; requires API keys, data formats).

---

### Phase 9 — Gamification & Training

**Goal:** Make learning fun: guided practice, scenario builder, score tracking, career progression. Educational value without compromising realism.

**Exit criteria / definition of done:**
- Phraseology coach: highlight expected formats, grade readbacks, offer corrections (if Phase 5 STT complete).
- Scenario generator: seed random traffic patterns, weather, equipment failures; replay for practice.
- Career mode: track statistics (flights, landings, incidents, violations), progression over sessions.
- Kneeboard: auto-display ATIS, wind, active runways, aircraft type checklists.
- Integration test: run scenario, grade performance, career stats persist.

**Delivered ideas:**
- **#33** — Phraseology coach + readback grading (training mode, Whisper grading if available).
- **#34** — Scenario generator (random seed, reproducible for practice).
- **#35** — Career mode/scoring (statistics, progression, achievements).
- **#36** — Auto-kneeboard (ATIS, wind, runways, checklists, on-screen).

**Key files touched:**
- `sidecar/main.py` (scenario seed, career stats tracking, kneeboard publishing).
- `sidecar/phraseology.py` (coach templates, readback format definitions).
- `addon/addon-main.nas` (kneeboard UI, career UI).
- `tests/` (scenario reproducibility, readback grading logic, career stats persistence).

**Dependencies:** Phase 0 (core stability), Phase 4 (session memory for stats), Phase 5 (STT for readback grading).

**Effort:** M (mostly UI + data tracking; reuses existing phraseology).

---

### Phase 10 — Wild Cards / Stretch + Cross-Cutting Architecture

**Goal:** Advanced features, multi-language support, multiplayer, and foundational cross-cutting systems for long-term sustainability.

**Exit criteria / definition of done:**
- Multiplayer ATC: multiple players control different positions at one airport (very high effort; coordinate via shared property tree or external backend).
- Multi-language ATC: ATC and phraseology in Spanish, French, German, Mandarin (model-dependent; Gemini supports).
- Regional phraseology packs: regional variations (UK airspace style, Australian, etc.).
- World-state blackboard (architecture): shared context for all modules (traffic, weather, airspace, config).
- Output validation guardrail (architecture): LLM output checker, catches unsafe/incorrect clearances before playback.
- Weather deviation/PIREPs: receive SIGMET, adjust routing, request deviations.
- Convective avoidance: detect radar echoes (FG weather plugin), route around, real-time diversions.
- Integration test (per feature): language selection works, phraseology is correct, multiplayer positions sync.

**Delivered ideas:**
- **#41** — Multiplayer ATC (coordinate positions, shared state).
- **#42** — Multi-language ATC (switchable language, Gemini prompt variation).
- **#4** — Regional phraseology packs (regional variation, community extensions).
- **#46** — World-state blackboard (shared context architecture).
- **#49** — Output validation guardrail (safety checker on clearances).
- **#26** — Weather deviation/windshear/PIREPs/convective (weather integration, adaptive routing).

**Key files touched:**
- `sidecar/main.py` (language selection, weather integration, validation pipeline).
- `sidecar/gemini_client.py` (multi-language prompts, validation model).
- `sidecar/phraseology.py` (regional variants, phrase packs as data).
- `addon/addon-main.nas` (language selector, weather display).
- `tests/` (language correctness, validation accuracy, weather routing).

**Dependencies:** All prior phases (these are extensions on mature foundation).

**Effort:** XL (multiplayer & architecture refactoring are very large; others moderate).

---

## Idea → Phase Index

| Idea # | Title | Phase | Status |
|--------|-------|-------|--------|
| #1 | Gate-to-gate chain | 7 | ⚪ Future |
| #2 | Personality engine | 4 | ⚪ Future |
| #3 | Mood/fatigue drift | 4 | ⚪ Future |
| #4 | Regional phraseology packs | 10 | ⚪ Stretch |
| #5 | Relief handoff | 4 | ⚪ Future |
| #6 | Navaid integration (VOR/NDB/DME/ILS) | 7 | ⚪ Future |
| #7 | Airways/direct-to/DME arcs | 7 | ⚪ Future |
| #8 | SIDs/STARs/approaches (CIFP) | 7–8 | ⚪ Future |
| #9 | Holding patterns | 7 | ⚪ Future |
| #10 | Full IFR clearance (CRAFT format) | 7 | ⚪ Future |
| #11 | Airspace class entry (OpenAIP/FAA NASR) | 8 | ⚪ Future |
| #12 | Special-use airspace | 8 | ⚪ Future |
| #13 | Airspace bust/Brasher warning | 8 | ⚪ Future |
| #14 | Arrival clearance | 7 | ⚪ Future |
| #15 | MAYDAY/PAN-PAN emergencies | 3 | ⚪ Future |
| #16 | Squawk 7500/7600/7700 reactions | 3 | ⚪ Future |
| #17 | Abnormal ops (min-fuel/diversion/go-around/gear) | 3 | ⚪ Future |
| #18 | Gear fly-by | 3 | ⚪ Future |
| #19 | Traffic sequencing | 6 | ⚪ Future |
| #20 | Wake turbulence | 6 | ⚪ Future |
| #21 | LAHSO/intersection departures | 6 | ⚪ Future |
| #22 | Go-around runway occupied | 3 | ⚪ Future |
| #23 | Ambient frequency chatter | 6 | ⚪ Future |
| #24 | Wind-based runway auto-selection | — | ✅ Done |
| #25 | METAR fetch (core) | — | ✅ Done |
| #26 | Weather deviation/windshear/PIREPs/convective | 10 | ⚪ Stretch |
| #27 | Whisper STT / Piper TTS | 5 | ⚪ Future |
| #28 | Stepped-on transmissions | 5 | ⚪ Future |
| #29 | Radio static/squelch | 5 | ⚪ Future |
| #30 | Readback enforcement | 5 | ⚪ Future |
| #31 | PTT/joystick | 5 | ⚪ Future |
| #32 | Student vs checkride modes | 4 | ⚪ Future |
| #33 | Phraseology coach + readback grading | 9 | ⚪ Future |
| #34 | Scenario generator | 9 | ⚪ Future |
| #35 | Career mode/scoring | 9 | ⚪ Future |
| #36 | Auto-kneeboard | 9 | ⚪ Future |
| #37 | SimBrief import | 8 | ⚪ Future |
| #38 | UNICOM/CTAF uncontrolled fields | 8 | ⚪ Future |
| #39 | FSS briefings/flight plans | 8 | ⚪ Future |
| #40 | Guard 121.5 monitoring | 3 | ⚪ Future |
| #41 | Multiplayer ATC | 10 | ⚪ Stretch |
| #42 | Multi-language ATC | 10 | ⚪ Stretch |
| #43 | LLM controller-of-the-day backstories | 4 | ⚪ Future |
| #44 | Flow control/ground stops/EDCT | 7 | ⚪ Future |
| #45 | Quiet-night easter eggs | 4 | ⚪ Future |
| #46 | World-state blackboard (architecture) | 10 | ⚪ Stretch |
| #47 | Per-position controller state machine (architecture) | 7 | ⚪ Future |
| #48 | Session memory/continuity | 4 | ⚪ Future |
| #49 | Output validation guardrail (architecture) | 10 | ⚪ Stretch |
| #50 | Mode A active/inactive runway config | 2 | ⚪ Future |
| #51 | Mode B live traffic sequencing | 2 | ⚪ Future |
| #52 | Config panel UI | 2 | ⚪ Future |
| #53 | run-mac.command hardening | 0 | 🟡 Committed |
| #54 | Sidecar heartbeat + connection status | 0 | 🟡 Committed |
| #55 | Request watchdog/never-hang | 0 | 🟡 Committed |
| #56 | Keybinding/menu→request() unification (callsign auto-fill) | 0 | 🟡 Committed |
| #57 | Sidecar always-reply on exception | 0 | 🟡 Committed |
| #58 | Telnet bridge banner/prompt hardening | 0 | 🟡 Committed |
| #59 | --selftest flag | 0 | 🟡 Committed |
| #60 | Airport-change listener re-publish | 0 | 🟡 Committed |
| #61 | Panel redesign (Stage 1) | 1 | ⚪ Future |
| #62 | Arrival/approach request types (Stage 2) | 1 | ⚪ Future |

**Tier 1b bug fixes (scattered across Phase 0):**
- `addon.version.str()` fix, `append_log()` growth cap, `publish_airport_data()` nil guard, cancel-binding status reset, deterministic runway order, double-listener-on-reload, `fg_bridge` mid-read `BridgeError`, `cache.py` WAL+`OperationalError`, runway tie-break determinism, Gemini non-401 `ClientError` leak, groundnet XML pre-validation, `.env.example` population, METAR MPS units, `CACHE_DB_PATH` relative path, `replay.py` docstring, replay integration test gap.

---

## Explicitly Deferred / Out of Scope

**B5: `AI_TAXIWAY_LABELS` off — policy constraint, not on roadmap.**
- Taxiway naming requires authoritative real-world data sources (OpenStreetMap, airport operators, FAA).
- Gemini-fabricated names are unreliable and unsafe for training.
- **Current decision:** off by default (`AI_TAXIWAY_LABELS` flag); correct behavior.
- **Future path:** Phase 8 groundings may eventually unlock safe automated labeling, but not committed.

**B6: Commanding the whole AI fleet — architectural constraint, permanently out of scope.**
- FlightGear does not expose a write API for `/ai/models/` properties from add-on scripts.
- Mode A (user controls active runways, ATC directs user) and Mode B (read-only traffic awareness, user-centric sequencing) route around this constraint.
- "Take over whole AI fleet" is **not** a goal; the add-on focuses on user as pilot, ATC as advisor/instruction giver.

---

## Summary

This roadmap delivers the FlightGear AI ATC add-on as 10 phased increments:

1. **Phase 0 (now):** Unblock in-sim testing (FG2026 fix, telnet, exception recovery, watchdog).
2. **Phases 1–2 (next ~2 months):** Panel redesign + request framework (all flight phases), Mode A/B traffic config.
3. **Phase 3 (tactical):** Emergencies & abnormals (quick win, high realism).
4. **Phase 4 (narrative):** Personality, mood, session memory (ATC feels alive).
5. **Phase 5 (audio):** Piper TTS, Whisper STT, radio realism (full voice loop).
6. **Phase 6 (world):** Multi-aircraft traffic sequencing, wake turbulence, chatter (busy airport feel).
7. **Phase 7 (IFR):** Full state machine, navaids, airways, SIDs/STARs, gate-to-gate (complete flight coverage).
8. **Phase 8 (grounding):** SimBrief, airspace, FSS, real-world data integrations (maximum accuracy).
9. **Phase 9 (training):** Phraseology coach, scenarios, career mode, kneeboard (educational + fun).
10. **Phase 10 (stretch):** Multiplayer, multi-language, architecture foundations (long-term flexibility).

**Key dependency ordering:**
- Phase 0 is blockers & robustness (must ship first).
- Phases 1–2 build cohesive UI + baseline traffic awareness.
- Phase 3 (emergencies) can land early once Phase 1 request framework is solid.
- Phase 4 (personality) layers on top of session log (cheap, high ROI).
- Phases 5–6 deepen realism (audio + multi-aircraft) and require Phase 0–2 foundation.
- Phase 7 (IFR) is the "big one" — requires state machine architecture.
- Phases 8–10 are integrations & extensions on a mature foundation.

All 62 ideas mapped; nothing dropped.
