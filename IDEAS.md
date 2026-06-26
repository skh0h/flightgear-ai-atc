# FlightGear AI ATC — IDEAS

> Living brainstorm pool. Unfiltered on purpose. Feeds the V2/V3 roadmaps — not a commitment.
> Legend: 🔥 = standout/high-impact · _(note)_ = data/feasibility flag.
> Related: `V's/V1.md` (build plan) · `V's/V2.md` (vision roadmap).

## 🗼 The controllers themselves
- Full gate-to-gate position chain: Clearance Delivery → Ground → Tower → Departure → Center → Approach → Tower → Ground, with real handoffs + frequency changes
- Personality engine: bored midnight controller, rapid-fire NY approach, chill rural tower, by-the-book military
- 🔥 Controller mood/fatigue drift over a long session — gets terser when busy
- Regional phraseology packs: FAA / ICAO / UK CAA / Aussie CASA
- 🔥 "Controller goes on break" — relief controller takes over with a position-relief briefing

## 📡 Navaids & IFR routing (the VOR family)
- VOR / NDB / DME / ILS, fixes, intersections _(already in FG navdb via navinfo()/findNavaidsWithinRange())_
- Airways (Victor/Jet), direct-to, radial intercepts, DME arcs
- SIDs / STARs, ILS / RNAV / visual / circling approaches _(procedural data — partly via X-Plane CIFP)_
- Holding patterns (published + ATC-assigned) with EFC times
- Full IFR clearance in CRAFT format; pop-up IFR clearances airborne; "climb via the SID"

## 🛑 Airspace
- Class A/B/C/D/E/G with entry clearances; the Class B "wedding cake" shelves
- Special-use: MOAs, restricted, prohibited, TFRs, ADIZ _(boundary polygons NOT in FG core navdata — pull from OpenAIP / FAA NASR)_
- 🔥 Airspace bust → "possible pilot deviation, advise you contact this number" (Brasher warning)
- VFR flight following / traffic advisories; practice areas; transition altitude

## 🚨 Emergencies & abnormals (LLM gold)
- MAYDAY / PAN-PAN; engine fire, medical, fuel, electrical, pressurization
- Souls-on-board + fuel-remaining queries; priority handling; clear traffic; deterministic vector to nearest field _(findAirportsWithinRange())_
- 🔥 Squawk reactions: 7500 hijack / 7600 lost comms / 7700 emergency — behavior flips on transponder code
- 🔥 NORDO / lost comms → light-gun signals from the tower
- Minimum-fuel declaration, emergency descent, diversions, go-arounds, gear fly-by for visual check

## 🌍 The living world (the big immersion gap)
- Sequencing behind AI traffic; spacing & speed control ("reduce 180, no delay")
- Wake turbulence separation + "caution wake turbulence"
- LUAW (line up and wait), intersection departures, LAHSO
- Go-around because someone's still on the runway
- 🔥 Ambient chatter — other (AI-generated) aircraft talking on your frequency so it feels alive
- Wind-based runway assignment

## 🌦️ Weather
- Live METAR → ATIS + altimeter; runway pick by wind _(aviationweather.gov)_
- "Deviate left for weather, approved"; windshear/microburst alerts; low-vis CAT II/III + RVR
- PIREPs, ATIS info-code updates, convective reroutes

## 🎙️ Realism craft (the secret sauce)
- Whisper STT in / Piper TTS out; multiple distinct controller voices
- 🔥 Stepped-on transmissions — two stations key up at once = garble + "last station, say again"
- Radio static/squelch, "stand by," frequency congestion, blocked freq
- Readback enforcement + correction; phonetic numbers ("niner," "tree")
- Real PTT key/joystick button integration

## 🎓 Modes & gamification
- Student-pilot mode (patient, explains) vs. checkride/exam mode (throws scenarios)
- 🔥 "What do I say?" phraseology coach + live readback grading
- Scenario generator: "KSFO at rush hour," random emergency, mid-approach runway change
- Career mode: fly a schedule, earn ratings; scoring for clean readbacks / no busts
- Auto-kneeboard (clearance + ATIS + freqs); interaction logbook / transcript export

## 🌐 Integration extras
- SimBrief flight-plan import → "cleared as filed" actually means something
- 🔥 UNICOM/CTAF at uncontrolled fields — self-announce, AI traffic responds
- Flight Service Station: briefings, open/close flight plans
- Guard (121.5) monitoring + emergency broadcasts
- Multiplayer: AI ATC controlling a whole server (the fgatc model), or human+AI controller mix

## 🃏 Wild cards
- 🔥 Multi-language ATC — fly into France, get French-accented English + occasional French exchanges with AI traffic
- LLM-generated controllers with little backstories ("controller of the day")
- 🔥 Flow control / ground stops / EDCT times — staffing-shortage realism
- Quiet-night easter eggs (controller cracks a joke at 0300)

