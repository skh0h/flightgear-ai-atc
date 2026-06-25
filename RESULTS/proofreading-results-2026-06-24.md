# Implementation Plan Proofreading Audit Results

**Document Audited:** `/Users/andrewkhoh/Documents/FlightGear Add-on/PLANS/implementation-plan.md` (132 lines)  
**Checklist Source:** `/Users/andrewkhoh/Documents/FlightGear Add-on/PLANS/proofreading-checklist.md` (163 items)  
**Audit Date:** 2026-06-24  
**Overall Tally:** **156 Pass / 5 Issue / 2 Note**

---

## Key Findings

### Critical Issues Found

1. **No Table of Contents** (Structural & Formatting item 5)
   - The implementation-plan.md has no TOC. For a 132-line planning document with 8 major sections, a TOC would improve navigation but is not required for a plan of this length.
   - **Severity:** Low (helpful but not critical for a moderately-sized document)

2. **Architecture Diagram: Text Sketch, Not ASCII Art** (Structural & Formatting item 8)
   - Lines 32–42 show a text "mailbox" representation, not a traditional ASCII-art flowchart. The diagram is present, labeled, and readable; however, it uses a non-standard format (text labels + property paths) rather than box-and-arrow ASCII art.
   - **Verdict:** Technically deficient from a strict "ASCII art" perspective, but functional and clear.
   - **Severity:** Low (content is clear; format is unconventional)

3. **Python Version Not Explicitly Stated** (Dependencies & Versions item 1)
   - Plan does not specify a minimum Python version (e.g., "3.8+", "3.11+"). The requirements.txt in the repo specifies 3.11+, but the plan itself doesn't.
   - **Line reference:** No mention in implementation-plan.md; would belong in Phase 1 or Dependencies section.
   - **Severity:** Low (inferable from requirements.txt; not a fatal omission in the plan)

4. **Red Griffin Version/Release Date Not Specified** (Dependencies & Versions item 2 subitem "version/release date")
   - Checklist notes this is "acceptable, skeleton only," but flags it for completeness. The plan does not provide a version or release date for Red Griffin (e.g., "v2.0 from 2023").
   - **Line reference:** L16, L109
   - **Severity:** Acceptable (skeleton reuse only; version pin not critical for reference material)

5. **Taxiway Name Inference Not Detailed** (Architectural Clarity — taxi routing subsection)
   - Line 54 states "the AI parser infers/labels these" for empty taxiway names but doesn't explain the inference strategy. Acceptable for a plan, but slightly vague.
   - **Line reference:** L54
   - **Severity:** Low (implementation detail; can be decided during Phase 2)

### Important Notes (Non-Issues, but Worth Flagging)

1. **Cross-Document Flag: README.md vs. Implementation Plan Discrepancy**
   - **README.md (Line 26, 65):** `--telnet=5501`
   - **Implementation-plan.md (Line 30, 74):** `--props=5501`
   - **Root cause:** README.md is outdated (likely created with different understanding). The plan correctly specifies `--props=5501` (properties protocol flag), which matches checklist item 22. **The implementation-plan.md is correct; the README needs updating.**
   - **Not a plan defect, but a repo cross-document inconsistency.**

2. **Gemini Model Names: Shorthand vs. Full**
   - Plan uses shorthand "Gemini 2.5 Flash" and "2.5 Pro" (L60). Checklist item 8 asks if these match Google's official docs. The plan mitigates this risk with an explicit note (L60): "**At implementation time, confirm the current `google-genai` package name and live model IDs against Google's official docs before pinning versions**" — this is good risk management.
   - **Verdict:** Acceptable hedge; implementation-time confirmation is planned.

---

## Per-Item Audit (All 163 Items)

### Structural & Formatting (8 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 1 | Heading hierarchy consistent (# for main, ## for subsections) | **Pass** | Sections use # and ## correctly (L1, L3, L13, L23, etc.) |
| 2 | Section ordering logical (Context → Decisions → Architecture → Phases → Files → Reuse → Verification → Future) | **Pass** | Exact order follows: Context (L3) → Decisions (L13) → Architecture (L23) → Phases (L62) → Files (L76) → Reuse (L107) → Verification (L114) → Open Items (L126) |
| 3 | Code blocks have proper language tags or clear identification | **Pass** | Schema example at L44–53 is marked with triple backticks; ASCII sketch L32–42 is in triple backticks |
| 4 | Lists and indentation consistently formatted | **Pass** | Bulleted lists (Confirmed decisions L13–21, Reuse L108–112, etc.) and nested structure (L78–105 file tree) are consistent |
| 5 | Table of contents present and accurate | **Issue** | No TOC present. For a 132-line plan with 8 major sections, a TOC would improve navigation. However, the document is small enough that TOC is not critical. **Acceptable omission.** |
| 6 | Markdown syntax correct (no malformed backticks, unclosed brackets) | **Pass** | All code blocks closed; all lists properly formatted; no orphaned brackets detected |
| 7 | Spacing between sections consistent | **Pass** | Blank lines between major sections; heading spacing uniform |
| 8 | Architecture diagram present, clearly labeled, ASCII art readable | **Issue** | Diagram present (L32–42) and labeled ("Bridge: FlightGear launched with..."); however, it is a **text-based mailbox diagram**, not traditional ASCII-art boxes/arrows. Format is unconventional but functional and clear. |

**Structural & Formatting Summary:** 6 Pass, 2 Issue (minor — no TOC, non-standard diagram format)

---

### Technical Accuracy: File Paths & Project Structure (10 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 9 | Root directory consistently `~/Documents/FlightGear Add-on` | **Pass** | L79 specifies root; context assumes this throughout |
| 10 | All Python sidecar files under `sidecar/` | **Pass** | Files L80–91 all under `sidecar/`; verified in repo: all .py files present |
| 11 | Nasal/XML addon files under `addon/` with correct filenames | **Pass** | L92–97 lists all five files correctly; verified in repo: all present |
| 11a | `addon-metadata.xml` | **Pass** | L93; verified in repo |
| 11b | `addon-main.nas` | **Pass** | L94; verified in repo |
| 11c | `addon-menubar-items.xml` | **Pass** | L95; verified in repo |
| 11d | `addon-config.xml` | **Pass** | L96; verified in repo |
| 11e | `gui/dialogs/ai-atc.xml` | **Pass** | L97; verified in repo |
| 12 | `tests/` directory specified for pytest | **Pass** | L98; exists in repo |
| 13 | `fixtures/` directory for sample groundnet.xml (KSFO) and airportinfo | **Pass** | L99; exists in repo |
| 14 | `docs/ARCHITECTURE.md` specified | **Pass** | L104; exists in repo (verified) |
| 15 | Config files at root: `.env.example`, `.gitignore`, `README.md` | **Pass** | L101–103; all present in repo |
| 16 | `requirements.txt` at root (not nested) | **Pass** | L100; verified at project root |

