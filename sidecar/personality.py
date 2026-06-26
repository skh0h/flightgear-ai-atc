"""
Controller personality — deterministic, offline-safe persona generation.

A persona gives the AI controller a stable identity (name, working position,
speaking style, a short backstory, and an accent) so that transmissions can be
flavoured consistently within a session.  Generation is **fully deterministic**:
the same ``seed`` always yields an identical :class:`ControllerPersona`, chosen
from fixed lists via a hash of the seed.  No randomness, no time or network
dependence — safe to call anywhere in the sidecar.

``mood_for`` maps how long the controller has been working (interaction count)
to a mood word, and ``is_quiet_night`` flags the late-night hours when a
controller is more likely to be reflective.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Seeded option pools (>= 8 each so seeds spread out)
# ---------------------------------------------------------------------------

_NAMES: list[str] = [
    "Marcus Reyes",
    "Dana Whitfield",
    "Hiroshi Tanaka",
    "Priya Nair",
    "Liam O'Connor",
    "Sofia Marchetti",
    "Aisha Bello",
    "Gunnar Eriksson",
    "Chen Wei",
    "Yuki Sato",
    "Omar Haddad",
    "Elena Petrova",
]

_STYLES: list[str] = [
    "calm and methodical",
    "brisk and no-nonsense",
    "warm and patient",
    "dry, with deadpan humor",
    "crisp and by-the-book",
    "easygoing and conversational",
    "terse but precise",
    "encouraging and supportive",
]

_BACKSTORIES: list[str] = [
    "Twenty years in the tower; has seen every kind of weather.",
    "Former military controller who values tight discipline.",
    "Came up through ground control and knows every taxiway by heart.",
    "Trains new hires and tends to coach as they work.",
    "Logs hours on the radio between flights they fly themselves.",
    "Grew up next to the field and always wanted this seat.",
    "Quiet pro who lets the work speak for itself.",
    "Veteran of a busy hub, unflappable under pressure.",
]

_ACCENTS: list[str] = [
    "neutral American",
    "soft Irish lilt",
    "clipped British",
    "Midwestern flat",
    "light Scandinavian",
    "gentle Southern drawl",
    "cosmopolitan, hard to place",
    "crisp Pacific Northwest",
]


@dataclass
class ControllerPersona:
    """A stable identity for the AI controller."""

    name: str
    position: str = "Tower"
    style: str = ""
    backstory: str = ""
    accent: str = ""


def _hash_bytes(seed: str) -> bytes:
    """Return a stable digest for ``seed`` (empty seeds are allowed)."""
    return hashlib.sha256((seed or "").encode("utf-8")).digest()


def _pick(options: list[str], digest: bytes, offset: int) -> str:
    """Deterministically choose one of ``options`` using two digest bytes."""
    # Combine two bytes so lists longer than 256 still index cleanly.
    idx = (digest[offset % len(digest)] << 8 | digest[(offset + 1) % len(digest)])
    return options[idx % len(options)]


def generate_persona(seed: str, *, position: str = "Tower") -> ControllerPersona:
    """Build a deterministic persona from ``seed``.

    The same ``seed`` (and ``position``) always returns an identical persona.
    Name, style, backstory, and accent are selected from fixed pools by hashing
    the seed — there is no randomness or time dependence.
    """
    digest = _hash_bytes(seed)
    return ControllerPersona(
        name=_pick(_NAMES, digest, 0),
        position=position,
        style=_pick(_STYLES, digest, 4),
        backstory=_pick(_BACKSTORIES, digest, 8),
        accent=_pick(_ACCENTS, digest, 12),
    )


def mood_for(interaction_count: int, *, quiet_night: bool = False) -> str:
    """Map a controller's workload to a mood word.

    Thresholds: ``fresh`` (0-3), ``brisk`` (4-9), ``tired`` (10-19),
    ``weary`` (20+).  When ``quiet_night`` is set the controller is
    ``reflective`` regardless of count.
    """
    if quiet_night:
        return "reflective"
    n = max(0, int(interaction_count))
    if n <= 3:
        return "fresh"
    if n <= 9:
        return "brisk"
    if n <= 19:
        return "tired"
    return "weary"


def is_quiet_night(local_hour: int) -> bool:
    """True for the late-night window: hour >= 23 or hour < 5."""
    return local_hour >= 23 or local_hour < 5
