"""Tests for sidecar/routing.py — A* routing and instruction rendering."""

from __future__ import annotations

from pathlib import Path

from sidecar.airport_picture import AirportPicture, Node, ParkingSpot, Segment, build_taxi_graph
from sidecar.parser_code import parse_groundnet
from sidecar.routing import (
    find_route,
    nearest_node,
    route_coverage,
    route_to_instructions,
    taxiways_for_clearance,
)

_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "KSFO.groundnet.xml"


def _picture(
    nodes: list[Node],
    segments: list[Segment],
    parking: list[ParkingSpot] | None = None,
) -> AirportPicture:
    return AirportPicture(
        icao="TST",
        source="code",
        generated_at="2026-06-24T00:00:00+00:00",
        groundnet_hash="h",
        nodes=nodes,
        segments=segments,
        parking=parking or [],
        taxi_graph=build_taxi_graph(nodes, segments),
    )


# ---------------------------------------------------------------------------
# A* on small hand-built graphs
# ---------------------------------------------------------------------------


def test_a_star_picks_shorter_path() -> None:
    nodes = [
        Node(index=1, lat=0.0, lon=0.000),
        Node(index=2, lat=0.0, lon=0.001),
        Node(index=3, lat=0.0, lon=0.002),
        Node(index=4, lat=0.05, lon=0.001),  # large detour to the north
    ]
    segments = [
        Segment(begin=1, end=2),
        Segment(begin=2, end=3),  # direct, ~222 m
        Segment(begin=1, end=4),
        Segment(begin=4, end=3),  # detour, ~11 km
    ]
    pic = _picture(nodes, segments)
    assert find_route(pic, 1, 3) == [1, 2, 3]


def test_find_route_same_start_and_goal() -> None:
    pic = _picture([Node(index=1, lat=0.0, lon=0.0)], [])
    assert find_route(pic, 1, 1) == [1]


def test_find_route_unknown_endpoint_returns_empty() -> None:
    nodes = [Node(index=1, lat=0.0, lon=0.0), Node(index=2, lat=0.0, lon=0.001)]
    pic = _picture(nodes, [Segment(begin=1, end=2)])
    assert find_route(pic, 1, 999) == []
    assert find_route(pic, 999, 2) == []


def test_find_route_disconnected_returns_empty() -> None:
    nodes = [
        Node(index=1, lat=0.0, lon=0.0),
        Node(index=2, lat=0.0, lon=0.001),
        Node(index=3, lat=1.0, lon=1.0),  # isolated node
    ]
    pic = _picture(nodes, [Segment(begin=1, end=2)])
    assert 3 in pic.taxi_graph  # present as a key...
    assert find_route(pic, 1, 3) == []  # ...but unreachable


# ---------------------------------------------------------------------------
# Instruction rendering
# ---------------------------------------------------------------------------


def test_route_to_instructions_collapses_same_name() -> None:
    nodes = [Node(index=i, lat=0.0, lon=i * 0.001) for i in range(1, 5)]
    segments = [
        Segment(begin=1, end=2, name="A"),
        Segment(begin=2, end=3, name="A"),  # repeated name collapses
        Segment(begin=3, end=4, name="B"),
    ]
    pic = _picture(nodes, segments)
    instr = route_to_instructions([1, 2, 3, 4], pic, hold_short="28R")
    assert instr == ["via A, B", "hold short of 28R"]


def test_route_to_instructions_skips_unnamed_arcs() -> None:
    nodes = [Node(index=i, lat=0.0, lon=i * 0.001) for i in range(1, 4)]
    segments = [Segment(begin=1, end=2, name=""), Segment(begin=2, end=3, name="C")]
    pic = _picture(nodes, segments)
    assert route_to_instructions([1, 2, 3], pic, hold_short="10L") == [
        "via C",
        "hold short of 10L",
    ]


def test_route_to_instructions_empty_or_trivial_route() -> None:
    pic = _picture([Node(index=1, lat=0.0, lon=0.0)], [])
    assert route_to_instructions([], pic) == []
    assert route_to_instructions([1], pic) == []


# ---------------------------------------------------------------------------
# Integration: route across the real KSFO ground network
# ---------------------------------------------------------------------------


