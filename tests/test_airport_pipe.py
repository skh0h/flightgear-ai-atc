"""Tests for the Nasal→sidecar airport data pipe (Item 3).

These are sidecar-side unit tests: a fake bridge supplies a synthetic mailbox
payload and we assert that ``merge_airport_mailbox`` populates
``picture.runways`` and ``picture.frequencies`` correctly, and that an empty
mailbox leaves the picture unchanged.
"""

from __future__ import annotations

from typing import Any

from sidecar.airport_picture import AirportPicture, Node, Segment, build_taxi_graph
from sidecar.main import (
    AP_FREQ_ATIS,
    AP_FREQ_DEPARTURE,
    AP_FREQ_GROUND,
    AP_FREQ_TOWER,
    AP_FREQ_APPROACH,
    AP_RUNWAY_COUNT,
    AP_RUNWAY_PREFIX,
    merge_airport_mailbox,
)


class _FakeBridge:
    """Minimal bridge stub that serves a fixed property dict."""

    def __init__(self, props: dict[str, Any]) -> None:
        self.props = props

    def get(self, path: str) -> str:
        return str(self.props.get(path, ""))

    def set(self, path: str, value: Any) -> None:
        self.props[path] = value


def _empty_picture() -> AirportPicture:
    nodes = [Node(index=1, lat=37.62, lon=-122.38)]
    segs: list[Segment] = []
    return AirportPicture(
        icao="TST",
        source="code",
        generated_at="2026-06-24T00:00:00+00:00",
        groundnet_hash="h",
        nodes=nodes,
        segments=segs,
        taxi_graph=build_taxi_graph(nodes, segs),
    )


# ---------------------------------------------------------------------------
# Empty mailbox — picture must be unchanged
# ---------------------------------------------------------------------------

def test_merge_empty_mailbox_leaves_picture_unchanged() -> None:
    pic = _empty_picture()
    bridge = _FakeBridge({})
    result = merge_airport_mailbox(pic, bridge)
    assert result is pic  # same object — no copy when no data
    assert result.runways == []
    assert result.frequencies.ground is None


def test_merge_zero_runway_count_leaves_picture_unchanged() -> None:
    pic = _empty_picture()
    bridge = _FakeBridge({AP_RUNWAY_COUNT: "0"})
    result = merge_airport_mailbox(pic, bridge)
    assert result is pic


def test_merge_invalid_runway_count_leaves_picture_unchanged() -> None:
    pic = _empty_picture()
    bridge = _FakeBridge({AP_RUNWAY_COUNT: "not_a_number"})
    result = merge_airport_mailbox(pic, bridge)
    assert result is pic


# ---------------------------------------------------------------------------
# Populated mailbox — runways and frequencies get merged
# ---------------------------------------------------------------------------

def _runway_props(index: int, rwy_id: str, heading: float, thr_lat: float,
                   thr_lon: float, length: float, ils_freq: str = "") -> dict[str, str]:
    pfx = f"{AP_RUNWAY_PREFIX}[{index}]"
    d = {
        f"{pfx}/id": rwy_id,
        f"{pfx}/heading": str(heading),
        f"{pfx}/thr_lat": str(thr_lat),
        f"{pfx}/thr_lon": str(thr_lon),
        f"{pfx}/length": str(length),
        f"{pfx}/ils_freq": ils_freq,
    }
    return d


def test_merge_single_runway_populates_picture() -> None:
    pic = _empty_picture()
    props: dict[str, Any] = {AP_RUNWAY_COUNT: "1"}
    props.update(_runway_props(0, "28L", 284.0, 37.6158, -122.3572, 11870.0, "108.90"))
    bridge = _FakeBridge(props)

    result = merge_airport_mailbox(pic, bridge)

    assert result is not pic  # new object returned
    assert len(result.runways) == 1
    rwy = result.runways[0]
    assert rwy.id == "28L"
    assert abs(rwy.heading - 284.0) < 0.001
    assert abs(rwy.thr_lat - 37.6158) < 0.0001
    assert abs(rwy.thr_lon - (-122.3572)) < 0.0001
    assert abs(rwy.length - 11870.0) < 0.1
    assert rwy.ils_freq == "108.90"


