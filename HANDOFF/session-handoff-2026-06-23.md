# Session Handoff — FlightGear AI ATC Add-on

**Date:** 2026-06-23
**Repo:** `/Users/andrewkhoh/Documents/FlightGear Add-on` (nested git repo)
**Remote:** `https://github.com/skh0h/flightgear-ai-atc` (private)
**Current branch:** `main` @ commit `89313fc` (author `skh0h <samuelkhoh84@gmail.com>`)

---

## 1. What we're building

An **AI-powered ATC add-on for FlightGear 2024.1.5 (macOS)** that gives *specific, real* instructions (e.g., "taxi to runway 28R via A, B, hold short of 28R") instead of the generic phraseology of the existing **Red Griffin ATC** add-on.

**Core principle — "AI when possible, code when not":** every capability has an AI path (Gemini, online) and a deterministic code path (offline). Airport "pictures" are derived once per airport and cached locally so offline sessions still work.

Full design is in **`PLANS/implementation-plan.md`** and **`docs/ARCHITECTURE.md`** — read those first.

## 2. Key decisions (locked)

- **Interaction:** Listen + menu replies (Red Griffin style). No microphone/STT in v1.
- **Two components:** thin **Nasal add-on** in FlightGear (menu + `/ai-atc/` property mailbox) + **Python sidecar** (Gemini, parsing, A* routing, cache, TTS).
- **Bridge:** FlightGear `--props=5501` (telnet); sidecar reads state + writes responses; speaks via macOS `say`.
- **Data:** both an **AI parser** (Gemini reads `groundnet.xml` + `airportinfo`) and a **code parser** (offline fallback), into one cached "picture" schema (SQLite).
- **Two-Mac workflow:** develop on THIS Mac (no FlightGear here) → push to GitHub → pull/test on the OTHER Mac (has FlightGear 2024.1.5 + Red Griffin installed).
- **Git authorship:** commits as `skh0h <samuelkhoh84@gmail.com>`, **never** add a `Co-Authored-By: Claude` trailer.

## 3. Status

**Phase 0 — DONE & pushed:**
- Scaffold: `sidecar/` (11 stub modules + `__init__`), `addon/` (metadata, main.nas, menubar, config, gui dialog), `tests/` (smoke test passing), `fixtures/`, `docs/ARCHITECTURE.md`, `requirements.txt`, `.env.example`, `.gitignore`, `README.md`.
- Nested git repo created (does NOT touch the parent `~/Documents` repo, whose remote is `xstate-app` — leave that alone).
- Private GitHub repo `skh0h/flightgear-ai-atc` created and pushed; smoke test green.

**Phases 1–5 — NOT STARTED** (see plan). Next up: Phase 1 = `gemini_client.py` + `config.py` (mock-testable now; live test needs the key in `.env`).

## 4. Open items / blockers

- ⚠️ **Uncommitted:** `PLANS/implementation-plan.md` and this `HANDOFF/` file are not yet committed/pushed.
- ⚠️ **Gemini key:** user will add `GEMINI_API_KEY` to a **gitignored `.env`** (never commit it; never paste it in chat). Live Gemini smoke test waits on this.
- ⚠️ **Duplicate repo:** `andrewkhoh/flightgear-ai-atc` still exists. Deletion is blocked because that account's `gh` token lacks the `delete_repo` scope. To finish: delete via GitHub web UI, or `gh auth switch --user andrewkhoh && gh auth refresh -h github.com -s delete_repo` then `gh repo delete andrewkhoh/flightgear-ai-atc --yes`.
- 💰 **Cost:** session reached ~$58 (heavy upfront deep-research + multiple orchestration agents). Build was paused pending user go-ahead. Resume cheaply: fewer/smaller agents, more inline edits.

## 5. How to resume

1. `cd "/Users/andrewkhoh/Documents/FlightGear Add-on"` and read `PLANS/implementation-plan.md`.
2. Confirm `git -C . rev-parse --show-toplevel` == this folder (NOT `~/Documents`) before any git op.
3. Ensure `gh` active account is `skh0h` (`gh auth status`).
4. Start **Phase 1**: implement `sidecar/config.py` + `sidecar/gemini_client.py` with mock tests; confirm current `google-genai` package name + live model IDs against Google docs before pinning versions.
5. Commit as `skh0h <samuelkhoh84@gmail.com>`, no Claude trailer; push to `origin main`.
