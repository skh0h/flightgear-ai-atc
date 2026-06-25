"""
Gemini-backed groundnet parser — the online path.

Calls the code parser first to get all geometry, then asks Gemini to label
any unnamed taxiway segments.  This avoids re-emitting the entire
AirportPicture and prevents hitting the output-token cap on large airports
(KSFO: 1144 nodes, 3131 arcs).

The offline contract is unchanged: any ``OfflineError`` from the client
(missing key, network down, auth/quota failure, retries exhausted) is caught
and the code-parser picture is returned directly with ``source="code"``, so
callers always get an :class:`AirportPicture`.
"""

from __future__ import annotations

import logging

from sidecar import parser_code
from sidecar.airport_picture import (
    AIAirportResponse,
    AirportPicture,
)
from sidecar.gemini_client import GeminiClient, OfflineError

_log = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """You are an expert FlightGear airport ground-network analyst.

Airport ICAO: {icao}

Below is the airport's groundnet.xml.  Your ONLY task is to infer taxiway
names for segments whose name attribute is empty or missing.

Return a JSON list of objects — one per segment you can name — with fields:
  "begin"  : integer node index (from the source XML)
  "end"    : integer node index (from the source XML)
  "name"   : the taxiway label you infer (e.g. "Alpha", "B", "Taxiway C")

Rules:
- Include ONLY segments that currently have no name (or an empty name).
- Do NOT echo segments that already have a name in the source.
- Do NOT include any geometry, coordinates, parking spots, runways, or
  frequencies — label list ONLY.
- Keep begin/end index values identical to the source XML.
- Infer names from the airport's geometry and standard taxiway-naming
  conventions for {icao}.

groundnet.xml:
{xml}
"""


def parse_with_ai(
    icao: str,
    groundnet_xml_text: str | bytes,
    gemini_client: GeminiClient,
    *,
    airportinfo: dict | None = None,
    model: str | None = None,
) -> AirportPicture:
    """Parse a groundnet with Gemini labeling, falling back to code parser offline.

    The code parser runs unconditionally to produce all geometry.  Gemini then
    supplies taxiway labels for unnamed segments; those labels are merged onto
    the code-parser result before returning.

    Args:
        icao: ICAO identifier to stamp on the result.
        groundnet_xml_text: Raw groundnet XML (text or bytes).
        gemini_client: The configured :class:`GeminiClient`.
        airportinfo: Optional in-sim runway/frequency data; forwarded to
            :func:`parser_code.parse_groundnet` which handles it authoritatively.
        model: Optional Gemini model override.

    Returns:
        An :class:`AirportPicture` — ``source="ai"`` on success, ``source="code"``
        if Gemini is unavailable.
    """
    # Step 1: always get full geometry from the deterministic code parser.
    base = parser_code.parse_groundnet(
        groundnet_xml_text, icao, airportinfo=airportinfo
    )

    # Step 2: ask Gemini for taxiway labels only.
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
        return base  # source="code", all fields already set

    # Step 3: merge AI labels onto code-parser segments.
    # Build an undirected lookup: both (begin,end) and (end,begin) -> name.
    label_map: dict[tuple[int, int], str] = {}
    for lbl in ai.taxiway_labels:
        if lbl.name:
            label_map[(lbl.begin, lbl.end)] = lbl.name
            label_map[(lbl.end, lbl.begin)] = lbl.name

    if label_map:
        merged_segments = []
        for seg in base.segments:
            key = (seg.begin, seg.end)
            ai_name = label_map.get(key)
            if ai_name is not None:
                seg = seg.model_copy(update={"name": ai_name})
            merged_segments.append(seg)
    else:
        merged_segments = list(base.segments)

    # Step 4: return code-parser picture with AI labels applied and source="ai".
    # groundnet_hash, generated_at, and taxi_graph stay exactly as code-parsed.
    return base.model_copy(
        update={
            "source": "ai",
            "segments": merged_segments,
        }
    )
