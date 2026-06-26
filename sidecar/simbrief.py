"""SimBrief OFP import — standard-library only, offline-safe.

A SimBrief "OFP" (Operational Flight Plan) is fetched as JSON from the public
fetcher API and reduced to the small :class:`FlightPlan` the ATC sidecar cares
about (origin, destination, route, alternate, cruise altitude, block fuel and
ATC callsign).

``parse_ofp`` is pure and tolerates an arbitrarily sparse/missing OFP dict —
any absent key yields the dataclass default ("").  ``fetch_ofp`` performs the
network GET using stdlib :mod:`urllib`; the opener is injectable (``_opener``)
so tests never hit the network.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass

_log = logging.getLogger(__name__)

# Public SimBrief OFP fetcher.  json=1 asks for a JSON body rather than XML.
_OFP_URL = "https://www.simbrief.com/api/xml.fetcher.php?username={username}&json=1"
_TIMEOUT_SEC = 10.0


@dataclass
class FlightPlan:
    """The slice of a SimBrief OFP the sidecar uses for ATC phraseology."""

    origin: str = ""
    destination: str = ""
    route: str = ""
    alternate: str = ""
    cruise_alt: str = ""
    block_fuel: str = ""
    callsign: str = ""


def parse_ofp(ofp: dict) -> FlightPlan:
    """Reduce a SimBrief OFP JSON dict to a :class:`FlightPlan`.

    Tolerates missing/sparse keys: any absent section or field yields ``""``.
    Maps:
      - origin.icao_code        -> origin
      - destination.icao_code   -> destination
      - general.route           -> route
      - alternate.icao_code     -> alternate
      - general.initial_altitude-> cruise_alt
      - fuel.plan_ramp          -> block_fuel
      - atc.callsign            -> callsign
    """
    data = ofp or {}

    def _get(section: str, key: str) -> str:
        sec = data.get(section)
        if not isinstance(sec, dict):
            return ""
        val = sec.get(key, "")
        return "" if val is None else str(val)

    return FlightPlan(
        origin=_get("origin", "icao_code"),
        destination=_get("destination", "icao_code"),
        route=_get("general", "route"),
        alternate=_get("alternate", "icao_code"),
        cruise_alt=_get("general", "initial_altitude"),
        block_fuel=_get("fuel", "plan_ramp"),
        callsign=_get("atc", "callsign"),
    )


def fetch_ofp(username: str, *, _opener=None) -> dict:
    """Fetch and JSON-decode the latest OFP for *username*.

    Uses stdlib :mod:`urllib`.  ``_opener`` (a callable accepting
    ``(request, timeout=...)`` and returning a context-manager response) is
    injectable so tests can supply fixture bytes; it defaults to
    :func:`urllib.request.urlopen`.  Raises on any network/decode failure —
    callers that want offline tolerance must guard the call themselves.
    """
    opener = _opener if _opener is not None else urllib.request.urlopen
    url = _OFP_URL.format(username=urllib.parse.quote(str(username)))
    req = urllib.request.Request(
        url, headers={"User-Agent": "FlightGear-ATC-Sidecar/1.0"}
    )
    with opener(req, timeout=_TIMEOUT_SEC) as resp:
        raw = resp.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    return json.loads(raw)
