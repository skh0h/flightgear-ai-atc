# addon-main.nas — AI ATC addon entry point
#
# /ai-atc/ property mailbox:
#   /ai-atc/request/type      (string) request token, e.g.:
#                               departure: "pushback" | "taxi" | "takeoff" |
#                                          "intersection_departure" | "ifr_clearance" |
#                                          "cancel"
#                               arrival:   "approach" | "ils" | "airfield_in_sight" |
#                                          "lahso" | "radio_check" | "arrival_clearance" |
#                                          "holding" | "expect_approach"
#                               flow:      "flow_control"
#                               emergency: "mayday" | "pan_pan" | "gear_emergency" |
#                                          "min_fuel" | "diversion" | "go_around" |
#                                          "squawk_7500" | "squawk_7600" | "squawk_7700"
#                               info:      "ctaf" | "fss_briefing" | "simbrief" |
#                                          "airspace_check"
#                               weather:   "windshear" | "pirep" | "weather_deviation"
#                               training:  "scenario" | "kneeboard" | "career"
#   /ai-atc/request/callsign  (string) aircraft callsign, e.g. "N12345"
#   /ai-atc/request/runway    (string) requested/active runway, e.g. "28R"
#   /ai-atc/request/destination (string) IFR destination ICAO, best-effort from the
#                               route-manager; published by publish_flightplan()
#   /ai-atc/request/route     (string) IFR route string (or "DCT" fallback), published
#                               by publish_flightplan() for the ifr_clearance request
#   /ai-atc/request/altitude  (string) requested/cruise altitude in ft, best-effort from
#                               the route-manager; published by publish_flightplan()
#   /ai-atc/request/squawk    (string) assigned transponder code; written by the sidecar
#                               on an ifr_clearance, seeded blank by the add-on
#   /ai-atc/flight-phase      (string) current flight phase published by the sidecar
#                               (e.g. "preflight"); shown live in the dialog ("Phase: %s")
#   /ai-atc/request/trigger   (bool)   set to 1 to fire the request; sidecar resets to 0
#   /ai-atc/response/text     (string) latest ATC clearance text written by the sidecar
#   /ai-atc/response/ready    (bool)   set to 1 by the sidecar when a response is available
#   /ai-atc/readback/heard    (string) pilot's readback text (Phase 5 push-to-talk).
#                               Live-bound to the dialog's Readback input; also set
#                               by aiatc.ptt() (Ctrl+R) and graded on a "readback"
#                               request.
#   /ai-atc/readback/result   (string) human-readable readback grade written by the
#                               sidecar, e.g. "OK (1.00)" / "Missing: 28R". Shown live.
#   /ai-atc/status            (string) "idle" | "processing" | "error"
#   /ai-atc/log               (string) accumulating transcript shown in the dialog
#   /ai-atc/sidecar/heartbeat (int)    incremented every ~5 s by the sidecar
#   /ai-atc/sidecar/mode      (string) "ai" | "offline" — set by the sidecar
#   /ai-atc/backend           (string) human-readable backend status for the UI
#   /ai-atc/mode              (string) "normal" | "student" | "checkride" — interaction
#                               mode read by the sidecar (default "normal")
#   /ai-atc/local-hour        (int)    sim local hour 0-23, published by the add-on for
#                               the sidecar's quiet-night ("reflective" mood) easter egg
#   /ai-atc/controller/name   (string) current controller persona name, published by the
#                               sidecar; shown live in the dialog header
#   /ai-atc/chatter           (string) one ambient-chatter line published by the sidecar;
#                               shown live in the dialog ("Chatter: %s")
#   /ai-atc/airspace/class    (string) coarse airspace class published by the add-on's
#                               publish_airspace() (default "G"); read by the sidecar for
#                               the airspace_check request and shown live ("Airspace: %s")
#   /ai-atc/airspace/warning  (string) human-readable airspace advisory published by
#                               publish_airspace() (default ""); read by the sidecar and
#                               shown live in the dialog
#   /ai-atc/kneeboard         (string) multi-line training reference text published by
#                               the sidecar (e.g. on a "kneeboard" / "scenario" /
#                               "career" request); seeded blank by the add-on and shown
#                               live in the dialog's read-only Kneeboard textbox
#   /ai-atc/guardrail         (string) human-readable validation warning published by the
#                               sidecar (e.g. unsafe/ungrounded phraseology); seeded blank
#                               by the add-on and shown live in the dialog ("Guardrail: %s").
#                               Usually blank — non-empty means the sidecar flagged an issue.
#   /ai-atc/language          (string) UI/phraseology language code read by the sidecar
#                               (default "en"); written by aiatc.set_language(...)
#   /ai-atc/region            (string) phraseology region code read by the sidecar
#                               (default "us"); written by aiatc.set_region(...)
#
# The Python sidecar polls /ai-atc/request/trigger over the FG telnet interface.
# When triggered it reads context props, generates a clearance, writes
# /ai-atc/response/text, sets /ai-atc/response/ready = 1, and resets the trigger.
# The listeners below surface each clearance in the dialog log.

