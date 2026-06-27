"""
Phase 6 — deterministic "living world" traffic logic for the FlightGear AI ATC
sidecar.

Everything in this module is **offline and deterministic**: wake-turbulence
classification and separation, runway-intersection / LAHSO heuristics,
intersection-departure feasibility, seeded ambient chatter, and a wake-aware
departure-sequence summary.  Randomness is replaced by ``hashlib`` digests of an
explicit ``seed`` plus the (sorted) inputs, so the same arguments always yield
the same output — which is exactly what the test-suite and the replay harness
rely on.

The module deliberately *reads* the existing Phase 2 types by duck-typing
(``picture.runways``/``picture.nodes`` and ``TrafficSnapshot``-shaped objects)
and only imports :mod:`sidecar.routing` for the shared nearest-node helper, so it
never participates in an import cycle with :mod:`sidecar.main`.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from sidecar import routing

# ---------------------------------------------------------------------------
# Wake-turbulence categories
# ---------------------------------------------------------------------------

# Category strings, ordered light -> super.  Kept as plain strings (not an enum)
# so they round-trip trivially through JSON/property mailboxes.
_CATEGORY_RANK = {"light": 0, "medium": 1, "heavy": 2, "super": 3}

# ICAO RECAT-ish prefix tables (matched against an alphanumeric-normalised,
# upper-cased type/keyword string).  Order of evaluation is super -> heavy ->
# light, with an unmatched type defaulting to "medium".
_SUPER_PREFIXES = ("A388", "A380", "AN225")
_HEAVY_PREFIXES = (
    "B74", "B77", "B78", "B76",          # 747 / 777 / 787 / 767
    "A33", "A34", "A35", "A300", "A310",  # A330 / A340 / A350 / A300 / A310
    "MD11", "DC10", "IL96",
)
_LIGHT_PREFIXES = (
    # Cessna singles
    "C150", "C152", "C162", "C170", "C172", "C175", "C180", "C182", "C185",
    "C206", "C208", "C210", "C177",
    # Piper
    "PA", "P28", "P32", "P46",
    # Diamond / Robin / Cirrus / small Beech / TBM
    "DA20", "DA40", "DA42", "DA62", "DV20", "DR40", "DR60",
    "SR20", "SR22", "TBM",
    "BE19", "BE23", "BE33", "BE35", "BE36", "BE58", "BE76",
    # Gliders by type designator
    "DG", "ASK", "ASW", "LS8", "DUO",
)


def wake_category(aircraft_type: str) -> str:
    """Classify an ICAO type designator (or sim model / callsign) into a wake
    category: ``"super"`` | ``"heavy"`` | ``"medium"`` | ``"light"``.

    Recognises both type designators (``B744`` -> heavy, ``C172`` -> light) and
    spoken keywords (``"... Heavy"`` / ``"... Super"`` suffixes, ``"glider"``).
    Anything unrecognised — including the empty string — defaults to
    ``"medium"`` so callers always get a usable category.
    """
    t = (aircraft_type or "").strip().upper()
    if not t:
        return "medium"

    # Spoken keywords (callsign suffixes / model names).
    if "GLIDER" in t or "SAILPLANE" in t:
        return "light"
    if "SUPER" in t:
        return "super"
    if "HEAVY" in t:
        return "heavy"

    norm = "".join(ch for ch in t if ch.isalnum())

    if norm.startswith(_SUPER_PREFIXES):
        return "super"
    if norm.startswith(_HEAVY_PREFIXES):
        return "heavy"
    if norm.startswith(_LIGHT_PREFIXES):
        return "light"
    return "medium"


# ---------------------------------------------------------------------------
# Wake separation
# ---------------------------------------------------------------------------


@dataclass
class Separation:
    """Required extra wake-turbulence spacing behind a leading aircraft.

    ``distance_nm`` is the radar separation minimum in nautical miles and
    ``time_min`` the equivalent runway/departure spacing in minutes.  Both are
    ``0`` when no *extra* wake spacing is required for the category pair.
    """

    distance_nm: float
    time_min: float


# (lead_category, follower_category) -> (distance_nm, time_min).  Pairs absent
# from the table need no extra wake spacing (Separation(0, 0)).  Values follow
# the classic ICAO wake scheme (Super/Heavy/Medium/Light).
_WAKE_TABLE: dict[tuple[str, str], tuple[float, float]] = {
    ("super", "heavy"): (6.0, 2.0),
    ("super", "medium"): (7.0, 2.0),
    ("super", "light"): (8.0, 3.0),
    ("heavy", "heavy"): (4.0, 2.0),
    ("heavy", "medium"): (5.0, 2.0),
    ("heavy", "light"): (6.0, 3.0),
    ("medium", "light"): (5.0, 2.0),
}


def wake_separation(lead_type: str, follower_type: str) -> Separation:
    """Return the extra wake spacing required for ``follower`` behind ``lead``.

    Looks up the ICAO-ish table by wake-category pair; returns
    ``Separation(0.0, 0.0)`` when no additional spacing is needed (e.g. a light
    following a light, or any aircraft following a lighter one).
    """
    lead = wake_category(lead_type)
    follower = wake_category(follower_type)
    dist, mins = _WAKE_TABLE.get((lead, follower), (0.0, 0.0))
    return Separation(distance_nm=dist, time_min=mins)


def separation_advice(lead_type: str, follower_type: str) -> str:
    """Human wake-turbulence caution for ``follower`` behind ``lead``.

    Returns a non-empty caution (e.g. ``"Caution wake turbulence, heavy aircraft
    ahead."``) when the leading aircraft requires extra wake spacing, otherwise
    the empty string.
    """
    sep = wake_separation(lead_type, follower_type)
    if sep.distance_nm <= 0.0:
        return ""
    lead_cat = wake_category(lead_type)
    return f"Caution wake turbulence, {lead_cat} aircraft ahead."


# ---------------------------------------------------------------------------
# Runway intersection / LAHSO heuristics
# ---------------------------------------------------------------------------

# A runway pair "conflicts" for LAHSO when the absolute heading difference,
# folded into [0, 180), lands in this open-ish band: near-0 (parallel/same) and
# near-180 (reciprocal) pairs are excluded, leaving genuine crossing geometry.
_INTERSECT_MIN_DEG = 20.0
_INTERSECT_MAX_DEG = 160.0


def _runways(picture) -> list:
    """Runways with a non-empty id, sorted by id for deterministic output."""
    rwys = [r for r in getattr(picture, "runways", []) if getattr(r, "id", "")]
    return sorted(rwys, key=lambda r: str(r.id))


def intersecting_runways(picture) -> list[tuple[str, str]]:
    """Return runway-id pairs whose geometry crosses (LAHSO candidates).

    Heuristic, geometry-from-heading only: two runways are treated as
    intersecting when their heading difference (mod 180) falls between
    ~20 and ~160 degrees.  Output is deterministic — runways are sorted by id
    and each pair is emitted as ``(lower_id, higher_id)``.
    """
    rwys = _runways(picture)
    pairs: list[tuple[str, str]] = []
    for i in range(len(rwys)):
        for j in range(i + 1, len(rwys)):
            a, b = rwys[i], rwys[j]
            try:
                diff = abs(float(a.heading) - float(b.heading)) % 180.0
            except (TypeError, ValueError):
                continue
            if _INTERSECT_MIN_DEG <= diff <= _INTERSECT_MAX_DEG:
                pairs.append((str(a.id), str(b.id)))
    return pairs


def lahso_eligible(picture) -> bool:
    """True when the airport has >=2 runways and at least one crossing pair."""
    return len(_runways(picture)) >= 2 and bool(intersecting_runways(picture))


# ---------------------------------------------------------------------------
# Intersection departures
# ---------------------------------------------------------------------------

# Minimum usable runway length (metres) for a takeoff, by wake category.  These
# are deliberately coarse, conservative thresholds for a feasibility gate.
_MIN_TAKEOFF_M = {
    "light": 800.0,
    "medium": 1800.0,
    "heavy": 2500.0,
    "super": 3000.0,
}


def intersection_departure_ok(
    aircraft_type: str,
    *,
    runway_length_m: float,
    intersection_remaining_m: float,
) -> bool:
    """Whether ``aircraft_type`` can depart from a runway intersection.

    The usable distance is the runway length remaining from the intersection
    (capped at the total runway length).  An intersection departure is approved
    when that distance meets the category's minimum takeoff length — lighter
    aircraft need less, so they qualify with shorter remaining runway.
    """
    cat = wake_category(aircraft_type)
    required = _MIN_TAKEOFF_M.get(cat, _MIN_TAKEOFF_M["medium"])
    available = intersection_remaining_m
    if runway_length_m > 0:
        available = min(available, runway_length_m)
    return available >= required


# ---------------------------------------------------------------------------
# Ambient chatter (deterministic, seeded)
# ---------------------------------------------------------------------------

_CHATTER_TEMPLATES = (
    "{icao} Ground, {callsign}, request taxi.",
    "{callsign}, {icao} Ground, taxi to the active, hold short.",
    "{icao} Tower, {callsign}, holding short, ready for departure.",
    "{callsign}, {icao} Tower, line up and wait.",
    "{icao} Ground, {callsign}, with you on the ramp.",
    "{callsign}, contact Ground point niner, good day.",
    "{icao} Tower, {callsign}, traffic in sight.",
    "{callsign}, {icao} Tower, continue, expect landing clearance shortly.",
)


def _snapshot_sort_key(snap) -> tuple:
    """Stable ordering key for a traffic snapshot (callsign, node, position)."""
    callsign = (getattr(snap, "callsign", "") or "traffic")
    node = getattr(snap, "node_index", None)
    return (
        callsign,
        node if node is not None else -1,
        float(getattr(snap, "lat", 0.0) or 0.0),
        float(getattr(snap, "lon", 0.0) or 0.0),
    )


def ambient_chatter(snapshots, picture, *, seed: str, n: int = 3) -> list[str]:
    """Build up to ``n`` deterministic background-chatter lines.

    Lines are derived from the (sorted) traffic list and the airport id, with a
    template chosen by a ``hashlib`` digest of ``seed`` + callsign + airport, so
    the output is fully reproducible for a given ``seed`` and input set.  Returns
    ``[]`` when there is no traffic.
    """
    snaps = list(snapshots or [])
    if not snaps or n <= 0:
        return []
    icao = (getattr(picture, "icao", "") or "").strip() or "Approach"
    ordered = sorted(snaps, key=_snapshot_sort_key)

    lines: list[str] = []
    for snap in ordered:
        if len(lines) >= n:
            break
        callsign = (getattr(snap, "callsign", "") or "traffic").strip() or "traffic"
        digest = hashlib.sha256(f"{seed}|{callsign}|{icao}".encode("utf-8")).hexdigest()
        idx = int(digest, 16) % len(_CHATTER_TEMPLATES)
        lines.append(_CHATTER_TEMPLATES[idx].format(icao=icao, callsign=callsign))
    return lines


# ---------------------------------------------------------------------------
# Wake-aware departure sequencing
# ---------------------------------------------------------------------------


def _dist_to_runway(picture, lat: float, lon: float) -> float:
    """Distance (m) from a position to the nearest on-runway node, or +inf."""
    _idx, dist = routing.nearest_node_with_distance(
        picture, lat, lon, require_on_runway=True
    )
    return dist


def _node_coord(picture, idx: int | None) -> tuple[float, float] | None:
    if idx is None:
        return None
    for node in getattr(picture, "nodes", []):
        if node.index == idx:
            return (node.lat, node.lon)
    return None


def sequence_with_separation(
    snapshots,
    user_node_index: int | None,
    picture,
    *,
    user_type: str = "",
) -> tuple[int, str]:
    """Sequence ground traffic + the user, adding a wake note for a heavy lead.

    Mirrors :func:`sidecar.main.compute_traffic_queue` ordering (closeness to
    the nearest on-runway node, ties broken deterministically), then — when a
    heavy or super aircraft is immediately ahead of the user — appends a
    wake-turbulence caution with the expected spacing.  Returns
    ``(traffic_count, summary)``.  Fully deterministic for fixed inputs.
    """
    count = len(snapshots)

    # (dist_to_runway, is_user_flag, label, is_user, snapshot_or_None)
    participants: list[tuple[float, int, str, bool, object]] = []
    for snap in snapshots:
        label = (getattr(snap, "callsign", "") or "traffic")
        participants.append(
            (_dist_to_runway(picture, snap.lat, snap.lon), 0, label, False, snap)
        )

    user_coord = _node_coord(picture, user_node_index)
    user_dist = (
        _dist_to_runway(picture, *user_coord) if user_coord is not None else math.inf
    )
    participants.append((user_dist, 1, "You", True, None))

    participants.sort(key=lambda p: (p[0], p[1], p[2]))

    user_pos = next(i for i, p in enumerate(participants) if p[3])
    user_number = user_pos + 1
    if user_pos == 0:
        summary = f"Ground traffic: {count}. You are number 1 for departure."
        return count, summary

    ahead = participants[user_pos - 1]
    ahead_label = ahead[2]
    summary = (
        f"Ground traffic: {count}. "
        f"You are number {user_number}, behind {ahead_label}."
    )

    ahead_snap = ahead[4]
    if ahead_snap is not None:
        lead_cat = wake_category(getattr(ahead_snap, "callsign", "") or "")
        if lead_cat in ("heavy", "super"):
            sep = wake_separation(getattr(ahead_snap, "callsign", "") or "", user_type)
            note = f" Caution wake turbulence, {lead_cat} ahead"
            if sep.distance_nm > 0:
                note += f"; expect {sep.distance_nm:.0f} mile spacing"
            note += "."
            summary += note
    return count, summary
