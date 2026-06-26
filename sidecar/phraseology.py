"""
ATC phraseology generation — online (Gemini) with a deterministic offline fallback.

``phrase_offline`` builds clearances from fixed templates, so the add-on always
has something sensible to say.  ``phrase_online`` asks Gemini for more natural,
ICAO-flavoured wording and falls back to the offline template on any
``OfflineError`` — the same offline contract used throughout the sidecar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from sidecar.gemini_client import GeminiClient, OfflineError


@dataclass
class Clearance:
    """A ground clearance to be voiced to the pilot.

    ``taxi_route`` is the ordered list of taxiway names (e.g. ``["A", "B"]``).
    ``aircraft_type`` is the sim aircraft ID (e.g. "c172p"); used to tailor the
    online Gemini prompt when present; ignored by the offline template.
    """

    callsign: str
    clearance_type: str = "taxi"  # "taxi" | "pushback" | "takeoff"
    taxi_route: list[str] = field(default_factory=list)
    active_runway: str = ""
    hold_short: str = ""
    frequency: str = ""
    remarks: str = ""
    aircraft_type: str = ""  # optional; empty string = not available
    divert_target: str = ""  # optional; "ICAO Name" for a diversion clearance


class PhraseResult(BaseModel):
    """Structured-output schema for the online phraseology call."""

    text: str


def _safe_rwy(s: str) -> str:
    """Return s if it is a real runway id; empty string if it is a FG bool token.

    FG telnet can serialize a bool-false property as the literal token 'false'.
    This backstop ensures that artifact never appears as a spoken runway id or
    hold-short point.
    """
    return s if s and s.lower() not in ("false", "true") else ""


def phrase_offline(clearance: Clearance) -> str:
    """Render a clearance using deterministic templates."""
    callsign = clearance.callsign or "Aircraft"
    ctype = (clearance.clearance_type or "taxi").lower()

    if ctype == "pushback":
        sentence = f"{callsign}, pushback approved"
        if _safe_rwy(clearance.active_runway):
            sentence += f", expect runway {clearance.active_runway}"
        sentence += "."
    elif ctype == "takeoff":
        runway = _safe_rwy(clearance.active_runway) or "the active runway"
        sentence = f"{callsign}, runway {runway}, cleared for takeoff."
    elif ctype == "approach":
        runway = _safe_rwy(clearance.active_runway) or "active runway"
        sentence = f"{callsign}, expect approach runway {runway}."
    elif ctype == "ils":
        runway = _safe_rwy(clearance.active_runway) or "active runway"
        sentence = f"{callsign}, cleared ILS runway {runway} approach."
    elif ctype == "airfield_in_sight":
        runway = _safe_rwy(clearance.active_runway) or "active runway"
        sentence = f"{callsign}, cleared visual approach runway {runway}."
    elif ctype == "radio_check":
        sentence = f"{callsign}, reading you five by five."
    elif ctype == "mayday":
        sentence = (
            f"{callsign}, roger mayday. State souls on board, fuel remaining, "
            f"and intentions."
        )
    elif ctype == "pan_pan":
        sentence = f"{callsign}, roger pan-pan, say intentions."
    elif ctype == "gear_emergency":
        runway = _safe_rwy(clearance.active_runway) or "the active runway"
        sentence = (
            f"{callsign}, roger. Emergency services are standing by, "
            f"cleared to land runway {runway}."
        )
    elif ctype == "min_fuel":
        sentence = (
            f"{callsign}, roger minimum fuel, you are number one for the approach."
        )
    elif ctype == "diversion":
        target = clearance.divert_target or "the nearest suitable airport"
        sentence = (
            f"{callsign}, roger, cleared to divert to {target}, "
            f"descend at pilot's discretion."
        )
    elif ctype == "go_around":
        sentence = (
            f"{callsign}, roger, going around, fly runway heading, "
            f"climb to pattern altitude."
        )
    elif ctype == "squawk_7500":
        sentence = (
            f"{callsign}, roger, squawk seven five zero zero acknowledged, "
            f"say intentions when able."
        )
    elif ctype == "squawk_7600":
        sentence = (
            f"{callsign}, radio failure acknowledged, squawk seven six zero zero, "
            f"continue and look for light-gun signals."
        )
    elif ctype == "squawk_7700":
        sentence = (
            f"{callsign}, roger emergency, squawk seven seven zero zero, "
            f"state nature of emergency and intentions."
        )
    else:  # taxi (default)
        parts = [f"{callsign}, taxi"]
        if _safe_rwy(clearance.active_runway):
            parts.append(f"to runway {clearance.active_runway}")
        if clearance.taxi_route:
            parts.append("via " + ", ".join(clearance.taxi_route))
        sentence = " ".join(parts)
        if _safe_rwy(clearance.hold_short):
            sentence += f", hold short of {clearance.hold_short}"
        sentence += "."

    if clearance.frequency:
        sentence += f" Contact {clearance.frequency}."
    if clearance.remarks:
        sentence += f" {clearance.remarks}"
    return sentence


# Per-type ICAO-style guidance appended to the online prompt to steer phrasing.
# Keep each value a single sentence and free of the literal phrase "aircraft
# type" (the prompt's aircraft line is gated separately and unit-tested).
_TYPE_GUIDANCE = {
    "pushback": "For pushback, approve pushback and state the expected departure runway if known.",
    "taxi": "For taxi, give the runway and the taxi route, and include any hold-short instruction.",
    "takeoff": "For takeoff, state the departure runway and issue the takeoff clearance.",
    "approach": "For approach, tell the pilot which runway to expect for the approach.",
    "ils": "For an ILS approach, clear the aircraft for the ILS approach to the specified runway.",
    "airfield_in_sight": "When the airfield is in sight, clear the aircraft for a visual approach to the runway.",
    "radio_check": "For a radio check, reply with a readability report such as 'reading you five by five'.",
    "mayday": "For a mayday distress call, acknowledge the emergency and ask the pilot to state souls on board, fuel remaining, and intentions.",
    "pan_pan": "For a pan-pan urgency call, acknowledge the urgency and ask the pilot to say their intentions.",
    "gear_emergency": "For a landing-gear emergency, advise that emergency services are standing by and clear the flight to land on the active runway.",
    "min_fuel": "For a minimum-fuel advisory, acknowledge it and give the flight priority sequencing as number one for the approach.",
    "diversion": "For a diversion, clear the flight to divert to the named alternate field or the nearest suitable airport and allow descent at the pilot's discretion.",
    "go_around": "For a go-around, acknowledge it and instruct the pilot to fly runway heading and climb to the pattern altitude.",
    "squawk_7500": "For a 7500 unlawful-interference squawk, keep the reply restrained, acknowledge the code, and ask for intentions when able.",
    "squawk_7600": "For a 7600 radio-failure squawk, acknowledge lost communications, confirm the code, and tell the pilot to continue and watch for light-gun signals.",
    "squawk_7700": "For a 7700 general-emergency squawk, acknowledge the emergency and ask the pilot to state the nature of the emergency and intentions.",
}


def _build_prompt(clearance: Clearance) -> str:
    route = ", ".join(clearance.taxi_route) if clearance.taxi_route else "(none)"
    aircraft_line = (
        f"- aircraft type: {clearance.aircraft_type}\n"
        if clearance.aircraft_type
        else ""
    )
    guidance = _TYPE_GUIDANCE.get((clearance.clearance_type or "").lower(), "")
    guidance_line = f"Guidance: {guidance}\n" if guidance else ""
    return (
        "Render the following ground clearance as a single, natural, "
        "ICAO-standard ATC transmission. Return only the spoken text.\n"
        f"- callsign: {clearance.callsign}\n"
        f"- type: {clearance.clearance_type}\n"
        f"{aircraft_line}"
        f"- taxiways: {route}\n"
        f"- active runway: {clearance.active_runway or '(none)'}\n"
        f"- hold short of: {clearance.hold_short or '(none)'}\n"
        f"- frequency: {clearance.frequency or '(none)'}\n"
        f"- remarks: {clearance.remarks or '(none)'}\n"
        f"{guidance_line}"
    )


def phrase_online(
    clearance: Clearance,
    gemini_client: GeminiClient,
    *,
    model: str | None = None,
) -> str:
    """Voice a clearance via Gemini, falling back to the offline template.

    Returns the model's text on success; on any ``OfflineError`` (missing key,
    network/auth/quota failure, retries exhausted) returns
    :func:`phrase_offline` instead.
    """
    try:
        result = gemini_client.generate(
            _build_prompt(clearance), PhraseResult, model=model
        )
    except OfflineError:
        return phrase_offline(clearance)
    text = (result.text or "").strip()
    return text or phrase_offline(clearance)
