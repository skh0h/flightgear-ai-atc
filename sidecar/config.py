"""
Configuration loader for the FlightGear AI ATC sidecar.

Reads settings from environment variables (and optionally a .env file via
python-dotenv).  The GEMINI_API_KEY is intentionally optional so the offline
code path works without a key present.  ConfigError is raised only when a
value that *is* present is structurally invalid (e.g. a non-integer port).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when a config value is present but structurally invalid."""


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration."""

    gemini_api_key: str | None
    fg_telnet_host: str
    fg_telnet_port: int
    cache_db_path: str
    tts_voice: str
    log_level: str
    gemini_model_fast: str
    gemini_model_pro: str
    metar_enabled: bool = True  # set METAR_ENABLED=0 to disable METAR fetches
    session_log_path: str | None = None  # path to JSONL session log; None = off
    # AI-inferred taxiway names are unverified guesses — Gemini has no access to
    # chart data, AIRAC, or any authoritative naming source.  Default False keeps
    # ATC clearances grounded in real groundnet XML names only.  Enable only once
    # Gemini is wired to an authoritative source (e.g. FAA NASR, Jeppesen charts).
    ai_taxiway_labels: bool = False  # set AI_TAXIWAY_LABELS=1 to enable (unsafe)


def load(env_path: str | None = None) -> Settings:
    """Load Settings from environment variables, optionally reading a .env file.

    Args:
        env_path: Path to a .env file.  If *None* the loader tries the default
            ``.env`` in the current working directory.  Missing .env files are
            silently ignored — environment variables and defaults still apply.

    Returns:
        A frozen :class:`Settings` instance.

    Raises:
        ConfigError: When a present value cannot be parsed or is out of range.
            Never raised for a missing ``GEMINI_API_KEY``.
    """
    # Load .env without overriding already-set env vars; ignore missing file.
    load_dotenv(dotenv_path=env_path, override=False)

    # --- gemini_api_key: optional ---
    raw_key = os.environ.get("GEMINI_API_KEY", "").strip()
    gemini_api_key: str | None = raw_key if raw_key else None

    # --- fg_telnet_host ---
    fg_telnet_host = os.environ.get("FG_TELNET_HOST", "localhost").strip()
    if not fg_telnet_host:
        raise ConfigError("FG_TELNET_HOST must not be empty when specified")

    # --- fg_telnet_port ---
    raw_port = os.environ.get("FG_TELNET_PORT", "5501").strip()
    try:
        fg_telnet_port = int(raw_port)
    except ValueError:
        raise ConfigError(
            f"FG_TELNET_PORT must be an integer, got: {raw_port!r}"
        ) from None
    if not (1 <= fg_telnet_port <= 65535):
        raise ConfigError(
            f"FG_TELNET_PORT must be in 1..65535, got: {fg_telnet_port}"
        )

    # --- cache_db_path ---
    cache_db_path = os.environ.get(
        "CACHE_DB_PATH", "fixtures/cache/airports.sqlite"
    ).strip()

    # --- tts_voice ---
    tts_voice = os.environ.get("TTS_VOICE", "Alex").strip()

    # --- log_level ---
    log_level = os.environ.get("LOG_LEVEL", "INFO").strip().upper()

    # --- model ids ---
    gemini_model_fast = os.environ.get(
        "GEMINI_MODEL_FAST", "gemini-2.5-flash"
    ).strip()
    gemini_model_pro = os.environ.get(
        "GEMINI_MODEL_PRO", "gemini-2.5-pro"
    ).strip()

    # --- metar_enabled ---
    metar_enabled = os.environ.get("METAR_ENABLED", "1").strip() not in ("0", "false", "no")

    # --- session_log_path ---
    raw_log_path = os.environ.get("SESSION_LOG_PATH", "").strip()
    session_log_path: str | None = raw_log_path if raw_log_path else None

    # --- ai_taxiway_labels ---
    ai_taxiway_labels = os.environ.get("AI_TAXIWAY_LABELS", "0").strip() in ("1", "true", "yes")

    return Settings(
        gemini_api_key=gemini_api_key,
        fg_telnet_host=fg_telnet_host,
        fg_telnet_port=fg_telnet_port,
        cache_db_path=cache_db_path,
        tts_voice=tts_voice,
        log_level=log_level,
        gemini_model_fast=gemini_model_fast,
        gemini_model_pro=gemini_model_pro,
        metar_enabled=metar_enabled,
        session_log_path=session_log_path,
        ai_taxiway_labels=ai_taxiway_labels,
    )
