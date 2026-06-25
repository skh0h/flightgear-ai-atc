# FlightGear AI ATC

AI-powered ATC clearances and taxi routing for FlightGear.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![FlightGear 2024.1.5+](https://img.shields.io/badge/flightgear-2024.1.5%2B-green)
![Windows | macOS](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-blue)
![License](https://img.shields.io/badge/license-TODO-red)

## Overview

A smart assistant for FlightGear pilots combining real-time ATC services with automated taxi routing. Two components work together:

- **Python sidecar** (`sidecar/`) — AI parsing, routing, and TTS running on Windows or macOS. Communicates with FlightGear over telnet.
- **Nasal add-on** (`addon/`) — lightweight in-sim UI layer. Exchanges data with the sidecar via property mailbox at `/ai-atc/`.

**When online:** Uses the Google Gemini API to intelligently parse real airport data and generate contextual ATC phrases.  
**When offline:** Falls back to deterministic groundnet.xml parsing and template-based responses.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full system design.

### Platform Support

This add-on runs on **Windows and macOS**. The core sidecar (Python) and in-sim add-on (Nasal) are fully cross-platform. Native text-to-speech voice output is currently available on macOS; Windows TTS support is coming soon — all other features work seamlessly on both platforms.

## Features

- 🎙️ **AI-Powered ATC** — Real-time clearances and phraseology using Google Gemini
- 🗺️ **Smart Taxi Routing** — A* pathfinding with groundnet awareness
- 🛬 **Runway Selection** — Intelligent runway recommendations based on wind and traffic
- 🖼️ **Airport Intelligence** — Automated parsing of airport pictures and groundnet data
- 🔄 **Offline Fallback** — Full functionality without internet (template-based responses)
- 🔊 **Text-to-Speech** — Native macOS TTS integration for immersive ATC experience (Windows support coming soon)
- 🧠 **Schema Learning** — AI-assisted parser that learns from airport layouts (Phase 4)

## Coming Soon

More documentation is on the way. This section will include:

- Installation & Setup
- Quick Start Guide
- Configuration Reference
- Project Structure Overview
- Development Workflow
- Contributing Guidelines
- License Information

Check back soon, or see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for detailed system design in the meantime.
