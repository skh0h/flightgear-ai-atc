# AI ATC Add-on — Meticulous Test & Verification Checklist

> **Purpose:** A self-contained run-book for an agent (or human) with **no prior context** to verify the
> entire phased-roadmap build (Phases 0–10) is correct and wired. Run top to bottom. Each item has a
> **command/action** and an **expected result**. Mark `[x]` only when the expected result is observed verbatim.
>
> **Authoritative gate:** the full `pytest` suite (Section 1) **must** report `560 passed, 0 failed`.
> Everything else explains *what that green number actually proves* and what it does **not** (runtime/in-sim items).
>
> Repo root (all paths relative to it): `/Users/andrewkhoh/Documents/FlightGear Add-on`
> Stack: Python 3.13 + `.venv`, `pytest`; FlightGear add-on = Nasal (`addon/`) + Python sidecar (`sidecar/`),
> bridged over FG telnet `:5501` / httpd `:8080`. Run all `python3`/`pytest` from the repo root.

---

## 0. Preconditions & Environment

- [ ] **Repo present & on the right tip.** `git -C "<repo>" log --oneline -1` → newest commit is `feat(phase-10): cross-cutting architecture …`. `git status --short` → **empty** (clean tree).
- [ ] **Python & pytest.** `python3 --version` → 3.13.x. `python3 -m pytest --version` → pytest 8.x.
- [ ] **Module inventory.** `ls -1 sidecar/*.py | wc -l` → **31**. `ls -1 tests/test_*.py | wc -l` → **32**.
- [ ] **No secret required for tests.** Tests are fully offline — **no** `GEMINI_API_KEY`, no network, no live FlightGear, no audio. If any test reaches the network, that is a **FAIL** (regression).
- [ ] **(In-sim only)** FlightGear 2024.1.6 installed at `/Applications/FlightGear.app` (needed only for Section 10).

---

## 1. Automated Test Suite — the authoritative gate

- [ ] **Full suite green.**
  `python3 -m pytest -q` → final line **`560 passed, 1 warning`** (0 failed, 0 errored).
  The single warning is a third-party `PydanticDeprecatedSince212` from `google.genai` in `test_gemini_client.py` — **expected/benign**.
- [ ] **Clean collection (no import/collection errors).**
  `python3 -m pytest --collect-only -q 2>&1 | tail -3` → ends with the collected count, **no `ERROR`** lines.
- [ ] **Determinism — run twice, identical.**
  Run `python3 -m pytest -q` a second time → still `560 passed`. (Catches order-dependence / hidden randomness / time-of-day coupling.)
- [ ] **Every test module collects & passes (no silent skips of whole files).** Confirm each file below appears and passes:
  ```
  pytest tests/test_airport_picture.py tests/test_airport_pipe.py tests/test_cache.py tests/test_config.py \
         tests/test_fg_bridge.py tests/test_gemini_client.py tests/test_main.py tests/test_metar.py \
         tests/test_parser_ai.py tests/test_parser_code.py tests/test_phraseology.py tests/test_replay.py \
         tests/test_routing.py tests/test_runway_selection.py tests/test_smoke.py tests/test_tts.py \
         tests/test_stt.py tests/test_personality.py tests/test_session_log.py tests/test_traffic.py \
         tests/test_state.py tests/test_procedures.py tests/test_airspace.py tests/test_simbrief.py \
         tests/test_briefing.py tests/test_scenario.py tests/test_career.py tests/test_kneeboard.py \
         tests/test_coach.py tests/test_blackboard.py tests/test_guardrail.py tests/test_i18n.py -q
  ```
  → all 32 files run; total still `560 passed`.

---

## 2. Build / Import / CLI Sanity

- [ ] **All 31 sidecar modules import cleanly** (catches a broken import the test suite might not exercise):
  ```
  python3 -c "import importlib,pkgutil,sidecar; [importlib.import_module('sidecar.'+m.name) for m in pkgutil.iter_modules(sidecar.__path__)]; print('ALL SIDECAR MODULES IMPORT OK')"
  ```
  → prints `ALL SIDECAR MODULES IMPORT OK`.
