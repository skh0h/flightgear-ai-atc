"""
Phase 7 — deterministic, advisory flight-phase state machine for the FlightGear
AI ATC sidecar.

A flight progresses through a fixed, ordered sequence of phases (preflight ->
clearance -> pushback -> ... -> parked).  This module turns the pilot's request
tokens (the same ``clearance_type`` / request vocabulary used by
:mod:`sidecar.phraseology`) into a best-effort estimate of *where in the flight*
the aircraft currently is, so the rest of the sidecar can colour its responses
with phase context and publish ``/ai-atc/flight-phase`` for the Nasal side.

Design rules (all deliberate):

* **Advisory, never authoritative.**  :meth:`FlightStateMachine.on_request` never
  rejects, never raises, and never regresses the phase — it only nudges the
  machine *forward* when a request maps to a later phase, and it *always* returns
  the current phase.  A pilot who asks for a taxi clearance after takeoff simply
  gets the current (later) phase back; the request is still handled elsewhere.
* **Deterministic & offline.**  No randomness, no I/O.  The same inputs always
  yield the same phase, which is exactly what the test-suite and replay harness
  rely on.
* **Pure strings.**  Phases are plain strings (not an enum) so they round-trip
  trivially through the JSON / telnet property mailbox.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Phase constants + canonical ordering
# ---------------------------------------------------------------------------

PREFLIGHT = "preflight"
CLEARANCE = "clearance"
PUSHBACK = "pushback"
TAXI_OUT = "taxi_out"
TAKEOFF = "takeoff"
DEPARTURE = "departure"
CLIMB = "climb"
CRUISE = "cruise"
DESCENT = "descent"
ARRIVAL = "arrival"
APPROACH = "approach"
LANDING = "landing"
TAXI_IN = "taxi_in"
PARKED = "parked"

#: Canonical, monotonically-ordered list of flight phases (gate to gate).
PHASES = [
    PREFLIGHT,
    CLEARANCE,
    PUSHBACK,
    TAXI_OUT,
    TAKEOFF,
    DEPARTURE,
    CLIMB,
    CRUISE,
    DESCENT,
    ARRIVAL,
    APPROACH,
    LANDING,
    TAXI_IN,
    PARKED,
]

#: Fast index lookup, phase string -> position in :data:`PHASES`.
_PHASE_INDEX = {phase: i for i, phase in enumerate(PHASES)}


# ---------------------------------------------------------------------------
# Request-token -> phase mapping
# ---------------------------------------------------------------------------

# Maps a pilot request / clearance token to the flight phase it implies.  Any
# token NOT present here (cancel, readback, radio_check, the squawk-emergencies,
# flow_control, ...) is "non-phase" and yields ``None`` from
# :func:`phase_for_request` — it does not move the state machine.
_REQUEST_PHASE: dict[str, str] = {
    # --- pre-departure ---
    "ifr_clearance": CLEARANCE,
    "clearance": CLEARANCE,
    "pdc": CLEARANCE,
    "pushback": PUSHBACK,
    "taxi": TAXI_OUT,
    "taxi_out": TAXI_OUT,
    # --- departure ---
    "takeoff": TAKEOFF,
    "intersection_departure": TAKEOFF,
    "lineup": TAKEOFF,
    "departure": DEPARTURE,
    "climb": CLIMB,
    "cruise": CRUISE,
    # --- arrival ---
    "descent": DESCENT,
    "descend": DESCENT,
    "holding": DESCENT,
    "airfield_in_sight": ARRIVAL,
    "arrival": ARRIVAL,
    "approach": APPROACH,
    "ils": APPROACH,
    "expect_approach": APPROACH,
    "arrival_clearance": APPROACH,
    # --- landing & after ---
    "landing": LANDING,
    "lahso": LANDING,
    "taxi_in": TAXI_IN,
    "parked": PARKED,
    "shutdown": PARKED,
}


def phase_for_request(req_type: str) -> str | None:
    """Return the flight phase implied by a request token, or ``None``.

    The lookup is case-insensitive and tolerant of surrounding whitespace.
    Non-phase tokens — cancel, readback, radio_check, the emergency / squawk
    calls, flow_control, and anything unrecognised — return ``None``.

    Args:
        req_type: A request / clearance token (e.g. ``"taxi"``, ``"ils"``).

    Returns:
        The mapped phase string from :data:`PHASES`, or ``None`` when the token
        does not correspond to a flight phase.
    """
    if not req_type:
        return None
    return _REQUEST_PHASE.get(req_type.strip().lower())


# ---------------------------------------------------------------------------
# The state machine
# ---------------------------------------------------------------------------


class FlightStateMachine:
    """Advisory, forward-only flight-phase tracker.

    The machine starts at ``start`` (default :data:`PREFLIGHT`) and only ever
    advances toward :data:`PARKED`.  It never regresses and never raises on a
    pilot request — see the module docstring for the rationale.
    """

    def __init__(self, start: str = PREFLIGHT) -> None:
        # Fall back to PREFLIGHT if handed a bogus start so the machine is always
        # in a valid, known phase (advisory => degrade gracefully, never raise).
        self._start = start if start in _PHASE_INDEX else PREFLIGHT
        self._phase = self._start

    @property
    def phase(self) -> str:
        """The current flight phase (a member of :data:`PHASES`)."""
        return self._phase

    def can_advance(self, target: str) -> bool:
        """Return ``True`` iff ``target`` is a valid phase at/after the current one.

        Equality is allowed (advancing to the current phase is a no-op success);
        an unknown ``target`` returns ``False``.
        """
        ti = _PHASE_INDEX.get(target)
        if ti is None:
            return False
        ci = _PHASE_INDEX.get(self._phase, -1)
        return ti >= ci

    def advance_to(self, target: str) -> bool:
        """Advance to ``target`` when permitted; return whether the move happened.

        Returns ``False`` (and leaves the phase unchanged) for an unknown target
        or an attempt to regress to an earlier phase.
        """
        if self.can_advance(target):
            self._phase = target
            return True
        return False

    def on_request(self, req_type: str) -> str:
        """Fold a pilot request into the machine and return the current phase.

        This is the advisory entry point: it advances the phase *only* when the
        request maps to a later phase, never regresses, never rejects, and never
        raises.  It ALWAYS returns the (possibly updated) current phase.
        """
        try:
            mapped = phase_for_request(req_type)
            if mapped is not None and self.can_advance(mapped):
                self.advance_to(mapped)
        except Exception:  # pragma: no cover - advisory: never break the caller
            pass
        return self._phase

    def reset(self) -> None:
        """Reset the machine to its original starting phase."""
        self._phase = self._start

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return f"FlightStateMachine(phase={self._phase!r})"
