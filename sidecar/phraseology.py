"""
ATC phraseology generation.

TODO: Implement:
  - phrase_online(clearance_data, gemini_client) -> str
    Uses Gemini to produce natural, ICAO-standard ATC speech
  - phrase_offline(clearance_data) -> str
    Template-based fallback using string.Template or f-strings
  - Clearance data schema: callsign, clearance_type, taxi_route,
    active_runway, hold_short, frequency, remarks
"""