var ROOT = "/ai-atc";
var _listeners = [];

# How many seconds without a heartbeat increment before we call the sidecar gone.
var HEARTBEAT_STALE_SEC = 15;
# Watchdog timeout: seconds after request() before we give up waiting for a reply.
var WATCHDOG_SEC = 8;

# Initialise the mailbox so the dialog and sidecar see well-formed defaults.
var _set_defaults = func {
    setprop(ROOT ~ "/request/type", "taxi");
    setprop(ROOT ~ "/request/callsign", "");
    setprop(ROOT ~ "/request/runway", "");
    setprop(ROOT ~ "/request/trigger", 0);
    # Phase 7 IFR clearance inputs. Seeded blank; publish_flightplan() refreshes
    # destination/route/altitude best-effort from the route-manager, and the
    # sidecar may write /request/squawk back on an ifr_clearance.
    setprop(ROOT ~ "/request/destination", "");
    setprop(ROOT ~ "/request/route", "");
    setprop(ROOT ~ "/request/altitude", "");
    setprop(ROOT ~ "/request/squawk", "");
    # Current flight phase published by the sidecar to /ai-atc/flight-phase;
    # seeded "preflight" so the dialog's live "Phase: %s" binding renders before
    # the sidecar publishes the first phase.
    setprop(ROOT ~ "/flight-phase", "preflight");
    setprop(ROOT ~ "/response/text", "");
    setprop(ROOT ~ "/response/ready", 0);
    # Phase 5 push-to-talk readback mailbox. Seeded blank so the dialog's live
    # Readback input/result bindings render before the sidecar grades anything.
    setprop(ROOT ~ "/readback/heard", "");
    setprop(ROOT ~ "/readback/result", "");
    setprop(ROOT ~ "/status", "idle");
    setprop(ROOT ~ "/log", "");
    setprop(ROOT ~ "/sidecar/heartbeat", -1);
    setprop(ROOT ~ "/sidecar/mode", "");
    setprop(ROOT ~ "/backend", "Not running - launch run-mac.command");
    # Interaction mode + quiet-night easter-egg inputs. Seeded so the dialog's
    # live bindings and the sidecar both see well-formed values at startup; the
    # add-on refreshes /local-hour from sim time, the sidecar writes /controller/name.
    setprop(ROOT ~ "/mode", "normal");
    setprop(ROOT ~ "/local-hour", 12);
    setprop(ROOT ~ "/controller/name", "");
    setprop(ROOT ~ "/airport/icao", "");
    setprop(ROOT ~ "/airport/name", "");
    # Best-effort nearest-airport publication for 'diversion' phrasing. Seeded
    # empty so the sidecar always sees well-formed (possibly blank) props.
    setprop(ROOT ~ "/nearest-airport/icao", "");
    setprop(ROOT ~ "/nearest-airport/name", "");
    # Mode B live traffic display — seed so the dialog's live bindings render
    # before the sidecar writes the first sequencing summary.
    setprop(ROOT ~ "/traffic/summary", "");
    setprop(ROOT ~ "/traffic/count", 0);
    # Ambient-chatter line published by the sidecar; seeded blank so the dialog's
    # live "Chatter: %s" binding renders before the first chatter line arrives.
    setprop(ROOT ~ "/chatter", "");
    # Airspace classification + advisory published by publish_airspace(); seeded
    # with the conservative default class "G" (uncontrolled) and no warning so the
    # dialog's live bindings and the sidecar's airspace_check both see well-formed
    # values before the first publish.
    setprop(ROOT ~ "/airspace/class", "G");
    setprop(ROOT ~ "/airspace/warning", "");
    # Training kneeboard reference text published by the sidecar (e.g. on a
    # "kneeboard" / "scenario" / "career" request); seeded blank so the dialog's
    # live read-only Kneeboard textbox renders before the first publish.
    setprop(ROOT ~ "/kneeboard", "");
    # Guardrail validation warning published by the sidecar; seeded blank so the
    # dialog's live "Guardrail: %s" binding renders before (and whenever there is
    # no) validation issue. Usually blank.
    setprop(ROOT ~ "/guardrail", "");
    # Language + region config read by the sidecar; seeded with the contract
    # defaults ("en"/"us") so the sidecar and the dialog's helpers both see
    # well-formed values before the user changes them.
    setprop(ROOT ~ "/language", "en");
    setprop(ROOT ~ "/region", "us");
    # Voice mute flag: 0 = unmuted (default), 1 = spoken audio suppressed.
    # Text transcript (RESP_TEXT/RESP_READY) is always published regardless.
    setprop(ROOT ~ "/voice/muted", 0);
};

