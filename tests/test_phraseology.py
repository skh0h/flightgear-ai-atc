"""Tests for sidecar/phraseology.py — exact offline templates + online fallback."""

from __future__ import annotations

from typing import Any

from sidecar.gemini_client import OfflineError
from sidecar.phraseology import (
    Clearance,
    PhraseResult,
    expected_readback,
    phrase_offline,
    phrase_online,
)


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


# ---------------------------------------------------------------------------
# Arrival types — offline templates
# ---------------------------------------------------------------------------


def test_phrase_offline_approach_exact() -> None:
    c = Clearance(callsign="UAL1", clearance_type="approach", active_runway="28R")
    assert phrase_offline(c) == "UAL1, expect approach runway 28R."


def test_phrase_offline_ils_exact() -> None:
    c = Clearance(callsign="DAL5", clearance_type="ils", active_runway="10L")
    assert phrase_offline(c) == "DAL5, cleared ILS runway 10L approach."


def test_phrase_offline_airfield_in_sight_exact() -> None:
    c = Clearance(callsign="N12", clearance_type="airfield_in_sight", active_runway="01")
    assert phrase_offline(c) == "N12, cleared visual approach runway 01."


def test_phrase_offline_radio_check_exact() -> None:
    c = Clearance(callsign="SWA9", clearance_type="radio_check")
    assert phrase_offline(c) == "SWA9, reading you five by five."


def test_phrase_offline_approach_no_runway() -> None:
    """approach without active_runway falls back to 'active runway' placeholder."""
    c = Clearance(callsign="UAL1", clearance_type="approach")
    result = phrase_offline(c)
    assert "UAL1" in result
    assert "active runway" in result


def test_phrase_offline_approach_with_remarks() -> None:
    """remarks (e.g. distance/bearing) are appended after the approach clearance."""
    c = Clearance(callsign="UAL1", clearance_type="approach", active_runway="28R", remarks="15 nm, 270 degrees")
    result = phrase_offline(c)
    assert result == "UAL1, expect approach runway 28R. 15 nm, 270 degrees"


# ---------------------------------------------------------------------------
# Arrival types — online → offline fallback
# ---------------------------------------------------------------------------


def test_phrase_online_falls_back_for_ils_on_offline_error() -> None:
    client = _FakeClient(raise_offline=True)
    c = Clearance(callsign="UAL1", clearance_type="ils", active_runway="28R")
    assert phrase_online(c, client) == phrase_offline(c)  # type: ignore[arg-type]


def test_phrase_online_returns_model_text_for_approach() -> None:
    client = _FakeClient(response=PhraseResult(text="United 1, expect the visual, runway 28R."))
    c = Clearance(callsign="UAL1", clearance_type="approach", active_runway="28R")
    assert phrase_online(c, client) == "United 1, expect the visual, runway 28R."  # type: ignore[arg-type]
    assert client.calls == 1


def test_phrase_online_falls_back_for_approach_on_offline_error() -> None:
    client = _FakeClient(raise_offline=True)
    c = Clearance(callsign="UAL1", clearance_type="approach", active_runway="28R")
    assert phrase_online(c, client) == phrase_offline(c)  # type: ignore[arg-type]


def test_phrase_online_returns_model_text_for_ils() -> None:
    client = _FakeClient(response=PhraseResult(text="Delta 5, cleared ILS runway 10 left."))
    c = Clearance(callsign="DAL5", clearance_type="ils", active_runway="10L")
    assert phrase_online(c, client) == "Delta 5, cleared ILS runway 10 left."  # type: ignore[arg-type]
    assert client.calls == 1


def test_phrase_online_returns_model_text_for_airfield_in_sight() -> None:
    client = _FakeClient(
        response=PhraseResult(text="November 12, cleared visual approach runway 1.")
    )
    c = Clearance(callsign="N12", clearance_type="airfield_in_sight", active_runway="01")
    assert phrase_online(c, client) == "November 12, cleared visual approach runway 1."  # type: ignore[arg-type]
    assert client.calls == 1


def test_phrase_online_falls_back_for_airfield_in_sight_on_offline_error() -> None:
    client = _FakeClient(raise_offline=True)
    c = Clearance(callsign="N12", clearance_type="airfield_in_sight", active_runway="01")
    assert phrase_online(c, client) == phrase_offline(c)  # type: ignore[arg-type]


