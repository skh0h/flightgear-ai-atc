"""
Guardrail — deterministic output validation for ATC clearances (#49).

:func:`validate_clearance` runs a handful of cheap, offline, rule-based checks
over a rendered clearance string and returns a :class:`ValidationResult`.  It is
purely *advisory*: callers are expected to still publish the clearance and use
the issues only for logging / surfacing — never to block the reply.

The checks are intentionally conservative to avoid false positives:

* A runway is only flagged as non-active for an actual takeoff/landing
  clearance ("cleared for takeoff" / "cleared to land").
* The takeoff/hold-short contradiction is only flagged when the *same* runway
  number appears both in the takeoff portion and in the hold-short clause, so a
  legitimate land-and-hold-short of a *different* runway is never flagged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# A runway id mentioned after the word "runway": 1-2 digits + optional L/R/C.
_RWY = re.compile(r"runway\s+(\d{1,2}[LRC]?)", re.IGNORECASE)
# A hold-short runway, with or without the literal word "runway".
_HOLD_RWY = re.compile(
    r"hold short(?:\s+of)?\s+(?:runway\s+)?(\d{1,2}[LRC]?)", re.IGNORECASE
)


@dataclass
class ValidationResult:
    """Outcome of validating a clearance string.

    ``ok`` is simply ``not issues``; ``issues`` lists human-readable problems.
    """

    ok: bool
    issues: list[str] = field(default_factory=list)


def _norm_runway(rwy: str) -> str:
    """Normalise a runway id for comparison (upper-case, strip leading zero).

    ``"01L" -> "1L"``, ``"09" -> "9"``, ``"28R" -> "28R"``.
    """
    s = rwy.strip().upper()
    m = re.match(r"(\d+)([LRC]?)$", s)
    if m:
        return f"{int(m.group(1))}{m.group(2)}"
    return s


def validate_clearance(
    text: str,
    *,
    callsign: str = "",
    active_runways: list[str] | None = None,
    allow_empty: bool = False,
) -> ValidationResult:
    """Validate a rendered clearance ``text`` and return a :class:`ValidationResult`.

    Checks (all deterministic):

    1. Non-empty — unless ``allow_empty`` is set.
    2. When ``callsign`` is given, it must appear verbatim in ``text``.
    3. When ``active_runways`` is given, any ``runway NN`` mentioned in a
       *takeoff/landing* clearance must be one of the active runways.
    4. Contradiction — "cleared for takeoff" *and* "hold short" of the *same*
       runway number.

    ``ok`` is ``True`` exactly when no issues were found.
    """
    issues: list[str] = []
    body = text or ""
    low = body.lower()

    # 1. Non-empty.
    if not body.strip():
        if not allow_empty:
            issues.append("clearance text is empty")
        return ValidationResult(ok=not issues, issues=issues)

    # 2. Callsign present.
    if callsign and callsign not in body:
        issues.append(f"callsign {callsign} missing from clearance text")

    # 3. Runway must be active for a takeoff/landing clearance.
    is_takeoff_or_landing = "cleared for takeoff" in low or "cleared to land" in low
    if active_runways is not None and is_takeoff_or_landing:
        active_norm = {_norm_runway(r) for r in active_runways}
        seen: set[str] = set()
        for rwy in _RWY.findall(body):
            norm = _norm_runway(rwy)
            if norm in seen:
                continue
            seen.add(norm)
            if norm not in active_norm:
                issues.append(
                    f"runway {rwy} is not an active runway for a "
                    f"takeoff/landing clearance"
                )

    # 4. Takeoff + hold-short of the SAME runway -> contradiction.
    if "cleared for takeoff" in low and "hold short" in low:
        idx = low.index("hold short")
        takeoff_rwys = {_norm_runway(r) for r in _RWY.findall(body[:idx])}
        hold_rwys = {_norm_runway(r) for r in _HOLD_RWY.findall(body)}
        common = takeoff_rwys & hold_rwys
        if common:
            shared = ", ".join(sorted(common))
            issues.append(
                f"contradiction: cleared for takeoff and hold short of the "
                f"same runway ({shared})"
            )

    return ValidationResult(ok=not issues, issues=issues)