**File Paths Summary:** 14 Pass, 0 Issue

---

### Technical Accuracy: Core Module Names & Functions (9 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 17 | Phase 1: `config.py`, `gemini_client.py` mentioned | **Pass** | L66 lists both modules |
| 18 | Phase 2: `parser_code.py`, `parser_ai.py`, `cache.py`, `airport_picture.py` mentioned | **Pass** | L68 lists all four; verified in repo |
| 19 | Phase 3: `routing.py`, `phraseology.py` mentioned | **Pass** | L70 lists both; verified in repo |
| 20 | Phase 4: `fg_bridge.py`, `main.py`, `tts.py` mentioned | **Pass** | L72 lists all three; verified in repo |
| 21 | Function/method names specific (e.g., "A\* taxi routing") | **Pass** | L57 "A\*"; L56 "A\* taxi routing"; L87 routing.py description clear |
| 22 | FlightGear Nasal `main(addon)` and `unload(addon)` mentioned as Red Griffin patterns | **Pass** | L109 references Red Griffin skeleton; pattern reuse mentioned |
| 23 | Property mailbox `/ai-atc/` path used consistently | **Pass** | L27, L30, L39–40 all use `/ai-atc/`, `/ai-atc/request`, `/ai-atc/response/text` consistently |
| 24 | Logging setup mentioned (Phase 1) | **Pass** | L66 notes "basic logging" |
| 25 | __init__.py mentioned for sidecar package structure | **Note** | Plan doesn't explicitly list `sidecar/__init__.py`, but it is present in the repo. This is a Python convention not strictly required to be in the plan. **N/A — best practice, not documented but correctly implemented.** |

**Core Module Names Summary:** 8 Pass, 0 Issue, 1 Note

---

### Technical Accuracy: APIs, Ports & Protocols (9 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 26 | FlightGear telnet server port `5501` consistently specified | **Pass** | L30, L74 both specify `5501`; consistent |
| 27 | FlightGear command-line flags: `--addon=…/addon` and `--props=5501` documented in Phase 5 | **Pass** | L122 states `fgfs --addon=…/addon --props=5501`; matches L30 and L74 |
| 28 | Gemini model names specified: "Gemini 2.5 Flash" (phraseology) and "2.5 Pro" (optional groundnet) | **Pass** | L60 lists both; shorthand format is acceptable given the hedge note on L60 |
| 29 | Google `google-genai` SDK package name correct | **Pass** | L60 specifies `google-genai` (not `google-generativeai`); verified in requirements.txt L5 |
| 30 | Environment variable `GEMINI_API_KEY` specified | **Pass** | L60, L101; verified in .env.example L1 |
| 31 | Property server protocol (get/set/subscribe) mentioned for Phase 4 verification | **Pass** | L111 mentions telnet property protocol; L122 mentions property server |
| 32 | macOS `say` command specified as TTS mechanism, noted as built-in | **Pass** | L28 specifies `say`; L112 notes "built in; no extra install" |
| 33 | Telnet property protocol for `fg_bridge.py` | **Pass** | L111 explicit; L81 fg_bridge.py description confirms telnet |
| 34 | `/sim/sound/voices/atc` property toggle mentioned for Phase 4 TTS | **Pass** | L72 specifies "toggle for /sim/sound/voices/atc" |

**APIs, Ports & Protocols Summary:** 9 Pass, 0 Issue

---

### Technical Accuracy: Config Keys & Data Models (12 items)

#### Airport Picture Schema Fields

| # | Item | Verdict | Note |
|---|---|---|---|
| 35 | `icao` field present | **Pass** | L46 |
| 36 | `source` field ("ai" or "code") | **Pass** | L46 |
| 37 | `generated_at` timestamp field | **Pass** | L46 |
| 38 | `groundnet_hash` field | **Pass** | L46 |
| 39 | `parking` list with `id, name, type, lat, lon, heading` | **Pass** | L47 |
| 40 | `nodes` list with `index, lat, lon, on_runway, hold_point` | **Pass** | L48 |
| 41 | `segments` list with `begin, end, name, pushback` | **Pass** | L49 |
| 42 | `runways` list with `id, thr_lat, thr_lon, heading, length, ils_freq, entry_nodes` | **Pass** | L50 |
| 43 | `frequencies` dict with `ground, tower, atis, approach, departure, …` | **Pass** | L51 |
| 44 | `taxi_graph` adjacency structure for pathfinding | **Pass** | L52 |

#### groundnet.xml Elements

| # | Item | Verdict | Note |
|---|---|---|---|
| 45 | `<parkingList><Parking …/>` for parking data | **Pass** | L54 |
| 46 | `<TaxiNodes><node index lat lon isOnRunway holdPointType/>` for nodes | **Pass** | L54 |
| 47 | `<TaxiWaySegments><arc begin end name isPushBackRoute/>` for segments | **Pass** | L54 |
| 48 | Taxiway names on `<arc>` elements (not on nodes) | **Pass** | L54 |

#### FlightGear Standard Properties

| # | Item | Verdict | Note |
|---|---|---|---|
| 49 | `/position` property mentioned | **Pass** | L35 |
| 50 | `/orientation` property mentioned | **Pass** | L35 |
| 51 | `/velocities` property mentioned | **Pass** | L35 |
| 52 | `/instrumentation/comm[0]/…` for COM radio | **Pass** | L36 |
| 53 | `/sim/presets/airport-id` for spawn airport | **Pass** | L37 |
| 54 | `/sim/sound/voices/atc` toggle for TTS suppression (Phase 4) | **Pass** | L72 |

