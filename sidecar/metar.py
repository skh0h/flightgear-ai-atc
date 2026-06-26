"""
METAR wind fetcher — standard-library only, offline-safe.

``get_wind(icao)`` fetches the current METAR from aviationweather.gov and
returns ``(wind_dir_deg, wind_kt)`` or ``None`` on any failure (network,
parse, timeout).  The caller treats ``None`` as calm and uses the deterministic
runway fallback — mirroring the sidecar offline contract.

Wind-group parsing decisions:
  - ``dddssKT``     → (ddd, ss)
  - ``dddssGppKT``  → (ddd, ss)  — steady speed only, gust ignored
  - ``dddssMPS``    → (ddd, ss*1.94384 rounded)  — metres/second (Russia/China)
  - ``dddssGppMPS`` → (ddd, ss*1.94384 rounded)  — steady speed only, gust ignored
  - ``VRBssKT``     → None        — variable direction: caller uses calm fallback
  - ``00000KT``     → (0.0, 0.0) — calm
  - ``00000MPS``    → (0.0, 0.0) — calm
  - Any parse error → None
"""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request

_log = logging.getLogger(__name__)

_METAR_URL = (
    "https://aviationweather.gov/api/data/metar?ids={icao}&format=raw"
)
_TIMEOUT_SEC = 5.0

# Conversion factor: 1 metre/second = 1.94384 knots
_MPS_TO_KT = 1.94384

# Matches: dddssKT, dddssGppKT, dddssMPS, dddssGppMPS (steady + optional gust)
_WIND_RE = re.compile(
    r"\b"
    r"(?P<dir>\d{3}|VRB)"           # 3-digit direction or VRB
    r"(?P<speed>\d{2,3})"           # speed (2–3 digits)
    r"(?:G\d{2,3})?"                # optional gust (ignored)
    r"(?P<unit>KT|MPS)"            # unit: knots or metres/second
    r"\b"
)


def get_wind(icao: str) -> tuple[float, float] | None:
    """Return ``(wind_dir_deg, wind_kt)`` for *icao*, or ``None`` on any failure.

    Direction is degrees magnetic that the wind blows *from* (METAR convention).
    Calm (00000KT) returns ``(0.0, 0.0)``.
    Variable direction (VRBxxKT) returns ``None`` so the caller falls back to
    the deterministic calm runway selection.

    Never raises — all exceptions are caught and logged.
    """
    try:
        return _fetch_and_parse(icao)
    except Exception:
        _log.debug("METAR fetch/parse failed for %s", icao, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_raw(icao: str) -> str:
    """Fetch the raw METAR text for *icao*.  Raises on any network error."""
    url = _METAR_URL.format(icao=icao.upper())
    req = urllib.request.Request(url, headers={"User-Agent": "FlightGear-ATC-Sidecar/1.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse_wind(raw_metar: str) -> tuple[float, float] | None:
    """Extract the first wind group from *raw_metar*.

    Returns ``(dir_deg, speed_kt)``, or ``None`` for variable wind or parse failure.
    """
    m = _WIND_RE.search(raw_metar)
    if m is None:
        return None
    if m.group("dir") == "VRB":
        # Variable direction — caller should treat as calm/unknown
        return None
    wind_dir = float(m.group("dir"))
    speed = float(m.group("speed"))
    if m.group("unit") == "MPS":
        # Metres/second (Russia/China): convert to knots, round to whole knots
        # to match the whole-knot resolution of the KT form.
        wind_kt = float(round(speed * _MPS_TO_KT))
    else:
        wind_kt = speed
    return (wind_dir, wind_kt)


def _fetch_and_parse(icao: str) -> tuple[float, float] | None:
    raw = _fetch_raw(icao)
    return _parse_wind(raw)
