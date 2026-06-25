"""Tests for sidecar/main.py — Sidecar orchestration with fakes, no network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sidecar.config import Settings
from sidecar.cache import PictureCache
from sidecar.gemini_client import OfflineError
from sidecar.main import (
    AIRPORT_ID,
    POS_LAT,
    POS_LON,
    REQ_CALLSIGN,
    REQ_RUNWAY,
    REQ_TRIGGER,
    REQ_TYPE,
    RESP_READY,
    RESP_TEXT,
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
