"""
Sidecar entry point: the event loop that ties the pipeline to FlightGear.

Flow per request (Nasal sets ``/ai-atc/request/trigger`` = 1):

    poll trigger -> read request + aircraft state -> get/parse+cache the airport
    picture -> route -> phraseology -> speak -> write response props + status ->
    reset trigger.

Everything is dependency-injected on :class:`Sidecar`, so the orchestration is
unit-testable with a fake bridge/client and the real cache/parsers/router.  The
``main()`` wrapper wires the real implementations and installs SIGINT/SIGTERM
handlers for a clean shutdown.  Live in-sim verification is Phase 5.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import logging
import math
import signal
import sys
import time
from collections.abc import Callable

from sidecar import (
    career,
    coach,
    guardrail,
    i18n,
    kneeboard as kneeboard_mod,
    metar,
    parser_ai,
    personality,
    phraseology,
    routing,
    scenario as scenario_mod,
    traffic,
)
from sidecar.airport_picture import (
    AirportPicture,
    Frequencies,
    Runway,
    TrafficSnapshot,
)
from sidecar.blackboard import Blackboard
from sidecar.cache import PictureCache
from sidecar.config import Settings, load
from sidecar.fg_bridge import BridgeError, FGTelnetBridge
from sidecar.gemini_client import GeminiClient
from sidecar.phraseology import Clearance
from sidecar.runway_selection import build_taxi_clearance
from sidecar.session_log import SessionMemory
from sidecar.state import FlightStateMachine
from sidecar.stt import grade_readback
from sidecar.tts import TTS, make_tts_backend

_log = logging.getLogger(__name__)

# --- mailbox / state property paths -----------------------------------------
REQ_TYPE = "/ai-atc/request/type"
REQ_CALLSIGN = "/ai-atc/request/callsign"
REQ_RUNWAY = "/ai-atc/request/runway"
REQ_TRIGGER = "/ai-atc/request/trigger"
RESP_TEXT = "/ai-atc/response/text"
RESP_READY = "/ai-atc/response/ready"
STATUS = "/ai-atc/status"

# --- Phase 5: pilot readback grading (Nasal publishes heard text; sidecar grades) ---
READBACK_HEARD = "/ai-atc/readback/heard"
READBACK_RESULT = "/ai-atc/readback/result"
AIRPORT_ID = "/sim/presets/airport-id"
POS_LAT = "/position/latitude-deg"
POS_LON = "/position/longitude-deg"
AIRCRAFT_ID = "/sim/aircraft-id"

# --- diversion: nearest-airport contract (Nasal publishes, sidecar reads) ----
NEAREST_AIRPORT_ICAO = "/ai-atc/nearest-airport/icao"
NEAREST_AIRPORT_NAME = "/ai-atc/nearest-airport/name"

# --- Phase 7: flight-phase state machine + IFR request mailbox --------------
# Sidecar writes the advisory flight phase; Nasal may publish the IFR request
# fields used to build a CRAFT clearance (all optional, best-effort reads).
FLIGHT_PHASE = "/ai-atc/flight-phase"
REQ_ROUTE = "/ai-atc/request/route"
REQ_DESTINATION = "/ai-atc/request/destination"
REQ_ALTITUDE = "/ai-atc/request/altitude"
REQ_SQUAWK = "/ai-atc/request/squawk"

# --- Phase 8: grounding / data integrations ---------------------------------
# Nasal (or a future grounding helper) publishes the current airspace class and
# any advisory warning; the sidecar reads them for an ``airspace_check`` reply.
AIRSPACE_CLASS = "/ai-atc/airspace/class"
AIRSPACE_WARN = "/ai-atc/airspace/warning"

# --- Phase 4: personality / session memory / modes --------------------------
# Nasal publishes MODE + LOCAL_HOUR; sidecar publishes CONTROLLER_NAME.
MODE = "/ai-atc/mode"  # normal | student | checkride (default normal)
LOCAL_HOUR = "/ai-atc/local-hour"  # int local hour (0-23); default neutral 12
CONTROLLER_NAME = "/ai-atc/controller/name"  # sidecar writes the persona name
# Stable seed for the persona created at startup (before any callsign is known).
_DEFAULT_PERSONA_SEED = "ai-atc-tower"

# --- sidecar heartbeat / mode (Task 2) — sidecar writes, Nasal reads --------
HEARTBEAT = "/ai-atc/sidecar/heartbeat"
SIDECAR_MODE = "/ai-atc/sidecar/mode"

# --- airport data pipe (Item 3) — Nasal publishes here, sidecar reads -------
AP_RUNWAY_COUNT = "/ai-atc/airport/runway_count"
AP_RUNWAY_PREFIX = "/ai-atc/airport/runway"  # + "[N]/field"
AP_FREQ_GROUND = "/ai-atc/airport/freq/ground"
AP_FREQ_TOWER = "/ai-atc/airport/freq/tower"
AP_FREQ_ATIS = "/ai-atc/airport/freq/atis"
AP_FREQ_APPROACH = "/ai-atc/airport/freq/approach"
AP_FREQ_DEPARTURE = "/ai-atc/airport/freq/departure"

# --- Mode B: live AI traffic (sidecar reads /ai/models via telnet) ----------
AI_MODELS_PREFIX = "/ai/models/aircraft"  # + "[N]/field"
# Sidecar writes these for the panel to display (Mode B contract):
TRAFFIC_COUNT = "/ai-atc/traffic/count"
TRAFFIC_SUMMARY = "/ai-atc/traffic/summary"
# Phase 6: living-world ambient background chatter (sidecar writes one line).
CHATTER = "/ai-atc/chatter"

# --- Phase 9: gamification / training --------------------------------------
# Sidecar writes the rendered kneeboard card here for the panel to display.
KNEEBOARD = "/ai-atc/kneeboard"

# --- Phase 10: advisory output guardrail (#49) ------------------------------
# Sidecar writes any deterministic validation issues for the just-rendered
# clearance here (newline-joined, "" when clean).  ADVISORY ONLY: the clearance
# in RESP_TEXT is always published regardless of issues.
GUARDRAIL = "/ai-atc/guardrail"


def _is_true(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes")


# Map a clearance to the controller position whose voice should speak it.  Used
# only to colour the TTS voice; never affects RESP_TEXT/RESP_READY.
_GROUND_TYPES = frozenset({"pushback", "taxi"})
_TOWER_TYPES = frozenset({"takeoff"})
_APPROACH_TYPES = frozenset({"approach", "ils", "airfield_in_sight"})


def role_for_clearance(clearance: "Clearance | None") -> str:
    """Return the ATC role ({ground,tower,approach}) for a clearance's voice.

    Ground works pushback/taxi; arrivals (approach/ils/visual) get the approach
    voice; everything else (takeoff, emergencies, relief, None) speaks as tower.
    """
    ctype = ((getattr(clearance, "clearance_type", "") or "")).lower()
    if ctype in _GROUND_TYPES:
        return "ground"
    if ctype in _APPROACH_TYPES:
        return "approach"
    return "tower"


def _to_float(value: str, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _clean_fg_str(value: str) -> str:
    """FG telnet serializes a bool-false property as the token 'false'.
    For string-valued request fields that artifact must be treated as empty."""
    s = (value or "").strip()
    return "" if s.lower() in ("false", "true") else s


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in nautical miles between two lat/lon points."""
    R_NM = 3440.065
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R_NM * 2 * math.asin(math.sqrt(a))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing in degrees [0, 360) from (lat1, lon1) to (lat2, lon2)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    x = math.sin(dlam) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def groundnet_path_for(icao: str, *, base: str = "fixtures") -> str:
    """Conventional on-disk location of a groundnet (overridable in-sim)."""
    return f"{base}/{icao}.groundnet.xml"


