"""Tests for sidecar/main.py — Sidecar orchestration with fakes, no network."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from sidecar.airport_picture import AirportPicture, Node, Runway, Segment, build_taxi_graph
from sidecar.config import Settings
from sidecar.cache import PictureCache
from sidecar.gemini_client import OfflineError
from sidecar.main import (
    AIRCRAFT_ID,
    AIRPORT_ID,
    CONTROLLER_NAME,
    HEARTBEAT,
    LOCAL_HOUR,
    MODE,
    POS_LAT,
    POS_LON,
    REQ_CALLSIGN,
    REQ_RUNWAY,
    REQ_TRIGGER,
    REQ_TYPE,
    READBACK_HEARD,
    READBACK_RESULT,
    RESP_READY,
    RESP_TEXT,
    SIDECAR_MODE,
    STATUS,
    Sidecar,
    role_for_clearance,
)
from sidecar.tts import TTS, TTSBackend, voice_for

_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "KSFO.groundnet.xml"


def _settings() -> Settings:
    return Settings(
        gemini_api_key=None,
        fg_telnet_host="localhost",
        fg_telnet_port=5501,
        cache_db_path="unused",
        tts_voice="Alex",
        log_level="INFO",
        gemini_model_fast="gemini-2.5-flash",
        gemini_model_pro="gemini-2.5-pro",
    )


class _FakeBridge:
    def __init__(self, props: dict[str, Any]) -> None:
        self.props = dict(props)
        self.sets: list[tuple[str, Any]] = []

    def get(self, path: str) -> str:
        return str(self.props.get(path, ""))

    def set(self, path: str, value: Any) -> None:
        self.props[path] = value
        self.sets.append((path, value))


class _OfflineClient:
    def generate(self, *args: Any, **kwargs: Any) -> Any:
        raise OfflineError("offline in test")


class _RecordingBackend(TTSBackend):
    def __init__(self) -> None:
        self.said: list[tuple[str, str]] = []

    def say(self, text: str, voice: str) -> None:
        self.said.append((text, voice))


def _make(tmp_path: Path, props: dict[str, Any]):
    bridge = _FakeBridge(props)
    cache = PictureCache(tmp_path / "cache.sqlite")
    backend = _RecordingBackend()
    tts = TTS(backend=backend)

    def loader(icao: str) -> str | None:
        return _FIXTURE.read_text() if icao == "KSFO" else None

    sidecar = Sidecar(
        _settings(), bridge, _OfflineClient(), cache, tts, groundnet_loader=loader
    )
    return sidecar, bridge, backend


def test_handle_trigger_taxi_writes_response_and_resets(tmp_path: Path) -> None:
    props = {
        AIRPORT_ID: "KSFO",
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL123",
        REQ_RUNWAY: "",
        POS_LAT: "37.62",
        POS_LON: "-122.38",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make(tmp_path, props)
    sidecar.handle_trigger()

    assert bridge.props[RESP_TEXT].startswith("UAL123, taxi")
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[STATUS] == "idle"
    assert bridge.props[REQ_TRIGGER] == 0
    assert backend.said, "a clearance should have been spoken"


def test_handle_trigger_cancel_resets_without_response(tmp_path: Path) -> None:
    props = {AIRPORT_ID: "KSFO", REQ_TYPE: "cancel", REQ_TRIGGER: "1"}
    sidecar, bridge, backend = _make(tmp_path, props)
    sidecar.handle_trigger()

    assert bridge.props[STATUS] == "idle"
    assert bridge.props[REQ_TRIGGER] == 0
    assert bridge.props.get(RESP_TEXT, "") == ""
    assert backend.said == []


def test_get_airport_picture_uses_cache_and_offline_parser(tmp_path: Path) -> None:
    sidecar, _bridge, _backend = _make(tmp_path, {AIRPORT_ID: "KSFO"})
    xml = _FIXTURE.read_text()

    first = sidecar.get_airport_picture("KSFO", xml)
    second = sidecar.get_airport_picture("KSFO", xml)  # served from cache

    assert first.source == "code"  # offline client -> deterministic parser
    assert first.groundnet_hash == second.groundnet_hash
    assert sidecar.cache.get("KSFO", first.groundnet_hash) is not None


def test_poll_loop_dispatches_on_trigger(tmp_path: Path) -> None:
    props = {
        AIRPORT_ID: "KSFO",
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "N1",
        REQ_RUNWAY: "",
        POS_LAT: "37.6",
        POS_LON: "-122.38",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, _backend = _make(tmp_path, props)
    sidecar.poll_loop(max_iterations=1, _sleep=lambda *_: None)

    assert bridge.props[REQ_TRIGGER] == 0  # handled and reset
    assert bridge.props[RESP_READY] == 1


# ---------------------------------------------------------------------------
# Item 2: explicit REQ_RUNWAY path vs auto-select path
# ---------------------------------------------------------------------------


_SYNTH_XML = "<groundnet/>"
_SYNTH_HASH = hashlib.sha256(_SYNTH_XML.encode()).hexdigest()


def _synthetic_picture() -> AirportPicture:
    """Minimal picture with one runway (28L) and two nodes: gate → runway.

    ``groundnet_hash`` is set to sha256("<groundnet/>") so the cache lookup in
    ``get_airport_picture`` (which hashes the loader's XML) hits on first call.
    """
    nodes = [
        Node(index=1, lat=37.620, lon=-122.380, on_runway=False),
        Node(index=2, lat=37.625, lon=-122.385, on_runway=True),
    ]
    segs = [Segment(begin=1, end=2, name="")]
    runways = [Runway(id="28L", heading=284.0, entry_nodes=[2])]
    return AirportPicture(
        icao="SYN",
        source="code",
        generated_at="2026-06-24T00:00:00+00:00",
        groundnet_hash=_SYNTH_HASH,
        nodes=nodes,
        segments=segs,
        runways=runways,
        taxi_graph=build_taxi_graph(nodes, segs),
    )


def _make_with_picture(tmp_path: Path, props: dict[str, Any], picture: AirportPicture):
    """Sidecar wired to return a fixed picture (pre-seeded cache, stub XML loader)."""
    bridge = _FakeBridge(props)
    cache = PictureCache(tmp_path / "cache.sqlite")
    backend = _RecordingBackend()
    tts = TTS(backend=backend)

    # Pre-populate cache; the loader returns _SYNTH_XML whose hash matches
    cache.put(picture)

    def loader(icao: str) -> str | None:
        return _SYNTH_XML if icao == picture.icao else None

    sidecar = Sidecar(
        _settings(), bridge, _OfflineClient(), cache, tts, groundnet_loader=loader
    )
    return sidecar, bridge, backend


def test_build_clearance_explicit_runway_routes_to_it(tmp_path: Path) -> None:
    """When REQ_RUNWAY is set, sidecar routes to that specific runway."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "DAL5",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)

    # _build_clearance calls runway_goal_node("28L") which maps to node 2
    clearance = sidecar._build_clearance("taxi", "DAL5", pic)
    assert clearance.active_runway == "28L"
    assert "DAL5" == clearance.callsign
    assert clearance.clearance_type == "taxi"


def test_build_clearance_auto_selects_runway_when_none_given(tmp_path: Path) -> None:
    """When REQ_RUNWAY is empty, sidecar auto-selects 28L (only runway in picture)."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL9",
        REQ_RUNWAY: "",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)

    clearance = sidecar._build_clearance("taxi", "UAL9", pic)
    # Only runway in picture is 28L — auto-select must choose it
    assert clearance.active_runway == "28L"
    assert clearance.callsign == "UAL9"
    assert clearance.clearance_type == "taxi"


def test_handle_trigger_auto_select_writes_runway_in_response(tmp_path: Path) -> None:
    """Full handle_trigger cycle: no REQ_RUNWAY → sidecar picks one and voices it."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "SWA7",
        REQ_RUNWAY: "",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    resp = bridge.props[RESP_TEXT]
    assert "SWA7" in resp
    assert "28L" in resp
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[REQ_TRIGGER] == 0
    assert backend.said


# ---------------------------------------------------------------------------
# Item 2: aircraft_type propagation
# ---------------------------------------------------------------------------


def test_build_clearance_carries_aircraft_type(tmp_path: Path) -> None:
    """Aircraft ID from bridge is set on the returned Clearance."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        AIRCRAFT_ID: "c172p",
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "N1",
        REQ_RUNWAY: "",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, _ = _make_with_picture(tmp_path, props, pic)
    clearance = sidecar._build_clearance("taxi", "N1", pic)
    assert clearance.aircraft_type == "c172p"


def test_build_clearance_explicit_runway_carries_aircraft_type(tmp_path: Path) -> None:
    """Aircraft type is set on the explicit-runway path too."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        AIRCRAFT_ID: "b738",
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "DAL5",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, _ = _make_with_picture(tmp_path, props, pic)
    clearance = sidecar._build_clearance("taxi", "DAL5", pic)
    assert clearance.aircraft_type == "b738"


def test_build_clearance_no_aircraft_id_gives_empty_string(tmp_path: Path) -> None:
    """When /sim/aircraft-id is absent, aircraft_type defaults to empty string."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        # AIRCRAFT_ID deliberately absent
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "N2",
        REQ_RUNWAY: "",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
    }
    sidecar, _, _ = _make_with_picture(tmp_path, props, pic)
    clearance = sidecar._build_clearance("taxi", "N2", pic)
    assert clearance.aircraft_type == ""


# ---------------------------------------------------------------------------
# Stage 0: exception-path recovery (Task 4a)
# ---------------------------------------------------------------------------


class _BrokenClient:
    """A client that always raises RuntimeError to trigger the exception path."""

    def generate(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("forced failure for test")


def test_handle_trigger_exception_path_writes_error_reply(tmp_path: Path) -> None:
    """When handle_trigger() raises, it must write a user-facing error reply
    and reset STATUS to idle (not leave it stuck on 'processing' or 'error')."""
    props = {
        AIRPORT_ID: "KSFO",
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL1",
        REQ_RUNWAY: "",
        POS_LAT: "37.62",
        POS_LON: "-122.38",
        REQ_TRIGGER: "1",
    }
    bridge = _FakeBridge(props)
    cache = PictureCache(tmp_path / "cache.sqlite")
    backend = _RecordingBackend()
    tts = TTS(backend=backend)

    # Loader that returns something to trigger the AI path (which will fail).
    def loader(icao: str) -> str | None:
        return _FIXTURE.read_text() if icao == "KSFO" else None

    sidecar = Sidecar(
        _settings(), bridge, _BrokenClient(), cache, tts, groundnet_loader=loader
    )
    sidecar.handle_trigger()

    # Must have written a user-facing error message.
    assert bridge.props.get(RESP_TEXT, "") != ""
    assert "Stand by" in bridge.props[RESP_TEXT]
    # Must have set RESP_READY so the UI unblocks.
    assert bridge.props[RESP_READY] == 1
    # Must have reset STATUS to idle (not left as "error").
    assert bridge.props[STATUS] == "idle"
    # Must have reset the trigger.
    assert bridge.props[REQ_TRIGGER] == 0


# ---------------------------------------------------------------------------
# Stage 0: heartbeat write in poll_loop (Task 2)
# ---------------------------------------------------------------------------


def test_poll_loop_writes_heartbeat(tmp_path: Path) -> None:
    """poll_loop must increment /ai-atc/sidecar/heartbeat on each heartbeat tick."""
    props = {
        AIRPORT_ID: "KSFO",
        REQ_TRIGGER: "0",
    }
    sidecar, bridge, _ = _make(tmp_path, props)

    # Run enough iterations so at least one heartbeat fires (heartbeat_interval=0.0).
    sidecar.poll_loop(
        max_iterations=3,
        _sleep=lambda *_: None,
        heartbeat_interval=0.0,
    )

    assert bridge.props.get(HEARTBEAT, 0) > 0
    assert bridge.props.get(SIDECAR_MODE) in ("ai", "offline")


# ---------------------------------------------------------------------------
# Arrival req_types: approach, ils, airfield_in_sight, radio_check
# ---------------------------------------------------------------------------


import pytest


@pytest.mark.parametrize("req_type", ["approach", "ils", "airfield_in_sight", "radio_check"])
def test_handle_trigger_arrival_types_write_response(tmp_path: Path, req_type: str) -> None:
    """handle_trigger routes each new arrival req_type through phraseology and writes a response."""
    props = {
        AIRPORT_ID: "KSFO",
        REQ_TYPE: req_type,
        REQ_CALLSIGN: "UAL1",
        REQ_RUNWAY: "28R",
        POS_LAT: "37.62",
        POS_LON: "-122.38",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make(tmp_path, props)
    sidecar.handle_trigger()

    assert bridge.props[RESP_READY] == 1
    assert bridge.props[STATUS] == "idle"
    assert bridge.props[REQ_TRIGGER] == 0
    resp = bridge.props[RESP_TEXT]
    assert resp.strip(), f"Expected non-empty response for req_type={req_type!r}"
    assert "UAL1" in resp, f"Callsign missing from response for req_type={req_type!r}"


def test_build_clearance_arrival_types_set_clearance_type(tmp_path: Path) -> None:
    """_build_clearance sets clearance_type correctly for each arrival req_type."""
    pic = _synthetic_picture()
    for req_type in ("approach", "ils", "airfield_in_sight", "radio_check"):
        props = {
            AIRPORT_ID: pic.icao,
            REQ_TYPE: req_type,
            REQ_CALLSIGN: "UAL1",
            REQ_RUNWAY: "28L",
            POS_LAT: "37.620",
            POS_LON: "-122.380",
        }
        sidecar, _, _ = _make_with_picture(tmp_path, props, pic)
        clearance = sidecar._build_clearance(req_type, "UAL1", pic)
        assert clearance.clearance_type == req_type, f"clearance_type mismatch for {req_type!r}"
        assert clearance.callsign == "UAL1"


def test_build_clearance_arrival_remarks_with_threshold_data(tmp_path: Path) -> None:
    """When runway threshold coords are non-zero, distance/bearing goes into remarks."""
    from sidecar.airport_picture import Frequencies

    pic = _synthetic_picture()
    # Give the runway real threshold coordinates (non-zero triggers computation)
    rwy_with_thr = pic.runways[0].model_copy(update={"thr_lat": 37.625, "thr_lon": -122.385})
    pic_with_thr = pic.model_copy(update={"runways": [rwy_with_thr]})

    props = {
        AIRPORT_ID: pic_with_thr.icao,
        REQ_TYPE: "approach",
        REQ_CALLSIGN: "N1",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
    }
    sidecar, _, _ = _make_with_picture(tmp_path, props, pic_with_thr)
    clearance = sidecar._build_clearance("approach", "N1", pic_with_thr)
    assert clearance.remarks, "remarks should be non-empty when threshold coords are available"
    assert "nm" in clearance.remarks


def test_build_clearance_radio_check_no_remarks(tmp_path: Path) -> None:
    """radio_check never computes distance/bearing; remarks stays empty."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "radio_check",
        REQ_CALLSIGN: "N1",
        REQ_RUNWAY: "",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
    }
    sidecar, _, _ = _make_with_picture(tmp_path, props, pic)
    clearance = sidecar._build_clearance("radio_check", "N1", pic)
    assert clearance.remarks == ""


