"""
Text-to-speech output with a pluggable backend and a non-blocking queue.

The default backend shells out to macOS ``say``.  Speech is processed on a
background worker thread so a long clearance never blocks the event loop.  The
backend is an ABC so alternative engines (pyttsx3, ElevenLabs, …) can be
swapped in, and the ``subprocess`` runner is injectable for testing (no audio
is emitted in tests).
"""

from __future__ import annotations

import logging
import queue
import shutil
import subprocess
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sidecar.config import Settings

_log = logging.getLogger(__name__)


# Deterministic, distinct macOS ``say`` voices per controller role.  Unknown
# roles fall back to "Alex" (the project-wide default voice).
_ROLE_VOICES = {
    "ground": "Fred",
    "tower": "Daniel",
    "approach": "Samantha",
    "departure": "Karen",
    "atis": "Tom",
}
_DEFAULT_VOICE = "Alex"


def voice_for(role: str) -> str:
    """Return a deterministic, distinct macOS voice name for a controller role.

    ``role`` is one of {ground, tower, approach, departure, atis}.  Any other
    value (including ``None``/empty) maps to the default voice "Alex".
    """
    return _ROLE_VOICES.get((role or "").strip().lower(), _DEFAULT_VOICE)


def apply_radio_static(text_or_marker: Any, enabled: bool) -> Any:
    """Interface hook for radio-static colouring of an utterance.

    This is intentionally a passthrough: real static is a runtime audio-DSP
    concern (applied to the synthesized waveform), not something that belongs in
    the deterministic, offline-testable text path.  The hook exists so callers
    can route every utterance through a single, stable seam; when ``enabled`` is
    False (the default) it is a strict no-op.
    """
    return text_or_marker


class TTSBackend(ABC):
    """Speaks a single utterance synchronously."""

    @abstractmethod
    def say(self, text: str, voice: str) -> None: ...


class SayBackend(TTSBackend):
    """macOS ``say`` backend: ``say -v <voice> <text>``."""

    def __init__(self, runner: Callable[..., Any] = subprocess.run) -> None:
        self._runner = runner

    def say(self, text: str, voice: str) -> None:
        self._runner(["say", "-v", voice, text], check=False)


class PiperBackend(TTSBackend):
    """Offline neural TTS backend that shells out to ``piper``.

    Capability-detected via :meth:`available` (``shutil.which``).  ``say`` is
    best-effort: piper is fed the text on stdin and any failure is swallowed so
    a missing binary or a bad model never breaks the speak loop.
    """

    def __init__(
        self,
        piper_bin: str = "piper",
        voice: str = "",
        runner: Callable[..., Any] = subprocess.run,
    ) -> None:
        self._piper_bin = piper_bin
        self._voice = voice
        self._runner = runner

    @classmethod
    def available(cls, piper_bin: str = "piper") -> bool:
        """True when the piper executable is resolvable on PATH."""
        return shutil.which(piper_bin) is not None

    def say(self, text: str, voice: str = "") -> None:  # noqa: ARG002 (voice unused)
        cmd = [self._piper_bin]
        if self._voice:
            cmd += ["--model", self._voice]
        try:
            self._runner(cmd, input=text.encode("utf-8"), check=False)
        except Exception:  # best-effort: never break the worker on a TTS failure
            _log.exception("piper backend failed for: %r", text)


def make_tts_backend(settings: "Settings") -> TTSBackend:
    """Select a TTS backend from settings, with graceful fallback.

    Returns a :class:`PiperBackend` only when ``tts_engine == "piper"`` *and*
    piper is actually installed; otherwise returns the macOS :class:`SayBackend`.
    """
    engine = getattr(settings, "tts_engine", "say")
    piper_bin = getattr(settings, "piper_bin", "piper")
    if engine == "piper" and PiperBackend.available(piper_bin):
        return PiperBackend(piper_bin=piper_bin, voice=getattr(settings, "piper_voice", ""))
    return SayBackend()


class TTS:
    """Queued speech dispatcher.

    Without :meth:`start`, :meth:`speak` runs synchronously (handy for tests).
    After :meth:`start`, utterances are queued and spoken on a daemon thread.
    """

    def __init__(self, voice: str = "Alex", backend: TTSBackend | None = None) -> None:
        self._voice = voice
        self._backend = backend or SayBackend()
        self._queue: queue.Queue[tuple[str, str] | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._running = False
        self._muted = False

    def set_muted(self, flag: bool) -> None:
        """Silence or un-silence future utterances.  Any utterance already
        playing is allowed to finish; this only guards new calls to speak()."""
        self._muted = bool(flag)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._worker, name="tts-worker", daemon=True
        )
        self._thread.start()

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:  # shutdown sentinel
                    return
                text, voice = item
                try:
                    self._backend.say(text, voice)
                except Exception:  # never let a backend error kill the worker
                    _log.exception("TTS backend failed for: %r", text)
            finally:
                self._queue.task_done()

    def speak(
        self, text: str, voice: str | None = None, *, role: str | None = None
    ) -> None:
        """Queue ``text`` for speech (or speak synchronously if not started).

        An explicit ``voice`` always wins.  Otherwise an optional ``role`` (one
        of {ground, tower, approach, departure, atis}) selects a distinct voice
        via :func:`voice_for`.  With neither, the instance default voice is used
        — so the legacy ``speak(text)`` behaviour is preserved byte-for-byte.
        """
        if self._muted:
            return
        if voice is not None:
            chosen = voice
        elif role is not None:
            chosen = voice_for(role)
        else:
            chosen = self._voice
        if self._running:
            self._queue.put((text, chosen))
        else:
            self._backend.say(text, chosen)

    def wait(self) -> None:
        """Block until all queued utterances have been spoken."""
        self._queue.join()

    def stop(self) -> None:
        """Stop the worker thread, draining any in-flight utterance."""
        if not self._running:
            return
        self._running = False
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def __enter__(self) -> "TTS":
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()
