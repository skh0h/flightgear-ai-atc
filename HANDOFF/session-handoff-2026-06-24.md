# Session Handoff — FlightGear AI ATC Add-on (resume Phase 2)

**Date:** 2026-06-24
**Repo:** `/Users/andrewkhoh/Documents/FlightGear Add-on` (nested git repo — NOT the parent `~/Documents`)
**Remote:** `https://github.com/skh0h/flightgear-ai-atc` (private)
**Branch:** `main`

> ⚠️ **Read this first, then `PLANS/implementation-plan.md` + `docs/ARCHITECTURE.md`.** This file captures everything needed to build Phases 2–4 **cheaply in a fresh session** — exact Phase 1 interfaces, the corrected dependency pins, the fixture/skeleton URLs, and per-phase specs. The detailed research lived in a `/private/tmp/...` file that will NOT survive `/clear`, so the essentials are inlined below.

---

## 0. Why this handoff exists (cost)

Phase 1 was completed via heavy multi-agent **Workflow** orchestration. That, plus large research/result payloads accumulating in one conversation, drove session cost to **$111** before Phase 2 was even written. Two lessons for the resume:

- **Implement INLINE. Do NOT spawn large `Workflow`/agent fleets.** The agents auto-abort when a cost-warning hook fires (Phase 2 burned ~$8 producing *nothing* this way). Write the code directly, run `pytest` directly.
- **Keep the conversation lean.** Don't re-read big files into context repeatedly; read a file once, edit, move on.
- A cost hook (`gateguard` / cost-critical) fires in this environment; the override to disable is `ECC_GATEGUARD=off` or `ECC_DISABLED_HOOKS=pre:bash:gateguard-fact-force`. The first `Bash` call each session must be preceded by a one-line "facts" preamble (request + what the command does).

---

## 1. Status

| Phase | State |
|---|---|
| **0 — scaffold** | ✅ done (prior session), pushed |
| **1 — config + Gemini client** | ✅ **done, committed, pushed this session** (`a9582b8`) |
| **2 — airport picture pipeline** | ⬜ NOT started — **next** |
| **3 — routing + phraseology** | ⬜ NOT started |
| **4 — FG bridge + Nasal add-on** | ⬜ NOT started |
| **5 — end-to-end in-sim** | ⛔ BLOCKED — requires the FlightGear Mac (the other machine) |

**Commits on `main`:** `a9582b8` (Phase 1 feat) · `b0c1e15` (docs: plan+handoff, ignore `.claude-mpm`) · `89313fc` (Phase 0) · `d32476a` (initial).

---

## 2. Locked constraints (do not relitigate)

- **Authorship:** every commit authored `skh0h <samuelkhoh84@gmail.com>`, **never** a `Co-Authored-By: Claude` trailer. Use `git -c user.name='skh0h' -c user.email='samuelkhoh84@gmail.com' commit …`.
- **Safety gate before any write/commit:** `git -C "<repo>" rev-parse --show-toplevel` MUST equal the FlightGear Add-on folder, **not** `/Users/andrewkhoh/Documents` (parent repo = `xstate-app`, leave alone). `gh` active account must be `skh0h`.
- **Secrets:** `GEMINI_API_KEY` lives only in a gitignored `.env` (user adds it later). Never commit/print it. **Tests are mock-only — no live Gemini calls.**
- **Commit per phase**, push to `origin main`.

---

## 3. Environment (already set up)