@pytest.mark.parametrize(
    "req_type,expected",
    [
        ("approach", "UAL1, expect approach runway 28L."),
        ("ils", "UAL1, cleared ILS runway 28L approach."),
        ("airfield_in_sight", "UAL1, cleared visual approach runway 28L."),
        ("radio_check", "UAL1, reading you five by five."),
    ],
)
def test_handle_trigger_arrival_offline_template_exact(
    tmp_path: Path, req_type: str, expected: str
) -> None:
    """Full handle_trigger cycle (offline client) writes the exact offline template.

    The synthetic picture's runway has zero threshold coords, so no
    distance/bearing remark is appended — RESP_TEXT equals the bare template.
    """
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: req_type,
        REQ_CALLSIGN: "UAL1",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    assert bridge.props[RESP_TEXT] == expected
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[STATUS] == "idle"
    assert bridge.props[REQ_TRIGGER] == 0
    assert backend.said


# ---------------------------------------------------------------------------
# Regression: FG telnet bool-false artifact must never leak into clearance
# ---------------------------------------------------------------------------


def test_fg_bool_false_not_spoken_as_runway_or_callsign(tmp_path: Path) -> None:
    """When FG telnet serializes a bool-false property as the token 'false',
    that string must not appear in the spoken clearance as a callsign or runway
    identifier.  Callsign must fall back to 'Aircraft'; runway auto-selection
    must engage so a real runway (28L) is used instead.
    """
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "false",   # FG bool-false artifact
        REQ_RUNWAY: "false",     # FG bool-false artifact
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    resp = bridge.props[RESP_TEXT]
    assert "false" not in resp.lower(), f"'false' leaked into clearance: {resp!r}"
    assert "Aircraft" in resp, f"callsign should fall back to 'Aircraft': {resp!r}"
    assert "28L" in resp, f"runway should auto-select to 28L: {resp!r}"
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[REQ_TRIGGER] == 0


