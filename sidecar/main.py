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

import hashlib
import logging
import signal
import time
from collections.abc import Callable

from sidecar import parser_ai, phraseology, routing
from sidecar.airport_picture import AirportPicture
from sidecar.cache import PictureCache
from sidecar.config import Settings, load
from sidecar.fg_bridge import BridgeError, FGTelnetBridge
from sidecar.gemini_client import GeminiClient
from sidecar.phraseology import Clearance
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

    def _build_clearance(
        self, req_type: str, callsign: str, picture: AirportPicture | None
    ) -> Clearance:
        active_runway = self.bridge.get(REQ_RUNWAY) or ""
        taxiways: list[str] = []
        if picture is not None and req_type == "taxi" and active_runway:
            try:
                lat = _to_float(self.bridge.get(POS_LAT))
                lon = _to_float(self.bridge.get(POS_LON))
                start = routing.nearest_node(picture, lat, lon)
                goal = routing.runway_goal_node(picture, active_runway)
                if start is not None and goal is not None:
                    route = routing.find_route(picture, start, goal)
                    taxiways = routing.route_taxiways(route, picture)
            except Exception:  # routing is best-effort; templates still work
                _log.warning("route computation failed", exc_info=True)
        return Clearance(
            callsign=callsign or "Aircraft",
            clearance_type=req_type or "taxi",
            taxi_route=taxiways,
            active_runway=active_runway,
            hold_short=active_runway if req_type == "taxi" else "",
        )

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
            groundnet_xml = self._groundnet_loader(icao)
            picture = (
                self.get_airport_picture(icao, groundnet_xml)
                if groundnet_xml
                else None
            )
            clearance = self._build_clearance(req_type, callsign, picture)
            text = phraseology.phrase_online(clearance, self.client)
        except Exception:
            _log.exception("failed to handle request")
            self.bridge.set(STATUS, "error")
            self.bridge.set(REQ_TRIGGER, 0)
            return

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
