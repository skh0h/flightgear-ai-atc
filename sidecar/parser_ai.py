"""
Gemini-based airport parser (online path).

TODO: Implement parse_with_ai(icao, groundnet_xml_text, gemini_client) that:
  - Builds a prompt containing the raw groundnet XML and airport context
  - Calls gemini_client.generate() with AirportPicture as the response schema
  - Returns a fully populated AirportPicture with source="ai"
  - Falls back to parser_code on OfflineError or structured-output failure
"""
