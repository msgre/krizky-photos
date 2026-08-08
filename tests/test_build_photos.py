"""Tests for krizky.build_photos — pure helpers (no external API calls)."""

from __future__ import annotations

import pytest

from krizky_photos.build import (
    _normalize_base_name,
    compare_photos,
    resolve_quality,
)
from krizky_photos.fetch import _parse_row_number


# ---------------------------------------------------------------------------
# resolve_quality
# ---------------------------------------------------------------------------

def test_resolve_quality_size_wins():
    size_cfg = {"name": "micro", "quality": {"jpg": 82, "avif": 52}}
    fmt_cfg = {"format": "jpg", "quality": 85}
    assert resolve_quality(size_cfg, "jpg", fmt_cfg) == 82


def test_resolve_quality_format_fallback():
    size_cfg = {"name": "small"}
    fmt_cfg = {"format": "webp", "quality": 80}
    assert resolve_quality(size_cfg, "webp", fmt_cfg) == 80


def test_resolve_quality_missing_fmt_in_size():
    """Size má quality dict, ale pro daný formát klíč chybí → vezme z formátu."""
    size_cfg = {"name": "micro", "quality": {"jpg": 82}}
    fmt_cfg = {"format": "avif", "quality": 60}
    assert resolve_quality(size_cfg, "avif", fmt_cfg) == 60


def test_resolve_quality_ultimate_fallback():
    size_cfg = {"name": "micro"}
    fmt_cfg = {"format": "webp"}
    assert resolve_quality(size_cfg, "webp", fmt_cfg) == 100


def test_resolve_quality_non_dict_size_quality():
    """Pokud size.quality není dict (neočekávaný config), bere z formátu."""
    size_cfg = {"name": "micro", "quality": 85}
    fmt_cfg = {"format": "jpg", "quality": 80}
    assert resolve_quality(size_cfg, "jpg", fmt_cfg) == 80


# ---------------------------------------------------------------------------
# _parse_row_number
# ---------------------------------------------------------------------------

def test_parse_row_number_simple():
    assert _parse_row_number("007.JPG") == 7


def test_parse_row_number_with_suffix():
    assert _parse_row_number("007-2.jpg") == 7


def test_parse_row_number_non_photo():
    assert _parse_row_number("foto_natura.jpg") is None


def test_parse_row_number_directory():
    assert _parse_row_number("folder") is None


# ---------------------------------------------------------------------------
# _normalize_base_name
# ---------------------------------------------------------------------------

def test_normalize_base_name_primary():
    assert _normalize_base_name("007.JPG", 7) == "007"


def test_normalize_base_name_additional():
    assert _normalize_base_name("007-2.jpg", 7) == "007-2"


def test_normalize_base_name_pads_zeros():
    assert _normalize_base_name("42.jpg", 42) == "042"


def test_normalize_base_name_fallback_to_row():
    """Nestandardní název → fallback na row_number."""
    assert _normalize_base_name("foto.jpg", 42) == "042"


def test_normalize_base_name_uppercase():
    assert _normalize_base_name("432-3.JPG", 432) == "432-3"


# ---------------------------------------------------------------------------
# compare_photos
# ---------------------------------------------------------------------------

PHOTOS_CFG = {"sizes": [{"name": "thumb"}, {"name": "big"}]}


def _entry(title: str, row: int, last_modified: str = "2026-01-01T00:00:00Z", file_id: str = "abc") -> dict:
    return {"title": title, "row_number": row, "last_modified": last_modified, "file_id": file_id}


def test_compare_new_photo():
    gdrive = [_entry("007.jpg", 7)]
    result = compare_photos(gdrive, {}, PHOTOS_CFG)
    assert len(result["to_process"]) == 1
    assert result["to_delete"] == []


def test_compare_unchanged_photo():
    gdrive = [_entry("007.jpg", 7, "2026-01-01T00:00:00Z")]
    cf = {"007": {"_last_modified": "2026-01-01T00:00:00Z", "thumb": {"w": 330, "h": 220}, "big": {"w": 1600, "h": 1067}}}
    result = compare_photos(gdrive, cf, PHOTOS_CFG)
    assert result["to_process"] == []
    assert result["to_delete"] == []