- [ ] **CLI entrypoint help.** `python3 -m sidecar.main --help` → shows `--selftest`, `--selftest-telnet`, `--replay`.
- [ ] **Self-test (offline path).** `python3 -m sidecar.main --selftest` → prints an `AI (connected)` **or** `offline (...)` line and exits **non-crashing** (exit 1 is acceptable with no key; it must not traceback).
- [ ] **No stray top-level side effects.** Importing `sidecar.main` must not open a socket or block. (Covered by import check above; confirm it returns instantly.)

---

## 3. Addon XML & Nasal Validity

- [ ] **All four XML files well-formed.**
  ```
  xmllint --noout addon/gui/dialogs/ai-atc.xml addon/addon-config.xml addon/addon-metadata.xml addon/addon-menubar-items.xml && echo XML_OK
  ```
  → prints `XML_OK` (no errors). *(If `xmllint` is absent, install libxml2 or skip with a noted FAIL-to-verify.)*
- [ ] **Nasal brace/paren balance** in `addon/addon-main.nas`:
  ```
  python3 - <<'PY'
  s=open('addon/addon-main.nas').read()
  print('braces', s.count('{'), s.count('}'), '| parens', s.count('('), s.count(')'))
  PY
  ```
  → `{` count == `}` count, and `(` count == `)` count (expected ≈ 67/67 and 357/357; exact numbers may drift — they must be **equal**).
- [ ] **FG2026 metadata forward-compat.** `addon/addon-metadata.xml` contains `<min-FG-version …>2020.0.0` and `<max-FG-version …>2099.0.0` and a `<meta><file-type>FlightGear add-on metadata</file-type>` block.

---

## 4. Cross-Layer Wiring — the "all things wired correctly" gate

The system has **3 layers** that must agree on every request token: the **XML buttons** (`aiatc.request("X")`),
the sidecar **`phrase_offline`** branches (`phraseology.py`), and the **`main.py`** control/data branches.
A token with a button but no branch silently mis-renders as a **taxi** clearance — this section catches that.

- [ ] **Enumerate UI tokens** (ignore the 4 commented placeholders in `ai-atc.xml`):
  `grep -ohE 'aiatc\.request\("([a-z0-9_]+)"\)' addon/gui/dialogs/ai-atc.xml addon/addon-config.xml | sort -u`
- [ ] **Enumerate offline branches:** inspect `phraseology.py` `phrase_offline` `ctype == "..."` / `in ("...")` branches.
- [ ] **Every UI token resolves** to a `phrase_offline` branch **OR** a `main.py` control verb. The only UI tokens that are control verbs (no offline branch, handled in `main.py`) are **`cancel`** and **`readback`**. Any *other* UI token lacking a branch is a **BUG**.
- [ ] **Expected token set (34):** `airfield_in_sight, airspace_check, approach, arrival_clearance, career, ctaf, diversion, expect_approach, flow_control, fss_briefing, gear_emergency, go_around, holding, ifr_clearance, ils, intersection_departure, kneeboard, lahso, mayday, min_fuel, pan_pan, pirep, pushback, radio_check, readback, scenario, simbrief, squawk_7500, squawk_7600, squawk_7700, takeoff, taxi, weather_deviation, windshear`. *(Plus `relief_handoff` — has a branch + `main.py` path but **no** button by design; reachable only internally. Not a bug.)*
- [ ] **`_TYPE_GUIDANCE` mirrors every offline branch** (so the online Gemini path phrases each type). Spot-check that each token above appears as a `_TYPE_GUIDANCE` key in `phraseology.py`.
- [ ] **`globals.aiatc` exposes every helper called from XML.**
  `grep -ohE 'aiatc\.([a-z_]+)\(' addon/gui/dialogs/ai-atc.xml addon/addon-config.xml | sort -u`
  → the set is exactly `{request, ptt, set_runway_active, set_mode, set_language, set_region}`, and
  `grep 'globals.aiatc' addon/addon-main.nas` registers **all six**.