def test_fixture_gate_to_runway_route_is_connected() -> None:
    pic = parse_groundnet(str(_FIXTURE), "KSFO")
    start = pic.parking[0].id  # gates join the graph via their pushback arc
    assert start in pic.taxi_graph

    runway_nodes = [n.index for n in pic.nodes if n.on_runway]
    assert runway_nodes, "fixture should have on-runway nodes"

    route: list[int] = []
    for runway_node in runway_nodes:
        route = find_route(pic, start, runway_node)
        if route:
            break
    assert route, "no runway node reachable from the first gate"

    assert route[0] == start
    assert route[-1] in runway_nodes
    # Every consecutive pair must be a real edge in the taxi graph.
    for a, b in zip(route, route[1:]):
        assert b in pic.taxi_graph[a]

    instr = route_to_instructions(route, pic, hold_short="28R")
    assert instr[-1] == "hold short of 28R"


def test_nearest_node_filters_on_runway() -> None:
    pic = parse_groundnet(str(_FIXTURE), "KSFO")
    idx = nearest_node(pic, 37.62, -122.38, require_on_runway=True)
    assert idx is not None
    chosen = next(n for n in pic.nodes if n.index == idx)
    assert chosen.on_runway is True


# ---------------------------------------------------------------------------
# Coverage gate (Item 1)
# ---------------------------------------------------------------------------


def _dense_picture() -> AirportPicture:
    """5-node chain, all 4 arcs named → named=4, total=4, ratio=1.0 (dense)."""
    nodes = [Node(index=i, lat=0.0, lon=i * 0.001) for i in range(1, 6)]
    segments = [
        Segment(begin=1, end=2, name="A"),
        Segment(begin=2, end=3, name="A"),
        Segment(begin=3, end=4, name="B"),
        Segment(begin=4, end=5, name="C"),
    ]
    return _picture(nodes, segments)


def _sparse_picture() -> AirportPicture:
    """5-node chain, 1 of 4 arcs named → named=1, total=4, ratio=0.25 (sparse)."""
    nodes = [Node(index=i, lat=0.0, lon=i * 0.001) for i in range(1, 6)]
    segments = [
        Segment(begin=1, end=2, name=""),
        Segment(begin=2, end=3, name=""),
        Segment(begin=3, end=4, name="A"),  # only 1 named
        Segment(begin=4, end=5, name=""),
    ]
    return _picture(nodes, segments)


def test_route_coverage_empty_route() -> None:
    pic = _dense_picture()
    named, total, ratio = route_coverage([], pic)
    assert named == 0 and total == 0 and ratio == 0.0


def test_route_coverage_single_node() -> None:
    pic = _dense_picture()
    named, total, ratio = route_coverage([1], pic)
    assert named == 0 and total == 0 and ratio == 0.0


def test_route_coverage_dense() -> None:
    pic = _dense_picture()
    named, total, ratio = route_coverage([1, 2, 3, 4, 5], pic)
    assert named == 4
    assert total == 4
    assert abs(ratio - 1.0) < 0.001


def test_route_coverage_sparse() -> None:
    pic = _sparse_picture()
    named, total, ratio = route_coverage([1, 2, 3, 4, 5], pic)
    assert named == 1
    assert total == 4
    assert abs(ratio - 0.25) < 0.001


def test_taxiways_for_clearance_dense_keeps_via() -> None:
    """Dense path (>= 3 named segments) → taxiways non-empty."""
    pic = _dense_picture()
    taxiways = taxiways_for_clearance([1, 2, 3, 4, 5], pic)
    # 3 distinct names after collapsing: A, B, C — meets >= 3 gate
    assert taxiways == ["A", "B", "C"]


def test_taxiways_for_clearance_sparse_drops_via() -> None:
    """Sparse path (1 named / 4 total = 25% < 30%, and < 3 named) → empty list."""
    pic = _sparse_picture()
    taxiways = taxiways_for_clearance([1, 2, 3, 4, 5], pic)
    assert taxiways == []


def test_taxiways_for_clearance_ratio_gate() -> None:
    """Path with > 30% but < 3 named segments still qualifies via ratio gate."""
    # 2-node path: 1 named arc out of 2 total → 50% > 30%, but only 1 named segment
    nodes = [Node(index=i, lat=0.0, lon=i * 0.001) for i in range(1, 4)]
    segments = [
        Segment(begin=1, end=2, name="A"),  # named
        Segment(begin=2, end=3, name=""),    # unnamed
    ]
    pic = _picture(nodes, segments)
    # named=1, total=2, ratio=0.5 > 0.30 → gate passes
    taxiways = taxiways_for_clearance([1, 2, 3], pic)
    assert taxiways == ["A"]


def test_taxiways_for_clearance_empty_route() -> None:
    pic = _dense_picture()
    assert taxiways_for_clearance([], pic) == []
