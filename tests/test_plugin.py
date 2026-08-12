"""Tests for krizky_photos.plugin — inject_head focal_points wiring."""

from __future__ import annotations

import json

import pytest

from krizky_photos.plugin import PhotosPlugin


def test_inject_head_returns_none_without_focal_points():
    plugin = PhotosPlugin()
    assert plugin.inject_head(page_cfg={}, config={}) is None


def test_inject_head_emits_focal_points_when_loaded():
    plugin = PhotosPlugin()
    plugin._focal_points = {"007": "50% 46%", "008": "30% 20%"}
    html = plugin.inject_head(page_cfg={}, config={})
    assert html is not None
    assert html.startswith("<script>window.krizkyPhotos=")
    assert html.endswith("</script>")
    # Extract JSON payload and verify structure.
    payload = html[len("<script>window.krizkyPhotos="):-len(";</script>")]
    data = json.loads(payload)
    assert data == {"focalPoints": {"007": "50% 46%", "008": "30% 20%"}}


def test_prepare_jinja2_environment_no_photos_section_clears_state(tmp_path):
    """Bez sources.photos plugin nedělá nic; state se resetuje."""
    plugin = PhotosPlugin()
    plugin._focal_points = {"stale": "50% 50%"}

    class _Env:
        globals: dict = {}

    env = _Env()
    plugin.prepare_jinja2_environment(env, {"sources": {}}, tmp_path)
    assert plugin._focal_points == {}
    assert env.globals["photo_contexts"] == {}


def test_prepare_jinja2_environment_loads_focal_points(tmp_path):
    """S nakonfigurovanou focal_points cestou se dict načte a photos() se registruje."""
    fp_dir = tmp_path / "data"
    fp_dir.mkdir()
    (fp_dir / "fp.json").write_text(json.dumps({"007": "50% 46%"}), encoding="utf-8")

    config = {
        "sources": {
            "output": "sources",
            "photos": {
                "base_url": "https://cdn.example.com",
                "focal_points": "data/fp.json",
                "formats": [{"format": "jpg", "mime": "image/jpeg"}],
                "sizes": [{"name": "thumb", "max_width": 330}],
            },
        }
    }

    class _Env:
        globals: dict = {}

    env = _Env()
    plugin = PhotosPlugin()
    plugin.prepare_jinja2_environment(env, config, tmp_path)

    assert plugin._focal_points == {"007": "50% 46%"}
    assert "photos" in env.globals
    # inject_head now produces the script.
    html = plugin.inject_head(page_cfg={}, config=config)
    assert '"focalPoints"' in html
    assert '"007"' in html


def test_prepare_jinja2_environment_missing_explicit_focal_points_raises(tmp_path):
    """Explicitní cesta k chybějícímu souboru → ClickException."""
    import click

    config = {
        "sources": {
            "output": "sources",
            "photos": {
                "focal_points": "data/does_not_exist.json",
                "formats": [],
                "sizes": [],
            },
        }
    }

    class _Env:
        globals: dict = {}

    plugin = PhotosPlugin()
    with pytest.raises(click.ClickException, match="focal_points file not found"):
        plugin.prepare_jinja2_environment(_Env(), config, tmp_path)
