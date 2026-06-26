"""Tests for sidecar/briefing.py — pure, deterministic FSS briefing assembly."""

from __future__ import annotations

from sidecar.briefing import fss_briefing

_METAR = "KSFO 241753Z 24015KT 10SM SKC 20/10 A2992"


def test_briefing_includes_all_fields_when_provided() -> None:
    out = fss_briefing(
        "KSFO",
        "KLAX",
        metar=_METAR,
        notams=["RWY 28L CLSD", "TWY B LGT U/S"],
        tfrs=["TFR 1/2345 STADIUM SFO"],
        route="OFFSH3 BSR Q90 GMN SADDE6",
    )
    assert "KSFO" in out
    assert "KLAX" in out
    assert _METAR in out
    assert "RWY 28L CLSD" in out
    assert "TWY B LGT U/S" in out
    assert "TFR 1/2345 STADIUM SFO" in out
    assert "OFFSH3 BSR Q90 GMN SADDE6" in out


def test_briefing_section_headers_present() -> None:
    out = fss_briefing("KSFO", "KLAX")
    for header in ("SYNOPSIS", "WEATHER", "NOTAMS", "TFRS", "ROUTE"):
        assert header in out


def test_briefing_deterministic() -> None:
    """Identical inputs produce byte-identical output (no timestamps)."""
    args = ("KBOS", "KJFK")
    kwargs = dict(metar=_METAR, notams=["A"], tfrs=["B"], route="DCT")
    assert fss_briefing(*args, **kwargs) == fss_briefing(*args, **kwargs)


def test_briefing_handles_empty_notams_and_tfrs() -> None:
    """Empty/None notams & tfrs render explicit 'none on file' lines."""
    out = fss_briefing("KSFO", "KLAX")
    assert "No NOTAMs on file." in out
    assert "No TFRs on file." in out
    # Empty iterables behave the same as None.
    out2 = fss_briefing("KSFO", "KLAX", notams=[], tfrs=[])
    assert "No NOTAMs on file." in out2
    assert "No TFRs on file." in out2


def test_briefing_handles_missing_metar_and_route() -> None:
    out = fss_briefing("KSFO", "KLAX")
    assert "No current weather reported." in out
    assert "No route filed." in out


def test_briefing_returns_multiline_string() -> None:
    out = fss_briefing("KSFO", "KLAX", metar=_METAR)
    assert isinstance(out, str)
    assert "\n" in out
    assert out.splitlines()[0] == "FLIGHT SERVICE STATION BRIEFING"
