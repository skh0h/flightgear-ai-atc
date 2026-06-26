"""Tests for sidecar/config.py — all offline, no network calls."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sidecar.config import ConfigError, Settings, load


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all config-related env vars so defaults are predictable."""
    for key in (
        "GEMINI_API_KEY",
        "FG_TELNET_HOST",
        "FG_TELNET_PORT",
        "CACHE_DB_PATH",
        "TTS_VOICE",
        "LOG_LEVEL",
        "GEMINI_MODEL_FAST",
        "GEMINI_MODEL_PRO",
        "AI_TAXIWAY_LABELS",
        "TTS_ENGINE",
        "PIPER_BIN",
        "PIPER_VOICE",
        "STT_ENGINE",
        "WHISPER_BIN",
        "RADIO_STATIC",
        "CAREER_PATH",
    ):
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


def test_load_returns_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """load() with no env vars returns the documented defaults."""
    _clean_env(monkeypatch)

    settings = load(env_path=None)

    assert isinstance(settings, Settings)
    assert settings.fg_telnet_host == "localhost"
    assert settings.fg_telnet_port == 5501
    assert settings.cache_db_path == "fixtures/cache/airports.sqlite"
    assert settings.tts_voice == "Alex"
    assert settings.log_level == "INFO"
    assert settings.gemini_model_fast == "gemini-2.5-flash"
    assert settings.gemini_model_pro == "gemini-2.5-pro"


def test_missing_api_key_yields_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing GEMINI_API_KEY must produce gemini_api_key=None, not raise."""
    _clean_env(monkeypatch)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    # Point at a non-existent .env so load_dotenv() does NOT auto-discover a
    # developer's real, gitignored .env at the repo root. find_dotenv() walks up
    # from config.py's own location (not the CWD), so passing an explicit path
    # is the only reliable way to isolate this test from a local key.
    settings = load(env_path=str(tmp_path / "nonexistent.env"))

    assert settings.gemini_api_key is None


def test_empty_api_key_yields_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty GEMINI_API_KEY string also yields None."""
    _clean_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "")

    settings = load(env_path=None)

    assert settings.gemini_api_key is None


# ---------------------------------------------------------------------------
# Reading values from env vars
# ---------------------------------------------------------------------------


def test_reads_api_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")

    settings = load(env_path=None)

    assert settings.gemini_api_key == "test-key-123"


def test_reads_all_overrides_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("FG_TELNET_HOST", "192.168.1.10")
    monkeypatch.setenv("FG_TELNET_PORT", "9999")
    monkeypatch.setenv("CACHE_DB_PATH", "/tmp/test.sqlite")
    monkeypatch.setenv("TTS_VOICE", "Samantha")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("GEMINI_MODEL_FAST", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_MODEL_PRO", "gemini-2.5-pro")

    settings = load(env_path=None)

    assert settings.fg_telnet_host == "192.168.1.10"
    assert settings.fg_telnet_port == 9999
    assert settings.cache_db_path == "/tmp/test.sqlite"
    assert settings.tts_voice == "Samantha"
    assert settings.log_level == "DEBUG"  # normalised to uppercase
    assert settings.gemini_model_fast == "gemini-2.5-flash"
    assert settings.gemini_model_pro == "gemini-2.5-pro"


# ---------------------------------------------------------------------------
# Reading from a .env file
# ---------------------------------------------------------------------------


def test_reads_values_from_dotenv_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """load(env_path=...) picks up values from a .env file."""
    _clean_env(monkeypatch)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "GEMINI_API_KEY=file-key\nFG_TELNET_PORT=7777\n"
    )

    settings = load(env_path=str(env_file))

    assert settings.gemini_api_key == "file-key"
    assert settings.fg_telnet_port == 7777


def test_missing_dotenv_file_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """load() must not raise if the .env path doesn't exist."""
    _clean_env(monkeypatch)

    # Should complete without error even though the path is bogus.
    settings = load(env_path="/nonexistent/path/.env")

    assert isinstance(settings, Settings)