# ---------------------------------------------------------------------------
# Mode A: merge_airport_mailbox reads runway active flags
# ---------------------------------------------------------------------------


def test_merge_airport_mailbox_reads_active_flags() -> None:
    from sidecar.main import (
        AP_RUNWAY_COUNT,
        AP_RUNWAY_PREFIX,
        merge_airport_mailbox,
    )

    pic = _synthetic_picture()
    props = {
        AP_RUNWAY_COUNT: "2",
        f"{AP_RUNWAY_PREFIX}[0]/id": "28L",
        f"{AP_RUNWAY_PREFIX}[0]/heading": "284",
        f"{AP_RUNWAY_PREFIX}[0]/active": "1",
        f"{AP_RUNWAY_PREFIX}[1]/id": "10R",
        f"{AP_RUNWAY_PREFIX}[1]/heading": "104",
        f"{AP_RUNWAY_PREFIX}[1]/active": "0",
    }
    merged = merge_airport_mailbox(pic, _FakeBridge(props))
    by_id = {r.id: r for r in merged.runways}
    assert by_id["28L"].active is True
    assert by_id["10R"].active is False


def test_merge_airport_mailbox_active_absent_defaults_false() -> None:
    from sidecar.main import (
        AP_RUNWAY_COUNT,
        AP_RUNWAY_PREFIX,
        merge_airport_mailbox,
    )

    pic = _synthetic_picture()
    props = {
        AP_RUNWAY_COUNT: "1",
        f"{AP_RUNWAY_PREFIX}[0]/id": "28L",
        f"{AP_RUNWAY_PREFIX}[0]/heading": "284",
        # no /active key published
    }
    merged = merge_airport_mailbox(pic, _FakeBridge(props))
    assert merged.runways[0].active is False


# ---------------------------------------------------------------------------
# Mode B: read_ai_traffic + compute_traffic_queue + handle_trigger wiring
# ---------------------------------------------------------------------------


