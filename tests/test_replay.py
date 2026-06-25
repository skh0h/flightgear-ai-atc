"""Tests for sidecar/replay.py — no FlightGear, no network, no Gemini."""

from __future__ import annotations

import json
from pathlib import Path

from sidecar.airport_picture import AirportPicture, Node, Runway, Segment, build_taxi_graph
from sidecar.phraseology import Clearance, phrase_offline
from sidecar.replay import replay_session

# ---------------------------------------------------------------------------
# Synthetic picture and helpers
# ---------------------------------------------------------------------------

def _synthetic_picture() -> AirportPicture:
    """Minimal picture: one gate node, one on-runway node, runway 28L."""
    nodes = [
        Node(index=1, lat=37.620, lon=-122.380, on_runway=False),
        Node(index=2, lat=37.625, lon=-122.385, on_runway=True),
    ]
    segs = [Segment(begin=1, end=2, name="A")]
    runways = [Runway(id="28L", heading=284.0, entry_nodes=[2])]
    return AirportPicture(
        icao="SYN",
        source="code",
        generated_at="2026-06-24T00:00:00+00:00",
        groundnet_hash="testhash",
        nodes=nodes,
        segments=segs,
        runways=runways,
        taxi_graph=build_taxi_graph(nodes, segs),
    )


def _compute_golden(picture: AirportPicture, callsign: str, runway: str, req_type: str, aircraft_type: str) -> str:
    """Compute the golden text the same way replay does — via _rebuild_clearance + phrase_offline."""
    from sidecar.replay import _rebuild_clearance
    record = {
        "req_type": req_type,
        "callsign": callsign,
        "runway": runway,
        "aircraft_type": aircraft_type,
        "lat": 37.620,
        "lon": -122.380,
    }
    clearance = _rebuild_clearance(record, picture)
    return phrase_offline(clearance)


def _make_record(
    picture: AirportPicture,
    *,
    callsign: str = "N1",
    runway: str = "",
    req_type: str = "taxi",
    aircraft_type: str = "",
    golden: str | None = None,
) -> dict:
    """Build a synthetic session record; golden defaults to what replay would produce."""
    expected = golden if golden is not None else _compute_golden(
        picture, callsign, runway, req_type, aircraft_type
    )
    return {
        "timestamp": "2026-06-24T00:00:00+00:00",
        "airport_id": picture.icao,
        "lat": 37.620,
        "lon": -122.380,
        "req_type": req_type,
        "callsign": callsign,
        "runway": runway,
        "aircraft_type": aircraft_type,
        "picture_json": json.loads(picture.model_dump_json()),
        "response_text": expected,
    }


def _write_jsonl(tmp_path: Path, records: list[dict]) -> Path:
    p = tmp_path / "session.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_replay_pass_when_golden_matches(tmp_path: Path) -> None:
    """A record whose golden text matches the offline renderer reports PASS."""
    pic = _synthetic_picture()
    # golden is computed via _compute_golden so it matches replay exactly
    record = _make_record(pic, callsign="UAL1", runway="")
    log_path = _write_jsonl(tmp_path, [record])

    diffs = replay_session(log_path)
    assert diffs == 0


def test_replay_diff_when_golden_altered(tmp_path: Path) -> None:
    """A record with a wrong golden text reports DIFF and returns non-zero."""
    pic = _synthetic_picture()
    record = _make_record(pic, callsign="SWA5", runway="")
    record["response_text"] = "WRONG TEXT that will never match"
    log_path = _write_jsonl(tmp_path, [record])

    diffs = replay_session(log_path)
    assert diffs == 1


def test_replay_two_records_one_diff(tmp_path: Path) -> None:
    """Two records: first passes (golden matches), second has wrong golden → diffs=1."""
    pic = _synthetic_picture()
    good_record = _make_record(pic, callsign="DAL3", runway="")  # golden computed correctly
    bad_record = _make_record(pic, callsign="AAL9", runway="", golden="completely wrong")
    log_path = _write_jsonl(tmp_path, [good_record, bad_record])

    diffs = replay_session(log_path)
    assert diffs == 1


def test_replay_explicit_runway_record(tmp_path: Path) -> None:
    """Explicit runway path: record with runway='28L' replays correctly."""
    pic = _synthetic_picture()
    record = _make_record(pic, callsign="UAL9", runway="28L")  # golden computed correctly
    log_path = _write_jsonl(tmp_path, [record])

    diffs = replay_session(log_path)
    assert diffs == 0


def test_replay_empty_file_reports_zero_diffs(tmp_path: Path) -> None:
    """Empty session log → 0 records, 0 diffs."""
    log_path = tmp_path / "empty.jsonl"
    log_path.write_text("")
    assert replay_session(log_path) == 0


def test_replay_skips_blank_lines(tmp_path: Path) -> None:
    """Blank lines in JSONL are silently skipped; valid records are still replayed."""
    pic = _synthetic_picture()
    record = _make_record(pic, callsign="N5", runway="")  # golden computed correctly
    log_path = tmp_path / "session.jsonl"
    with log_path.open("w") as fh:
        fh.write("\n")
        fh.write(json.dumps(record) + "\n")
        fh.write("\n")

    diffs = replay_session(log_path)
    assert diffs == 0


def test_replay_no_picture_json_uses_template(tmp_path: Path) -> None:
    """When picture_json is null, replay falls back to template clearance."""
    # Without a picture, build_taxi_clearance can't auto-select; clearance has no runway
    record = {
        "timestamp": "2026-06-24T00:00:00+00:00",
        "airport_id": "SYN",
        "lat": 37.620,
        "lon": -122.380,
        "req_type": "taxi",
        "callsign": "N7",
        "runway": "",
        "aircraft_type": "",
        "picture_json": None,
        "response_text": "N7, taxi.",
    }
    log_path = _write_jsonl(tmp_path, [record])
    # With no picture and no runway, phrase_offline produces "N7, taxi."
    diffs = replay_session(log_path)
    assert diffs == 0