def test_phrase_online_returns_model_text_for_radio_check() -> None:
    client = _FakeClient(response=PhraseResult(text="Southwest 9, reading you loud and clear."))
    c = Clearance(callsign="SWA9", clearance_type="radio_check")
    assert phrase_online(c, client) == "Southwest 9, reading you loud and clear."  # type: ignore[arg-type]
    assert client.calls == 1


def test_phrase_online_falls_back_for_radio_check_on_offline_error() -> None:
    client = _FakeClient(raise_offline=True)
    c = Clearance(callsign="SWA9", clearance_type="radio_check")
    assert phrase_online(c, client) == phrase_offline(c)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _build_prompt: per-type guidance (Phase 1)
# ---------------------------------------------------------------------------


def test_build_prompt_includes_type_guidance_for_arrival() -> None:
    """_build_prompt appends the per-type ICAO guidance for an arrival type."""
    from sidecar.phraseology import _TYPE_GUIDANCE, _build_prompt

    c = Clearance(callsign="UAL1", clearance_type="approach", active_runway="28R")
    prompt = _build_prompt(c)
    assert _TYPE_GUIDANCE["approach"] in prompt
    assert "approach" in prompt


# ---------------------------------------------------------------------------
# Phase 3: emergency & abnormal phraseology — offline templates (exact)
# ---------------------------------------------------------------------------


def test_phrase_offline_mayday_exact() -> None:
    c = Clearance(callsign="UAL123", clearance_type="mayday")
    assert phrase_offline(c) == (
        "UAL123, roger mayday. State souls on board, fuel remaining, and intentions."
    )


def test_phrase_offline_pan_pan_exact() -> None:
    c = Clearance(callsign="N12", clearance_type="pan_pan")
    assert phrase_offline(c) == "N12, roger pan-pan, say intentions."


def test_phrase_offline_gear_emergency_exact() -> None:
    c = Clearance(callsign="DAL2", clearance_type="gear_emergency", active_runway="28R")
    assert phrase_offline(c) == (
        "DAL2, roger. Emergency services are standing by, "
        "cleared to land runway 28R."
    )


def test_phrase_offline_gear_emergency_no_runway_uses_placeholder() -> None:
    c = Clearance(callsign="DAL2", clearance_type="gear_emergency")
    result = phrase_offline(c)
    assert "DAL2" in result
    assert "the active runway" in result


def test_phrase_offline_min_fuel_exact() -> None:
    c = Clearance(callsign="SWA45", clearance_type="min_fuel")
    assert phrase_offline(c) == (
        "SWA45, roger minimum fuel, you are number one for the approach."
    )


def test_phrase_offline_diversion_with_target_exact() -> None:
    c = Clearance(
        callsign="UAL1", clearance_type="diversion", divert_target="KSQL San Carlos"
    )
    assert phrase_offline(c) == (
        "UAL1, roger, cleared to divert to KSQL San Carlos, "
        "descend at pilot's discretion."
    )


def test_phrase_offline_diversion_generic_exact() -> None:
    c = Clearance(callsign="UAL1", clearance_type="diversion")
    assert phrase_offline(c) == (
        "UAL1, roger, cleared to divert to the nearest suitable airport, "
        "descend at pilot's discretion."
    )


def test_phrase_offline_go_around_exact() -> None:
    c = Clearance(callsign="DAL2", clearance_type="go_around")
    assert phrase_offline(c) == (
        "DAL2, roger, going around, fly runway heading, climb to pattern altitude."
    )


def test_phrase_offline_squawk_7500_exact() -> None:
    c = Clearance(callsign="N12", clearance_type="squawk_7500")
    assert phrase_offline(c) == (
        "N12, roger, squawk seven five zero zero acknowledged, "
        "say intentions when able."
    )


def test_phrase_offline_squawk_7600_exact() -> None:
    c = Clearance(callsign="N12", clearance_type="squawk_7600")
    assert phrase_offline(c) == (
        "N12, radio failure acknowledged, squawk seven six zero zero, "
        "continue and look for light-gun signals."
    )


