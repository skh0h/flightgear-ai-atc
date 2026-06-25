# Execute Phase-5 Handoff + Proofreading Checklist → /RESULTS

## Context

Two source documents drive this work:
- `HANDOFF/session-handoff-2026-06-24-phase5.md` — Phases 0–4 are complete (HEAD `9c6d71a`, 85 passing tests). The handoff's resume checklist (§7 step 3) says the **next action** is the `parser_ai` "label-only" refactor (§3), then green tests, then a *local* commit. Phase 5 in-sim validation (§4) requires a separate FlightGear Mac and is out of scope for execution here.
- `PLANS/proofreading-checklist.md` — a 163-item checklist for auditing `PLANS/implementation-plan.md` (a 132-line doc).

**Why the refactor matters:** the current `parser_ai` asks Gemini to re-emit the *entire* `AirportPicture` (all parking/nodes/segments). For KSFO (1144 nodes + 3131 arcs) that blows past gemini-2.5-flash's output-token cap, truncates, fails schema validation, and silently falls back to the code parser — wasting spend. The fix makes the deterministic code parser produce all geometry and asks the AI only for a small `{(begin,end) -> taxiway_name}` label map.

**User-confirmed scope:** Execute **both tracks**; on the code track **stop at a local commit** — no push to main, no live Gemini/KSFO API call.

This is a PM-orchestrated effort: Track A → Engineer (+ QA verify), Track B → Documentation/Research audit, then a Version Control agent for the local commit. Findings written to `/RESULTS/`.

---

## Track A — `parser_ai` label-only refactor (Engineer → QA)

**Files in play** (verified):
- `sidecar/airport_picture.py` — `AIAirportResponse` (lines 87–100, Pydantic), `AirportPicture` (103–118, unchanged target shape)
- `sidecar/parser_ai.py` — `parse_with_ai(...)` (108–174), prompt template (37–54), Gemini call (133–135), picture construction (146–157), offline fallback (136–144), airportinfo merge (162–171), divergence warn (173)
- `sidecar/parser_code.py` — `parse_groundnet(...)` (252–306) already returns full geometry; **no change needed**
- `tests/test_parser_ai.py` — 3 tests (lines 40, 54, 63) + `_FakeClient` (15–27) + `_ai_response()` factory (30–37)
- `sidecar/gemini_client.py` — `GeminiClient.generate(prompt, schema, ...)` (113–132); interface is schema-agnostic, **no change needed**

**A1 — Verify baseline.** `cd` to repo root; `git pull origin main` (expect HEAD `9c6d71a`); `.venv/bin/python -m pytest tests/ -q` → expect 85 green. Confirm `gh auth status` = `skh0h`. Do **not** stage untracked `V's/` or `.claude/`.

**A2 — Reshape the schema.** Replace `AIAirportResponse`'s 5 full-geometry fields with a label-only shape, e.g. `taxiway_labels: list[SegmentLabel]` where `SegmentLabel = {begin: int, end: int, name: str}` (a list of structured objects is more reliable for Gemini structured output than a dict keyed by a tuple). Keep it a Pydantic model so `generate()` is unchanged.

**A3 — Reshape `parse_with_ai`.** Call `parser_code.parse_groundnet(...)` unconditionally to get full geometry; call Gemini for the label map; merge labels onto the code-parser `segments` by `(begin, end)` key (apply name where AI provides one, leave code-parser name otherwise); set `source="ai"`; keep `groundnet_hash`, `generated_at`, and `build_taxi_graph(...)` computed locally exactly as today. Preserve the existing `OfflineError` → code-parser fallback and the `airportinfo` runway/frequency override. Rewrite `_PROMPT_TEMPLATE` to request *only* labels for unnamed segments (no geometry echo).

**A4 — Update mocks/tests.** Reduce `_ai_response()` to the label-only shape; update assertions in `test_ai_success_*` to verify labels are merged onto code-parser geometry and that unlabeled segments retain their code-parser names. Keep all 3 tests **mock-only** (no live calls). The offline-fallback and hash-consistency tests should still pass with minimal change.

**A5 — Minor §6 cleanups (batch in same commit).** `config.py` `load()` → add `-> Settings`; `gemini_client.py` → drop redundant `socket.error` in `_is_offline`, hoist `from google.genai import types`, `_client: Any` → `TYPE_CHECKING`; add a test that an unexpected exception type propagates out of `generate()`. (Skip `pytest-cov` add and `test_smoke.py` rewrite unless trivial — note as deferred.)

**A6 — QA gate.** `.venv/bin/python -m pytest tests/ -q` → all green (85+). Capture the count. No green, no commit.

**A7 — Local commit (Version Control agent).** Only after green:
`git -c user.name='skh0h' -c user.email='samuelkhoh84@gmail.com' commit` with a `feat(sidecar): parser_ai label-only schema` style message. **No `Co-Authored-By` trailer. No push.** Do not stage `V's/` or `.claude/`.

---

## Track B — Proofreading audit of `implementation-plan.md` (Documentation/Research)

Audit `PLANS/implementation-plan.md` against all 163 checklist items, grouped by the checklist's own sections (Structural, Technical Accuracy, Consistency, Completeness, Clarity, Feasibility, Testing, Technical Depth, References, Final). Cross-reference doc claims against actual repo state (Track-A exploration already confirmed file/module/port/SDK/env-var facts match).

**Known findings to bake in** (from exploration):
- No Table of Contents (item 5 — N/A but note); no true ASCII art architecture diagram, only a text mailbox sketch at lines 32–42 (item 8 — note).
- **Cross-document discrepancy:** plan says `--props=5501` (lines 30, 74, 122) which *matches checklist item 22*; the **handoff** says `--telnet=5501`. Flag as a handoff↔plan inconsistency for the user to reconcile (the plan is internally consistent).
- Model IDs use shorthand "2.5 Flash"/"2.5 Pro" with an explicit "confirm live model IDs" hedge (item 35 — pass).
- All file paths, module-per-phase lists, addon file list, `google-genai`, `GEMINI_API_KEY` verified present and correct.

Output: a per-item annotated table — **Pass / Issue / Note** with line references for every issue.

---

## Deliverables → `/RESULTS/` (currently an empty dir)

- `/RESULTS/proofreading-results-2026-06-24.md` — annotated 163-item audit + the handoff↔plan flag.
- `/RESULTS/parser-ai-refactor-summary-2026-06-24.md` — what changed, before/after test counts, deferred §6 items, and the explicit follow-ups left for the user (push to main; one live KSFO call to populate cache; Phase 5 in-sim on the FlightGear Mac).

---

## Verification

- **Track A:** `.venv/bin/python -m pytest tests/ -q` shows all tests green (≥85); `git log -1` shows one local commit authored `skh0h <samuelkhoh84@gmail.com>` with no Claude co-author trailer and no push (`git status` shows `ahead of origin/main by 1`). `git status` must still show `V's/` and `.claude/` untracked (not staged).
- **Track B:** `/RESULTS/proofreading-results-2026-06-24.md` exists with all 163 items annotated.
- **Out of scope (user follow-ups, flagged not done):** push to main, live Gemini/KSFO cache population, Phase 5 in-sim validation on the separate FlightGear Mac.
