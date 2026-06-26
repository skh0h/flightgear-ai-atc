"""
Career / progression tracking — deterministic, offline-safe.

:class:`CareerStats` is a small tally of a pilot's flying record.  Points are a
pure function of the tallies (recomputed on every :func:`record_event`), so the
score can never drift out of sync with the counts.  :func:`career_rank` maps a
point total to a rank band, and :func:`load_career`/:func:`save_career` persist
the stats as JSON (a missing file simply yields a fresh record).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields, replace
from os import PathLike

# Per-counter point weights.  Negative weights penalise unsafe outcomes.
_POINTS = {
    "flights": 5,
    "landings": 10,
    "readbacks_correct": 2,
    "incidents": -20,
    "violations": -15,
    # readbacks_total is a denominator only; it carries no points.
    "readbacks_total": 0,
}

# Maps a record_event() event name to the CareerStats counter it increments.
_EVENT_FIELDS = {
    "flight": "flights",
    "landing": "landings",
    "incident": "incidents",
    "violation": "violations",
    "readback_correct": "readbacks_correct",
    "readback_total": "readbacks_total",
}


@dataclass
class CareerStats:
    """A pilot's cumulative flying record."""

    flights: int = 0
    landings: int = 0
    incidents: int = 0
    violations: int = 0
    readbacks_correct: int = 0
    readbacks_total: int = 0
    points: int = 0


def _recompute_points(stats: CareerStats) -> int:
    """Return the point total implied by ``stats``'s counters."""
    return (
        stats.flights * _POINTS["flights"]
        + stats.landings * _POINTS["landings"]
        + stats.readbacks_correct * _POINTS["readbacks_correct"]
        + stats.incidents * _POINTS["incidents"]
        + stats.violations * _POINTS["violations"]
    )


def record_event(stats: CareerStats, event: str) -> CareerStats:
    """Return a copy of ``stats`` with ``event`` recorded and points recomputed.

    ``event`` is one of ``flight``, ``landing``, ``incident``, ``violation``,
    ``readback_correct``, ``readback_total``.  An unknown event leaves the
    counters unchanged (points are still recomputed) so callers never need to
    guard the call.  The input ``stats`` is never mutated.
    """
    field = _EVENT_FIELDS.get(event)
    if field is None:
        new = replace(stats)
    else:
        new = replace(stats, **{field: getattr(stats, field) + 1})
    return replace(new, points=_recompute_points(new))


def career_rank(points: int) -> str:
    """Map a point total to a rank band.

    Thresholds: ``Student`` (< 100), ``Private`` (100-499),
    ``Commercial`` (500-999), ``ATP`` (>= 1000).
    """
    if points >= 1000:
        return "ATP"
    if points >= 500:
        return "Commercial"
    if points >= 100:
        return "Private"
    return "Student"


def load_career(path: str | PathLike[str]) -> CareerStats:
    """Load :class:`CareerStats` from a JSON file; missing/invalid -> fresh."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return CareerStats()
    if not isinstance(data, dict):
        return CareerStats()
    known = {f.name for f in fields(CareerStats)}
    return CareerStats(**{k: v for k, v in data.items() if k in known})


def save_career(stats: CareerStats, path: str | PathLike[str]) -> None:
    """Persist :class:`CareerStats` to ``path`` as JSON."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(asdict(stats), fh)
