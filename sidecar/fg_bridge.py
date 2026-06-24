"""
FlightGear telnet property client.

TODO: Implement async telnet client connecting to localhost:5501 that supports:
  - get(path) -> str
  - set(path, value)
  - subscribe(path, callback) for property-change events
  - Reconnect/back-off logic when FG is not yet running
"""