# Append one line to the scrolling transcript.
var LOG_MAX_LINES = 200;
var append_log = func(line) {
    if (line == nil or line == "") return;
    var existing = getprop(ROOT ~ "/log");
    if (existing == nil) existing = "";
    var combined = existing ~ line ~ "\n";
    # Cap the transcript so the property cannot grow unbounded over a long
    # session: keep only the last LOG_MAX_LINES lines. The trailing "\n" makes
    # split() yield a final empty element, so re-join with "\n" as a separator
    # (rather than appending "\n" to each) to preserve a single trailing newline.
    var lines = split("\n", combined);
    if (size(lines) > LOG_MAX_LINES) {
        lines = subvec(lines, size(lines) - LOG_MAX_LINES);
        combined = "";
        var first = 1;
        foreach (var l; lines) {
            if (first) { combined = l; first = 0; }
            else { combined = combined ~ "\n" ~ l; }
        }
    }
    setprop(ROOT ~ "/log", combined);
};

# ---------------------------------------------------------------------------
# Watchdog: started when request() fires, cancelled when a reply arrives.
# ---------------------------------------------------------------------------
var _watchdog_timer = nil;

var _cancel_watchdog = func {
    if (_watchdog_timer != nil) {
        _watchdog_timer.stop();
        _watchdog_timer = nil;
    }
};

var _start_watchdog = func {
    _cancel_watchdog();
    _watchdog_timer = maketimer(WATCHDOG_SEC, func {
        _watchdog_timer = nil;
        var st = getprop(ROOT ~ "/status");
        if (st == "processing") {
            setprop(ROOT ~ "/status", "idle");
            print("[atc] No response from backend — is the sidecar running?");
            append_log("[atc] No response from backend — is the sidecar running?");
        }
    });
    _watchdog_timer.singleShot = 1;
    _watchdog_timer.start();
};

# ---------------------------------------------------------------------------
# Fire a request to the sidecar. Called from the menu, dialog, and keybinding.
# ---------------------------------------------------------------------------
var request = func(req_type) {
    var callsign = getprop(ROOT ~ "/request/callsign");
    if (callsign == nil or callsign == "") {
        callsign = getprop("/sim/multiplay/callsign");
        if (callsign == nil or callsign == "") callsign = "Aircraft";
        setprop(ROOT ~ "/request/callsign", callsign);
    }
    setprop(ROOT ~ "/request/type", req_type);
    setprop(ROOT ~ "/response/ready", 0);
    setprop(ROOT ~ "/status", "processing");
    setprop(ROOT ~ "/request/trigger", 1);
    append_log("[you] request " ~ req_type ~ " (" ~ callsign ~ ")");
    _start_watchdog();
};

# Push-to-talk: submit the pilot's readback for grading. The dialog's Readback
# <input> writes /ai-atc/readback/heard live, so ptt() simply fires a "readback"
# request; the sidecar grades the heard text against the most recent clearance
# and writes /ai-atc/readback/result. Exposed on globals.aiatc so the Ctrl+R
# keybinding (which runs in the global scope) can submit a readback without the
# dialog open. Minimal and best-effort: an empty heard field still fires.
var ptt = func {
    request("readback");
};

