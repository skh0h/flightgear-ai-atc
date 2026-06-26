"""Tests for sidecar/guardrail.py — deterministic clearance validation."""

from __future__ import annotations

from sidecar.guardrail import ValidationResult, validate_clearance


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_takeoff_clearance_is_ok() -> None:
    result = validate_clearance(
        "UAL123, runway 28R, cleared for takeoff.",
        callsign="UAL123",
        active_runways=["28R"],
    )
    assert isinstance(result, ValidationResult)
    assert result.ok
    assert result.issues == []


def test_ok_equals_no_issues() -> None:
    result = validate_clearance("N12, taxi to runway 19.", callsign="N12")
    assert result.ok == (not result.issues)


# ---------------------------------------------------------------------------
# Empty
# ---------------------------------------------------------------------------


def test_empty_text_is_not_ok() -> None:
    result = validate_clearance("")
    assert not result.ok
    assert result.issues


def test_empty_text_ok_when_allow_empty() -> None:
    result = validate_clearance("   ", allow_empty=True)
    assert result.ok
    assert result.issues == []


# ---------------------------------------------------------------------------
# Callsign
# ---------------------------------------------------------------------------


def test_missing_callsign_is_flagged() -> None:
    result = validate_clearance(
        "Runway 28R, cleared for takeoff.",
        callsign="UAL123",
        active_runways=["28R"],
    )
    assert not result.ok
    assert any("UAL123" in issue for issue in result.issues)


# ---------------------------------------------------------------------------
# Active-runway check (takeoff/landing only)
# ---------------------------------------------------------------------------


def test_takeoff_to_non_active_runway_is_flagged() -> None:
    result = validate_clearance(
        "UAL123, runway 9, cleared for takeoff.",
        callsign="UAL123",
        active_runways=["28R"],
    )
    assert not result.ok
    assert any("9" in issue for issue in result.issues)


def test_non_active_runway_not_flagged_for_taxi() -> None:
    # A taxi clearance mentioning a non-active runway must NOT be flagged —
    # the active-runway rule only applies to takeoff/landing clearances.
    result = validate_clearance(
        "UAL123, taxi to runway 9 via A.",
        callsign="UAL123",
        active_runways=["28R"],
    )
    assert result.ok
    assert result.issues == []


# ---------------------------------------------------------------------------
# Takeoff + hold-short contradiction
# ---------------------------------------------------------------------------


def test_takeoff_and_hold_short_same_runway_is_contradiction() -> None:
    result = validate_clearance(
        "UAL9, cleared for takeoff runway 9, hold short runway 9.",
        callsign="UAL9",
    )
    assert not result.ok
    assert any("contradiction" in issue.lower() for issue in result.issues)


def test_taxi_hold_short_different_runway_is_ok() -> None:
    result = validate_clearance(
        "UAL123, taxi to runway 28R via A, B, hold short of runway 4L.",
        callsign="UAL123",
    )
    assert result.ok
    assert result.issues == []
