"""Tests for sidecar/blackboard.py — WorldState defaults + shared store."""

from __future__ import annotations

from sidecar.blackboard import Blackboard, WorldState


# ---------------------------------------------------------------------------
# WorldState defaults
# ---------------------------------------------------------------------------


def test_world_state_defaults() -> None:
    ws = WorldState()
    assert ws.phase == "preflight"
    assert ws.airport == ""
    assert ws.traffic_count == 0
    assert ws.wind_dir == 0
    assert ws.wind_kt == 0
    assert ws.airspace_class == "G"
    assert ws.mode == "normal"
    assert ws.controller == ""
    assert ws.language == "en"
    assert ws.region == "us"


# ---------------------------------------------------------------------------
# get / set
# ---------------------------------------------------------------------------


def test_get_returns_default_for_unknown_key() -> None:
    bb = Blackboard()
    assert bb.get("nope") is None
    assert bb.get("nope", "fallback") == "fallback"


def test_set_get_world_state_field() -> None:
    bb = Blackboard()
    bb.set("airport", "KJFK")
    assert bb.get("airport") == "KJFK"
    # The typed field is updated on the backing state, not the extra dict.
    assert bb.state.airport == "KJFK"


def test_set_get_extra_key() -> None:
    bb = Blackboard()
    bb.set("weather_note", "gusty")
    assert bb.get("weather_note") == "gusty"


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


def test_update_sets_fields_and_extras() -> None:
    bb = Blackboard()
    bb.update(phase="taxi", airport="KSFO", traffic_count=3, custom="bar")
    assert bb.get("phase") == "taxi"
    assert bb.get("airport") == "KSFO"
    assert bb.get("traffic_count") == 3
    assert bb.get("custom") == "bar"


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------


def test_snapshot_includes_fields_and_extras() -> None:
    bb = Blackboard()
    bb.update(airport="KLAX", note="hello")
    snap = bb.snapshot()
    assert snap["airport"] == "KLAX"
    assert snap["phase"] == "preflight"  # default field still present
    assert snap["note"] == "hello"


def test_snapshot_is_a_copy() -> None:
    bb = Blackboard()
    bb.set("airport", "KORD")
    snap = bb.snapshot()
    snap["airport"] = "XXXX"
    # Mutating the snapshot must not change the blackboard's state.
    assert bb.get("airport") == "KORD"


def test_blackboard_accepts_initial_state() -> None:
    ws = WorldState(airport="EGLL", language="fr", region="uk")
    bb = Blackboard(ws)
    assert bb.get("airport") == "EGLL"
    assert bb.get("language") == "fr"
    assert bb.get("region") == "uk"