# Mode A: set runway[idx]/active to "1" (active) or "0" (inactive). Exposed on
# globals.aiatc so dialog <checkbox> bindings (which run in the global scope,
# not the add-on scope) can toggle a runway via aiatc.set_runway_active(idx, on).
# `on` is coerced to a string "1"/"0" so the sidecar's merge_airport_mailbox
# sees the exact contract value regardless of how PUI wrote the checkbox state.
var set_runway_active = func(idx, on) {
    var pfx = ROOT ~ "/airport/runway[" ~ idx ~ "]";
    setprop(pfx ~ "/active", on ? "1" : "0");
};

# Set the controller interaction mode to one of the three contract values.
# Exposed on globals.aiatc so the dialog's Mode buttons (which run in the global
# scope, not the add-on scope) can call aiatc.set_mode("student") etc. Any
# unrecognised token falls back to "normal" so the sidecar never sees an
# out-of-contract mode value.
var set_mode = func(m) {
    if (m != "normal" and m != "student" and m != "checkride") m = "normal";
    setprop(ROOT ~ "/mode", m);
};

# Set the UI/phraseology language (e.g. "en", "fr", "de") read by the sidecar.
# Exposed on globals.aiatc so the dialog's Language buttons (which run in the
# global scope, not the add-on scope) can call aiatc.set_language("fr") etc. The
# value is lower-cased and a nil/blank falls back to the contract default "en" so
# the sidecar never sees an out-of-contract language value.
var set_language = func(lang) {
    if (lang == nil or lang == "") lang = "en";
    setprop(ROOT ~ "/language", string.lc(lang));
};

# Set the phraseology region (e.g. "us", "uk") read by the sidecar. Exposed on
# globals.aiatc so the dialog's Region buttons (which run in the global scope,
# not the add-on scope) can call aiatc.set_region("uk") etc. The value is
# lower-cased and a nil/blank falls back to the contract default "us" so the
# sidecar never sees an out-of-contract region value.
var set_region = func(reg) {
    if (reg == nil or reg == "") reg = "us";
    setprop(ROOT ~ "/region", string.lc(reg));
};

# Mute or unmute spoken audio.  Exposed on globals.aiatc so a panel checkbox
# (which runs in the global scope) can call aiatc.set_muted(1) / aiatc.set_muted(0).
# Text transcript (RESP_TEXT / RESP_READY) is always published regardless.
var set_muted = func(on) {
    setprop(ROOT ~ "/voice/muted", on ? 1 : 0);
};