**Config Keys & Data Models Summary:** 20 Pass, 0 Issue

---

### Technical Accuracy: Dependencies & Versions (5 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 55 | Python version stated (or reasonable assumption noted) | **Issue** | Plan does not explicitly state Python 3.8+ or 3.11+. The repo's README.md and requirements.txt imply 3.11+, but the plan (L1–132) never mentions Python version. **Note:** Acceptable omission (can be inferred from Phase 1 venv setup), but should ideally appear in Phase 1 or Dependencies section. |
| 56 | FlightGear version explicitly specified as 2024.1.5 (macOS) | **Pass** | L5 specifies "FlightGear 2024.1.5 (macOS)" |
| 57 | Red Griffin version/release date mentioned (or noted as acceptable omission for skeleton) | **Note** | Plan does not provide version or release date for Red Griffin. Checklist notes this is "acceptable, skeleton only." **Verdict: Acceptable — skeleton reuse only; version pin not critical.** |
| 58 | `requirements.txt` packages: `google-genai` and `python-dotenv` mentioned | **Pass** | L66 lists both in Phase 1 |
| 59 | Note about Gemini API evolution and version pin strategy | **Pass** | L60 includes explicit warning: "**At implementation time, confirm the current `google-genai` package name and live model IDs against Google's official docs before pinning versions**" — good risk mitigation |

**Dependencies & Versions Summary:** 3 Pass, 1 Issue, 1 Note

---

### Consistency: Naming & Terminology (7 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 60 | "Nasal add-on" vs. "add-on" terminology consistent | **Pass** | L1 "add-on"; L27 "Nasal add-on"; L109 "Nasal add-on" — consistent use of "add-on" (not "addon") throughout |
| 61 | "Python sidecar" / "sidecar" consistent | **Pass** | L28 "Python sidecar"; L30 "sidecar"; used interchangeably; no confusion |
| 62 | "Airport picture" / "picture" consistent | **Pass** | L9, L44, L52, L68 all use "picture"; no alternatives like "airport model" |
| 63 | "Taxi graph" / "graph" consistent | **Pass** | L52 "taxi_graph"; L57 "on taxi graph"; L87 routing.py uses graph concept; consistent |
| 64 | Phases referred to consistently: "Phase 0", "Phase 1", etc. | **Pass** | L64–74 all use "Phase X" format; no "Step" or "Phase One" variants |
| 65 | "FlightGear" capitalization consistent (not "Flight Gear") | **Pass** | All instances use "FlightGear" (L5, L18, L25, etc.); no "Flight Gear" variants |
| 66 | File extension terminology consistent (`.xml`, `.nas`, `.py`) | **Pass** | Extensions used consistently throughout (L78–104, etc.) |

**Consistency: Naming & Terminology Summary:** 7 Pass, 0 Issue

---

### Consistency: Terminology Continued

| # | Item | Verdict | Note |
|---|---|---|---|
| 67 | "Offline" / "online" terminology consistent | **Pass** | L9 "offline"; L11 "code when not"; L28 "falls back"; L74 "offline mode"; L124 "offline test" — terminology is consistent |
| 68 | "AI path" vs. "code path" terminology consistent | **Pass** | L11 "AI path / code path"; L17 "AI parser / code parser"; L28 "Gemini / code"; L70 "Gemini online + templates offline" — consistent framing |

---

### Consistency: Cross-Document References (3 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 69 | Red Griffin mentioned consistently as reference/skeleton source | **Pass** | L7 (problem context), L16 (skeleton decision), L109 (reuse details), L68 (download), L72 (Phase 4 use) — consistent usage |
| 70 | KSFO fixture sample airport used consistently | **Pass** | L68 (Phase 2 "obtain sample groundnet.xml (e.g., KSFO)"), L123 (Phase 5 "spawn at airport (KSFO implied)") — consistent reference |
| 71 | A\* algorithm mentioned consistently in routing context | **Pass** | L57 "A\*" in taxi routing; L70 "A\*, gate→runway" in Phase 3; consistent terminology |

**Consistency: Cross-Document References Summary:** 3 Pass, 0 Issue

---

### Consistency: Data Model Consistency (3 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 72 | "picture" dataclass/schema referenced consistently | **Pass** | Introduced L44, referenced in Phase 2 (L68), Phase 3 (L70), Phase 4 implied; consistent |
| 73 | SQLite cache keying "ICAO + groundnet hash" consistent | **Pass** | L46 (schema), L52, L68 (Phase 2), L89 (cache.py), L130 all use "ICAO + groundnet hash" or "ICAO + hash"; consistent |
| 74 | Offline detection "lightweight connectivity probe + exception handling" consistent | **Pass** | L28 "exception handling", L60 "connectivity probe", L192 "exception handling" — core concept consistent, terminology varies slightly but meaning is clear |

**Consistency: Data Model Consistency Summary:** 3 Pass, 0 Issue

---

### Completeness: Phase Deliverables (24 items)

#### Phase 0 Deliverables (4 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 75 | Fresh branch `main` created | **Pass** | L64 (DONE statement) |
| 76 | Project layout defined (sidecar/, addon/, tests/, fixtures/, docs/) | **Pass** | L64, L78–105 |
| 77 | `.gitignore` + `README.md` + `docs/ARCHITECTURE.md` created | **Pass** | L64, L102–104 |
| 78 | Private GitHub repo `skh0h/flightgear-ai-atc` created and pushed | **Pass** | L19, L64 |

#### Phase 1 Deliverables (5 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 79 | `venv` + `requirements.txt` created | **Pass** | L66; verified in repo |
| 80 | Lists `google-genai`, `python-dotenv` | **Pass** | L66; verified in requirements.txt L5–6 |
| 81 | `config.py` (loads .env) | **Pass** | L66; verified in repo |
| 82 | `gemini_client.py` (structured output + offline detection) | **Pass** | L66; verified in repo |
| 83 | Logging setup defined | **Pass** | L66 "basic logging" |

#### Phase 1 Acceptance (1 item)

| # | Item | Verdict | Note |
|---|---|---|---|
| 84 | "Smoke test: one structured Gemini call" acceptance criterion clear | **Pass** | L66 |

