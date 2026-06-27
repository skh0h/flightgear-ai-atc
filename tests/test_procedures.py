"""Tests for sidecar/procedures.py — deterministic IFR procedure helpers."""

from __future__ import annotations

from sidecar.procedures import (
    CraftClearance,
    Navaid,
    assign_edct,
    build_craft_clearance,
    dme_arc_instruction,
    holding_entry,
)


# ---------------------------------------------------------------------------
# Navaid dataclass
# ---------------------------------------------------------------------------


def test_navaid_defaults() -> None:
    nav = Navaid("BOS")
    assert nav.ident == "BOS"
    assert nav.kind == ""
    assert nav.freq == ""
    assert nav.lat == 0.0
    assert nav.lon == 0.0
    assert nav.radial == 0.0


def test_navaid_full() -> None:
    nav = Navaid("OAK", kind="VORTAC", freq="116.8", lat=37.7, lon=-122.2, radial=90.0)
    assert (nav.kind, nav.freq, nav.lat, nav.lon, nav.radial) == (
        "VORTAC",
        "116.8",
        37.7,
        -122.2,
        90.0,
    )


# ---------------------------------------------------------------------------
# holding_entry — standard (right) pattern, all three entry types
# ---------------------------------------------------------------------------


def test_holding_entry_direct_right() -> None:
    # Heading clockwise of the inbound course (holding side) -> direct.
    assert holding_entry(90.0, 0.0) == "direct"
    # On the inbound course exactly -> direct.
    assert holding_entry(90.0, 90.0) == "direct"
    # Just inside the holding-side half (d ~ 170) -> direct.
    assert holding_entry(170.0, 0.0) == "direct"


def test_holding_entry_teardrop_right() -> None:
    # 180 <= d < 250 -> teardrop (70-deg sector adjacent to the outbound course).
    assert holding_entry(200.0, 0.0) == "teardrop"
    assert holding_entry(180.0, 0.0) == "teardrop"  # boundary: outbound course
    assert holding_entry(249.0, 0.0) == "teardrop"


def test_holding_entry_parallel_right() -> None:
    # 250 <= d < 360 -> parallel (110-deg sector adjacent to the inbound course).
    assert holding_entry(300.0, 0.0) == "parallel"
    assert holding_entry(250.0, 0.0) == "parallel"  # boundary
    assert holding_entry(359.0, 0.0) == "parallel"


def test_holding_entry_handles_wraparound_in_course() -> None:
    # inbound course 350, heading 020 -> d = (20 - 350) % 360 = 30 -> direct.
    assert holding_entry(20.0, 350.0) == "direct"
    # inbound course 270, heading 100 -> d = (100 - 270) % 360 = 190 -> teardrop.
    assert holding_entry(100.0, 270.0) == "teardrop"


# ---------------------------------------------------------------------------
# holding_entry — left (non-standard) pattern is the mirror image
# ---------------------------------------------------------------------------


def test_holding_entry_left_is_mirror_of_right() -> None:
    # Geometry that is "parallel" for a standard pattern becomes "direct" when
    # the pattern is mirrored to left turns, and vice-versa.
    assert holding_entry(300.0, 0.0, turn="right") == "parallel"
    assert holding_entry(300.0, 0.0, turn="left") == "direct"

    assert holding_entry(60.0, 0.0, turn="right") == "direct"
    assert holding_entry(60.0, 0.0, turn="left") == "parallel"

    # Teardrop mirrors to teardrop's mirror sector.
    assert holding_entry(160.0, 0.0, turn="right") == "direct"
    assert holding_entry(160.0, 0.0, turn="left") == "teardrop"


def test_holding_entry_turn_arg_is_case_insensitive() -> None:
    assert holding_entry(60.0, 0.0, turn="LEFT") == "parallel"
    assert holding_entry(60.0, 0.0, turn="L") == "parallel"
    assert holding_entry(60.0, 0.0, turn="Right") == "direct"


# ---------------------------------------------------------------------------
# CRAFT clearance
# ---------------------------------------------------------------------------


def test_build_craft_clearance_maps_fields() -> None:
    clr = build_craft_clearance(
        "N123AB",
        destination="KBOS",
        route="as filed",
        altitude="5000",
        departure_freq="124.7",
        squawk="4271",
    )
    assert isinstance(clr, CraftClearance)
    assert clr.cleared_limit == "KBOS"
    assert clr.route == "as filed"
    assert clr.altitude == "5000"
    assert clr.departure_freq == "124.7"
    assert clr.squawk == "4271"


def test_craft_clearance_as_phrase_exact() -> None:
    clr = build_craft_clearance(
        "N123AB",
        destination="KBOS",
        route="as filed",
        altitude="5000",
        departure_freq="124.7",
        squawk="4271",
    )
    assert clr.as_phrase("N123AB") == (
        "N123AB, cleared to KBOS via as filed, climb maintain 5000, "
        "departure 124.7, squawk 4271."
    )


def test_build_craft_clearance_defaults_empty() -> None:
    clr = build_craft_clearance("N1")
    assert (
        clr.cleared_limit,
        clr.route,
        clr.altitude,
        clr.departure_freq,
        clr.squawk,
    ) == ("", "", "", "", "")


# ---------------------------------------------------------------------------
# assign_edct — pure arithmetic incl. midnight wraparound
# ---------------------------------------------------------------------------


def test_assign_edct_basic_window() -> None:
    # 10:00Z + 30 min = EDCT 10:30Z, window -5/+5 -> 10:25Z-10:35Z.
    assert assign_edct(600, 30) == "10:25Z-10:35Z"


def test_assign_edct_wraps_past_midnight() -> None:
    # 23:58Z + 5 min = EDCT 00:03Z; window 23:58Z-00:08Z.
    assert assign_edct(1438, 5) == "23:58Z-00:08Z"


def test_assign_edct_large_offset_wraps_mod_1440() -> None:
    # 23:00Z (1380) + 120 min = 25:00 -> 01:00Z; window 00:55Z-01:05Z.
    assert assign_edct(1380, 120) == "00:55Z-01:05Z"


def test_assign_edct_zero_offset() -> None:
    assert assign_edct(0, 0) == "23:55Z-00:05Z"


# ---------------------------------------------------------------------------
# dme_arc_instruction
# ---------------------------------------------------------------------------


def test_dme_arc_instruction_integer_distance() -> None:
    assert (
        dme_arc_instruction("abc", 15.0, "clockwise")
        == "Fly the 15 DME arc clockwise of ABC."
    )


def test_dme_arc_instruction_fractional_distance() -> None:
    assert (
        dme_arc_instruction("OAK", 12.5, "counterclockwise")
        == "Fly the 12.5 DME arc counterclockwise of OAK."
    )