# Publish runway + frequency data from airportinfo() into the /ai-atc/airport/
# mailbox so the Python sidecar can read real runway/frequency data.
var publish_airport_data = func(icao) {
    if (icao == nil or icao == "") return;
    var info = airportinfo(icao);
    if (info == nil) {
        print("[AI ATC] airportinfo returned nil for " ~ icao ~ "; skipping airport data publish");
        return;
    }

    # Airport identity for the dialog header.
    setprop(ROOT ~ "/airport/icao", info.id);
    setprop(ROOT ~ "/airport/name", info.name);

    # Frequencies — call comms() with no argument to get all comm objects.
    # Each object has .ident (e.g. "Ground", "Tower", "ATIS") and .frequency
    # already in MHz (confirmed from FG1000/garmin196 Nasal source).
    # comms(type_string) is case-sensitive and returns empty for lowercase keys,
    # so we fetch all and match by substring against lowercased .ident.
    var _err = [];
    var all_comms = nil;
    call(func { all_comms = info.comms(); }, nil, _err);
    if (size(_err) == 0 and all_comms != nil) {
        var freq_keys = ["ground", "tower", "atis", "approach", "departure"];
        foreach (var c; all_comms) {
            var ident = nil;
            var hz = nil;
            _err = [];
            call(func { ident = string.lc(c.ident); hz = c.frequency; }, nil, _err);
            if (size(_err) != 0 or ident == nil or hz == nil or hz <= 0) continue;
            foreach (var key; freq_keys) {
                if (find(key, ident) >= 0) {
                    setprop(ROOT ~ "/airport/freq/" ~ key, sprintf("%.3f", hz));
                    break;
                }
            }
        }
    }

    # Runways — clear stale entries first
    var old_count = getprop(ROOT ~ "/airport/runway_count");
    if (old_count == nil) old_count = 0;
    var i = 0;
    while (i < old_count) {
        var pfx = ROOT ~ "/airport/runway[" ~ i ~ "]";
        setprop(pfx ~ "/id", "");
        i += 1;
    }

    var rwy_list = nil;
    _err = [];
    call(func { rwy_list = info.runways; }, nil, _err);
    if (rwy_list == nil) return;
    var n = 0;
    # Sort the runway keys so runway[N] indices are stable across reloads and
    # airport changes; keys() order is otherwise non-deterministic.
    var rwy_keys = sort(keys(rwy_list), func(a, b) { cmp(a, b); });
    foreach (var rwy_key; rwy_keys) {
        var r = rwy_list[rwy_key];
        if (r == nil) continue;
        var pfx = ROOT ~ "/airport/runway[" ~ n ~ "]";
        _err = [];
        call(func {
            setprop(pfx ~ "/id",      r.id);
            setprop(pfx ~ "/heading", r.heading);
            setprop(pfx ~ "/thr_lat", r.lat);
            setprop(pfx ~ "/thr_lon", r.lon);
            setprop(pfx ~ "/length",  r.length);
            var ils = r.ils;
            if (ils != nil) {
                setprop(pfx ~ "/ils_freq", sprintf("%.2f", ils.frequency / 1000.0));
            } else {
                setprop(pfx ~ "/ils_freq", "");
            }
            # Mode A: publish per-runway active state, defaulting to "1"
            # (active) unless a stored config value already exists for this
            # slot (e.g. the user previously unchecked it in the dialog).
            var active = getprop(pfx ~ "/active");
            if (active == nil or active == "") setprop(pfx ~ "/active", "1");
        }, nil, _err);
        if (size(_err) == 0) n += 1;
    }
    setprop(ROOT ~ "/airport/runway_count", n);
};

# Best-effort: publish the nearest airport to /ai-atc/nearest-airport/{icao,name}
# so the sidecar can phrase a 'diversion' request as "...divert to KSQL San
# Carlos...". Uses FlightGear's airport DB (geo.aircraft_position +
# findAirportsWithinRange, which returns nearest-first). The whole body runs
# inside a call() guard: if any of those APIs are unavailable this simply does
# nothing and never throws, leaving the seeded "" defaults in place.
var publish_nearest_airport = func {
    var _err = [];
    call(func {
        var pos = geo.aircraft_position();
        if (pos == nil) return;
        var list = findAirportsWithinRange(pos, 100);
        if (list == nil or size(list) == 0) return;
        var ap = list[0];   # nearest-first ordering
        if (ap == nil) return;
        if (ap.id != nil)   setprop(ROOT ~ "/nearest-airport/icao", ap.id);
        if (ap.name != nil) setprop(ROOT ~ "/nearest-airport/name", ap.name);
    }, nil, _err);
    # _err intentionally ignored — nearest-airport data is optional.
};

# Best-effort: publish the aircraft's current airspace classification to
# /ai-atc/airspace/class (default "G") and a human-readable advisory to
# /ai-atc/airspace/warning (default ""). The base FlightGear package does not
# expose a reliable nearest-airspace-class property, so this is intentionally
# conservative: it derives a coarse class from real, deterministic NAS rules
# (Class A is 18,000 ft MSL to FL600) when altitude is available, and otherwise
# leaves the seeded defaults in place rather than fabricating a lateral class.
# The whole body runs inside a call() guard so a missing or odd property simply
# does nothing and never throws.
var publish_airspace = func {
    var _err = [];
    call(func {
        # Start from whatever is already published (seeded "G"), never blank.
        var cls = getprop(ROOT ~ "/airspace/class");
        if (cls == nil or cls == "") cls = "G";
        var warn = "";

        # Coarse MSL-altitude rule: at/above 18,000 ft is Class A in the US NAS,
        # where an IFR clearance is required. Below that we cannot reliably
        # classify lateral airspace from base properties, so keep the default.
        var alt_ft = getprop("/position/altitude-ft");
        if (alt_ft != nil and alt_ft >= 18000) {
            cls = "A";
            warn = "Class A: IFR clearance required at/above FL180";
        } else {
            cls = "G";
        }

        setprop(ROOT ~ "/airspace/class", cls);
        setprop(ROOT ~ "/airspace/warning", warn);
    }, nil, _err);
    # _err intentionally ignored — airspace data is best-effort/optional.
};

