# V1a Execution Plan — Device-Doable Work for the FlightGear Mac

## Context

The FlightGear AI ATC add-on (Python sidecar + thin Nasal add-on) has its
documented **V1 architecture (Phases 0–4) complete and on-tree**: `parser_code`,
`parser_ai` (label-only refactor), `routing` (A*), `phraseology`, `cache`,
`fg_bridge`, `tts`, `main` event loop, plus the Nasal add-on skeleton. The full
suite is **105 tests passing, 0 failing** (HEAD `86637fc`, committed locally,
**not pushed**).

What's **not** done is everything that needs a running simulator — **Phase 5
in-sim end-to-end verification** — plus a set of code items that V1a flags as
incomplete but that are fully implementable *without* FlightGear. This Mac has
no FlightGear yet (the user is installing it); the other Mac runs FlightGear
2024.1.5 and pulls via GitHub.

**This plan's scope (per the user):** do **everything implementable on this
device now**, push it so the FlightGear Mac can pull, and hand off a precise
**in-sim verification checklist** for the sim. It deliberately does **not**
re-document Phases 0–4 (see `PLANS/implementation-plan.md`) or the parser_ai
refactor (see `PLANS/phase5-execution-plan-2026-06-24.md` and
`RESULTS/parser-ai-refactor-summary-2026-06-24.md`) — it complements them.

**Source of truth for requirements:** `V's/V1a.md` (§6 sparse-name suppression,
§7 runway-selection completion list, §8/§9 Phase-2 priorities, §13 verification
& hygiene). All citations below point back to it.

**Intended outcome:** the FlightGear Mac can `git pull` and run a sidecar that
(a) auto-selects a departure runway from wind, (b) produces clean clearances
that suppress confusing sparse `via` clauses, and (c) is exercised through a
documented in-sim taxi-clearance demo — closing V1 and laying the device-doable
foundations for the Phase-2 top priorities.

---

## Execution model

Work is staged so each stage is independently shippable and locally verifiable
with `pytest` (no sim). Stages 0–2 are **build-now on this Mac**; Stage 3 is a
**checklist to run on the FlightGear Mac**. Implementation is delegated:
Engineer for code, QA for tests, Version Control for the push.

**Gate after every code change:** `cd "<repo>" && .venv/bin/python -m pytest tests/ -q`
must stay green (currently 105 passed). Authorship: `skh0h
<samuelkhoh84@gmail.com>`, **no Co-Authored-By trailer** (V1a §2).

---

## Stage 0 — Sync & hygiene (unblocks the FlightGear Mac first)

Goal: get the already-working tree onto GitHub and remove the small frictions
in V1a §13 so the other Mac has something clean to pull.

1. **Push to `origin/main`** (user-authorized). Pushes the local commit `86637fc`
   so the FlightGear Mac can `git pull`. Authored as skh0h, no Claude trailer.
2. **Track the fixture** — `fixtures/KSFO.groundnet.xml` is on disk but untracked
   (V1a §13). `git add` + commit it; the test suite and offline path depend on it.
3. **Reconcile the launch flag** — `README.md` documents `--telnet=5501` while
   `PLANS/implementation-plan.md` uses `--props=5501`. These are the *same*
   FlightGear property/telnet server (`--telnet` is the modern alias). Make the
   docs consistent and state explicitly which flag the launch scripts use.
4. **Dependency confirmation** (V1a §2, §13) — confirm the current `google-genai`
   package name and live model IDs against Google's official docs before relying
   on pinned versions; add `pydantic` to `requirements.txt` explicitly (currently
   only transitive via `google-genai`) so tests don't depend on a transitive pin.
5. **Cross-platform launch scripts** (V1a §2, §13) — add `run-mac.command`/shell
   and `run-windows.bat`/PowerShell that launch `fgfs` with
   `--addon=…/addon --telnet=5501 --httpd=8080` and start `python sidecar/main.py`.
   No installer.

