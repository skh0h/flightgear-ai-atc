"""Tests for sidecar/metar.py — no live network; urllib.request.urlopen is mocked."""

from __future__ import annotations

import io
import socket
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from sidecar.metar import _parse_wind, get_wind

# ---------------------------------------------------------------------------
# _parse_wind unit tests (no I/O)
# ---------------------------------------------------------------------------


def test_parse_wind_standard() -> None:
    """240/15 kt: standard dddssKT group."""
    assert _parse_wind("KSFO 241753Z 24015KT 10SM SKC 20/10 A2992") == (240.0, 15.0)


def test_parse_wind_gust_uses_steady() -> None:
    """With gust, steady speed is returned; gust is discarded."""
    assert _parse_wind("EGLL 211220Z 27018G30KT 9999 FEW030 15/08 Q1012") == (270.0, 18.0)


def test_parse_wind_calm() -> None:
    """00000KT -> (0.0, 0.0)."""
    assert _parse_wind("KORD 121755Z 00000KT 10SM CLR 12/05 A3002") == (0.0, 0.0)


def test_parse_wind_variable_returns_none() -> None:
    """VRBssKT -> None (caller treats as calm fallback)."""
    assert _parse_wind("KSFO 241800Z VRB05KT 10SM SCT015 18/12 A2992") is None


def test_parse_wind_three_digit_speed() -> None:
    """Three-digit speed (> 99 kt, e.g. 100KT): rare but valid METAR."""
    assert _parse_wind("KDEN 010000Z 270100KT") == (270.0, 100.0)


def test_parse_wind_malformed_returns_none() -> None:
    """Completely absent or malformed wind group -> None."""
    assert _parse_wind("This is not a METAR at all") is None
    assert _parse_wind("") is None


def test_parse_wind_missing_from_metar() -> None:
    """METAR body without a wind group -> None."""
    assert _parse_wind("KSFO 241753Z 10SM SKC 20/10 A2992") is None


# ---------------------------------------------------------------------------
# get_wind integration: mock urlopen
# ---------------------------------------------------------------------------

_SAMPLE_METAR = "KSFO 241753Z 24015KT 10SM SKC 20/10 A2992"
_SAMPLE_METAR_GUST = "EGLL 211220Z 27018G30KT 9999 FEW030 15/08 Q1012"
_CALM_METAR = "KORD 121755Z 00000KT 10SM CLR 12/05 A3002"
_VRB_METAR = "KSFO 241800Z VRB05KT 10SM SCT015 18/12 A2992"


def _mock_urlopen(metar_text: str):
    """Return a context-manager mock whose read() gives *metar_text*."""
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = metar_text.encode("utf-8")
    return mock_resp


@patch("sidecar.metar.urllib.request.urlopen")
def test_get_wind_parses_standard(mock_urlopen) -> None:
    mock_urlopen.return_value = _mock_urlopen(_SAMPLE_METAR)
    result = get_wind("KSFO")
    assert result == (240.0, 15.0)


@patch("sidecar.metar.urllib.request.urlopen")
def test_get_wind_parses_gust(mock_urlopen) -> None:
    mock_urlopen.return_value = _mock_urlopen(_SAMPLE_METAR_GUST)
    result = get_wind("EGLL")
    assert result == (270.0, 18.0)


@patch("sidecar.metar.urllib.request.urlopen")
def test_get_wind_calm(mock_urlopen) -> None:
    mock_urlopen.return_value = _mock_urlopen(_CALM_METAR)
    assert get_wind("KORD") == (0.0, 0.0)


@patch("sidecar.metar.urllib.request.urlopen")
def test_get_wind_variable_returns_none(mock_urlopen) -> None:
    mock_urlopen.return_value = _mock_urlopen(_VRB_METAR)
    assert get_wind("KSFO") is None


@patch("sidecar.metar.urllib.request.urlopen")
def test_get_wind_network_error_returns_none(mock_urlopen) -> None:
    """OSError (network down, timeout) -> None, never raises."""
    mock_urlopen.side_effect = OSError("network unreachable")
    assert get_wind("KSFO") is None


@patch("sidecar.metar.urllib.request.urlopen")
def test_get_wind_timeout_returns_none(mock_urlopen) -> None:
    """Socket timeout -> None."""
    mock_urlopen.side_effect = TimeoutError("timed out")
    assert get_wind("KSFO") is None


@patch("sidecar.metar.urllib.request.urlopen")
def test_get_wind_http_error_returns_none(mock_urlopen) -> None:
    """HTTP 404 from the API -> None."""
    mock_urlopen.side_effect = urllib.error.HTTPError(
        url="https://aviationweather.gov/...",
        code=404,
        msg="Not Found",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )
    assert get_wind("ZZZZ") is None


@patch("sidecar.metar.urllib.request.urlopen")
def test_get_wind_empty_response_returns_none(mock_urlopen) -> None:
    """Empty API response body -> None (no wind group to parse)."""
    mock_urlopen.return_value = _mock_urlopen("")
    assert get_wind("KSFO") is None