- [ ] **No spelling drift** (underscores/case) of any token between the three layers (e.g. `squawk_7500`, `airfield_in_sight`, `intersection_departure`, `weather_deviation` identical everywhere).

---

## 5. Property Mailbox Contract (sidecar ↔ Nasal must use identical paths)

Verify each path constant in `sidecar/main.py` has the **identical string** referenced in `addon/addon-main.nas`
(writer/reader directions in parentheses). Grep both sides for each path.

- [ ] **Request (Nasal writes → sidecar reads):** `/ai-atc/request/type`, `/request/callsign`, `/request/runway`, `/request/trigger`, `/request/route`, `/request/destination`, `/request/altitude`, `/request/squawk`
- [ ] **Response (sidecar writes → Nasal reads):** `/ai-atc/response/text`, `/response/ready`, `/ai-atc/status`
- [ ] **Heartbeat/mode (sidecar → Nasal):** `/ai-atc/sidecar/heartbeat`, `/ai-atc/sidecar/mode`
- [ ] **Airport pipe (Nasal → sidecar):** `/ai-atc/airport/runway_count`, `/airport/runway[i]/{id,heading,thr_lat,thr_lon,length,ils_freq,active}`, `/airport/freq/{ground,tower,atis,approach,departure}`, `/airport/icao`, `/airport/name`
- [ ] **Traffic / world (sidecar → Nasal):** `/ai-atc/traffic/count`, `/traffic/summary`, `/ai-atc/chatter`, `/ai-atc/flight-phase`, `/ai-atc/kneeboard`, `/ai-atc/guardrail`
- [ ] **Airspace (Nasal → sidecar):** `/ai-atc/airspace/class`, `/airspace/warning`
- [ ] **Readback (Phase 5):** `/ai-atc/readback/heard`, `/readback/result`
- [ ] **Personality/config (Nasal → sidecar / display):** `/ai-atc/controller/name`, `/ai-atc/mode`, `/ai-atc/local-hour`, `/ai-atc/language`, `/ai-atc/region`, `/ai-atc/nearest-airport/{icao,name}`
- [ ] **Every `<property>`/`format` binding in `ai-atc.xml`** points at a path the sidecar or Nasal actually writes (no dead bindings rendering blank).

---

## 6. Per-Phase Functional Verification (sidecar behavior, offline)

For each phase, run the targeted tests **and** the inline behavior probe. Probes use the deterministic offline path
(no Gemini), so they assert real behavior, not just "tests exist."

- [ ] **Phase 0 — Stabilize.** `pytest tests/test_fg_bridge.py tests/test_cache.py tests/test_metar.py tests/test_gemini_client.py tests/test_parser_code.py -q` green. Probes:
  - METAR MPS→kt: `python3 -c "import sidecar.metar as m; print(m._parse_wind('24003MPS'))"` → `(240.0, 6.0)`.
  - Cache OperationalError degrades to miss (covered in `test_cache.py`), cwd-independent path (relative resolves under repo root).
  - Gemini non-offline `ClientError` (400/404) → `OfflineError` (in `test_gemini_client.py`).
  - Malformed groundnet XML → clear `ParseError` (in `test_parser_code.py`).
- [ ] **Phase 1 — Request framework.** `pytest tests/test_phraseology.py -q`. Probe:
  `python3 -c "from sidecar.phraseology import phrase_offline,Clearance as C; print(phrase_offline(C(callsign='UAL1',clearance_type='approach',active_runway='28R')))"` → an **approach** clearance (NOT a taxi line).
- [ ] **Phase 2 — Mode A/B.** `pytest tests/test_runway_selection.py tests/test_routing.py tests/test_airport_pipe.py -q`. Probes:
  - `active` filter: `select_departure_runway` restricts to active ends when any active, else all (in tests).
  - `routing.nearest_node_with_distance` returns `(idx, metres)`; `read_ai_traffic` snaps `/ai/models/...` (fake-bridge tests).
