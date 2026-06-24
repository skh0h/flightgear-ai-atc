"""Tests for sidecar/cache.py — SQLite round-trip, miss, invalidate, dir-create."""

from __future__ import annotations

from sidecar.airport_picture import AirportPicture, Frequencies, Node, Segment
from sidecar.cache import PictureCache


def _picture(icao: str = "KSFO", h: str = "hash-aaa") -> AirportPicture:
    return AirportPicture(
        icao=icao,
        source="code",
        generated_at="2026-06-24T00:00:00+00:00",
        groundnet_hash=h,
        nodes=[Node(index=1, lat=37.6, lon=-122.3), Node(index=2, lat=37.61, lon=-122.31)],
        segments=[Segment(begin=1, end=2, name="A")],
        frequencies=Frequencies(ground="121.80"),
        taxi_graph={1: [2], 2: [1]},
    )


def test_put_get_round_trip(tmp_path) -> None:
    cache = PictureCache(tmp_path / "airports.sqlite")
    pic = _picture()
    cache.put(pic)
    assert cache.get("KSFO", "hash-aaa") == pic
    cache.close()


def test_get_miss_on_different_hash(tmp_path) -> None:
    cache = PictureCache(tmp_path / "airports.sqlite")
    cache.put(_picture(h="hash-aaa"))
    assert cache.get("KSFO", "different-hash") is None
    assert cache.get("KLAX", "hash-aaa") is None
    cache.close()


def test_invalidate_removes_all_hashes_for_icao(tmp_path) -> None:
    cache = PictureCache(tmp_path / "airports.sqlite")
    cache.put(_picture(h="hash-aaa"))
    cache.put(_picture(h="hash-bbb"))
    cache.invalidate("KSFO")
    assert cache.get("KSFO", "hash-aaa") is None
    assert cache.get("KSFO", "hash-bbb") is None
    cache.close()


def test_put_replaces_existing_key(tmp_path) -> None:
    cache = PictureCache(tmp_path / "airports.sqlite")
    cache.put(_picture(h="hash-aaa"))
    updated = _picture(h="hash-aaa").model_copy(
        update={"frequencies": Frequencies(ground="999.99")}
    )
    cache.put(updated)
    got = cache.get("KSFO", "hash-aaa")
    assert got is not None
    assert got.frequencies.ground == "999.99"
    cache.close()


def test_creates_missing_parent_directory(tmp_path) -> None:
    nested = tmp_path / "deep" / "nested" / "dir" / "airports.sqlite"
    assert not nested.parent.exists()
    cache = PictureCache(nested)
    assert nested.parent.exists()
    cache.put(_picture())
    assert cache.get("KSFO", "hash-aaa") is not None
    cache.close()


def test_context_manager_closes(tmp_path) -> None:
    with PictureCache(tmp_path / "airports.sqlite") as cache:
        cache.put(_picture())
        assert cache.get("KSFO", "hash-aaa") is not None
