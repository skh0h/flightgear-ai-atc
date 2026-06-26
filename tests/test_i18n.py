"""Tests for sidecar/i18n.py — language directives and regional phrase packs.

Both helpers are pure and deterministic: no network, no state, no timestamps,
so identical inputs always produce identical output.
"""

from __future__ import annotations

from sidecar.i18n import REGION_OVERRIDES, apply_region, language_directive


# --- language_directive ----------------------------------------------------


def test_english_returns_empty_string() -> None:
    assert language_directive("en") == ""


def test_empty_and_blank_return_empty_string() -> None:
    assert language_directive("") == ""
    assert language_directive("   ") == ""


def test_french_is_non_empty_and_names_the_language() -> None:
    out = language_directive("fr")
    assert out != ""
    assert "French" in out
    assert out == "Respond in French using ICAO phraseology."


def test_german_is_non_empty_and_names_the_language() -> None:
    out = language_directive("de")
    assert out != ""
    assert "German" in out
    assert out == "Respond in German using ICAO phraseology."


def test_spanish_and_chinese_are_non_empty() -> None:
    assert language_directive("es") != ""
    assert language_directive("zh") != ""
    assert "Spanish" in language_directive("es")
    assert "Chinese" in language_directive("zh")


def test_case_insensitive_language_code() -> None:
    assert language_directive("FR") == language_directive("fr")
    assert language_directive("EN") == ""


def test_unknown_language_returns_empty_string() -> None:
    # Unknown codes never crash; they leave the prompt unchanged.
    assert language_directive("xx") == ""


def test_language_directive_is_deterministic() -> None:
    assert language_directive("de") == language_directive("de")


# --- apply_region ----------------------------------------------------------


def test_uk_substitutes_active_runway() -> None:
    out = apply_region("Taxi to the active runway via Alpha.", "uk")
    assert "the runway in use" in out
    assert "the active runway" not in out


def test_us_region_is_a_noop() -> None:
    text = "Taxi to the active runway via Alpha."
    assert apply_region(text, "us") == text


def test_unknown_region_leaves_text_unchanged() -> None:
    text = "Taxi to the active runway via Alpha."
    assert apply_region(text, "zz") == text


def test_empty_text_is_returned_unchanged() -> None:
    assert apply_region("", "uk") == ""


def test_region_code_is_case_insensitive() -> None:
    out = apply_region("the active runway", "UK")
    assert out == "the runway in use"


def test_apply_region_is_deterministic() -> None:
    text = "Join the traffic pattern for the active runway."
    assert apply_region(text, "uk") == apply_region(text, "uk")


def test_region_overrides_has_us_and_uk_packs() -> None:
    assert "us" in REGION_OVERRIDES
    assert "uk" in REGION_OVERRIDES
    # US is the empty baseline pack.
    assert REGION_OVERRIDES["us"] == {}
    # UK pack carries the documented active-runway override.
    assert REGION_OVERRIDES["uk"]["the active runway"] == "the runway in use"
