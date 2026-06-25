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
import subprocess
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

_log = logging.getLogger(__name__)


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

    def speak(self, text: str, voice: str | None = None) -> None:
        """Queue ``text`` for speech (or speak synchronously if not started)."""
        chosen = voice or self._voice
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
