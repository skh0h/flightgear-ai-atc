"""Tests for sidecar/routing.py — A* routing and instruction rendering."""

from __future__ import annotations

from pathlib import Path

from sidecar.airport_picture import AirportPicture, Node, ParkingSpot, Segment, build_taxi_graph
from sidecar.parser_code import parse_groundnet
from sidecar.routing import (
    find_route,
    nearest_node,
    route_to_instructions,
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
