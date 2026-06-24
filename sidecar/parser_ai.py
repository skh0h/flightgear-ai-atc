"""
Gemini-backed groundnet parser — the online path.

Sends the raw groundnet XML to Gemini, asking it to label the many unnamed
taxiway segments, and converts the structured response into an
:class:`AirportPicture` with ``source="ai"``.  The *trusted* fields
(``taxi_graph``, ``groundnet_hash``, ``generated_at``) are always computed
locally — never taken from the model.

The whole design hinges on the offline contract: any ``OfflineError`` from the
client (missing key, network down, auth/quota failure, retries exhausted) is
caught and the deterministic :func:`parser_code.parse_groundnet` result is
returned instead, so callers always get an :class:`AirportPicture`.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from sidecar import parser_code
from sidecar.airport_picture import (
    AIAirportResponse,
    AirportPicture,
    build_taxi_graph,
)
from sidecar.gemini_client import GeminiClient, OfflineError

_log = logging.getLogger(__name__)

# Relative count divergence above which we warn that the AI dropped/added a lot.
_DIVERGENCE_FRACTION = 0.30
_DIVERGENCE_FLOOR = 5

_PROMPT_TEMPLATE = """You are an expert FlightGear airport ground-network analyst.

Airport ICAO: {icao}

Below is the airport's groundnet.xml. Extract the ground network as structured
data: parking spots, taxi nodes, taxiway segments, runways, and frequencies.

Important rules:
- Echo every node and parking coordinate exactly as given; do NOT invent or move
  positions.
- Do NOT add nodes or segments that are not present in the source.
- For each taxiway segment whose source name is empty, infer a sensible taxiway
  label from the airport's geometry and standard taxiway-naming conventions.
- Keep node/parking index numbers identical to the source.

groundnet.xml:
{xml}
"""


def _raw_bytes(groundnet_xml_text: str | bytes) -> bytes:
    if isinstance(groundnet_xml_text, bytes):
        return groundnet_xml_text
    return groundnet_xml_text.encode("utf-8")


def _source_counts(groundnet_xml_text: str | bytes) -> tuple[int | None, int | None]:
    """Count source taxi nodes and unique undirected arcs (== code-parser counts).

    Returns ``(None, None)`` if the XML cannot be parsed — the divergence check
    is best-effort and must never raise into the happy path.
    """
    try:
        root = ET.fromstring(_raw_bytes(groundnet_xml_text))
    except ET.ParseError:
        return None, None
    node_count = len(root.findall("./TaxiNodes/node"))
    undirected: set[tuple[int, int]] = set()
    for arc in root.findall("./TaxiWaySegments/arc"):
        try:
            begin, end = int(arc.get("begin")), int(arc.get("end"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        undirected.add((min(begin, end), max(begin, end)))
    return node_count, len(undirected)


def _warn_on_divergence(
    icao: str, groundnet_xml_text: str | bytes, picture: AirportPicture
) -> None:
    src_nodes, src_segs = _source_counts(groundnet_xml_text)
    if src_nodes is not None and abs(len(picture.nodes) - src_nodes) > max(
        _DIVERGENCE_FLOOR, _DIVERGENCE_FRACTION * src_nodes
    ):
        _log.warning(
            "%s: AI node count %d diverges from source %d",
            icao,
            len(picture.nodes),
            src_nodes,
        )
    if src_segs is not None and abs(len(picture.segments) - src_segs) > max(
        _DIVERGENCE_FLOOR, _DIVERGENCE_FRACTION * src_segs
    ):
        _log.warning(
            "%s: AI segment count %d diverges from source %d",
            icao,
            len(picture.segments),
            src_segs,
        )


def parse_with_ai(
    icao: str,
    groundnet_xml_text: str | bytes,
    gemini_client: GeminiClient,
    *,
    airportinfo: dict | None = None,
    model: str | None = None,
) -> AirportPicture:
    """Parse a groundnet with Gemini, falling back to the code parser offline.

    Args:
        icao: ICAO identifier to stamp on the result.
        groundnet_xml_text: Raw groundnet XML (text or bytes).
        gemini_client: The configured :class:`GeminiClient`.
        airportinfo: Optional in-sim runway/frequency data; when present its
            runways/frequencies are authoritative (the model cannot reliably
            infer ILS or threshold positions from a groundnet alone).
        model: Optional Gemini model override.

    Returns:
        An :class:`AirportPicture` — ``source="ai"`` on success, ``source="code"``
        if Gemini is unavailable.
    """
    prompt = _PROMPT_TEMPLATE.format(icao=icao, xml=groundnet_xml_text)
    try:
        ai: AIAirportResponse = gemini_client.generate(
            prompt, AIAirportResponse, model=model
        )
    except OfflineError as exc:
        _log.warning(
            "%s: Gemini unavailable (%s); using deterministic code parser",
            icao,
            exc,
        )
        return parser_code.parse_groundnet(
            groundnet_xml_text, icao, airportinfo=airportinfo
        )

    picture = AirportPicture(
        icao=icao,
        source="ai",
        generated_at=datetime.now(timezone.utc).isoformat(),
        groundnet_hash=hashlib.sha256(_raw_bytes(groundnet_xml_text)).hexdigest(),
        parking=ai.parking,
        nodes=ai.nodes,
        segments=ai.segments,
        runways=ai.runways,
        frequencies=ai.frequencies,
        taxi_graph=build_taxi_graph(ai.nodes, ai.segments),
    )

    # Runway thresholds/ILS and (when provided) frequencies are not reliably
    # inferable by the model — take them from the deterministic parser, which
    # folds in the authoritative in-sim airportinfo.  Cheap, local, no network.
    if airportinfo:
        code_pic = parser_code.parse_groundnet(
            groundnet_xml_text, icao, airportinfo=airportinfo
        )
        picture = picture.model_copy(
            update={
                "runways": code_pic.runways or picture.runways,
                "frequencies": code_pic.frequencies,
            }
        )

    _warn_on_divergence(icao, groundnet_xml_text, picture)
    return picture
