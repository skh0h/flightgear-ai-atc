"""
Configuration loader.

TODO: Implement:
  - load() -> Settings dataclass
  - Read GEMINI_API_KEY and optional overrides from .env via python-dotenv
  - Settings fields: gemini_api_key, fg_telnet_host, fg_telnet_port,
      cache_db_path, tts_voice, log_level
  - Raise ConfigError on missing required keys
"""