def test_read_ai_traffic_snaps_drops_far_and_stops_at_blank() -> None:
    from sidecar import routing
    from sidecar.main import AI_MODELS_PREFIX, read_ai_traffic

    pic = _synthetic_picture()  # node 1 @ (37.620,-122.380), node 2 @ (37.625,-122.385)
    ai = AI_MODELS_PREFIX
    props = {
        # aircraft[0]: near node 1 → snapped & kept
        f"{ai}[0]/valid": "true",
        f"{ai}[0]/callsign": "DLH123",
        f"{ai}[0]/position/latitude-deg": "37.6201",
        f"{ai}[0]/position/longitude-deg": "-122.3801",
        f"{ai}[0]/orientation/true-heading-deg": "90",
        # aircraft[1]: far away → dropped (> max_snap_m) but probing continues
        f"{ai}[1]/valid": "1",
        f"{ai}[1]/callsign": "FAR1",
        f"{ai}[1]/position/latitude-deg": "40.0",
        f"{ai}[1]/position/longitude-deg": "-120.0",
        # aircraft[2]: valid blank → probing stops here
    }
    snaps = read_ai_traffic(_FakeBridge(props), pic)
    assert [s.callsign for s in snaps] == ["DLH123"]
    assert snaps[0].node_index == routing.nearest_node(pic, 37.6201, -122.3801)
    assert snaps[0].snap_dist_m >= 0.0


def test_read_ai_traffic_stops_at_first_invalid_entry() -> None:
    from sidecar.main import AI_MODELS_PREFIX, read_ai_traffic

    pic = _synthetic_picture()
    ai = AI_MODELS_PREFIX
    props = {
        f"{ai}[0]/valid": "1",
        f"{ai}[0]/callsign": "AAL1",
        f"{ai}[0]/position/latitude-deg": "37.6201",
        f"{ai}[0]/position/longitude-deg": "-122.3801",
        # aircraft[1] valid is blank → STOP before reaching aircraft[2]
        f"{ai}[2]/valid": "1",
        f"{ai}[2]/callsign": "SHOULD_NOT_APPEAR",
        f"{ai}[2]/position/latitude-deg": "37.6201",
        f"{ai}[2]/position/longitude-deg": "-122.3801",
    }
    snaps = read_ai_traffic(_FakeBridge(props), pic)
    assert [s.callsign for s in snaps] == ["AAL1"]


def test_read_ai_traffic_drops_null_island() -> None:
    from sidecar.main import AI_MODELS_PREFIX, read_ai_traffic

    pic = _synthetic_picture()
    ai = AI_MODELS_PREFIX
    props = {
        f"{ai}[0]/valid": "1",
        f"{ai}[0]/callsign": "ZERO",
        f"{ai}[0]/position/latitude-deg": "0",
        f"{ai}[0]/position/longitude-deg": "0",
        f"{ai}[1]/valid": "1",
        f"{ai}[1]/callsign": "GOOD",
        f"{ai}[1]/position/latitude-deg": "37.6201",
        f"{ai}[1]/position/longitude-deg": "-122.3801",
    }
    snaps = read_ai_traffic(_FakeBridge(props), pic)
    assert [s.callsign for s in snaps] == ["GOOD"]


def test_compute_traffic_queue_user_behind_traffic() -> None:
    from sidecar.airport_picture import TrafficSnapshot
    from sidecar.main import compute_traffic_queue

    pic = _synthetic_picture()  # node 2 is the only on-runway node
    # DLH123 sits at the runway entrance; the user is back at the gate (node 1).
    traffic = [TrafficSnapshot(callsign="DLH123", lat=37.6249, lon=-122.3849)]
    count, summary = compute_traffic_queue(traffic, user_node_index=1, picture=pic)
    assert count == 1
    assert summary == "Ground traffic: 1. You are number 2, behind DLH123."


def test_compute_traffic_queue_empty_is_number_one() -> None:
    from sidecar.main import compute_traffic_queue

    pic = _synthetic_picture()
    count, summary = compute_traffic_queue([], user_node_index=1, picture=pic)
    assert count == 0
    assert "number 1" in summary


def test_handle_trigger_taxi_writes_traffic_summary(tmp_path: Path) -> None:
    from sidecar.main import AI_MODELS_PREFIX, TRAFFIC_COUNT, TRAFFIC_SUMMARY

    pic = _synthetic_picture()
    ai = AI_MODELS_PREFIX
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL9",
        REQ_RUNWAY: "",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
        f"{ai}[0]/valid": "1",
        f"{ai}[0]/callsign": "DLH123",
        f"{ai}[0]/position/latitude-deg": "37.6249",
        f"{ai}[0]/position/longitude-deg": "-122.3849",
        f"{ai}[0]/orientation/true-heading-deg": "284",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    assert "DLH123" in bridge.props[TRAFFIC_SUMMARY]
    assert bridge.props[TRAFFIC_COUNT] == 1
    # Clearance must still be produced normally.
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[REQ_TRIGGER] == 0
    assert backend.said


