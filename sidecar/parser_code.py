"""
Deterministic groundnet.xml + airportinfo parser (offline path).

TODO: Implement parse_groundnet(xml_path) and parse_airportinfo(icao) that:
  - Read and parse FlightGear's groundnet.xml via xml.etree.ElementTree
  - Extract nodes, segments, parking spots, and runways into AirportPicture
  - Read frequency data from FlightGear's navdata or airportinfo API
  - Return a fully populated AirportPicture with source="code"
  - Raise ParseError on malformed input
"""
