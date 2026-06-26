"""Tests for sidecar/runway_selection.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from sidecar.airport_picture import AirportPicture, Node, ParkingSpot, Runway, Segment, build_taxi_graph
from sidecar.parser_code import parse_groundnet
from sidecar.runway_selection import (
    headwind_component,
    on_runway_node_for_position,
    runway_entry_node,
    select_departure_runway,
    start_node_for_position,
    taxi_to_runway,
)

_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "KSFO.groundnet.xml"


# ---------------------------------------------------------------------------
# Minimal picture builder (no runways — mirrors fixture-only parse)
# ---------------------------------------------------------------------------

def _minimal(
    nodes: list[Node],
    segments: list[Segment],
    parking: list[ParkingSpot] | None = None,
    runways: list[Runway] | None = None,
) -> AirportPicture:
    return AirportPicture(
        icao="TST",
        source="code",
        generated_at="2026-06-24T00:00:00+00:00",
        groundnet_hash="h",
        nodes=nodes,
        segments=segments,
        parking=parking or [],
        runways=runways or [],
        taxi_graph=build_taxi_graph(nodes, segments),
    )


# ---------------------------------------------------------------------------
# headwind_component
# ---------------------------------------------------------------------------

def test_headwind_component_direct_headwind() -> None:
    # Wind from 280°, runway heading 280° → pure headwind
    hw = headwind_component(280.0, 280.0, 20.0)
    assert abs(hw - 20.0) < 0.01


def test_headwind_component_direct_tailwind() -> None:
    # Wind from 100° onto runway 280° → pure tailwind
    hw = headwind_component(280.0, 100.0, 20.0)
    assert abs(hw + 20.0) < 0.01


def test_headwind_component_crosswind() -> None:
    # 90° crosswind gives ~0 headwind component
    hw = headwind_component(280.0, 10.0, 20.0)
    assert abs(hw) < 0.1


# ---------------------------------------------------------------------------
# select_departure_runway — with Runway objects
# ---------------------------------------------------------------------------

_RWY_28L = Runway(id="28L", heading=284.0, length=11870.0)
_RWY_10R = Runway(id="10R", heading=104.0, length=11870.0)
_RWY_28R = Runway(id="28R", heading=284.0, length=10600.0)
_RWY_10L = Runway(id="10L", heading=104.0, length=10600.0)


def _pic_with_runways(*rwys: Runway) -> AirportPicture:
    return _minimal(
        [Node(index=1, lat=37.62, lon=-122.38, on_runway=True)],
        [],
        runways=list(rwys),
    )


def test_select_runway_westerly_wind_picks_28() -> None:
    pic = _pic_with_runways(_RWY_28L, _RWY_10R, _RWY_28R, _RWY_10L)
    rwy = select_departure_runway(pic, wind_dir=270.0, wind_kt=15.0)
    assert rwy is not None
    assert rwy.id in ("28L", "28R")


def test_select_runway_easterly_wind_picks_10() -> None:
    pic = _pic_with_runways(_RWY_28L, _RWY_10R, _RWY_28R, _RWY_10L)
    rwy = select_departure_runway(pic, wind_dir=90.0, wind_kt=12.0)
    assert rwy is not None
    assert rwy.id in ("10L", "10R")


def test_select_runway_calm_is_deterministic() -> None:
    pic = _pic_with_runways(_RWY_28L, _RWY_10R, _RWY_28R, _RWY_10L)
    r1 = select_departure_runway(pic)
    r2 = select_departure_runway(pic)
    assert r1 is not None and r2 is not None
    assert r1.id == r2.id


def test_select_runway_no_runways_returns_none() -> None:
    pic = _minimal([Node(index=1, lat=0.0, lon=0.0)], [])
    assert select_departure_runway(pic) is None


def test_select_runway_zero_wind_treated_as_calm() -> None:
    pic = _pic_with_runways(_RWY_28L, _RWY_10R)
    # wind_kt=0 → calm path, not wind-driven
    rwy = select_departure_runway(pic, wind_dir=90.0, wind_kt=0.0)
    assert rwy is not None


# ---------------------------------------------------------------------------
# Mode A: active-runway filtering
# ---------------------------------------------------------------------------

def test_select_runway_restricts_to_active_ends() -> None:
    """When some runways are flagged active, only those are candidates."""
    rwy_28l_active = Runway(id="28L", heading=284.0, length=11870.0, active=True)
    rwy_10r = Runway(id="10R", heading=104.0, length=11870.0)  # inactive
    pic = _pic_with_runways(rwy_28l_active, rwy_10r)
    # Easterly wind would normally favour 10R, but only 28L is active.
    rwy = select_departure_runway(pic, wind_dir=90.0, wind_kt=12.0)
    assert rwy is not None
    assert rwy.id == "28L"


def test_select_runway_falls_back_to_all_when_none_active() -> None:
    """With no runway flagged active, all runways remain candidates (no-op)."""
    pic = _pic_with_runways(_RWY_28L, _RWY_10R, _RWY_28R, _RWY_10L)
    assert all(not r.active for r in pic.runways)
    # Easterly wind across ALL runways → a 10-series end.
    rwy = select_departure_runway(pic, wind_dir=90.0, wind_kt=12.0)
    assert rwy is not None
    assert rwy.id in ("10L", "10R")


# ---------------------------------------------------------------------------
# start_node_for_position
# ---------------------------------------------------------------------------

def test_start_node_uses_parking_id_when_in_graph() -> None:
    nodes = [Node(index=10, lat=37.62, lon=-122.38)]
    segs = [Segment(begin=10, end=11)]
    parking = [ParkingSpot(id=11, name="G1", lat=37.621, lon=-122.381)]
    pic = _minimal(nodes, segs, parking)
    assert 11 in pic.taxi_graph
    result = start_node_for_position(pic, 37.621, -122.381, parking_id=11)
    assert result == 11


def test_start_node_falls_back_to_nearest_off_runway() -> None:
    nodes = [
        Node(index=1, lat=37.620, lon=-122.380, on_runway=False),
        Node(index=2, lat=37.625, lon=-122.385, on_runway=True),
    ]
    pic = _minimal(nodes, [Segment(begin=1, end=2)])
    result = start_node_for_position(pic, 37.620, -122.380)
    assert result == 1  # closest non-runway node


# ---------------------------------------------------------------------------
# runway_entry_node
# ---------------------------------------------------------------------------

def test_runway_entry_node_prefers_entry_nodes_list() -> None:
    rwy = Runway(id="28L", heading=284.0, entry_nodes=[42, 99])
    pic = _minimal([Node(index=42, lat=37.62, lon=-122.39, on_runway=True)], [])
    assert runway_entry_node(pic, rwy) == 42


def test_runway_entry_node_uses_threshold_when_no_entry_nodes() -> None:
    # thr near node index 1
    rwy = Runway(id="28L", heading=284.0, thr_lat=37.620, thr_lon=-122.380)
    nodes = [
        Node(index=1, lat=37.620, lon=-122.380, on_runway=True),
        Node(index=2, lat=37.625, lon=-122.385, on_runway=True),
    ]
    pic = _minimal(nodes, [])
    result = runway_entry_node(pic, rwy)
    assert result == 1


def test_runway_entry_node_last_resort_is_any_on_runway_node() -> None:
    rwy = Runway(id="28L", heading=284.0)  # no entry_nodes, no threshold
    nodes = [
        Node(index=5, lat=37.62, lon=-122.38, on_runway=True),
        Node(index=6, lat=37.63, lon=-122.39, on_runway=False),
    ]
    pic = _minimal(nodes, [])
    result = runway_entry_node(pic, rwy)
    assert result == 5


# ---------------------------------------------------------------------------
# on_runway_node_for_position (fixture-only fallback)
# ---------------------------------------------------------------------------

def test_on_runway_node_for_position_returns_on_runway_node() -> None:
    pic = parse_groundnet(_FIXTURE, "KSFO")
    # Aircraft near KSFO centre
    node_idx = on_runway_node_for_position(pic, 37.6188, -122.3750)
    assert node_idx is not None
    node = next(n for n in pic.nodes if n.index == node_idx)
    assert node.on_runway is True


# ---------------------------------------------------------------------------
# taxi_to_runway — full end-to-end on KSFO fixture
# ---------------------------------------------------------------------------

def test_taxi_to_runway_produces_nonempty_route_from_gate() -> None:
    pic = parse_groundnet(_FIXTURE, "KSFO")
    gate = pic.parking[0]

    result = taxi_to_runway(
        pic,
        callsign="SWA123",
        lat=gate.lat,
        lon=gate.lon,
        parking_id=gate.id,
    )

    # Route must be non-empty and connected
    assert result.route, "expected a route from gate to runway node"
    for a, b in zip(result.route, result.route[1:]):
        assert b in pic.taxi_graph[a], f"edge {a}-{b} not in graph"

    # Clearance text must mention the callsign
    assert "SWA123" in result.clearance_text
    assert "taxi" in result.clearance_text.lower()


def test_taxi_to_runway_westerly_wind_ksfo(tmp_path: Path) -> None:
    """With westerly wind at KSFO (real runways injected via airportinfo)."""
    airportinfo = {
        "runways": [
            {"id": "28L", "heading": 284.0, "length": 11870.0,
             "thr_lat": 37.6158, "thr_lon": -122.3572, "entry_nodes": []},
            {"id": "10R", "heading": 104.0, "length": 11870.0,
             "thr_lat": 37.6301, "thr_lon": -122.3926, "entry_nodes": []},
            {"id": "28R", "heading": 284.0, "length": 10600.0,
             "thr_lat": 37.6139, "thr_lon": -122.3589, "entry_nodes": []},
            {"id": "10L", "heading": 104.0, "length": 10600.0,
             "thr_lat": 37.6283, "thr_lon": -122.3908, "entry_nodes": []},
        ]
    }
    pic = parse_groundnet(_FIXTURE, "KSFO", airportinfo=airportinfo)
    gate = pic.parking[0]

    result = taxi_to_runway(
        pic,
        callsign="UAL1",
        lat=gate.lat,
        lon=gate.lon,
        parking_id=gate.id,
        wind_dir=270.0,
        wind_kt=15.0,
    )

    assert result.runway_id in ("28L", "28R"), (
        f"westerly wind should select a 28-series runway, got {result.runway_id!r}"
    )
    assert "UAL1" in result.clearance_text
    assert result.runway_id in result.clearance_text


def test_taxi_to_runway_no_taxiways_produces_simple_clearance() -> None:
    """When no named segments exist the clearance omits the 'via' clause."""
    nodes = [
        Node(index=1, lat=37.620, lon=-122.380, on_runway=False),
        Node(index=2, lat=37.625, lon=-122.385, on_runway=True),
    ]
    segs = [Segment(begin=1, end=2, name="")]  # unnamed
    runways = [Runway(id="28L", heading=284.0, entry_nodes=[2])]
    pic = _minimal(nodes, segs, runways=runways)

    result = taxi_to_runway(pic, "N123AB", 37.620, -122.380)
    assert result.taxiways == []
    assert "via" not in result.clearance_text
    assert "28L" in result.clearance_text
