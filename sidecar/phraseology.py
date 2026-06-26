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


class PhraseResult(BaseModel):
    """Structured-output schema for the online phraseology call."""

    text: str


def phrase_offline(clearance: Clearance) -> str:
    """Render a clearance using deterministic templates."""
    callsign = clearance.callsign or "Aircraft"
    ctype = (clearance.clearance_type or "taxi").lower()

    if ctype == "pushback":
        sentence = f"{callsign}, pushback approved"
        if clearance.active_runway:
            sentence += f", expect runway {clearance.active_runway}"
        sentence += "."
    elif ctype == "takeoff":
        runway = clearance.active_runway or "the active runway"
        sentence = f"{callsign}, runway {runway}, cleared for takeoff."
    elif ctype == "approach":
        runway = clearance.active_runway or "active runway"
        sentence = f"{callsign}, expect approach runway {runway}."
    elif ctype == "ils":
        runway = clearance.active_runway or "active runway"
        sentence = f"{callsign}, cleared ILS runway {runway} approach."
    elif ctype == "airfield_in_sight":
        runway = clearance.active_runway or "active runway"
        sentence = f"{callsign}, cleared visual approach runway {runway}."
    elif ctype == "radio_check":
        sentence = f"{callsign}, reading you five by five."
    else:  # taxi (default)
        parts = [f"{callsign}, taxi"]
        if clearance.active_runway:
            parts.append(f"to runway {clearance.active_runway}")
        if clearance.taxi_route:
            parts.append("via " + ", ".join(clearance.taxi_route))
        sentence = " ".join(parts)
        if clearance.hold_short:
            sentence += f", hold short of {clearance.hold_short}"
        sentence += "."

    if clearance.frequency:
        sentence += f" Contact {clearance.frequency}."
    if clearance.remarks:
        sentence += f" {clearance.remarks}"
    return sentence


def _build_prompt(clearance: Clearance) -> str:
    route = ", ".join(clearance.taxi_route) if clearance.taxi_route else "(none)"
    aircraft_line = (
        f"- aircraft type: {clearance.aircraft_type}\n"
        if clearance.aircraft_type
        else ""
    )
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
