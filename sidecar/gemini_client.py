"""
Gemini API client with structured-output support.

Wraps the google-genai SDK to:
  - Return typed, validated objects via Pydantic response_schema.
  - Raise OfflineError whenever Gemini is unreachable, the key is absent,
    auth fails, or the quota is exhausted — so callers can seamlessly
    fall back to the deterministic code path.
  - Retry transient 5xx ServerErrors with bounded exponential back-off.

The _sleep parameter injected into generate() is a no-op in tests so the
retry loop runs instantly without any real delays.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from sidecar.config import Settings

if TYPE_CHECKING:
    from google import genai as _genai_type  # noqa: F401 (type-checking only)

T = TypeVar("T")

_DEFAULT_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 2.0  # seconds; doubled on each retry


class OfflineError(Exception):
    """Raised when Gemini is unreachable or unavailable for any reason.

    Callers (parser_ai, phraseology) catch this and use the deterministic
    offline code path.
    """


class GeminiClient:
    """Thin wrapper around google.genai that adds retry and offline detection.

    The underlying genai.Client is constructed lazily on the first call to
    generate(), keeping import-time side-effects minimal and allowing the
    offline path to operate without ever touching the SDK network layer.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: _genai_type.Client | None = None  # populated lazily by _get_client()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self) -> _genai_type.Client:
        """Return the cached genai.Client, creating it on first access.

        Raises:
            OfflineError: If the API key is absent.
        """
        if not self._settings.gemini_api_key:
            raise OfflineError(
                "GEMINI_API_KEY is not set; Gemini is unavailable (offline mode)"
            )
        if self._client is None:
            from google import genai  # noqa: PLC0415 (lazy import intentional)

            self._client = genai.Client(api_key=self._settings.gemini_api_key)
        return self._client

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """Return True for transient 5xx server errors worth retrying."""
        try:
            from google.genai import errors  # noqa: PLC0415

            return isinstance(exc, errors.ServerError)
        except ImportError:
            return False

    @staticmethod
    def _is_offline(exc: Exception) -> bool:
        """Return True when the exception indicates Gemini is unreachable."""
        try:
            from google.genai import errors  # noqa: PLC0415

            if isinstance(exc, errors.ServerError):
                return True
            if isinstance(exc, errors.ClientError):
                # 401/403 = auth failure, 429 = quota/rate-limit
                return exc.code in (401, 403, 429)
        except ImportError:
            pass

        # Transport-level failures (DNS, TCP) before HTTP is established.
        # OSError already covers socket.error and ConnectionError as subclasses.
        return isinstance(exc, (OSError, TimeoutError))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        schema: type[T],
        *,
        model: str | None = None,
        _sleep: Callable[[float], None] = time.sleep,
    ) -> T:
        """Call Gemini with structured output and return a typed object.

        Args:
            prompt: The user prompt to send.
            schema: A Pydantic BaseModel subclass used as the response schema.
                    The SDK deserialises the response into this type.
            model:  Gemini model ID.  Defaults to settings.gemini_model_fast.
            _sleep: Backoff sleep function.  Override with a no-op in tests
                    so retries run instantly.

        Returns:
            An instance of *schema* populated from the model response.

        Raises:
            OfflineError: Key absent, network unreachable, auth failed,
                          quota exceeded, or max retries exhausted.
        """
        resolved_model = model or self._settings.gemini_model_fast

        client = self._get_client()  # raises OfflineError if key is missing

        from google.genai import types  # noqa: PLC0415

        last_exc: Exception | None = None
        for attempt in range(_DEFAULT_MAX_ATTEMPTS):
            try:
                response = client.models.generate_content(
                    model=resolved_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=schema,
                    ),
                )
                # Prefer SDK-parsed typed object; fall back to manual parse.
                if response.parsed is not None:
                    return response.parsed  # type: ignore[return-value]
                if response.text is None:
                    raise OfflineError(
                        "Gemini returned no text (response may be safety-blocked or empty)"
                    )
                return schema.model_validate_json(response.text)  # type: ignore[union-attr]

            except Exception as exc:
                if self._is_retryable(exc):
                    last_exc = exc
                    if attempt < _DEFAULT_MAX_ATTEMPTS - 1:
                        _sleep(_BACKOFF_BASE ** attempt)
                    continue
                if self._is_offline(exc):
                    raise OfflineError(
                        f"Gemini unavailable: {type(exc).__name__}: {exc}"
                    ) from exc
                raise  # unexpected — re-raise as-is

        raise OfflineError(
            f"Gemini unreachable after {_DEFAULT_MAX_ATTEMPTS} attempts: "
            f"{type(last_exc).__name__}: {last_exc}"
        ) from last_exc
