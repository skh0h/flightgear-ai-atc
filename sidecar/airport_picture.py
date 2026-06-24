"""
Dataclasses for the cached "airport picture" schema.

Schema fields:
  icao          (str)   - ICAO airport identifier
  source        (str)   - "ai" | "code" — which parser produced this picture
  generated_at  (str)   - ISO-8601 timestamp of generation
  groundnet_hash(str)   - SHA-256 hex of the raw groundnet.xml used as cache key
  parking       (list[ParkingSpot])
    ParkingSpot: id, name, type, lat, lon, heading
  nodes         (list[Node])
    Node: index, lat, lon, on_runway (bool), hold_point (bool)
  segments      (list[Segment])
    Segment: begin (node index), end (node index), name, pushback (bool)
  runways       (list[Runway])
    Runway: id, thr_lat, thr_lon, heading, length, ils_freq, entry_nodes (list[int])
  frequencies   (Frequencies)
    Frequencies: ground, tower, atis, approach, departure  (all str MHz)
  taxi_graph    (dict)  - adjacency dict {node_index: [neighbor_index, ...]}

TODO: Convert to dataclasses (or attrs/pydantic) with from_dict / to_dict helpers.
"""

# TODO: implement dataclass definitions per schema above
