"""
Replay / regression harness for FlightGear ATC sidecar sessions.

``replay_session(path)`` reads a JSONL session log (one JSON object per line,
written by :mod:`sidecar.main` when ``SESSION_LOG_PATH`` is set) and feeds each
recorded request through the routing/clearance pipeline using a fake bridge
built from the recorded properties.  Phraseology is rendered via the
deterministic offline path so output is stable across re-runs (no Gemini, no
FlightGear).  Each record is diffed against its stored golden text and a
PASS/DIFF summary is printed.

Returns the number of records that diffed (0 = all pass).  The caller should
exit non-zero when the return value is non-zero.

JSONL record schema (written by :func:`sidecar.main.log_session_record`):
    {
        "timestamp":   <ISO-8601 string>,
        "airport_id":  <ICAO string>,
        "lat":         <float>,
        "lon":         <float>,
        "req_type":    <string>,
        "callsign":    <string>,
        "runway":      <string>,
        "aircraft_type": <string>,
        "picture_json": <AirportPicture JSON, may be null>,
        "response_text": <golden response text>
    }
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from sidecar.airport_picture import AirportPicture
from sidecar.phraseology import Clearance, phrase_offline
from sidecar import routing
from sidecar.runway_selection import build_taxi_clearance


# ---------------------------------------------------------------------------
# Fake bridge for replay
# ---------------------------------------------------------------------------

class _ReplayBridge:
    """Fake bridge backed by a flat dict of property values."""

    def __init__(self, props: dict[str, str]) -> None:
        self._props = props
        self._sets: list[tuple[str, Any]] = []

    def get(self, path: str) -> str:
        return str(self._props.get(path, ""))

    def set(self, path: str, value: Any) -> None:
        self._props[path] = str(value)
        self._sets.append((path, value))


# ---------------------------------------------------------------------------
# Clearance rebuild from a record
# ---------------------------------------------------------------------------

def _rebuild_clearance(record: dict[str, Any], picture: AirportPicture | None) -> Clearance:
    """Reconstruct the offline Clearance from a session record."""
    req_type = (record.get("req_type") or "taxi").strip()
    callsign = (record.get("callsign") or "Aircraft").strip()
    active_runway = (record.get("runway") or "").strip()
    aircraft_type = (record.get("aircraft_type") or "").strip()
    lat = float(record.get("lat") or 0.0)
    lon = float(record.get("lon") or 0.0)

    # Auto-select path
    if picture is not None and req_type == "taxi" and not active_runway:
        clearance = build_taxi_clearance(
            picture, callsign, lat, lon,
            wind_dir=None, wind_kt=None,
        )
        clearance.aircraft_type = aircraft_type
        return clearance

    # Explicit-runway path
    taxiways: list[str] = []
    if picture is not None and req_type == "taxi" and active_runway:
        try:
            start = routing.nearest_node(picture, lat, lon)
            goal = routing.runway_goal_node(picture, active_runway)
            if start is not None and goal is not None:
                route = routing.find_route(picture, start, goal)
                taxiways = routing.taxiways_for_clearance(route, picture)
        except Exception:
            pass

    return Clearance(
        callsign=callsign,
        clearance_type=req_type,
        taxi_route=taxiways,
        active_runway=active_runway,
        hold_short=active_runway if req_type == "taxi" else "",
        aircraft_type=aircraft_type,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def replay_session(path: str | Path) -> int:
    """Replay a JSONL session log and return the number of diffing records.

    Prints a per-record PASS/DIFF summary to stdout.

    Args:
        path: Path to the JSONL session log file.

    Returns:
        Number of records whose freshly-rendered text differs from the golden.
        0 = all records pass.
    """
    path = Path(path)
    diffs = 0
    total = 0

    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as exc:
                print(f"[line {lineno}] SKIP  — invalid JSON: {exc}", file=sys.stderr)
                continue

            total += 1
            golden = record.get("response_text", "")

            picture: AirportPicture | None = None
            pic_json = record.get("picture_json")
            if pic_json:
                try:
                    picture = AirportPicture.model_validate(pic_json)
                except Exception:
                    picture = None

            clearance = _rebuild_clearance(record, picture)
            fresh = phrase_offline(clearance)

            ts = record.get("timestamp", "?")
            cs = record.get("callsign", "?")
            if fresh == golden:
                print(f"[{lineno}] PASS  ts={ts} callsign={cs}")
            else:
                diffs += 1
                print(f"[{lineno}] DIFF  ts={ts} callsign={cs}")
                print(f"       golden : {golden!r}")
                print(f"       fresh  : {fresh!r}")

    print(f"\n{total} record(s) replayed — {diffs} DIFF(s).")
    return diffs