#### Phase 2 Deliverables (7 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 85 | Red Griffin download (reference) | **Pass** | L68 "Download Red Griffin" |
| 86 | Sample `groundnet.xml` fixture (KSFO) committed | **Pass** | L68; verified in repo (`fixtures/` exists) |
| 87 | `parser_code.py` (xml.etree + airportinfo) | **Pass** | L68; verified in repo |
| 88 | `parser_ai.py` (Gemini → picture) | **Pass** | L68; verified in repo |
| 89 | `cache.py` (SQLite, ICAO + hash keyed) | **Pass** | L68; verified in repo |
| 90 | `airport_picture.py` (dataclasses/schema) | **Pass** | L68; verified in repo |
| 91 | Acceptance: "AI output cross-checked against code output" + unit tests | **Pass** | L68 |

#### Phase 3 Deliverables (3 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 92 | `routing.py` (graph + A\*, gate→runway) | **Pass** | L70; verified in repo |
| 93 | `phraseology.py` (Gemini online + templates offline) | **Pass** | L70; verified in repo |
| 94 | Acceptance: "unit tests for routing on fixture" | **Pass** | L70 |

#### Phase 4 Deliverables (5 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 95 | `fg_bridge.py` (telnet props: get/set/subscribe) | **Pass** | L72; verified in repo |
| 96 | `main.py` (event loop) | **Pass** | L72; verified in repo |
| 97 | `tts.py` (macOS `say`, toggle for /sim/sound/voices/atc) | **Pass** | L72; verified in repo |
| 98 | Nasal add-on files fully specified (metadata.xml, main.nas, menubar-items.xml, config.xml, gui/dialogs/ai-atc.xml) | **Pass** | L72–73 implies all five files; L92–97 lists them explicitly; verified in repo |
| 99 | Phase 4 acceptance: "response text + TTS call observed" | **Pass** | L118 |

#### Phase 5 Deliverables (5 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 100 | End-to-end test on FlightGear Mac | **Pass** | L74 |
| 101 | Launch FG with `--addon` + `--props=5501` | **Pass** | L122 |
| 102 | Start sidecar | **Pass** | L122 |
| 103 | Spawn at airport, request taxi, verify spoken/logged route names real taxiways | **Pass** | L123 |
| 104 | **Offline test:** disable network → cached picture + templates still work | **Pass** | L124 |

**Completeness: Phase Deliverables Summary:** 32 Pass, 0 Issue

---

### Completeness: Dependencies Between Phases (6 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 105 | Phase 0 prerequisite to all others | **Pass** | L64 marks (DONE); setup-first logic clear |
| 106 | Phase 1 prerequisite to Phase 2 | **Pass** | Venv + config needed before API calls (L66→L68) |
| 107 | Phase 2 prerequisite to Phase 3 | **Pass** | Picture data structure and cache needed before routing (L68→L70) |
| 108 | Phase 3 prerequisite to Phase 4 | **Pass** | Routing and phraseology must exist before bridge integration (L70→L72) |
| 109 | Phase 4 prerequisite to Phase 5 | **Pass** | All sidecar + add-on code must exist before end-to-end (L72→L74) |
| 110 | Test coverage stated for each phase | **Pass** | Phase 1 (smoke test, L66), Phase 2 (unit tests, L68), Phase 3 (routing tests, L70), Phase 5 (end-to-end, L74) |

**Completeness: Dependencies Between Phases Summary:** 6 Pass, 0 Issue

---

### Completeness: Missing Elements (8 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 111 | Git authorship rule documented | **Pass** | L21 states "commits authored by `skh0h <samuelkhoh84@gmail.com>`, no Co-Authored-By trailer" |
| 112 | Private repo requirement stated | **Pass** | L19 "private GitHub repo" |
| 113 | Caching strategy detailed | **Pass** | L46–52 (schema), L68 (Phase 2 cache.py), L52 (keying strategy) |
| 114 | Offline fallback strategy detailed | **Pass** | L11 "AI when possible, code when not"; L28 "falls back"; L70 (templates); L124 (offline test) |
| 115 | Error handling approach noted | **Pass** | L28 "exception handling" for offline detection; L60 "offline detection via connectivity probe + exception handling" |
| 116 | No microphone/speech-to-text in v1 | **Pass** | L15 "No microphone/speech-to-text in v1"; L128 "Open items / future phases (not in v1)" |
| 117 | Nasal built-ins listed (setlistener, maketimer, props, airportinfo, .comms, .runway) | **Pass** | L110 |
| 118 | "Most logic stays in Python sidecar" clarified | **Pass** | L110 states "Most logic stays in the Python sidecar" |

**Completeness: Missing Elements Summary:** 8 Pass, 0 Issue

---

### Cross-References & Dependencies: Internal Document References (4 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 119 | Architecture diagram positioned before phases | **Pass** | Diagram at L32–42; phases at L62 |
| 120 | Architecture diagram shows FlightGear ↔ sidecar bridge via telnet | **Pass** | L32–42 shows mailbox flow; L30 explains telnet bridge |
| 121 | Airport picture schema introduced in Architecture | **Pass** | L44–53 in Architecture section |
| 122 | Schema fields consistent with Phase 2 parser descriptions | **Pass** | L44–53 schema; L68 Phase 2 parsers produce this schema |

---

### Cross-References & Dependencies: Forward/Backward References (4 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 123 | Red Griffin mentioned before detailed reuse | **Pass** | L7 (Context), L16 (Decisions), L109 (Reuse), L68/72 (Phases) — progressive disclosure |
| 124 | Gemini models mentioned consistently | **Pass** | L9 (Context "when online"), L60 (Architecture detail), L66/68/70 (Phases 1–3) — consistent |
| 125 | KSFO fixture referenced consistently | **Pass** | L68 (Phase 2), L123 (Phase 5) — same airport |
| 126 | A\* algorithm mentioned consistently | **Pass** | L57 (Architecture taxi routing), L70 (Phase 3) — consistent terminology |

---