def _default_groundnet_loader(icao: str) -> str | None:
    """Load a groundnet XML for ``icao`` from the fixtures dir, or None."""
    if not icao:
        return None
    try:
        with open(groundnet_path_for(icao), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        _log.warning("no groundnet file for %s", icao)
        return None


def merge_airport_mailbox(
    picture: AirportPicture, bridge: "FGTelnetBridge"
) -> AirportPicture:
    """Read runway + frequency data published by Nasal and merge into ``picture``.

    Reads from the ``/ai-atc/airport/...`` mailbox.  Safe when the mailbox is
    empty (``runway_count`` absent or zero) — the picture is returned unchanged.
    Merging is idempotent: calling twice with the same mailbox yields the same
    result.

    Mailbox property paths (written by Nasal, read here):

    - ``/ai-atc/airport/runway_count``          — number of runway entries
    - ``/ai-atc/airport/runway[N]/id``           — runway identifier (e.g. "28L")
    - ``/ai-atc/airport/runway[N]/heading``      — magnetic heading
    - ``/ai-atc/airport/runway[N]/thr_lat``      — threshold latitude
    - ``/ai-atc/airport/runway[N]/thr_lon``      — threshold longitude
    - ``/ai-atc/airport/runway[N]/length``       — length in feet
    - ``/ai-atc/airport/runway[N]/ils_freq``     — ILS frequency string (optional)
    - ``/ai-atc/airport/freq/ground``            — ground control MHz
    - ``/ai-atc/airport/freq/tower``             — tower MHz
    - ``/ai-atc/airport/freq/atis``              — ATIS MHz
    - ``/ai-atc/airport/freq/approach``          — approach MHz
    - ``/ai-atc/airport/freq/departure``         — departure MHz

    Returns a new :class:`AirportPicture` with ``runways`` and ``frequencies``
    populated (other fields unchanged), or the original picture when the mailbox
    contains no runway data.
    """
    count_str = bridge.get(AP_RUNWAY_COUNT)
    try:
        count = int(count_str)
    except (TypeError, ValueError):
        count = 0
    if count <= 0:
        return picture

    runways: list[Runway] = []
    for i in range(count):
        prefix = f"{AP_RUNWAY_PREFIX}[{i}]"
        rwy_id = bridge.get(f"{prefix}/id") or ""
        if not rwy_id:
            continue
        try:
            heading = float(bridge.get(f"{prefix}/heading") or 0)
        except ValueError:
            heading = 0.0
        try:
            thr_lat = float(bridge.get(f"{prefix}/thr_lat") or 0)
        except ValueError:
            thr_lat = 0.0
        try:
            thr_lon = float(bridge.get(f"{prefix}/thr_lon") or 0)
        except ValueError:
            thr_lon = 0.0
        try:
            length = float(bridge.get(f"{prefix}/length") or 0)
        except ValueError:
            length = 0.0
        ils_freq = bridge.get(f"{prefix}/ils_freq") or None
        # Mode A: active-runway flag (absent/blank -> inactive).
        active = _is_true(bridge.get(f"{prefix}/active") or "")
        runways.append(Runway(
            id=rwy_id,
            heading=heading,
            thr_lat=thr_lat,
            thr_lon=thr_lon,
            length=length,
            ils_freq=ils_freq,
            active=active,
        ))

    def _freq(path: str) -> str | None:
        v = bridge.get(path)
        return v if v else None

    frequencies = Frequencies(
        ground=_freq(AP_FREQ_GROUND),
        tower=_freq(AP_FREQ_TOWER),
        atis=_freq(AP_FREQ_ATIS),
        approach=_freq(AP_FREQ_APPROACH),
        departure=_freq(AP_FREQ_DEPARTURE),
    )

    return picture.model_copy(update={"runways": runways, "frequencies": frequencies})


# ---------------------------------------------------------------------------
# Mode B: live AI traffic snapshotting + queue sequencing
# ---------------------------------------------------------------------------

def read_ai_traffic(
    bridge: "FGTelnetBridge",
    picture: AirportPicture,
    *,
    max_models: int = 64,
    max_snap_m: float = 150.0,
) -> list[TrafficSnapshot]:
    """Index-probe FlightGear's ``/ai/models`` and snap each aircraft to the net.

    Reads per aircraft ``i`` (like :func:`merge_airport_mailbox`):

    - ``/ai/models/aircraft[i]/valid``
    - ``/ai/models/aircraft[i]/callsign``
    - ``/ai/models/aircraft[i]/position/latitude-deg``
    - ``/ai/models/aircraft[i]/position/longitude-deg``
    - ``/ai/models/aircraft[i]/orientation/true-heading-deg``

    Each aircraft is snapped to the nearest taxi node
    (:func:`routing.nearest_node_with_distance`).  Snaps beyond ``max_snap_m``
    or sitting at the null island ``(0, 0)`` are dropped.  Probing stops at the
    first blank/invalid entry.  Every ``bridge.get`` is best-effort guarded so a
    flaky bridge never raises out of here.
    """
    def _get(path: str) -> str:
        try:
            return bridge.get(path) or ""
        except Exception:  # bridge is best-effort; treat as blank
            return ""

    snapshots: list[TrafficSnapshot] = []
    for i in range(max_models):
        prefix = f"{AI_MODELS_PREFIX}[{i}]"
        # Stop at the first invalid/blank entry (index-probe contract).
        if not _is_true(_get(f"{prefix}/valid")):
            break
        lat = _to_float(_get(f"{prefix}/position/latitude-deg"))
        lon = _to_float(_get(f"{prefix}/position/longitude-deg"))
        # Drop null-island / unpositioned entries but keep probing.
        if lat == 0.0 and lon == 0.0:
            continue
        callsign = _get(f"{prefix}/callsign").strip()
        heading = _to_float(_get(f"{prefix}/orientation/true-heading-deg"))
        node_index, snap_dist = routing.nearest_node_with_distance(picture, lat, lon)
        if node_index is None or snap_dist > max_snap_m:
            continue
        snapshots.append(
            TrafficSnapshot(
                callsign=callsign,
                lat=lat,
                lon=lon,
                heading=heading,
                node_index=node_index,
                snap_dist_m=snap_dist,
            )
        )
    return snapshots


def compute_traffic_queue(
    snapshots: list[TrafficSnapshot],
    user_node_index: int | None,
    picture: AirportPicture,
) -> tuple[int, str]:
    """Sequence ground traffic + the user into a departure queue.

    Deterministic rule: order every participant (the detected ground traffic
    plus the user, identified by ``user_node_index``) by how close they are to
    the nearest on-runway node — closer to the runway means lower queue number.
    Ties break on ``(is_user, callsign)`` so the ordering is fully stable for
    tests.  Returns ``(count, summary)`` where ``count`` is the number of ground
    traffic considered and ``summary`` is the one-line panel string per the
    Mode B contract.
    """
    count = len(snapshots)

    def _dist_to_runway(lat: float, lon: float) -> float:
        _idx, dist = routing.nearest_node_with_distance(
            picture, lat, lon, require_on_runway=True
        )
        return dist

    def _node_coord(idx: int | None) -> tuple[float, float] | None:
        if idx is None:
            return None
        for node in picture.nodes:
            if node.index == idx:
                return (node.lat, node.lon)
        return None

    # (distance_to_runway, is_user_flag, label, is_user) — sort is deterministic.
    participants: list[tuple[float, int, str, bool]] = []
    for snap in snapshots:
        label = snap.callsign or "traffic"
        participants.append((_dist_to_runway(snap.lat, snap.lon), 0, label, False))

    user_coord = _node_coord(user_node_index)
    user_dist = _dist_to_runway(*user_coord) if user_coord is not None else math.inf
    participants.append((user_dist, 1, "You", True))

    participants.sort(key=lambda p: (p[0], p[1], p[2]))

    user_pos = next(i for i, p in enumerate(participants) if p[3])
    user_number = user_pos + 1
    if user_pos == 0:
        summary = f"Ground traffic: {count}. You are number 1 for departure."
    else:
        ahead_label = participants[user_pos - 1][2]
        summary = (
            f"Ground traffic: {count}. "
            f"You are number {user_number}, behind {ahead_label}."
        )
    return count, summary


class Sidecar:
    """Owns the request/response loop. All collaborators are injected."""

    def __init__(
        self,
        settings: Settings,
        bridge: FGTelnetBridge,
        client: GeminiClient,
        cache: PictureCache,
        tts: TTS,
        *,
        groundnet_loader: Callable[[str], str | None] = _default_groundnet_loader,
    ) -> None:
        self.settings = settings
        self.bridge = bridge
        self.client = client
        self.cache = cache
        self.tts = tts
        self._groundnet_loader = groundnet_loader
        self._running = False
        # Phase 5: the most recently issued clearance, for readback grading.
        self._last_clearance: Clearance | None = None
        # Phase 4: a stable controller identity + bounded session memory.
        self.persona = personality.generate_persona(_DEFAULT_PERSONA_SEED)
        self.memory = SessionMemory()
        # Phase 7: advisory, forward-only flight-phase tracker (gate to gate).
        self.fsm = FlightStateMachine()
        # Phase 10: shared world-state blackboard (advisory; refreshed per request).
        self.blackboard = Blackboard()
        # Best-effort publish so the panel can show who is working the position.
        try:
            self.bridge.set(CONTROLLER_NAME, self.persona.name)
        except Exception:  # bridge may not be connected yet; republished in main()
            _log.debug("could not publish controller name at init", exc_info=True)

    # ------------------------------------------------------------------
    # Airport picture: cache -> AI/code parse -> cache
    # ------------------------------------------------------------------

    def get_airport_picture(
        self, icao: str, groundnet_xml: str
    ) -> AirportPicture:
        groundnet_hash = hashlib.sha256(groundnet_xml.encode("utf-8")).hexdigest()
        cached = self.cache.get(icao, groundnet_hash)
        if cached is not None:
            return cached
        picture = parser_ai.parse_with_ai(
            icao, groundnet_xml, self.client,
            ai_taxiway_labels=self.settings.ai_taxiway_labels,
        )
        self.cache.put(picture)
        return picture

    # ------------------------------------------------------------------
    # Clearance assembly
    # ------------------------------------------------------------------

    def _fetch_metar_wind(self, icao: str) -> tuple[float, float] | None:
        """Fetch METAR wind best-effort; returns None on any failure."""
        if not self.settings.metar_enabled:
            return None
        try:
            return metar.get_wind(icao)
        except Exception:
            _log.warning("METAR fetch unexpectedly raised for %s", icao, exc_info=True)
            return None

    def _build_clearance(
        self, req_type: str, callsign: str, picture: AirportPicture | None
    ) -> Clearance:
        active_runway = _clean_fg_str(self.bridge.get(REQ_RUNWAY))
        eff_callsign = callsign or "Aircraft"
        eff_type = req_type or "taxi"
        icao = (self.bridge.get(AIRPORT_ID) or "").strip()
        aircraft_type = (self.bridge.get(AIRCRAFT_ID) or "").strip()

        # Auto-select path: taxi request + no explicit runway + picture available
        if picture is not None and eff_type == "taxi" and not active_runway:
            try:
                lat = _to_float(self.bridge.get(POS_LAT))
                lon = _to_float(self.bridge.get(POS_LON))
                wind = self._fetch_metar_wind(icao)
                wind_dir = wind[0] if wind is not None else None
                wind_kt = wind[1] if wind is not None else None
                clearance = build_taxi_clearance(
                    picture, eff_callsign, lat, lon,
                    wind_dir=wind_dir, wind_kt=wind_kt,
                )
                clearance.aircraft_type = aircraft_type
                return clearance
            except Exception:
                _log.warning("auto runway selection failed", exc_info=True)
                # Fall through to template clearance with no runway

        # Explicit-runway path: route to the requested runway + coverage gate
        taxiways: list[str] = []
        if picture is not None and eff_type == "taxi" and active_runway:
            try:
                lat = _to_float(self.bridge.get(POS_LAT))
                lon = _to_float(self.bridge.get(POS_LON))
                start = routing.nearest_node(picture, lat, lon)
                goal = routing.runway_goal_node(picture, active_runway)
                if start is not None and goal is not None:
                    route = routing.find_route(picture, start, goal)
                    taxiways = routing.taxiways_for_clearance(route, picture)
            except Exception:  # routing is best-effort; templates still work
                _log.warning("route computation failed", exc_info=True)

        # Arrival path: compute distance/bearing from aircraft to runway threshold
        remarks = ""
        if eff_type in ("approach", "ils", "airfield_in_sight"):
            try:
                lat = _to_float(self.bridge.get(POS_LAT))
                lon = _to_float(self.bridge.get(POS_LON))
                if picture is not None:
                    for rwy in picture.runways:
                        if rwy.thr_lat != 0.0 and rwy.thr_lon != 0.0:
                            dist_nm = _haversine_nm(lat, lon, rwy.thr_lat, rwy.thr_lon)
                            brg = _bearing_deg(lat, lon, rwy.thr_lat, rwy.thr_lon)
                            remarks = f"{dist_nm:.0f} nm, {brg:.0f} degrees"
                            break
            except Exception:
                _log.debug("distance/bearing computation failed", exc_info=True)

        # IFR clearance path: best-effort read of the CRAFT request fields
        # (route/destination/altitude/squawk) plus the departure frequency so
        # phraseology can render a full CRAFT clearance.  All guarded; any read
        # failure simply leaves the fields empty (generic IFR clearance).
        ifr_route = ifr_dest = ifr_alt = ifr_squawk = ifr_dep_freq = ""
        if eff_type == "ifr_clearance":
            try:
                ifr_route = _clean_fg_str(self.bridge.get(REQ_ROUTE) or "")
                ifr_dest = _clean_fg_str(self.bridge.get(REQ_DESTINATION) or "")
                ifr_alt = _clean_fg_str(self.bridge.get(REQ_ALTITUDE) or "")
                ifr_squawk = _clean_fg_str(self.bridge.get(REQ_SQUAWK) or "")
                if picture is not None and picture.frequencies is not None:
                    ifr_dep_freq = picture.frequencies.departure or ""
                if not ifr_dep_freq:
                    ifr_dep_freq = _clean_fg_str(self.bridge.get(AP_FREQ_DEPARTURE) or "")
            except Exception:
                _log.debug("ifr clearance field read failed", exc_info=True)

        # Diversion path: best-effort nearest-airport lookup published by Nasal.
        divert_target = ""
        if eff_type == "diversion":
            try:
                d_icao = _clean_fg_str(self.bridge.get(NEAREST_AIRPORT_ICAO) or "")
                d_name = _clean_fg_str(self.bridge.get(NEAREST_AIRPORT_NAME) or "")
                if d_icao:
                    divert_target = f"{d_icao} {d_name}".strip()
            except Exception:
                _log.debug("nearest-airport read failed", exc_info=True)

        # Phase 8: SimBrief plan confirmation — reuse the IFR request mailbox
        # (route/destination/altitude) to confirm the imported flight plan.
        sb_route = sb_dest = sb_alt = ""
        if eff_type == "simbrief":
            try:
                sb_route = _clean_fg_str(self.bridge.get(REQ_ROUTE) or "")
                sb_dest = _clean_fg_str(self.bridge.get(REQ_DESTINATION) or "")
                sb_alt = _clean_fg_str(self.bridge.get(REQ_ALTITUDE) or "")
            except Exception:
                _log.debug("simbrief field read failed", exc_info=True)

        # Phase 8: airspace check — current class + advisory published by Nasal.
        airspace_class = airspace_warning = ""
        if eff_type == "airspace_check":
            try:
                airspace_class = _clean_fg_str(self.bridge.get(AIRSPACE_CLASS) or "")
                airspace_warning = _clean_fg_str(self.bridge.get(AIRSPACE_WARN) or "")
            except Exception:
                _log.debug("airspace check read failed", exc_info=True)

        return Clearance(
            callsign=eff_callsign,
            clearance_type=eff_type,
            taxi_route=taxiways,
            active_runway=active_runway,
            hold_short=active_runway if eff_type == "taxi" else "",
            aircraft_type=aircraft_type,
            remarks=remarks,
            divert_target=divert_target,
            # IFR CRAFT fields double as SimBrief plan fields (mutually exclusive
            # by req type, so ``or`` simply picks whichever path populated them).
            route=ifr_route or sb_route,
            destination=ifr_dest or sb_dest,
            altitude=ifr_alt or sb_alt,
            squawk=ifr_squawk,
            # ``frequency`` stays "" for ctaf so phrase_offline adds no controller
            # contact tail; it is only the CRAFT departure freq for ifr_clearance.
            frequency=ifr_dep_freq,
            airspace_class=airspace_class,
            airspace_warning=airspace_warning,
        )

    # ------------------------------------------------------------------
    # Session logging
    # ------------------------------------------------------------------

    def _append_session_record(
        self,
        *,
        airport_id: str,
        lat: float,
        lon: float,
        req_type: str,
        callsign: str,
        runway: str,
        aircraft_type: str,
        picture: AirportPicture | None,
        response_text: str,
    ) -> None:
        """Append one JSONL record to the session log (best-effort)."""
        log_path = self.settings.session_log_path
        if not log_path:
            return
        record = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "airport_id": airport_id,
            "lat": lat,
            "lon": lon,
            "req_type": req_type,
            "callsign": callsign,
            "runway": runway,
            "aircraft_type": aircraft_type,
            "picture_json": json.loads(picture.model_dump_json()) if picture else None,
            "response_text": response_text,
        }
        try:
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        except Exception:
            _log.warning("session log write failed", exc_info=True)

    # ------------------------------------------------------------------
    # Phase 4: personality / modes / position relief
    # ------------------------------------------------------------------

    def _apply_mode_nuance(self, clearance: Clearance, mode: str) -> None:
        """Add a student/checkride nuance to a clearance's remarks (best-effort).

        ``normal`` (the default) leaves the clearance untouched so existing
        exact-template behaviour is preserved.
        """
        if mode == "student":
            extra = "Take your time, and let me know if you need anything repeated."
        elif mode == "checkride":
            extra = "Read back all instructions."
        else:
            return
        clearance.remarks = (
            f"{clearance.remarks} {extra}".strip() if clearance.remarks else extra
        )

    def _relief_handoff(self, callsign: str, context: str, mood: str) -> str:
        """Regenerate the controller persona and voice a position-relief briefing.

        A new persona is derived from a fresh seed, ``CONTROLLER_NAME`` is
        republished, and a briefing built from recent session memory is voiced
        (offline template when the model is unavailable).
        """
        new_seed = f"{callsign}-relief-{self.memory.count}"
        self.persona = personality.generate_persona(new_seed)
        try:
            self.bridge.set(CONTROLLER_NAME, self.persona.name)
        except Exception:  # republish is best-effort
            _log.debug("could not republish controller name", exc_info=True)
        remarks = f"This is {self.persona.name} taking over the position."
        if context:
            remarks += " Recent activity:\n" + context
        clearance = Clearance(
            callsign=callsign,
            clearance_type="relief_handoff",
            remarks=remarks,
        )
        return phraseology.phrase_online(
            clearance,
            self.client,
            context=context,
            persona=self.persona,
            mood=mood,
        )

    # ------------------------------------------------------------------
    # Phase 5: pilot readback grading
    # ------------------------------------------------------------------

    def _handle_readback(self) -> None:
        """Grade the heard readback against the most recent clearance.

        Best-effort throughout: any failure still writes a usable RESP_TEXT and
        sets RESP_READY so the UI never hangs.  Writes a human-readable verdict
        to READBACK_RESULT and voices an approval or a correction.
        """
        self.bridge.set(STATUS, "processing")
        try:
            heard = _clean_fg_str(self.bridge.get(READBACK_HEARD) or "")
        except Exception:
            heard = ""

        clearance = self._last_clearance
        result_text = ""
        resp_text = ""
        try:
            if clearance is None:
                result_text = "No active clearance to read back."
                resp_text = "Say again, no clearance is active."
            else:
                expected = phraseology.expected_readback(clearance)
                graded = grade_readback(expected, heard)
                callsign = clearance.callsign or "Aircraft"
                if graded.ok:
                    result_text = f"Readback correct (score {graded.score:.2f})."
                    resp_text = f"{callsign}, readback correct."
                else:
                    missing = ", ".join(graded.missing) or "(none)"
                    result_text = (
                        f"Readback incomplete (score {graded.score:.2f}); "
                        f"missing: {missing}."
                    )
                    resp_text = f"{callsign}, negative. I say again, {expected}."
                # Phase 9: in student mode, append friendly coaching feedback.
                try:
                    mode = (self.bridge.get(MODE) or "normal").strip().lower()
                    if mode == "student":
                        resp_text = (
                            f"{resp_text} {coach.coach_feedback(expected, heard)}"
                        ).strip()
                except Exception:
                    _log.debug("coach feedback failed", exc_info=True)
        except Exception:
            _log.warning("readback grading failed", exc_info=True)
            result_text = result_text or "Readback could not be processed."
            resp_text = resp_text or "Standby."

        try:
            self.bridge.set(READBACK_RESULT, result_text)
        except Exception:
            _log.debug("could not publish readback result", exc_info=True)
        try:
            self.tts.speak(resp_text, role=role_for_clearance(clearance))
        except Exception:
            _log.debug("readback speak failed", exc_info=True)

        self.bridge.set(RESP_TEXT, resp_text)
        self.bridge.set(RESP_READY, 1)
        self.bridge.set(STATUS, "idle")
        self.bridge.set(REQ_TRIGGER, 0)

    # ------------------------------------------------------------------
    # Phase 9: training / gamification announce handlers
    # ------------------------------------------------------------------

    def _finish_announce(self, text: str, role: str) -> None:
        """Voice an announce reply and finalise the mailbox (best-effort)."""
        try:
            self.tts.speak(text, role=role)
        except Exception:
            _log.debug("announce speak failed", exc_info=True)
        self.bridge.set(RESP_TEXT, text)
        self.bridge.set(RESP_READY, 1)
        self.bridge.set(STATUS, "idle")
        self.bridge.set(REQ_TRIGGER, 0)

    def _handle_scenario(self, callsign: str) -> None:
        """Generate a deterministic training scenario and voice its summary."""
        self.bridge.set(STATUS, "processing")
        text = ""
        try:
            icao = (self.bridge.get(AIRPORT_ID) or "").strip()
            seed = f"{callsign}-{self.memory.count}"
            s = scenario_mod.generate_scenario(seed, airport=icao)
            summary = scenario_mod.scenario_summary(s)
            clearance = Clearance(
                callsign=callsign, clearance_type="scenario", remarks=summary
            )
            text = phraseology.phrase_online(clearance, self.client, persona=self.persona)
        except Exception:
            _log.warning("scenario generation failed", exc_info=True)
            text = text or "Stand by — unable to generate a training scenario."
        self._finish_announce(text, "tower")

    def _handle_kneeboard(self, callsign: str) -> None:
        """Build a kneeboard from the current picture + METAR wind; publish + voice."""
        self.bridge.set(STATUS, "processing")
        text = ""
        try:
            icao = (self.bridge.get(AIRPORT_ID) or "").strip()
            groundnet_xml = self._groundnet_loader(icao)
            picture = (
                self.get_airport_picture(icao, groundnet_xml)
                if groundnet_xml
                else None
            )
            if picture is not None:
                picture = merge_airport_mailbox(picture, self.bridge)

            wind = self._fetch_metar_wind(icao)
            wind_dir = int(wind[0]) if wind is not None else None
            wind_kt = int(wind[1]) if wind is not None else None

            runways: list[str] = []
            freqs: dict[str, str] = {}
            if picture is not None:
                active = [r.id for r in picture.runways if getattr(r, "active", False)]
                runways = active or [r.id for r in picture.runways]
                f = picture.frequencies
                if f is not None:
                    for label, value in (
                        ("Ground", f.ground),
                        ("Tower", f.tower),
                        ("ATIS", f.atis),
                        ("Approach", f.approach),
                        ("Departure", f.departure),
                    ):
                        if value:
                            freqs[label] = value

            card = kneeboard_mod.build_kneeboard(
                icao=icao,
                wind_dir=wind_dir,
                wind_kt=wind_kt,
                runways=runways,
                freqs=freqs,
            )
            try:
                self.bridge.set(KNEEBOARD, card)
            except Exception:
                _log.debug("could not publish kneeboard", exc_info=True)

            summary = (
                f"kneeboard updated for {icao or 'the field'}, "
                f"{len(runways)} active runway(s)."
            )
            clearance = Clearance(
                callsign=callsign, clearance_type="kneeboard", remarks=summary
            )
            text = phraseology.phrase_online(clearance, self.client, persona=self.persona)
        except Exception:
            _log.warning("kneeboard build failed", exc_info=True)
            text = text or "Stand by — unable to build the kneeboard."
        self._finish_announce(text, "tower")

    def _handle_career(self, callsign: str) -> None:
        """Load career stats (if configured) and voice the current rank/points."""
        self.bridge.set(STATUS, "processing")
        text = ""
        try:
            path = getattr(self.settings, "career_path", "") or ""
            stats = career.load_career(path) if path else career.CareerStats()
            rank = career.career_rank(stats.points)
            summary = (
                f"career rank {rank}, {stats.points} points, "
                f"{stats.landings} landings logged."
            )
            clearance = Clearance(
                callsign=callsign, clearance_type="career", remarks=summary
            )
            text = phraseology.phrase_online(clearance, self.client, persona=self.persona)
        except Exception:
            _log.warning("career summary failed", exc_info=True)
            text = text or "Stand by — career stats are unavailable."
        self._finish_announce(text, "tower")

    # ------------------------------------------------------------------
    # One request
    # ------------------------------------------------------------------

    def handle_trigger(self) -> None:
        req_type = (self.bridge.get(REQ_TYPE) or "taxi").strip()
        callsign = _clean_fg_str(self.bridge.get(REQ_CALLSIGN)) or "Aircraft"

        # Phase 7: fold the request into the advisory flight-phase machine and
        # publish the current phase.  Advisory only: on_request never raises and
        # the publish is best-effort, so this never breaks RESP_TEXT/RESP_READY.
        try:
            phase = self.fsm.on_request(req_type)
            self.bridge.set(FLIGHT_PHASE, phase)
        except Exception:
            _log.debug("flight-phase update failed", exc_info=True)

        # Phase 10: refresh the shared world-state blackboard (advisory only;
        # never feeds back into the reply, so this can never break it).  Cheap,
        # offline reads — no METAR/network fetch on the hot path.
        try:
            try:
                tcount = int(str(self.bridge.get(TRAFFIC_COUNT) or "0").strip() or "0")
            except (TypeError, ValueError):
                tcount = 0
            self.blackboard.update(
                phase=self.fsm.phase,
                airport=(self.bridge.get(AIRPORT_ID) or "").strip(),
                traffic_count=tcount,
                airspace_class=_clean_fg_str(self.bridge.get(AIRSPACE_CLASS) or "") or "G",
                mode=(self.bridge.get(MODE) or "normal").strip().lower() or "normal",
                controller=self.persona.name,
                language=self.settings.language,
                region=self.settings.region,
            )
        except Exception:
            _log.debug("blackboard update failed", exc_info=True)

        if req_type == "cancel":
            self.bridge.set(STATUS, "idle")
            self.bridge.set(REQ_TRIGGER, 0)
            return

        if req_type == "readback":
            self._handle_readback()
            return

        # Phase 9: training / gamification announce types.  Each is a
        # self-contained, best-effort handler that always writes RESP_TEXT/
        # RESP_READY and resets the mailbox (never breaks the request loop).
        if req_type == "scenario":
            self._handle_scenario(callsign)
            return
        if req_type == "kneeboard":
            self._handle_kneeboard(callsign)
            return
        if req_type == "career":
            self._handle_career(callsign)
            return

        self.bridge.set(STATUS, "processing")
        aircraft_type = ""
        clearance: Clearance | None = None
        try:
            icao = (self.bridge.get(AIRPORT_ID) or "").strip()
            lat = _to_float(self.bridge.get(POS_LAT))
            lon = _to_float(self.bridge.get(POS_LON))

            # Phase 4 personality context (best-effort; never breaks the reply).
            mode = (self.bridge.get(MODE) or "normal").strip().lower() or "normal"
            try:
                local_hour = int(float(self.bridge.get(LOCAL_HOUR) or 12))
            except (TypeError, ValueError):
                local_hour = 12
            mood = personality.mood_for(
                self.memory.count,
                quiet_night=personality.is_quiet_night(local_hour),
            )
            context = self.memory.recent_context()

            if req_type == "relief_handoff":
                picture = None
                text = self._relief_handoff(callsign, context, mood)
            else:
                groundnet_xml = self._groundnet_loader(icao)
                picture = (
                    self.get_airport_picture(icao, groundnet_xml)
                    if groundnet_xml
                    else None
                )
                # Merge runway/frequency data Nasal has published into the picture
                if picture is not None:
                    picture = merge_airport_mailbox(picture, self.bridge)
                clearance = self._build_clearance(req_type, callsign, picture)
                self._apply_mode_nuance(clearance, mode)
                aircraft_type = clearance.aircraft_type
                # Phase 6: best-effort wake-turbulence caution for departures and
                # arrivals — append separation advice for the nearest preceding
                # heavier traffic.  Never breaks the clearance reply.
                if picture is not None and req_type in ("takeoff", "approach", "ils"):
                    try:
                        dep_snaps = read_ai_traffic(self.bridge, picture)
                        lead_cs = ""
                        lead_d = math.inf
                        for s in dep_snaps:
                            if traffic.wake_category(s.callsign) in ("heavy", "super"):
                                d = _haversine_nm(lat, lon, s.lat, s.lon)
                                if d < lead_d:
                                    lead_d, lead_cs = d, s.callsign
                        if lead_cs:
                            advice = traffic.separation_advice(
                                lead_cs, clearance.aircraft_type
                            )
                            if advice:
                                clearance.remarks = (
                                    f"{clearance.remarks} {advice}".strip()
                                    if clearance.remarks
                                    else advice
                                )
                    except Exception:
                        _log.debug("wake separation advice failed", exc_info=True)
                # Remember the issued clearance so a later readback can be graded.
                self._last_clearance = clearance
                text = phraseology.phrase_online(
                    clearance,
                    self.client,
                    context=context,
                    persona=self.persona,
                    mood=mood,
                    language=self.settings.language,
                )
                # Mode B: best-effort live traffic sequencing for taxi requests.
                # Wrapped so any traffic failure NEVER breaks the clearance reply.
                if picture is not None and req_type == "taxi":
                    try:
                        from sidecar.runway_selection import (  # noqa: PLC0415
                            start_node_for_position,
                        )
                        user_node = start_node_for_position(picture, lat, lon)
                        snapshots = read_ai_traffic(self.bridge, picture)
                        count, summary = compute_traffic_queue(
                            snapshots, user_node, picture
                        )
                        self.bridge.set(TRAFFIC_COUNT, count)
                        self.bridge.set(TRAFFIC_SUMMARY, summary)
                        # Phase 6: publish one deterministic ambient chatter line.
                        chatter = traffic.ambient_chatter(
                            snapshots, picture, seed=f"{icao}-{self.memory.count}"
                        )
                        if chatter:
                            self.bridge.set(CHATTER, chatter[0])
                    except Exception:
                        _log.debug("traffic sequencing failed", exc_info=True)
        except Exception:
            _log.exception("failed to handle request")
            self.bridge.set(RESP_TEXT, "Stand by — unable to process that request.")
            self.bridge.set(RESP_READY, 1)
            self.bridge.set(STATUS, "idle")
            self.bridge.set(REQ_TRIGGER, 0)
            return

        # Phase 10: regional wording substitution (#4) — best-effort; the
        # default "us" pack (and any unknown region) is a no-op.  Applied to the
        # final rendered text so the offline templates stay region-neutral.
        try:
            text = i18n.apply_region(text, self.settings.region)
        except Exception:
            _log.debug("region substitution failed", exc_info=True)

        # Phase 10: advisory output guardrail (#49) — validate the rendered
        # clearance and publish any issues.  ADVISORY ONLY: RESP_TEXT is still
        # published regardless; a guardrail failure never blocks the reply.
        try:
            active_ids: list[str] = []
            if picture is not None:
                active_ids = [
                    r.id for r in picture.runways if getattr(r, "active", False)
                ]
            result = guardrail.validate_clearance(
                text, callsign=callsign, active_runways=active_ids or None
            )
            self.bridge.set(GUARDRAIL, "\n".join(result.issues) if result.issues else "")
        except Exception:
            _log.debug("guardrail validation failed", exc_info=True)

        # Remember this interaction so later transmissions have continuity.
        try:
            self.memory.remember(req_type, callsign, text)
        except Exception:  # session memory is best-effort
            _log.debug("session memory update failed", exc_info=True)

        self._append_session_record(
            airport_id=icao,
            lat=lat,
            lon=lon,
            req_type=req_type,
            callsign=callsign,
            runway=(self.bridge.get(REQ_RUNWAY) or "").strip(),
            aircraft_type=aircraft_type,
            picture=picture,
            response_text=text,
        )
        # Voice the reply with the controller position's voice (best-effort).
        self.tts.speak(text, role=role_for_clearance(clearance))
        self.bridge.set(RESP_TEXT, text)
        self.bridge.set(RESP_READY, 1)
        self.bridge.set(STATUS, "idle")
        self.bridge.set(REQ_TRIGGER, 0)

    # ------------------------------------------------------------------
    # Loop
    # ------------------------------------------------------------------

    def poll_loop(
        self,
        *,
        interval: float = 0.1,
        max_iterations: int | None = None,
        _sleep: Callable[[float], None] = time.sleep,
        heartbeat_interval: float = 5.0,
    ) -> None:
        """Poll the trigger property and dispatch requests.

        ``max_iterations`` bounds the loop for tests; ``None`` runs until
        :meth:`stop` or a signal.  Bridge errors are logged and retried on the
        next tick rather than crashing the loop.

        Every ``heartbeat_interval`` seconds the loop increments
        ``/ai-atc/sidecar/heartbeat`` and writes ``/ai-atc/sidecar/mode`` so
        the Nasal add-on can detect whether the backend is alive.
        """
        self._running = True
        iterations = 0
        heartbeat_counter = 0
        elapsed_since_heartbeat = 0.0
        while self._running and (max_iterations is None or iterations < max_iterations):
            try:
                if _is_true(self.bridge.get(REQ_TRIGGER)):
                    self.handle_trigger()
            except BridgeError:
                _log.warning("bridge error during poll; will retry", exc_info=True)
            elapsed_since_heartbeat += interval
            if elapsed_since_heartbeat >= heartbeat_interval:
                elapsed_since_heartbeat = 0.0
                heartbeat_counter += 1
                mode = "ai" if self.client is not None and getattr(
                    self.settings, "gemini_api_key", None
                ) else "offline"
                try:
                    self.bridge.set(HEARTBEAT, heartbeat_counter)
                    self.bridge.set(SIDECAR_MODE, mode)
                except BridgeError:
                    pass  # heartbeat is best-effort
            iterations += 1
            _sleep(interval)

    def stop(self) -> None:
        self._running = False


