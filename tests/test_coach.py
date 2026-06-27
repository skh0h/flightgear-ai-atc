"""Tests for sidecar/coach.py — deterministic readback coaching.

No network, no audio: ``coach_feedback`` delegates to the pure
``sidecar.stt.grade_readback`` token grader, so output is fully deterministic.
"""

from __future__ import annotations

from sidecar.coach import coach_feedback
from sidecar.stt import grade_readback


def test_correct_readback_returns_exact_phrase() -> None:
    out = coach_feedback(
        "runway 28R via A B hold short 28R",
        "runway 28R via A B hold short 28R",
    )
    assert out == "Readback correct."


def test_case_and_punctuation_insensitive_still_correct() -> None:
    # grade_readback is case/punctuation insensitive; coaching inherits that.
    out = coach_feedback("Cleared for takeoff 28R", "cleared for takeoff 28r.")
    assert out == "Readback correct."


def test_extra_chatter_still_correct() -> None:
    # Extra tokens never drop the score below the ok threshold.
    out = coach_feedback(
        "cleared for takeoff 28R",
        "cleared for takeoff 28R with you good day",
    )
    assert out == "Readback correct."


def test_empty_expected_is_vacuously_correct() -> None:
    assert coach_feedback("", "anything at all") == "Readback correct."


def test_missing_tokens_produce_coaching_text() -> None:
    out = coach_feedback("runway 28R via A B hold short 28R", "runway 28R")
    assert out.startswith("Check your readback — missing: ")
    # The dropped salient tokens are listed in the coaching text.
    assert "hold" in out
    assert "short" in out
    assert "via" in out


def test_coaching_text_lists_grade_readback_missing_tokens() -> None:
    expected = "alpha bravo charlie delta echo"
    heard = "alpha bravo"
    out = coach_feedback(expected, heard)
    # The listed tokens are exactly grade_readback's (sorted) missing set.
    result = grade_readback(expected, heard)
    assert result.ok is False
    expected_line = "Check your readback — missing: " + ", ".join(result.missing) + "."
    assert out == expected_line


def test_deterministic_same_inputs_same_output() -> None:
    a = coach_feedback("alpha bravo charlie", "alpha")
    b = coach_feedback("alpha bravo charlie", "alpha")
    assert a == b