- **venv:** `.venv/` at repo root (gitignored), **uv-managed, Python 3.13**. Run tests with: `cd "<repo>" && .venv/bin/python -m pytest tests/ -q` (run from repo root so `import sidecar` resolves).
- **`requirements.txt` pins (verified from PyPI — the earlier research report's versions were WRONG, e.g. it claimed `google-genai==2.10.0`; real is `1.47.0`):**
  - `google-genai==1.47.0`, `python-dotenv==1.2.1`, `pytest==8.4.2`
  - `cryptography==43.0.3` — **build constraint only** (transitive via `google-auth`; last version with a prebuilt x86_64 macOS wheel on this machine; not used by sidecar code directly).
  - **Always verify any new pin against PyPI directly, not from a research summary.**
- **Current test count:** 27 passing (Phase 0 smoke + Phase 1 config/gemini).

---

## 4. Phase 1 interfaces your new code MUST call

```python
# sidecar/config.py
from sidecar.config import Settings, ConfigError, load
# Settings (frozen dataclass) fields:
#   gemini_api_key: str | None        # None when key absent — offline path must still work
#   fg_telnet_host: str               # default "localhost"
#   fg_telnet_port: int               # default 5501
#   cache_db_path: str                # default "fixtures/cache/airports.sqlite"
#   tts_voice: str                    # default "Alex"
#   log_level: str                    # default "INFO"
#   gemini_model_fast: str            # default "gemini-2.5-flash"
#   gemini_model_pro: str             # default "gemini-2.5-pro"
settings = load()                     # reads .env (optional) + env vars; ConfigError only on bad values

# sidecar/gemini_client.py
from sidecar.gemini_client import GeminiClient, OfflineError
client = GeminiClient(settings)
# generate() takes a *Pydantic BaseModel subclass* as the response schema and returns an instance of it.
result = client.generate(prompt: str, schema: type[T], *, model: str | None = None) -> T
#   raises OfflineError on: missing key / network error / auth (401,403) / quota (429) / retries exhausted.
#   Tests inject _sleep=lambda *_: None to skip backoff. Catch OfflineError → use the code path.
```

**The whole design hinges on the offline contract:** anything that calls Gemini must `try: … except OfflineError: <deterministic fallback>`.

---

## 5. Shared schema (Phase 2 builds this; Phases 3–4 consume it)

Implement in `sidecar/airport_picture.py` as **Pydantic `BaseModel`s** (so the same models serve as the Gemini `response_schema` AND the SQLite (de)serializer via `model_dump_json()` / `model_validate_json()`):

```
AirportPicture: icao, source: Literal["ai","code"], generated_at (ISO-8601),
                groundnet_hash (sha256 hex), parking[], nodes[], segments[],
                runways[], frequencies, taxi_graph: dict[int, list[int]]
ParkingSpot:  id, name, type, lat, lon, heading
Node:         index, lat, lon, on_runway: bool, hold_point: bool
Segment:      begin: int, end: int, name: str, pushback: bool
Runway:       id, thr_lat, thr_lon, heading, length, ils_freq, entry_nodes: list[int]
Frequencies:  ground, tower, atis, approach, departure   (all Optional[str])
```

**Critical design rules:**
- `taxi_graph` is **computed**, never AI-trusted → write a free function `build_taxi_graph(nodes, segments) -> dict[int, list[int]]` (undirected adjacency). Both parsers call it after producing nodes/segments.
- Define a **separate "AI response" Pydantic schema** for `parser_ai` that **excludes** `taxi_graph`, `groundnet_hash`, `generated_at` (the AI returns only parking/nodes/segments/runways/frequencies; compute the rest locally). Int-keyed dicts are unreliable for structured output.

---

## 6. Phase 2 — airport picture pipeline (DO THIS NEXT)

**Fixture (commit a REAL one):** fetch a busy airport groundnet with named taxiways → save verbatim to `fixtures/KSFO.groundnet.xml` (this path is tracked; `fixtures/cache/` and `fixtures/*.generated.*` are gitignored). Sources:
- `https://raw.githubusercontent.com/mherweg/Airports/master/K/S/F/KSFO.groundnet.xml`
- fallback (fgdata SVN): `https://svn.code.sf.net/p/flightgear/fgdata/trunk/Airports/K/S/F/KSFO.groundnet.xml`
- **Inspect the actual XML** — confirm attribute spellings/coordinate format before coding the parser.

**`groundnet.xml` structure:** root `<groundnet>` → `<parkingList><Parking index type name lat lon heading …/></parkingList>` · `<TaxiNodes><node index lat lon isOnRunway holdPointType/></TaxiNodes>` · `<TaxiWaySegments><arc begin end name isPushBackRoute/></TaxiWaySegments>`. Taxiway names live on `<arc name>` and **may be empty**. Parse `isOnRunway`/`isPushBackRoute` as `attr.lower()=="true"`; `hold_point = bool(holdPointType set/non-empty)`.

**Modules:**
- `parser_code.py` — `class ParseError(Exception)`; `parse_groundnet(xml_source, icao, *, airportinfo: dict|None=None) -> AirportPicture` (source="code"). `xml.etree.ElementTree`; guard every `.get()`; reject non-numeric lat/lon with `ParseError`; dedup arcs by canonical `(min,max)`; `groundnet_hash = sha256(raw_bytes).hexdigest()`; `generated_at = datetime.now(timezone.utc).isoformat()`; runway thresholds/ILS + frequencies come from the optional `airportinfo` dict (supplied in-sim by the Nasal layer) — **leave None/empty when absent so the fixture-only path still succeeds**.
- `parser_ai.py` — `parse_with_ai(icao, groundnet_xml_text, gemini_client, *, airportinfo=None) -> AirportPicture`. Prompt embeds raw XML + "infer/label taxiway names"; `gemini_client.generate(prompt, <AIResponse schema>)`; convert → `AirportPicture(source="ai")`, compute taxi_graph+hash+generated_at locally. **`except OfflineError: return parser_code.parse_groundnet(...)`** (source="code"). Log a warning if AI vs code node/segment counts diverge wildly.
- `cache.py` — `class PictureCache`: db path default `settings.cache_db_path`; `db_path.parent.mkdir(parents=True, exist_ok=True)`; table `pictures(icao TEXT, hash TEXT, data TEXT, created_at TEXT, PRIMARY KEY(icao,hash))`; `get(icao, groundnet_hash)->AirportPicture|None`, `put(picture)` (INSERT OR REPLACE), `invalidate(icao)`. **Parameterized SQL only** (`?` placeholders).

**Tests (mock/fixture only):** `test_airport_picture.py` (round-trip + `build_taxi_graph` on a tiny hand set), `test_parser_code.py` (parse the KSFO fixture: counts>0, symmetric taxi_graph, deterministic hash, `ParseError` on malformed, airportinfo merge), `test_parser_ai.py` (fake client returns fixed obj → source="ai"; raises `OfflineError` → falls back to source="code"; no network), `test_cache.py` (put/get round-trip, different-hash miss, invalidate, tmp_path parent-dir create).

**Commit:** `feat(sidecar): Phase 2 — airport picture pipeline (code+AI parsers, cache) with KSFO groundnet fixture` (+ the fixture).

---

## 7. Phase 3 — routing + phraseology

- `routing.py` — `find_route(picture, start_node, goal_node) -> list[int]` via **A\*** with **haversine** heuristic over node lat/lon (`taxi_graph` is the adjacency). Helpers: nearest node to a parking spot (start); runway entry/hold node (goal). `route_to_instructions(route, picture) -> list[str]`: collapse consecutive same-`name` arcs into an ordered taxiway list ("via A, B"), end with "hold short of <rwy>". Handle empty/disconnected gracefully.
- `phraseology.py` — `phrase_offline(clearance) -> str` (templates, e.g. `"{callsign}, taxi to runway {rwy} via {taxiways}, hold short of {rwy}."`); `phrase_online(clearance, gemini_client) -> str` → call `gemini_client.generate(prompt, schema=<PhraseResult pydantic {text:str}>)`, return `.text`; **`except OfflineError: return phrase_offline(...)`**. Clearance fields: callsign, clearance_type, taxi_route, active_runway, hold_short, frequency, remarks.
- **Tests:** `test_routing.py` (gate→runway on the KSFO fixture yields a valid ordered taxiway list; A* optimality on a tiny graph), `test_phraseology.py` (offline templates exact; online falls back to offline on `OfflineError`).
- **Commit:** `feat(sidecar): Phase 3 — A* taxi routing + online/offline phraseology`.

---

## 8. Phase 4 — FG bridge + Nasal add-on (largest; in-sim test deferred to Phase 5)

**`/ai-atc/` mailbox (see `docs/ARCHITECTURE.md`):**
`/ai-atc/request/{type,callsign,trigger}` (Nasal→sidecar) · `/ai-atc/response/{text,ready}` + `/ai-atc/status` (sidecar→Nasal).

**Telnet/property bridge** — Launch FG with **`--telnet=5501`** (raw telnet property server; `--props=5501` is the equivalent generic property server — README currently says `--telnet=5501`, keep that). Line protocol over the socket: `get <prop>`, `set <prop> <val>`, `ls [dir]`, `cd`, `pwd`, `dump`, `run <cmd>`, `quit`; lines CRLF/`\n`-terminated; responses are plain text. **The basic telnet protocol does not push async updates → POLL** `/ai-atc/request/trigger` at ~5–10 Hz (re-confirm subscribe support at `wiki.flightgear.org/Telnet_usage` + `Property_Tree_Servers` if you want push). Refs: `flightgear-python` lib (`flightgear_python.fg_if.TelnetConnection`), `github.com/puffergas/PiStack/blob/master/telnet.py`.
- `fg_bridge.py` — socket client: `connect()` (with retry/backoff while FG not up), `get(path)->str`, `set(path,value)`, `poll(path)` / a `subscribe(path, cb)` implemented via polling. Unit-test against a **mock socket server** (no live FG).
- `tts.py` — `speak(text, voice=settings.tts_voice)` via `subprocess.run(["say","-v",voice,text])`; backend ABC for future swap; queue so long clearances don't block. **Mock `subprocess` in tests** (don't actually emit audio).
- `main.py` — event loop: init bridge+client+cache+router+tts → poll trigger → on fire: read request + aircraft state (`/position`, `/orientation`, `/sim/presets/airport-id`) → cache `get` (miss → `parser_ai`/`parser_code` → `put`) → `routing` → `phraseology` → `tts.speak` → set `/ai-atc/response/text` + `ready=true` + `status` → reset `trigger`. Graceful SIGINT/SIGTERM.

