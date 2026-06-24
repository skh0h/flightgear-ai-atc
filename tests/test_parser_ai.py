"""Tests for sidecar/parser_ai.py — fake Gemini client, no network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sidecar.airport_picture import AIAirportResponse, Node, ParkingSpot, Segment
from sidecar.gemini_client import OfflineError
from sidecar.parser_ai import parse_with_ai

_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "KSFO.groundnet.xml"


class _FakeClient:
    """Stand-in matching GeminiClient.generate()'s signature."""

    def __init__(self, response: Any = None, raise_offline: bool = False) -> None:
        self._response = response
        self._raise_offline = raise_offline
        self.calls = 0

    def generate(self, prompt: str, schema: type, *, model: str | None = None) -> Any:
        self.calls += 1
        if self._raise_offline:
            raise OfflineError("forced offline")
        return self._response


def _ai_response() -> AIAirportResponse:
    return AIAirportResponse(
        parking=[
            ParkingSpot(id=0, name="A1", type="gate", lat=37.6, lon=-122.3, heading=90.0)
        ],
        nodes=[Node(index=209, lat=37.6, lon=-122.38), Node(index=210, lat=37.61, lon=-122.39)],
        segments=[Segment(begin=209, end=210, name="Alpha")],
    )


def test_ai_success_returns_source_ai_with_computed_fields() -> None:
    client = _FakeClient(response=_ai_response())
    xml = "<groundnet><TaxiNodes></TaxiNodes></groundnet>"
    pic = parse_with_ai("KSFO", xml, client)  # type: ignore[arg-type]
    assert client.calls == 1
    assert pic.source == "ai"
    assert pic.icao == "KSFO"
    # taxi_graph is computed locally from the AI-provided segments.
    assert pic.taxi_graph == {209: [210], 210: [209]}
    assert pic.segments[0].name == "Alpha"
    assert len(pic.groundnet_hash) == 64
    assert pic.generated_at


def test_ai_offline_falls_back_to_code_parser() -> None:
    client = _FakeClient(raise_offline=True)
    xml = _FIXTURE.read_text()
    pic = parse_with_ai("KSFO", xml, client)  # type: ignore[arg-type]
    assert client.calls == 1
    assert pic.source == "code"
    assert len(pic.nodes) > 0  # the real fixture was parsed by the code path


def test_hash_matches_between_ai_and_offline_paths() -> None:
    xml = _FIXTURE.read_text()
    ai_pic = parse_with_ai("KSFO", xml, _FakeClient(response=_ai_response()))  # type: ignore[arg-type]
    code_pic = parse_with_ai("KSFO", xml, _FakeClient(raise_offline=True))  # type: ignore[arg-type]
    # Identical groundnet bytes -> identical cache key, whichever path ran.
    assert ai_pic.groundnet_hash == code_pic.groundnet_hash
