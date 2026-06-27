"""Tests for sidecar/session_log.py — bounded recent-interaction memory."""

from __future__ import annotations

from sidecar.session_log import SessionMemory


# ---------------------------------------------------------------------------
# Empty / count
# ---------------------------------------------------------------------------


def test_empty_recent_context_is_blank() -> None:
    mem = SessionMemory()
    assert mem.recent_context() == ""
    assert mem.count == 0


def test_count_tracks_total_remembered() -> None:
    mem = SessionMemory()
    mem.remember("taxi", "UAL1", "UAL1, taxi to runway 28R.")
    mem.remember("takeoff", "DAL2", "DAL2, cleared for takeoff.")
    assert mem.count == 2


# ---------------------------------------------------------------------------
# recent_context — content & ordering (most-recent LAST)
# ---------------------------------------------------------------------------


def test_recent_context_content_and_ordering() -> None:
    mem = SessionMemory()
    mem.remember("taxi", "UAL1", "UAL1, taxi to runway 28R.")
    mem.remember("takeoff", "DAL2", "DAL2, cleared for takeoff.")
    ctx = mem.recent_context()
    lines = ctx.split("\n")
    assert lines == [
        "UAL1: taxi -> UAL1, taxi to runway 28R.",
        "DAL2: takeoff -> DAL2, cleared for takeoff.",
    ]
    # Most recent is the last line.
    assert lines[-1].startswith("DAL2")


def test_recent_context_respects_n() -> None:
    mem = SessionMemory()
    for i in range(5):
        mem.remember("taxi", f"AC{i}", f"resp{i}")
    ctx = mem.recent_context(n=2)
    lines = ctx.split("\n")
    assert lines == ["AC3: taxi -> resp3", "AC4: taxi -> resp4"]


def test_recent_context_n_zero_is_blank() -> None:
    mem = SessionMemory()
    mem.remember("taxi", "UAL1", "resp")
    assert mem.recent_context(n=0) == ""


# ---------------------------------------------------------------------------
# Bounded by max_recent
# ---------------------------------------------------------------------------


def test_bounded_by_max_recent() -> None:
    mem = SessionMemory(max_recent=3)
    for i in range(6):
        mem.remember("taxi", f"AC{i}", f"resp{i}")
    ctx = mem.recent_context(n=10)
    lines = ctx.split("\n")
    # Only the last 3 are retained; oldest dropped.
    assert lines == [
        "AC3: taxi -> resp3",
        "AC4: taxi -> resp4",
        "AC5: taxi -> resp5",
    ]
    # count still reflects the total ever remembered.
    assert mem.count == 6


def test_max_recent_default_is_eight() -> None:
    mem = SessionMemory()
    for i in range(12):
        mem.remember("taxi", f"AC{i}", f"resp{i}")
    lines = mem.recent_context(n=100).split("\n")
    assert len(lines) == 8
    assert lines[0] == "AC4: taxi -> resp4"
    assert lines[-1] == "AC11: taxi -> resp11"