def test_handle_trigger_takeoff_appends_wake_caution_for_heavy_traffic(
    tmp_path: Path,
) -> None:
    """A takeoff with a nearby heavy in /ai/models appends a wake caution to RESP_TEXT."""
    from sidecar.main import AI_MODELS_PREFIX

    pic = _synthetic_picture()
    ai = AI_MODELS_PREFIX
    props = {
        AIRPORT_ID: pic.icao,
        AIRCRAFT_ID: "c172p",  # light follower
        REQ_TYPE: "takeoff",
        REQ_CALLSIGN: "UAL1",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
        # A heavy sitting next to the user, snapped to the net.
        f"{ai}[0]/valid": "1",
        f"{ai}[0]/callsign": "DLH9 Heavy",
        f"{ai}[0]/position/latitude-deg": "37.6201",
        f"{ai}[0]/position/longitude-deg": "-122.3801",
        f"{ai}[0]/orientation/true-heading-deg": "284",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    resp = bridge.props[RESP_TEXT]
    assert "cleared for takeoff" in resp.lower()
    assert "wake" in resp.lower(), f"expected a wake-turbulence caution in {resp!r}"
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[REQ_TRIGGER] == 0


def test_handle_trigger_taxi_writes_chatter_when_traffic_present(tmp_path: Path) -> None:
    """A taxi request with nearby AI traffic publishes one ambient chatter line."""
    from sidecar.main import AI_MODELS_PREFIX, CHATTER

    pic = _synthetic_picture()
    ai = AI_MODELS_PREFIX
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL9",
        REQ_RUNWAY: "",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
        f"{ai}[0]/valid": "1",
        f"{ai}[0]/callsign": "DLH123",
        f"{ai}[0]/position/latitude-deg": "37.6249",
        f"{ai}[0]/position/longitude-deg": "-122.3849",
        f"{ai}[0]/orientation/true-heading-deg": "284",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    assert bridge.props.get(CHATTER, ""), "expected a non-empty ambient chatter line"
    # Clearance reply is unaffected.
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[REQ_TRIGGER] == 0


def test_handle_trigger_traffic_failure_still_writes_response(
    tmp_path: Path, monkeypatch: Any
) -> None:
    import sidecar.main as main_mod

    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL9",
        REQ_RUNWAY: "",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("traffic blew up")

    monkeypatch.setattr(main_mod, "read_ai_traffic", _boom)
    sidecar.handle_trigger()

    # Traffic sequencing failed, but the clearance response is intact.
    assert bridge.props[RESP_TEXT].startswith("UAL9")
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[STATUS] == "idle"
    assert bridge.props[REQ_TRIGGER] == 0


# ---------------------------------------------------------------------------
# Phase 3: emergency & abnormal req_types end-to-end
# ---------------------------------------------------------------------------


_EMERGENCY_TYPES = [
    "mayday",
    "pan_pan",
    "gear_emergency",
    "min_fuel",
    "diversion",
    "go_around",
    "squawk_7500",
    "squawk_7600",
    "squawk_7700",
]


@pytest.mark.parametrize("req_type", _EMERGENCY_TYPES)
def test_handle_trigger_emergency_offline_template_exact(
    tmp_path: Path, req_type: str
) -> None:
    """Full handle_trigger cycle (offline client) writes the exact offline template
    for each emergency/abnormal req_type, and resets the mailbox state."""
    from sidecar.phraseology import Clearance, phrase_offline

    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: req_type,
        REQ_CALLSIGN: "UAL1",
        REQ_RUNWAY: "",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    expected = phrase_offline(Clearance(callsign="UAL1", clearance_type=req_type))
    assert bridge.props[RESP_TEXT] == expected
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[STATUS] == "idle"
    assert bridge.props[REQ_TRIGGER] == 0
    assert backend.said


def test_handle_trigger_diversion_includes_nearest_airport(tmp_path: Path) -> None:
    """When Nasal publishes nearest-airport icao+name, the diversion clearance
    names that airport."""
    from sidecar.main import NEAREST_AIRPORT_ICAO, NEAREST_AIRPORT_NAME

    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "diversion",
        REQ_CALLSIGN: "UAL1",
        REQ_RUNWAY: "",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
        NEAREST_AIRPORT_ICAO: "KSQL",
        NEAREST_AIRPORT_NAME: "San Carlos",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    resp = bridge.props[RESP_TEXT]
    assert "KSQL" in resp
    assert "San Carlos" in resp
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[REQ_TRIGGER] == 0


def test_handle_trigger_diversion_generic_when_nearest_absent(tmp_path: Path) -> None:
    """With no nearest-airport properties published, the diversion clearance
    falls back to generic 'nearest suitable airport' wording (never raises)."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "diversion",
        REQ_CALLSIGN: "UAL1",
        REQ_RUNWAY: "",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    resp = bridge.props[RESP_TEXT]
    assert "nearest suitable airport" in resp
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[REQ_TRIGGER] == 0


# ---------------------------------------------------------------------------
# Phase 4: personality, session memory, modes, position relief
# ---------------------------------------------------------------------------


def test_sidecar_publishes_controller_name_at_init(tmp_path: Path) -> None:
    """Constructing a Sidecar publishes the persona name to CONTROLLER_NAME."""
    pic = _synthetic_picture()
    sidecar, bridge, _ = _make_with_picture(tmp_path, {AIRPORT_ID: pic.icao}, pic)
    assert sidecar.persona.name, "persona should have a name"
    assert bridge.props.get(CONTROLLER_NAME) == sidecar.persona.name


def test_handle_trigger_remembers_interactions(tmp_path: Path) -> None:
    """Each handled request grows the bounded session memory's count."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL9",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, _ = _make_with_picture(tmp_path, props, pic)
    assert sidecar.memory.count == 0

    sidecar.handle_trigger()
    assert sidecar.memory.count == 1

    bridge.props[REQ_TRIGGER] = "1"
    sidecar.handle_trigger()
    assert sidecar.memory.count == 2
    # The remembered context should mention the callsign.
    assert "UAL9" in sidecar.memory.recent_context()


def test_handle_trigger_normal_mode_leaves_template_intact(tmp_path: Path) -> None:
    """The default (normal) mode adds no coaching/readback nuance."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL9",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, _ = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()
    assert bridge.props[RESP_TEXT] == "UAL9, taxi to runway 28L, hold short of 28L."


def test_handle_trigger_student_mode_adds_coaching_remark(tmp_path: Path) -> None:
    """student mode appends a coaching nuance that changes RESP_TEXT."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL9",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
        MODE: "student",
    }
    sidecar, bridge, _ = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()
    resp = bridge.props[RESP_TEXT]
    assert resp != "UAL9, taxi to runway 28L, hold short of 28L."
    assert "Take your time" in resp
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[REQ_TRIGGER] == 0


def test_handle_trigger_checkride_mode_requests_readback(tmp_path: Path) -> None:
    """checkride mode appends an explicit read-back instruction."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL9",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
        MODE: "checkride",
    }
    sidecar, bridge, _ = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()
    assert "Read back all instructions." in bridge.props[RESP_TEXT]
    assert bridge.props[RESP_READY] == 1


def test_handle_trigger_local_hour_does_not_break_reply(tmp_path: Path) -> None:
    """A late LOCAL_HOUR (quiet-night mood) must not disturb the clearance reply."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL9",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
        LOCAL_HOUR: "2",  # quiet night -> reflective mood
    }
    sidecar, bridge, _ = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()
    # Offline client: mood only flavours the (unused) prompt, not the reply.
    assert bridge.props[RESP_TEXT] == "UAL9, taxi to runway 28L, hold short of 28L."
    assert bridge.props[RESP_READY] == 1


