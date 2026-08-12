"""Tests for krizky.photo_context — PhotoContext."""

from __future__ import annotations

import pytest

from krizky_photos.context import PhotoContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FORMATS = [
    {"format": "avif", "mime": "image/avif", "quality": 60},
    {"format": "webp", "mime": "image/webp", "quality": 80},
    {"format": "jpg",  "mime": "image/jpeg", "quality": 85},
]

SIZES = [
    {"name": "micro",  "max_width": 150},
    {"name": "thumb",  "max_width": 330},
    {"name": "big",    "max_width": 1600},
]

BASE_URL = "https://cdn.example.com"


def _ctx(cf_meta: dict, focal_points: dict | None = None) -> PhotoContext:
    return PhotoContext(cf_meta, focal_points or {}, BASE_URL, FORMATS, SIZES)


# ---------------------------------------------------------------------------
# has_photos / counts
# ---------------------------------------------------------------------------

def test_no_photos_for_row():
    ctx = _ctx({})
    result = ctx(42)
    assert result["has_photos"] is False
    assert result["primary"] is None
    assert result["additional"] == []
    assert result["count"] == 0
    assert result["all"] == []


def test_primary_only():
    cf = {"042": {"micro": {"w": 150, "h": 100}, "thumb": {"w": 330, "h": 220}, "big": {"w": 1600, "h": 1067}}}
    result = _ctx(cf)(42)
    assert result["has_photos"] is True
    assert result["primary"] is not None
    assert result["count"] == 1
    assert result["additional"] == []


def test_primary_and_additional():
    cf = {
        "007": {"big": {"w": 1600, "h": 1200}},
        "007-1": {"big": {"w": 1600, "h": 900}},
        "007-2": {"big": {"w": 800, "h": 600}},
    }
    result = _ctx(cf)(7)
    assert result["count"] == 3
    assert len(result["additional"]) == 2
    assert result["all"][0]["base_name"] == "007"
    assert result["all"][1]["base_name"] == "007-1"
    assert result["all"][2]["base_name"] == "007-2"


def test_additional_stops_at_gap():
    """Pokud chybí 007-1, nehledá dál (007-2 se ignoruje)."""
    cf = {
        "007": {"big": {"w": 1600, "h": 1200}},
        "007-2": {"big": {"w": 800, "h": 600}},   # 007-1 chybí → stop
    }
    result = _ctx(cf)(7)
    assert result["count"] == 1


# ---------------------------------------------------------------------------
# photo_dict structure
# ---------------------------------------------------------------------------

def test_photo_dict_base_name():
    cf = {"007": {"big": {"w": 1600, "h": 1200}}}
    photo = _ctx(cf)(7)["primary"]
    assert photo["base_name"] == "007"


def test_photo_dict_src_url():
    cf = {"007": {"big": {"w": 1600, "h": 1200}}}
    photo = _ctx(cf)(7)["primary"]
    assert photo["src"] == f"{BASE_URL}/007_big.jpg"


def test_photo_dict_width_height_from_largest():
    cf = {"007": {"micro": {"w": 150, "h": 100}, "big": {"w": 1600, "h": 1200}}}
    photo = _ctx(cf)(7)["primary"]
    assert photo["width"] == 1600
    assert photo["height"] == 1200


def test_photo_dict_variants_keys():
    cf = {"007": {"micro": {"w": 150, "h": 100}, "big": {"w": 1600, "h": 1200}}}
    photo = _ctx(cf)(7)["primary"]
    assert "micro" in photo["variants"]
    assert "big" in photo["variants"]
    assert "_last_modified" not in photo["variants"]


def test_photo_dict_variant_url():
    cf = {"007": {"thumb": {"w": 330, "h": 220}}}
    photo = _ctx(cf)(7)["primary"]
    assert photo["variants"]["thumb"]["url"] == f"{BASE_URL}/007_thumb.jpg"
    assert photo["variants"]["thumb"]["w"] == 330
    assert photo["variants"]["thumb"]["h"] == 220


def test_photo_dict_sources_excludes_jpg():
    """sources list obsahuje pouze AVIF a WebP, ne JPEG."""
    cf = {"007": {"big": {"w": 1600, "h": 1200}}}
    photo = _ctx(cf)(7)["primary"]
    mime_types = [s["mime"] for s in photo["sources"]]
    assert "image/jpeg" not in mime_types
    assert "image/avif" in mime_types
    assert "image/webp" in mime_types


def test_photo_dict_srcset_contains_jpg_urls():
    cf = {"007": {"micro": {"w": 150, "h": 100}, "big": {"w": 1600, "h": 1200}}}
    photo = _ctx(cf)(7)["primary"]
    assert "007_micro.jpg" in photo["srcset"]
    assert "007_big.jpg" in photo["srcset"]
    assert "150w" in photo["srcset"]
    assert "1600w" in photo["srcset"]


def test_photo_dict_avif_srcset_in_sources():
    cf = {"007": {"micro": {"w": 150, "h": 100}, "big": {"w": 1600, "h": 1200}}}
    photo = _ctx(cf)(7)["primary"]
    avif_source = next(s for s in photo["sources"] if s["mime"] == "image/avif")
    assert "007_micro.avif" in avif_source["srcset"]
    assert "007_big.avif" in avif_source["srcset"]


def test_photo_dict_focal_point_present():
    cf = {"007": {"big": {"w": 1600, "h": 1200}}}
    fp = {"007": "30% 70%"}
    photo = _ctx(cf, fp)(7)["primary"]
    assert photo["focal_point"] == "30% 70%"


def test_photo_dict_focal_point_absent():
    cf = {"007": {"big": {"w": 1600, "h": 1200}}}
    photo = _ctx(cf)(7)["primary"]
    assert photo["focal_point"] is None


def test_photo_dict_last_modified_not_in_variants():
    """_last_modified klíč v cf_meta se do variants nepropaguje."""
    cf = {"007": {"_last_modified": "2026-01-01T00:00:00Z", "big": {"w": 1600, "h": 1200}}}
    photo = _ctx(cf)(7)["primary"]
    assert "_last_modified" not in photo["variants"]


def test_base_url_trailing_slash_stripped():
    cf = {"007": {"big": {"w": 1600, "h": 1200}}}
    ctx = PhotoContext(cf, {}, "https://cdn.example.com/", FORMATS, SIZES)
    photo = ctx(7)["primary"]
    assert "//007_big.jpg" not in photo["src"]
    assert photo["src"].startswith("https://cdn.example.com/007_big.jpg")
