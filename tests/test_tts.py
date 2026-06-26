"""Tests for sidecar/tts.py — mock subprocess runner, no real audio."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from sidecar.tts import (
    PiperBackend,
    SayBackend,
    TTS,
    TTSBackend,
    apply_radio_static,
    make_tts_backend,
    voice_for,
)


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


# ---------------------------------------------------------------------------
# Phase 5: per-role voice selection
# ---------------------------------------------------------------------------


def test_voice_for_returns_distinct_voices_per_role() -> None:
    roles = ["ground", "tower", "approach", "departure", "atis"]
    voices = [voice_for(r) for r in roles]
    # Every role gets a non-empty voice, and they are all distinct.
    assert all(v for v in voices)
    assert len(set(voices)) == len(voices)


def test_voice_for_unknown_role_defaults_to_alex() -> None:
    assert voice_for("nonsense") == "Alex"
    assert voice_for("") == "Alex"


def test_tts_speak_role_selects_voice() -> None:
    backend = _RecordingBackend()
    TTS(voice="Alex", backend=backend).speak("taxi", role="ground")
    assert backend.said == [("taxi", voice_for("ground"))]
    assert backend.said[0][1] != "Alex"  # role overrides the instance default


def test_tts_speak_explicit_voice_beats_role() -> None:
    backend = _RecordingBackend()
    TTS(voice="Alex", backend=backend).speak("hi", voice="Daniel", role="ground")
    assert backend.said == [("hi", "Daniel")]


def test_tts_speak_without_role_keeps_default_voice() -> None:
    # Backward-compatible: no role == previous behaviour.
    backend = _RecordingBackend()
    TTS(voice="Alex", backend=backend).speak("hello")
    assert backend.said == [("hello", "Alex")]


# ---------------------------------------------------------------------------
# Phase 5: PiperBackend + make_tts_backend selection
# ---------------------------------------------------------------------------


@dataclass
class _FakeSettings:
    tts_engine: str = "say"
    piper_bin: str = "piper"
    piper_voice: str = ""


def test_piper_available_reflects_which_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sidecar.tts.shutil.which", lambda _name: "/usr/bin/piper")
    assert PiperBackend.available("piper") is True


def test_piper_available_reflects_which_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sidecar.tts.shutil.which", lambda _name: None)
    assert PiperBackend.available("piper") is False


def test_piper_say_shells_to_piper_best_effort() -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def runner(args: list[str], **kwargs: Any) -> None:
        calls.append((args, kwargs))

    PiperBackend(piper_bin="piper", voice="/models/en.onnx", runner=runner).say("hi", "")
    assert calls[0][0][0] == "piper"
    assert "/models/en.onnx" in calls[0][0]


def test_piper_say_never_raises_on_runner_failure() -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("piper exploded")

    # Must swallow the error so the speak worker is never killed.
    PiperBackend(runner=boom).say("hi", "")


def test_make_tts_backend_returns_say_for_say_engine() -> None:
    assert isinstance(make_tts_backend(_FakeSettings(tts_engine="say")), SayBackend)


def test_make_tts_backend_returns_say_when_piper_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(PiperBackend, "available", classmethod(lambda cls, b="piper": False))
    backend = make_tts_backend(_FakeSettings(tts_engine="piper"))
    assert isinstance(backend, SayBackend)


def test_make_tts_backend_returns_piper_when_engine_and_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(PiperBackend, "available", classmethod(lambda cls, b="piper": True))
    backend = make_tts_backend(_FakeSettings(tts_engine="piper", piper_voice="/m.onnx"))
    assert isinstance(backend, PiperBackend)


# ---------------------------------------------------------------------------
# Phase 5: radio static passthrough hook
# ---------------------------------------------------------------------------


def test_apply_radio_static_passthrough_when_disabled() -> None:
    assert apply_radio_static("taxi to 28R", enabled=False) == "taxi to 28R"


def test_apply_radio_static_passthrough_when_enabled() -> None:
    # The hook is text-path neutral; real DSP is runtime-only.
    assert apply_radio_static("taxi to 28R", enabled=True) == "taxi to 28R"
