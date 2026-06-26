"""Deterministic kneeboard card assembly for the FlightGear AI ATC sidecar.

``build_kneeboard`` renders a compact, multi-line "kneeboard" reference card
from an already-gathered airport picture (ICAO, name, wind, active runways,
frequencies, ATIS).  It performs no I/O and contains no timestamps, so
identical inputs always produce identical output — safe to snapshot in tests.

The shape is stable: every section header (Airport, Wind, Active runways,
Frequencies, ATIS) is always emitted.  Missing values render an explicit
``n/a`` rather than being omitted, so callers (and the in-sim mailbox at
``/ai-atc/kneeboard``) can rely on a fixed line layout.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Optional

_NONE = "n/a"


def _airport_line(icao: str, airport_name: str) -> str:
    icao = (icao or "").strip()
    airport_name = (airport_name or "").strip()
    if icao and airport_name:
        return f"{icao} {airport_name}"
    if icao:
        return icao
    if airport_name:
        return airport_name
    return _NONE


def _wind_line(wind_dir: Optional[int], wind_kt: Optional[int]) -> str:
    if wind_dir is None and wind_kt is None:
        return _NONE
    direction = f"{int(wind_dir):03d}" if wind_dir is not None else _NONE
    speed = f"{int(wind_kt)} kt" if wind_kt is not None else _NONE
    return f"{direction} at {speed}"


def build_kneeboard(
    *,
    icao: str = "",
    airport_name: str = "",
    wind_dir: Optional[int] = None,
    wind_kt: Optional[int] = None,
    runways: Optional[Sequence[str]] = None,
    atis: str = "",
    freqs: Optional[Mapping[str, str]] = None,
) -> str:
    """Build a deterministic multi-line kneeboard card.

    Args:
        icao: Airport ICAO identifier (e.g. ``"KJFK"``).
        airport_name: Human-readable airport name.
        wind_dir: Wind direction in degrees, or ``None`` if unknown.
        wind_kt: Wind speed in knots, or ``None`` if unknown.
        runways: Active runway identifiers, e.g. ``["28R", "28L"]``.
        atis: ATIS letter/text, e.g. ``"information alpha"``.
        freqs: Frequency mapping, e.g. ``{"Ground": "121.80"}``.  Rendered in
            sorted-key order for determinism.

    Returns:
        A newline-joined card with a fixed section order.  All inputs are
        optional; absent values render ``n/a`` so the shape never changes.
    """
    lines: list[str] = ["KNEEBOARD"]

    lines.append(f"Airport: {_airport_line(icao, airport_name)}")
    lines.append(f"Wind: {_wind_line(wind_dir, wind_kt)}")

    runway_list = [str(r).strip() for r in (runways or []) if str(r).strip()]
    if runway_list:
        lines.append(f"Active runways: {', '.join(runway_list)}")
    else:
        lines.append(f"Active runways: {_NONE}")

    lines.append("Frequencies:")
    freq_items = [
        (str(name).strip(), str(value).strip())
        for name, value in (freqs or {}).items()
        if str(value).strip()
    ]
    if freq_items:
        for name, value in sorted(freq_items):
            lines.append(f"  {name} {value}")
    else:
        lines.append(f"  {_NONE}")

    atis_text = (atis or "").strip()
    lines.append(f"ATIS: {atis_text if atis_text else _NONE}")

    return "\n".join(lines)
