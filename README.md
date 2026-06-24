# FlightGear AI ATC

AI-powered ATC clearances and taxi routing for FlightGear.

## Overview

Two components work together:

- **Python sidecar** (`sidecar/`) — AI/parsing/routing on your Mac. Talks to FlightGear over telnet.
- **Nasal addon** (`addon/`) — thin in-sim UI. Reads/writes the `/ai-atc/` property mailbox.

When online the sidecar uses the Gemini API for airport parsing and phraseology. When offline it falls back to deterministic groundnet.xml parsing and template-based ATC phrases.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design.

## Two-Mac Dev/Test Workflow

| Mac | Role |
|---|---|
| Dev Mac | Code here, push to GitHub |
| FlightGear Mac | Pull from GitHub, run FlightGear + sidecar |

Steps:
1. Push changes from dev Mac to `main`.
2. On FlightGear Mac: `git pull origin main`.
3. Start FlightGear with `--telnet=5501` and the addon path pointed at this repo's `addon/` directory.
4. On FlightGear Mac: `python3 sidecar/main.py`.
5. Test in-sim, iterate.

## Setup

### Requirements

- Python 3.11+
- FlightGear 2024.1.5+
- macOS (for `say` TTS; other platforms need a TTS backend swap)

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=<your key>
```

### Run tests

```bash
pytest tests/ -q
```

### Start sidecar

```bash
python3 sidecar/main.py
```

Make sure FlightGear is already running with `--telnet=5501` before starting the sidecar.

## Loading the Addon in FlightGear

In the FlightGear launcher add the `addon/` directory as an add-on path, or pass:

```
--addon=/path/to/flightgear-ai-atc/addon
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | Yes (online mode) | Google Gemini API key. Goes in `.env` (gitignored). |

Never commit `.env`. Only `.env.example` is tracked.