def test_handle_trigger_relief_handoff_regenerates_and_briefs(tmp_path: Path) -> None:
    """relief_handoff regenerates the persona, republishes the name, and briefs."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL9",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    # One normal interaction so the briefing has recent activity to summarise.
    sidecar.handle_trigger()

    bridge.props[REQ_TYPE] = "relief_handoff"
    bridge.props[REQ_CALLSIGN] = "UAL9"
    bridge.props[REQ_TRIGGER] = "1"
    sidecar.handle_trigger()

    resp = bridge.props[RESP_TEXT]
    # New controller name is republished and appears in the briefing.
    assert bridge.props[CONTROLLER_NAME] == sidecar.persona.name
    assert sidecar.persona.name in resp
    assert "taking over the position" in resp
    # Briefing recaps the earlier taxi interaction.
    assert "UAL9" in resp
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[STATUS] == "idle"
    assert bridge.props[REQ_TRIGGER] == 0
    assert backend.said


# ---------------------------------------------------------------------------
# Phase 5: pilot readback grading + per-role voice
# ---------------------------------------------------------------------------


def test_role_for_clearance_maps_positions() -> None:
    from sidecar.phraseology import Clearance

    assert role_for_clearance(Clearance(callsign="A", clearance_type="taxi")) == "ground"
    assert role_for_clearance(Clearance(callsign="A", clearance_type="pushback")) == "ground"
    assert role_for_clearance(Clearance(callsign="A", clearance_type="takeoff")) == "tower"
    assert role_for_clearance(Clearance(callsign="A", clearance_type="approach")) == "approach"
    assert role_for_clearance(Clearance(callsign="A", clearance_type="ils")) == "approach"
    assert role_for_clearance(None) == "tower"


def test_handle_trigger_taxi_speaks_with_ground_voice(tmp_path: Path) -> None:
    """A taxi clearance is voiced with the ground controller's distinct voice."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL9",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()
    assert backend.said
    spoken_text, spoken_voice = backend.said[-1]
    assert spoken_voice == voice_for("ground")


def test_handle_trigger_readback_correct(tmp_path: Path) -> None:
    """A faithful readback of the prior taxi clearance grades as correct."""
    from sidecar.phraseology import Clearance, expected_readback

    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL9",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()  # issue the clearance first

    expected = expected_readback(sidecar._last_clearance)
    bridge.props[REQ_TYPE] = "readback"
    bridge.props[READBACK_HEARD] = expected
    bridge.props[REQ_TRIGGER] = "1"
    sidecar.handle_trigger()

    assert "correct" in bridge.props[READBACK_RESULT].lower()
    assert "readback correct" in bridge.props[RESP_TEXT].lower()
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[STATUS] == "idle"
    assert bridge.props[REQ_TRIGGER] == 0


def test_handle_trigger_readback_incomplete_voices_correction(tmp_path: Path) -> None:
    """A partial readback grades as incomplete and the controller re-issues it."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL9",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    bridge.props[REQ_TYPE] = "readback"
    bridge.props[READBACK_HEARD] = "wilco"  # nothing salient
    bridge.props[REQ_TRIGGER] = "1"
    sidecar.handle_trigger()

    assert "incomplete" in bridge.props[READBACK_RESULT].lower()
    assert "negative" in bridge.props[RESP_TEXT].lower()
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[REQ_TRIGGER] == 0


def test_handle_trigger_readback_without_prior_clearance(tmp_path: Path) -> None:
    """A readback with no active clearance never raises and still unblocks the UI."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "readback",
        READBACK_HEARD: "runway 28L",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    assert bridge.props[RESP_READY] == 1
    assert bridge.props[STATUS] == "idle"
    assert bridge.props[REQ_TRIGGER] == 0
    assert bridge.props.get(RESP_TEXT, "")


# ---------------------------------------------------------------------------
# Phase 7: flight-phase state machine + IFR CRAFT clearance wiring
# ---------------------------------------------------------------------------


def test_handle_trigger_publishes_flight_phase_and_advances(tmp_path: Path) -> None:
    """handle_trigger publishes FLIGHT_PHASE and advances the fsm forward across
    a pushback -> taxi -> takeoff sequence."""
    from sidecar import state
    from sidecar.main import FLIGHT_PHASE

    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "pushback",
        REQ_CALLSIGN: "UAL9",
        REQ_RUNWAY: "",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, _ = _make_with_picture(tmp_path, props, pic)

    sidecar.handle_trigger()
    assert bridge.props[FLIGHT_PHASE] == state.PUSHBACK
    assert sidecar.fsm.phase == state.PUSHBACK

    bridge.props[REQ_TYPE] = "taxi"
    bridge.props[REQ_TRIGGER] = "1"
    sidecar.handle_trigger()
    assert bridge.props[FLIGHT_PHASE] == state.TAXI_OUT
    assert sidecar.fsm.phase == state.TAXI_OUT

    bridge.props[REQ_TYPE] = "takeoff"
    bridge.props[REQ_RUNWAY] = "28L"
    bridge.props[REQ_TRIGGER] = "1"
    sidecar.handle_trigger()
    assert bridge.props[FLIGHT_PHASE] == state.TAKEOFF
    assert sidecar.fsm.phase == state.TAKEOFF


def test_handle_trigger_ifr_clearance_builds_craft_clearance(tmp_path: Path) -> None:
    """An ifr_clearance request with route/destination/altitude/squawk props
    produces a full CRAFT clearance in RESP_TEXT."""
    from sidecar.main import (
        AP_FREQ_DEPARTURE,
        REQ_ALTITUDE,
        REQ_DESTINATION,
        REQ_ROUTE,
        REQ_SQUAWK,
    )

    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "ifr_clearance",
        REQ_CALLSIGN: "UAL123",
        REQ_RUNWAY: "",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
        REQ_ROUTE: "SID then as filed",
        REQ_DESTINATION: "KLAX",
        REQ_ALTITUDE: "FL350",
        REQ_SQUAWK: "4271",
        AP_FREQ_DEPARTURE: "120.5",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    assert bridge.props[RESP_TEXT] == (
        "UAL123, cleared to KLAX via SID then as filed, "
        "climb maintain FL350, departure 120.5, squawk 4271."
    )
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[STATUS] == "idle"
    assert bridge.props[REQ_TRIGGER] == 0
    assert backend.said


def test_build_clearance_ifr_populates_craft_fields(tmp_path: Path) -> None:
    """_build_clearance copies the IFR request fields onto the Clearance."""
    from sidecar.main import (
        AP_FREQ_DEPARTURE,
        REQ_ALTITUDE,
        REQ_DESTINATION,
        REQ_ROUTE,
        REQ_SQUAWK,
    )

    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "ifr_clearance",
        REQ_CALLSIGN: "UAL123",
        REQ_RUNWAY: "",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_ROUTE: "DCT",
        REQ_DESTINATION: "KLAX",
        REQ_ALTITUDE: "6000",
        REQ_SQUAWK: "4271",
        AP_FREQ_DEPARTURE: "120.5",
    }
    sidecar, _, _ = _make_with_picture(tmp_path, props, pic)
    clearance = sidecar._build_clearance("ifr_clearance", "UAL123", pic)
    assert clearance.destination == "KLAX"
    assert clearance.route == "DCT"
    assert clearance.altitude == "6000"
    assert clearance.squawk == "4271"
    assert clearance.frequency == "120.5"


