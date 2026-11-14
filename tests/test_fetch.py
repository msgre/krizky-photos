"""Tests for krizky_photos.fetch."""

import pytest

from krizky_photos.fetch import PhotosFetchError, fetch_gdrive_metadata


def test_missing_photos_section_raises(tmp_path):
    with pytest.raises(PhotosFetchError, match=r"sources\.photos"):
        fetch_gdrive_metadata({}, tmp_path)
