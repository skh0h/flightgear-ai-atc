"""
Text-to-speech output, pluggable backend.

TODO: Implement:
  - speak(text, voice="Alex") -> None  (default: macOS `say` subprocess)
  - Backend protocol/ABC so alternative engines (pyttsx3, ElevenLabs) can swap in
  - Queue-based speaking so long clearances don't block the event loop
"""