def test_handle_trigger_fsm_failure_still_writes_response(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """If the flight-phase machine raises, handle_trigger still writes
    RESP_TEXT/RESP_READY and resets the mailbox (the fsm call is guarded)."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL9",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("fsm blew up")

    monkeypatch.setattr(sidecar.fsm, "on_request", _boom)
    sidecar.handle_trigger()

    assert bridge.props[RESP_TEXT].startswith("UAL9")
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[STATUS] == "idle"
    assert bridge.props[REQ_TRIGGER] == 0


# ---------------------------------------------------------------------------
# Phase 8: grounding / data integrations — airspace check + SimBrief wiring
# ---------------------------------------------------------------------------


def test_handle_trigger_airspace_check_states_class_and_warning(tmp_path: Path) -> None:
    """An airspace_check request reads the published class + warning and voices
    a reply that mentions both."""
    from sidecar.main import AIRSPACE_CLASS, AIRSPACE_WARN

    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "airspace_check",
        REQ_CALLSIGN: "N12",
        REQ_RUNWAY: "",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
        AIRSPACE_CLASS: "B",
        AIRSPACE_WARN: "Clearance required before entering.",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    resp = bridge.props[RESP_TEXT]
    assert "Class B" in resp
    assert "Clearance required before entering." in resp
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[STATUS] == "idle"
    assert bridge.props[REQ_TRIGGER] == 0
    assert backend.said


def test_build_clearance_airspace_check_populates_fields(tmp_path: Path) -> None:
    """_build_clearance copies the airspace class + warning onto the Clearance."""
    from sidecar.main import AIRSPACE_CLASS, AIRSPACE_WARN

    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "airspace_check",
        REQ_CALLSIGN: "N12",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        AIRSPACE_CLASS: "C",
        AIRSPACE_WARN: "Establish two-way radio communication.",
    }
    sidecar, _, _ = _make_with_picture(tmp_path, props, pic)
    clearance = sidecar._build_clearance("airspace_check", "N12", pic)
    assert clearance.airspace_class == "C"
    assert clearance.airspace_warning == "Establish two-way radio communication."


def test_handle_trigger_simbrief_confirms_plan(tmp_path: Path) -> None:
    """A simbrief request with route/destination/altitude props confirms the
    imported plan in RESP_TEXT."""
    from sidecar.main import REQ_ALTITUDE, REQ_DESTINATION, REQ_ROUTE

    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "simbrief",
        REQ_CALLSIGN: "UAL123",
        REQ_RUNWAY: "",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
        REQ_ROUTE: "SID then as filed",
        REQ_DESTINATION: "KLAX",
        REQ_ALTITUDE: "FL350",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    assert bridge.props[RESP_TEXT] == (
        "UAL123, flight plan confirmed: KLAX via SID then as filed, "
        "climb maintain FL350."
    )
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[STATUS] == "idle"
    assert bridge.props[REQ_TRIGGER] == 0
    assert backend.said


def test_build_clearance_simbrief_populates_plan_fields(tmp_path: Path) -> None:
    """_build_clearance copies the SimBrief request fields onto the Clearance and
    leaves frequency empty (no controller-contact tail)."""
    from sidecar.main import REQ_ALTITUDE, REQ_DESTINATION, REQ_ROUTE

    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "simbrief",
        REQ_CALLSIGN: "UAL123",
        REQ_RUNWAY: "",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_ROUTE: "DCT",
        REQ_DESTINATION: "KLAX",
        REQ_ALTITUDE: "6000",
    }
    sidecar, _, _ = _make_with_picture(tmp_path, props, pic)
    clearance = sidecar._build_clearance("simbrief", "UAL123", pic)
    assert clearance.destination == "KLAX"
    assert clearance.route == "DCT"
    assert clearance.altitude == "6000"
    assert clearance.frequency == ""


def test_handle_trigger_ctaf_self_announce_no_contact_tail(tmp_path: Path) -> None:
    """A ctaf request voices a self-announce with no controller-contact tail."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "ctaf",
        REQ_CALLSIGN: "N12345",
        REQ_RUNWAY: "",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    resp = bridge.props[RESP_TEXT]
    assert "N12345" in resp
    assert "Contact" not in resp
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[STATUS] == "idle"
    assert bridge.props[REQ_TRIGGER] == 0
    assert backend.said


# ---------------------------------------------------------------------------
# Phase 9: training / gamification (scenario / kneeboard / career / coaching)
# ---------------------------------------------------------------------------


def test_handle_trigger_kneeboard_publishes_card_and_writes_resp(tmp_path: Path) -> None:
    """A kneeboard request publishes a non-empty /ai-atc/kneeboard and RESP_TEXT."""
    import dataclasses

    from sidecar.main import KNEEBOARD

    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "kneeboard",
        REQ_CALLSIGN: "N12",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    # Keep the test offline/deterministic: no live METAR fetch.
    sidecar.settings = dataclasses.replace(sidecar.settings, metar_enabled=False)
    sidecar.handle_trigger()

    card = bridge.props.get(KNEEBOARD, "")
    assert card, "kneeboard card should be published"
    assert "KNEEBOARD" in card
    assert pic.icao in card  # airport line carries the ICAO
    assert "28L" in card  # the synthetic active runway
    assert bridge.props[RESP_TEXT], "a spoken summary should be written"
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[STATUS] == "idle"
    assert bridge.props[REQ_TRIGGER] == 0
    assert backend.said


def test_handle_trigger_scenario_deterministic_for_fixed_seed(tmp_path: Path) -> None:
    """A scenario request is deterministic: same seed -> identical RESP_TEXT."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "scenario",
        REQ_CALLSIGN: "N12",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()
    first = bridge.props[RESP_TEXT]
    assert first, "a scenario summary should be voiced"
    assert "training scenario" in first.lower()

    # The scenario seed derives from callsign + memory.count; announce handlers
    # never grow session memory, so a second identical request is byte-identical.
    bridge.props[REQ_TRIGGER] = "1"
    sidecar.handle_trigger()
    second = bridge.props[RESP_TEXT]
    assert second == first
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[REQ_TRIGGER] == 0


def test_handle_trigger_career_voices_rank_from_tmp_file(tmp_path: Path) -> None:
    """A career request with a populated career file voices the computed rank."""
    import dataclasses

    from sidecar import career

    career_file = tmp_path / "career.json"
    # 100 points -> "Private" rank (>= 100 threshold).
    career.save_career(career.CareerStats(landings=10, points=100), career_file)

    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "career",
        REQ_CALLSIGN: "N12",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.settings = dataclasses.replace(
        sidecar.settings, career_path=str(career_file)
    )
    sidecar.handle_trigger()

    resp = bridge.props[RESP_TEXT]
    assert "Private" in resp
    assert "100 points" in resp
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[STATUS] == "idle"
    assert bridge.props[REQ_TRIGGER] == 0
    assert backend.said


def test_handle_trigger_student_mode_readback_includes_coach_feedback(
    tmp_path: Path,
) -> None:
    """In student mode an incomplete readback appends coach feedback to RESP_TEXT."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL9",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
        MODE: "student",
    }
    sidecar, bridge, _ = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()  # issue the clearance first

    bridge.props[REQ_TYPE] = "readback"
    bridge.props[READBACK_HEARD] = "wilco"  # nothing salient -> incomplete
    bridge.props[REQ_TRIGGER] = "1"
    sidecar.handle_trigger()

    resp = bridge.props[RESP_TEXT]
    assert "Check your readback" in resp  # coach feedback appended
    assert "missing:" in resp
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[REQ_TRIGGER] == 0

    # Mode-gating: the same incomplete readback in normal mode has no coaching.
    props_normal = dict(props)
    props_normal[MODE] = "normal"
    sc2, bridge2, _ = _make_with_picture(tmp_path, props_normal, pic)
    sc2.handle_trigger()
    bridge2.props[REQ_TYPE] = "readback"
    bridge2.props[READBACK_HEARD] = "wilco"
    bridge2.props[REQ_TRIGGER] = "1"
    sc2.handle_trigger()
    assert "Check your readback" not in bridge2.props[RESP_TEXT]