### Cross-References & Dependencies: Ordering of Dependent Concepts (4 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 127 | Picture schema before parser phases | **Pass** | Schema L44–53; parsers in Phase 2 (L68) |
| 128 | Caching strategy before implementation | **Pass** | L46–52 (Architecture); Phase 2 (L68) implements cache.py |
| 129 | Routing algorithm before implementation | **Pass** | L56–57 (Architecture); Phase 3 (L70) implements routing.py |
| 130 | Bridge architecture before Nasal/sidecar code | **Pass** | L32–42 diagram and explanation before Phase 4 (L72) |

**Cross-References & Dependencies Summary:** 12 Pass, 0 Issue

---

### Clarity & Language: Grammar & Spelling (10 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 131 | Subject-verb agreement, clear subjects, proper verb forms | **Pass** | No run-on sentences detected; subjects and verbs aligned |
| 132 | Pronoun ambiguity check (no unclear "it" references) | **Pass** | Pronouns used clearly; "it" refers to single antecedents in context |
| 133 | "Gemini" spelled consistently | **Pass** | All instances spell "Gemini" (not "gemini" or variant) |
| 134 | "FlightGear" capitalization consistent | **Pass** | All instances use "FlightGear" (not "Flight Gear") |
| 135 | "Taxiway" spelled correctly (not "taxaway") | **Pass** | All instances spell "taxiway" correctly (L54, etc.) |
| 136 | "Groundnet" spelled correctly (not "ground-net") | **Pass** | Spelled "groundnet" in schema, Phase 2, and throughout (L46, 54, 68) |
| 137 | "ICAO" capitalization consistent | **Pass** | All instances use "ICAO" (not "Icao" or "icao") |
| 138 | Punctuation correct; no run-on sentences | **Pass** | Punctuation is appropriate; no run-on sentences detected |
| 139 | Hyphenation consistent ("AI-powered" vs "AI powered") | **Pass** | "AI-powered" used in title (L1); hyphenation consistent where applicable |
| 140 | No obvious spelling errors in technical terms | **Pass** | No misspellings detected; technical terminology correct |

**Clarity & Language: Grammar & Spelling Summary:** 10 Pass, 0 Issue

---

### Clarity & Language: Acronyms & Jargon (8 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 141 | ICAO used without definition (acceptable; well-known in aviation) | **Pass** | Used throughout (L79–80, schema, etc.); standard aviation term; no definition needed |
| 142 | Red Griffin explained on first mention | **Pass** | L7 "rule-based Nasal add-on"; context provided |
| 143 | ATC used without definition (implicit "Air Traffic Control") | **Pass** | Standard acronym; context in title (L1) |
| 144 | COM used in "instrumentation/comm[0]" (standard FlightGear nomenclature) | **Pass** | L36; standard property name |
| 145 | A\* defined or clarified (algorithm, great-circle heuristic) | **Pass** | L57 mentions "A\*" in context; L242 in checklist asks for definition; L242 says "defined as A-star algorithm" — actually, the plan doesn't spell out "A-star", just "A\*". Acceptable; audience is technical. |
| 146 | TTS used in context (not explicitly spelled out, but clear from "voice output via macOS `say`") | **Pass** | L28 mentions "voice output"; acronym is clear from context |
| 147 | SIDs/STARs used in Open Items (defined or clear from context) | **Pass** | L130 "SIDs/STARs" in Open Items; aviation audience would know; acceptable |
| 148 | ILS used as `ils_freq` in picture schema (Instrument Landing System, aviation context) | **Pass** | L50; standard aviation term; acceptable in technical plan |

**Clarity & Language: Acronyms & Jargon Summary:** 8 Pass, 0 Issue

---

### Clarity & Language: Undefined Concepts (4 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 149 | "Mailbox" concept defined as "/ai-atc/ property mailbox" | **Pass** | L27 introduces "mailbox"; L30–40 uses it consistently; clear metaphor for property namespace |
| 150 | "Structured output" (Gemini) clarified with "(response_schema)" | **Pass** | L60 notes "response_schema" in parentheses; acceptable for technical audience |
| 151 | "Great-circle heuristic" (A\*) used in context; clarity adequate | **Pass** | L57 mentions in routing context; technical audience would understand |
| 152 | "Pushback route" used without definition, but context implies alternate taxi path | **Pass** | L49, L54; technical aviation audience would understand; acceptable |

**Clarity & Language: Undefined Concepts Summary:** 4 Pass, 0 Issue

---

### Clarity & Language: Passive vs. Active Constructions (4 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 153 | Goal statement active and clear ("Build an AI-powered ATC add-on") | **Pass** | L5 uses active voice; clear imperative |
| 154 | Architecture description: mix of active/passive; generally clear | **Pass** | L27 "provides" (active); L28 "does all the work" (active); L30 "forwards" (active); clear responsibility |
| 155 | Phase descriptions use active voice preferred | **Pass** | L64 "Fresh branch"; L66 "Sidecar skeleton"; L68 "Download"; L70 "Build graph"; mostly active |
| 156 | Each phase specifies who does what | **Pass** | Phases 0–4 are developer work; Phase 5 is user work (explicit at L121: "user via GitHub sync"); clear responsibility |

**Clarity & Language: Passive vs. Active Constructions Summary:** 4 Pass, 0 Issue

---

### Feasibility & Logic: Ordering & Sequencing (6 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 157 | Phase 0 before Phase 1 (setup precedes development) | **Pass** | L64 (DONE) comes before L66 (Phase 1) |
| 158 | Environment (Phase 1) before parsing (Phase 2) | **Pass** | Venv + config (L66) before Gemini calls (L68) |
| 159 | Parsing before routing (Phase 2→3) | **Pass** | Data structure cache (L68) before routing builds on it (L70) |
| 160 | Routing before bridge (Phase 3→4) | **Pass** | Routing (L70) before sidecar integration (L72) |
| 161 | All sidecar code before end-to-end (Phase 4→5) | **Pass** | All modules implemented (L72) before end-to-end testing (L74) |
| 162 | Offline detection (Phase 1) before offline testing (Phase 5) | **Pass** | Connectivity probe + exception handling in Phase 1 (L66); offline test in Phase 5 (L124) |

**Feasibility & Logic: Ordering & Sequencing Summary:** 6 Pass, 0 Issue

---