def test_phrase_offline_squawk_7700_exact() -> None:
    c = Clearance(callsign="N12", clearance_type="squawk_7700")
    assert phrase_offline(c) == (
        "N12, roger emergency, squawk seven seven zero zero, "
        "state nature of emergency and intentions."
    )


# ---------------------------------------------------------------------------
# Phase 3: emergencies — online return-text + offline-fallback
# ---------------------------------------------------------------------------


def test_phrase_online_returns_model_text_for_mayday() -> None:
    client = _FakeClient(response=PhraseResult(text="United 123, roger mayday, say souls and fuel."))
    c = Clearance(callsign="UAL123", clearance_type="mayday")
    assert phrase_online(c, client) == "United 123, roger mayday, say souls and fuel."  # type: ignore[arg-type]
    assert client.calls == 1


def test_phrase_online_falls_back_for_mayday_on_offline_error() -> None:
    client = _FakeClient(raise_offline=True)
    c = Clearance(callsign="UAL123", clearance_type="mayday")
    assert phrase_online(c, client) == phrase_offline(c)  # type: ignore[arg-type]


def test_phrase_online_returns_model_text_for_diversion() -> None:
    client = _FakeClient(response=PhraseResult(text="United 1, cleared to divert to Kilo Sierra Quebec Lima."))
    c = Clearance(callsign="UAL1", clearance_type="diversion", divert_target="KSQL San Carlos")
    assert phrase_online(c, client) == "United 1, cleared to divert to Kilo Sierra Quebec Lima."  # type: ignore[arg-type]
    assert client.calls == 1


def test_phrase_online_falls_back_for_diversion_on_offline_error() -> None:
    client = _FakeClient(raise_offline=True)
    c = Clearance(callsign="UAL1", clearance_type="diversion", divert_target="KSQL San Carlos")
    assert phrase_online(c, client) == phrase_offline(c)  # type: ignore[arg-type]


def test_phrase_online_returns_model_text_for_squawk_7700() -> None:
    client = _FakeClient(response=PhraseResult(text="November 12, roger emergency, state your intentions."))
    c = Clearance(callsign="N12", clearance_type="squawk_7700")
    assert phrase_online(c, client) == "November 12, roger emergency, state your intentions."  # type: ignore[arg-type]
    assert client.calls == 1


def test_phrase_online_falls_back_for_squawk_7700_on_offline_error() -> None:
    client = _FakeClient(raise_offline=True)
    c = Clearance(callsign="N12", clearance_type="squawk_7700")
    assert phrase_online(c, client) == phrase_offline(c)  # type: ignore[arg-type]


def test_build_prompt_includes_type_guidance_for_emergency() -> None:
    """_build_prompt appends the per-type ICAO guidance for an emergency type."""
    from sidecar.phraseology import _TYPE_GUIDANCE, _build_prompt

    c = Clearance(callsign="UAL1", clearance_type="mayday")
    prompt = _build_prompt(c)
    assert _TYPE_GUIDANCE["mayday"] in prompt
    assert "aircraft type" not in prompt


# ---------------------------------------------------------------------------
# Phase 4: persona / mood / session context in the online prompt
# ---------------------------------------------------------------------------


def test_build_prompt_includes_persona_mood_context_when_provided() -> None:
    """When persona/mood/context are supplied, they appear in the prompt."""
    from sidecar.personality import ControllerPersona
    from sidecar.phraseology import _build_prompt

    c = Clearance(callsign="UAL1", clearance_type="taxi", active_runway="28R")
    persona = ControllerPersona(name="Dana Whitfield", style="calm and methodical")
    prompt = _build_prompt(
        c,
        context="UAL1: taxi -> UAL1, taxi to runway 28R.",
        persona=persona,
        mood="brisk",
    )
    assert "Controller: Dana Whitfield, calm and methodical." in prompt
    assert "Mood: brisk." in prompt
    assert "Session so far:" in prompt
    assert "UAL1: taxi ->" in prompt


def test_build_prompt_omits_persona_mood_context_by_default() -> None:
    """Without the new kwargs, none of the Phase 4 lines appear (no regression)."""
    from sidecar.phraseology import _build_prompt

    c = Clearance(callsign="UAL1", clearance_type="taxi", active_runway="28R")
    prompt = _build_prompt(c)
    assert "Controller:" not in prompt
    assert "Mood:" not in prompt
    assert "Session so far:" not in prompt