# Best-effort: publish the active flightplan from FlightGear's route-manager into
# the /ai-atc/request/{destination,route,altitude} mailbox so the sidecar can
# phrase an 'ifr_clearance' (e.g. "cleared to KLAX via DCT, climb and maintain
# 8000"). Every read is wrapped in a call() guard: if the route-manager is empty
# or an API is unavailable this simply leaves the seeded "" defaults in place and
# never throws. The route-manager's departure runway also seeds /request/runway,
# but only when the pilot hasn't already typed one into the dialog.
var publish_flightplan = func {
    var _err = [];
    call(func {
        var dest = getprop("/autopilot/route-manager/destination/airport");
        if (dest != nil and dest != "")
            setprop(ROOT ~ "/request/destination", dest);

        var alt = getprop("/autopilot/route-manager/cruise/altitude-ft");
        if (alt != nil and alt != "" and alt != 0)
            setprop(ROOT ~ "/request/altitude", sprintf("%d", int(alt)));

        # Seed the requested runway from the route-manager's departure runway,
        # but only if the pilot hasn't already typed one into the dialog.
        var dep_rwy = getprop("/autopilot/route-manager/departure/runway");
        var cur_rwy = getprop(ROOT ~ "/request/runway");
        if (dep_rwy != nil and dep_rwy != "" and (cur_rwy == nil or cur_rwy == ""))
            setprop(ROOT ~ "/request/runway", dep_rwy);

        # Route string: prefer the route-manager's published route text when
        # present, else fall back to "DCT" (direct) so the sidecar always sees a
        # well-formed route for the IFR clearance.
        var route = getprop("/autopilot/route-manager/route");
        if (route == nil or route == "") route = "DCT";
        setprop(ROOT ~ "/request/route", route);
    }, nil, _err);
    # _err intentionally ignored — flightplan data is best-effort/optional.
};

# Best-effort: publish the sim's current local hour (0-23) to /ai-atc/local-hour
# so the sidecar can detect "quiet night" hours for the reflective-mood easter
# egg. Prefers /sim/time/local-day-seconds (sim local time at the aircraft),
# falling back to /sim/time/utc/hour. The whole body runs inside a call() guard,
# so a missing or odd property simply leaves the seeded default in place and
# never throws.
var publish_local_hour = func {
    var _err = [];
    call(func {
        var hour = nil;
        var secs = getprop("/sim/time/local-day-seconds");
        if (secs != nil) {
            hour = int(math.mod(int(secs / 3600), 24));
        } else {
            var uh = getprop("/sim/time/utc/hour");
            if (uh != nil) hour = int(math.mod(int(uh), 24));
        }
        if (hour == nil) return;
        if (hour < 0) hour += 24;
        setprop(ROOT ~ "/local-hour", hour);
    }, nil, _err);
    # _err intentionally ignored — local-hour is a best-effort easter-egg input.
};

# ---------------------------------------------------------------------------
# Backend heartbeat watcher — updates /ai-atc/backend status string.
# ---------------------------------------------------------------------------
var _last_heartbeat = -2;  # sentinel: -2 = never seen, -1 = FG default
var _heartbeat_timer = nil;
# Periodic timer that republishes /ai-atc/local-hour from sim time (~60 s).
var _local_hour_timer = nil;
# Periodic timer that republishes /ai-atc/airspace/{class,warning} (~45 s).
var _airspace_timer = nil;

var _update_backend_status = func {
    var hb = getprop(ROOT ~ "/sidecar/heartbeat");
    var mode = getprop(ROOT ~ "/sidecar/mode");
    if (hb == nil) hb = -1;
    if (mode == nil) mode = "";

    if (hb == _last_heartbeat or hb < 0) {
        # Heartbeat not advancing (or never set by sidecar) — backend is gone.
        setprop(ROOT ~ "/backend", "Not running - launch run-mac.command");
    } elsif (mode == "ai") {
        setprop(ROOT ~ "/backend", "Connected (AI)");
    } else {
        setprop(ROOT ~ "/backend", "Connected (offline templates)");
    }
    _last_heartbeat = hb;
};

