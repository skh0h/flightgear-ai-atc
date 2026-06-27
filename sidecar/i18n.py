"""Multi-language directives and regional phraseology packs for the AI ATC sidecar.

Two tiny, fully deterministic helpers — no network, no state, no timestamps —
so identical inputs always produce identical output and unit tests stay trivial.

* :func:`language_directive` turns a language code into a one-line instruction
  that can be appended to the online (LLM) prompt context.  English (``"en"``)
  is the default and yields an empty string so the prompt is unchanged.
* :data:`REGION_OVERRIDES` plus :func:`apply_region` apply literal,
  region-specific word swaps to already-rendered ATC text (e.g. US
  ``"the active runway"`` -> UK ``"the runway in use"``).  Unknown regions and
  the default ``"us"`` pack are no-ops.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Multi-language (#42)
# ---------------------------------------------------------------------------

# Map of ISO-639-1 language codes to their human-readable names.  ``en`` is the
# default and deliberately absent here so it produces no directive.
_LANGUAGE_NAMES: dict[str, str] = {
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "zh": "Chinese",
    "ja": "Japanese",
    "ru": "Russian",
}


def language_directive(lang: str) -> str:
    """Return a one-line prompt directive for the requested *lang*.

    English (``"en"``), the empty string, or any unknown code returns ``""`` so
    the prompt is left unchanged.  Recognised non-English codes (``fr``, ``de``,
    ``es``, ``zh`` etc.) return
    ``"Respond in <Language> using ICAO phraseology."``.
    """
    code = (lang or "").strip().lower()
    if not code or code == "en":
        return ""
    name = _LANGUAGE_NAMES.get(code)
    if name is None:
        return ""
    return f"Respond in {name} using ICAO phraseology."


# ---------------------------------------------------------------------------
# Regional packs (#4)
# ---------------------------------------------------------------------------

# Literal substitutions applied to rendered ATC text per region.  Keys are
# lower-cased region codes; values map a US/default phrase to its regional
# variant.  ``us`` is the baseline and intentionally empty.
REGION_OVERRIDES: dict[str, dict[str, str]] = {
    "us": {},
    "uk": {
        "the active runway": "the runway in use",
        "active runway": "runway in use",
        "traffic pattern": "circuit",
        "downwind leg": "downwind",
    },
}


def apply_region(text: str, region: str) -> str:
    """Apply this *region*'s literal phrase substitutions to *text*.

    The default ``"us"`` pack and any unknown region leave *text* unchanged.
    Substitutions are plain string replacements applied in definition order.
    """
    if not text:
        return text
    overrides = REGION_OVERRIDES.get((region or "").strip().lower())
    if not overrides:
        return text
    out = text
    for src, dst in overrides.items():
        out = out.replace(src, dst)
    return out