def test_compare_changed_photo():
    gdrive = [_entry("007.jpg", 7, "2026-07-01T00:00:00Z")]
    cf = {"007": {"_last_modified": "2026-01-01T00:00:00Z", "thumb": {"w": 330, "h": 220}, "big": {"w": 1600, "h": 1067}}}
    result = compare_photos(gdrive, cf, PHOTOS_CFG)
    assert len(result["to_process"]) == 1


def test_compare_missing_variant():
    """CF má fotku, ale chybí varianta → reprocess."""
    gdrive = [_entry("007.jpg", 7, "2026-01-01T00:00:00Z")]
    cf = {"007": {"_last_modified": "2026-01-01T00:00:00Z", "thumb": {"w": 330, "h": 220}}}  # big chybí
    result = compare_photos(gdrive, cf, PHOTOS_CFG)
    assert len(result["to_process"]) == 1


def test_compare_photo_to_delete():
    gdrive: list = []
    cf = {"007": {"thumb": {"w": 330, "h": 220}}}
    result = compare_photos(gdrive, cf, PHOTOS_CFG)
    assert result["to_delete"] == ["007"]
    assert result["to_process"] == []


def test_compare_mixed():
    gdrive = [
        _entry("007.jpg", 7, "2026-01-01T00:00:00Z"),  # unchanged
        _entry("008.jpg", 8, "2026-07-01T00:00:00Z"),  # changed
        _entry("009.jpg", 9),                          # new
    ]
    cf = {
        "007": {"_last_modified": "2026-01-01T00:00:00Z", "thumb": {"w": 330, "h": 220}, "big": {"w": 1600, "h": 1067}},
        "008": {"_last_modified": "2026-01-01T00:00:00Z", "thumb": {"w": 330, "h": 220}, "big": {"w": 1600, "h": 1067}},
        "010": {"thumb": {"w": 330, "h": 220}},        # smazaná fotka
    }
    result = compare_photos(gdrive, cf, PHOTOS_CFG)
    assert len(result["to_process"]) == 2  # 008 a 009
    assert "010" in result["to_delete"]


def test_compare_additional_photos():
    """Fotky s suffixem (007-1) se normalizují správně."""
    gdrive = [_entry("007-1.jpg", 7)]
    result = compare_photos(gdrive, {}, PHOTOS_CFG)
    assert len(result["to_process"]) == 1
    assert _normalize_base_name("007-1.jpg", 7) == "007-1"


def test_compare_no_last_modified_checks_only_sizes():
    """CF entry bez _last_modified → neporovnává timestamp, jen varianty."""
    gdrive = [_entry("007.jpg", 7, "2026-07-01T00:00:00Z")]
    # Stará CF metadata bez _last_modified, ale se všemi variantami.
    cf = {"007": {"thumb": {"w": 330, "h": 220}, "big": {"w": 1600, "h": 1067}}}
    result = compare_photos(gdrive, cf, PHOTOS_CFG)
    assert result["to_process"] == []


def test_compare_no_last_modified_missing_variant():
    """CF entry bez _last_modified ale s chybějící variantou → reprocess."""
    gdrive = [_entry("007.jpg", 7, "2026-07-01T00:00:00Z")]
    cf = {"007": {"thumb": {"w": 330, "h": 220}}}  # big chybí
    result = compare_photos(gdrive, cf, PHOTOS_CFG)
    assert len(result["to_process"]) == 1


def test_compare_duplicate_entries_last_wins():
    """Při duplicitním base_name v gdrive_meta se použije poslední záznam."""
    gdrive = [
        _entry("007.jpg", 7, "2026-01-01T00:00:00Z", "file_id_old"),
        _entry("007.jpg", 7, "2026-07-01T00:00:00Z", "file_id_new"),  # přepíše předchozí
    ]
    cf = {"007": {"_last_modified": "2026-01-01T00:00:00Z", "thumb": {"w": 330, "h": 220}, "big": {"w": 1600, "h": 1067}}}
    result = compare_photos(gdrive, cf, PHOTOS_CFG)
    # last_modified se liší → reprocess
    assert len(result["to_process"]) == 1
    assert result["to_process"][0]["file_id"] == "file_id_new"
