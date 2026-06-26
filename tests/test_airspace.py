"""Tests for sidecar/airspace.py — deterministic airspace classification."""

from __future__ import annotations

from sidecar.airspace import (
    Airspace,
    airspace_class_at,
    brasher_warning,
    special_use_at,
)

# A shared reference centre (roughly Newark/EWR-ish, but values are arbitrary).
_LAT = 40.69
_LON = -74.17


def _class_c() -> Airspace:
    return Airspace(
        ident="C-EWR",
        airspace_class="C",
        kind="class",
        center_lat=_LAT,
        center_lon=_LON,
        radius_nm=5.0,
        floor_ft=0.0,
        ceiling_ft=4000.0,
    )


def _class_b() -> Airspace:
    return Airspace(
        ident="B-NYC",
        airspace_class="B",
        kind="class",
        center_lat=_LAT,
        center_lon=_LON,
        radius_nm=10.0,
        floor_ft=0.0,
        ceiling_ft=10000.0,
    )


# ---------------------------------------------------------------------------
# airspace_class_at
# ---------------------------------------------------------------------------


def test_airspace_class_inside_class_c_band() -> None:
    # A point at the centre, within the 0-4000 ft band -> "C".
    assert airspace_class_at(_LAT, _LON, 2000.0, [_class_c()]) == "C"


def test_airspace_class_outside_radius_is_g() -> None:
    # Far away horizontally -> uncontrolled "G".
    assert airspace_class_at(48.0, 2.0, 2000.0, [_class_c()]) == "G"


def test_airspace_class_above_ceiling_is_g() -> None:
    # Over the centre but above the ceiling -> "G".
    assert airspace_class_at(_LAT, _LON, 9000.0, [_class_c()]) == "G"


def test_airspace_class_nested_b_over_c_returns_most_restrictive() -> None:
    # Point sits inside both the class B and class C cylinders; B wins.
    airspaces = [_class_c(), _class_b()]
    assert airspace_class_at(_LAT, _LON, 2000.0, airspaces) == "B"


def test_airspace_class_empty_defaults_to_g() -> None:
    assert airspace_class_at(_LAT, _LON, 2000.0, []) == "G"


# ---------------------------------------------------------------------------
# special_use_at
# ---------------------------------------------------------------------------


def test_special_use_finds_containing_and_excludes_far() -> None:
    moa = Airspace(
        ident="WARRIOR-MOA",
        kind="moa",
        center_lat=_LAT,
        center_lon=_LON,
        radius_nm=20.0,
        floor_ft=5000.0,
        ceiling_ft=18000.0,
    )
    restricted = Airspace(
        ident="R-4001",
        kind="restricted",
        center_lat=_LAT,
        center_lon=_LON,
        radius_nm=8.0,
        floor_ft=0.0,
        ceiling_ft=20000.0,
    )
    far = Airspace(
        ident="R-9999",
        kind="restricted",
        center_lat=45.0,
        center_lon=-100.0,
        radius_nm=5.0,
        floor_ft=0.0,
        ceiling_ft=20000.0,
    )
    found = special_use_at(_LAT, _LON, 10000.0, [moa, restricted, far])
    idents = {a.ident for a in found}
    assert idents == {"WARRIOR-MOA", "R-4001"}
    assert "R-9999" not in idents


def test_special_use_excludes_class_airspace() -> None:
    # A plain controlled class is not "special use".
    assert special_use_at(_LAT, _LON, 2000.0, [_class_c()]) == []


# ---------------------------------------------------------------------------
# brasher_warning
# ---------------------------------------------------------------------------


def test_brasher_warning_below_min_safe_is_nonempty() -> None:
    msg = brasher_warning("N12345", altitude_ft=1000.0, min_safe_ft=2000.0)
    assert msg != ""
    assert "N12345" in msg
    assert "deviation" in msg.lower()


def test_brasher_warning_in_restricted_is_nonempty() -> None:
    msg = brasher_warning(
        "N12345", altitude_ft=8000.0, min_safe_ft=2000.0, in_restricted=True
    )
    assert msg != ""
    assert "restricted" in msg.lower()


def test_brasher_warning_empty_when_safe() -> None:
    assert (
        brasher_warning("N12345", altitude_ft=8000.0, min_safe_ft=2000.0) == ""
    )
