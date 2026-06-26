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
    HEARTBEAT,
    POS_LAT,
    POS_LON,
    REQ_CALLSIGN,
    REQ_RUNWAY,
    REQ_TRIGGER,
    REQ_TYPE,
    RESP_READY,
    RESP_TEXT,
    SIDECAR_MODE,
    STATUS,
    Sidecar,
)
from sidecar.tts import TTS, TTSBackend

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
