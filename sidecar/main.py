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
import signal
import sys
import time
from collections.abc import Callable

from sidecar import metar, parser_ai, phraseology, routing
from sidecar.airport_picture import AirportPicture, Frequencies, Runway
from sidecar.cache import PictureCache
from sidecar.config import Settings, load
from sidecar.fg_bridge import BridgeError, FGTelnetBridge
from sidecar.gemini_client import GeminiClient
from sidecar.phraseology import Clearance
from sidecar.runway_selection import build_taxi_clearance
from sidecar.tts import TTS

_log = logging.getLogger(__name__)

# --- mailbox / state property paths -----------------------------------------
REQ_TYPE = "/ai-atc/request/type"
REQ_CALLSIGN = "/ai-atc/request/callsign"
REQ_RUNWAY = "/ai-atc/request/runway"
REQ_TRIGGER = "/ai-atc/request/trigger"
RESP_TEXT = "/ai-atc/response/text"
RESP_READY = "/ai-atc/response/ready"
STATUS = "/ai-atc/status"
AIRPORT_ID = "/sim/presets/airport-id"
POS_LAT = "/position/latitude-deg"
POS_LON = "/position/longitude-deg"
AIRCRAFT_ID = "/sim/aircraft-id"

# --- airport data pipe (Item 3) — Nasal publishes here, sidecar reads -------
AP_RUNWAY_COUNT = "/ai-atc/airport/runway_count"
AP_RUNWAY_PREFIX = "/ai-atc/airport/runway"  # + "[N]/field"
AP_FREQ_GROUND = "/ai-atc/airport/freq/ground"
AP_FREQ_TOWER = "/ai-atc/airport/freq/tower"
AP_FREQ_ATIS = "/ai-atc/airport/freq/atis"
AP_FREQ_APPROACH = "/ai-atc/airport/freq/approach"
AP_FREQ_DEPARTURE = "/ai-atc/airport/freq/departure"


def _is_true(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes")


def _to_float(value: str, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


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
        runways.append(Runway(
            id=rwy_id,
            heading=heading,
            thr_lat=thr_lat,
            thr_lon=thr_lon,
            length=length,
            ils_freq=ils_freq,
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
        picture = parser_ai.parse_with_ai(icao, groundnet_xml, self.client)
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
        active_runway = self.bridge.get(REQ_RUNWAY) or ""
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
        return Clearance(
            callsign=eff_callsign,
            clearance_type=eff_type,
            taxi_route=taxiways,
            active_runway=active_runway,
            hold_short=active_runway if eff_type == "taxi" else "",
            aircraft_type=aircraft_type,
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
    # One request
    # ------------------------------------------------------------------

    def handle_trigger(self) -> None:
        req_type = (self.bridge.get(REQ_TYPE) or "taxi").strip()
        callsign = (self.bridge.get(REQ_CALLSIGN) or "Aircraft").strip()

        if req_type == "cancel":
            self.bridge.set(STATUS, "idle")
            self.bridge.set(REQ_TRIGGER, 0)
            return

        self.bridge.set(STATUS, "processing")
        try:
            icao = (self.bridge.get(AIRPORT_ID) or "").strip()
            lat = _to_float(self.bridge.get(POS_LAT))
            lon = _to_float(self.bridge.get(POS_LON))
            groundnet_xml = self._groundnet_loader(icao)
            picture = (
                self.get_airport_picture(icao, groundnet_xml)
                if groundnet_xml
                else None
            )
            # Merge any runway/frequency data Nasal has published into the picture
            if picture is not None:
                picture = merge_airport_mailbox(picture, self.bridge)
            clearance = self._build_clearance(req_type, callsign, picture)
            text = phraseology.phrase_online(clearance, self.client)
        except Exception:
            _log.exception("failed to handle request")
            self.bridge.set(STATUS, "error")
            self.bridge.set(REQ_TRIGGER, 0)
            return

        self._append_session_record(
            airport_id=icao,
            lat=lat,
            lon=lon,
            req_type=req_type,
            callsign=callsign,
            runway=(self.bridge.get(REQ_RUNWAY) or "").strip(),
            aircraft_type=clearance.aircraft_type,
            picture=picture,
            response_text=text,
        )
        self.tts.speak(text)
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
    ) -> None:
        """Poll the trigger property and dispatch requests.

        ``max_iterations`` bounds the loop for tests; ``None`` runs until
        :meth:`stop` or a signal.  Bridge errors are logged and retried on the
        next tick rather than crashing the loop.
        """
        self._running = True
        iterations = 0
        while self._running and (max_iterations is None or iterations < max_iterations):
            try:
                if _is_true(self.bridge.get(REQ_TRIGGER)):
                    self.handle_trigger()
            except BridgeError:
                _log.warning("bridge error during poll; will retry", exc_info=True)
            iterations += 1
            _sleep(interval)

    def stop(self) -> None:
        self._running = False


def build_sidecar(settings: Settings) -> Sidecar:
    """Wire up the real collaborators from configuration."""
    bridge = FGTelnetBridge(settings.fg_telnet_host, settings.fg_telnet_port)
    client = GeminiClient(settings)
    cache = PictureCache(settings.cache_db_path)
    tts = TTS(voice=settings.tts_voice)
    return Sidecar(settings, bridge, client, cache, tts)


def main() -> None:
    parser = argparse.ArgumentParser(description="FlightGear AI ATC sidecar")
    parser.add_argument(
        "--replay",
        metavar="SESSION_JSONL",
        help="Replay a session log offline and diff against golden text; exits non-zero on any diff.",
    )
    args = parser.parse_args()

    if args.replay:
        from sidecar.replay import replay_session  # noqa: PLC0415
        diffs = replay_session(args.replay)
        sys.exit(1 if diffs else 0)

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
        sidecar.poll_loop()
    except BridgeError as exc:
        _log.error("could not start sidecar: %s", exc)
    finally:
        sidecar.tts.stop()
        sidecar.bridge.close()


if __name__ == "__main__":
    main()
