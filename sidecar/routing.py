"""
Taxi routing over an :class:`AirportPicture`.

``find_route`` runs A* across the undirected ``taxi_graph`` adjacency, using a
great-circle (haversine) heuristic and edge costs computed from node/parking
coordinates.  Helpers locate the nearest taxi node to a gate (the route start)
and a runway entry/hold node (the route goal).  ``route_to_instructions`` turns
a node path into a human-readable ordered taxiway list, collapsing consecutive
arcs that share a name.

Everything degrades gracefully: unknown endpoints or a disconnected graph yield
an empty route rather than raising.
"""

from __future__ import annotations

import heapq
import math

from sidecar.airport_picture import AirportPicture

_EARTH_RADIUS_M = 6371000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    return 2.0 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _coord_map(picture: AirportPicture) -> dict[int, tuple[float, float]]:
    """Index -> (lat, lon) for every node and parking spot (shared namespace)."""
    coords: dict[int, tuple[float, float]] = {}
    for node in picture.nodes:
        coords[node.index] = (node.lat, node.lon)
    for spot in picture.parking:
        coords.setdefault(spot.id, (spot.lat, spot.lon))
    return coords


def nearest_node(
    picture: AirportPicture,
    lat: float,
    lon: float,
    *,
    require_on_runway: bool | None = None,
) -> int | None:
    """Return the index of the taxi node closest to ``(lat, lon)``.

    ``require_on_runway`` filters candidates: ``True`` for runway nodes only,
    ``False`` for non-runway nodes only, ``None`` (default) for any node.
    Returns ``None`` if no candidate qualifies.
    """
    best_index: int | None = None
    best_dist = math.inf
    for node in picture.nodes:
        if require_on_runway is not None and node.on_runway != require_on_runway:
            continue
        dist = haversine_m(lat, lon, node.lat, node.lon)
        if dist < best_dist:
            best_dist = dist
            best_index = node.index
    return best_index


def nearest_node_to_parking(picture: AirportPicture, parking_id: int) -> int | None:
    """Nearest taxi node to a given gate/parking id (the usual route start)."""
    for spot in picture.parking:
        if spot.id == parking_id:
            return nearest_node(picture, spot.lat, spot.lon)
    return None


def runway_goal_node(picture: AirportPicture, runway_id: str) -> int | None:
    """Pick a goal node for a runway: its first entry node, else nearest hold/
    on-runway node to the threshold.  Returns ``None`` when unknown."""
    for runway in picture.runways:
        if runway.id != runway_id:
            continue
        if runway.entry_nodes:
            return runway.entry_nodes[0]
        if runway.thr_lat or runway.thr_lon:
            goal = nearest_node(
                picture, runway.thr_lat, runway.thr_lon, require_on_runway=True
            )
            if goal is not None:
                return goal
        break
    return None


def _reconstruct(came_from: dict[int, int], current: int) -> list[int]:
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def find_route(
    picture: AirportPicture, start_node: int, goal_node: int
) -> list[int]:
    """A* shortest taxi path from ``start_node`` to ``goal_node``.

    Edge weights are the haversine distance between adjacent indices (falling
    back to a unit cost when a coordinate is unknown); the heuristic is the
    straight-line distance to the goal, which is admissible.

    Returns the ordered list of node indices (inclusive of both ends), or an
    empty list if either endpoint is absent from the graph or no path exists.
    """
    graph = picture.taxi_graph
    if start_node not in graph or goal_node not in graph:
        return []
    if start_node == goal_node:
        return [start_node]

    coords = _coord_map(picture)

    def heuristic(index: int) -> float:
        if index in coords and goal_node in coords:
            return haversine_m(*coords[index], *coords[goal_node])
        return 0.0

    def edge_cost(a: int, b: int) -> float:
        if a in coords and b in coords:
            return haversine_m(*coords[a], *coords[b])
        return 1.0

    open_heap: list[tuple[float, float, int]] = [(heuristic(start_node), 0.0, start_node)]
    came_from: dict[int, int] = {}
    g_score: dict[int, float] = {start_node: 0.0}
    closed: set[int] = set()

    while open_heap:
        _, g_current, current = heapq.heappop(open_heap)
        if current == goal_node:
            return _reconstruct(came_from, current)
        if current in closed:
            continue
        closed.add(current)
        for neighbour in graph.get(current, []):
            if neighbour in closed:
                continue
            tentative = g_current + edge_cost(current, neighbour)
            if tentative < g_score.get(neighbour, math.inf):
                came_from[neighbour] = current
                g_score[neighbour] = tentative
                heapq.heappush(
                    open_heap, (tentative + heuristic(neighbour), tentative, neighbour)
                )
    return []


def route_taxiways(route: list[int], picture: AirportPicture) -> list[str]:
    """Ordered list of named taxiways traversed, collapsing repeats.

    Unnamed arcs are skipped; consecutive arcs sharing a name appear once.
    """
    if len(route) < 2:
        return []
    seg_names: dict[tuple[int, int], str] = {}
    for seg in picture.segments:
        seg_names[(min(seg.begin, seg.end), max(seg.begin, seg.end))] = seg.name

    taxiways: list[str] = []
    for a, b in zip(route, route[1:]):
        name = seg_names.get((min(a, b), max(a, b)), "")
        if not name:
            continue
        if not taxiways or taxiways[-1] != name:
            taxiways.append(name)
    return taxiways


def route_to_instructions(
    route: list[int], picture: AirportPicture, *, hold_short: str | None = None
) -> list[str]:
    """Human-readable taxi instructions for a node route.

    Produces a ``"via A, B"`` entry from the ordered taxiway list and, when a
    runway is given, a closing ``"hold short of <rwy>"``.  Returns an empty list
    for an empty/trivial route with no hold-short.
    """
    instructions: list[str] = []
    taxiways = route_taxiways(route, picture)
    if taxiways:
        instructions.append("via " + ", ".join(taxiways))
    if hold_short:
        instructions.append(f"hold short of {hold_short}")
    return instructions
