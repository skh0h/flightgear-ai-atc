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