- [ ] **Phase 3 — Emergencies.** Probe each: `python3 -c "from sidecar.phraseology import phrase_offline,Clearance as C; [print(phrase_offline(C(callsign='N1',clearance_type=t))) for t in ('mayday','pan_pan','squawk_7700','min_fuel','go_around','gear_emergency')]"` → each renders distinct emergency phraseology, none as taxi. Diversion with/without `/ai-atc/nearest-airport/*` (in `test_main.py`).
- [ ] **Phase 4 — Personality/memory.** `pytest tests/test_personality.py tests/test_session_log.py -q`. Probe determinism:
  `python3 -c "from sidecar.personality import generate_persona as g; print(g('seedX').name==g('seedX').name)"` → `True`.
  Mood bands: `mood_for(0)`→`fresh`, `mood_for(25)`→`weary`, `mood_for(2,quiet_night=True)`→`reflective`.
- [ ] **Phase 5 — Voice.** `pytest tests/test_tts.py tests/test_stt.py -q`. Probes:
  - `python3 -c "from sidecar.tts import voice_for; print(voice_for('ground')!=voice_for('tower'))"` → `True`.
  - `python3 -c "from sidecar.stt import grade_readback as gr; r=gr('runway 28R cleared for takeoff','cleared for takeoff'); print(r.ok, r.missing)"` → `ok` reflects token overlap; `missing` lists dropped tokens.
  - Backend fallback: with no Piper, `make_tts_backend` returns a `SayBackend` (in tests).
- [ ] **Phase 6 — Living world.** `pytest tests/test_traffic.py -q`. Probes:
  - `python3 -c "from sidecar.traffic import wake_category as w; print(w('A388'),w('B744'),w('A320'),w('C172'))"` → `super heavy medium light`.
  - `separation_advice('B744','C172')` non-empty; `ambient_chatter(...,seed='s')` deterministic.
- [ ] **Phase 7 — IFR.** `pytest tests/test_state.py tests/test_procedures.py -q`. Probes:
  - State machine forward-only: `python3 -c "from sidecar.state import FlightStateMachine as F; m=F(); m.on_request('taxi'); print(m.phase); m.on_request('pushback'); print(m.phase)"` → advances to taxi-out, does **not** regress to pushback.
  - Holding entry: `python3 -c "from sidecar.procedures import holding_entry as h; print(h(90,270))"` → one of `direct/teardrop/parallel` (deterministic).
  - CRAFT: `build_craft_clearance(...).as_phrase('DAL1')` produces a full "cleared to … via … climb maintain … departure … squawk …" line. `assign_edct` wraps past midnight.
- [ ] **Phase 8 — Grounding.** `pytest tests/test_airspace.py tests/test_simbrief.py tests/test_briefing.py -q`. Probes:
  - `airspace_class_at` returns most-restrictive containing class; `brasher_warning` non-empty below `min_safe_ft`.
  - `parse_ofp({...})` tolerant of missing keys; `fetch_ofp` uses an **injectable opener** (no real network in tests).
  - `ctaf` token is a **self-announce** with **no** "Contact <freq>" controller tail.
- [ ] **Phase 9 — Training.** `pytest tests/test_scenario.py tests/test_career.py tests/test_kneeboard.py tests/test_coach.py -q`. Probes:
  - `generate_scenario('s')` deterministic; `record_event` updates points & `career_rank` thresholds; `load_career`/`save_career` round-trip via a temp file; `build_kneeboard(...)` stable multi-line.
- [ ] **Phase 10 — Cross-cutting.** `pytest tests/test_blackboard.py tests/test_guardrail.py tests/test_i18n.py -q`. Probes:
  - Guardrail catches a bad clearance: `python3 -c "from sidecar.guardrail import validate_clearance as v; print(v('Cleared for takeoff runway 9, hold short runway 9.', callsign='').ok)"` → `False` with issues (contradiction + missing callsign). A valid takeoff line → `ok=True`.
  - `i18n.language_directive('en')==''` and `language_directive('fr')` non-empty; `apply_region('… the active runway …','uk')` substitutes.

