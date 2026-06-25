# Parser AI Label-Only Refactor Summary

**Date:** 2026-06-24  
**Scope:** Track A of Phase 5 execution — `parser_ai` architecture refactor (completed)  
**Test Result:** 105 passed, 1 warning in 1.83s

---

## Why This Refactor Was Needed

The original `parser_ai` implementation asked Gemini to re-emit the **entire** `AirportPicture` object — all parking, nodes, segments, runways, and frequencies — alongside the taxiway labels. For large airports this became prohibitive:

- **KSFO example:** 1144 nodes, 3131 arcs
- **Result:** Output exceeded `gemini-2.5-flash`'s token cap, causing truncation, failed schema validation, and silent fallback to the code parser
- **Cost:** Wasted API spend on requests that always failed at validation

**Solution:** The deterministic code parser already produces **all geometry** correctly. The AI now returns **only taxiway-name labels** — a small, bounded output that fits well within Gemini's limits, and merges seamlessly into the code-derived geometry.

---

## What Changed

### `sidecar/airport_picture.py`
- **New type:** `SegmentLabel(begin: int, end: int, name: str)` — Pydantic model for AI-labeled segment
- **Schema reduction:** `AIAirportResponse` reduced from 5 full-geometry fields to a single field:
  - `taxiway_labels: list[SegmentLabel]`
- **Invariant:** The final `AirportPicture` schema is **unchanged** — all fields remain as the code parser produces them

### `sidecar/parser_ai.py`
Complete rewrite of `parse_with_ai()` function:

1. **Unconditional code-parser call:** Always calls `parser_code.parse_groundnet()` first to build full geometry
2. **AI-only labels:** Calls Gemini with new prompt requesting **only taxiway-name labels** (no geometry echo)
3. **Offline fallback:** On `OfflineError`, immediately returns the code-derived picture with `source="code"` (fallback path preserved)
4. **Merge logic:** On success, builds an undirected label lookup `{(begin, end): name}`, applies labels onto the code-parser segments:
   - Labeled segments get their AI-resolved name
   - Unlabeled segments keep their code-parser name (no overwrite)
5. **Immutable geometry fields:** `groundnet_hash`, `generated_at`, and `taxi_graph` remain exactly as the code parser computed them — never modified by AI
6. **Return:** Picture with `source="ai"` on success, or `source="code"` on offline failure

**Removed vacuous code:**
- `_warn_on_divergence()` — no longer needed (geometry is always code-derived, so counts always match)
- `_source_counts()` — no longer needed for the same reason

**Prompt template rewritten:**
- Old: "Re-emit the entire AirportPicture including parking, nodes, segments..."
- New: "Return only taxiway labels as a JSON list of `{begin, end, name}` objects..."

### `sidecar/gemini_client.py` (Minor Cleanups § 6)
- Removed redundant `socket.error` check in `_is_offline()` (already covered by `OSError`)
- Moved `_client` type annotation under `TYPE_CHECKING` guard:
  - Before: `_client: Any`
  - After: `_client: Optional[GenerativeModel]` (only in type-checking)
  - Runtime: `_client = None` (untyped but works correctly)

### `sidecar/config.py`
- Already had its `-> Settings` annotation; no change needed

### Test Changes: `tests/test_parser_ai.py`
- **Mock updates:** `AIAirportResponse` mock updated to label-only shape
- **New assertions:** Merge logic verified with:
  - Labeled vs unlabeled segment handling
  - Boundary cases (empty labels, malformed responses)
- **2 new merge tests added:**
  - Test 1: Verifies labeled segment names are applied
  - Test 2: Verifies unlabeled segments keep code-parser names
- **Integration:** All mocks updated to reflect new label-only interface

### Test Changes: `tests/test_gemini_client.py`
- **New test:** Unexpected exception type (not `OfflineError`) propagates out of `generate()`, not swallowed
- Ensures offline detection logic is precise and doesn't mask real failures

### Test Changes: `tests/test_airport_picture.py`
- **1 assertion updated:** Reflects new schema reduction (geometry fields unchanged, labels field added)

---

## Test Results

**Baseline:** 85 passed  
**Final:** 105 passed, 1 warning in 1.83s

All test suites pass. No live API calls were made (mock-only coverage). The warning is pre-existing and outside the refactor scope.

---

## Deferred (Out of Approved Scope)

Per Phase 5 execution scope, these items were intentionally deferred:

1. **`pytest-cov` integration:** Not added; baseline coverage tracking already in place
2. **`test_smoke.py` rewrite:** Trivial smoke tests not prioritized; should be addressed in a separate pass
3. **Lazy import design constraint:** The `from google.genai import types` import stays as the first statement **inside** `generate()` (not hoisted to module top). This is required to maintain offline-import behavior — hoisting would break the offline smoke test. This constraint is documented; no change.

---

## Related Finding (From Proofreading Audit)

A flag inconsistency was discovered in documentation:

- **README.md (lines 26, 65):** Uses `--telnet=5501`
- **implementation-plan.md:** Correctly uses `--props=5501`
- **Status:** Mismatch should be reconciled in README (implementation plan is authoritative)

This is a separate documentation issue, not part of the parser_ai refactor, but flagged for follow-up.

---

## Follow-Ups Left for the User

The following tasks were explicitly **NOT** completed (outside approved scope and/or require user action):

### 1. Push to `origin/main`
The refactor commit was created locally on branch `graphql` only. Per your handoff instructions, pushing requires per-session authorization. This is deferred pending user confirmation.

### 2. Live Gemini/KSFO Validation
One end-to-end call against real Gemini API and KSFO fixture is needed to:
- Validate the label-only response shape works with Gemini's actual output
- Populate the SQLite cache at `fixtures/cache/airports.sqlite`
- Note: Cache does not yet exist; this call will spend real tokens (expected to be cheap with label-only output)

### 3. Phase 5 In-Sim Validation
Full validation on FlightGear Mac:
1. Launch FlightGear with the add-on
2. Start the sidecar with this refactored code
3. Spawn at KSFO
4. Request taxi routing
5. Verify spoken/logged route names use real taxiways (not code-parser fallback)
6. Run offline sub-test to verify fallback path works

---

## Summary

The refactor successfully constrains AI output to labels only, eliminating token-cap overruns and wasted spend on invalid schemas. All 105 tests pass. The code-parser geometry path is now immutable (no AI-driven divergence), and the offline fallback is preserved. Ready for live validation and in-sim testing.
