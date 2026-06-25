"""Tests for sidecar/fg_bridge.py — mock socket, no live FlightGear."""

from __future__ import annotations

import pytest

from sidecar.fg_bridge import BridgeError, FGTelnetBridge, _parse_get


def _noop(_seconds: float) -> None:
    pass


class _FakeSocket:
    """A minimal socket double: programmable get-replies + recorded writes."""

    def __init__(self, responder=None) -> None:
        self.sent: list[str] = []
        self._recv_buf = b""
        self._responder = responder or (lambda _cmd: "")
        self.closed = False

    def settimeout(self, _timeout: float) -> None:
        pass

    def connect(self, _addr) -> None:
        pass

    def sendall(self, data: bytes) -> None:
        cmd = data.decode("utf-8").strip()
        self.sent.append(cmd)
        reply = self._responder(cmd)
        if reply:
            self._recv_buf += reply.encode("utf-8")

    def recv(self, n: int) -> bytes:
        chunk, self._recv_buf = self._recv_buf[:n], self._recv_buf[n:]
        return chunk

    def close(self) -> None:
        self.closed = True


class _FailOnConnect:
    def settimeout(self, _timeout: float) -> None:
        pass

    def connect(self, _addr) -> None:
        raise OSError("connection refused")

    def close(self) -> None:
        pass


def _factory_returning(*sockets):
    it = iter(sockets)
    return lambda *_a, **_k: next(it)


# ---------------------------------------------------------------------------
# Reply parsing
# ---------------------------------------------------------------------------


def test_parse_get_formats() -> None:
    assert _parse_get("/sim/aircraft = 'c172p' (string)") == "c172p"
    assert _parse_get("/position/latitude-deg = 37.6 (double)") == "37.6"
    assert _parse_get("plain-value") == "plain-value"
    assert _parse_get("/x = '' (string)") == ""


# ---------------------------------------------------------------------------
# get / set round trip
# ---------------------------------------------------------------------------


def test_get_and_set_round_trip() -> None:
    def responder(cmd: str) -> str:
        if cmd.startswith("get /sim/aircraft"):
            return "/sim/aircraft = 'c172p' (string)\r\n"
        if cmd.startswith("get /position/latitude-deg"):
            return "/position/latitude-deg = 37.6191 (double)\r\n"
        return ""

    sock = _FakeSocket(responder)
    bridge = FGTelnetBridge(socket_factory=_factory_returning(sock))
    bridge.connect(_sleep=_noop)

    assert bridge.get("/sim/aircraft") == "c172p"
    assert bridge.get("/position/latitude-deg") == "37.6191"

    bridge.set("/ai-atc/request/trigger", 0)
    assert "set /ai-atc/request/trigger 0" in sock.sent


# ---------------------------------------------------------------------------
# Reconnect with back-off
# ---------------------------------------------------------------------------


def test_connect_retries_then_succeeds() -> None:
    good = _FakeSocket()
    factory = _factory_returning(_FailOnConnect(), _FailOnConnect(), good)
    bridge = FGTelnetBridge(socket_factory=factory)
    bridge.connect(retries=5, backoff=0.0, _sleep=_noop)
    assert bridge.connected


def test_connect_exhausts_retries_raises() -> None:
    factory = _factory_returning(_FailOnConnect(), _FailOnConnect(), _FailOnConnect())
    bridge = FGTelnetBridge(socket_factory=factory)
    with pytest.raises(BridgeError):
        bridge.connect(retries=3, backoff=0.0, _sleep=_noop)
    assert not bridge.connected


def test_operation_without_connect_raises() -> None:
    bridge = FGTelnetBridge(socket_factory=_factory_returning(_FakeSocket()))
    with pytest.raises(BridgeError):
        bridge.get("/anything")


# ---------------------------------------------------------------------------
# Polling subscribe fires only on change
# ---------------------------------------------------------------------------


def test_subscribe_fires_only_on_change() -> None:
    values = iter(["0", "0", "1", "1"])

    def responder(cmd: str) -> str:
        if cmd.startswith("get /ai-atc/request/trigger"):
            return f"/ai-atc/request/trigger = '{next(values)}' (string)\r\n"
        return ""

    bridge = FGTelnetBridge(socket_factory=_factory_returning(_FakeSocket(responder)))
    bridge.connect(_sleep=_noop)

    seen: list[str] = []
    bridge.subscribe(
        "/ai-atc/request/trigger", seen.append, count=4, _sleep=_noop
    )
    assert seen == ["0", "1"]