**Nasal add-on** (flesh out the Phase 0 stubs in `addon/`; reference the **FGAddon "Skeleton"** — structure only, it's the canonical template): `https://sourceforge.net/p/flightgear/fgaddon/HEAD/tree/trunk/Addons/Skeleton/` (`addon-main.nas` `main(addon)`/`unload(addon)`, `addon-menubar-items.xml`, `addon-metadata.xml`, `gui/dialogs/sample-dialog.xml`). Red Griffin (GPLv3, skeleton reference only): `sourceforge.net/projects/red-griffin-atc/`, `wiki.flightgear.org/Red_Griffin_ATC`.
- `addon-main.nas`: `main(addon)` inits `/ai-atc/` mailbox, wires menu actions (Request Pushback/Taxi/Takeoff/Cancel → set request props + `trigger=true`), `setlistener("/ai-atc/response/text", …)` to append to the log dialog; `unload(addon)` tears down listeners/timers.
- `addon-menubar-items.xml`, `addon-config.xml`, `gui/dialogs/ai-atc.xml`: menu + scrollable log dialog.

**Tests:** `test_fg_bridge.py` (mock socket: get/set round-trip, reconnect), `test_tts.py` (mock subprocess: correct `say` argv). Nasal is not unit-testable here — verified in Phase 5.
**Commit:** `feat: Phase 4 — FG telnet bridge, sidecar event loop, TTS, and Nasal add-on`.

---

## 9. Phase 5 — end-to-end (BLOCKED here; the FlightGear Mac does this)

Pull on the FlightGear Mac → launch `fgfs --addon=…/addon --telnet=5501` → `python3 sidecar/main.py` → spawn at KSFO → menu "Request Taxi" → confirm spoken+logged route names **real** taxiways to the assigned runway. Offline test: disable network → cached picture + templates still produce a route.

---

## 10. Deferred minor cleanups (batch into a final pass)

From Phase 1 review (all non-blocking): `load()` is missing a `-> Settings` return annotation; redundant `socket.error` in `_is_offline` (alias of `OSError`); trivial `test_smoke.py` (replace with a real import sanity check); add `pytest-cov`; hoist the `from google.genai import types` import; `_client: Any` → `TYPE_CHECKING` annotation; add a test that an *unexpected* exception type propagates out of `generate()` unchanged.

---

## 11. Resume checklist

1. `cd "/Users/andrewkhoh/Documents/FlightGear Add-on"`; `git -C . rev-parse --show-toplevel` == this folder; `gh auth status` → `skh0h`.
2. `git pull origin main`; confirm `.venv` exists (else `uv venv && .venv/bin/python -m pip install -r requirements.txt`); `.venv/bin/python -m pytest tests/ -q` → 27 green.
3. Build **Phase 2 inline** (§6) → tests green → commit/push as `skh0h` → Phase 3 (§7) → Phase 4 (§8). Stop at Phase 5.
4. Implement **inline, lean** — no large agent fleets (see §0).