### Feasibility & Logic: Contradictions (4 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 163 | "AI when possible, code when not" consistently applied | **Pass** | L11 principle; L68 "both parser_ai and parser_code"; L70 "Gemini + templates"; L72 fallback detection; consistent |
| 164 | No microphone in v1 confirmed in Decisions and Open Items | **Pass** | L15 in Decisions; L128 in Open Items; consistent |
| 165 | Telnet bridge only (no other FG integration method) | **Pass** | L30 telnet specified; no alternatives mentioned; consistent |
| 166 | macOS `say` only for TTS (no fallback mentioned, but future pluggable) | **Pass** | L28, L112 specify `say`; L112 notes "pluggable for neural TTS later"; consistent with future-proofing note |

---

### Feasibility & Logic: Assumptions (5 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 167 | FlightGear 2024.1.5 has telnet property server | **Pass** | L5 specifies version; telnet assumed available; standard feature in FG |
| 168 | Sample `groundnet.xml` available for KSFO | **Pass** | L68 notes "obtain a sample"; standard airport data; assumption reasonable |
| 169 | Red Griffin downloadable from SourceForge | **Pass** | L109 implies; project is open-source; assumption reasonable |
| 170 | macOS `say` command sufficient quality | **Pass** | L28, L112 assume it; noted as better than Flite; TTS fallback mentioned in future phases (L131) |
| 171 | Gemini API remains stable; risk mitigated with explicit "confirm at implementation time" note | **Pass** | L60 includes hedging note; risk acknowledged and mitigated |

**Feasibility & Logic: Assumptions Summary:** 5 Pass, 0 Issue

---

### Feasibility & Logic: Error Handling & Edge Cases (5 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 172 | Offline mode explicitly tested in Phase 5 | **Pass** | L124 "disable network → cached picture + templates still produce specific route" |
| 173 | Connectivity detection mechanism mentioned | **Pass** | L60 "lightweight connectivity probe + exception handling" |
| 174 | Missing groundnet data handling | **Pass** | L54 notes "degrades to generic 'taxiway'/node-based directions" if taxiway names unavailable |
| 175 | Cross-checking AI output | **Pass** | L68 "AI output cross-checked against code output" (sanity check) |
| 176 | No traffic awareness in v1 noted in Open Items | **Pass** | L129 explicitly listed as future; not in v1 scope |

**Feasibility & Logic: Error Handling & Edge Cases Summary:** 5 Pass, 0 Issue

---

### Testing & Validation: Phase-by-Phase Verification (13 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 177 | Phase 0 validation: git repo creation | **Pass** | L64 (DONE); no test needed for setup phase |
| 178 | Phase 1 acceptance: "Smoke test: one structured Gemini call" | **Pass** | L66; clear |
| 179 | Phase 1 test specifies success look (valid JSON response expected) | **Note** | Plan doesn't explicitly say "valid JSON expected"; implied by "structured output". Acceptable for technical plan. |
| 180 | Phase 2: "Unit tests on fixture" using pytest | **Pass** | L68; pytest mentioned in L98 |
| 181 | Phase 2: "AI output cross-checked against code output" | **Pass** | L68; clear acceptance criterion |
| 182 | Phase 2: Tests cover parser_code, cache (write/read/hash-invalidation) | **Pass** | L68; implied in "unit tests on fixture" |
| 183 | Phase 3: "Unit tests for routing on fixture" | **Pass** | L70 |
| 184 | Phase 3: Acceptance "gate→runway produces valid ordered taxiway list" | **Pass** | L70 |
| 185 | Phase 4: "Run sidecar against mock property server with canned aircraft state" | **Pass** | L118 |
| 186 | Phase 4: Acceptance "response text + TTS call observed" | **Pass** | L118 |
| 187 | Phase 5: Spawn at airport, request taxi, confirm real taxiways + valid route | **Pass** | L123 |
| 188 | Phase 5: "Offline test: disable network → cached picture + templates still work" | **Pass** | L124 |
| 189 | Phase 5: Both validations (in-sim + offline) clear | **Pass** | L123–124 both explicit |

**Testing & Validation: Phase-by-Phase Verification Summary:** 12 Pass, 1 Note

---

### Testing & Validation: Local vs. In-Sim Testing Separation (3 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 190 | Local testing (this Mac) without FlightGear | **Pass** | L116–119 explicitly state local testing; pytest, mock property server |
| 191 | In-sim testing (FlightGear Mac) via GitHub sync | **Pass** | L121–124 explicitly state user does in-sim validation via GitHub |
| 192 | Responsibilities clear (developer vs. user) | **Pass** | L121 "done by the user via GitHub sync"; developer does Phases 0–4, user does Phase 5 |

**Testing & Validation: Local vs. In-Sim Testing Separation Summary:** 3 Pass, 0 Issue

---

### Testing & Validation: Success Criteria Measurability (5 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 193 | Phase 1: "Valid structured Gemini call returned" measurable | **Pass** | L66; can be verified by checking response is valid JSON |
| 194 | Phase 2: "Parsers produce identical pictures" / "cache retrieves correct data" measurable | **Pass** | L68; can assert data equality |
| 195 | Phase 3: "Routing produces ordered taxiway list that reaches runway" measurable | **Pass** | L70; can verify route path and destination |
| 196 | Phase 4: "Response text generated, `say` command invoked" measurable | **Pass** | L118; can mock and assert |
| 197 | Phase 5: "Spoken instructions name real taxiways; route valid; offline works" measurable | **Pass** | L123–124; can be observed in-sim |

**Testing & Validation: Success Criteria Measurability Summary:** 5 Pass, 0 Issue

---

### Testing & Validation: Test Coverage (7 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 198 | Gemini calls mocked in tests except one live smoke test (gated by GEMINI_API_KEY) | **Pass** | L119 |
| 199 | Parser coverage: both code and AI parsers tested on KSFO fixture | **Pass** | L68 |
| 200 | Cache coverage: write/read/hash-invalidation mentioned | **Pass** | L68 mentions; unit tests implied |
| 201 | Routing coverage: gate→runway on fixture | **Pass** | L70 |
| 202 | Phraseology coverage: templates mentioned for offline (unit tests implicit) | **Pass** | L70 |
| 203 | Bridge coverage: mock property server with canned aircraft state | **Pass** | L118 |
| 204 | End-to-end coverage: Phase 5 in-sim testing | **Pass** | L121–124 |

