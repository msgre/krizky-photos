"""Photo context for Jinja2 templates.

Reads CF metadata + focal points JSON files (committed in repo) and exposes
a callable ``PhotoContext`` that templates use as ``photos(row_number)``.

No external dependencies — works purely from the committed JSON metadata.
"""

from __future__ import annotations

from pathlib import Path


class PhotoContext:
    """Callable that returns photo data for a given row number.

    Exposed in Jinja2 templates as ``photos``:

        {% set imgs = photos(record.row_number) %}
        {% if imgs.has_photos %}
          {% from "_picture.html" import picture %}
          {{ picture(imgs.primary, sizes="330px", alt=record.nazev, size="thumb") }}
        {% endif %}
    """

    def __init__(
        self,
        cf_meta: dict,
        focal_points: dict,
        base_url: str,
        formats: list[dict],
        sizes: list[dict],
    ) -> None:
        self._cf_meta = cf_meta
        # Normalize focal_points keys: strip file extension if present ("047.jpg" → "047").
        self._focal_points = {Path(k).stem: v for k, v in focal_points.items()}
        self._base_url = base_url.rstrip("/")
        # Only non-JPEG formats go into <source> elements; JPEG is the <img> fallback.
        self._source_formats = [f for f in formats if f["format"] != "jpg"]
        self._sizes = sizes

    def __call__(self, row_number) -> dict:
        """Return photo data dict for *row_number*.

        Structure::

            {
                "primary":    photo_dict | None,
                "additional": [photo_dict, ...],   # 007-1, 007-2, …
                "all":        [primary, *additional],
                "count":      int,
                "has_photos": bool,
            }
        """
        primary_base = f"{int(row_number):03d}"
        primary = self._build_photo_dict(primary_base)

        additional: list[dict] = []
        idx = 1
        while True:
            base = f"{row_number:03d}-{idx}"
            if base not in self._cf_meta:
                break
            photo = self._build_photo_dict(base)
            if photo:
                additional.append(photo)
            idx += 1

        all_photos = ([primary] if primary else []) + additional
        return {
            "primary": primary,
            "additional": additional,
            "all": all_photos,
            "count": len(all_photos),
            "has_photos": bool(all_photos),
        }

    def _build_photo_dict(self, base_name: str) -> dict | None:
        """Build a photo data dict for *base_name* (e.g. ``"007"`` or ``"007-1"``)."""
        entry = self._cf_meta.get(base_name)
        if not entry:
            return None

        # Skip internal metadata keys (prefixed with _).
        variant_dims = {k: v for k, v in entry.items() if not k.startswith("_")}
        if not variant_dims:
            return None

        # Build per-size variant dict with pre-computed URLs.
        variants: dict[str, dict] = {}
        for size_cfg in self._sizes:
            size_name = size_cfg["name"]
            dims = variant_dims.get(size_name)
            if dims:
                variants[size_name] = {
                    "url": f"{self._base_url}/{base_name}_{size_name}.jpg",
                    "w": dims["w"],
                    "h": dims["h"],
                }

        if not variants:
            return None

        # Largest available variant (last size_cfg that has metadata).
        largest_name = next(
            (s["name"] for s in reversed(self._sizes) if s["name"] in variants),
            next(iter(variants)),
        )
        largest = variants[largest_name]

        # Build srcset strings per format.
        sources: list[dict] = []
        jpg_parts: list[str] = []

        all_formats = self._source_formats + [{"format": "jpg", "mime": "image/jpeg"}]
        for fmt_cfg in all_formats:
            fmt = fmt_cfg["format"]
            parts: list[str] = []
            for size_cfg in self._sizes:
                size_name = size_cfg["name"]
                dims = variant_dims.get(size_name)
                if dims:
                    url = f"{self._base_url}/{base_name}_{size_name}.{fmt}"
                    parts.append(f"{url} {dims['w']}w")

            if fmt == "jpg":
                jpg_parts = parts
            elif parts:
                sources.append({"mime": fmt_cfg["mime"], "srcset": ", ".join(parts)})

        return {
            "base_name": base_name,
            "sources": sources,                         # list of {mime, srcset} for <source>
            "srcset": ", ".join(jpg_parts),             # JPEG srcset for <img>
            "src": f"{self._base_url}/{base_name}_{largest_name}.jpg",
            "variants": variants,                       # {size_name: {url, w, h}}
            "width": largest["w"],
            "height": largest["h"],
            "focal_point": self._focal_points.get(base_name),
        }
