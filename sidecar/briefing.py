"""FSS-style pre-flight briefing assembly — pure and deterministic.

``fss_briefing`` assembles a standard Flight Service Station style briefing
string from already-gathered inputs (current weather, NOTAMs, TFRs, route).
It performs no I/O and contains no timestamps, so identical inputs always
produce identical output — safe to snapshot in tests.
"""

from __future__ import annotations

from collections.abc import Iterable

_NONE_WX = "No current weather reported."
_NONE_NOTAMS = "No NOTAMs on file."
_NONE_TFRS = "No TFRs on file."
_NONE_ROUTE = "No route filed."


def fss_briefing(
    origin: str,
    destination: str,
    *,
    metar: str = "",
    notams: Iterable[str] | None = None,
    tfrs: Iterable[str] | None = None,
    route: str = "",
) -> str:
    """Assemble a deterministic FSS-style briefing for *origin* -> *destination*.

    Sections (always present, in this order): header, synopsis, weather,
    NOTAMs, TFRs, route.  Empty/None ``notams`` and ``tfrs`` render an explicit
    "none on file" line rather than being omitted, so the shape is stable.
    """
    notam_list = [str(n) for n in (notams or [])]
    tfr_list = [str(t) for t in (tfrs or [])]
    origin = str(origin)
    destination = str(destination)

    lines: list[str] = []
    lines.append("FLIGHT SERVICE STATION BRIEFING")
    lines.append(f"Route of flight: {origin} to {destination}")

    lines.append("")
    lines.append("SYNOPSIS")
    lines.append(f"Standard briefing for departure {origin}, destination {destination}.")

    lines.append("")
    lines.append("WEATHER")
    lines.append(metar.strip() if metar.strip() else _NONE_WX)

    lines.append("")
    lines.append("NOTAMS")
    if notam_list:
        lines.extend(f"  - {n}" for n in notam_list)
    else:
        lines.append(_NONE_NOTAMS)

    lines.append("")
    lines.append("TFRS")
    if tfr_list:
        lines.extend(f"  - {t}" for t in tfr_list)
    else:
        lines.append(_NONE_TFRS)

    lines.append("")
    lines.append("ROUTE")
    lines.append(route.strip() if route.strip() else _NONE_ROUTE)

    return "\n".join(lines)
