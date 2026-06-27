"""Tests for sidecar/traffic.py — deterministic living-world traffic logic."""

from __future__ import annotations

from sidecar.airport_picture import (
    AirportPicture,
    Node,
    Runway,
    Segment,
    TrafficSnapshot,
    build_taxi_graph,
)
from sidecar.traffic import (
    Separation,
    ambient_chatter,
    intersecting_runways,
    intersection_departure_ok,
    lahso_eligible,
    separation_advice,
    sequence_with_separation,
    wake_category,
    wake_separation,
)


def _picture(
    nodes: list[Node],
    segments: list[Segment],
    runways: list[Runway] | None = None,
) -> AirportPicture:
    return AirportPicture(
        icao="TST",
        source="code",
        generated_at="2026-06-25T00:00:00+00:00",
        groundnet_hash="h",
        nodes=nodes,
        segments=segments,
        runways=runways or [],
        taxi_graph=build_taxi_graph(nodes, segments),
    )


# ---------------------------------------------------------------------------
# wake_category
# ---------------------------------------------------------------------------


def test_wake_category_representative_types() -> None:
    assert wake_category("A388") == "super"
    assert wake_category("B744") == "heavy"
    assert wake_category("A320") == "medium"
    assert wake_category("C172") == "light"
    assert wake_category("ZZZZ") == "medium"  # unknown -> medium
    assert wake_category("") == "medium"


def test_wake_category_case_insensitive_and_keywords() -> None:
    assert wake_category("c172p") == "light"
    assert wake_category("b738") == "medium"
    # A318/A319 must stay medium (not mis-classified as heavy via "A31").
    assert wake_category("A319") == "medium"
    # Spoken callsign suffixes classify correctly.
    assert wake_category("UAL123 Heavy") == "heavy"
    assert wake_category("Speedbird 2 Super") == "super"
    assert wake_category("glider") == "light"


# ---------------------------------------------------------------------------
# wake_separation
# ---------------------------------------------------------------------------


def test_wake_separation_heavy_lead_exceeds_medium_lead() -> None:
    heavy = wake_separation("B744", "C172")
    medium = wake_separation("A320", "C172")
    assert isinstance(heavy, Separation)
    assert heavy.distance_nm > medium.distance_nm > 0.0


def test_wake_separation_zero_when_light_follows_light() -> None:
    sep = wake_separation("C172", "C172")
    assert sep.distance_nm == 0.0
    assert sep.time_min == 0.0


# ---------------------------------------------------------------------------
# separation_advice
# ---------------------------------------------------------------------------


def test_separation_advice_nonempty_when_lead_heavier() -> None:
    advice = separation_advice("B744", "C172")
    assert advice != ""
    assert "wake" in advice.lower()


def test_separation_advice_empty_when_lead_not_heavier() -> None:
    assert separation_advice("C172", "B744") == ""
    assert separation_advice("A320", "A320") == ""


# ---------------------------------------------------------------------------
# intersecting_runways / lahso_eligible
# ---------------------------------------------------------------------------


def _two_runway_picture() -> AirportPicture:
    nodes = [Node(index=1, lat=0.0, lon=0.0, on_runway=True)]
    runways = [
        Runway(id="04", heading=40.0, length=2500.0),
        Runway(id="13", heading=130.0, length=2000.0),
    ]
    return _picture(nodes, [], runways)


def test_intersecting_runways_detects_crossing_pair() -> None:
    pairs = intersecting_runways(_two_runway_picture())
    assert pairs == [("04", "13")]


def test_intersecting_runways_parallel_not_flagged() -> None:
    nodes = [Node(index=1, lat=0.0, lon=0.0)]
    runways = [Runway(id="09L", heading=90.0), Runway(id="09R", heading=90.0)]
    assert intersecting_runways(_picture(nodes, [], runways)) == []


def test_intersecting_runways_reciprocal_not_flagged() -> None:
    nodes = [Node(index=1, lat=0.0, lon=0.0)]
    runways = [Runway(id="10", heading=100.0), Runway(id="28", heading=280.0)]
    assert intersecting_runways(_picture(nodes, [], runways)) == []


def test_lahso_eligible_true_for_crossing_pair() -> None:
    assert lahso_eligible(_two_runway_picture()) is True


def test_lahso_eligible_false_with_single_runway() -> None:
    one = _picture(
        [Node(index=1, lat=0.0, lon=0.0)], [], [Runway(id="04", heading=40.0)]
    )
    assert lahso_eligible(one) is False


# ---------------------------------------------------------------------------
# intersection_departure_ok
# ---------------------------------------------------------------------------


def test_intersection_departure_ok_light_with_long_remaining() -> None:
    assert (
        intersection_departure_ok(
            "C172", runway_length_m=3000.0, intersection_remaining_m=2000.0
        )
        is True
    )


def test_intersection_departure_ok_false_for_heavy_with_short_remaining() -> None:
    assert (
        intersection_departure_ok(
            "B744", runway_length_m=2500.0, intersection_remaining_m=1000.0
        )
        is False
    )


# ---------------------------------------------------------------------------
# ambient_chatter
# ---------------------------------------------------------------------------


def test_ambient_chatter_deterministic_for_fixed_seed() -> None:
    pic = _two_runway_picture()
    snaps = [
        TrafficSnapshot(callsign="DLH1", lat=0.0, lon=0.0, node_index=1),
        TrafficSnapshot(callsign="AAL2", lat=0.0, lon=0.0, node_index=1),
    ]
    first = ambient_chatter(snaps, pic, seed="abc", n=3)
    second = ambient_chatter(snaps, pic, seed="abc", n=3)
    assert first == second  # deterministic
    assert first  # non-empty when traffic present
    assert len(first) <= 3
    assert all(isinstance(line, str) and line for line in first)


def test_ambient_chatter_empty_when_no_traffic() -> None:
    assert ambient_chatter([], _two_runway_picture(), seed="abc") == []


# ---------------------------------------------------------------------------
# sequence_with_separation
# ---------------------------------------------------------------------------


def _picture_with_runway_node() -> AirportPicture:
    nodes = [
        Node(index=1, lat=37.620, lon=-122.380, on_runway=False),
        Node(index=2, lat=37.625, lon=-122.385, on_runway=True),
    ]
    segs = [Segment(begin=1, end=2, name="")]
    runways = [Runway(id="28L", heading=284.0, length=3500.0, entry_nodes=[2])]
    return _picture(nodes, segs, runways)


def test_sequence_with_separation_wake_note_when_heavy_precedes() -> None:
    pic = _picture_with_runway_node()
    # A heavy sits at the runway entrance, ahead of the user at the gate (node 1).
    snaps = [
        TrafficSnapshot(
            callsign="DLH9 Heavy", lat=37.6249, lon=-122.3849, node_index=2
        )
    ]
    count, summary = sequence_with_separation(snaps, user_node_index=1, picture=pic)
    again = sequence_with_separation(snaps, user_node_index=1, picture=pic)
    assert (count, summary) == again  # deterministic
    assert count == 1
    assert "number 2" in summary
    assert "DLH9 Heavy" in summary
    assert "wake" in summary.lower()


def test_sequence_with_separation_no_note_when_user_alone() -> None:
    pic = _picture_with_runway_node()
    count, summary = sequence_with_separation([], user_node_index=1, picture=pic)
    assert count == 0
    assert "number 1" in summary
    assert "wake" not in summary.lower()