var main = func(addon) {
    _set_defaults();

    # Expose request() in the global namespace so dialog <command>nasal</command>
    # bindings (which run in the global scope, not the add-on scope) can reach it
    # via the short name  aiatc.request("pushback")  etc.
    globals.aiatc = { request: request, ptt: ptt, set_runway_active: set_runway_active, set_mode: set_mode, set_language: set_language, set_region: set_region, set_muted: set_muted };

    # Surface each new clearance in the transcript as the sidecar writes it.
    append(_listeners, setlistener(ROOT ~ "/response/text", func(n) {
        var text = n.getValue();
        if (text != nil and text != "") append_log("[atc] " ~ text);
    }, 0, 0));

    # Cancel watchdog and clear processing flag once a response is ready.
    append(_listeners, setlistener(ROOT ~ "/response/ready", func(n) {
        if (n.getBoolValue()) {
            _cancel_watchdog();
            setprop(ROOT ~ "/status", "idle");
        }
    }, 0, 0));

    # Surface error status in log and reset to idle.
    append(_listeners, setlistener(ROOT ~ "/status", func(n) {
        if (n.getValue() == "error") {
            print("[atc] Backend reported an error; resetting to idle.");
            append_log("[atc] Backend reported an error.");
            _cancel_watchdog();
            setprop(ROOT ~ "/status", "idle");
        }
    }, 0, 0));

    # Re-publish airport data when the user changes airport.
    append(_listeners, setlistener("/sim/presets/airport-id", func(n) {
        var icao = n.getValue();
        if (icao != nil and icao != "") {
            publish_airport_data(icao);
            publish_nearest_airport();   # best-effort; never throws
            publish_flightplan();        # best-effort IFR flightplan; never throws
        }
    }, 0, 0));

    # Heartbeat polling timer: check every HEARTBEAT_STALE_SEC seconds.
    _heartbeat_timer = maketimer(HEARTBEAT_STALE_SEC, _update_backend_status);
    _heartbeat_timer.start();

    # Publish the sim local hour now and refresh it every ~60 s so the sidecar's
    # quiet-night ("reflective" mood) easter egg always sees a current value.
    publish_local_hour();
    _local_hour_timer = maketimer(60, publish_local_hour);
    _local_hour_timer.start();

    # Publish the airspace class/advisory now and refresh it every ~45 s so the
    # dialog's live bindings and the sidecar's airspace_check see a current value.
    publish_airspace();
    _airspace_timer = maketimer(45, publish_airspace);
    _airspace_timer.start();

    # Publish airport data for the current airport at startup.
    var icao = getprop("/sim/presets/airport-id");
    publish_airport_data(icao);
    publish_nearest_airport();   # best-effort nearest-airport for diversions
    publish_flightplan();        # best-effort IFR flightplan for ifr_clearance

    # Initial backend status check.
    _update_backend_status();

    # addon.version is an FG Version ghost; concatenating it directly prints
    # garbage. Stringify defensively so this never throws if .str() is absent.
    var verstr = "?";
    if (addon != nil and addon.version != nil) {
        if (typeof(addon.version) == "scalar") {
            verstr = addon.version;
        } else {
            var _verr = [];
            call(func { verstr = addon.version.str(); }, nil, nil, nil, _verr);
            if (size(_verr) != 0) verstr = "?";
        }
    }
    print("[AI ATC] addon loaded, version " ~ verstr);
};

var unload = func(addon) {
    foreach (var l; _listeners) removelistener(l);
    _listeners = [];
    _cancel_watchdog();
    if (_heartbeat_timer != nil) {
        _heartbeat_timer.stop();
        _heartbeat_timer = nil;
    }
    if (_local_hour_timer != nil) {
        _local_hour_timer.stop();
        _local_hour_timer = nil;
    }
    if (_airspace_timer != nil) {
        _airspace_timer.stop();
        _airspace_timer = nil;
    }
    print("[AI ATC] addon unloaded");
};
