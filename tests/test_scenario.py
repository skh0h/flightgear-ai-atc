"""Tests for sidecar/scenario.py — deterministic training-scenario generation."""

from __future__ import annotations

from sidecar.scenario import (
    Scenario,
    generate_scenario,
    scenario_summary,
)


# ---------------------------------------------------------------------------
# generate_scenario — determinism
# ---------------------------------------------------------------------------


def test_same_seed_yields_identical_scenario() -> None:
    a = generate_scenario("KJFK-1")
    b = generate_scenario("KJFK-1")
    assert a == b
    assert isinstance(a, Scenario)


def test_same_seed_and_airport_identical() -> None:
    a = generate_scenario("UAL123", airport="KJFK")
    b = generate_scenario("UAL123", airport="KJFK")
    assert a == b


def test_empty_seed_is_safe_and_deterministic() -> None:
    assert generate_scenario("") == generate_scenario("")


def test_airport_kwarg_is_respected() -> None:
    s = generate_scenario("seed", airport="KSFO")
    assert s.airport == "KSFO"
    assert s.seed == "seed"


# ---------------------------------------------------------------------------
# generate_scenario — fields in range
# ---------------------------------------------------------------------------


def test_scenario_fields_in_range_across_many_seeds() -> None:
    for i in range(200):
        s = generate_scenario(f"seed-{i}", airport="KJFK")
        assert 0 <= s.traffic_count <= 8
        assert 0 <= s.wind_dir <= 359
        assert 0 <= s.wind_kt <= 25
        assert s.weather in ("VFR", "MVFR", "IFR")
        assert s.failure in (
            "none",
            "engine",
            "electrical",
            "vacuum",
            "flaps",
            "gear",
            "radio",
            "brakes",
        )
        assert s.difficulty in ("easy", "normal", "hard")


def test_different_seeds_usually_differ() -> None:
    seeds = [f"seed-{i}" for i in range(16)]
    # Scenario is a mutable dataclass (unhashable); compare rendered summaries.
    summaries = {scenario_summary(generate_scenario(s)) for s in seeds}
    # The hashed selection should spread these out across distinct setups.
    assert len(summaries) > 1


# ---------------------------------------------------------------------------
# scenario_summary — one-line, non-empty
# ---------------------------------------------------------------------------


def test_summary_non_empty_and_mentions_airport() -> None:
    s = generate_scenario("KJFK-7", airport="KJFK")
    summary = scenario_summary(s)
    assert summary
    assert "\n" not in summary  # one line
    assert "KJFK" in summary
    assert summary.endswith(".")


def test_summary_handles_missing_airport() -> None:
    s = generate_scenario("seed")  # no airport
    summary = scenario_summary(s)
    assert summary
    assert "the field" in summary


def test_summary_mentions_failure_when_present() -> None:
    s = Scenario(seed="x", failure="engine")
    assert "engine" in scenario_summary(s)


def test_summary_omits_failure_when_none() -> None:
    s = Scenario(seed="x", failure="none")
    assert "failure" not in scenario_summary(s)
