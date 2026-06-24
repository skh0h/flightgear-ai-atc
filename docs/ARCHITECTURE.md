# Architecture

## Two-Component Design

The system splits into two loosely coupled parts:

1. **Python sidecar** (`sidecar/`) — runs on the same Mac as FlightGear. Handles all AI calls, parsing, routing computation, and TTS. Communicates with FlightGear over a telnet property connection on `localhost:5501`.

2. **FlightGear Nasal addon** (`addon/`) — thin in-sim UI layer. Writes pilot requests into the `/ai-atc/` property mailbox and reads ATC responses back from it. Contains no AI or routing logic.

## The `/ai-atc/` Property Mailbox

The two components exchange data exclusively through FlightGear's property tree, accessed by the sidecar via the telnet interface:

| Property | Direction | Purpose |
|---|---|---|
| `/ai-atc/request/type` | Nasal → sidecar | "pushback" / "taxi" / "takeoff" / "cancel" |
| `/ai-atc/request/callsign` | Nasal → sidecar | Aircraft callsign |
| `/ai-atc/request/trigger` | Nasal → sidecar | Set to `true` to fire; sidecar resets to `false` |
| `/ai-atc/response/text` | sidecar → Nasal | Full ATC clearance text |
| `/ai-atc/response/ready` | sidecar → Nasal | Set to `true` when response is available |
| `/ai-atc/status` | sidecar → Nasal | "idle" / "processing" / "error" |

## Airport Picture Schema

The sidecar builds and caches an **airport picture** — a structured snapshot of one airport's ground layout:

```
AirportPicture
  icao            str
  source          "ai" | "code"
  generated_at    ISO-8601 str
  groundnet_hash  SHA-256 hex of source groundnet.xml
  parking[]       {id, name, type, lat, lon, heading}
  nodes[]         {index, lat, lon, on_runway, hold_point}
  segments[]      {begin, end, name, pushback}
  runways[]       {id, thr_lat, thr_lon, heading, length, ils_freq, entry_nodes[]}
  frequencies     {ground, tower, atis, approach, departure}
  taxi_graph      {node_index: [neighbor_index, ...]}
```

The picture is cached in SQLite keyed by `(icao, groundnet_hash)` so it is reused across sessions unless the groundnet changes.

## AI-When-Online / Code-When-Offline Principle

Every step that can use AI has a deterministic fallback:

| Step | Online | Offline |
|---|---|---|
| Airport parsing | `parser_ai.py` (Gemini structured output) | `parser_code.py` (XML parse) |
| Phraseology | `phraseology.phrase_online()` (Gemini) | `phraseology.phrase_offline()` (templates) |

The `gemini_client` raises `OfflineError` on any network or quota failure; callers catch it and invoke the code path. This ensures the addon remains functional without an internet connection or API key.

## Data Flow (happy path)

```
Pilot presses "Request Taxi" in dialog
  → Nasal sets /ai-atc/request props + trigger=true
  → sidecar FGBridge detects trigger
  → sidecar checks cache for (icao, groundnet_hash)
      hit  → use cached AirportPicture
      miss → parser_ai (or parser_code offline) → cache.put()
  → routing.find_route(graph, gate, runway)
  → phraseology.phrase_online (or offline)
  → tts.speak(clearance)
  → sidecar writes /ai-atc/response/text + ready=true
  → Nasal listener displays text in dialog
```

## Dev/Test Workflow (Two-Mac Setup)

Development happens on the **dev Mac** (this repo). The FlightGear Mac runs the actual simulator. Workflow:

1. Push changes to GitHub from dev Mac.
2. Pull on the FlightGear Mac.
3. Start FlightGear with `--telnet=5501` and load the addon.
4. Run the sidecar (`python3 sidecar/main.py`) on the FlightGear Mac.
5. Test in-sim, iterate on dev Mac.
