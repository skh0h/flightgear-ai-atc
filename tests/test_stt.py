"""Tests for sidecar/stt.py — deterministic readback grading + capability hooks.

No network, no audio: shutil.which / subprocess are monkeypatched so neither a
real whisper binary nor real audio is ever touched.
"""

from __future__ import annotations

from typing import Any

import pytest

from sidecar.stt import (
    OfflineSTTError,
    ReadbackResult,
    STTError,
    WhisperBackend,
    grade_readback,
)


# ---------------------------------------------------------------------------
# grade_readback — deterministic token-set grading
# ---------------------------------------------------------------------------


def test_grade_readback_exact_match_is_perfect() -> None:
    res = grade_readback("runway 28R via A B hold short 28R",
                         "runway 28R via A B hold short 28R")
    assert isinstance(res, ReadbackResult)
    assert res.ok is True
    assert res.score == 1.0
    assert res.missing == []
    assert res.extra == []


def test_grade_readback_case_and_punctuation_insensitive() -> None:
    res = grade_readback("Cleared for takeoff 28R", "cleared for takeoff 28r.")
    assert res.score == 1.0
    assert res.ok is True


def test_grade_readback_missing_tokens_lower_score_and_fail() -> None:
    # Heard drops "hold short 28r" entirely -> below the 0.8 threshold.
    res = grade_readback("runway 28R via A B hold short 28R", "runway 28R")
    assert res.ok is False
    assert res.score < 0.8
    # The dropped salient tokens are reported as missing.
    assert "hold" in res.missing
    assert "short" in res.missing
    assert "via" in res.missing


def test_grade_readback_extra_tokens_are_listed_but_dont_block_ok() -> None:
    # Everything expected is present, plus some unsolicited chatter.
    res = grade_readback("cleared for takeoff 28R",
                         "cleared for takeoff 28R with you good day")
    assert res.ok is True  # score over expected set is still 1.0
    assert res.score == 1.0
    assert "good" in res.extra
    assert "day" in res.extra
    assert res.missing == []


def test_grade_readback_threshold_boundary_is_inclusive() -> None:
    # 4 of 5 expected tokens heard == 0.8 -> ok (>= 0.8).
    res = grade_readback("alpha bravo charlie delta echo",
                         "alpha bravo charlie delta")
    assert res.score == pytest.approx(0.8)
    assert res.ok is True
    assert res.missing == ["echo"]


def test_grade_readback_empty_expected_is_vacuously_ok() -> None:
    res = grade_readback("", "anything at all")
    assert res.score == 1.0
    assert res.ok is True
    assert res.missing == []


# ---------------------------------------------------------------------------
# WhisperBackend — capability detection + offline error
# ---------------------------------------------------------------------------


def test_whisper_available_reflects_which_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sidecar.stt.shutil.which", lambda _name: "/usr/bin/whisper")
    assert WhisperBackend.available("whisper") is True


def test_whisper_available_reflects_which_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sidecar.stt.shutil.which", lambda _name: None)
    assert WhisperBackend.available("whisper") is False


def test_transcribe_raises_offline_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sidecar.stt.shutil.which", lambda _name: None)
    with pytest.raises(OfflineSTTError):
        WhisperBackend().transcribe("/tmp/whatever.wav")


def test_offline_stt_error_is_an_stt_error() -> None:
    assert issubclass(OfflineSTTError, STTError)


def test_transcribe_shells_to_whisper_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sidecar.stt.shutil.which", lambda _name: "/usr/bin/whisper")

    class _Result:
        stdout = "  runway two eight right  "

    calls: list[list[str]] = []

    def runner(args: list[str], **kwargs: Any) -> _Result:
        calls.append(args)
        return _Result()

    out = WhisperBackend(runner=runner).transcribe("/tmp/clip.wav")
    assert out == "runway two eight right"
    assert calls[0][0] == "whisper"
    assert "/tmp/clip.wav" in calls[0]
