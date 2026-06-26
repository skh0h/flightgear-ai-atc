"""
Blackboard — a small shared world-state context for the sidecar (#46).

The :class:`Blackboard` is a deliberately simple shared store backed by a
:class:`WorldState` dataclass (the well-known, typed fields) plus an open
``extra`` dict for anything ad-hoc.  Reads/writes go through ``get``/``set`` so
callers do not need to know whether a key is a first-class ``WorldState`` field
or an extra; ``snapshot`` returns a flat dict of everything for logging or
publishing.

This module is intentionally dependency-free and deterministic so it is safe to
update on every request without risk to the offline reply path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass
class WorldState:
    """The shared, typed world-state fields the sidecar reasons over.

    All fields default so a ``WorldState()`` is a valid, neutral starting point
    (preflight, no airport, calm wind, normal mode, English/US).
    """

    phase: str = "preflight"
    airport: str = ""
    traffic_count: int = 0
    wind_dir: int = 0
    wind_kt: int = 0
    airspace_class: str = "G"
    mode: str = "normal"
    controller: str = ""
    language: str = "en"
    region: str = "us"


class Blackboard:
    """A shared store backed by :class:`WorldState` fields plus an extra dict.

    Keys that name a ``WorldState`` field read/write that field directly; any
    other key lives in a free-form extra dict.  This keeps the common,
    well-known context strongly typed while still allowing ad-hoc annotations.
    """

    def __init__(self, state: WorldState | None = None) -> None:
        self.state: WorldState = state if state is not None else WorldState()
        self._extra: dict[str, Any] = {}
        self._field_names: frozenset[str] = frozenset(
            f.name for f in fields(WorldState)
        )

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for ``key`` (a WorldState field or an extra key)."""
        if key in self._field_names:
            return getattr(self.state, key)
        return self._extra.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set ``key`` — updates the WorldState field or the extra dict."""
        if key in self._field_names:
            setattr(self.state, key, value)
        else:
            self._extra[key] = value

    def update(self, **kw: Any) -> None:
        """Set several keys at once (each routed via :meth:`set`)."""
        for key, value in kw.items():
            self.set(key, value)

    def snapshot(self) -> dict[str, Any]:
        """Return a flat dict copy of all WorldState fields plus extras."""
        snap: dict[str, Any] = asdict(self.state)
        snap.update(self._extra)
        return snap
