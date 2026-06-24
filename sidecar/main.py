"""
Sidecar entry point: event loop and FlightGear bridge orchestration.

TODO: Implement asyncio event loop that:
  - Initialises FGBridge, GeminiClient, cache, TTS, and router
  - Listens for property changes from FlightGear via fg_bridge
  - Dispatches inbound /ai-atc/request to the parser and phraseology pipeline
  - Writes ATC responses back to /ai-atc/response via fg_bridge
  - Handles graceful shutdown on SIGINT/SIGTERM
"""
