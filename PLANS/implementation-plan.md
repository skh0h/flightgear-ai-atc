# AI-Powered ATC Add-on for FlightGear — Implementation Plan

## Context

**Goal:** Build an AI-powered Air Traffic Control add-on for FlightGear 2024.1.5 (macOS) that gives **specific, real instructions** (e.g., "taxi to runway 28R via A, B, hold short of 28R") instead of the generic instructions produced by the existing **Red Griffin ATC** add-on.

**The problem with what exists:** Red Griffin ATC is a rule-based Nasal add-on with hardcoded, generic phraseology and **no taxi routing** (the author was blocked because Nasal can't reach FlightGear's ground-network data in-process). It has no traffic awareness and stale, non-standard phraseology.

**Intended outcome:** An add-on that uses **Gemini when online** for rich/natural phraseology and for interpreting airport data, and **falls back to deterministic code when offline**. Airport "pictures" (parking + named taxiway graph + runway links + frequencies) are derived once per airport and **cached locally** so offline sessions still get specific instructions.

**Key design principle — "AI when possible, code when not":** every capability has both an AI path (online, easy/rich) and a code path (offline, reliable). The code path also sanity-checks the AI path.

## Confirmed decisions (from the user)

- **Interaction model:** Listen + menu replies (Red Griffin style). No microphone/speech-to-text in v1.
- **Codebase:** New add-on; download Red Griffin and **extract only its skeleton for reference** (it's GPLv3).
- **Data:** Use both an **AI parser** (Gemini reads `groundnet.xml` + `airportinfo` → structured "picture") and a **code parser** (deterministic fallback). Same cached schema.
- **Machines:** Develop on this Mac (no FlightGear here); **sync via GitHub** to the other Mac (has FlightGear 2024.1.5 + Red Griffin) for in-sim testing.
- **Repo:** Fresh start in `~/Documents/FlightGear Add-on`, new branch, **private** GitHub repo `skh0h/flightgear-ai-atc`.
- **Sidecar language:** Python.
- **Git authorship:** commits authored by `skh0h <samuelkhoh84@gmail.com>`, no Co-Authored-By trailer.

## Architecture

Two components, both deployed to the FlightGear Mac:

1. **Nasal add-on** (thin, runs *inside* FlightGear) — provides a menu + log dialog (listen + menu replies), exposes a small property "mailbox" under `/ai-atc/`, and forwards menu requests. It does **not** contain ATC logic.
2. **Python sidecar** (separate process, same Mac) — does all the work: Gemini calls, `groundnet.xml`/`airportinfo` parsing, A\* taxi routing, phraseology, caching, offline fallback, and **voice output via macOS `say`** (avoids depending on FlightGear's Flite TTS being compiled in; better quality, pluggable to neural TTS later).

**Bridge:** FlightGear launched with `--props=5501` (telnet property server) and `--addon=…/addon`. The sidecar connects to `localhost:5501`, subscribes to `/ai-atc/request`, reads aircraft state from standard properties, computes a response, sets `/ai-atc/response/text`, and speaks it. The Nasal add-on listens on `/ai-atc/response/text` to update the log.

```
FlightGear (other Mac)                          Python sidecar (same Mac)
  Nasal add-on  ── /ai-atc/* mailbox ──┐
  /position, /orientation, /velocities │  telnet  ┌─ fg_bridge (get/set/subscribe)
  /instrumentation/comm[0]/…           ├──:5501───┤─ gemini_client (online)  ──► Gemini API
  /sim/presets/airport-id              │          ├─ parser_ai / parser_code ──► "picture"
                                       │          ├─ cache (SQLite, per ICAO+hash)
  log dialog ◄── /ai-atc/response/text ┘          ├─ routing (A* on taxi graph)
                                                  ├─ phraseology (AI online / templates offline)
  audio ◄──────────── macOS `say` ◄───────────────┴─ tts
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
`groundnet.xml` structure to parse: `<parkingList><Parking …/>`, `<TaxiNodes><node index lat lon isOnRunway holdPointType/>`, `<TaxiWaySegments><arc begin end name isPushBackRoute/>`. Taxiway **names** live on `<arc>` and may be empty for some airports — the AI parser infers/labels these; the code path degrades to generic "taxiway"/node-based directions.

### Taxi routing
Build graph from nodes+segments → nearest node to the gate is the start, runway-entry/hold nodes are targets → **A\*** (great-circle heuristic) → node path → collapse consecutive same-name arcs into an ordered taxiway list → phraseology ("via A, B, hold short of 28R").

### Gemini integration
Python `google-genai` SDK; model **Gemini 2.5 Flash** for phraseology (fast/cheap), optionally **2.5 Pro** for the one-time groundnet parse. Use **structured output (`response_schema`)** so the picture/phraseology come back as validated JSON. API key from `GEMINI_API_KEY` in a **gitignored `.env`**. Offline detection via a lightweight connectivity probe + exception handling → automatic fallback to code parser + template phraseology. **At implementation time, confirm the current `google-genai` package name and live model IDs against Google's official docs before pinning versions** (the API evolves).

## Implementation phases

**Phase 0 — Repo & scaffolding. (DONE)** Fresh branch `main`; project layout (`sidecar/`, `addon/`, `tests/`, `fixtures/`, `docs/`); `.gitignore`; `README.md`; `docs/ARCHITECTURE.md`. Private GitHub repo `skh0h/flightgear-ai-atc` created and pushed.

**Phase 1 — Sidecar skeleton + Gemini.** `venv` + `requirements.txt` (`google-genai`, `python-dotenv`). `config.py` (.env, settings), `gemini_client.py` (structured-output call + offline detection), basic logging. Smoke test: one structured Gemini call.

**Phase 2 — Airport "picture" pipeline.** Download Red Griffin (SourceForge) + obtain a sample `groundnet.xml` (e.g., KSFO) as a committed test fixture. `parser_code.py` (deterministic `xml.etree` parse + airportinfo), `parser_ai.py` (Gemini → picture), `cache.py` (SQLite, keyed by ICAO + groundnet hash), `airport_picture.py` (dataclasses/schema). AI output cross-checked against code output. Unit tests on the fixture.

**Phase 3 — Routing + phraseology.** `routing.py` (graph + A\*, gate→runway), `phraseology.py` (Gemini online + templates offline). Unit tests for routing on the fixture.

**Phase 4 — FlightGear bridge + Nasal add-on.** `fg_bridge.py` (telnet props: get/set/subscribe), `main.py` (event loop), `tts.py` (macOS `say`, toggle for FG `/sim/sound/voices/atc`). Nasal add-on built from the Red Griffin skeleton: `addon-metadata.xml`, `addon-main.nas` (`main`/`unload`, init `/ai-atc/` mailbox, menu wiring, listener on `/ai-atc/response/text`), `addon-menubar-items.xml`, `addon-config.xml`, `gui/dialogs/ai-atc.xml`.

**Phase 5 — End-to-end on the FlightGear Mac.** Sync via GitHub. Launch FG with `--addon` + `--props=5501`; start sidecar; spawn at an airport; request taxi via menu; confirm a spoken/logged route naming real taxiways. Verify offline mode (disable network → cached picture + templates still produce a route). Iterate.

## Critical files to create

```
~/Documents/FlightGear Add-on/
├── sidecar/
│   ├── main.py            # event loop + FG bridge orchestration
│   ├── fg_bridge.py       # telnet property client (get/set/subscribe on :5501)
│   ├── gemini_client.py   # Gemini structured-output calls + offline detection
│   ├── airport_picture.py # picture schema / dataclasses
│   ├── parser_code.py     # deterministic groundnet.xml + airportinfo parser (offline path)
│   ├── parser_ai.py       # Gemini-based parser (online path)
│   ├── routing.py         # taxi graph + A* (gate → runway)
│   ├── phraseology.py     # AI phrasing (online) + templates (offline)
│   ├── cache.py           # SQLite picture cache (ICAO + groundnet hash)
│   ├── tts.py             # macOS `say`; pluggable
│   └── config.py          # .env loading, settings
├── addon/
│   ├── addon-metadata.xml
│   ├── addon-main.nas
│   ├── addon-menubar-items.xml
│   ├── addon-config.xml
│   └── gui/dialogs/ai-atc.xml
├── tests/                 # pytest: parser_code, routing, cache, phraseology
├── fixtures/              # sample groundnet.xml (KSFO) + sample airportinfo
├── requirements.txt
├── .env.example           # GEMINI_API_KEY=  (real .env is gitignored)
├── .gitignore
├── README.md
└── docs/ARCHITECTURE.md
```

## Reuse / references (don't reinvent)

- **Red Griffin skeleton** (download from SourceForge) — copy the add-on layout, `addon-main.nas` `main(addon)`/`unload(addon)` shape, and dialog XML conventions only.
- **FlightGear Nasal built-ins** for the thin add-on: `setlistener`, `maketimer`, `props`, and `airportinfo()`/`.comms()`/`.runway()` if any data is fetched in-sim. Most logic stays in the Python sidecar.
- **FlightGear telnet/property protocol** (`get`/`set`/`subscribe`) for `fg_bridge.py`.
- **macOS `say`** for TTS (built in; no extra install).

## Verification

**Local (this Mac, no FlightGear):**
- `pytest tests/` — parser (code path on the committed `groundnet.xml` fixture), routing (gate→runway produces a valid ordered taxiway list), cache (write/read/hash-invalidation), phraseology templates.
- Run the sidecar against a **mock property server** with canned aircraft state; confirm a request produces correct response text and a `say` invocation.
- Gemini calls mocked in tests; one live structured-output smoke test gated behind `GEMINI_API_KEY`.

**On the FlightGear Mac (in-sim, done by the user via GitHub sync):**
- Launch `fgfs --addon=…/addon --props=5501`; start `python sidecar/main.py`.
- Spawn at an airport with groundnet data (e.g., KSFO); use the menu to request taxi; confirm the spoken + logged instruction names **real** taxiways and a valid route to the assigned runway.
- **Offline test:** disable network → confirm the cached picture + template phraseology still produce a specific route (graceful degradation).

## Open items / future phases (not in v1)

- Microphone / speech-to-text ("talk to ATC").
- Traffic awareness & sequencing via `/ai/models/` (the biggest Red Griffin gap).
- Real-world procedure enrichment (SIDs/STARs) via Gemini + Google Search grounding.
- Neural TTS voices (swap into `tts.py`).
