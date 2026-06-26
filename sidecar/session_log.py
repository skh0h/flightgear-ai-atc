"""
Session memory — a small bounded log of recent ATC interactions.

:class:`SessionMemory` keeps the last ``max_recent`` exchanges so the sidecar
can feed a compact summary back into the online prompt (for continuity) and
build relief-briefings.  It is intentionally tiny and offline-safe: a ring of
recent items, oldest dropped first.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class _Interaction:
    req_type: str
    callsign: str
    response_text: str


class SessionMemory:
    """A bounded, ordered record of recent interactions.

    Newest items are appended last; once ``max_recent`` is exceeded the oldest
    items are discarded.  ``count`` reports the total number of interactions
    ever remembered (not just those still retained).
    """

    def __init__(self, max_recent: int = 8) -> None:
        self._max_recent = max(1, int(max_recent))
        self._items: deque[_Interaction] = deque(maxlen=self._max_recent)
        self._count = 0

    def remember(self, req_type: str, callsign: str, response_text: str) -> None:
        """Record one interaction (oldest dropped past ``max_recent``)."""
        self._items.append(
            _Interaction(
                req_type=req_type or "",
                callsign=callsign or "",
                response_text=response_text or "",
            )
        )
        self._count += 1

    def recent_context(self, n: int = 5) -> str:
        """Return a compact multi-line summary of the last ``n`` interactions.

        Each line is ``"callsign: req_type -> response"``, oldest first / most
        recent last.  Returns ``""`` when there is nothing to report.
        """
        if n <= 0 or not self._items:
            return ""
        recent = list(self._items)[-n:]
        return "\n".join(
            f"{it.callsign}: {it.req_type} -> {it.response_text}" for it in recent
        )

    @property
    def count(self) -> int:
        """Total interactions remembered over the session's lifetime."""
        return self._count
