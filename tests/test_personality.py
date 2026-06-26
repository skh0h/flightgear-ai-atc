"""Tests for sidecar/personality.py — deterministic persona + mood helpers."""

from __future__ import annotations

from sidecar.personality import (
    ControllerPersona,
    generate_persona,
    is_quiet_night,
    mood_for,
)


# ---------------------------------------------------------------------------
# generate_persona — determinism
# ---------------------------------------------------------------------------


def test_same_seed_yields_identical_persona() -> None:
    a = generate_persona("UAL123")
    b = generate_persona("UAL123")
    assert a == b
    assert isinstance(a, ControllerPersona)


def test_persona_fields_are_populated() -> None:
    p = generate_persona("KJFK-tower")
    assert p.name
    assert p.position == "Tower"
    assert p.style
    assert p.backstory
    assert p.accent


def test_position_kwarg_is_respected() -> None:
    p = generate_persona("seed", position="Ground")
    assert p.position == "Ground"


def test_empty_seed_is_safe_and_deterministic() -> None:
    assert generate_persona("") == generate_persona("")


def test_different_seeds_usually_differ() -> None:
    seeds = ["UAL123", "DAL2", "SWA45", "N12", "BAW7", "AFR9", "KLM3", "QFA1"]
    names = {generate_persona(s).name for s in seeds}
    # The hashed selection should spread these out across the name pool.
    assert len(names) > 1


# ---------------------------------------------------------------------------
# mood_for — thresholds
# ---------------------------------------------------------------------------


def test_mood_fresh_band() -> None:
    assert mood_for(0) == "fresh"
    assert mood_for(3) == "fresh"


def test_mood_brisk_band() -> None:
    assert mood_for(4) == "brisk"
    assert mood_for(9) == "brisk"


def test_mood_tired_band() -> None:
    assert mood_for(10) == "tired"
    assert mood_for(19) == "tired"


def test_mood_weary_band() -> None:
    assert mood_for(20) == "weary"
    assert mood_for(100) == "weary"


def test_mood_quiet_night_overrides_to_reflective() -> None:
    assert mood_for(0, quiet_night=True) == "reflective"
    assert mood_for(50, quiet_night=True) == "reflective"


# ---------------------------------------------------------------------------
# is_quiet_night — boundaries
# ---------------------------------------------------------------------------


def test_is_quiet_night_boundaries() -> None:
    assert is_quiet_night(22) is False
    assert is_quiet_night(23) is True
    assert is_quiet_night(0) is True
    assert is_quiet_night(4) is True
    assert is_quiet_night(5) is False
    assert is_quiet_night(12) is False
