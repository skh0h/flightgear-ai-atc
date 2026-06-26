"""Tests for sidecar/parser_code.py — parses the real KSFO groundnet fixture."""

from __future__ import annotations

from pathlib import Path

import pytest

from sidecar.parser_code import ParseError, parse_groundnet

_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "KSFO.groundnet.xml"


def _parse():
    return parse_groundnet(str(_FIXTURE), "KSFO")


def test_parses_fixture_counts_positive() -> None:
    pic = _parse()
    assert pic.icao == "KSFO"
    assert pic.source == "code"
    assert len(pic.parking) > 0
    assert len(pic.nodes) > 0
    assert len(pic.segments) > 0


def test_dmm_coordinate_decoding_exact() -> None:
    # Node 209 in the fixture: lat="N37 36.386" lon="W122 23.011".
    pic = _parse()
    node = next(n for n in pic.nodes if n.index == 209)
    assert abs(node.lat - (37 + 36.386 / 60.0)) < 1e-4
    assert abs(node.lon - -(122 + 23.011 / 60.0)) < 1e-4


def test_all_coordinates_in_bay_area_box() -> None:
    pic = _parse()
    for node in pic.nodes:
        assert 37.0 < node.lat < 38.0
        assert -123.0 < node.lon < -122.0


def test_segments_deduped_undirected() -> None:
    pic = _parse()
    keys = [(min(s.begin, s.end), max(s.begin, s.end)) for s in pic.segments]
    assert len(keys) == len(set(keys))


def test_taxi_graph_is_symmetric() -> None:
    graph = _parse().taxi_graph
    for a, neighbours in graph.items():
        for b in neighbours:
            assert a in graph[b]


def test_hash_is_deterministic() -> None:
    assert _parse().groundnet_hash == _parse().groundnet_hash
    assert len(_parse().groundnet_hash) == 64


def test_frequencies_parsed_from_groundnet() -> None:
    freqs = _parse().frequencies
    assert freqs.ground is not None
    assert freqs.tower is not None
    assert "." in freqs.tower


def test_on_runway_and_hold_point_flags_present() -> None:
    pic = _parse()
    assert any(n.on_runway for n in pic.nodes)
    assert any(n.hold_point for n in pic.nodes)


def test_parse_error_on_malformed_xml() -> None:
    with pytest.raises(ParseError):
        parse_groundnet("<groundnet><TaxiNodes><node", "BAD")


def test_parse_error_on_empty_string() -> None:
    with pytest.raises(ParseError, match="empty"):
        parse_groundnet("", "BAD")


def test_parse_error_on_whitespace_only() -> None:
    with pytest.raises(ParseError, match="empty"):
        parse_groundnet("   \n\t  ", "BAD")


def test_parse_error_on_malformed_xml_has_helpful_message() -> None:
    with pytest.raises(ParseError, match="(?i)malformed.*ZZZZ"):
        parse_groundnet("<groundnet><node", "ZZZZ")


def test_parse_error_on_wrong_root() -> None:
    with pytest.raises(ParseError):
        parse_groundnet("<notgroundnet/>", "BAD")


def test_parse_error_on_non_numeric_coord() -> None:
    xml = (
        "<groundnet><TaxiNodes>"
        '<node index="0" lat="abc" lon="W122 0.0" isOnRunway="0" holdPointType="none"/>'
        "</TaxiNodes></groundnet>"
    )
    with pytest.raises(ParseError):
        parse_groundnet(xml, "BAD")


def test_airportinfo_merges_runways_and_freq_override() -> None:
    airportinfo = {
        "runways": [
            {
                "id": "28R",
                "thr_lat": 37.61,
                "thr_lon": -122.36,
                "heading": 281.0,
                "length": 3618.0,
                "ils_freq": "111.70",
                "entry_nodes": [209, 210],
            }
        ],
        "frequencies": {"ground": "121.80"},
    }
    pic = parse_groundnet(str(_FIXTURE), "KSFO", airportinfo=airportinfo)
    assert len(pic.runways) == 1
    assert pic.runways[0].id == "28R"
    assert pic.runways[0].ils_freq == "111.70"
    assert pic.runways[0].entry_nodes == [209, 210]
    assert pic.frequencies.ground == "121.80"


def test_accepts_raw_xml_text_and_bytes() -> None:
    xml = (
        "<groundnet><TaxiNodes>"
        '<node index="209" lat="N37 36.386" lon="W122 23.011" isOnRunway="1" holdPointType="none"/>'
        '<node index="210" lat="N37 36.434" lon="W122 22.707" isOnRunway="0" holdPointType="PushBack"/>'
        "</TaxiNodes>"
        '<TaxiWaySegments><arc begin="209" end="210" name="" isPushBackRoute="0"/></TaxiWaySegments>'
        "</groundnet>"
    )
    pic_text = parse_groundnet(xml, "TST")
    pic_bytes = parse_groundnet(xml.encode("utf-8"), "TST")
    assert len(pic_text.nodes) == 2
    assert pic_text.nodes[0].on_runway is True
    assert pic_text.nodes[0].hold_point is False  # holdPointType="none"
    assert pic_text.nodes[1].hold_point is True  # holdPointType="PushBack"
    assert pic_text.groundnet_hash == pic_bytes.groundnet_hash
