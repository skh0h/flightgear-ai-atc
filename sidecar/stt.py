"""
Speech-to-text + readback grading for the FlightGear AI ATC sidecar.

Two concerns live here, both fully offline-testable:

  - :class:`WhisperBackend` — a capability-detected hook around an offline
    ``whisper`` CLI.  ``transcribe`` raises :class:`OfflineSTTError` when the
    binary is unavailable, mirroring the sidecar's offline-fallback contract.
  - :func:`grade_readback` — a deterministic token-set grader that scores how
    completely a heard readback covers the expected clearance.  No network, no
    audio: it operates purely on strings, so it is trivial to unit-test.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_log = logging.getLogger(__name__)


class STTError(Exception):
    """Base class for speech-to-text failures."""


class OfflineSTTError(STTError):
    """Raised when no speech-to-text engine is available (offline)."""


class WhisperBackend:
    """Offline speech-to-text via the ``whisper`` CLI (capability-detected)."""

    def __init__(
        self,
        whisper_bin: str = "whisper",
        runner: Callable[..., Any] = subprocess.run,
    ) -> None:
        self._whisper_bin = whisper_bin
        self._runner = runner

    @classmethod
    def available(cls, whisper_bin: str = "whisper") -> bool:
        """True when the whisper executable is resolvable on PATH."""
        return shutil.which(whisper_bin) is not None

    def transcribe(self, audio_path: str) -> str:
        """Transcribe an audio file to text.

        Raises:
            OfflineSTTError: When the whisper binary is not available.
        """
        if not self.available(self._whisper_bin):
            raise OfflineSTTError(
                f"whisper not available (looked for {self._whisper_bin!r} on PATH)"
            )
        result = self._runner(
            [self._whisper_bin, audio_path],
            check=False,
            capture_output=True,
            text=True,
        )
        return (getattr(result, "stdout", "") or "").strip()


@dataclass
class ReadbackResult:
    """Outcome of grading a pilot readback against the expected clearance."""

    ok: bool
    score: float
    missing: list[str]
    extra: list[str]


def _tokenize(text: str) -> list[str]:
    """Lowercase, alphanumeric token split (numbers + words, order-preserving)."""
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def grade_readback(expected: str, heard: str) -> ReadbackResult:
    """Grade a heard readback against the expected clearance, deterministically.

    Scoring is a token-set comparison: ``score = |expected ∩ heard| / |expected|``.
    The readback is ``ok`` when ``score >= 0.8``.  ``missing`` are expected tokens
    the pilot did not say; ``extra`` are tokens the pilot added that were not
    expected.  Both are sorted for stable output.  No network, no audio.
    """
    expected_set = set(_tokenize(expected))
    heard_set = set(_tokenize(heard))

    if not expected_set:
        # Nothing was required: a perfect (vacuous) match.
        score = 1.0
    else:
        score = len(expected_set & heard_set) / len(expected_set)

    missing = sorted(expected_set - heard_set)
    extra = sorted(heard_set - expected_set)
    return ReadbackResult(ok=score >= 0.8, score=score, missing=missing, extra=extra)