---

## 7. End-to-End Request Flow (offline, via the Sidecar object)

- [ ] **`handle_trigger` writes the full response contract for a normal request.** Drive a `Sidecar` with a fake bridge (pattern in `tests/test_main.py::_make` / `_make_with_picture`): set `/ai-atc/request/type` + trigger, call `handle_trigger()`, then assert: `RESP_TEXT` non-empty, `RESP_READY == 1`, `STATUS == "idle"`, `REQ_TRIGGER == 0`. (This is already asserted across `test_main.py`; confirm those tests pass.)
- [ ] **Resilience — exception never swallows the reply.** With a client/bridge that raises mid-request, `handle_trigger` still writes a fallback `RESP_TEXT` + `RESP_READY=1` + `STATUS=idle` (see `test_handle_trigger_exception_path…`). **Critical** — verify it passes.
- [ ] **Advisory features never block the reply.** Traffic-read failure, guardrail issues, persona/memory/fsm errors must all be caught so `RESP_TEXT`/`RESP_READY` are always written (per-phase `…raises…still writes…` tests).

---

## 8. Determinism & Replay Regression

- [ ] **Replay harness.** `pytest tests/test_replay.py -q` green. The harness re-renders a recorded JSONL session via the **offline** path and diffs against golden text (`python3 -m sidecar.main --replay <session.jsonl>` returns 0 when all match).
- [ ] **Seeded determinism (no time/random leakage):** `personality.generate_persona`, `scenario.generate_scenario`, `traffic.ambient_chatter`, and `procedures.holding_entry` all return identical output for identical inputs across repeated runs (Section 6 probes + their tests).

---

## 9. Config Surface

- [ ] **`.env.example` documents every supported var** and matches `sidecar/config.py`: `GEMINI_API_KEY, FG_TELNET_HOST, FG_TELNET_PORT, CACHE_DB_PATH, AI_TAXIWAY_LABELS, METAR_ENABLED, SESSION_LOG_PATH, GEMINI_MODEL_FAST, GEMINI_MODEL_PRO, LOG_LEVEL, TTS_VOICE, TTS_ENGINE, PIPER_BIN, PIPER_VOICE, STT_ENGINE, WHISPER_BIN, RADIO_STATIC, CAREER_PATH, LANGUAGE, REGION`.
- [ ] **Defaults are safe/offline:** `AI_TAXIWAY_LABELS` default **off** (no AI-fabricated taxiway names — policy), `TTS_ENGINE=say`, `STT_ENGINE=none`, `LANGUAGE=en`, `REGION=us`, `METAR_ENABLED=true`. `pytest tests/test_config.py -q` green.

---

## 10. In-Sim End-to-End (FlightGear 2024.1.6) — RUNTIME, manual

> Not covered by `pytest`. Requires a live FG session. Launch via `open -a FlightGear --args …`
> (a raw-binary background launch hangs at GL init — use `open -a`). Easiest: double-click `scripts/run-mac.command`.

- [ ] **Launcher.** Double-click `scripts/run-mac.command` → it auto-detects `fgfs`, opens telnet `:5501`, starts the sidecar, tees to `sidecar.log`. No silent hang.
- [ ] **Panel loads** (add-on menu → Open ATC Panel) — header shows airport ICAO + name; **Backend** flips to `Connected (AI)` or `Connected (offline templates)` within ~15 s.
- [ ] **Each request type:** click Pushback/Taxi/Takeoff, the Arrival/Emergency/IFR/Briefings/Training/Weather buttons → each yields a **spoken** clearance + a `[atc]` transcript line. **No** button produces a generic taxi clearance by mistake.
- [ ] **Watchdog / never-hang:** kill the sidecar mid-session → within ~8–15 s the panel shows `Not running…` and status returns to idle (no stuck "Processing").
- [ ] **Airport change:** change `/sim/presets/airport-id` → frequency/runway/airspace displays refresh.
- [ ] **Mailbox round-trip:** `Phase:`, `Traffic:`, `Chatter:`, `Controller:`, `Airspace:`, `Guardrail:`, `Kneeboard` fields populate live.

