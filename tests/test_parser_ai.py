"""Tests for sidecar/parser_ai.py — fake Gemini client, no network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sidecar.airport_picture import AIAirportResponse, SegmentLabel
from sidecar.gemini_client import OfflineError
from sidecar.parser_ai import parse_with_ai

_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "KSFO.groundnet.xml"


class _FakeClient:
    """Stand-in matching GeminiClient.generate()'s signature."""

    def __init__(self, response: Any = None, raise_offline: bool = False) -> None:
        self._response = response
        self._raise_offline = raise_offline
        self.calls = 0

    def generate(self, prompt: str, schema: type, *, model: str | None = None) -> Any:
        self.calls += 1
        if self._raise_offline:
            raise OfflineError("forced offline")
        return self._response


def _ai_response() -> AIAirportResponse:
    """Return a label-only AIAirportResponse labeling a real KSFO segment.

    Segment (0, 490) exists in the KSFO fixture and has no name in the source,
    so it is a realistic target for AI labeling.
    """
    return AIAirportResponse(
        taxiway_labels=[
            SegmentLabel(begin=0, end=490, name="AI-Alpha"),
        ]
    )


def test_ai_success_returns_source_ai_with_computed_fields() -> None:
    """On success with flag enabled: source=='ai', AI label merged onto unnamed segment."""
    client = _FakeClient(response=_ai_response())
    xml = _FIXTURE.read_text()
    pic = parse_with_ai("KSFO", xml, client, ai_taxiway_labels=True)  # type: ignore[arg-type]

    assert client.calls == 1
    assert pic.source == "ai"
    assert pic.icao == "KSFO"
    # taxi_graph and hash are code-parser derived (not recomputed from AI data).
    assert len(pic.taxi_graph) > 0
    assert len(pic.groundnet_hash) == 64
    assert pic.generated_at

    # Find segment (0, 490) and verify the AI label was applied.
    labeled = [
        s for s in pic.segments if {s.begin, s.end} == {0, 490}
    ]
    assert labeled, "Segment (0, 490) not found in picture"
    assert labeled[0].name == "AI-Alpha"

    # At least one other segment should exist with its code-parser name
    # (possibly empty, but the point is AI didn't blank everything out).
    other = [s for s in pic.segments if {s.begin, s.end} != {209, 210}]
    assert other, "Expected more than one segment from the KSFO fixture"


def test_ai_offline_falls_back_to_code_parser() -> None:
    client = _FakeClient(raise_offline=True)
    xml = _FIXTURE.read_text()
    pic = parse_with_ai("KSFO", xml, client, ai_taxiway_labels=True)  # type: ignore[arg-type]
    assert client.calls == 1
    assert pic.source == "code"
    assert len(pic.nodes) > 0  # the real fixture was parsed by the code path


def test_hash_matches_between_ai_and_offline_paths() -> None:
    xml = _FIXTURE.read_text()
    ai_pic = parse_with_ai("KSFO", xml, _FakeClient(response=_ai_response()), ai_taxiway_labels=True)  # type: ignore[arg-type]
    code_pic = parse_with_ai("KSFO", xml, _FakeClient(raise_offline=True), ai_taxiway_labels=True)  # type: ignore[arg-type]
    # Both paths call parse_groundnet on the same bytes -> identical hash.
    assert ai_pic.groundnet_hash == code_pic.groundnet_hash


def test_ai_labels_unlabeled_segments_only() -> None:
    """Segments NOT in the AI label list keep their code-parser name unchanged."""
    xml = _FIXTURE.read_text()
    # Segment (0, 490) exists in KSFO and is unnamed in the source.
    response = AIAirportResponse(
        taxiway_labels=[SegmentLabel(begin=0, end=490, name="Tango")]
    )
    pic = parse_with_ai("KSFO", xml, _FakeClient(response=response), ai_taxiway_labels=True)  # type: ignore[arg-type]

    # The labeled segment carries the AI name.
    labeled = [s for s in pic.segments if {s.begin, s.end} == {0, 490}]
    assert labeled and labeled[0].name == "Tango"

    # A segment not in the label list keeps whatever name parse_groundnet gave it.
    from sidecar import parser_code
    code_pic = parser_code.parse_groundnet(xml, "KSFO")
    code_segs = {(s.begin, s.end): s.name for s in code_pic.segments}
    for seg in pic.segments:
        if {seg.begin, seg.end} == {0, 490}:
            continue
        code_name = code_segs.get((seg.begin, seg.end)) or code_segs.get(
            (seg.end, seg.begin), ""
        )
        assert seg.name == code_name, (
            f"Segment ({seg.begin},{seg.end}) name changed unexpectedly: "
            f"{seg.name!r} != {code_name!r}"
        )