**Files:** `README.md`, `requirements.txt`, new `scripts/run-mac.command`,
`scripts/run-windows.bat`. **Verify:** `pytest` still green; scripts shell-lint
cleanly (can't launch fgfs here).

---

## Stage 1 — Finish V1 logic locally (no sim; fully unit-testable)

Goal: close the V1a §6/§7 code gaps so the clearance pipeline is complete and
the sidecar can auto-select a runway.

1. **Sparse-name suppression** (V1a §6 refinement). Today
   `phraseology.phrase_offline` (`sidecar/phraseology.py:58`) appends `via …`
   whenever `taxi_route` is non-empty. Add a **coverage gate**: only include the
   `via` clause when the routed path has **≥3 named segments OR named arcs cover
   >30% of the path by arc count**; otherwise degrade to "taxi to runway XX"
   alone. The named/total ratio must be measured on the *routed path*, so compute
   coverage in `routing.route_taxiways` (return it, or a sibling helper) and let
   the caller decide whether to populate `Clearance.taxi_route`. Keep the empty-route
   contract ("taxi to runway XX") intact. **Tests:** extend
   `tests/test_phraseology.py` + `tests/test_routing.py` with sparse vs. dense
   cases.

2. **Wire runway auto-selection into the event loop** (V1a §7 items 1–3). Today
   `main._build_clearance` (`sidecar/main.py:116`) reads `REQ_RUNWAY` from the
   bridge and routes only when it's set; `runway_selection.taxi_to_runway` exists
   but is **unused**. Change the flow so that **when Nasal does not supply
   `REQ_RUNWAY`**, the sidecar calls `select_departure_runway` /
   `taxi_to_runway` (`sidecar/runway_selection.py`) using aircraft position
   (`POS_LAT`/`POS_LON`) and wind (Stage 2 METAR; until then `None` →
   deterministic fallback). Keep `REQ_RUNWAY` as an explicit **override**. Reuse
   the existing `taxi_to_runway` glue — do not duplicate A*/phraseology. **Tests:**
   extend `tests/test_main.py` with a fake bridge: runway-supplied path
   (unchanged) and auto-select path (runway resolved by the sidecar).

3. **Nasal → sidecar data pipe for runway data** (V1a §7 item 1, §12
   "Data-pipe note"). `groundnet.xml` has no runways — `picture.runways == []`
   from a fixture-only parse; runways come from in-sim `airportinfo()`. Have
   `addon/addon-main.nas` fetch `airportinfo()` runways + frequencies + parking
   and publish them under the `/ai-atc/` mailbox at first request; have the
   sidecar read them and populate `picture.runways`. Both ends are codeable here;
   end-to-end correctness is verified in Stage 3. **Tests:** sidecar-side
   population is unit-tested against a synthetic mailbox payload (Nasal side is
   verified in-sim).

**Files:** `sidecar/phraseology.py`, `sidecar/routing.py`, `sidecar/main.py`,
`sidecar/runway_selection.py` (caller only), `addon/addon-main.nas`, tests.

---

## Stage 2 — Phase-2 foundations that need no sim (V1a §8/§9 top priorities)

Goal: implement the device-doable Phase-2 top-5 items. These are bounded,
offline-testable, and reuse Stage-1 wiring.

1. **METAR-driven runway selection** — Priority #1 (V1a §8.1, §9). New
   `sidecar/metar.py`: fetch METAR from `aviationweather.gov`, parse wind
   dir/speed, expose `get_wind(icao) -> (dir, kt) | None` with the same
   offline-fallback contract as the rest of the sidecar (network failure → `None`
   → `select_departure_runway` calm fallback). Feed the wind into the Stage-1
   auto-selection path. **Tests:** new `tests/test_metar.py` with a mocked HTTP
   response + an offline-fallback case.

2. **Callsign + aircraft-type personalization** — Priority #2 (V1a §8.2). Read
   `/sim/multiplay/callsign` and `/sim/aircraft-id` (via the mailbox/bridge) and
   inject aircraft type into the Gemini prompt in `phraseology._build_prompt`
   (`sidecar/phraseology.py:72`); thread type into runway filtering where a
   type-specific crosswind limit applies. **Tests:** extend
   `tests/test_phraseology.py` (prompt includes type) and runway-selection tests.

3. **Replay / regression harness** — Priority #3 (V1a §8.3). Fully offline by
   design. Extend the `main` loop to log each request's property snapshot +
   request/response to a session **JSONL**; add a `--replay <session.jsonl>` mode
   that re-runs routing/phraseology against golden files **with no FlightGear
   running** and diffs the output. This is the safety net for every later
   refactor. **Tests:** new `tests/test_replay.py` round-tripping a small session.

**Deferred (need in-sim data, out of device scope):** phraseology grading/debrief
(V1a §8.4 — offline-scoreable but lower value without real readback capture) and
SID assignment (V1a §8.5 — needs `/autopilot/route-manager` properties). Note
them as the next Phase-2 work once the sim is available; do not build here.

**Files:** new `sidecar/metar.py`, `sidecar/replay.py` (or `main.py` flag),
edits to `sidecar/phraseology.py`, `sidecar/main.py`, `sidecar/runway_selection.py`,
new tests.

---

## Stage 3 — In-sim verification checklist (run on the FlightGear Mac)

Hand-off, not build. From V1a §13. On the FlightGear Mac after `git pull`:

1. Create `.venv`, `pip install -r requirements.txt`, add `.env` with
   `GEMINI_API_KEY=…` (gitignored).
2. Launch: `fgfs --addon=…/addon --telnet=5501 --httpd=8080`; start
   `python sidecar/main.py` (or the Stage-0 launch script).
3. **One live KSFO Gemini call** to populate the cache (validates the label-only
   parser_ai end-to-end; expected cost ~cents with the label-only schema).
4. Spawn at **KSFO** (has groundnet data); request taxi via the dialog; confirm
   the spoken + logged clearance **names real taxiways** and a valid route to the
   assigned runway, with the ATC text shown prominently at the top of the dialog.
5. **Runway auto-select test:** clear `REQ_RUNWAY`; confirm the sidecar selects a
   plausible runway from live wind and that `runway_entry_node` maps to a real
   hold-short/entry node (V1a §7 item 2).
6. **Offline test:** disable the network → confirm the cached picture + template
   phraseology still produce a specific route (graceful degradation).
7. Capture a session JSONL (Stage 2.3) as the first golden regression file.

---

## Risk & rollback

- **Runway data absent until in-sim** — Stages 1.2/2.1 are unit-tested with
  synthetic/mocked runways and wind; real `airportinfo` runway data is only
  proven in Stage 3. If the Nasal pipe (1.3) mis-maps fields, the sidecar
  degrades to the existing "taxi to runway XX" path — no crash (existing
  graceful-degradation contract).
- **Coverage gate too aggressive** (1.1) — if it suppresses `via` on routes that
  should keep it, tune the threshold (3 segments / 30%); behavior stays safe
  either way.
- **`google-genai` / model-ID drift** (0.4) — confirm names against official docs
  before pinning; tests mock Gemini, so local green ≠ live-call correctness (that
  is Stage 3.3's job).
- **Push** is the only irreversible/outward action; it runs only with the user's
  per-session authorization.

## Verification (local, this Mac)

- After each stage: `cd "<repo>" && .venv/bin/python -m pytest tests/ -q` — must
  stay green (baseline 105 passed) and grow with the new Stage 1–2 tests.
- New modules (`metar.py`, replay) covered by mocked-HTTP / golden-file tests; no
  live Gemini or FlightGear dependency in the local suite (one live smoke test
  stays gated behind `GEMINI_API_KEY`).
- Cross-platform scripts shell-lint cleanly.

## Deliverable note

Per the request, the **first execution step is to persist this plan into the repo**
as `PLANS/v1a-execution-plan-2026-06-24.md` (this file is the plan-mode working
copy). Subsequent stages execute against that committed plan.