---

## 11. Runtime-Dependency Features — validate ONLY when the resource exists

These are **wired with graceful fallback + mocked tests**; they cannot be exercised end-to-end without the resource.
Mark **N/A (resource absent)** if you can't supply it; that is not a FAIL.

- [ ] **Piper TTS** — set `TTS_ENGINE=piper` + install `piper`; `make_tts_backend` should pick `PiperBackend` and speak. Absent → falls back to macOS `say`.
- [ ] **Whisper STT** — `STT_ENGINE=whisper` + install `whisper`; `WhisperBackend.transcribe` works. Absent → `OfflineSTTError`, readback grading still works on typed text.
- [ ] **SimBrief** — provide a real OFP JSON via `fetch_ofp(username)`; `parse_ofp` maps it to a `FlightPlan`.
- [ ] **Navdata / CIFP (SIDs/STARs/airways)** — supplied via mailbox/fixtures; live CIFP needs the data feed.
- [ ] **Multiplayer (#41)** — position sync routes through the `/ai/models` reader; full multi-position sync needs a multiplayer backend.
- [ ] **PTT joystick** — the `Ctrl-R` keybinding fires `aiatc.ptt()`; a hardware joystick button needs an in-sim binding.

---

## 12. Repository / Delivery Integrity

- [ ] **11 phase commits present:** `git log --oneline main..phase-10-wildcards` → `feat(phase-0…)` … `feat(phase-10…)` (11 commits).
- [ ] **11 stacked PRs open** (#1 `phase-0-stabilize → main`, then each phase → the previous): `gh pr list --state open`.
- [ ] **`.gitignore` excludes tooling/scratch:** `.claude/`, `sidecar.log`, `*.stub-bak`, `.env`, `*.sqlite`, `__pycache__/`, `.venv/`.
- [ ] **No secrets committed:** `git log -p -- .env 2>/dev/null` empty; `.env` is gitignored.

---

## Pass / Fail Summary

| Section | Gate | Result |
|---|---|---|
| 1 | `pytest` → **560 passed, 0 failed** | ☐ |
| 2 | 31 modules import; CLI ok | ☐ |
| 3 | 4 XML valid; Nasal balanced | ☐ |
| 4 | 0 orphan tokens; 6 globals helpers; no spelling drift | ☐ |
| 5 | mailbox paths match both sides | ☐ |
| 6 | per-phase probes behave | ☐ |
| 7 | response contract + resilience | ☐ |
| 8 | replay + determinism | ☐ |
| 9 | config surface + safe defaults | ☐ |
| 10 | in-sim E2E (runtime) | ☐ N/A allowed |
| 11 | runtime-dep features | ☐ N/A allowed |
| 12 | repo/PR integrity | ☐ |

**Overall = PASS** iff Sections 1–9 and 12 are all ✅ (Sections 10–11 may be `N/A` when the runtime resource is absent).

---

### Fast path (CI-style, ~1 min)
```bash
cd "/Users/andrewkhoh/Documents/FlightGear Add-on"
python3 -m pytest -q                                   # expect: 560 passed
python3 -c "import importlib,pkgutil,sidecar; [importlib.import_module('sidecar.'+m.name) for m in pkgutil.iter_modules(sidecar.__path__)]; print('IMPORTS OK')"
xmllint --noout addon/gui/dialogs/ai-atc.xml addon/addon-config.xml addon/addon-metadata.xml addon/addon-menubar-items.xml && echo XML_OK
grep -ohE 'aiatc\.request\("([a-z0-9_]+)"\)' addon/gui/dialogs/ai-atc.xml addon/addon-config.xml | sort -u   # cross-check vs phraseology.py branches
```
If `560 passed` + `IMPORTS OK` + `XML_OK` and every UI token has a `phrase_offline` branch (or is `cancel`/`readback`), the build is verified.
