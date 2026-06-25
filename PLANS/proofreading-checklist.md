# Implementation Plan Proofreading Checklist

**Purpose:** This checklist is used by human reviewers to carefully proofread the implementation plan document for correctness, completeness, consistency, clarity, and feasibility.

**How to use:**
1. Read through each section of the plan alongside this checklist.
2. Check off each item as you verify it against the actual plan text.
3. Mark issues with a comment (e.g., `- [ ] Item #X – **Issue:** {description}`) if found.
4. Use specific line/section references (e.g., "Phase 3, taxi routing section").

**Reviewer name:** _________________  
**Date:** _________________  
**Reviewed version:** _________________  

---

## Structural & Formatting

- [ ] **Heading hierarchy:** Plan follows consistent heading levels (# for main sections, ## for subsections, ### for details)
- [ ] **Section ordering:** Sections are in logical order (Context → Decisions → Architecture → Phases → Files → Reuse → Verification → Future)
- [ ] **Code blocks:** All code blocks, diagrams, and schema examples have proper language tags or are clearly identified (e.g., ```` ``` ````)
- [ ] **Lists and indentation:** Bulleted and numbered lists are consistently formatted and properly indented
- [ ] **Table of contents:** If present, accurately reflects actual section headings and page locations
- [ ] **Markdown syntax:** No malformed Markdown (e.g., mismatched backticks, unclosed brackets, inconsistent emphasis)
- [ ] **Spacing:** Consistent spacing between sections; no orphaned headings or irregular paragraph breaks
- [ ] **Architecture diagram:** Diagram is present and clearly labeled; ASCII art is readable and properly formatted

---

## Technical Accuracy

### File Paths & Project Structure

- [ ] **Root directory:** Plan consistently refers to `~/Documents/FlightGear Add-on` as the project root
- [ ] **Sidecar directory:** All Python sidecar files are under `sidecar/` (main.py, fg_bridge.py, gemini_client.py, etc.)
- [ ] **Addon directory:** All Nasal/XML add-on files are under `addon/` with correct filenames:
  - [ ] `addon-metadata.xml`
  - [ ] `addon-main.nas`
  - [ ] `addon-menubar-items.xml`
  - [ ] `addon-config.xml`
  - [ ] `gui/dialogs/ai-atc.xml`
- [ ] **Tests directory:** `tests/` directory is specified for pytest-based tests
- [ ] **Fixtures directory:** `fixtures/` directory mentioned for sample `groundnet.xml` (KSFO) and airportinfo
- [ ] **Docs directory:** `docs/ARCHITECTURE.md` is specified as part of Phase 0 deliverables
- [ ] **Config files:** `.env.example`, `.gitignore`, `README.md` are all listed at the root level
- [ ] **requirements.txt:** Located at root of sidecar project (not nested)

### Core Module Names & Functions

- [ ] **Python modules match Phase descriptions:**
  - [ ] Phase 1: `config.py`, `gemini_client.py` mentioned
  - [ ] Phase 2: `parser_code.py`, `parser_ai.py`, `cache.py`, `airport_picture.py` mentioned
  - [ ] Phase 3: `routing.py`, `phraseology.py` mentioned
  - [ ] Phase 4: `fg_bridge.py`, `main.py`, `tts.py` mentioned
- [ ] **Function/method names are specific:** (e.g., "A\* taxi routing" in routing.py, "telnet property client" for fg_bridge.py)
- [ ] **FlightGear Nasal:** Add-on `main(addon)` and `unload(addon)` are mentioned as Red Griffin patterns to reuse
- [ ] **Property mailbox:** `/ai-atc/` path is consistently used throughout (request, response, response/text)

### APIs, Ports & Protocols

- [ ] **FlightGear telnet server:** Port is consistently specified as `5501` (not variable or hardcoded elsewhere)
- [ ] **FlightGear command-line flags:** `--addon=…/addon` and `--props=5501` are documented in Phase 5 (end-to-end verification)
- [ ] **Gemini API:** Model names specified as **"Gemini 2.5 Flash"** (for phraseology) and **"2.5 Pro"** (optional, for groundnet parse)
- [ ] **Google `google-genai` SDK:** Package name is correct (not `google-generativeai` or variant)
- [ ] **Environment variable:** `GEMINI_API_KEY` is the specified variable name for API key (in `.env`)
- [ ] **Property server protocol:** Telnet property protocol is mentioned for get/set/subscribe (Phase 4 verification)
- [ ] **macOS `say` command:** Specified as the TTS mechanism; noted as built-in (no extra install)

### Config Keys & Data Models

- [ ] **Airport picture schema fields are all present and correctly named:**
  - [ ] `icao` — airport identifier
  - [ ] `source` — either `"ai"` or `"code"`
  - [ ] `generated_at` — timestamp
  - [ ] `groundnet_hash` — hash of groundnet.xml
  - [ ] `parking` — list with fields: `id, name, type, lat, lon, heading`
  - [ ] `nodes` — list with fields: `index, lat, lon, on_runway, hold_point`
  - [ ] `segments` — list with fields: `begin, end, name, pushback`
  - [ ] `runways` — list with fields: `id, thr_lat, thr_lon, heading, length, ils_freq, entry_nodes`
  - [ ] `frequencies` — dict with keys: `ground, tower, atis, approach, departure, …`
  - [ ] `taxi_graph` — adjacency structure for pathfinding
- [ ] **groundnet.xml elements are correctly specified:**
  - [ ] `<parkingList><Parking …/>` for parking data
  - [ ] `<TaxiNodes><node index lat lon isOnRunway holdPointType/>` for nodes
  - [ ] `<TaxiWaySegments><arc begin end name isPushBackRoute/>` for segments
  - [ ] Taxiway names live on `<arc>` elements (not on nodes)
- [ ] **FlightGear standard properties mentioned** are verified as real properties:
  - [ ] `/position` — aircraft position
  - [ ] `/orientation` — aircraft heading/pitch/roll
  - [ ] `/velocities` — aircraft speed/climb rate
  - [ ] `/instrumentation/comm[0]/…` — COM radio frequency data
  - [ ] `/sim/presets/airport-id` — spawn airport ICAO
  - [ ] `/sim/sound/voices/atc` — optional toggle for suppressing FG default ATC sound (Phase 4)

### Dependencies & Versions

- [ ] **Python version:** Not explicitly stated; infer 3.8+ as reasonable assumption (note if unclear)
- [ ] **FlightGear version:** Explicitly specified as **2024.1.5** (macOS)
- [ ] **Red Griffin:** Mentioned as downloadable from **SourceForge**; version/release date not specified (acceptable, skeleton only)
- [ ] **requirements.txt packages:** Plan mentions `google-genai` and `python-dotenv`; no version pins specified (noted as "confirm at implementation time")
- [ ] **Note about Gemini API evolution:** Plan explicitly warns "confirm current `google-genai` package name and live model IDs against Google's official docs before pinning versions"

---

## Consistency

### Naming & Terminology

- [ ] **Component names consistent throughout:**
  - [ ] Nasal add-on / Nasal component (not "addon" alone; "add-on" used in title)
  - [ ] Python sidecar / sidecar (not "Python process" or "backend")
  - [ ] Airport picture / picture (not "airport model" or "data structure" inconsistently)
  - [ ] Taxi graph / graph (not "routing graph" or "taxiway graph" inconsistently)
- [ ] **Phases referred to consistently:** "Phase 0", "Phase 1", etc. (not "Step 0" or "Phase One")
- [ ] **FlightGear component:** "FlightGear" (not "Flight Gear" or "FG" without context)
- [ ] **File extension terminology:** `.xml`, `.nas`, `.py` used consistently (not "XML file" mixed with ".xml file")
- [ ] **Offline/online terminology:** "offline" and "online" used consistently (not "offline mode" vs "when online" inconsistently)
- [ ] **AI path vs code path:** Both terms used consistently throughout (AI path, code path, fallback path)

### Cross-Document References

- [ ] **Red Griffin mentioned consistently:** Used as reference/skeleton source (Phases 0, 2, 4, 5)
- [ ] **KSFO fixture:** Sample airport used consistently in Phase 2 and Phase 5 (same airport)
- [ ] **A\* algorithm:** Mentioned in Phase 3 (routing) and in taxi routing subsection of Architecture; terminology consistent
- [ ] **Gemini as decision:** Mentioned in Context, Architecture, and all relevant phases (Phase 1, 2, 3, 4); consistency of "Gemini" name (not "Google Gemini" alone, though that would be acceptable)

### Data Model Consistency

- [ ] **"picture" dataclass/schema:** Same structure referenced in Phase 2 (cache), Phase 3 (routing input), and Phase 4 (bridge output)
- [ ] **SQLite cache keying:** "ICAO + groundnet hash" used consistently (not "ICAO + hash" or "airport + version" inconsistently)
- [ ] **Offline detection mechanism:** "lightweight connectivity probe + exception handling" mentioned consistently (not sometimes "network check" vs "exception handler")

---

## Completeness

### Phase Deliverables

- [ ] **Phase 0 deliverables clear:**
  - [ ] Fresh branch `main` created
  - [ ] Project layout defined (sidecar/, addon/, tests/, fixtures/, docs/)
  - [ ] `.gitignore` + `README.md` + `docs/ARCHITECTURE.md` created
  - [ ] Private GitHub repo `skh0h/flightgear-ai-atc` created and pushed
- [ ] **Phase 1 deliverables clear:**
  - [ ] `venv` + `requirements.txt` created (lists `google-genai`, `python-dotenv`)
  - [ ] `config.py` (loads .env)
  - [ ] `gemini_client.py` (structured output + offline detection)
  - [ ] Logging setup defined (though minimal description)
  - [ ] Acceptance: "one structured Gemini call" smoke test
- [ ] **Phase 2 deliverables clear:**
  - [ ] Red Griffin download (reference)
  - [ ] Sample `groundnet.xml` fixture (KSFO) committed
  - [ ] `parser_code.py` (xml.etree + airportinfo)
  - [ ] `parser_ai.py` (Gemini → picture)
  - [ ] `cache.py` (SQLite, ICAO + hash keyed)
  - [ ] `airport_picture.py` (dataclasses/schema)
  - [ ] Acceptance: "AI output cross-checked against code output" + unit tests on fixture
- [ ] **Phase 3 deliverables clear:**
  - [ ] `routing.py` (graph + A\*, gate→runway)
  - [ ] `phraseology.py` (Gemini online + templates offline)
  - [ ] Acceptance: unit tests for routing on the fixture
- [ ] **Phase 4 deliverables clear:**
  - [ ] `fg_bridge.py` (telnet props: get/set/subscribe)
  - [ ] `main.py` (event loop)
  - [ ] `tts.py` (macOS `say`, toggle for /sim/sound/voices/atc)
  - [ ] Nasal add-on files fully specified (metadata.xml, main.nas, menubar-items.xml, config.xml, gui/dialogs/ai-atc.xml)
- [ ] **Phase 5 deliverables clear:**
  - [ ] End-to-end test on FlightGear Mac
  - [ ] Launch FG with `--addon` + `--props=5501`
  - [ ] Start sidecar
  - [ ] Spawn at an airport (KSFO implied)
  - [ ] Request taxi via menu
  - [ ] Verify spoken/logged route names real taxiways and valid path
  - [ ] **Offline test:** disable network → cached picture + templates still work

### Dependencies Between Phases

- [ ] **Phase 0 prerequisite to all others:** Clear (repo setup first)
- [ ] **Phase 1 prerequisite to Phase 2:** Clear (venv + config needed before API calls)
- [ ] **Phase 2 prerequisite to Phase 3:** Clear (picture data structure and cache needed before routing)
- [ ] **Phase 3 prerequisite to Phase 4:** Clear (routing and phraseology must exist before bridge integration)
- [ ] **Phase 4 prerequisite to Phase 5:** Clear (all sidecar + add-on code must exist before end-to-end)
- [ ] **Test coverage stated for each phase:** Phase 1 (smoke test), Phase 2 (unit tests on fixture), Phase 3 (routing tests), Phase 5 (end-to-end)

### Missing Elements

- [ ] **Git authorship rule documented:** "commits authored by `skh0h <samuelkhoh84@gmail.com>`, no Co-Authored-By trailer" (stated in Confirmed Decisions)
- [ ] **Private repo requirement stated:** "private GitHub repo `skh0h/flightgear-ai-atc`" (Confirmed Decisions)
- [ ] **Caching strategy detailed:** SQLite with ICAO + groundnet hash keys (Architecture + Phase 2)
- [ ] **Offline fallback strategy detailed:** Cached picture + template phraseology (Architecture + Phases 2–3)
- [ ] **Error handling approach noted:** Exception handling in gemini_client.py for connectivity detection (Architecture + Phase 1)
- [ ] **No microphone/speech-to-text in v1:** Explicitly noted in Confirmed Decisions and Open Items

---

## Cross-References & Dependencies

### Internal Document References

- [ ] **Architecture diagram**: Positioned before phases; correctly shows FlightGear ↔ sidecar bridge via telnet property server
- [ ] **Airport picture schema**: Introduced in Architecture; schema fields consistent with Phase 2 parser descriptions
- [ ] **Reuse section references**: Points to "FlightGear telnet/property protocol" (used in Phase 4 `fg_bridge.py`)
- [ ] **Verification section**: Cleanly separates local testing (this Mac) vs in-sim testing (FlightGear Mac)

### Forward/Backward References

- [ ] **Red Griffin mentioned before detailed reuse:** First mentioned in Context (problem statement), then in Confirmed Decisions (skeleton reuse), then in Reuse section (specific Red Griffin elements), then in Phase 0/4 (download + reuse tasks)
- [ ] **Gemini models mentioned**: First in Context (when online), then in Architecture (Gemini 2.5 Flash + optionally Pro), then in Phase 1 (Gemini calls), reaffirmed in Phase 2 (groundnet parse). Single recommendation given but with note to "confirm at implementation time"
- [ ] **KSFO fixture**: First mentioned in Phase 2 (sample groundnet.xml), then referenced in Phase 5 (spawn at airport to test)
- [ ] **A\* algorithm**: First mentioned in Architecture (taxi routing subsection), then detailed in Phase 3. Consistent terminology and context
- [ ] **Offline mode**: Mentioned in Context (graceful degradation), Architecture (AI when possible, code when not), Phase 2 (cache design), Phase 3 (templates), Phase 5 (offline test)

### Ordering of Dependent Concepts

- [ ] **Picture schema introduced before parser phases:** Architecture defines schema; Phase 2 implements parsers that produce it ✓
- [ ] **Caching strategy before implementation:** Described in Architecture; Phase 2 implements `cache.py` based on that strategy ✓
- [ ] **Routing algorithm before implementation:** Described in Architecture (A\* on taxi graph); Phase 3 implements `routing.py` ✓
- [ ] **Bridge architecture before Nasal/sidecar code:** Architecture diagram and explanation before Phase 4 code ✓

---

## Clarity & Language

### Grammar & Spelling

- [ ] **Subject-verb agreement:** All sentences have clear subjects and proper verb forms
- [ ] **Pronoun ambiguity:** No unclear references (e.g., "it" referring to multiple antecedents)
- [ ] **Spelling:** No obvious misspellings; check specifically:
  - [ ] "Gemini" spelled consistently (not "Gemini" vs "gemini")
  - [ ] "FlightGear" capitalization consistent
  - [ ] "taxiway" (not "taxaway" or "taxi-way" inconsistently)
  - [ ] "groundnet" (not "ground-net")
  - [ ] "ICAO" (not "Icao" or "icao" inconsistently)
- [ ] **Punctuation:** Commas, periods, hyphens used correctly; no run-on sentences

### Acronyms & Jargon

- [ ] **ICAO** — Used without definition (acceptable; well-known in aviation); verify it's not defined elsewhere as different
- [ ] **Red Griffin** — Explained as "rule-based Nasal add-on" on first mention (Context section)
- [ ] **ATC** — Used in title and throughout; implicit "Air Traffic Control" (acceptable, standard)
- [ ] **COM** — Used in "instrumentation/comm[0]" (standard FlightGear nomenclature)
- [ ] **A\*** — Defined as "A-star" algorithm in Taxi Routing subsection (good clarity)
- [ ] **TTS** — Used in "voice output via macOS `say`" section (mentioned but acronym not spelled out; context clear)
- [ ] **SIDs/STARs** — Used in "Open Items" (Standard Instrument Departures/Arrivals); defined as such or clear from context? (Acceptable for aviation audience; if unclear, should be expanded)
- [ ] **ILS** — Appears as `ils_freq` in picture schema (Instrument Landing System; acceptable in aviation context)

### Undefined Concepts

- [ ] **"Mailbox"** concept: Defined as "/ai-atc/ property mailbox" (Architecture), then used as "sets /ai-atc/response/text" — clear ✓
- [ ] **"Structured output"** (Gemini): Parenthetical note "(response_schema)" clarifies; acceptable for technical audience ✓
- [ ] **"Great-circle heuristic"** (A\*): Technical term; context ("nearest node to the gate") provides clarity
- [ ] **"Pushback route"**: Appears in groundnet.xml structure description; used without definition but context implies alternate taxi path (acceptable)

### Passive vs. Active Constructions

- [ ] **Goal statement:** "Build an AI-powered ATC add-on" (active, clear)
- [ ] **Architecture description:** Mix of active ("Nasal add-on…provides") and passive ("Airport pictures…are derived"); generally clear
- [ ] **Phase descriptions:** Active voice preferred (e.g., "Build graph from nodes+segments"); acceptable
- [ ] **Unclear responsibility:** Verify each phase says who does what (sidecar vs add-on vs user testing phase), not just what happens

---

## Feasibility & Logic

### Ordering & Sequencing

- [ ] **Phase 0 before Phase 1:** Setup must precede development ✓
- [ ] **Environment (Phase 1) before parsing (Phase 2):** venv + config must exist before Gemini calls ✓
- [ ] **Parsing before routing (Phase 2→3):** Data structure and caching must exist before routing builds on it ✓
- [ ] **Routing before bridge (Phase 3→4):** Routing logic must exist before sidecar integration ✓
- [ ] **All sidecar code before end-to-end (Phase 4→5):** Logical ✓
- [ ] **Offline detection mechanism (Phase 1) before offline testing (Phase 5):** Fallback code in place before testing ✓

### Contradictions

- [ ] **AI when possible, code when not:** Consistently applied:
  - [ ] Phase 2: Both parser_ai.py and parser_code.py created (parallel, not sequential) ✓
  - [ ] Phase 3: Both Gemini phraseology and templates mentioned ✓
  - [ ] Phase 4: Offline detection in gemini_client.py enables fallback ✓
- [ ] **No microphone in v1:** Confirmed in Decisions and reiterated in Open Items; consistent
- [ ] **Telnet bridge only:** Architecture specifies telnet (no other FG integration method mentioned); consistent
- [ ] **macOS `say` only:** No mention of fallback TTS or alternative; consistent (though future phases mention "pluggable to neural TTS later")

### Assumptions

- [ ] **FlightGear 2024.1.5 has telnet property server:** Assumed to be available (not explicitly verified in plan)
- [ ] **Sample `groundnet.xml` available for KSFO:** Assumed ("obtain a sample"); not addressed if unavailable or licensed
- [ ] **Red Griffin can be downloaded from SourceForge:** Assumed; GPL mentioned (v3), reuse constraints noted in Confirmed Decisions
- [ ] **macOS `say` command is sufficient quality:** Assumed; TTS fallback mentioned in future phases if not
- [ ] **Gemini API remains stable:** Plan explicitly warns "confirm at implementation time" for package names and model IDs

### Error Handling & Edge Cases

- [ ] **Offline mode explicitly tested:** Phase 5 offline test (disable network → cached picture + templates)
- [ ] **Connectivity detection mechanism:** "lightweight connectivity probe + exception handling" mentioned (Phase 1, Architecture)
- [ ] **Missing groundnet data:** Implied for some airports; plan notes "degrades to generic 'taxiway'/node-based directions" if taxiway names unavailable
- [ ] **Cross-checking AI output:** Phase 2 states "AI output cross-checked against code output" (sanity check)
- [ ] **No traffic awareness in v1:** Explicitly noted in Open Items (Red Griffin's biggest gap)

---

## Testing & Validation

### Phase-by-Phase Verification

- [ ] **Phase 0:** No explicit test stated (setup phase; git repo creation is the validation)
- [ ] **Phase 1:** 
  - [ ] "Smoke test: one structured Gemini call" — acceptance criterion clear
  - [ ] Does not specify what success looks like (valid JSON response expected? implicit)
- [ ] **Phase 2:**
  - [ ] "Unit tests on the fixture" — pytest mentioned
  - [ ] "AI output cross-checked against code output" — acceptance criterion clear
  - [ ] Tests cover: parser_code, cache (write/read/hash-invalidation), per Verification section
- [ ] **Phase 3:**
  - [ ] "Unit tests for routing on the fixture" — pytest
  - [ ] Acceptance: "gate→runway produces valid ordered taxiway list"
- [ ] **Phase 4:**
  - [ ] "Run sidecar against mock property server with canned aircraft state; confirm request produces response text and `say` invocation"
  - [ ] Acceptance: text response + TTS call observed
- [ ] **Phase 5:**
  - [ ] "Spawn at airport, request taxi via menu, confirm spoken + logged route names real taxiways and valid route to runway"
  - [ ] "Offline test: disable network → cached picture + templates still produce specific route"
  - [ ] Both in-sim validations clear

### Local vs. In-Sim Testing Separation

- [ ] **Local testing (this Mac):** Tests run without FlightGear (pytest, mock property server)
- [ ] **In-sim testing (FlightGear Mac):** User performs via GitHub sync + manual testing
- [ ] **Responsibilities clear:** Developer does local tests; user does in-sim validation (Phase 5)

### Success Criteria Measurability

- [ ] **Phase 1:** "Valid structured Gemini call returned" — measurable ✓
- [ ] **Phase 2:** "Parsers produce identical picture structures" / "cache retrieves correct data" — measurable ✓
- [ ] **Phase 3:** "Routing produces ordered taxiway list that reaches runway" — measurable ✓
- [ ] **Phase 4:** "Response text generated, `say` command invoked" — measurable ✓
- [ ] **Phase 5:** "Spoken instructions name real taxiways; route is valid; offline mode works" — measurable ✓

### Test Coverage

- [ ] **Gemini calls:** Mocked in tests except one live smoke test (gated by `GEMINI_API_KEY`)
- [ ] **Parser coverage:** Both code and AI parsers tested against KSFO fixture
- [ ] **Cache coverage:** Write/read/hash-invalidation mentioned
- [ ] **Routing coverage:** Gate→runway on fixture
- [ ] **Phraseology coverage:** Templates mentioned for offline (unit tests implicit)
- [ ] **Bridge coverage:** Mock property server with canned aircraft state
- [ ] **End-to-end coverage:** Phase 5 in-sim testing

---

## Technical Depth & Details

### Architecture Decisions Justified

- [ ] **Why two components (Nasal + Python)?** 
  - [ ] Nasal can't reach groundnet data in-process (Context mentions Red Griffin blocked here)
  - [ ] Python sidecar does the work; thin Nasal just provides UI/bridge
  - [ ] Justified ✓
- [ ] **Why Gemini + code fallback?**
  - [ ] "AI when possible, code when not" design principle stated
  - [ ] Offline resilience requirement implicit
  - [ ] Justified ✓
- [ ] **Why A\* routing?**
  - [ ] Great-circle heuristic appropriate for pathfinding on taxi graphs
  - [ ] Mentioned as chosen algorithm but not explicitly justified (acceptable for technical audience)
- [ ] **Why SQLite cache?**
  - [ ] Keyed by ICAO + groundnet hash; persists offline
  - [ ] Not explicitly justified, but design is clear ✓
- [ ] **Why macOS `say` for TTS?**
  - [ ] Built-in (no extra install)
  - [ ] Better quality than FlightGear Flite (optional, if compiled)
  - [ ] Pluggable for neural TTS later (mentioned)
  - [ ] Justified ✓

### Integration Points Detailed

- [ ] **FlightGear ↔ Sidecar bridge:**
  - [ ] Telnet on localhost:5501 ✓
  - [ ] Properties subscribed/monitored: `/ai-atc/request`, `/ai-atc/response/text`, `/position`, `/orientation`, etc. ✓
  - [ ] Direction of data flow clear (diagram shows this) ✓
- [ ] **Sidecar ↔ Gemini:**
  - [ ] google-genai SDK ✓
  - [ ] Structured output via response_schema ✓
  - [ ] API key from environment ✓
- [ ] **Sidecar ↔ Cache:**
  - [ ] SQLite, keyed by ICAO + groundnet hash ✓
  - [ ] Read before online call; write after parsing ✓
- [ ] **Sidecar ↔ TTS:**
  - [ ] macOS `say` command ✓
  - [ ] Toggleable via `/sim/sound/voices/atc` property (Phase 4) ✓

---

## References & Reusable Components

### Red Griffin Reuse Clarity

- [ ] **What to reuse:** "skeleton" only — `addon-main.nas` shape, menu wiring, dialog XML conventions (explicitly stated)
- [ ] **What NOT to reuse:** Hardcoded phraseology, lack of taxi routing, no traffic awareness (implied; new ATC logic will replace)
- [ ] **Where to get it:** SourceForge download (URL not provided, but project name clear)
- [ ] **License compliance:** GPLv3 mentioned; reuse of skeleton respected (new code is independent)

### FlightGear Built-in Components

- [ ] **Nasal built-ins:** `setlistener`, `maketimer`, `props`, `airportinfo()`, `.comms()`, `.runway()` listed (reference; most logic in sidecar) ✓
- [ ] **Standard properties:** `/position`, `/orientation`, `/velocities`, `/instrumentation/comm[0]/…`, `/sim/presets/airport-id` listed ✓
- [ ] **Property protocol:** Telnet get/set/subscribe for `fg_bridge.py` ✓

### External Data Sources

- [ ] **groundnet.xml:** Format specified (Parking, TaxiNodes, TaxiWaySegments elements); source not specified (assumed comes with airport data in FG or Red Griffin)
- [ ] **airportinfo:** FlightGear built-in function mentioned (Phase 2); no version/format details (acceptable, standard API)

---

## Final Consistency & Completeness Checks

- [ ] **All file names mentioned in "Critical files to create" are addressed in phases:** 
  - [ ] main.py, fg_bridge.py, gemini_client.py, airport_picture.py, parser_code.py, parser_ai.py, routing.py, phraseology.py, cache.py, tts.py, config.py in sidecar/ ✓
  - [ ] addon-metadata.xml, addon-main.nas, addon-menubar-items.xml, addon-config.xml, gui/dialogs/ai-atc.xml in addon/ ✓
  - [ ] requirements.txt, .env.example, .gitignore, README.md in root ✓
  - [ ] docs/ARCHITECTURE.md in docs/ ✓
- [ ] **All phases reference real files/deliverables:** No loose ends or undefined modules ✓
- [ ] **Dates/timelines:** No specific dates promised (appropriately open-ended for a plan)
- [ ] **Success criteria for each phase stated:** All phases have clear acceptance conditions ✓
- [ ] **Known limitations acknowledged:** Future phases (traffic awareness, neural TTS, SIDs/STARs, speech-to-text) listed in Open Items ✓
- [ ] **User/developer responsibilities clear:** 
  - [ ] Developer: Phases 0–4, local testing
  - [ ] User: Phase 5, in-sim testing via GitHub sync ✓

---

## Additional Observations

- [ ] **Plan assumes 2 Macs:** Implied by "develop on this Mac", "FlightGear on other Mac", "sync via GitHub"; could be stated more explicitly if needed
- [ ] **Git authorship compliance:** User's memory specifies `skh0h` as author, no Co-Authored-By; plan matches this ✓
- [ ] **API key management:** `.env.example` template + `.gitignore` strategy for GEMINI_API_KEY; `.env` not committed (correct) ✓
- [ ] **Offline graceful degradation:** Clear design philosophy applied throughout (parser, phraseology, testing)
- [ ] **KSFO fixture commitment:** Plan to commit sample groundnet.xml to repo (for reproducible tests); acceptable for test fixture
- [ ] **Gemini API evolution warning:** Explicit note at implementation time to verify package names and model IDs; good risk mitigation ✓

---

**End of Checklist**

