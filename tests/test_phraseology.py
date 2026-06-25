"""Tests for sidecar/phraseology.py — exact offline templates + online fallback."""

from __future__ import annotations

from typing import Any

from sidecar.gemini_client import OfflineError
from sidecar.phraseology import Clearance, PhraseResult, phrase_offline, phrase_online


class _FakeClient:
    def __init__(self, response: Any = None, raise_offline: bool = False) -> None:
        self._response = response
        self._raise_offline = raise_offline
        self.calls = 0

    def generate(self, prompt: str, schema: type, *, model: str | None = None) -> Any:
        self.calls += 1
        if self._raise_offline:
            raise OfflineError("offline")
        return self._response


# ---------------------------------------------------------------------------
# Offline templates — exact strings
# ---------------------------------------------------------------------------


def test_phrase_offline_taxi_exact() -> None:
    c = Clearance(
        callsign="UAL123",
        clearance_type="taxi",
        taxi_route=["A", "B"],
        active_runway="28R",
        hold_short="28R",
    )
    assert phrase_offline(c) == "UAL123, taxi to runway 28R via A, B, hold short of 28R."


def test_phrase_offline_taxi_without_route() -> None:
    c = Clearance(callsign="N12", clearance_type="taxi", active_runway="19")
    assert phrase_offline(c) == "N12, taxi to runway 19."


def test_phrase_offline_pushback_exact() -> None:
    c = Clearance(callsign="SWA45", clearance_type="pushback")
    assert phrase_offline(c) == "SWA45, pushback approved."


def test_phrase_offline_takeoff_exact() -> None:
    c = Clearance(callsign="DAL2", clearance_type="takeoff", active_runway="01L")
    assert phrase_offline(c) == "DAL2, runway 01L, cleared for takeoff."


# ---------------------------------------------------------------------------
# Online path with fallback
# ---------------------------------------------------------------------------


def test_phrase_online_returns_model_text() -> None:
    client = _FakeClient(response=PhraseResult(text="United 123, taxi via Alpha."))
    c = Clearance(callsign="UAL123", taxi_route=["A"])
    assert phrase_online(c, client) == "United 123, taxi via Alpha."  # type: ignore[arg-type]
    assert client.calls == 1


def test_phrase_online_falls_back_on_offline_error() -> None:
    client = _FakeClient(raise_offline=True)
    c = Clearance(
        callsign="UAL123",
        clearance_type="taxi",
        taxi_route=["A", "B"],
        active_runway="28R",
        hold_short="28R",
    )
    assert phrase_online(c, client) == phrase_offline(c)  # type: ignore[arg-type]


def test_phrase_online_empty_text_falls_back() -> None:
    client = _FakeClient(response=PhraseResult(text="   "))
    c = Clearance(callsign="UAL123", clearance_type="pushback")
    assert phrase_online(c, client) == phrase_offline(c)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Item 2: aircraft_type in prompt
# ---------------------------------------------------------------------------


def test_build_prompt_includes_aircraft_type_when_set() -> None:
    """When aircraft_type is provided, the prompt contains it."""
    from sidecar.phraseology import _build_prompt

    c = Clearance(callsign="N12", clearance_type="taxi", aircraft_type="c172p")
    prompt = _build_prompt(c)
    assert "c172p" in prompt
    assert "aircraft type" in prompt


def test_build_prompt_omits_aircraft_type_line_when_empty() -> None:
    """When aircraft_type is empty, no aircraft-type line appears in prompt."""
    from sidecar.phraseology import _build_prompt

    c = Clearance(callsign="N12", clearance_type="taxi", aircraft_type="")
    prompt = _build_prompt(c)
    assert "aircraft type" not in prompt


def test_phrase_offline_ignores_aircraft_type() -> None:
    """phrase_offline output is unchanged whether aircraft_type is set or not."""
    c_no_type = Clearance(callsign="UAL1", clearance_type="taxi", active_runway="28R")
    c_with_type = Clearance(
        callsign="UAL1", clearance_type="taxi", active_runway="28R", aircraft_type="b738"
    )
    assert phrase_offline(c_no_type) == phrase_offline(c_with_type)