# ---------------------------------------------------------------------------
# Phase 10: sidecar wiring — advisory guardrail, region pack, weather tokens
# ---------------------------------------------------------------------------


def test_handle_trigger_taxi_publishes_empty_guardrail(tmp_path: Path) -> None:
    """A normal taxi clearance publishes a (clean, empty) /ai-atc/guardrail."""
    from sidecar.main import GUARDRAIL

    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL9",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    assert GUARDRAIL in bridge.props  # the guardrail is always published
    assert bridge.props[GUARDRAIL] == ""  # nothing wrong with a normal taxi
    assert bridge.props[RESP_TEXT] == "UAL9, taxi to runway 28L, hold short of 28L."
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[REQ_TRIGGER] == 0


def test_handle_trigger_guardrail_flags_nonactive_runway_but_still_replies(
    tmp_path: Path,
) -> None:
    """A takeoff cleared on a NON-active runway publishes a non-empty guardrail
    issue, yet STILL writes RESP_TEXT/RESP_READY (advisory, never blocking)."""
    from sidecar.main import AP_RUNWAY_COUNT, AP_RUNWAY_PREFIX, GUARDRAIL

    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "takeoff",
        REQ_CALLSIGN: "UAL1",
        REQ_RUNWAY: "10R",  # cleared for takeoff on 10R...
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
        # ...but the mailbox declares 28L as the only ACTIVE runway.
        AP_RUNWAY_COUNT: "1",
        f"{AP_RUNWAY_PREFIX}[0]/id": "28L",
        f"{AP_RUNWAY_PREFIX}[0]/heading": "284",
        f"{AP_RUNWAY_PREFIX}[0]/active": "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    issues = bridge.props.get(GUARDRAIL, "")
    assert issues, "guardrail should flag the non-active runway clearance"
    assert "10R" in issues
    # Advisory only: the clearance is still issued and the UI is unblocked.
    assert "cleared for takeoff" in bridge.props[RESP_TEXT].lower()
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[STATUS] == "idle"
    assert bridge.props[REQ_TRIGGER] == 0
    assert backend.said


def test_handle_trigger_region_uk_alters_offline_wording(tmp_path: Path) -> None:
    """With region='uk', offline wording is substituted (active runway -> in use)."""
    import dataclasses

    from sidecar.main import GUARDRAIL

    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "takeoff",
        REQ_CALLSIGN: "UAL1",
        REQ_RUNWAY: "",  # no runway -> 'the active runway' placeholder appears
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.settings = dataclasses.replace(sidecar.settings, region="uk")
    sidecar.handle_trigger()

    resp = bridge.props[RESP_TEXT]
    assert "runway in use" in resp
    assert "the active runway" not in resp
    # Region substitution does not break the advisory guardrail or the mailbox.
    assert GUARDRAIL in bridge.props
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[REQ_TRIGGER] == 0


def test_handle_trigger_windshear_token_renders_offline_template(tmp_path: Path) -> None:
    """A windshear request flows through to the new offline phraseology template."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "windshear",
        REQ_CALLSIGN: "UAL1",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
    }
    sidecar, bridge, backend = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    assert bridge.props[RESP_TEXT] == "UAL1, windshear alert, runway 28L, use caution."
    assert bridge.props[RESP_READY] == 1
    assert bridge.props[STATUS] == "idle"
    assert bridge.props[REQ_TRIGGER] == 0
    assert backend.said


def test_handle_trigger_updates_blackboard_snapshot(tmp_path: Path) -> None:
    """handle_trigger refreshes the shared world-state blackboard each request."""
    pic = _synthetic_picture()
    props = {
        AIRPORT_ID: pic.icao,
        REQ_TYPE: "taxi",
        REQ_CALLSIGN: "UAL9",
        REQ_RUNWAY: "28L",
        POS_LAT: "37.620",
        POS_LON: "-122.380",
        REQ_TRIGGER: "1",
        MODE: "student",
    }
    sidecar, bridge, _ = _make_with_picture(tmp_path, props, pic)
    sidecar.handle_trigger()

    snap = sidecar.blackboard.snapshot()
    assert snap["airport"] == pic.icao
    assert snap["mode"] == "student"
    assert snap["controller"] == sidecar.persona.name
    assert snap["language"] == "en"
    assert snap["region"] == "us"