def test_build_prompt_default_is_byte_identical_to_explicit_empty() -> None:
    """Passing empty defaults must reproduce the legacy prompt byte-for-byte."""
    from sidecar.phraseology import _build_prompt

    c = Clearance(
        callsign="UAL1",
        clearance_type="taxi",
        taxi_route=["A", "B"],
        active_runway="28R",
        hold_short="28R",
        aircraft_type="c172p",
    )
    assert _build_prompt(c) == _build_prompt(c, context="", persona=None, mood="")


def test_phrase_online_forwards_persona_mood_context_to_prompt() -> None:
    """phrase_online forwards the new kwargs into the prompt sent to the client."""
    from sidecar.personality import ControllerPersona

    captured: dict[str, str] = {}

    class _CapturingClient:
        def generate(self, prompt: str, schema: type, *, model: str | None = None) -> Any:
            captured["prompt"] = prompt
            return PhraseResult(text="ok")

    c = Clearance(callsign="UAL1", clearance_type="taxi", active_runway="28R")
    persona = ControllerPersona(name="Hiroshi Tanaka", style="terse but precise")
    out = phrase_online(
        c,
        _CapturingClient(),  # type: ignore[arg-type]
        context="N12: taxi -> N12, taxi to runway 1.",
        persona=persona,
        mood="weary",
    )
    assert out == "ok"
    assert "Hiroshi Tanaka" in captured["prompt"]
    assert "Mood: weary." in captured["prompt"]
    assert "N12: taxi ->" in captured["prompt"]


# ---------------------------------------------------------------------------
# Phase 5: expected_readback — canonical pilot readback strings (exact)
# ---------------------------------------------------------------------------


def test_expected_readback_taxi_exact() -> None:
    c = Clearance(
        callsign="UAL123",
        clearance_type="taxi",
        taxi_route=["A", "B"],
        active_runway="28R",
        hold_short="28R",
    )
    assert expected_readback(c) == "runway 28R via A B hold short 28R"


def test_expected_readback_takeoff_exact() -> None:
    c = Clearance(callsign="DAL2", clearance_type="takeoff", active_runway="01L")
    assert expected_readback(c) == "cleared for takeoff 01L"


def test_expected_readback_approach_exact() -> None:
    c = Clearance(callsign="UAL1", clearance_type="approach", active_runway="28R")
    assert expected_readback(c) == "expect approach runway 28R"


def test_expected_readback_pushback_exact() -> None:
    c = Clearance(callsign="SWA45", clearance_type="pushback")
    assert expected_readback(c) == "pushback approved"


def test_expected_readback_ils_exact() -> None:
    c = Clearance(callsign="DAL5", clearance_type="ils", active_runway="10L")
    assert expected_readback(c) == "cleared ils runway 10L approach"


def test_expected_readback_taxi_without_route() -> None:
    c = Clearance(callsign="N12", clearance_type="taxi", active_runway="19")
    assert expected_readback(c) == "runway 19"


def test_expected_readback_generic_fallback_for_other_types() -> None:
    c = Clearance(callsign="N12", clearance_type="go_around")
    assert expected_readback(c) == "go around"


def test_expected_readback_omits_fg_bool_false_runway() -> None:
    """The FG bool-false 'false' artifact never leaks into a readback string."""
    c = Clearance(callsign="N12", clearance_type="takeoff", active_runway="false")
    assert "false" not in expected_readback(c)


def test_phrase_offline_relief_handoff_includes_remarks() -> None:
    """The relief-handoff offline template voices the briefing carried in remarks."""
    c = Clearance(
        callsign="Position",
        clearance_type="relief_handoff",
        remarks="This is Dana Whitfield taking over the position.",
    )
    out = phrase_offline(c)
    assert out.startswith("Position, position relief in progress")
    assert "This is Dana Whitfield taking over the position." in out


# ---------------------------------------------------------------------------
# Phase 6: LAHSO + intersection departures
# ---------------------------------------------------------------------------


