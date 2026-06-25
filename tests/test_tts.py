"""Tests for sidecar/tts.py — mock subprocess runner, no real audio."""

from __future__ import annotations

from typing import Any

from sidecar.tts import SayBackend, TTS, TTSBackend


class _RecordingBackend(TTSBackend):
    def __init__(self) -> None:
        self.said: list[tuple[str, str]] = []

    def say(self, text: str, voice: str) -> None:
        self.said.append((text, voice))


def test_say_backend_builds_correct_argv() -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def runner(args: list[str], **kwargs: Any) -> None:
        calls.append((args, kwargs))

    SayBackend(runner=runner).say("Taxi to runway 28R", "Samantha")

    assert calls[0][0] == ["say", "-v", "Samantha", "Taxi to runway 28R"]
    assert calls[0][1].get("check") is False


def test_tts_speaks_synchronously_when_not_started() -> None:
    backend = _RecordingBackend()
    TTS(voice="Alex", backend=backend).speak("hello")
    assert backend.said == [("hello", "Alex")]


def test_tts_voice_override() -> None:
    backend = _RecordingBackend()
    TTS(voice="Alex", backend=backend).speak("hi", voice="Daniel")
    assert backend.said == [("hi", "Daniel")]


def test_tts_queued_delivery() -> None:
    backend = _RecordingBackend()
    tts = TTS(voice="Alex", backend=backend)
    tts.start()
    try:
        tts.speak("one")
        tts.speak("two")
        tts.wait()  # block until the worker drains the queue
    finally:
        tts.stop()

    assert ("one", "Alex") in backend.said
    assert ("two", "Alex") in backend.said
    assert len(backend.said) == 2