def test_empty_label_list_leaves_all_segments_unchanged() -> None:
    """An empty taxiway_labels list produces the same segments as the code parser."""
    xml = _FIXTURE.read_text()
    response = AIAirportResponse(taxiway_labels=[])
    ai_pic = parse_with_ai("KSFO", xml, _FakeClient(response=response), ai_taxiway_labels=True)  # type: ignore[arg-type]

    from sidecar import parser_code
    code_pic = parser_code.parse_groundnet(xml, "KSFO")

    assert len(ai_pic.segments) == len(code_pic.segments)
    for ai_seg, code_seg in zip(ai_pic.segments, code_pic.segments):
        assert ai_seg.name == code_seg.name


# ---------------------------------------------------------------------------
# New safety-policy tests
# ---------------------------------------------------------------------------


def test_data_only_mode_skips_gemini_call() -> None:
    """With ai_taxiway_labels=False (default), Gemini is never called."""
    client = _FakeClient(response=_ai_response())
    xml = _FIXTURE.read_text()
    pic = parse_with_ai("KSFO", xml, client)  # default: ai_taxiway_labels=False

    assert client.calls == 0, "Gemini must not be called in data-only mode"
    assert pic.source == "code"
    assert pic.icao == "KSFO"
    assert len(pic.nodes) > 0


def test_data_only_mode_contains_no_ai_labels() -> None:
    """In data-only mode the picture has only real groundnet names — no AI guesses."""
    from sidecar import parser_code

    xml = _FIXTURE.read_text()
    client = _FakeClient(response=_ai_response())
    pic = parse_with_ai("KSFO", xml, client)  # default: ai_taxiway_labels=False

    code_pic = parser_code.parse_groundnet(xml, "KSFO")
    code_names = {(s.begin, s.end): s.name for s in code_pic.segments}

    for seg in pic.segments:
        expected = code_names.get((seg.begin, seg.end), "")
        assert seg.name == expected, (
            f"Segment ({seg.begin},{seg.end}) has name {seg.name!r} "
            f"but groundnet says {expected!r}"
        )


def test_additive_guard_never_overwrites_real_name() -> None:
    """An AI label for a segment that already has a real name must be ignored."""
    from sidecar import parser_code

    xml = _FIXTURE.read_text()
    # Find a segment that the code parser gives a non-empty name.
    code_pic = parser_code.parse_groundnet(xml, "KSFO")
    named_seg = next(s for s in code_pic.segments if s.name)

    # Craft an AI response that tries to relabel that already-named segment.
    response = AIAirportResponse(
        taxiway_labels=[
            SegmentLabel(begin=named_seg.begin, end=named_seg.end, name="FAKE-OVERRIDE"),
        ]
    )
    pic = parse_with_ai(
        "KSFO", xml, _FakeClient(response=response), ai_taxiway_labels=True  # type: ignore[arg-type]
    )

    result_seg = next(
        s for s in pic.segments
        if s.begin == named_seg.begin and s.end == named_seg.end
    )
    assert result_seg.name == named_seg.name, (
        f"Real name {named_seg.name!r} was overwritten by AI label 'FAKE-OVERRIDE'"
    )


def test_ai_label_applied_to_unnamed_segment_when_flag_enabled() -> None:
    """With ai_taxiway_labels=True, an AI label IS applied to a genuinely unnamed segment."""
    xml = _FIXTURE.read_text()
    # Segment (0, 490) is unnamed in the KSFO fixture.
    response = AIAirportResponse(
        taxiway_labels=[SegmentLabel(begin=0, end=490, name="Echo")]
    )
    client = _FakeClient(response=response)
    pic = parse_with_ai("KSFO", xml, client, ai_taxiway_labels=True)  # type: ignore[arg-type]

    assert client.calls == 1
    assert pic.source == "ai"
    labeled = [s for s in pic.segments if {s.begin, s.end} == {0, 490}]
    assert labeled and labeled[0].name == "Echo"
