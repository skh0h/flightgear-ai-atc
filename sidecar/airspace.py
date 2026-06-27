"""
Phase 8 — deterministic airspace classification and special-use containment for
the FlightGear AI ATC sidecar.

Everything here is **offline and deterministic**.  An :class:`Airspace` is a
simple cylinder: a centre, a radius (nautical miles) and a floor/ceiling band
(feet).  Containment is a great-circle horizontal test (reusing
:func:`sidecar.routing.haversine_m`, ``radius_nm * 1852`` metres) combined with an
inclusive altitude band test.

- :func:`airspace_class_at` returns the *most restrictive* controlled class
  (A > B > C > D > E > G) whose cylinder contains the point, defaulting to ``"G"``
  (uncontrolled) when nothing applies.
- :func:`special_use_at` returns the MOA / restricted / alert / prohibited areas
  that contain the point.
- :func:`brasher_warning` renders the standard FAA "Brasher" notification a
  controller issues on a possible pilot deviation (too low, or inside a
  restricted area), or ``""`` when everything is nominal.

The module only imports :mod:`sidecar.routing` for the shared haversine helper, so
it never participates in an import cycle with :mod:`sidecar.main`.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidecar import routing

_M_PER_NM = 1852.0

# Controlled airspace classes, ordered most-restrictive (A) -> least (G).  Lower
# rank == more restrictive.  Kept as plain strings (not an enum) so they
# round-trip trivially through JSON / property mailboxes.
_CLASS_RANK = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "G": 5}

# Kinds that are *special-use* rather than a plain controlled-airspace class.
_SPECIAL_KINDS = {"moa", "restricted", "alert", "prohibited"}


@dataclass
class Airspace:
    """A cylinder of airspace: centre, radius (nm) and a floor/ceiling band (ft).

    ``kind`` is one of ``{class, moa, restricted, alert, prohibited}``.  For a
    plain controlled volume (``kind == "class"``) ``airspace_class`` carries the
    letter (A/B/C/D/E/G); for special-use areas it is informational only.
    """

    ident: str
    airspace_class: str = "G"
    kind: str = "class"
    center_lat: float = 0.0
    center_lon: float = 0.0
    radius_nm: float = 0.0
    floor_ft: float = 0.0
    ceiling_ft: float = 99999.0


def _contains(airspace: Airspace, lat: float, lon: float, alt_ft: float) -> bool:
    """True when ``(lat, lon, alt_ft)`` lies within ``airspace``'s cylinder.

    Horizontal test is great-circle distance vs ``radius_nm`` (converted to
    metres); vertical test is an inclusive ``floor_ft <= alt_ft <= ceiling_ft``
    band.  A non-positive radius can never contain a point.
    """
    if airspace.radius_nm <= 0.0:
        return False
    if not (airspace.floor_ft <= alt_ft <= airspace.ceiling_ft):
        return False
    dist_m = routing.haversine_m(
        lat, lon, airspace.center_lat, airspace.center_lon
    )
    return dist_m <= airspace.radius_nm * _M_PER_NM


def airspace_class_at(
    lat: float, lon: float, alt_ft: float, airspaces: list[Airspace]
) -> str:
    """Return the most-restrictive controlled class containing the point.

    Considers only ``kind == "class"`` airspaces.  Among those that contain
    ``(lat, lon, alt_ft)`` the most restrictive letter wins (A > B > C > D > E >
    G).  Defaults to ``"G"`` (uncontrolled) when nothing applies.
    """
    best_rank = _CLASS_RANK["G"]
    best_class = "G"
    for airspace in airspaces:
        if airspace.kind != "class":
            continue
        if not _contains(airspace, lat, lon, alt_ft):
            continue
        letter = (airspace.airspace_class or "G").strip().upper()
        rank = _CLASS_RANK.get(letter, _CLASS_RANK["G"])
        if rank < best_rank:
            best_rank = rank
            best_class = letter
    return best_class


def special_use_at(
    lat: float, lon: float, alt_ft: float, airspaces: list[Airspace]
) -> list[Airspace]:
    """Return the special-use areas (MOA/restricted/alert/prohibited) containing
    the point, preserving input order.
    """
    return [
        airspace
        for airspace in airspaces
        if airspace.kind in _SPECIAL_KINDS
        and _contains(airspace, lat, lon, alt_ft)
    ]


def brasher_warning(
    callsign: str,
    *,
    altitude_ft: float,
    min_safe_ft: float,
    in_restricted: bool = False,
) -> str:
    """Render an FAA "Brasher" notification, or ``""`` when nominal.

    A Brasher notification is the standard phraseology a controller uses to
    advise a pilot of a *possible pilot deviation* so the event is documented.
    It is issued here when the aircraft is below ``min_safe_ft`` OR is inside a
    restricted area.  Returns ``""`` when the flight is at/above the safe
    altitude and clear of restricted airspace.
    """
    below = altitude_ft < min_safe_ft
    if not below and not in_restricted:
        return ""

    call = callsign.strip() or "Aircraft"
    if in_restricted:
        reason = "you have entered restricted airspace"
    else:
        reason = (
            f"you are below the minimum safe altitude of {int(min_safe_ft)} feet"
        )
    return (
        f"{call}, {reason}. Possible pilot deviation, advise you contact "
        f"ATC at this time and have a number to copy."
    )