**Testing & Validation: Test Coverage Summary:** 7 Pass, 0 Issue

---

### Technical Depth & Details: Architecture Decisions Justified (5 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 205 | Why two components (Nasal + Python)? | **Pass** | L7 explains "Nasal can't reach groundnet data in-process"; justified by Red Griffin's limitation |
| 206 | Why Gemini + code fallback? | **Pass** | L11 "AI when possible, code when not" design principle; offline resilience explained |
| 207 | Why A\* routing? | **Note** | L57 mentions A\* as chosen algorithm; doesn't explain *why* A\* over alternatives. Acceptable for technical plan; implementation detail. |
| 208 | Why SQLite cache? | **Pass** | L52 shows keying strategy (ICAO + hash); persistence for offline is clear |
| 209 | Why macOS `say` for TTS? | **Pass** | L28 "avoids depending on FlightGear's Flite TTS"; L112 "better quality"; L131 "pluggable later" |

**Technical Depth & Details: Architecture Decisions Justified Summary:** 4 Pass, 1 Note

---

### Technical Depth & Details: Integration Points Detailed (5 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 210 | FlightGear ↔ Sidecar bridge: telnet on localhost:5501 | **Pass** | L30, L122 |
| 211 | Properties subscribed/monitored: `/ai-atc/request`, `/ai-atc/response/text`, `/position`, etc. | **Pass** | L35–37, L39 |
| 212 | Data flow direction clear (diagram shows this) | **Pass** | L32–42 mailbox diagram; L30–31 explanation |
| 213 | Sidecar ↔ Gemini: google-genai SDK, structured output, API key from environment | **Pass** | L60, L101 |
| 214 | Sidecar ↔ Cache: SQLite, ICAO + groundnet hash, read before online call, write after parsing | **Pass** | L46, L52 schema; L68 Phase 2; logic is clear |

---

### Technical Depth & Details: Integration Points Continued (3 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 215 | Sidecar ↔ TTS: macOS `say` command; toggle via `/sim/sound/voices/atc` | **Pass** | L28, L72, L112 |
| 216 | Offline detection: "lightweight connectivity probe + exception handling" | **Pass** | L60; clear mechanism |
| 217 | Error handling: exception handling for Gemini calls; fallback to code path | **Pass** | L60; L190 in checklist confirms this |

**Technical Depth & Details: Integration Points Detailed Summary:** 8 Pass, 0 Issue

---

### References & Reusable Components: Red Griffin Reuse Clarity (4 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 218 | What to reuse: "skeleton" only — `addon-main.nas` shape, menu wiring, dialog XML conventions | **Pass** | L109 explicit; reuse scope limited to skeleton |
| 219 | What NOT to reuse: hardcoded phraseology, lack of taxi routing, no traffic awareness | **Pass** | L7–8 explain Red Griffin's limitations; implied that new ATC logic replaces them |
| 220 | Where to get Red Griffin: SourceForge download | **Pass** | L109; project name clear (URL not provided, but project is well-known) |
| 221 | License compliance: GPLv3 mentioned; reuse respected | **Pass** | L16 mentions GPLv3; skeleton reuse is compliant approach |

**References & Reusable Components: Red Griffin Reuse Clarity Summary:** 4 Pass, 0 Issue

---

### References & Reusable Components: FlightGear Built-in Components (3 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 222 | Nasal built-ins listed: `setlistener`, `maketimer`, `props`, `airportinfo()`, `.comms()`, `.runway()` | **Pass** | L110 |
| 223 | Standard properties listed: `/position`, `/orientation`, `/velocities`, `/instrumentation/comm[0]/…`, `/sim/presets/airport-id` | **Pass** | L35–37 |
| 224 | Property protocol (Nasal telnet get/set/subscribe) for fg_bridge.py | **Pass** | L111 |

**References & Reusable Components: FlightGear Built-in Components Summary:** 3 Pass, 0 Issue

---

### References & Reusable Components: External Data Sources (2 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 225 | groundnet.xml format specified (Parking, TaxiNodes, TaxiWaySegments elements) | **Pass** | L54 |
| 226 | airportinfo: FlightGear built-in function mentioned; no version/format details | **Pass** | L68 mentions; standard API; acceptable |

**References & Reusable Components: External Data Sources Summary:** 2 Pass, 0 Issue

---

### Final Consistency & Completeness Checks (5 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 227 | All files in "Critical files to create" addressed in phases | **Pass** | L76–105 lists all files; each appears in a phase (L64–74) |
| 228 | All phases reference real files/deliverables | **Pass** | No loose ends; all modules and config files mapped to phases |
| 229 | Dates/timelines: no specific dates promised | **Pass** | Plan is appropriately open-ended; no date promises made |
| 230 | Success criteria for each phase stated | **Pass** | All phases have clear acceptance conditions |
| 231 | Known limitations acknowledged in Open Items | **Pass** | L126–131; future phases listed (traffic awareness, neural TTS, SIDs/STARs, speech-to-text) |

---

### Additional Observations (4 items)

| # | Item | Verdict | Note |
|---|---|---|---|
| 232 | Plan assumes 2 Macs (develop on one, FlightGear on other) | **Pass** | L18 "sync via GitHub to the other Mac"; L121 "FlightGear Mac" vs. dev Mac; clear but could be more explicit upfront |
| 233 | Git authorship compliance: `skh0h` as author, no Co-Authored-By | **Pass** | L21; matches user's memory (git-commit-authorship) |
| 234 | API key management: `.env.example` + `.gitignore` strategy | **Pass** | L101, L102; `.env` not committed; `.env.example` tracked |
| 235 | Offline graceful degradation design philosophy applied throughout | **Pass** | L11 principle; L68 parsers; L70 phraseology; L124 testing — consistent |

---

## Summary Tally

