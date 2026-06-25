"""
Active departure runway selection.

``select_departure_runway`` picks the runway whose heading best aligns into the
wind (minimises the headwind-to-crosswind ratio, i.e. maximises the headwind
component).  Wind is an explicit input so the function is pure/testable; the
caller is responsible for fetching METAR/sim wind data.

When no wind is available, or the picture has no runway objects, the function
falls back deterministically:

  1. Use the runway with the largest heading into a default calm wind (360°/0
     kt — just picks the lowest numeric runway id, stable across calls).
  2. If the picture has no ``Runway`` objects at all, fall back to the nearest
     on-runway node to the given start position (or the first on-runway node).

``runway_entry_node`` finds the graph node to route *to* for a departure:
  - Prefers ``runway.entry_nodes[0]`` when populated (set by in-sim airportinfo).
  - Otherwise finds the on-runway node nearest to the runway threshold.
  - Last resort: the on-runway node nearest to any provided position hint.

``taxi_to_runway`` is the end-to-end glue: resolve start node → select runway
→ resolve entry node → A* → clearance text.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from sidecar.airport_picture import AirportPicture, Runway
from sidecar.phraseology import Clearance, phrase_offline
from sidecar import routing
from sidecar.routing import taxiways_for_clearance


# ---------------------------------------------------------------------------
# Wind helpers
# ---------------------------------------------------------------------------

def headwind_component(runway_heading: float, wind_dir: float, wind_kt: float) -> float:
    """Headwind component in knots for a runway heading given wind.

    Positive = headwind (desired), negative = tailwind.

    Args:
        runway_heading: Magnetic heading of the runway *in use* (degrees 0-360).
        wind_dir: Wind direction the wind is blowing *from* (degrees 0-360).
        wind_kt: Wind speed in knots (non-negative).
    """
    angle_rad = math.radians(wind_dir - runway_heading)
    return wind_kt * math.cos(angle_rad)


# ---------------------------------------------------------------------------
# Runway selection
# ---------------------------------------------------------------------------

def select_departure_runway(
    picture: AirportPicture,
    *,
    wind_dir: float | None = None,
    wind_kt: float | None = None,
) -> Runway | None:
    """Choose the best departure runway from ``picture.runways``.

    Strategy: pick the runway end whose heading maximises the headwind component
    (i.e. land into the wind).  Both ends of a physical runway are separate
    ``Runway`` objects in the model so we simply pick the best-scoring one.

    Falls back to the runway with id that sorts first when wind is calm/absent
    (stable, deterministic ordering).

    Returns ``None`` when ``picture.runways`` is empty (caller must use the
    on-runway-node fallback via :func:`on_runway_node_for_position`).
    """
    if not picture.runways:
        return None

    use_wind = (
        wind_dir is not None
        and wind_kt is not None
        and wind_kt > 0.0
    )

    def score(rwy: Runway) -> float:
        if use_wind:
            return headwind_component(rwy.heading, wind_dir, wind_kt)  # type: ignore[arg-type]
        # Calm/no-wind: prefer lower runway number (stable tie-break)
        try:
            num = int("".join(c for c in rwy.id if c.isdigit()) or "999")
        except ValueError:
            num = 999
        return -float(num)  # lower number → higher score → selected first

    return max(picture.runways, key=score)


# ---------------------------------------------------------------------------
# Entry-node resolution
# ---------------------------------------------------------------------------

def runway_entry_node(
    picture: AirportPicture,
    runway: Runway,
) -> int | None:
    """Graph node to route *to* when departing on ``runway``.

    Priority:
      1. ``runway.entry_nodes[0]`` (set by in-sim airportinfo).
      2. On-runway node nearest to the runway threshold (thr_lat/thr_lon).
      3. Any on-runway node (last resort when threshold coords are zero).
    """
    if runway.entry_nodes:
        return runway.entry_nodes[0]

    if runway.thr_lat or runway.thr_lon:
        node = routing.nearest_node(
            picture, runway.thr_lat, runway.thr_lon, require_on_runway=True
        )
        if node is not None:
            return node

    # Last resort: first on-runway node
    on_rwy = [n for n in picture.nodes if n.on_runway]
    return on_rwy[0].index if on_rwy else None


def on_runway_node_for_position(
    picture: AirportPicture,
    lat: float,
    lon: float,
) -> int | None:
    """Nearest on-runway node to ``(lat, lon)`` — used when no Runway objects
    exist (e.g. fixture-only parse without in-sim airportinfo).
    """
    return routing.nearest_node(picture, lat, lon, require_on_runway=True)


# ---------------------------------------------------------------------------
# Start-node resolution
# ---------------------------------------------------------------------------

def start_node_for_position(
    picture: AirportPicture,
    lat: float,
    lon: float,
    *,
    parking_id: int | None = None,
) -> int | None:
    """Resolve the A* start node for an aircraft at ``(lat, lon)``.

    If ``parking_id`` is supplied and the spot is in the graph, returns it
    directly (gates are graph nodes via their pushback arc).  Otherwise finds
    the nearest non-runway taxi node (off-runway taxiway), falling back to any
    nearest node.

    Args:
        picture: The airport picture.
        lat: Aircraft latitude in decimal degrees.
        lon: Aircraft longitude in decimal degrees.
        parking_id: Optional gate/parking index if known.

    Returns:
        A node index present in ``picture.taxi_graph``, or ``None``.
    """
    if parking_id is not None and parking_id in picture.taxi_graph:
        return parking_id

    # Prefer non-runway nodes as start (aircraft is at a gate/taxiway)
    node = routing.nearest_node(picture, lat, lon, require_on_runway=False)
    if node is not None and node in picture.taxi_graph:
        return node

    # Fallback: any node
    return routing.nearest_node(picture, lat, lon)


# ---------------------------------------------------------------------------
# End-to-end glue
# ---------------------------------------------------------------------------

@dataclass
class TaxiResult:
    """Outcome of a gate-to-runway taxi path computation."""

    clearance_text: str
    runway_id: str
    taxiways: list[str]
    route: list[int]


def _resolve_taxi(
    picture: AirportPicture,
    lat: float,
    lon: float,
    *,
    wind_dir: float | None = None,
    wind_kt: float | None = None,
    parking_id: int | None = None,
) -> tuple[str, list[str], list[int]]:
    """Core resolution: runway_id, taxiways (coverage-gated), route.

    Shared by :func:`build_taxi_clearance` and :func:`taxi_to_runway` so that
    A* runs exactly once per call.
    """
    # 1. Select departure runway
    runway = select_departure_runway(picture, wind_dir=wind_dir, wind_kt=wind_kt)
    runway_id = runway.id if runway else ""

    # 2. Resolve start node
    start = start_node_for_position(picture, lat, lon, parking_id=parking_id)

    # 3. Resolve goal node
    if runway is not None:
        goal = runway_entry_node(picture, runway)
    else:
        goal = on_runway_node_for_position(picture, lat, lon)

    # 4. A* route + coverage gate
    route: list[int] = []
    taxiways: list[str] = []
    if start is not None and goal is not None and start != goal:
        route = routing.find_route(picture, start, goal)
        taxiways = taxiways_for_clearance(route, picture)

    return runway_id, taxiways, route


def build_taxi_clearance(
    picture: AirportPicture,
    callsign: str,
    lat: float,
    lon: float,
    *,
    wind_dir: float | None = None,
    wind_kt: float | None = None,
    parking_id: int | None = None,
) -> Clearance:
    """Shared helper: select runway → resolve nodes → A* → coverage gate → Clearance.

    Returns a :class:`~sidecar.phraseology.Clearance` ready for the caller to
    render (offline or online).  Degrades gracefully at every step — routing
    failure yields an empty ``taxi_route`` so the template still produces a
    sensible "taxi to runway XX" clearance.

    The ``via`` clause is suppressed via :func:`~sidecar.routing.taxiways_for_clearance`
    when the routed path is only sparsely named (Item-1 coverage gate).

    Args:
        picture: Parsed airport picture.
        callsign: Pilot callsign.
        lat: Aircraft latitude in decimal degrees.
        lon: Aircraft longitude in decimal degrees.
        wind_dir: Wind direction (degrees from), or None for calm.
        wind_kt: Wind speed in knots, or None for calm.
        parking_id: Gate/parking index if known (speeds up start resolution).

    Returns:
        :class:`~sidecar.phraseology.Clearance` (unrendered).
    """
    runway_id, taxiways, _ = _resolve_taxi(
        picture, lat, lon,
        wind_dir=wind_dir, wind_kt=wind_kt, parking_id=parking_id,
    )
    return Clearance(
        callsign=callsign,
        clearance_type="taxi",
        taxi_route=taxiways,
        active_runway=runway_id,
        hold_short=runway_id,
    )


def taxi_to_runway(
    picture: AirportPicture,
    callsign: str,
    lat: float,
    lon: float,
    *,
    wind_dir: float | None = None,
    wind_kt: float | None = None,
    parking_id: int | None = None,
) -> TaxiResult:
    """Full pipeline: select runway → resolve nodes → A* → clearance.

    Degrades gracefully at every step:
    - No runway objects → uses nearest on-runway node as goal, runway_id="".
    - No A* path → clearance with empty taxiway list ("taxi to runway XX").
    - No named segments → same (no ``via`` clause).

    Args:
        picture: Parsed airport picture.
        callsign: Pilot callsign for the clearance.
        lat: Aircraft latitude.
        lon: Aircraft longitude.
        wind_dir: Wind direction from (degrees), or None for calm.
        wind_kt: Wind speed in knots, or None for calm.
        parking_id: Gate/parking index if known (speeds up start resolution).

    Returns:
        :class:`TaxiResult` with clearance text, runway id, taxiway list, route.
    """
    runway_id, taxiways, route = _resolve_taxi(
        picture, lat, lon,
        wind_dir=wind_dir, wind_kt=wind_kt, parking_id=parking_id,
    )
    clearance = Clearance(
        callsign=callsign,
        clearance_type="taxi",
        taxi_route=taxiways,
        active_runway=runway_id,
        hold_short=runway_id,
    )
    text = phrase_offline(clearance)
    return TaxiResult(
        clearance_text=text,
        runway_id=runway_id,
        taxiways=taxiways,
        route=route,
    )
