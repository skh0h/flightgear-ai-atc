"""
SQLite-backed airport picture cache.

TODO: Implement:
  - Cache keyed by (icao, groundnet_hash) stored in an SQLite database
  - get(icao, groundnet_hash) -> AirportPicture | None
  - put(airport_picture) -> None  (upsert)
  - invalidate(icao) -> None
  - Schema: table pictures(icao TEXT, hash TEXT, data JSON, created_at TEXT,
      PRIMARY KEY (icao, hash))
"""
