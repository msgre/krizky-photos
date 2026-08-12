"""Focal points loading and normalization.

The focal points file maps photo base names to CSS ``object-position`` values,
e.g. ``{"007": "50% 46%"}``. Keys must be base names without extension; legacy
files with keys like ``"005.jpg"`` are still accepted with a warning.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

_log = logging.getLogger(__name__)

_DEFAULT_RELATIVE_PATH = Path("photos") / "focal_points.json"


class FocalPointsError(Exception):
    """Raised when an explicitly configured focal_points file is missing or invalid."""


def resolve_focal_points_path(
    photos_cfg: dict,
    config_dir: Path,
    sources_output: Path,
) -> tuple[Path, bool]:
    """Return ``(path, explicit)`` for the focal_points JSON file.

    Priority:
      1. ``sources.photos.focal_points`` in the config — relative to ``config_dir``.
      2. Default ``<sources_output>/photos/focal_points.json``.

    ``explicit`` is True when the path came from the config (user opt-in), which
    changes the missing-file behavior in the caller (error vs. warning).
    """
    configured = photos_cfg.get("focal_points")
    if configured:
        path = (config_dir / configured).resolve()
        return path, True
    return sources_output / _DEFAULT_RELATIVE_PATH, False


def load_focal_points(
    photos_cfg: dict,
    config_dir: Path,
    sources_output: Path,
) -> dict:
    """Load and normalize the focal_points dict.

    Reads the file resolved by :func:`resolve_focal_points_path`. Keys with a
    file extension (legacy format) are normalized to the base name and a
    warning is emitted. Duplicate keys after normalization emit a warning
    (last one wins).

    Raises:
        FocalPointsError: If the file was explicitly configured but is missing
            or contains invalid JSON.
    """
    path, explicit = resolve_focal_points_path(photos_cfg, config_dir, sources_output)

    if not path.exists():
        if explicit:
            raise FocalPointsError(
                f"focal_points file not found: {path} "
                "(configured via sources.photos.focal_points)"
            )
        _log.warning(
            "Focal points file not found: %s — focal_point will be None for all photos",
            path,
        )
        return {}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        if explicit:
            raise FocalPointsError(f"Invalid JSON in {path}: {exc}") from exc
        _log.warning("Invalid JSON in %s: %s — using empty focal_points", path, exc)
        return {}

    if not isinstance(raw, dict):
        if explicit:
            raise FocalPointsError(
                f"focal_points file must be a JSON object, got {type(raw).__name__}: {path}"
            )
        _log.warning("focal_points file %s must be a JSON object — ignoring", path)
        return {}

    return _normalize(raw, path)


def _normalize(raw: dict, path: Path) -> dict:
    """Strip file extensions from keys, warn on legacy keys and duplicates."""
    normalized: dict = {}
    legacy_keys: list[str] = []
    duplicates: list[str] = []

    for key, value in raw.items():
        base = Path(key).stem
        if base != key:
            legacy_keys.append(key)
        if base in normalized and normalized[base] != value:
            duplicates.append(base)
        normalized[base] = value

    if legacy_keys:
        sample = ", ".join(legacy_keys[:5])
        more = f" (and {len(legacy_keys) - 5} more)" if len(legacy_keys) > 5 else ""
        _log.warning(
            "Focal points keys with file extensions (legacy format) in %s: %s%s — "
            "rename to base name without extension (e.g. '007' instead of '007.jpg')",
            path, sample, more,
        )

    if duplicates:
        sample = ", ".join(duplicates[:5])
        more = f" (and {len(duplicates) - 5} more)" if len(duplicates) > 5 else ""
        _log.warning(
            "Duplicate focal points keys after normalization in %s: %s%s — last value wins",
            path, sample, more,
        )

    return normalized
