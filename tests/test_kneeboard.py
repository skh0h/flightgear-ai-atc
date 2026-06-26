"""Tests for sidecar/kneeboard.py — deterministic, offline kneeboard cards.

No network, no audio, no timestamps: ``build_kneeboard`` is a pure function of
its keyword inputs, so output is snapshot-stable.
"""

from __future__ import annotations

from sidecar.kneeboard import build_kneeboard


# ---------------------------------------------------------------------------
# Content — included when provided
# ---------------------------------------------------------------------------


def test_includes_icao_and_airport_name() -> None:
    out = build_kneeboard(icao="KJFK", airport_name="John F Kennedy Intl")
    assert "KJFK" in out
    assert "John F Kennedy Intl" in out


def test_includes_wind_when_provided() -> None:
    out = build_kneeboard(wind_dir=270, wind_kt=12)
    # Direction is zero-padded to three digits; speed carries a unit.
    assert "270" in out
    assert "12 kt" in out


def test_includes_runways_when_provided() -> None:
    out = build_kneeboard(runways=["28R", "28L"])
    assert "28R" in out
    assert "28L" in out
    assert "Active runways:" in out


def test_includes_freqs_when_provided() -> None:
    out = build_kneeboard(freqs={"Ground": "121.80", "Tower": "119.10"})
    assert "Ground" in out
    assert "121.80" in out
    assert "Tower" in out
    assert "119.10" in out


def test_includes_atis_when_provided() -> None:
    out = build_kneeboard(atis="information alpha")
    assert "information alpha" in out
    assert "ATIS:" in out


# ---------------------------------------------------------------------------
# Shape — stable, multi-line, deterministic
# ---------------------------------------------------------------------------


def test_stable_shape_sections_always_present() -> None:
    out = build_kneeboard()
    assert out.splitlines()[0] == "KNEEBOARD"
    for header in ("Airport:", "Wind:", "Active runways:", "Frequencies:", "ATIS:"):
        assert header in out


def test_is_multiline() -> None:
    out = build_kneeboard(
        icao="KSFO",
        airport_name="San Francisco Intl",
        wind_dir=280,
        wind_kt=10,
        runways=["28R"],
        freqs={"Tower": "120.50"},
        atis="information bravo",
    )
    assert "\n" in out
    assert len(out.splitlines()) >= 6


def test_deterministic_same_inputs_same_output() -> None:
    kwargs = dict(
        icao="KLAX",
        airport_name="Los Angeles Intl",
        wind_dir=250,
        wind_kt=8,
        runways=["25R", "25L"],
        freqs={"Ground": "121.65", "Tower": "120.95"},
        atis="information charlie",
    )
    assert build_kneeboard(**kwargs) == build_kneeboard(**kwargs)


def test_freqs_rendered_in_sorted_key_order() -> None:
    # Insertion order is Tower-then-Ground; output must be deterministic
    # (sorted by key) regardless of insertion order.
    out = build_kneeboard(freqs={"Tower": "119.10", "Ground": "121.80"})
    assert out.index("Ground") < out.index("Tower")


# ---------------------------------------------------------------------------
# None / empty handling — renders n/a, never raises
# ---------------------------------------------------------------------------


def test_handles_all_none() -> None:
    out = build_kneeboard(
        icao="",
        airport_name="",
        wind_dir=None,
        wind_kt=None,
        runways=None,
        atis="",
        freqs=None,
    )
    assert "Airport: n/a" in out
    assert "Wind: n/a" in out
    assert "Active runways: n/a" in out
    assert "ATIS: n/a" in out
    # Frequencies header still present with an n/a body line.
    assert "Frequencies:" in out
    assert "n/a" in out


def test_handles_partial_wind() -> None:
    out = build_kneeboard(wind_dir=270, wind_kt=None)
    assert "270" in out
    # Does not raise and still emits a Wind line.
    assert "Wind:" in out


def test_handles_only_airport_name() -> None:
    out = build_kneeboard(airport_name="Some Field")
    assert "Some Field" in out


def test_default_call_does_not_raise() -> None:
    # Fully default invocation is valid and stable.
    assert build_kneeboard() == build_kneeboard()
