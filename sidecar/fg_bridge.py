"""
FlightGear telnet property-server bridge.

Speaks FlightGear's raw telnet property protocol (the server started with
``--telnet=5501``).  The protocol is line-oriented and request/response:

    get <prop>            -> "<prop> = 'value' (type)"
    set <prop> <value>    -> (no reply)
    ls [dir] / cd / pwd / dump / quit

The basic telnet protocol does not push asynchronous updates, so change
notification is implemented by polling (:meth:`subscribe`).  Connections retry
with exponential back-off while FlightGear is still starting up.

Tests drive this against an in-process mock socket (no live FlightGear): the
``socket_factory`` and ``sleep`` seams are injectable.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Callable
from typing import Any


class BridgeError(Exception):
    """Raised on connection failure or when an operation needs a live socket."""


def _parse_get(line: str) -> str:
    """Extract the value from a telnet ``get`` reply.

    Handles ``"/p = 'c172p' (string)"`` and ``"/p = 37.6 (double)"`` as well as
    a bare value line.  Returns the unquoted value with any trailing ``(type)``
    annotation removed.
    """
    line = line.strip()
    if "=" not in line:
        return line
    rhs = line.split("=", 1)[1].strip()
    if rhs.endswith(")") and "(" in rhs:
        rhs = rhs[: rhs.rfind("(")].strip()
    if len(rhs) >= 2 and rhs[0] in "'\"" and rhs[-1] == rhs[0]:
        rhs = rhs[1:-1]
    return rhs


class FGTelnetBridge:
    """A thin synchronous client for the FlightGear telnet property server."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5501,
        *,
        timeout: float = 5.0,
        socket_factory: Callable[..., socket.socket] = socket.socket,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._socket_factory = socket_factory
        self._sock: socket.socket | None = None
        self._buf = b""

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(
        self,
        *,
        retries: int = 5,
        backoff: float = 0.5,
        _sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Open the socket, retrying with exponential back-off.

        Raises:
            BridgeError: If all attempts fail (FlightGear never came up).
        """
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                sock = self._socket_factory(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self._timeout)
                sock.connect((self._host, self._port))
                self._sock = sock
                self._buf = b""
                return
            except OSError as exc:
                last_exc = exc
                if attempt < retries - 1:
                    _sleep(backoff * (2 ** attempt))
        raise BridgeError(
            f"could not connect to FlightGear telnet at {self._host}:{self._port}: "
            f"{last_exc}"
        )

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def _require_sock(self) -> socket.socket:
        if self._sock is None:
            raise BridgeError("not connected — call connect() first")
        return self._sock

    # ------------------------------------------------------------------
    # Line I/O
    # ------------------------------------------------------------------

    def _send(self, line: str) -> None:
        sock = self._require_sock()
        sock.sendall((line + "\r\n").encode("utf-8"))

    def _readline(self) -> str:
        sock = self._require_sock()
        while b"\n" not in self._buf:
            chunk = sock.recv(4096)
            if not chunk:  # peer closed
                break
            self._buf += chunk
        line, _, rest = self._buf.partition(b"\n")
        self._buf = rest
        return line.decode("utf-8", "replace").rstrip("\r")

    # ------------------------------------------------------------------
    # Property operations
    # ------------------------------------------------------------------

    def get(self, path: str) -> str:
        """Return the value of a property (always as a string)."""
        self._send(f"get {path}")
        return _parse_get(self._readline())

    def set(self, path: str, value: Any) -> None:
        """Set a property value."""
        self._send(f"set {path} {value}")

    def poll(self, path: str) -> str:
        """Alias for :meth:`get`, named for its polling role in the event loop."""
        return self.get(path)

    def subscribe(
        self,
        path: str,
        callback: Callable[[str], None],
        *,
        interval: float = 0.1,
        count: int | None = None,
        _sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Poll ``path`` and invoke ``callback`` whenever the value changes.

        The basic telnet protocol has no push notifications, so this polls at
        ``interval`` seconds.  ``count`` bounds the number of polls (``None`` =
        run until interrupted); tests pass a finite ``count`` and a no-op sleep.
        """
        previous: object = object()  # sentinel guarantees the first read fires
        polls = 0
        while count is None or polls < count:
            value = self.get(path)
            if value != previous:
                previous = value
                callback(value)
            polls += 1
            if count is None or polls < count:
                _sleep(interval)

    def close(self) -> None:
        """Send ``quit`` (best effort) and close the socket."""
        if self._sock is not None:
            try:
                self._send("quit")
            except OSError:
                pass
            try:
                self._sock.close()
            finally:
                self._sock = None

    def __enter__(self) -> "FGTelnetBridge":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