def test_phrase_offline_lahso_with_hold_short_exact() -> None:
    c = Clearance(
        callsign="UAL1",
        clearance_type="lahso",
        active_runway="28L",
        hold_short="01",
    )
    assert (
        phrase_offline(c)
        == "UAL1, cleared to land runway 28L, hold short of runway 01."
    )


def test_phrase_offline_lahso_without_hold_short_generic() -> None:
    c = Clearance(callsign="UAL1", clearance_type="lahso", active_runway="28L")
    assert (
        phrase_offline(c)
        == "UAL1, cleared to land runway 28L, hold short of the intersecting runway."
    )


def test_phrase_offline_intersection_departure_exact() -> None:
    c = Clearance(
        callsign="UAL1", clearance_type="intersection_departure", active_runway="28L"
    )
    assert (
        phrase_offline(c)
        == "UAL1, runway 28L at the intersection, cleared for takeoff."
    )


def test_append_wake_caution_adds_remark_when_lead_heavier() -> None:
    from sidecar.phraseology import append_wake_caution

    c = Clearance(callsign="UAL1", clearance_type="takeoff", aircraft_type="C172")
    append_wake_caution(c, "B744")
    assert "wake" in c.remarks.lower()


def test_append_wake_caution_noop_when_lead_not_heavier() -> None:
    from sidecar.phraseology import append_wake_caution

    c = Clearance(callsign="UAL1", clearance_type="takeoff", aircraft_type="B744")
    append_wake_caution(c, "C172")
    assert c.remarks == ""


# ---------------------------------------------------------------------------
# Phase 6: LAHSO + intersection departures — online return + offline fallback
# ---------------------------------------------------------------------------


def test_phrase_online_returns_model_text_for_lahso() -> None:
    client = _FakeClient(
        response=PhraseResult(text="United 1, cleared to land 28 left, hold short of runway 1.")
    )
    c = Clearance(
        callsign="UAL1", clearance_type="lahso", active_runway="28L", hold_short="01"
    )
    assert (
        phrase_online(c, client)  # type: ignore[arg-type]
        == "United 1, cleared to land 28 left, hold short of runway 1."
    )
    assert client.calls == 1


def test_phrase_online_falls_back_for_lahso_on_offline_error() -> None:
    client = _FakeClient(raise_offline=True)
    c = Clearance(
        callsign="UAL1", clearance_type="lahso", active_runway="28L", hold_short="01"
    )
    assert phrase_online(c, client) == phrase_offline(c)  # type: ignore[arg-type]


def test_phrase_online_falls_back_for_intersection_departure_on_offline_error() -> None:
    client = _FakeClient(raise_offline=True)
    c = Clearance(
        callsign="UAL1", clearance_type="intersection_departure", active_runway="28L"
    )
    assert phrase_online(c, client) == phrase_offline(c)  # type: ignore[arg-type]


def test_build_prompt_includes_type_guidance_for_lahso() -> None:
    from sidecar.phraseology import _TYPE_GUIDANCE, _build_prompt

    c = Clearance(callsign="UAL1", clearance_type="lahso", active_runway="28L")
    prompt = _build_prompt(c)
    assert _TYPE_GUIDANCE["lahso"] in prompt


# ---------------------------------------------------------------------------
# Phase 7: IFR clearance, holding, arrival_clearance, expect_approach,
# flow_control — offline templates (exact) + online return/fallback.
# ---------------------------------------------------------------------------


def test_phrase_offline_ifr_clearance_craft_exact() -> None:
    """An ifr_clearance carrying CRAFT fields renders the full CRAFT read-out."""
    c = Clearance(
        callsign="UAL123",
        clearance_type="ifr_clearance",
        destination="KLAX",
        route="SID then as filed",
        altitude="FL350",
        frequency="120.5",
        squawk="4271",
    )
    assert phrase_offline(c) == (
        "UAL123, cleared to KLAX via SID then as filed, "
        "climb maintain FL350, departure 120.5, squawk 4271."
    )


