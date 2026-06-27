"""Tests for sidecar/gemini_client.py — all mocked, no live network calls."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from sidecar.config import Settings
from sidecar.gemini_client import GeminiClient, OfflineError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_settings(api_key: str | None = "test-key") -> Settings:
    return Settings(
        gemini_api_key=api_key,
        fg_telnet_host="localhost",
        fg_telnet_port=5501,
        cache_db_path="fixtures/cache/airports.sqlite",
        tts_voice="Alex",
        log_level="INFO",
        gemini_model_fast="gemini-2.5-flash",
        gemini_model_pro="gemini-2.5-pro",
    )


class _SampleSchema(BaseModel):
    callsign: str
    runway: str


def _noop_sleep(_seconds: float) -> None:
    """Replacement for time.sleep that does nothing (fast tests)."""


# ---------------------------------------------------------------------------
# Helper: build a mock genai.Client that returns a successful response
# ---------------------------------------------------------------------------


def _mock_client_with_response(parsed_obj: Any) -> MagicMock:
    """Return a mock genai.Client whose generate_content returns parsed_obj."""
    mock_response = MagicMock()
    mock_response.parsed = parsed_obj
    mock_response.text = parsed_obj.model_dump_json()

    mock_models = MagicMock()
    mock_models.generate_content.return_value = mock_response

    mock_client = MagicMock()
    mock_client.models = mock_models
    return mock_client


# ---------------------------------------------------------------------------
# (a) Happy path — structured output returns the parsed typed object
# ---------------------------------------------------------------------------


def test_generate_returns_parsed_object() -> None:
    """generate() returns the typed Pydantic object on a successful call."""
    expected = _SampleSchema(callsign="N12345", runway="28R")
    settings = _make_settings()
    client = GeminiClient(settings)
    mock_genai_client = _mock_client_with_response(expected)

    with patch("sidecar.gemini_client.GeminiClient._get_client", return_value=mock_genai_client):
        result = client.generate("test prompt", _SampleSchema, _sleep=_noop_sleep)

    assert isinstance(result, _SampleSchema)
    assert result.callsign == "N12345"
    assert result.runway == "28R"


def test_generate_falls_back_to_model_validate_when_parsed_is_none() -> None:
    """generate() uses model_validate_json when response.parsed is None."""
    expected = _SampleSchema(callsign="N99999", runway="10L")

    mock_response = MagicMock()
    mock_response.parsed = None
    mock_response.text = expected.model_dump_json()

    mock_models = MagicMock()
    mock_models.generate_content.return_value = mock_response
    mock_client = MagicMock()
    mock_client.models = mock_models

    settings = _make_settings()
    gc = GeminiClient(settings)

    with patch("sidecar.gemini_client.GeminiClient._get_client", return_value=mock_client):
        result = gc.generate("prompt", _SampleSchema, _sleep=_noop_sleep)

    assert result.callsign == "N99999"
    assert result.runway == "10L"


def test_none_text_and_none_parsed_raises_offline_error() -> None:
    """generate() raises OfflineError when both response.parsed and response.text are None.

    This covers safety-blocked or otherwise empty Gemini responses where the SDK
    sets both fields to None.  The error must be OfflineError, not a raw
    ValidationError or AttributeError, so callers that catch OfflineError get a
    predictable contract.
    """
    mock_response = MagicMock()
    mock_response.parsed = None
    mock_response.text = None

    mock_models = MagicMock()
    mock_models.generate_content.return_value = mock_response
    mock_client = MagicMock()
    mock_client.models = mock_models

    gc = GeminiClient(_make_settings())

    with patch("sidecar.gemini_client.GeminiClient._get_client", return_value=mock_client):
        with pytest.raises(OfflineError, match="no text"):
            gc.generate("prompt", _SampleSchema, _sleep=_noop_sleep)


# ---------------------------------------------------------------------------
# (b) Missing api_key -> OfflineError (no network attempted)
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_offline_error() -> None:
    """generate() raises OfflineError immediately when the key is absent."""
    settings = _make_settings(api_key=None)
    gc = GeminiClient(settings)

    with pytest.raises(OfflineError, match="GEMINI_API_KEY"):
        gc.generate("prompt", _SampleSchema)


def test_empty_api_key_raises_offline_error() -> None:
    """An empty string key also triggers OfflineError (treated as absent)."""
    settings = _make_settings(api_key="")
    gc = GeminiClient(settings)

    with pytest.raises(OfflineError):
        gc.generate("prompt", _SampleSchema)


# ---------------------------------------------------------------------------
# (c) Network / connection error -> OfflineError
# ---------------------------------------------------------------------------


def test_connection_error_raises_offline_error() -> None:
    """An OSError (network unreachable) from generate_content -> OfflineError."""
    mock_models = MagicMock()
    mock_models.generate_content.side_effect = OSError("Network unreachable")
    mock_client = MagicMock()
    mock_client.models = mock_models

    gc = GeminiClient(_make_settings())

    with patch("sidecar.gemini_client.GeminiClient._get_client", return_value=mock_client):
        with pytest.raises(OfflineError):
            gc.generate("prompt", _SampleSchema, _sleep=_noop_sleep)


def test_timeout_error_raises_offline_error() -> None:
    """A TimeoutError from the transport layer -> OfflineError."""
    mock_models = MagicMock()
    mock_models.generate_content.side_effect = TimeoutError("timed out")
    mock_client = MagicMock()
    mock_client.models = mock_models

    gc = GeminiClient(_make_settings())

    with patch("sidecar.gemini_client.GeminiClient._get_client", return_value=mock_client):
        with pytest.raises(OfflineError):
            gc.generate("prompt", _SampleSchema, _sleep=_noop_sleep)


# ---------------------------------------------------------------------------
# (d) Auth failure -> OfflineError
# ---------------------------------------------------------------------------


def test_auth_401_raises_offline_error() -> None:
    """ClientError with code 401 (invalid key) -> OfflineError."""
    # Import and create a real ClientError with code=401
    from google.genai import errors

    auth_error = errors.ClientError(401, {"error": {"message": "API key invalid"}})

    mock_models = MagicMock()
    mock_models.generate_content.side_effect = auth_error
    mock_client = MagicMock()
    mock_client.models = mock_models

    gc = GeminiClient(_make_settings())

    with patch("sidecar.gemini_client.GeminiClient._get_client", return_value=mock_client):
        with pytest.raises(OfflineError):
            gc.generate("prompt", _SampleSchema, _sleep=_noop_sleep)


def test_auth_403_raises_offline_error() -> None:
    """ClientError with code 403 (permission denied) -> OfflineError."""
    from google.genai import errors

    auth_error = errors.ClientError(403, {"error": {"message": "Forbidden"}})

    mock_models = MagicMock()
    mock_models.generate_content.side_effect = auth_error
    mock_client = MagicMock()
    mock_client.models = mock_models

    gc = GeminiClient(_make_settings())

    with patch("sidecar.gemini_client.GeminiClient._get_client", return_value=mock_client):
        with pytest.raises(OfflineError):
            gc.generate("prompt", _SampleSchema, _sleep=_noop_sleep)


# ---------------------------------------------------------------------------
# (e) Quota / rate-limit -> OfflineError
# ---------------------------------------------------------------------------


def test_quota_429_raises_offline_error() -> None:
    """ClientError with code 429 (quota exceeded) -> OfflineError."""
    from google.genai import errors

    quota_error = errors.ClientError(429, {"error": {"message": "Quota exceeded"}})

    mock_models = MagicMock()
    mock_models.generate_content.side_effect = quota_error
    mock_client = MagicMock()
    mock_client.models = mock_models

    gc = GeminiClient(_make_settings())

    with patch("sidecar.gemini_client.GeminiClient._get_client", return_value=mock_client):
        with pytest.raises(OfflineError):
            gc.generate("prompt", _SampleSchema, _sleep=_noop_sleep)


# ---------------------------------------------------------------------------
# (e2) Non-offline ClientError (e.g. 400/404) -> OfflineError (graceful degrade)
# ---------------------------------------------------------------------------


def test_non_offline_client_error_400_raises_offline_error() -> None:
    """ClientError 400 (malformed schema) -> OfflineError, not a raw provider error.

    A 400 is not in the offline set (401/403/429) and is not retryable (5xx),
    but it must still degrade to OfflineError so callers (phrase_online) fall
    back to the deterministic offline template instead of crashing on a raw
    google.genai ClientError. The original error is preserved as __cause__.
    """
    from google.genai import errors

    bad_request = errors.ClientError(400, {"error": {"message": "Invalid JSON schema"}})

    mock_models = MagicMock()
    mock_models.generate_content.side_effect = bad_request
    mock_client = MagicMock()
    mock_client.models = mock_models

    gc = GeminiClient(_make_settings())

    with patch("sidecar.gemini_client.GeminiClient._get_client", return_value=mock_client):
        with pytest.raises(OfflineError) as exc_info:
            gc.generate("prompt", _SampleSchema, _sleep=_noop_sleep)

    # generate_content is called once: a 400 is not retried.
    assert mock_models.generate_content.call_count == 1
    # Original provider error preserved as the cause for debugging.
    assert isinstance(exc_info.value.__cause__, errors.ClientError)


def test_non_offline_client_error_404_raises_offline_error() -> None:
    """ClientError 404 (bad model) -> OfflineError rather than leaking out raw."""
    from google.genai import errors

    not_found = errors.ClientError(404, {"error": {"message": "model not found"}})

    mock_models = MagicMock()
    mock_models.generate_content.side_effect = not_found
    mock_client = MagicMock()
    mock_client.models = mock_models

    gc = GeminiClient(_make_settings())

    with patch("sidecar.gemini_client.GeminiClient._get_client", return_value=mock_client):
        with pytest.raises(OfflineError) as exc_info:
            gc.generate("prompt", _SampleSchema, _sleep=_noop_sleep)

    assert isinstance(exc_info.value.__cause__, errors.ClientError)


# ---------------------------------------------------------------------------
# (f) Transient 5xx -> retry, then success; backoff is no-op
# ---------------------------------------------------------------------------


def test_transient_server_error_retried_then_succeeds() -> None:
    """generate() retries on ServerError and returns result on success."""
    from google.genai import errors

    server_error = errors.ServerError(503, {"error": {"message": "overloaded"}})
    expected = _SampleSchema(callsign="UAL123", runway="09R")

    success_response = MagicMock()
    success_response.parsed = expected

    mock_models = MagicMock()
    # First call raises 5xx, second call succeeds.
    mock_models.generate_content.side_effect = [server_error, success_response]
    mock_client = MagicMock()
    mock_client.models = mock_models

    sleep_calls: list[float] = []

    def _recording_sleep(s: float) -> None:
        sleep_calls.append(s)

    gc = GeminiClient(_make_settings())

    with patch("sidecar.gemini_client.GeminiClient._get_client", return_value=mock_client):
        result = gc.generate("prompt", _SampleSchema, _sleep=_recording_sleep)

    assert result.callsign == "UAL123"
    assert result.runway == "09R"
    # Exactly one retry means exactly one sleep call.
    assert len(sleep_calls) == 1
    assert mock_models.generate_content.call_count == 2


def test_all_attempts_fail_raises_offline_error() -> None:
    """generate() raises OfflineError when all retry attempts hit ServerError."""
    from google.genai import errors

    server_error = errors.ServerError(500, {"error": {"message": "internal"}})

    mock_models = MagicMock()
    mock_models.generate_content.side_effect = server_error
    mock_client = MagicMock()
    mock_client.models = mock_models

    gc = GeminiClient(_make_settings())

    with patch("sidecar.gemini_client.GeminiClient._get_client", return_value=mock_client):
        with pytest.raises(OfflineError, match="3 attempts"):
            gc.generate("prompt", _SampleSchema, _sleep=_noop_sleep)

    assert mock_models.generate_content.call_count == 3


def test_retry_uses_backoff_sleep() -> None:
    """Each retry sleeps with increasing backoff (base ** attempt)."""
    from google.genai import errors

    server_error = errors.ServerError(503, {"error": {"message": "overloaded"}})

    mock_models = MagicMock()
    # All 3 attempts fail so we capture all sleep calls.
    mock_models.generate_content.side_effect = server_error
    mock_client = MagicMock()
    mock_client.models = mock_models

    sleep_calls: list[float] = []

    def _recording_sleep(s: float) -> None:
        sleep_calls.append(s)

    gc = GeminiClient(_make_settings())

    with patch("sidecar.gemini_client.GeminiClient._get_client", return_value=mock_client):
        with pytest.raises(OfflineError):
            gc.generate("prompt", _SampleSchema, _sleep=_recording_sleep)

    # 3 attempts: sleep after attempt 0 and attempt 1 (not after the last).
    assert sleep_calls == [1.0, 2.0]  # 2.0**0=1.0, 2.0**1=2.0


# ---------------------------------------------------------------------------
# (g) Unexpected exception type — must NOT be swallowed as OfflineError
# ---------------------------------------------------------------------------


def test_unexpected_exception_propagates_out_of_generate() -> None:
    """An unexpected exception (not offline/retryable) re-raises as-is from generate().

    generate() must not swallow arbitrary exceptions by wrapping them in
    OfflineError — only known offline/transient errors get that treatment.
    """

    class _WeirdError(Exception):
        """Some totally unexpected exception type."""

    mock_models = MagicMock()
    mock_models.generate_content.side_effect = _WeirdError("something unusual")
    mock_client = MagicMock()
    mock_client.models = mock_models

    gc = GeminiClient(_make_settings())

    with patch("sidecar.gemini_client.GeminiClient._get_client", return_value=mock_client):
        with pytest.raises(_WeirdError, match="something unusual"):
            gc.generate("prompt", _SampleSchema, _sleep=_noop_sleep)


# ---------------------------------------------------------------------------
# Default model selection
# ---------------------------------------------------------------------------


def test_generate_uses_fast_model_by_default() -> None:
    """generate() passes gemini_model_fast to the SDK when model is unset."""
    expected = _SampleSchema(callsign="X", runway="Y")
    mock_client = _mock_client_with_response(expected)

    gc = GeminiClient(_make_settings())

    with patch("sidecar.gemini_client.GeminiClient._get_client", return_value=mock_client):
        gc.generate("prompt", _SampleSchema, _sleep=_noop_sleep)

    call_kwargs = mock_client.models.generate_content.call_args
    assert call_kwargs.kwargs["model"] == "gemini-2.5-flash"


def test_generate_honours_explicit_model() -> None:
    """generate(model=...) passes the caller's model string to the SDK."""
    expected = _SampleSchema(callsign="X", runway="Y")
    mock_client = _mock_client_with_response(expected)

    gc = GeminiClient(_make_settings())

    with patch("sidecar.gemini_client.GeminiClient._get_client", return_value=mock_client):
        gc.generate("prompt", _SampleSchema, model="gemini-2.5-pro", _sleep=_noop_sleep)

    call_kwargs = mock_client.models.generate_content.call_args
    assert call_kwargs.kwargs["model"] == "gemini-2.5-pro"
