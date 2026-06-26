"""Tests for sidecar/career.py — career stats, points, ranks, JSON persistence."""

from __future__ import annotations

from pathlib import Path

from sidecar.career import (
    CareerStats,
    career_rank,
    load_career,
    record_event,
    save_career,
)


# ---------------------------------------------------------------------------
# record_event — counts + points
# ---------------------------------------------------------------------------


def test_record_event_increments_counter_and_returns_copy() -> None:
    stats = CareerStats()
    updated = record_event(stats, "landing")
    assert updated.landings == 1
    assert stats.landings == 0  # original is not mutated
    assert updated is not stats


def test_record_event_recomputes_points() -> None:
    stats = CareerStats()
    stats = record_event(stats, "landing")  # +10
    assert stats.points == 10
    stats = record_event(stats, "readback_correct")  # +2
    assert stats.points == 12
    stats = record_event(stats, "incident")  # -20
    assert stats.points == -8
    stats = record_event(stats, "violation")  # -15
    assert stats.points == -23
    stats = record_event(stats, "flight")  # +5
    assert stats.points == -18


def test_record_event_readback_total_is_counted_without_points() -> None:
    stats = record_event(CareerStats(), "readback_total")
    assert stats.readbacks_total == 1
    assert stats.points == 0


def test_record_event_unknown_event_is_noop_copy() -> None:
    stats = CareerStats(landings=2, points=20)
    updated = record_event(stats, "bogus")
    assert updated.landings == 2
    assert updated.points == 20  # recomputed from existing counters
    assert updated is not stats


def test_points_are_pure_function_of_counters() -> None:
    stats = CareerStats(
        flights=2, landings=3, incidents=1, violations=1, readbacks_correct=4
    )
    # Recompute by recording an unknown event (forces _recompute_points).
    recomputed = record_event(stats, "noop")
    # 2*5 + 3*10 + 4*2 - 1*20 - 1*15 = 10 + 30 + 8 - 20 - 15 = 13
    assert recomputed.points == 13


# ---------------------------------------------------------------------------
# career_rank — thresholds
# ---------------------------------------------------------------------------


def test_career_rank_thresholds() -> None:
    assert career_rank(0) == "Student"
    assert career_rank(99) == "Student"
    assert career_rank(100) == "Private"
    assert career_rank(499) == "Private"
    assert career_rank(500) == "Commercial"
    assert career_rank(999) == "Commercial"
    assert career_rank(1000) == "ATP"
    assert career_rank(5000) == "ATP"


def test_career_rank_negative_is_student() -> None:
    assert career_rank(-50) == "Student"


# ---------------------------------------------------------------------------
# save/load — JSON round-trip
# ---------------------------------------------------------------------------


def test_save_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "career.json"
    stats = CareerStats(
        flights=5,
        landings=4,
        incidents=1,
        violations=2,
        readbacks_correct=7,
        readbacks_total=9,
        points=42,
    )
    save_career(stats, path)
    loaded = load_career(path)
    assert loaded == stats


def test_load_missing_file_returns_fresh(tmp_path: Path) -> None:
    loaded = load_career(tmp_path / "does-not-exist.json")
    assert loaded == CareerStats()


def test_load_ignores_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "career.json"
    path.write_text('{"landings": 3, "points": 30, "unknown": 99}')
    loaded = load_career(path)
    assert loaded.landings == 3
    assert loaded.points == 30


def test_load_invalid_json_returns_fresh(tmp_path: Path) -> None:
    path = tmp_path / "career.json"
    path.write_text("not valid json {{{")
    assert load_career(path) == CareerStats()


def test_save_then_record_then_save_persists(tmp_path: Path) -> None:
    path = tmp_path / "career.json"
    save_career(CareerStats(), path)
    stats = load_career(path)
    stats = record_event(stats, "landing")
    save_career(stats, path)
    reloaded = load_career(path)
    assert reloaded.landings == 1
    assert reloaded.points == 10
