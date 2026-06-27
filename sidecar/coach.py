"""Deterministic student-mode readback coaching for the FlightGear AI ATC sidecar.

``coach_feedback`` turns a graded readback into a single line of coaching,
delegating entirely to :func:`sidecar.stt.grade_readback`.  No network, no
audio, no timestamps — identical inputs always produce identical output, so it
is trivial to unit-test and safe to append to the student-mode response.
"""

from __future__ import annotations

from sidecar.stt import grade_readback


def coach_feedback(expected: str, heard: str) -> str:
    """Return one line of coaching for *heard* against the *expected* clearance.

    Delegates to :func:`sidecar.stt.grade_readback`.  When the readback grades
    ``ok`` (score >= 0.8, including the vacuous empty-expected case), returns
    ``"Readback correct."``.  Otherwise returns coaching text that lists the
    expected tokens the pilot missed, e.g.
    ``"Check your readback — missing: hold, short."``.
    """
    result = grade_readback(expected, heard)
    if result.ok:
        return "Readback correct."
    missing = ", ".join(result.missing)
    return f"Check your readback — missing: {missing}."
