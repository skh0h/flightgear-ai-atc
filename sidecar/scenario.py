"""
Training-scenario generation — deterministic, offline-safe.

A :class:`Scenario` is a self-contained training setup (traffic level, wind,
weather category, an optional simulated failure, and a difficulty band).
Generation is **fully deterministic**: the same ``seed`` always yields an
identical scenario, chosen from fixed pools via a hash of the seed — no
randomness, no time or network dependence.  ``scenario_summary`` renders a
single human-readable line describing the setup.

The hashing pattern mirrors :mod:`sidecar.personality`: a SHA-256 digest of the
seed is indexed at fixed byte offsets so each field varies independently while
staying reproducible.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Seeded option pools
# ---------------------------------------------------------------------------

# Weather categories (in increasing severity); "VFR" is the safe default.
_WEATHER: list[str] = ["VFR", "MVFR", "IFR"]

# Optional simulated failure.  "none" appears more than once so the common case
# (no failure) is weighted higher than any single malfunction.
_FAILURES: list[str] = [
    "none",
    "none",
    "none",
    "engine",
    "electrical",
    "vacuum",
    "flaps",
    "gear",
    "radio",
    "brakes",
]

# Difficulty bands; "normal" is the default centre of the range.
_DIFFICULTIES: list[str] = ["easy", "normal", "hard"]

# Bounds for the numeric fields.
_MAX_TRAFFIC = 8  # traffic_count is 0..8 inclusive
_MAX_WIND_KT = 25  # wind_kt is 0..25 inclusive


@dataclass
class Scenario:
    """A deterministic training scenario."""

    seed: str
    airport: str = ""
    traffic_count: int = 0
    wind_dir: int = 0
    wind_kt: int = 0
    weather: str = "VFR"
    failure: str = "none"
    difficulty: str = "normal"


def _digest(seed: str) -> bytes:
    """Return a stable SHA-256 digest for ``seed`` (empty seeds allowed)."""
    return hashlib.sha256((seed or "").encode("utf-8")).digest()


def _byte(digest: bytes, offset: int) -> int:
    """Return a single digest byte (0-255) at ``offset`` (wrapped)."""
    return digest[offset % len(digest)]


def _word(digest: bytes, offset: int) -> int:
    """Combine two digest bytes into a 0-65535 value (wrapped offsets)."""
    return (digest[offset % len(digest)] << 8) | digest[(offset + 1) % len(digest)]


def _pick(options: list[str], digest: bytes, offset: int) -> str:
    """Deterministically choose one of ``options`` using two digest bytes."""
    return options[_word(digest, offset) % len(options)]


def generate_scenario(seed: str, *, airport: str = "") -> Scenario:
    """Build a deterministic :class:`Scenario` from ``seed``.

    The same ``seed`` (and ``airport``) always returns an identical scenario.
    Traffic (0-8), wind direction (0-359), wind speed (0-25 kt), weather
    category, an optional failure, and a difficulty band are all selected from
    fixed pools/ranges by hashing the seed — there is no randomness or time
    dependence.
    """
    d = _digest(seed)
    return Scenario(
        seed=seed,
        airport=airport,
        traffic_count=_byte(d, 0) % (_MAX_TRAFFIC + 1),
        wind_dir=_word(d, 2) % 360,
        wind_kt=_byte(d, 4) % (_MAX_WIND_KT + 1),
        weather=_pick(_WEATHER, d, 6),
        failure=_pick(_FAILURES, d, 10),
        difficulty=_pick(_DIFFICULTIES, d, 14),
    )


def scenario_summary(s: Scenario) -> str:
    """Return a one-line human description of a scenario (always non-empty)."""
    where = s.airport or "the field"
    line = (
        f"Training scenario at {where}: {s.weather}, "
        f"wind {s.wind_dir:03d} at {s.wind_kt} knots, "
        f"{s.traffic_count} traffic, {s.difficulty} difficulty"
    )
    if s.failure and s.failure != "none":
        line += f", simulated {s.failure} failure"
    return line + "."