def build_sidecar(settings: Settings) -> Sidecar:
    """Wire up the real collaborators from configuration."""
    bridge = FGTelnetBridge(settings.fg_telnet_host, settings.fg_telnet_port)
    client = GeminiClient(settings)
    cache = PictureCache(settings.cache_db_path)
    # Phase 5: pick the TTS backend from settings (piper when available, else
    # macOS ``say``).  The injectable backend test seam is unaffected — tests
    # construct TTS with their own recording backend and never call build_sidecar.
    tts = TTS(voice=settings.tts_voice, backend=make_tts_backend(settings))
    return Sidecar(settings, bridge, client, cache, tts)


def _run_selftest(*, telnet: bool = False) -> None:
    """Print connectivity status for Gemini (and optionally telnet), then exit."""
    import os  # noqa: PLC0415

    settings = load()
    logging.basicConfig(level=logging.WARNING)

    # --- Gemini check --------------------------------------------------------
    if not settings.gemini_api_key:
        print("Gemini: offline (GEMINI_API_KEY not set)")
        gemini_ok = False
    else:
        print("Gemini: checking...", end=" ", flush=True)
        try:
            from pydantic import BaseModel  # noqa: PLC0415

            class _Ping(BaseModel):
                ok: bool

            client = GeminiClient(settings)
            result = client.generate(
                "Reply with JSON {\"ok\": true}",
                _Ping,
            )
            if result.ok:
                print("AI (connected)")
                gemini_ok = True
            else:
                print("offline (unexpected response)")
                gemini_ok = False
        except Exception as exc:  # noqa: BLE001
            print(f"offline ({type(exc).__name__}: {exc})")
            gemini_ok = False

    # --- Telnet check --------------------------------------------------------
    if telnet:
        print(f"Telnet: checking {settings.fg_telnet_host}:{settings.fg_telnet_port}...", end=" ", flush=True)
        try:
            bridge = FGTelnetBridge(settings.fg_telnet_host, settings.fg_telnet_port)
            bridge.connect(retries=1, backoff=0.0)
            val = bridge.get("/sim/aircraft-id")
            bridge.close()
            print(f"connected (aircraft={val!r})")
        except BridgeError as exc:
            print(f"not reachable ({exc})")

    sys.exit(0 if gemini_ok else 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="FlightGear AI ATC sidecar")
    parser.add_argument(
        "--replay",
        metavar="SESSION_JSONL",
        help="Replay a session log offline and diff against golden text; exits non-zero on any diff.",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Check Gemini connectivity and optionally round-trip one telnet property, then exit.",
    )
    parser.add_argument(
        "--selftest-telnet",
        action="store_true",
        help="Also round-trip a telnet get during --selftest (requires FlightGear running).",
    )
    args = parser.parse_args()

    if args.replay:
        from sidecar.replay import replay_session  # noqa: PLC0415
        diffs = replay_session(args.replay)
        sys.exit(1 if diffs else 0)

    if args.selftest:
        _run_selftest(telnet=args.selftest_telnet)
        return

    settings = load()
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
    sidecar = build_sidecar(settings)

    def _shutdown(signum: int, _frame: object) -> None:
        _log.info("signal %s received; shutting down", signum)
        sidecar.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    sidecar.tts.start()
    try:
        sidecar.bridge.connect()
        sidecar.bridge.set(STATUS, "idle")
        mode = "ai" if settings.gemini_api_key else "offline"
        sidecar.bridge.set(SIDECAR_MODE, mode)
        sidecar.bridge.set(HEARTBEAT, 0)
        sidecar.bridge.set(CONTROLLER_NAME, sidecar.persona.name)
        sidecar.poll_loop()
    except BridgeError as exc:
        _log.error("could not start sidecar: %s", exc)
    finally:
        sidecar.tts.stop()
        sidecar.bridge.close()


if __name__ == "__main__":
    main()
