"""
Deterministic groundnet.xml parser — the offline / fallback path.

Parses FlightGear's ``groundnet.xml`` into an :class:`AirportPicture` with
``source="code"`` using only the standard library.  Runway thresholds, ILS,
and (optionally) frequency overrides come from an in-sim ``airportinfo`` dict
supplied by the Nasal layer; when absent those fields are simply left empty so
the fixture-only path still succeeds.

Real-world groundnet quirks handled here (verified against the KSFO fixture):

  * Coordinates are ``"N37 36.386"`` / ``"W122 23.011"`` — hemisphere letter,
    whole degrees, then decimal minutes (occasionally decimal seconds too).
    Plain decimal values are also accepted.
  * Booleans are ``"0"``/``"1"`` (not ``true``/``false``).
  * ``holdPointType`` is ``"none"`` when there is no hold point.
  * Arcs are emitted as directed pairs (both ``a->b`` and ``b->a``); we collapse
    them to a single undirected segment keyed on ``(min, max)``.
  * ``<frequencies>`` stores integers as MHz*100 (``12865`` -> ``"128.65"``).
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from os import PathLike
from xml.etree import ElementTree as ET

from sidecar.airport_picture import (
    AirportPicture,
    Frequencies,
    Node,
    ParkingSpot,
    Runway,
    Segment,
    build_taxi_graph,
)


class ParseError(Exception):
    """Raised when the groundnet source is unreadable or malformed."""


# Hemisphere + degrees + optional minutes + optional seconds.
_COORD_RE = re.compile(
    r"^([NSEW])\s*([0-9]+(?:\.[0-9]+)?)"
    r"(?:\s+([0-9]+(?:\.[0-9]+)?))?"
    r"(?:\s+([0-9]+(?:\.[0-9]+)?))?$",
    re.IGNORECASE,
)


def _parse_coord(raw: str | None, *, what: str) -> float:
    """Parse a groundnet coordinate into signed decimal degrees.

    Accepts decimal (``"-122.38"``) or hemisphere/DMM (``"W122 23.011"``).
    Raises :class:`ParseError` on anything else, per the handoff contract.
    """
    s = (raw or "").strip()
    if not s:
        raise ParseError(f"missing {what}")
    try:
        return float(s)
    except ValueError:
        pass
    m = _COORD_RE.match(s)
    if not m:
        raise ParseError(f"unparseable {what}: {raw!r}")
    hemi = m.group(1).upper()
    degrees = float(m.group(2))
    minutes = float(m.group(3)) if m.group(3) else 0.0
    seconds = float(m.group(4)) if m.group(4) else 0.0
    value = degrees + minutes / 60.0 + seconds / 3600.0
    if hemi in ("S", "W"):
        value = -value
    return value


def _truthy(raw: str | None) -> bool:
    """Interpret a groundnet boolean attribute (``"1"`` / ``"true"`` / ``"yes"``)."""
    return (raw or "").strip().lower() in ("1", "true", "yes")


def _to_float(raw: str | None, *, default: float = 0.0, what: str = "value") -> float:
    """Float with a default for missing values; ParseError when present-but-bad."""
    s = (raw or "").strip()
    if not s:
        return default
    try:
        return float(s)
    except ValueError:
        raise ParseError(f"non-numeric {what}: {raw!r}") from None


def _freq_to_str(raw: str | None) -> str | None:
    """Convert a groundnet frequency to an MHz string, or None when absent.

    FlightGear stores frequencies as integers: 5 digits = MHz*100 (``12865`` ->
    ``128.65``), 6 digits = kHz (``121800`` -> ``121.8``).  Already-decimal
    strings pass through.
    """
    s = (raw or "").strip()
    if not s:
        return None
    try:
        v = int(s)
    except ValueError:
        try:
            float(s)
            return s
        except ValueError:
            return None
    if v <= 0:
        return None
    mhz = v / 1000.0 if v >= 100000 else v / 100.0
    return f"{mhz:.3f}".rstrip("0").rstrip(".")


def _read_bytes(xml_source: str | bytes | PathLike[str]) -> bytes:
    """Return the raw groundnet bytes from a path, raw XML text, or bytes."""
    if isinstance(xml_source, bytes):
        if not xml_source.strip():
            raise ParseError("empty groundnet source")
        return xml_source
    if isinstance(xml_source, str):
        stripped = xml_source.strip()
        if not stripped:
            raise ParseError("empty groundnet source")
        if stripped.startswith("<"):
            return xml_source.encode("utf-8")
    try:
        with open(xml_source, "rb") as fh:  # path-like or filename string
            return fh.read()
    except OSError as exc:
        raise ParseError(f"cannot read groundnet source: {exc}") from exc


def _parse_parking(root: ET.Element) -> list[ParkingSpot]:
    spots: list[ParkingSpot] = []
    for el in root.findall("./parkingList/Parking"):
        idx_raw = el.get("index")
        if idx_raw is None:
            raise ParseError("Parking element missing 'index'")
        try:
            pid = int(idx_raw)
        except ValueError:
            raise ParseError(f"Parking index not an int: {idx_raw!r}") from None
        name = (el.get("name") or "").strip()
        number = (el.get("number") or "").strip()
        full_name = (name + number).strip() or f"parking-{pid}"
        spots.append(
            ParkingSpot(
                id=pid,
                name=full_name,
                type=(el.get("type") or "").strip(),
                lat=_parse_coord(el.get("lat"), what="Parking lat"),
                lon=_parse_coord(el.get("lon"), what="Parking lon"),
                heading=_to_float(el.get("heading"), what="Parking heading"),
            )
        )
    return spots


def _parse_nodes(root: ET.Element) -> list[Node]:
    nodes: list[Node] = []
    for el in root.findall("./TaxiNodes/node"):
        idx_raw = el.get("index")
        if idx_raw is None:
            raise ParseError("node element missing 'index'")
        try:
            nidx = int(idx_raw)
        except ValueError:
            raise ParseError(f"node index not an int: {idx_raw!r}") from None
        hold_type = (el.get("holdPointType") or "").strip().lower()
        nodes.append(
            Node(
                index=nidx,
                lat=_parse_coord(el.get("lat"), what="node lat"),
                lon=_parse_coord(el.get("lon"), what="node lon"),
                on_runway=_truthy(el.get("isOnRunway")),
                hold_point=hold_type not in ("", "none"),
            )
        )
    return nodes


def _parse_segments(root: ET.Element) -> list[Segment]:
    """Parse arcs, collapsing directed pairs into undirected segments."""
    seen: set[tuple[int, int]] = set()
    segments: list[Segment] = []
    for el in root.findall("./TaxiWaySegments/arc"):
        b_raw, e_raw = el.get("begin"), el.get("end")
        if b_raw is None or e_raw is None:
            raise ParseError("arc element missing 'begin'/'end'")
        try:
            begin, end = int(b_raw), int(e_raw)
        except ValueError:
            raise ParseError(
                f"arc begin/end not an int: {b_raw!r}/{e_raw!r}"
            ) from None
        key = (min(begin, end), max(begin, end))
        if key in seen:
            continue
        seen.add(key)
        segments.append(
            Segment(
                begin=begin,
                end=end,
                name=(el.get("name") or "").strip(),
                pushback=_truthy(el.get("isPushBackRoute")),
            )
        )
    return segments


def _parse_frequencies(root: ET.Element) -> Frequencies:
    el = root.find("./frequencies")
    if el is None:
        return Frequencies()
    return Frequencies(
        ground=_freq_to_str(el.findtext("GROUND")),
        tower=_freq_to_str(el.findtext("TOWER")),
        atis=_freq_to_str(el.findtext("ATIS") or el.findtext("AWOS")),
        approach=_freq_to_str(el.findtext("APPROACH")),
        departure=_freq_to_str(el.findtext("DEPARTURE")),
    )


def _runways_from_airportinfo(airportinfo: dict) -> list[Runway]:
    runways: list[Runway] = []
    for rw in airportinfo.get("runways") or []:
        ils = rw.get("ils_freq")
        runways.append(
            Runway(
                id=str(rw.get("id", "")),
                thr_lat=_to_float(str(rw.get("thr_lat", "")), what="runway thr_lat"),
                thr_lon=_to_float(str(rw.get("thr_lon", "")), what="runway thr_lon"),
                heading=_to_float(str(rw.get("heading", "")), what="runway heading"),
                length=_to_float(str(rw.get("length", "")), what="runway length"),
                ils_freq=str(ils) if ils is not None else None,
                entry_nodes=[int(n) for n in (rw.get("entry_nodes") or [])],
            )
        )
    return runways


def _merge_freq_overrides(base: Frequencies, overrides: dict | None) -> Frequencies:
    if not overrides:
        return base
    merged = base.model_dump()
    for key in ("ground", "tower", "atis", "approach", "departure"):
        if overrides.get(key):
            merged[key] = str(overrides[key])
    return Frequencies(**merged)


def parse_groundnet(
    xml_source: str | bytes | PathLike[str],
    icao: str,
    *,
    airportinfo: dict | None = None,
) -> AirportPicture:
    """Parse a groundnet source into an :class:`AirportPicture` (source="code").

    Args:
        xml_source: A filesystem path, raw XML text, or raw bytes.
        icao: The ICAO identifier to stamp on the result.
        airportinfo: Optional in-sim data — ``{"runways": [...],
            "frequencies": {...}}``.  Runways/ILS/thresholds and frequency
            overrides come from here; left empty when ``None``.

    Returns:
        A fully populated :class:`AirportPicture` with a computed
        ``taxi_graph`` and a ``groundnet_hash`` of the raw bytes.

    Raises:
        ParseError: The source is unreadable, not ``<groundnet>``, or contains
            malformed numeric/coordinate data.
    """
    raw_bytes = _read_bytes(xml_source)
    if not raw_bytes.strip():
        raise ParseError(f"empty groundnet XML for {icao}")
    try:
        root = ET.fromstring(raw_bytes)
    except ET.ParseError as exc:
        raise ParseError(
            f"malformed (not well-formed) groundnet XML for {icao}: {exc}"
        ) from exc
    if root.tag != "groundnet":
        raise ParseError(f"expected <groundnet> root, got <{root.tag}>")

    parking = _parse_parking(root)
    nodes = _parse_nodes(root)
    segments = _parse_segments(root)
    frequencies = _parse_frequencies(root)

    runways: list[Runway] = []
    if airportinfo:
        runways = _runways_from_airportinfo(airportinfo)
        frequencies = _merge_freq_overrides(
            frequencies, airportinfo.get("frequencies")
        )

    return AirportPicture(
        icao=icao,
        source="code",
        generated_at=datetime.now(timezone.utc).isoformat(),
        groundnet_hash=hashlib.sha256(raw_bytes).hexdigest(),
        parking=parking,
        nodes=nodes,
        segments=segments,
        runways=runways,
        frequencies=frequencies,
        taxi_graph=build_taxi_graph(nodes, segments),
    )
