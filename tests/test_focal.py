"""Tests for krizky_photos.focal — loading and normalization of focal_points.json."""

from __future__ import annotations

import json
import logging

import pytest

from krizky_photos.focal import (
    FocalPointsError,
    load_focal_points,
    resolve_focal_points_path,
    _normalize,
)


# ---------------------------------------------------------------------------
# resolve_focal_points_path
# ---------------------------------------------------------------------------

def test_resolve_default_path(tmp_path):
    photos_cfg: dict = {}
    sources_output = tmp_path / "sources"
    path, explicit = resolve_focal_points_path(photos_cfg, tmp_path, sources_output)
    assert path == sources_output / "photos" / "focal_points.json"
    assert explicit is False


def test_resolve_explicit_path_relative_to_config_dir(tmp_path):
    photos_cfg = {"focal_points": "data/focal_points.json"}
    sources_output = tmp_path / "sources"
    path, explicit = resolve_focal_points_path(photos_cfg, tmp_path, sources_output)
    assert path == (tmp_path / "data" / "focal_points.json").resolve()
    assert explicit is True


def test_resolve_explicit_path_absolute(tmp_path):
    absolute = tmp_path / "custom" / "fp.json"
    photos_cfg = {"focal_points": str(absolute)}
    path, explicit = resolve_focal_points_path(photos_cfg, tmp_path, tmp_path / "sources")
    assert path == absolute.resolve()
    assert explicit is True


# ---------------------------------------------------------------------------
# load_focal_points — default path behavior
# ---------------------------------------------------------------------------

def test_load_default_missing_returns_empty_with_warning(tmp_path, caplog):
    photos_cfg: dict = {}
    sources_output = tmp_path / "sources"
    with caplog.at_level(logging.WARNING, logger="krizky_photos.focal"):
        result = load_focal_points(photos_cfg, tmp_path, sources_output)
    assert result == {}
    assert any("Focal points file not found" in rec.message for rec in caplog.records)


def test_load_default_present(tmp_path):
    sources_output = tmp_path / "sources"
    fp_dir = sources_output / "photos"
    fp_dir.mkdir(parents=True)
    (fp_dir / "focal_points.json").write_text(json.dumps({"007": "50% 46%"}), encoding="utf-8")
    result = load_focal_points({}, tmp_path, sources_output)
    assert result == {"007": "50% 46%"}


# ---------------------------------------------------------------------------
# load_focal_points — explicit path behavior
# ---------------------------------------------------------------------------

def test_load_explicit_missing_raises(tmp_path):
    photos_cfg = {"focal_points": "data/does_not_exist.json"}
    with pytest.raises(FocalPointsError, match="focal_points file not found"):
        load_focal_points(photos_cfg, tmp_path, tmp_path / "sources")


def test_load_explicit_present(tmp_path):
    fp_dir = tmp_path / "data"
    fp_dir.mkdir()
    (fp_dir / "fp.json").write_text(json.dumps({"007": "50% 46%", "008": "30% 20%"}), encoding="utf-8")
    photos_cfg = {"focal_points": "data/fp.json"}
    result = load_focal_points(photos_cfg, tmp_path, tmp_path / "sources")
    assert result == {"007": "50% 46%", "008": "30% 20%"}


def test_load_explicit_invalid_json_raises(tmp_path):
    fp_dir = tmp_path / "data"
    fp_dir.mkdir()
    (fp_dir / "fp.json").write_text("{ not: json", encoding="utf-8")
    photos_cfg = {"focal_points": "data/fp.json"}
    with pytest.raises(FocalPointsError, match="Invalid JSON"):
        load_focal_points(photos_cfg, tmp_path, tmp_path / "sources")


def test_load_explicit_non_dict_raises(tmp_path):
    fp_dir = tmp_path / "data"
    fp_dir.mkdir()
    (fp_dir / "fp.json").write_text(json.dumps(["a", "b"]), encoding="utf-8")
    photos_cfg = {"focal_points": "data/fp.json"}
    with pytest.raises(FocalPointsError, match="must be a JSON object"):
        load_focal_points(photos_cfg, tmp_path, tmp_path / "sources")


# ---------------------------------------------------------------------------
# _normalize — legacy keys + duplicates
# ---------------------------------------------------------------------------

def test_normalize_strips_extension():
    result = _normalize({"047.jpg": "30% 70%"}, "unused")
    assert result == {"047": "30% 70%"}


def test_normalize_keeps_variant_suffix():
    """Klíč 246-3 (varianta) není postižen; Path(k).stem == '246-3'."""
    result = _normalize({"246-3": "50% 40%"}, "unused")
    assert result == {"246-3": "50% 40%"}


def test_normalize_warns_on_legacy_keys(caplog):
    with caplog.at_level(logging.WARNING, logger="krizky_photos.focal"):
        _normalize({"005.jpg": "50% 17%", "007": "50% 46%"}, "path.json")
    assert any(
        "legacy format" in rec.message and "005.jpg" in rec.message for rec in caplog.records
    )


def test_normalize_no_warning_when_all_keys_clean(caplog):
    with caplog.at_level(logging.WARNING, logger="krizky_photos.focal"):
        _normalize({"005": "50% 17%", "007": "50% 46%"}, "path.json")
    assert not any("legacy format" in rec.message for rec in caplog.records)


def test_normalize_warns_on_duplicates_after_normalization(caplog):
    with caplog.at_level(logging.WARNING, logger="krizky_photos.focal"):
        result = _normalize({"005.jpg": "50% 17%", "005": "10% 90%"}, "path.json")
    assert any("Duplicate" in rec.message and "005" in rec.message for rec in caplog.records)
    # Last value wins (dict iteration order).
    assert result == {"005": "10% 90%"}


def test_normalize_same_value_duplicates_are_silent(caplog):
    """Když je hodnota u 005.jpg i 005 stejná, není to konflikt."""
    with caplog.at_level(logging.WARNING, logger="krizky_photos.focal"):
        _normalize({"005.jpg": "50% 17%", "005": "50% 17%"}, "path.json")
    assert not any("Duplicate" in rec.message for rec in caplog.records)
