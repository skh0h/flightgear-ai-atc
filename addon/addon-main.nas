# addon-main.nas — AI ATC addon entry point
#
# /ai-atc/ property mailbox:
#   /ai-atc/request/type      (string) "pushback" | "taxi" | "takeoff" | "cancel"
#   /ai-atc/request/callsign  (string) aircraft callsign, e.g. "N12345"
#   /ai-atc/request/runway    (string) requested/active runway, e.g. "28R"
#   /ai-atc/request/trigger   (bool)   set to 1 to fire the request; sidecar resets to 0
#   /ai-atc/response/text     (string) latest ATC clearance text written by the sidecar
#   /ai-atc/response/ready    (bool)   set to 1 by the sidecar when a response is available
#   /ai-atc/status            (string) "idle" | "processing" | "error"
#   /ai-atc/log               (string) accumulating transcript shown in the dialog
#
# The Python sidecar polls /ai-atc/request/trigger over the FG telnet interface.
# When triggered it reads context props, generates a clearance, writes
# /ai-atc/response/text, sets /ai-atc/response/ready = 1, and resets the trigger.
# The listeners below surface each clearance in the dialog log.

var ROOT = "/ai-atc";
var _listeners = [];

# Initialise the mailbox so the dialog and sidecar see well-formed defaults.
var _set_defaults = func {
    setprop(ROOT ~ "/request/type", "taxi");
    setprop(ROOT ~ "/request/callsign", "");
    setprop(ROOT ~ "/request/runway", "");
    setprop(ROOT ~ "/request/trigger", 0);
    setprop(ROOT ~ "/response/text", "");
    setprop(ROOT ~ "/response/ready", 0);
    setprop(ROOT ~ "/status", "idle");
    setprop(ROOT ~ "/log", "");
};

# Append one line to the scrolling transcript.
var append_log = func(line) {
    if (line == nil or line == "") return;
    var existing = getprop(ROOT ~ "/log");
    if (existing == nil) existing = "";
    setprop(ROOT ~ "/log", existing ~ line ~ "\n");
};

# Fire a request to the sidecar. Called from the menu and dialog bindings.
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
};

# Publish runway + frequency data from airportinfo() into the /ai-atc/airport/
# mailbox so the Python sidecar can read real runway/frequency data.
var publish_airport_data = func(icao) {
    if (icao == nil or icao == "") return;
    var info = airportinfo(icao);
    if (info == nil) return;

    # Frequencies
    var freqs = ["ground", "tower", "atis", "approach", "departure"];
    foreach (var fname; freqs) {
        var f = info.comms(fname);
        if (f != nil and size(f) > 0) {
            setprop(ROOT ~ "/airport/freq/" ~ fname, sprintf("%.2f", f[0].frequency / 1000.0));
        }
    }

    # Runways
    var rwy_list = info.runways;
    if (rwy_list == nil) return;
    var n = 0;
    foreach (var rwy; keys(rwy_list)) {
        var r = rwy_list[rwy];
        var pfx = ROOT ~ "/airport/runway[" ~ n ~ "]";
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
        n += 1;
    }
    setprop(ROOT ~ "/airport/runway_count", n);
};

var main = func(addon) {
    _set_defaults();

    # Surface each new clearance in the transcript as the sidecar writes it.
    append(_listeners, setlistener(ROOT ~ "/response/text", func(n) {
        var text = n.getValue();
        if (text != nil and text != "") append_log("[atc] " ~ text);
    }, 0, 0));

    # Clear the processing flag once a response is ready.
    append(_listeners, setlistener(ROOT ~ "/response/ready", func(n) {
        if (n.getBoolValue()) setprop(ROOT ~ "/status", "idle");
    }, 0, 0));

    # Publish airport data for the current airport at startup
    var icao = getprop("/sim/presets/airport-id");
    publish_airport_data(icao);

    print("[AI ATC] addon loaded, version " ~ addon.version);
};

var unload = func(addon) {
    foreach (var l; _listeners) removelistener(l);
    _listeners = [];
    print("[AI ATC] addon unloaded");
};
