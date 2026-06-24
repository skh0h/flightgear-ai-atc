"""Tests for sidecar/airport_picture.py — models + build_taxi_graph."""

from __future__ import annotations

from sidecar.airport_picture import (
    AIAirportResponse,
    AirportPicture,
    Frequencies,
    Node,
    ParkingSpot,
    Segment,
    build_taxi_graph,
)


def _node(index: int, lat: float = 0.0, lon: float = 0.0) -> Node:
    return Node(index=index, lat=lat, lon=lon)


def test_build_taxi_graph_small_handset() -> None:
    nodes = [_node(1), _node(2), _node(3)]
    segments = [Segment(begin=1, end=2), Segment(begin=2, end=3)]
    assert build_taxi_graph(nodes, segments) == {1: [2], 2: [1, 3], 3: [2]}


def test_build_taxi_graph_is_symmetric_and_dedupes() -> None:
    nodes = [_node(i) for i in (10, 20, 30)]
    # Duplicate and reversed-duplicate edges should collapse.
    segments = [
        Segment(begin=10, end=20),
        Segment(begin=20, end=10),
        Segment(begin=20, end=30),
        Segment(begin=30, end=20),
    ]
    graph = build_taxi_graph(nodes, segments)
    for a, neighbours in graph.items():
        assert len(neighbours) == len(set(neighbours))  # no duplicate neighbours
        for b in neighbours:
            assert a in graph[b]  # symmetric


def test_build_taxi_graph_skips_self_loops_and_seeds_isolated_nodes() -> None:
    nodes = [_node(1), _node(2), _node(99)]  # 99 is isolated
    segments = [Segment(begin=1, end=1), Segment(begin=1, end=2)]  # self-loop ignored
    graph = build_taxi_graph(nodes, segments)
    assert graph[99] == []
    assert 1 not in graph[1]
    assert graph[1] == [2]


def test_build_taxi_graph_includes_parking_endpoints_not_in_nodes() -> None:
    # A pushback arc links parking index 0 (absent from nodes) to taxi node 209.
    nodes = [_node(209)]
    segments = [Segment(begin=0, end=209, pushback=True)]
    graph = build_taxi_graph(nodes, segments)
    assert graph[0] == [209]
    assert graph[209] == [0]


def _sample_picture() -> AirportPicture:
    return AirportPicture(
        icao="KSFO",
        source="code",
        generated_at="2026-06-24T00:00:00+00:00",
        groundnet_hash="abc123",
        parking=[
            ParkingSpot(id=0, name="A1", type="gate", lat=37.6, lon=-122.3, heading=90.0)
        ],
        nodes=[_node(209, 37.6, -122.38), _node(210, 37.61, -122.39)],
        segments=[Segment(begin=209, end=210, name="A")],
        frequencies=Frequencies(ground="121.80", tower="120.50"),
        taxi_graph={209: [210], 210: [209]},
    )


def test_airport_picture_json_round_trip_preserves_int_keys() -> None:
    pic = _sample_picture()
    restored = AirportPicture.model_validate_json(pic.model_dump_json())
    assert restored == pic
    assert set(restored.taxi_graph.keys()) == {209, 210}
    assert all(isinstance(k, int) for k in restored.taxi_graph)


def test_ai_response_schema_excludes_computed_fields() -> None:
    fields = set(AIAirportResponse.model_fields)
    assert "taxi_graph" not in fields
    assert "groundnet_hash" not in fields
    assert "generated_at" not in fields
    assert {"parking", "nodes", "segments", "runways", "frequencies"} <= fields