def test_phrase_offline_ifr_clearance_does_not_double_append_frequency() -> None:
    """The CRAFT departure freq must not be re-appended as a 'Contact' tail."""
    c = Clearance(
        callsign="UAL123",
        clearance_type="ifr_clearance",
        destination="KLAX",
        route="DCT",
        altitude="6000",
        frequency="120.5",
        squawk="4271",
    )
    out = phrase_offline(c)
    assert "Contact 120.5" not in out
    assert out.count("120.5") == 1


def test_phrase_offline_ifr_clearance_generic_without_craft_fields() -> None:
    """With no CRAFT fields, a sensible generic IFR clearance is produced."""
    c = Clearance(callsign="N12", clearance_type="ifr_clearance")
    assert phrase_offline(c) == (
        "N12, cleared to destination as filed, standby for full route clearance."
    )


def test_phrase_offline_holding_exact() -> None:
    c = Clearance(
        callsign="UAL1",
        clearance_type="holding",
        hold_fix="BOLDR",
        hold_direction="north",
        efc="1830Z",
    )
    assert phrase_offline(c) == (
        "UAL1, hold north of BOLDR as published, "
        "expect further clearance at 1830Z."
    )


def test_phrase_offline_arrival_clearance_exact() -> None:
    c = Clearance(
        callsign="UAL1",
        clearance_type="arrival_clearance",
        active_runway="28R",
        altitude="6000",
    )
    assert phrase_offline(c) == (
        "UAL1, expect vectors for the approach runway 28R, "
        "descend and maintain 6000."
    )


def test_phrase_offline_expect_approach_exact() -> None:
    c = Clearance(callsign="DAL5", clearance_type="expect_approach", active_runway="10L")
    assert phrase_offline(c) == "DAL5, expect the ILS approach runway 10L."


def test_phrase_offline_flow_control_exact() -> None:
    c = Clearance(
        callsign="SWA9", clearance_type="flow_control", efc="14:20Z-14:30Z"
    )
    assert phrase_offline(c) == (
        "SWA9, flow control in effect, "
        "expect departure clearance time 14:20Z-14:30Z."
    )


def test_phrase_online_returns_model_text_for_ifr_clearance() -> None:
    client = _FakeClient(
        response=PhraseResult(text="United 123, cleared to Los Angeles as filed.")
    )
    c = Clearance(
        callsign="UAL123",
        clearance_type="ifr_clearance",
        destination="KLAX",
        route="SID then as filed",
        altitude="FL350",
        frequency="120.5",
        squawk="4271",
    )
    assert phrase_online(c, client) == "United 123, cleared to Los Angeles as filed."  # type: ignore[arg-type]
    assert client.calls == 1


def test_phrase_online_falls_back_for_ifr_clearance_on_offline_error() -> None:
    client = _FakeClient(raise_offline=True)
    c = Clearance(
        callsign="UAL123",
        clearance_type="ifr_clearance",
        destination="KLAX",
        route="SID then as filed",
        altitude="FL350",
        frequency="120.5",
        squawk="4271",
    )
    assert phrase_online(c, client) == phrase_offline(c)  # type: ignore[arg-type]


def test_phrase_online_returns_model_text_for_holding() -> None:
    client = _FakeClient(
        response=PhraseResult(text="United 1, hold north of Boulder, as published.")
    )
    c = Clearance(
        callsign="UAL1",
        clearance_type="holding",
        hold_fix="BOLDR",
        hold_direction="north",
        efc="1830Z",
    )
    assert phrase_online(c, client) == "United 1, hold north of Boulder, as published."  # type: ignore[arg-type]
    assert client.calls == 1


def test_phrase_online_falls_back_for_holding_on_offline_error() -> None:
    client = _FakeClient(raise_offline=True)
    c = Clearance(
        callsign="UAL1",
        clearance_type="holding",
        hold_fix="BOLDR",
        hold_direction="north",
        efc="1830Z",
    )
    assert phrase_online(c, client) == phrase_offline(c)  # type: ignore[arg-type]


def test_build_prompt_includes_type_guidance_for_ifr_clearance() -> None:
    from sidecar.phraseology import _TYPE_GUIDANCE, _build_prompt

    c = Clearance(callsign="UAL1", clearance_type="ifr_clearance", destination="KLAX")
    prompt = _build_prompt(c)
    assert _TYPE_GUIDANCE["ifr_clearance"] in prompt


