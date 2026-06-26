"""Tests for sidecar/state.py — deterministic, advisory flight-phase machine."""

from __future__ import annotations

from sidecar.state import (
    APPROACH,
    ARRIVAL,
    CLEARANCE,
    DEPARTURE,
    DESCENT,
    LANDING,
    PARKED,
    PHASES,
    PREFLIGHT,
    PUSHBACK,
    TAKEOFF,
    TAXI_IN,
    TAXI_OUT,
    FlightStateMachine,
    phase_for_request,
)

# ---------------------------------------------------------------------------
# PHASES ordering
# ---------------------------------------------------------------------------


def test_phases_is_the_exact_contract_order() -> None:
    assert PHASES == [
        PREFLIGHT,
        CLEARANCE,
        PUSHBACK,
        TAXI_OUT,
        TAKEOFF,
        DEPARTURE,
        "climb",
        "cruise",
        DESCENT,
        ARRIVAL,
        APPROACH,
        LANDING,
        TAXI_IN,
        PARKED,
    ]


def test_phases_are_unique_and_monotonic() -> None:
    # No duplicates, and index() is a strictly increasing function over PHASES.
    assert len(PHASES) == len(set(PHASES))
    assert [PHASES.index(p) for p in PHASES] == list(range(len(PHASES)))


# ---------------------------------------------------------------------------
# phase_for_request mappings
# ---------------------------------------------------------------------------


def test_phase_for_request_core_mappings() -> None:
    assert phase_for_request("ifr_clearance") == CLEARANCE
    assert phase_for_request("pushback") == PUSHBACK
    assert phase_for_request("taxi") == TAXI_OUT
    assert phase_for_request("takeoff") == TAKEOFF
    assert phase_for_request("departure") == DEPARTURE
    assert phase_for_request("airfield_in_sight") == ARRIVAL
    assert phase_for_request("holding") == DESCENT


def test_phase_for_request_approach_family_all_map_to_approach() -> None:
    for token in ("approach", "ils", "expect_approach", "arrival_clearance"):
        assert phase_for_request(token) == APPROACH


def test_phase_for_request_is_case_and_whitespace_insensitive() -> None:
    assert phase_for_request("  TAXI ") == TAXI_OUT
    assert phase_for_request("ILS") == APPROACH


def test_phase_for_request_none_for_non_phase_tokens() -> None:
    # Cancel / readback / radio_check / emergencies / flow_control are advisory
    # no-ops: they must not correspond to any flight phase.
    for token in (
        "cancel",
        "readback",
        "radio_check",
        "mayday",
        "pan_pan",
        "squawk_7700",
        "go_around",
        "flow_control",
        "",
        "totally_unknown_token",
    ):
        assert phase_for_request(token) is None


# ---------------------------------------------------------------------------
# FlightStateMachine — construction & basic state
# ---------------------------------------------------------------------------


def test_default_start_is_preflight() -> None:
    assert FlightStateMachine().phase == PREFLIGHT


def test_explicit_start_is_respected() -> None:
    assert FlightStateMachine(start=TAXI_OUT).phase == TAXI_OUT


def test_bogus_start_falls_back_to_preflight() -> None:
    assert FlightStateMachine(start="not_a_phase").phase == PREFLIGHT


# ---------------------------------------------------------------------------
# can_advance correctness
# ---------------------------------------------------------------------------


def test_can_advance_forward_and_equal_true_backward_false() -> None:
    fsm = FlightStateMachine(start=TAXI_OUT)
    assert fsm.can_advance(TAKEOFF) is True  # forward
    assert fsm.can_advance(TAXI_OUT) is True  # equal allowed
    assert fsm.can_advance(PUSHBACK) is False  # backward rejected


def test_can_advance_unknown_target_is_false() -> None:
    assert FlightStateMachine().can_advance("not_a_phase") is False


# ---------------------------------------------------------------------------
# advance_to
# ---------------------------------------------------------------------------


def test_advance_to_forward_succeeds_and_moves() -> None:
    fsm = FlightStateMachine()
    assert fsm.advance_to(TAKEOFF) is True
    assert fsm.phase == TAKEOFF


def test_advance_to_backward_fails_and_holds() -> None:
    fsm = FlightStateMachine(start=APPROACH)
    assert fsm.advance_to(PUSHBACK) is False
    assert fsm.phase == APPROACH


def test_advance_to_unknown_target_fails_and_holds() -> None:
    fsm = FlightStateMachine(start=CLEARANCE)
    assert fsm.advance_to("not_a_phase") is False
    assert fsm.phase == CLEARANCE


# ---------------------------------------------------------------------------
# on_request — advisory advance, no regress, always returns current phase
# ---------------------------------------------------------------------------


def test_on_request_advances_forward_on_taxi_then_takeoff() -> None:
    fsm = FlightStateMachine()
    assert fsm.on_request("taxi") == TAXI_OUT
    assert fsm.phase == TAXI_OUT
    assert fsm.on_request("takeoff") == TAKEOFF
    assert fsm.phase == TAKEOFF


def test_on_request_does_not_regress_on_earlier_phase_request() -> None:
    fsm = FlightStateMachine(start=TAKEOFF)
    # An earlier-phase request (taxi/pushback) must NOT pull the phase backward.
    assert fsm.on_request("taxi") == TAKEOFF
    assert fsm.phase == TAKEOFF
    assert fsm.on_request("pushback") == TAKEOFF
    assert fsm.phase == TAKEOFF


def test_on_request_non_phase_token_returns_current_phase_unchanged() -> None:
    fsm = FlightStateMachine(start=TAXI_OUT)
    # Emergencies / readback / cancel are advisory no-ops on the machine.
    assert fsm.on_request("mayday") == TAXI_OUT
    assert fsm.on_request("readback") == TAXI_OUT
    assert fsm.phase == TAXI_OUT


def test_on_request_always_returns_a_valid_phase_and_never_raises() -> None:
    fsm = FlightStateMachine()
    for token in ("taxi", "", "garbage", None):  # type: ignore[list-item]
        result = fsm.on_request(token)  # type: ignore[arg-type]
        assert result in PHASES


def test_on_request_full_forward_sequence_is_monotonic() -> None:
    fsm = FlightStateMachine()
    sequence = [
        ("ifr_clearance", CLEARANCE),
        ("pushback", PUSHBACK),
        ("taxi", TAXI_OUT),
        ("takeoff", TAKEOFF),
        ("departure", DEPARTURE),
        ("holding", DESCENT),
        ("airfield_in_sight", ARRIVAL),
        ("ils", APPROACH),
        ("lahso", LANDING),
        ("taxi_in", TAXI_IN),
        ("shutdown", PARKED),
    ]
    last_index = -1
    for token, expected_phase in sequence:
        assert fsm.on_request(token) == expected_phase
        idx = PHASES.index(fsm.phase)
        assert idx > last_index  # strictly forward each step
        last_index = idx
    assert fsm.phase == PARKED


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


def test_reset_returns_to_original_start() -> None:
    fsm = FlightStateMachine(start=PUSHBACK)
    fsm.on_request("takeoff")
    assert fsm.phase == TAKEOFF
    fsm.reset()
    assert fsm.phase == PUSHBACK


def test_reset_default_machine_returns_to_preflight() -> None:
    fsm = FlightStateMachine()
    fsm.advance_to(CRUISE_TARGET := "cruise")
    assert fsm.phase == CRUISE_TARGET
    fsm.reset()
    assert fsm.phase == PREFLIGHT
