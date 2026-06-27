"""
Shared "airport picture" schema for the FlightGear AI ATC sidecar.

These Pydantic models serve three roles simultaneously:

  1. The Gemini ``response_schema`` for the AI parser (``AIAirportResponse``).
  2. The in-memory representation used by routing/phraseology (``AirportPicture``).
  3. The SQLite (de)serialiser via ``model_dump_json()`` / ``model_validate_json()``.

Design rules (see the Phase 2 handoff):

  * ``taxi_graph`` is *computed*, never trusted from the AI.  ``build_taxi_graph``
    is the single source of truth; both parsers call it after producing
    nodes/segments.
  * The AI is asked for only the fields it can reliably produce
    (``AIAirportResponse``).  The computed/trusted fields — ``taxi_graph``,
    ``groundnet_hash``, ``generated_at`` — are filled in locally.  Int-keyed
    dicts are unreliable for structured output, which is the main reason
    ``taxi_graph`` is excluded from the AI schema.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ParkingSpot(BaseModel):
    """A gate / parking position.  ``id`` is the groundnet index."""

    id: int
    name: str
    type: str = ""
    lat: float
    lon: float
    heading: float = 0.0


class Node(BaseModel):
    """A taxi-network node, identified by its groundnet ``index``."""

    index: int
    lat: float
    lon: float
    on_runway: bool = False
    hold_point: bool = False


class Segment(BaseModel):
    """An undirected taxiway segment between two node/parking indices.

    ``name`` may be empty in the source groundnet — the AI parser's job is to
    infer a sensible taxiway label for those.
    """

    begin: int
    end: int
    name: str = ""
    pushback: bool = False


class Runway(BaseModel):
    """A runway end.  Threshold/ILS data is supplied in-sim via airportinfo;
    left empty when only the fixture groundnet is available."""

    id: str
    thr_lat: float = 0.0
    thr_lon: float = 0.0
    heading: float = 0.0
    length: float = 0.0
    ils_freq: Optional[str] = None
    entry_nodes: list[int] = Field(default_factory=list)
    # Mode A: whether this runway end is currently active for departures.
    # Backward-compatible default (``False``): old cached pictures without the
    # field load cleanly, and runway selection falls back to ALL runways when
    # none are marked active (see ``select_departure_runway``).
    active: bool = False


class Frequencies(BaseModel):
    """ATC frequencies in MHz, as strings (e.g. ``"121.80"``).  All optional —
    absent frequencies stay ``None`` so the offline path still succeeds."""

    ground: Optional[str] = None
    tower: Optional[str] = None
    atis: Optional[str] = None
    approach: Optional[str] = None
    departure: Optional[str] = None


class SegmentLabel(BaseModel):
    """A taxiway name assigned by the AI to a specific segment.

    The ``begin``/``end`` pair identifies the segment (treated as undirected,
    so either orientation matches).  Structured objects are more reliable than
    tuple-keyed dicts for Gemini structured output.
    """

    begin: int
    end: int
    name: str


class AIAirportResponse(BaseModel):
    """The structured output the Gemini model is asked to return.

    The AI's sole job is labeling unnamed taxiway segments.  All geometry
    (nodes, parking, runways, frequencies) is produced deterministically by
    the code parser and never re-emitted by the model, avoiding the
    output-token cap on large airports (e.g. KSFO: 1144 nodes, 3131 arcs).
    """

    taxiway_labels: list[SegmentLabel] = Field(default_factory=list)


class AirportPicture(BaseModel):
    """The complete cached representation of an airport's ground network."""

    icao: str
    source: Literal["ai", "code"]
    generated_at: str
    groundnet_hash: str
    parking: list[ParkingSpot] = Field(default_factory=list)
    nodes: list[Node] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    runways: list[Runway] = Field(default_factory=list)
    frequencies: Frequencies = Field(default_factory=Frequencies)
    # Undirected adjacency: node/parking index -> sorted list of neighbours.
    # JSON serialises the int keys as strings; Pydantic coerces them back on
    # load, so model_dump_json()/model_validate_json() round-trips cleanly.
    taxi_graph: dict[int, list[int]] = Field(default_factory=dict)


class TrafficSnapshot(BaseModel):
    """A single live AI aircraft on the ground, snapped to the taxi network.

    Mode B data-only model (deliberately NOT part of ``AIAirportResponse`` —
    the Gemini schema is untouched).  ``node_index``/``snap_dist_m`` are filled
    in by the sidecar after snapping the raw ``/ai/models`` position to the
    nearest taxi node.
    """

    callsign: str = ""
    lat: float
    lon: float
    heading: float = 0.0
    node_index: Optional[int] = None
    snap_dist_m: float = 0.0


def build_taxi_graph(
    nodes: list[Node], segments: list[Segment]
) -> dict[int, list[int]]:
    """Build an undirected adjacency map from nodes and segments.

    Every node index appears as a key (isolated nodes map to an empty list).
    Every segment contributes both directions; self-loops are skipped and
    neighbour lists are sorted for determinism.  Segment endpoints that are not
    in ``nodes`` (e.g. parking indices linked by pushback arcs) still become
    keys, so routing can start from a gate.

    Args:
        nodes: Parsed taxi nodes.
        segments: Parsed (already de-duplicated) undirected segments.

    Returns:
        ``{index: [neighbour, ...]}`` with sorted keys and neighbour lists.
    """
    adjacency: dict[int, set[int]] = {}
    for node in nodes:
        adjacency.setdefault(node.index, set())
    for seg in segments:
        if seg.begin == seg.end:
            continue
        adjacency.setdefault(seg.begin, set()).add(seg.end)
        adjacency.setdefault(seg.end, set()).add(seg.begin)
    return {idx: sorted(neighbours) for idx, neighbours in sorted(adjacency.items())}
