"""
SQLite-backed cache for parsed airport pictures.

Keyed on ``(icao, groundnet_hash)`` so a changed groundnet (new hash) is a clean
cache miss rather than a stale hit.  Pictures are stored as JSON via
:meth:`AirportPicture.model_dump_json` and rehydrated with
:meth:`AirportPicture.model_validate_json`.

All SQL uses ``?`` placeholders — never string interpolation.
"""

from __future__ import annotations

import sqlite3
from os import PathLike
from pathlib import Path

from sidecar.airport_picture import AirportPicture

_DEFAULT_DB_PATH = "fixtures/cache/airports.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pictures (
    icao       TEXT NOT NULL,
    hash       TEXT NOT NULL,
    data       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (icao, hash)
)
"""


class PictureCache:
    """A small SQLite store for :class:`AirportPicture` objects.

    The parent directory of ``db_path`` is created on construction, so callers
    may point at ``fixtures/cache/airports.sqlite`` (or a ``tmp_path`` subdir)
    without pre-creating it.
    """

    def __init__(self, db_path: str | PathLike[str] | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else Path(_DEFAULT_DB_PATH)
        parent = self.db_path.parent
        if parent and str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def get(self, icao: str, groundnet_hash: str) -> AirportPicture | None:
        """Return the cached picture for ``(icao, groundnet_hash)``, or None."""
        cur = self._conn.execute(
            "SELECT data FROM pictures WHERE icao = ? AND hash = ?",
            (icao, groundnet_hash),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return AirportPicture.model_validate_json(row[0])

    def put(self, picture: AirportPicture) -> None:
        """Insert or replace the picture, keyed on its icao + groundnet_hash."""
        self._conn.execute(
            "INSERT OR REPLACE INTO pictures (icao, hash, data, created_at) "
            "VALUES (?, ?, ?, ?)",
            (
                picture.icao,
                picture.groundnet_hash,
                picture.model_dump_json(),
                picture.generated_at,
            ),
        )
        self._conn.commit()

    def invalidate(self, icao: str) -> None:
        """Delete all cached pictures for an airport (every hash)."""
        self._conn.execute("DELETE FROM pictures WHERE icao = ?", (icao,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "PictureCache":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
