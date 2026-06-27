"""Tests for sidecar/simbrief.py — no live network; _opener is injected."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from sidecar.simbrief import FlightPlan, fetch_ofp, parse_ofp

# ---------------------------------------------------------------------------
# parse_ofp
# ---------------------------------------------------------------------------

# Representative (trimmed) SimBrief OFP JSON dict.
_SAMPLE_OFP = {
    "origin": {"icao_code": "KSFO", "iata_code": "SFO"},
    "destination": {"icao_code": "KLAX", "iata_code": "LAX"},
    "alternate": {"icao_code": "KSAN"},
    "general": {
        "route": "OFFSH3 BSR Q90 GMN SADDE6",
        "initial_altitude": "36000",
    },
    "fuel": {"plan_ramp": "12500"},
    "atc": {"callsign": "SWA1234"},
}


def test_parse_ofp_full() -> None:
    """A representative OFP maps to an exact FlightPlan."""
    assert parse_ofp(_SAMPLE_OFP) == FlightPlan(
        origin="KSFO",
        destination="KLAX",
        route="OFFSH3 BSR Q90 GMN SADDE6",
        alternate="KSAN",
        cruise_alt="36000",
        block_fuel="12500",
        callsign="SWA1234",
    )


def test_parse_ofp_empty_dict_safe_defaults() -> None:
    """An empty dict yields all-default ("") FlightPlan, never raises."""
    assert parse_ofp({}) == FlightPlan()


def test_parse_ofp_none_safe_defaults() -> None:
    """A falsy/None OFP yields all-default FlightPlan."""
    assert parse_ofp(None) == FlightPlan()  # type: ignore[arg-type]


def test_parse_ofp_sparse_partial_fields() -> None:
    """Missing sections/keys fall back to defaults; present ones survive."""
    sparse = {
        "origin": {"icao_code": "EGLL"},
        "general": {},  # no route / initial_altitude
        # no destination / alternate / fuel / atc
    }
    fp = parse_ofp(sparse)
    assert fp.origin == "EGLL"
    assert fp.destination == ""
    assert fp.route == ""
    assert fp.alternate == ""
    assert fp.cruise_alt == ""
    assert fp.block_fuel == ""
    assert fp.callsign == ""


def test_parse_ofp_coerces_non_string_and_none() -> None:
    """Numeric values become str; explicit None values become ''."""
    ofp = {
        "origin": {"icao_code": "KJFK"},
        "general": {"route": "DCT", "initial_altitude": 41000},
        "fuel": {"plan_ramp": None},
    }
    fp = parse_ofp(ofp)
    assert fp.cruise_alt == "41000"
    assert fp.block_fuel == ""


def test_parse_ofp_non_dict_section_ignored() -> None:
    """A section that isn't a dict is treated as absent, not an error."""
    fp = parse_ofp({"origin": "KSFO", "destination": {"icao_code": "KLAX"}})
    assert fp.origin == ""
    assert fp.destination == "KLAX"


# ---------------------------------------------------------------------------
# fetch_ofp — injected opener, no network
# ---------------------------------------------------------------------------


def _mock_opener(payload: bytes):
    """Return a fake opener callable yielding a context-manager response."""

    def _opener(req, timeout=None):  # noqa: ANN001 - test stub
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.read.return_value = payload
        return resp

    return _opener


def test_fetch_ofp_parses_json_bytes() -> None:
    """A fake opener returning JSON bytes yields the parsed dict (no network)."""
    payload = json.dumps(_SAMPLE_OFP).encode("utf-8")
    result = fetch_ofp("someuser", _opener=_mock_opener(payload))
    assert result == _SAMPLE_OFP
    # And the result round-trips through parse_ofp.
    assert parse_ofp(result).origin == "KSFO"


def test_fetch_ofp_accepts_str_body() -> None:
    """Opener returning a str (not bytes) is still JSON-decoded."""
    payload = json.dumps({"origin": {"icao_code": "KBOS"}})

    def _opener(req, timeout=None):  # noqa: ANN001 - test stub
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.read.return_value = payload  # str, not bytes
        return resp

    result = fetch_ofp("u", _opener=_opener)
    assert result["origin"]["icao_code"] == "KBOS"


def test_fetch_ofp_propagates_opener_error() -> None:
    """Network failure inside the opener propagates (no silent swallow)."""

    def _boom(req, timeout=None):  # noqa: ANN001 - test stub
        raise OSError("network unreachable")

    try:
        fetch_ofp("u", _opener=_boom)
    except OSError:
        pass
    else:  # pragma: no cover - guard
        raise AssertionError("expected OSError to propagate")
