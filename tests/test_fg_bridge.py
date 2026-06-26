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


# ---------------------------------------------------------------------------
# Banner drain: connection banner is consumed transparently
# ---------------------------------------------------------------------------


def test_banner_drained_transparently() -> None:
    """A FG-style banner line is consumed during connect() and does not corrupt get()."""

    def responder(cmd: str) -> str:
        if cmd.startswith("get /sim/aircraft"):
            return "/sim/aircraft = 'c172p' (string)\r\n"
        return ""

    sock = _FakeSocket(responder)
    # Pre-load the banner into the recv buffer before connect runs drain.
    sock._recv_buf = b"FlightGear Telnet server\r\n"

    bridge = FGTelnetBridge(socket_factory=_factory_returning(sock))
    bridge.connect(_sleep=_noop)

    # The banner should be gone; get() should return the real reply.
    assert bridge.get("/sim/aircraft") == "c172p"


# ---------------------------------------------------------------------------
# Prompt drain: stray "> " prompt lines are skipped
# ---------------------------------------------------------------------------


def test_prompt_lines_skipped() -> None:
    """Bare '>' lines injected between replies are silently discarded."""

    call_count = [0]

    def responder(cmd: str) -> str:
        if cmd.startswith("get /ai-atc/status"):
            call_count[0] += 1
            # First call: inject a prompt line before the real reply.
            if call_count[0] == 1:
                return ">\r\n/ai-atc/status = 'idle' (string)\r\n"
            return "/ai-atc/status = 'idle' (string)\r\n"
        return ""

    sock = _FakeSocket(responder)
    bridge = FGTelnetBridge(socket_factory=_factory_returning(sock))
    bridge.connect(_sleep=_noop)

    assert bridge.get("/ai-atc/status") == "idle"


# ---------------------------------------------------------------------------
# Peer-close raises BridgeError
# ---------------------------------------------------------------------------


class _ClosingSocket(_FakeSocket):
    """A fake socket that returns empty bytes from recv() (simulates peer close)."""

    def recv(self, n: int) -> bytes:
        return b""  # peer closed


def test_peer_close_raises_bridge_error() -> None:
    """_readline must raise BridgeError when the peer closes the connection."""
    sock = _ClosingSocket()
    bridge = FGTelnetBridge(socket_factory=_factory_returning(sock))
    bridge.connect(_sleep=_noop)

    with pytest.raises(BridgeError, match="closed"):
        bridge.get("/any/prop")