def test_merge_two_runways() -> None:
    pic = _empty_picture()
    props: dict[str, Any] = {AP_RUNWAY_COUNT: "2"}
    props.update(_runway_props(0, "28L", 284.0, 37.6158, -122.3572, 11870.0))
    props.update(_runway_props(1, "10R", 104.0, 37.6301, -122.3926, 11870.0))
    bridge = _FakeBridge(props)

    result = merge_airport_mailbox(pic, bridge)

    ids = {r.id for r in result.runways}
    assert ids == {"28L", "10R"}


def test_merge_runway_without_ils_has_none_ils_freq() -> None:
    pic = _empty_picture()
    props: dict[str, Any] = {AP_RUNWAY_COUNT: "1"}
    props.update(_runway_props(0, "01L", 10.0, 37.0, -122.0, 8000.0, ""))
    bridge = _FakeBridge(props)

    result = merge_airport_mailbox(pic, bridge)
    assert result.runways[0].ils_freq is None


def test_merge_frequencies_populated() -> None:
    pic = _empty_picture()
    props: dict[str, Any] = {
        AP_RUNWAY_COUNT: "1",
        AP_FREQ_GROUND: "121.80",
        AP_FREQ_TOWER: "118.85",
        AP_FREQ_ATIS: "135.65",
        AP_FREQ_APPROACH: "120.35",
        AP_FREQ_DEPARTURE: "135.10",
    }
    props.update(_runway_props(0, "28L", 284.0, 37.6158, -122.3572, 11870.0))
    bridge = _FakeBridge(props)

    result = merge_airport_mailbox(pic, bridge)

    assert result.frequencies.ground == "121.80"
    assert result.frequencies.tower == "118.85"
    assert result.frequencies.atis == "135.65"
    assert result.frequencies.approach == "120.35"
    assert result.frequencies.departure == "135.10"


def test_merge_partial_frequencies_leaves_absent_as_none() -> None:
    pic = _empty_picture()
    props: dict[str, Any] = {
        AP_RUNWAY_COUNT: "1",
        AP_FREQ_TOWER: "118.85",  # only tower present
    }
    props.update(_runway_props(0, "28L", 284.0, 37.0, -122.0, 11000.0))
    bridge = _FakeBridge(props)

    result = merge_airport_mailbox(pic, bridge)

    assert result.frequencies.tower == "118.85"
    assert result.frequencies.ground is None
    assert result.frequencies.atis is None


def test_merge_skips_runway_with_empty_id() -> None:
    """A runway entry with an empty id string is silently skipped."""
    pic = _empty_picture()
    props: dict[str, Any] = {AP_RUNWAY_COUNT: "2"}
    props.update(_runway_props(0, "", 284.0, 37.0, -122.0, 11000.0))  # no id
    props.update(_runway_props(1, "28R", 284.0, 37.61, -122.36, 10600.0))
    bridge = _FakeBridge(props)

    result = merge_airport_mailbox(pic, bridge)
    assert len(result.runways) == 1
    assert result.runways[0].id == "28R"


def test_merge_is_idempotent() -> None:
    """Calling merge twice with the same mailbox yields identical runway data."""
    pic = _empty_picture()
    props: dict[str, Any] = {AP_RUNWAY_COUNT: "1"}
    props.update(_runway_props(0, "28L", 284.0, 37.6158, -122.3572, 11870.0))
    bridge = _FakeBridge(props)

    result1 = merge_airport_mailbox(pic, bridge)
    result2 = merge_airport_mailbox(result1, bridge)

    assert len(result2.runways) == 1
    assert result2.runways[0].id == "28L"