# ---------------------------------------------------------------------------
# Phase 8: CTAF, FSS briefing, SimBrief, airspace check — offline templates
# (exact) + online return/fallback + guidance.
# ---------------------------------------------------------------------------


def test_phrase_offline_ctaf_self_announce_exact() -> None:
    """CTAF self-announce is a blind pilot advisory with no controller handoff."""
    c = Clearance(callsign="N12345", clearance_type="ctaf", active_runway="28")
    out = phrase_offline(c)
    assert out == "Traffic, N12345, taxiing for departure, runway 28, traffic."
    assert "N12345" in out
    assert "Contact" not in out  # no controller-handoff tail on a self-announce


def test_phrase_offline_ctaf_uses_remarks_as_intentions() -> None:
    c = Clearance(
        callsign="N1", clearance_type="ctaf", remarks="back-taxiing runway 9"
    )
    assert phrase_offline(c) == "Traffic, N1, back-taxiing runway 9, traffic."


def test_phrase_offline_ctaf_suppresses_frequency_tail() -> None:
    """Even when frequency is set, ctaf never appends a 'Contact <freq>.' tail."""
    c = Clearance(
        callsign="N12345", clearance_type="ctaf", active_runway="28", frequency="122.8"
    )
    out = phrase_offline(c)
    assert "Contact" not in out
    assert "122.8" not in out


def test_phrase_offline_fss_briefing_default_exact() -> None:
    c = Clearance(callsign="N12345", clearance_type="fss_briefing")
    assert phrase_offline(c) == (
        "N12345, Flight Service, briefing on request, "
        "VFR not recommended check NOTAMs and TFRs."
    )


def test_phrase_offline_fss_briefing_with_remarks_no_double_append() -> None:
    c = Clearance(
        callsign="N1", clearance_type="fss_briefing", remarks="VFR not recommended."
    )
    out = phrase_offline(c)
    assert out == "N1, Flight Service, VFR not recommended."
    assert out.count("VFR not recommended.") == 1  # remarks not double-appended


def test_phrase_offline_simbrief_exact() -> None:
    c = Clearance(
        callsign="UAL123",
        clearance_type="simbrief",
        destination="KLAX",
        route="SID then as filed",
        altitude="FL350",
    )
    assert phrase_offline(c) == (
        "UAL123, flight plan confirmed: KLAX via SID then as filed, "
        "climb maintain FL350."
    )


def test_phrase_offline_simbrief_generic_without_fields() -> None:
    c = Clearance(callsign="N12", clearance_type="simbrief")
    assert phrase_offline(c) == (
        "N12, flight plan confirmed: destination via filed route, "
        "climb maintain filed altitude."
    )


def test_phrase_offline_airspace_check_with_warning_exact() -> None:
    c = Clearance(
        callsign="N12",
        clearance_type="airspace_check",
        airspace_class="B",
        airspace_warning="Clearance required before entering.",
    )
    assert phrase_offline(c) == (
        "N12, you are currently in Class B airspace. "
        "Clearance required before entering."
    )


def test_phrase_offline_airspace_check_defaults_to_class_g() -> None:
    c = Clearance(callsign="N12", clearance_type="airspace_check")
    assert phrase_offline(c) == "N12, you are currently in Class G airspace."


def test_phrase_online_returns_model_text_for_airspace_check() -> None:
    client = _FakeClient(
        response=PhraseResult(text="November 12, you are in Class Bravo airspace.")
    )
    c = Clearance(callsign="N12", clearance_type="airspace_check", airspace_class="B")
    assert phrase_online(c, client) == "November 12, you are in Class Bravo airspace."  # type: ignore[arg-type]
    assert client.calls == 1


def test_phrase_online_falls_back_for_airspace_check_on_offline_error() -> None:
    client = _FakeClient(raise_offline=True)
    c = Clearance(
        callsign="N12",
        clearance_type="airspace_check",
        airspace_class="B",
        airspace_warning="Clearance required before entering.",
    )
    assert phrase_online(c, client) == phrase_offline(c)  # type: ignore[arg-type]