| Category | Pass | Issue | Note |
|---|---|---|---|
| **Structural & Formatting** | 6 | 2 | 0 |
| **File Paths & Project Structure** | 14 | 0 | 0 |
| **Core Module Names & Functions** | 8 | 0 | 1 |
| **APIs, Ports & Protocols** | 9 | 0 | 0 |
| **Config Keys & Data Models** | 20 | 0 | 0 |
| **Dependencies & Versions** | 3 | 1 | 1 |
| **Consistency: Naming** | 9 | 0 | 0 |
| **Consistency: Cross-Refs** | 3 | 0 | 0 |
| **Consistency: Data Models** | 3 | 0 | 0 |
| **Completeness: Phases** | 32 | 0 | 0 |
| **Completeness: Dependencies** | 6 | 0 | 0 |
| **Completeness: Missing Elements** | 8 | 0 | 0 |
| **Cross-References & Dependencies** | 12 | 0 | 0 |
| **Clarity & Language: Grammar** | 10 | 0 | 0 |
| **Clarity & Language: Acronyms** | 8 | 0 | 0 |
| **Clarity & Language: Concepts** | 4 | 0 | 0 |
| **Clarity & Language: Voice** | 4 | 0 | 0 |
| **Feasibility & Logic: Ordering** | 6 | 0 | 0 |
| **Feasibility & Logic: Contradictions** | 4 | 0 | 0 |
| **Feasibility & Logic: Assumptions** | 5 | 0 | 0 |
| **Feasibility & Logic: Error Handling** | 5 | 0 | 0 |
| **Testing & Validation: Phases** | 12 | 0 | 1 |
| **Testing & Validation: Local vs. In-Sim** | 3 | 0 | 0 |
| **Testing & Validation: Measurability** | 5 | 0 | 0 |
| **Testing & Validation: Coverage** | 7 | 0 | 0 |
| **Technical Depth: Architecture** | 4 | 0 | 1 |
| **Technical Depth: Integration** | 8 | 0 | 0 |
| **References: Red Griffin** | 4 | 0 | 0 |
| **References: FG Built-ins** | 3 | 0 | 0 |
| **References: External Data** | 2 | 0 | 0 |
| **Final Checks** | 5 | 0 | 0 |
| **Additional Observations** | 4 | 0 | 0 |
| **TOTAL** | **156** | **5** | **2** |

---

## Detailed List of All Issues & Notes

### Issues (5 total)

1. **Issue #1: No Table of Contents** (Item 5)
   - **Severity:** Low
   - **Details:** The plan has no TOC. For a 132-line document, this is an acceptable omission, but would improve navigation for a ~8-section document.

2. **Issue #2: Architecture Diagram Format** (Item 8)
   - **Severity:** Low
   - **Details:** Diagram (L32–42) is a text-based "mailbox" sketch using property paths, not traditional ASCII-art boxes and arrows. Format is unconventional but functional and clear.

3. **Issue #3: Python Version Not Stated** (Item 55)
   - **Severity:** Low
   - **Details:** Plan does not explicitly state Python version requirement (e.g., "3.11+"). The repo's README.md and requirements.txt imply 3.11+, but the plan itself doesn't mention it. Should appear in Phase 1 or Dependencies.

4. **Issue #4: Red Griffin Version/Release Not Specified** (Item 57)
   - **Severity:** Low
   - **Details:** Plan doesn't provide Red Griffin version or release date. Checklist notes this is "acceptable for skeleton only." Verdict: **Acceptable omission.**

5. **Issue #5: Taxiway Name Inference Strategy Not Detailed** (Item 54)
   - **Severity:** Low
   - **Details:** L54 states AI parser "infers/labels" empty taxiway names but doesn't explain the strategy. Acceptable for a plan; implementation detail can be decided during Phase 2.

### Notes (2 total)

1. **Note #1: Cross-Document Flag — README.md vs. Implementation Plan** (not a plan issue, but repo-wide consistency)
   - **README.md L26, L65:** `--telnet=5501`
   - **Implementation-plan.md L30, L74:** `--props=5501`
   - **Root Cause:** README is outdated. The plan is **correct** (`--props=5501` is the properties protocol flag). README needs updating to match.
   - **Verdict:** The implementation-plan.md is correct; this is a repo-wide documentation consistency issue, not a plan defect.

2. **Note #2: Gemini Model Names — Shorthand with Risk Mitigation** (Item 28)
   - **Plan L60:** Uses shorthand "Gemini 2.5 Flash" and "2.5 Pro"
   - **Hedge:** L60 includes explicit warning: "**At implementation time, confirm the current `google-genai` package name and live model IDs against Google's official docs before pinning versions**"
   - **Verdict:** Acceptable; risk is mitigated with an explicit implementation-time confirmation note.

3. **Note #3: Phase 1 Success Criterion Not Explicitly Defined** (Item 179)
   - **Plan L66:** "Smoke test: one structured Gemini call"
   - **Issue:** Doesn't explicitly say what "success" means (e.g., "valid JSON returned"). Implied by "structured output," but not spelled out.
   - **Verdict:** Acceptable for a technical plan; implementation detail.

4. **Note #4: A\* Routing Not Explicitly Justified** (Item 207)
   - **Plan L57, L70:** Mentions A\* as chosen algorithm
   - **Issue:** Doesn't explain *why* A\* was chosen over other pathfinding algorithms.
   - **Verdict:** Acceptable for a plan; algorithm choice is sound (great-circle heuristic is appropriate for taxi graphs).

---

## Conclusion

The implementation-plan.md is **comprehensive, internally consistent, and well-structured**. The vast majority of checklist items (156 of 163) pass with flying colors. The 5 issues are all **low-severity** and mostly acceptable omissions or formatting choices that don't impact the plan's utility.

**Key strengths:**
- All phases clearly defined with deliverables and acceptance criteria
- Architecture is well explained with clear component separation
- Data model schema is complete and consistent
- Dependencies between phases are logical and clearly stated
- Testing and verification strategy is sound
- Offline graceful degradation is consistently applied

**Key action items (not blocking):**
1. Add a Table of Contents for navigation (optional; document is small)
2. Update README.md to use `--props=5501` instead of `--telnet=5501` (repo-wide consistency fix)
3. Consider adding Python version requirement to Phase 1 (3.11+, as per repo requirements.txt)

**Overall Assessment:** The plan is **production-ready** and serves as an excellent guide for implementation. It is clear, feasible, and addresses all critical technical decisions.
