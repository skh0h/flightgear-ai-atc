"""
Gemini API client with structured-output support.

TODO: Implement wrapper around google-genai SDK that:
  - Accepts a Pydantic/dataclass response schema and returns typed output
  - Detects offline state (network error / quota) and raises OfflineError
  - Manages API key from config, retries with exponential back-off
  - Exposes generate(prompt, schema) -> typed result
"""
