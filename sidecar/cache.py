"""
SQLite-backed cache for parsed airport pictures.

Keyed on ``(icao, groundnet_hash)`` so a changed groundnet (new hash) is a clean
cache miss rather than a stale hit.  Pictures are stored as JSON via
:meth:`AirportPicture.model_dump_json` and rehydrated with
:meth:`AirportPicture.model_validate_json`.

All SQL uses ``?`` placeholders — never string interpolation.
"""

from __future__ import annotations

import logging
import sqlite3
from os import PathLike
from pathlib import Path

from sidecar.airport_picture import AirportPicture

_LOG = logging.getLogger(__name__)

_DEFAULT_DB_PATH = "fixtures/cache/airports.sqlite"

# Repo root = parent of the ``sidecar/`` package directory.  Used to anchor
# relative ``db_path`` values so the DB location is independent of the current
# working directory.
_REPO_ROOT = Path(__file__).resolve().parents[1]

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
        raw_path = Path(db_path) if db_path is not None else Path(_DEFAULT_DB_PATH)
        # Anchor RELATIVE paths to the repo root so the DB location does not
        # depend on the process's current working directory.  Absolute paths
        # (e.g. a test's ``tmp_path``) pass through unchanged.
        if raw_path.is_absolute():
            self.db_path = raw_path
        else:
            self.db_path = _REPO_ROOT / raw_path
        parent = self.db_path.parent
        if parent and str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        # WAL improves concurrent read/write resilience.  On some filesystems
        # (or in-memory DBs) the journal mode cannot be set and SQLite reports
        # a different mode (e.g. 'memory') instead of raising — that is fine.
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
        except sqlite3.OperationalError as exc:
            _LOG.warning("PRAGMA setup failed for %s: %s", self.db_path, exc)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def get(self, icao: str, groundnet_hash: str) -> AirportPicture | None:
        """Return the cached picture for ``(icao, groundnet_hash)``, or None.

        A :class:`sqlite3.OperationalError` (locked/busy DB, I/O error) is
        treated as a cache miss rather than crashing the caller.
        """
        try:
            cur = self._conn.execute(
                "SELECT data FROM pictures WHERE icao = ? AND hash = ?",
                (icao, groundnet_hash),
            )
            row = cur.fetchone()
        except sqlite3.OperationalError as exc:
            _LOG.warning("cache get failed for %s/%s: %s", icao, groundnet_hash, exc)
            return None
        if row is None:
            return None
        return AirportPicture.model_validate_json(row[0])

    def put(self, picture: AirportPicture) -> None:
        """Insert or replace the picture, keyed on its icao + groundnet_hash.

        A :class:`sqlite3.OperationalError` is swallowed and logged so a
        transient write failure does not crash the caller.
        """
        try:
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
        except sqlite3.OperationalError as exc:
            _LOG.warning("cache put failed for %s/%s: %s", picture.icao, picture.groundnet_hash, exc)

    def invalidate(self, icao: str) -> None:
        """Delete all cached pictures for an airport (every hash).

        A :class:`sqlite3.OperationalError` is swallowed and logged.
        """
        try:
            self._conn.execute("DELETE FROM pictures WHERE icao = ?", (icao,))
            self._conn.commit()
        except sqlite3.OperationalError as exc:
            _LOG.warning("cache invalidate failed for %s: %s", icao, exc)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "PictureCache":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