# ---------------------------------------------------------------------------
# Invalid values raise ConfigError
# ---------------------------------------------------------------------------


def test_invalid_port_string_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("FG_TELNET_PORT", "not-a-number")

    with pytest.raises(ConfigError, match="FG_TELNET_PORT"):
        load(env_path=None)


def test_port_zero_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("FG_TELNET_PORT", "0")

    with pytest.raises(ConfigError, match="FG_TELNET_PORT"):
        load(env_path=None)


def test_port_out_of_range_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("FG_TELNET_PORT", "99999")

    with pytest.raises(ConfigError, match="FG_TELNET_PORT"):
        load(env_path=None)


def test_empty_host_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("FG_TELNET_HOST", "")

    with pytest.raises(ConfigError, match="FG_TELNET_HOST"):
        load(env_path=None)


def test_ai_taxiway_labels_defaults_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """ai_taxiway_labels must default to False (data-only / safe mode)."""
    _clean_env(monkeypatch)
    settings = load(env_path=None)
    assert settings.ai_taxiway_labels is False


def test_ai_taxiway_labels_enabled_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI_TAXIWAY_LABELS=1 enables the flag."""
    _clean_env(monkeypatch)
    monkeypatch.setenv("AI_TAXIWAY_LABELS", "1")
    settings = load(env_path=None)
    assert settings.ai_taxiway_labels is True


def test_ai_taxiway_labels_not_enabled_by_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI_TAXIWAY_LABELS=0 keeps the flag False."""
    _clean_env(monkeypatch)
    monkeypatch.setenv("AI_TAXIWAY_LABELS", "0")
    settings = load(env_path=None)
    assert settings.ai_taxiway_labels is False


# ---------------------------------------------------------------------------
# Phase 5: voice-realism settings (TTS/STT/radio static)
# ---------------------------------------------------------------------------


def test_phase5_voice_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """The six Phase 5 fields fall back to safe defaults."""
    _clean_env(monkeypatch)
    settings = load(env_path=None)
    assert settings.tts_engine == "say"
    assert settings.piper_bin == "piper"
    assert settings.piper_voice == ""
    assert settings.stt_engine == "none"
    assert settings.whisper_bin == "whisper"
    assert settings.radio_static is False


def test_phase5_voice_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """All six Phase 5 fields parse from their environment variables."""
    _clean_env(monkeypatch)
    monkeypatch.setenv("TTS_ENGINE", "piper")
    monkeypatch.setenv("PIPER_BIN", "/opt/piper/piper")
    monkeypatch.setenv("PIPER_VOICE", "/models/en_US.onnx")
    monkeypatch.setenv("STT_ENGINE", "whisper")
    monkeypatch.setenv("WHISPER_BIN", "/opt/whisper/whisper")
    monkeypatch.setenv("RADIO_STATIC", "1")
    settings = load(env_path=None)
    assert settings.tts_engine == "piper"
    assert settings.piper_bin == "/opt/piper/piper"
    assert settings.piper_voice == "/models/en_US.onnx"
    assert settings.stt_engine == "whisper"
    assert settings.whisper_bin == "/opt/whisper/whisper"
    assert settings.radio_static is True


def test_radio_static_zero_keeps_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """RADIO_STATIC=0 keeps the flag False (boolean parsing like the others)."""
    _clean_env(monkeypatch)
    monkeypatch.setenv("RADIO_STATIC", "0")
    settings = load(env_path=None)
    assert settings.radio_static is False


# ---------------------------------------------------------------------------
# Phase 9: career persistence path
# ---------------------------------------------------------------------------


def test_career_path_defaults_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """career_path defaults to "" (career persistence off)."""
    _clean_env(monkeypatch)
    settings = load(env_path=None)
    assert settings.career_path == ""


def test_career_path_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """CAREER_PATH populates career_path verbatim (trimmed)."""
    _clean_env(monkeypatch)
    monkeypatch.setenv("CAREER_PATH", "/tmp/career.json")
    settings = load(env_path=None)
    assert settings.career_path == "/tmp/career.json"