def test_phrase_online_falls_back_for_simbrief_on_offline_error() -> None:
    client = _FakeClient(raise_offline=True)
    c = Clearance(
        callsign="UAL123",
        clearance_type="simbrief",
        destination="KLAX",
        route="DCT",
        altitude="FL350",
    )
    assert phrase_online(c, client) == phrase_offline(c)  # type: ignore[arg-type]


def test_build_prompt_includes_type_guidance_for_phase8_tokens() -> None:
    from sidecar.phraseology import _TYPE_GUIDANCE, _build_prompt

    for ctype in ("ctaf", "fss_briefing", "simbrief", "airspace_check"):
        c = Clearance(callsign="N12", clearance_type=ctype)
        prompt = _build_prompt(c)
        assert _TYPE_GUIDANCE[ctype] in prompt
        assert "aircraft type" not in prompt


# ---------------------------------------------------------------------------
# Phase 9: training / gamification announce types (scenario/kneeboard/career)
# ---------------------------------------------------------------------------


def test_phrase_offline_scenario_voices_remarks_verbatim() -> None:
    """A scenario clearance voices the supplied summary after the callsign only."""
    c = Clearance(
        callsign="N12",
        clearance_type="scenario",
        remarks="Training scenario at KSFO: VFR, wind 250 at 8 knots.",
    )
    assert phrase_offline(c) == (
        "N12, Training scenario at KSFO: VFR, wind 250 at 8 knots."
    )


def test_phrase_offline_scenario_default_when_no_remarks() -> None:
    """With no remarks a scenario falls back to a fixed default body."""
    c = Clearance(callsign="N12", clearance_type="scenario")
    assert phrase_offline(c) == "N12, training scenario ready."


def test_phrase_offline_kneeboard_voices_remarks_verbatim() -> None:
    c = Clearance(
        callsign="N12",
        clearance_type="kneeboard",
        remarks="kneeboard updated for KSFO, 1 active runway(s).",
    )
    assert phrase_offline(c) == "N12, kneeboard updated for KSFO, 1 active runway(s)."


def test_phrase_offline_kneeboard_default_when_no_remarks() -> None:
    c = Clearance(callsign="N12", clearance_type="kneeboard")
    assert phrase_offline(c) == "N12, kneeboard updated and available."


def test_phrase_offline_career_voices_remarks_verbatim() -> None:
    c = Clearance(
        callsign="N12",
        clearance_type="career",
        remarks="career rank Student, 30 points, 3 landings logged.",
    )
    assert phrase_offline(c) == "N12, career rank Student, 30 points, 3 landings logged."


def test_phrase_offline_career_default_when_no_remarks() -> None:
    c = Clearance(callsign="N12", clearance_type="career")
    assert phrase_offline(c) == "N12, career stats updated."


def test_phrase_offline_announce_types_never_append_freq_or_remarks_tail() -> None:
    """Announce types return early: no 'Contact ...' or doubled remarks tail."""
    c = Clearance(
        callsign="N12",
        clearance_type="kneeboard",
        remarks="kneeboard ready.",
        frequency="121.9",
    )
    assert phrase_offline(c) == "N12, kneeboard ready."


def test_phrase_online_returns_model_text_for_scenario() -> None:
    client = _FakeClient(
        response=PhraseResult(text="November 12, training scenario set: VFR, light wind.")
    )
    c = Clearance(callsign="N12", clearance_type="scenario", remarks="VFR, light wind.")
    assert phrase_online(c, client) == (  # type: ignore[arg-type]
        "November 12, training scenario set: VFR, light wind."
    )
    assert client.calls == 1


def test_phrase_online_falls_back_for_career_on_offline_error() -> None:
    client = _FakeClient(raise_offline=True)
    c = Clearance(
        callsign="N12",
        clearance_type="career",
        remarks="career rank Student, 30 points.",
    )
    assert phrase_online(c, client) == phrase_offline(c)  # type: ignore[arg-type]


def test_build_prompt_includes_type_guidance_for_phase9_tokens() -> None:
    from sidecar.phraseology import _TYPE_GUIDANCE, _build_prompt

    for ctype in ("scenario", "kneeboard", "career"):
        c = Clearance(callsign="N12", clearance_type=ctype)
        prompt = _build_prompt(c)
        assert _TYPE_GUIDANCE[ctype] in prompt
        assert "aircraft type" not in prompt
