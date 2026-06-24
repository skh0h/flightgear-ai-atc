# addon-main.nas — AI ATC addon entry point
#
# /ai-atc/ property mailbox plan:
#   /ai-atc/request/type      (string) "pushback" | "taxi" | "takeoff" | "cancel"
#   /ai-atc/request/callsign  (string) aircraft callsign, e.g. "N12345"
#   /ai-atc/request/trigger   (bool)   set to 1 to fire the request; sidecar resets to 0
#   /ai-atc/response/text     (string) ATC clearance text written by sidecar
#   /ai-atc/response/ready    (bool)   set to 1 by sidecar when response is available
#   /ai-atc/status            (string) "idle" | "processing" | "error"
#
# The Python sidecar watches /ai-atc/request/trigger via the FG telnet interface.
# When triggered it reads context props, generates a clearance, writes
# /ai-atc/response/text, then sets /ai-atc/response/ready = 1.
# The Nasal listener here picks up ready=1, surfaces text in the dialog, and
# passes it to the TTS engine on the sidecar side.

var _listener = nil;

var main = func(addon) {
    # TODO: initialise /ai-atc/ property tree with defaults
    # TODO: register a setlistener on /ai-atc/response/ready to display clearance
    # TODO: build menu items / dialog (see addon-menubar-items.xml, gui/dialogs/ai-atc.xml)
    print("[AI ATC] addon loaded, version " ~ addon.version);
}

var unload = func(addon) {
    # TODO: remove listeners, reset property tree
    if (_listener != nil) { removelistener(_listener); }
    print("[AI ATC] addon unloaded");
}
