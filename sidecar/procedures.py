"""
Phase 7 — deterministic IFR procedure helpers for the FlightGear AI ATC sidecar.

Everything in this module is **offline and deterministic**: holding-pattern entry
determination (the classic AIM sector method), CRAFT clearance assembly, EDCT /
flow-control slot arithmetic, and DME-arc phrasing.  No network, no clocks, no
randomness — the same arguments always produce the same output, which is what the
test-suite and the replay harness rely on.

CIFP / navdata (fixes, navaids, published holds) are expected to be supplied by
the caller (the Nasal side via the property mailbox, or test fixtures); nothing is
bundled here.  The :class:`Navaid` dataclass is the lightweight shape used to pass
that data around.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Navaid
# ---------------------------------------------------------------------------


@dataclass
class Navaid:
    """A navigation aid / fix as supplied by CIFP/navdata or a test fixture.

    Only ``ident`` is required; everything else defaults to an empty/zero value
    so partially-known fixes (e.g. a named intersection with no frequency) still
    round-trip cleanly through the property mailbox.
    """

    ident: str
    kind: str = ""
    freq: str = ""
    lat: float = 0.0
    lon: float = 0.0
    radial: float = 0.0


# ---------------------------------------------------------------------------
# Holding-pattern entry (classic AIM sector method)
# ---------------------------------------------------------------------------

# Sector boundaries, measured clockwise from the inbound holding course toward
# the holding side.  For a STANDARD (right-turn) pattern the holding side is the
# right of the inbound course, so "clockwise from the inbound course" sweeps the
# protected side first:
#
#   * Direct   — 180 deg sector on the holding side  (0   <= d < 180)
#   * Teardrop —  70 deg sector adjacent to outbound  (180 <= d < 250)
#   * Parallel — 110 deg sector adjacent to inbound    (250 <= d < 360)
#
# 180 + 70 + 110 = 360.  For a LEFT (non-standard) pattern the geometry is a
# mirror image, so we simply reflect the angle (``d -> 360 - d``) and reuse the
# same thresholds.
_TEARDROP_START = 180.0
_PARALLEL_START = 250.0


def holding_entry(
    inbound_heading: float,
    holding_course: float,
    *,
    turn: str = "right",
) -> str:
    """Determine the AIM holding-pattern entry: ``"direct"`` | ``"teardrop"`` |
    ``"parallel"``.

    ``inbound_heading`` is the magnetic heading the aircraft is flying as it
    approaches the holding fix; ``holding_course`` is the published inbound
    course (the heading flown *to* the fix once established in the hold).
    ``turn`` selects the pattern direction — ``"right"`` (standard) or
    ``"left"`` (non-standard); only the first letter is significant and case is
    ignored.

    Deterministic and pure: depends only on the two angles and the turn
    direction.
    """
    # Angle from the inbound course to the aircraft heading, measured clockwise
    # (toward the holding side for a standard / right-turn pattern).
    d = (float(inbound_heading) - float(holding_course)) % 360.0

    # Non-standard (left) patterns are the mirror image: reflect the angle so the
    # same sector thresholds apply.
    if str(turn).strip().lower().startswith("l"):
        d = (-d) % 360.0

    if d < _TEARDROP_START:
        return "direct"
    if d < _PARALLEL_START:
        return "teardrop"
    return "parallel"


# ---------------------------------------------------------------------------
# CRAFT IFR clearance
# ---------------------------------------------------------------------------


@dataclass
class CraftClearance:
    """A CRAFT IFR clearance (Cleared-limit, Route, Altitude, Frequency, Transponder).

    The five fields map directly onto the five lines of a read-back-able IFR
    clearance.  :meth:`as_phrase` renders them into a single spoken clearance.
    """

    cleared_limit: str
    route: str
    altitude: str
    departure_freq: str
    squawk: str

    def as_phrase(self, callsign: str) -> str:
        """Render a complete, read-back-able IFR clearance for ``callsign``."""
        return (
            f"{callsign}, cleared to {self.cleared_limit} via {self.route}, "
            f"climb maintain {self.altitude}, departure {self.departure_freq}, "
            f"squawk {self.squawk}."
        )


def build_craft_clearance(
    callsign: str,
    *,
    destination: str = "",
    route: str = "",
    altitude: str = "",
    departure_freq: str = "",
    squawk: str = "",
) -> CraftClearance:
    """Assemble a :class:`CraftClearance` from mailbox / request fields.

    The ``destination`` becomes the cleared limit.  ``callsign`` is accepted for
    call-site symmetry (the caller already knows who the clearance is for and
    supplies it again to :meth:`CraftClearance.as_phrase`); it is not stored on
    the clearance itself.
    """
    return CraftClearance(
        cleared_limit=destination,
        route=route,
        altitude=altitude,
        departure_freq=departure_freq,
        squawk=squawk,
    )


# ---------------------------------------------------------------------------
# EDCT / flow-control slot arithmetic
# ---------------------------------------------------------------------------

# Half-width (minutes) of the EDCT wheels-up compliance window (the standard
# -5 / +5 minute tolerance around the assigned Expect-Departure-Clearance-Time).
_EDCT_WINDOW_HALF_MIN = 5


def _hhmmz(minute_of_day: int) -> str:
    """Format a minute-of-day (already reduced mod 1440) as ``HH:MMZ``."""
    m = int(minute_of_day) % 1440
    return f"{m // 60:02d}:{m % 60:02d}Z"


def assign_edct(now_minute_of_day: int, slot_offset_min: int) -> str:
    """Assign an EDCT wheels-up window ``"HH:MMZ-HH:MMZ"``.

    The EDCT is ``now + slot_offset`` minutes (reduced modulo 1440 so it wraps
    cleanly past midnight); the returned window spans the standard -5 / +5 minute
    compliance tolerance around it.  Pure arithmetic — fully deterministic.
    """
    edct = (int(now_minute_of_day) + int(slot_offset_min)) % 1440
    start = (edct - _EDCT_WINDOW_HALF_MIN) % 1440
    end = (edct + _EDCT_WINDOW_HALF_MIN) % 1440
    return f"{_hhmmz(start)}-{_hhmmz(end)}"


# ---------------------------------------------------------------------------
# DME arc phrasing
# ---------------------------------------------------------------------------


def _fmt_num(value: float) -> str:
    """Render a distance with no trailing ``.0`` (``15.0 -> "15"``)."""
    return f"{float(value):g}"


def dme_arc_instruction(navaid_ident: str, arc_dme: float, direction: str) -> str:
    """Phrase a DME-arc clearance, e.g. ``"Fly the 15 DME arc clockwise of ABC."``."""
    ident = (navaid_ident or "").strip().upper()
    return f"Fly the {_fmt_num(arc_dme)} DME arc {direction} of {ident}."
