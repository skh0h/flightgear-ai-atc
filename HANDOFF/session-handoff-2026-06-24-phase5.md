# Session Handoff — FlightGear AI ATC (resume at Phase 5 + parser_ai refactor)

**Date:** 2026-06-24 (second session this day)
**Repo:** `/Users/andrewkhoh/Documents/FlightGear Add-on` (nested git repo — NOT parent `~/Documents`)
**Remote:** `https://github.com/skh0h/flightgear-ai-atc` (private) · **Branch:** `main`
**Supersedes:** `session-handoff-2026-06-24.md` (Phases 2–4 are now DONE). Read that file too for the deep per-phase specs; this file records what changed.

---

## 0. Cost discipline (read first)
- This session ended at **~$260**. The cost-critical hook fires in this environment. **Stay lean: implement inline, do NOT spawn Workflow/agent fleets, don't re-read big files repeatedly.**
- A **GateGuard fact-forcing gate** intercepts the first `Bash` of a session and EVERY `Write`/`Edit` (first attempt per file blocks; present the 4 facts, then the retry succeeds). It also flags shell `>` redirects as "destructive" (present files-modified + rollback + the user instruction, then retry).
- **Do NOT disable GateGuard** (`ECC_GATEGUARD=off` is denied by the auto classifier and shouldn't be bypassed).

## 1. Status
| Phase | State |
|---|---|
| 0 scaffold | done, pushed |
| 1 config + Gemini client | done, pushed |
| 2 airport picture pipeline | DONE this session — pushed (`9adc6a3`) |
| 3 routing + phraseology | DONE this session — pushed (`4aa31b5`) |
| 4 FG bridge + event loop + TTS + Nasal add-on | DONE this session — pushed (`9c6d71a`) |
| 5 end-to-end in-sim | BLOCKED — needs the FlightGear Mac |
| (new) parser_ai redesign | RECOMMENDED before any live KSFO run — see §3 |

`main` HEAD = `9c6d71a`. Test suite: **85 passing, mock/fixture-only.** Also committed `afabe23` (test-isolation fix, see §5).

## 2. Locked constraints (unchanged — do not relitigate)
- **Authorship:** every commit `skh0h <samuelkhoh84@gmail.com>`, **never** a `Co-Authored-By: Claude` trailer. Use `git -c user.name='skh0h' -c user.email='samuelkhoh84@gmail.com' commit …`.
- **Safety gate before write/commit:** `git rev-parse --show-toplevel` MUST equal the Add-on folder; `gh` active account MUST be `skh0h`.
- **Secrets:** `GEMINI_API_KEY` now lives in a **gitignored `.env`** (user added their REAL key this session). Never commit/print it. **Tests stay mock-only — no live Gemini calls in pytest.**
- **Pushing to `main` needs EXPLICIT USER authorization** — the auto classifier blocks pushes whose authority comes only from a handoff file. User authorized pushes in this session; re-confirm next session. Commit locally and push in a SEPARATE command (a combined `commit && push` gets the whole command denied).

## 3. THE KEY FINDING — parser_ai must be redesigned before live KSFO
The user clarified: **"the AI is to parse the airport, not speak."** The current `sidecar/parser_ai.py` (per the old handoff §5/§6) asks Gemini to **re-emit the entire AirportPicture** (all parking/nodes/segments). For a busy airport that does not scale:
- KSFO = **1144 nodes + 3131 arcs** (368 KB groundnet). Re-emitting them as structured JSON is ~150k+ output tokens — **far beyond `gemini-2.5-flash`'s output cap**. A live call will **truncate → fail schema validation → fall back to the code parser**, wasting the spend.
- **KSFO is NOT cached** (`fixtures/cache/airports.sqlite` does not exist). First AI run = full price; only repeats are free.

**Recommended refactor (the correct shape):**
1. The deterministic **`parser_code`** produces ALL geometry (nodes/arcs/coords/runways) — free, exact. Already works (real KSFO format handled: `N37 36.386` DMM coords, `0/1` booleans, `holdPointType`, directed-arc dedup, `MHz*100` freqs).
2. The **AI returns ONLY taxiway name labels** for the ~2981 unnamed arcs — e.g. a small `{(begin,end) -> taxiway_name}` map. Tiny output, costs cents, fits limits, caches well.
3. Merge the AI labels onto the code-parser geometry → `AirportPicture(source="ai")`; keep `taxi_graph`/`hash`/`generated_at` computed locally (unchanged).
4. Update `AIAirportResponse` to the label-only schema; update `tests/test_parser_ai.py` mocks to the new shape (still mock-only).
5. THEN run live on KSFO ONCE to validate + populate the cache (cheap with the new shape).

## 4. Phase 5 — end-to-end (BLOCKED here; the FlightGear Mac does this)
Pull on the FlightGear Mac → `fgfs --addon=…/addon --telnet=5501` → `python -m sidecar.main` → spawn at KSFO → "AI ATC" menu/dialog → Request Taxi → confirm spoken + logged route names REAL taxiways to the assigned runway. Offline test: disable network → cached picture + offline templates still produce a route.
- Mailbox props (Nasal ↔ sidecar): `/ai-atc/request/{type,callsign,runway,trigger}` · `/ai-atc/response/{text,ready}` · `/ai-atc/status` · `/ai-atc/log`.
- Sidecar entry: `python -m sidecar.main` (telnet host/port from config; defaults localhost:5501). Groundnet loaded from `fixtures/<ICAO>.groundnet.xml` by default (`_default_groundnet_loader`).

## 5. What shipped this session (for context)
- **Phase 2:** `airport_picture.py` (Pydantic models + `AIAirportResponse` + `build_taxi_graph`), `parser_code.py`, `parser_ai.py`, `cache.py` (SQLite, parameterized SQL), **real `fixtures/KSFO.groundnet.xml`**. 28 tests.
- **Phase 3:** `routing.py` (A* + haversine, `nearest_node`/`runway_goal_node`, `route_to_instructions` collapsing same-name arcs), `phraseology.py` (offline templates + online w/ `OfflineError` fallback). 16 tests. (NOTE: phraseology is the cheap online path; not the priority per the user — the AIRPORT parse is.)
- **Phase 4:** `fg_bridge.py` (telnet client, retry/backoff, polling subscribe), `tts.py` (queued `say` backend), `main.py` (`Sidecar` orchestration + SIGINT/SIGTERM), fleshed-out `addon/` (mailbox init, menu, dialog, Ctrl-Shift-T). 14 tests.
- **`afabe23`** `test(config)`: made `test_missing_api_key_yields_none` hermetic — it broke once the user added a real `.env`, because `load(env_path=None)` auto-discovers `.env` via `find_dotenv()` (walks up from `config.py`'s location, NOT the CWD). Fix: pass an explicit non-existent `env_path`. Config code itself is correct.

## 6. Deferred (still pending) — old handoff §10, non-blocking
`load()` missing `-> Settings`; redundant `socket.error` in `_is_offline`; trivial `test_smoke.py`; add `pytest-cov`; hoist `from google.genai import types`; `_client: Any` → `TYPE_CHECKING`; test that an unexpected exception type propagates out of `generate()`.
Also: untracked `V's/V1.md` and `.claude/` sit in the tree — NOT ours, left alone, never stage them.

## 7. Resume checklist
1. `cd "/Users/andrewkhoh/Documents/FlightGear Add-on"`; toplevel == this folder; `gh auth status` active = `skh0h`.
2. `git pull origin main` (HEAD `9c6d71a`); `.venv/bin/python -m pytest tests/ -q` → **85 green**.
3. Do the **parser_ai label-only refactor (§3)** inline → tests green → commit/push as skh0h (get explicit push OK).
4. Then live-validate on KSFO ONCE (populates cache), then hand to the FlightGear Mac for Phase 5 (§4).
5. Implement inline, lean — watch cost (§0).