## 🧠 Cross-cutting architecture ideas
- World-state "blackboard" the LLM *reads but never writes* (positions, weather, traffic, assigned clearances) — the context-injection layer
- Per-position controller state machine; LLM only renders surface language
- Session memory/continuity — controller remembers your callsign and prior instructions
- Output validation guardrail — LLM phrasing checked against rules before it's spoken (e.g., assigned altitude ≥ MSA, runway exists and is active)

## 📚 Recurring data sources
- FlightGear navdb (Nasal): VOR/NDB/ILS/fixes/airways — VORs, navaids, nearest airport
- OpenAIP / FAA NASR: airspace boundary polygons (not in FG core)
- aviationweather.gov: live METAR for ATIS/altimeter
- SimBrief: flight-plan import
- X-Plane CIFP: SIDs/STARs/approaches (procedural)

---

## ✅ Committed Spec: Airport Configuration & Traffic Sequencing

**Why:** Turns the add-on from an ATC *narrator* into an ATC that *runs the airport* — the single biggest differentiator vs. Red Griffin. Delivered as one "Airport Configuration" panel with a **mode toggle**.

### Mode A — Controller (Solo)
- User opens the config panel and marks runways **active / inactive**.
- No AI traffic involved. Clearances issued against the user's chosen active runway(s).
- Wind-based auto-select still runs, but **only among active runways**.
- Feasibility: **HIGH** — fully buildable today, no AI dependency.

### Mode B — Blend In (Live Traffic)
- Add-on **reads** surrounding AI / multiplayer aircraft and **sequences the *user*** into the flow: *"You're number 3, follow the 737 on a 4-mile final, extend your downwind."*
- The AI planes keep running their own logic — **we never command them**, only the human pilot (who actually obeys). This is what makes the feature tractable.
- Feasibility: **MEDIUM** — read + sequence is feasible; depends on traffic being present.

### Why this two-mode split is the right design
The only blocked capability in FlightGear is *controlling* AI aircraft (no property exists to route an AI plane to a runway). Both modes route around it — Mode A involves no AI at all; Mode B reads AI but issues instructions only to the user. The "ATC actively vectors the whole AI fleet" version stays on the backlog.

### Feasibility summary (codebase recon, 2026-06-24)

| Piece | Verdict | Notes |
|---|---|---|
| Active/inactive runway state | HIGH | Add `active: bool` to `Runway`; filter before wind-scoring |
| Config screen UI | HIGH | Extend existing PropertyList dialog `addon/gui/dialogs/ai-atc.xml` |
| Reading AI positions | MEDIUM | Poll `/ai/models/` over existing telnet bridge, or aggregate in Nasal |
| Sequencing logic | MEDIUM | Distance/time-to-threshold; snap planes to existing groundnet graph |
| Controlling AI planes | LOW / BLOCKED | No FG property to route an AI aircraft; out of scope by design |

### Reuses (no new subsystems)
- `sidecar/runway_selection.py` — wind-based `select_departure_runway()` (filter to active)
- `sidecar/airport_picture.py` — `Runway` model gains an `active: bool` field
- `sidecar/routing.py` / `parser_code.py` — groundnet graph for snapping AI positions to the field
- `sidecar/phraseology.py` — online + offline clearance text (new sequencing templates/prompts)
- `sidecar/fg_bridge.py` — same telnet/HTTP bridge, pointed at `/ai/models/`
- `addon/gui/dialogs/ai-atc.xml` + `addon/addon-main.nas` — extend the existing dialog + mailbox

### Sketch of moving parts
- Data model: `Runway.active: bool = True`.
- Mailbox (new properties): `/ai-atc/config/mode` (`controller` | `blend_in`), `/ai-atc/config/runway[N]/active`; for Mode B, aggregated `/ai-atc/ai-traffic/aircraft[N]/{callsign,position,heading,dist_to_threshold,seq_position}`.
- Read path (Mode B): enumerate `/ai/models/aircraft[N]` and `/ai/models/multiplayer[N]` → lat/lon/alt/heading/speed/callsign → snap to nearest groundnet node/segment → compute sequence.
- UI: add a mode toggle + per-runway active checkbox list to `ai-atc.xml`; for Mode B, show the live landing queue in the transcript/status area.

### Open questions (decide before building)
1. Traffic source for Mode B: FlightGear built-in AI Traffic schedules, live multiplayer, or spawn our own controllable traffic?
2. Scope of "blend in": arrivals only (landing sequence) first, or also ground + departures?
3. Output channel: text-in-dialog only (v1 style) vs. spoken sequencing via the TTS path.

### Suggested phasing (non-binding — build order deferred)
1. Mode A: config screen + `active` flag + filtered runway selection.
2. Mode B read-only: enumerate `/ai/models/`, snap to groundnet, **display** a live landing queue.
3. Mode B sequencing: compute the user's slot + phraseology ("number 3, follow the 737").
