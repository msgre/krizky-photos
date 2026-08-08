"""Photo processing: resize, convert, upload to Cloudflare R2.

Requires optional dependencies: pip install krizky[photos]
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import click

_log = logging.getLogger(__name__)


class PhotoError(Exception):
    """Raised when photo processing fails."""


# ---------------------------------------------------------------------------
# Pure helpers (no external deps)
# ---------------------------------------------------------------------------

def resolve_quality(size_cfg: dict, fmt_name: str, fmt_cfg: dict) -> int:
    """Resolve JPEG/WebP/AVIF quality for one size × format combination.

    Priority: sizes[n].quality.{fmt}  →  formats[n].quality  →  100
    """
    size_quality = size_cfg.get("quality")
    if isinstance(size_quality, dict) and fmt_name in size_quality:
        return int(size_quality[fmt_name])
    if "quality" in fmt_cfg:
        return int(fmt_cfg["quality"])
    return 100


def _normalize_base_name(title: str, row_number: int) -> str:
    """Return canonical base name ('007', '007-2') from a Drive filename."""
    stem = Path(title).stem
    m = re.match(r"^(\d+)(-\d+)?$", stem, re.IGNORECASE)
    if m:
        rn = int(m.group(1))
        suffix = m.group(2) or ""
        return f"{rn:03d}{suffix}"
    return f"{row_number:03d}"


def compare_photos(
    gdrive_meta: list[dict],
    cf_meta: dict,
    photos_cfg: dict,
) -> dict[str, list]:
    """Compare GDrive metadata with CF metadata and return what needs processing.

    Returns::

        {
            "to_process": [gdrive_entry, ...],   # new / changed / missing variants
            "to_delete":  [base_name, ...],      # in CF but no longer on Drive
        }
    """
    expected_sizes = {s["name"] for s in photos_cfg.get("sizes", [])}

    # Index GDrive entries by base_name; last entry wins on collision.
    gdrive_index: dict[str, dict] = {}
    for entry in gdrive_meta:
        base = _normalize_base_name(entry["title"], entry["row_number"])
        gdrive_index[base] = entry

    to_process: list[dict] = []
    for base, entry in gdrive_index.items():
        cf_entry = cf_meta.get(base)
        if cf_entry is None:
            # New photo — not in CF yet.
            to_process.append(entry)
            continue
        cf_last_modified = cf_entry.get("_last_modified")
        if cf_last_modified is not None:
            # We know when this photo was last processed; compare timestamps.
            if entry.get("last_modified") != cf_last_modified:
                to_process.append(entry)
                continue
        # Check that all expected size variants are present.
        cf_sizes = {k for k in cf_entry if not k.startswith("_")}
        if not expected_sizes.issubset(cf_sizes):
            to_process.append(entry)

    to_delete: list[str] = [b for b in cf_meta if b not in gdrive_index]

    return {"to_process": to_process, "to_delete": to_delete}


# ---------------------------------------------------------------------------
# External-dependency helpers (lazy imports)
# ---------------------------------------------------------------------------

def _require_pillow():
    try:
        from PIL import Image, ImageOps  # noqa: F401
    except ImportError:
        raise PhotoError(
            "Pillow is required for photo processing. "
            "Install with: pip install krizky[photos]"
        )


def _require_google():
    try:
        import googleapiclient  # noqa: F401
        import google.oauth2  # noqa: F401
    except ImportError:
        raise PhotoError(
            "google-api-python-client and google-auth are required. "
            "Install with: pip install krizky[photos]"
        )


def _require_boto3():
    try:
        import boto3  # noqa: F401
    except ImportError:
        raise PhotoError(
            "boto3 is required for Cloudflare R2 upload. "
            "Install with: pip install krizky[photos]"
        )


def _get_drive_service(photos_cfg: dict, config_dir: Path):
    _require_google()
    from googleapiclient.discovery import build
    from krizky_photos.fetch import _resolve_gdrive_credentials

    account_key: str = photos_cfg["source"]["account_key"]
    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    try:
        creds = _resolve_gdrive_credentials(account_key, config_dir, scopes)
    except ValueError as exc:
        raise PhotoError(str(exc)) from exc
    return build("drive", "v3", credentials=creds)


def _get_r2_client(photos_cfg: dict):
    _require_boto3()
    import boto3

    dest = photos_cfg["destination"]
    jurisdiction = dest.get("jurisdiction", "")
    jurisdiction_prefix = f"{jurisdiction}." if jurisdiction else ""
    endpoint = f"https://{dest['account_id']}.{jurisdiction_prefix}r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=dest["access_key_id"],
        aws_secret_access_key=dest["secret_access_key"],
        region_name="auto",
    )


def _download_drive_file(service, file_id: str, dest: Path) -> None:
    import io
    from googleapiclient.http import MediaIoBaseDownload

    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    fh = io.FileIO(str(dest), "wb")
    try:
        downloader = MediaIoBaseDownload(fh, request, chunksize=2 * 1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    finally:
        fh.close()


def _run_optimizer(optimizer: str, path: Path, quality: int) -> None:
    if optimizer == "cjpeg":
        tmp = path.with_suffix(".tmp.jpg")
        subprocess.run(
            f'djpeg "{path}" | cjpeg -quality {quality} -progressive -optimize -outfile "{tmp}"',
            shell=True, check=True,
        )
        tmp.replace(path)
    elif optimizer == "jpegoptim":
        subprocess.run(["jpegoptim", f"--max={quality}", str(path)], check=True)
    else:
        _log.warning("Unknown optimizer %r — skipping", optimizer)


def _save_image(img, out_path: Path, fmt_name: str, quality: int, optimizer: str | None) -> None:
    if fmt_name == "jpg":
        img.save(out_path, "JPEG", quality=quality, progressive=True, optimize=False)
        if optimizer and shutil.which(optimizer):
            _run_optimizer(optimizer, out_path, quality)
    elif fmt_name == "webp":
        img.save(out_path, "WEBP", quality=quality, method=6)
    elif fmt_name == "avif":
        img.save(out_path, "AVIF", quality=quality, speed=6)
    else:
        img.save(out_path, quality=quality)


def _upload_to_r2(cf_client, bucket: str, local_path: Path, content_type: str) -> None:
    cf_client.upload_file(
        str(local_path),
        bucket,
        local_path.name,
        ExtraArgs={"ContentType": content_type},
    )


def _delete_from_r2(cf_client, bucket: str, base_name: str, photos_cfg: dict) -> None:
    keys = [
        {"Key": f"{base_name}_{s['name']}.{f['format']}"}
        for s in photos_cfg.get("sizes", [])
        for f in photos_cfg.get("formats", [])
    ]
    if keys:
        cf_client.delete_objects(Bucket=bucket, Delete={"Objects": keys})


def _check_optimizers(photos_cfg: dict) -> None:
    for fmt_cfg in photos_cfg.get("formats", []):
        optimizer = fmt_cfg.get("optimizer")
        if optimizer and not shutil.which(optimizer):
            _log.warning(
                "Optimizer %r configured for format %r but not found in PATH — skipping",
                optimizer, fmt_cfg["format"],
            )


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def _process_photo(
    entry: dict,
    service,
    photos_cfg: dict,
    cf_client,
    work_dir: Path,
    dry_run: bool,
    index: int = 0,
    total: int = 0,
) -> dict:
    """Download, resize, convert, and upload one photo.

    Returns a cf_meta entry dict with ``_last_modified`` and per-size dims.
    """
    _require_pillow()
    from PIL import Image, ImageOps

    base_name = _normalize_base_name(entry["title"], entry["row_number"])
    formats: list[dict] = photos_cfg.get("formats", [])
    sizes: list[dict] = photos_cfg.get("sizes", [])
    bucket: str = photos_cfg["destination"]["bucket"]

    width = len(str(total))
    counter = f"[{index:{width}}/{total}]" if total else ""
    prefix = f"  {counter} {base_name}"

    if dry_run:
        click.echo(f"{prefix}  (dry-run)")
        return {}

    click.echo(f"{prefix}  ↓ stahování...", nl=False)
    suffix = Path(entry["title"]).suffix or ".jpg"
    temp_file = work_dir / f"{base_name}_orig{suffix}"
    _download_drive_file(service, entry["file_id"], temp_file)
    click.echo("\r" + " " * (len(prefix) + 20) + "\r", nl=False)  # přepsat řádek

    try:
        img = Image.open(temp_file)
        img = ImageOps.exif_transpose(img)
        img.load()
        if img.mode != "RGB":
            img = img.convert("RGB")

        dims: dict = {"_last_modified": entry["last_modified"]}
        fmt_names = [f["format"] for f in formats]

        for size_cfg in sizes:
            size_name = size_cfg["name"]
            max_width = size_cfg["max_width"]

            src_w, src_h = img.size
            if src_w > max_width:
                new_h = max(1, round(src_h * max_width / src_w))
                resized = img.resize((max_width, new_h), Image.Resampling.LANCZOS)
            else:
                resized = img.copy()

            actual_w, actual_h = resized.size
            dims[size_name] = {"w": actual_w, "h": actual_h}

            click.echo(f"{prefix}  {size_name:8} {actual_w}×{actual_h}", nl=False)

            for fmt_cfg in formats:
                fmt_name = fmt_cfg["format"]
                quality = resolve_quality(size_cfg, fmt_name, fmt_cfg)
                out_path = work_dir / f"{base_name}_{size_name}.{fmt_name}"
                _save_image(resized, out_path, fmt_name, quality, fmt_cfg.get("optimizer"))
                if cf_client:
                    _upload_to_r2(cf_client, bucket, out_path, fmt_cfg["mime"])
                    out_path.unlink(missing_ok=True)
                click.echo(f"  {fmt_name}", nl=False)

            click.echo()  # nový řádek po každé velikosti

        return dims

    finally:
        temp_file.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def build_photos(
    config: dict,
    config_dir: Path,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    """Process and upload changed photos to Cloudflare R2.

    Reads ``sources/photos/gdrive_metadata.json`` and ``cf_metadata.json``,
    compares them, processes changed photos, and updates ``cf_metadata.json``.

    Args:
        config: Parsed krizky configuration dict.
        config_dir: Directory of the config file.
        force: Reprocess all photos regardless of change detection.
        dry_run: Log what would happen without downloading, processing, or uploading.

    Raises:
        PhotoError: If required optional dependencies are missing or processing fails.
    """
    photos_cfg = config.get("sources", {}).get("photos")
    if not photos_cfg:
        raise PhotoError("No 'sources.photos' section found in config")

    sources_output = (config_dir / config["sources"]["output"]).resolve()
    photos_dir = sources_output / "photos"
    gdrive_meta_path = photos_dir / "gdrive_metadata.json"
    cf_meta_path = photos_dir / "cf_metadata.json"

    gdrive_meta: list[dict] = (
        json.loads(gdrive_meta_path.read_text(encoding="utf-8"))
        if gdrive_meta_path.exists() else []
    )
    cf_meta: dict = (
        json.loads(cf_meta_path.read_text(encoding="utf-8"))
        if cf_meta_path.exists() else {}
    )

    if force:
        changes: dict = {"to_process": gdrive_meta, "to_delete": []}
    else:
        changes = compare_photos(gdrive_meta, cf_meta, photos_cfg)

    n_process = len(changes["to_process"])
    n_delete = len(changes["to_delete"])

    if not n_process and not n_delete:
        click.echo("Žádné změny fotek.")
        return

    click.echo(f"Fotky: {n_process} ke zpracování, {n_delete} ke smazání")

    _check_optimizers(photos_cfg)

    service = _get_drive_service(photos_cfg, config_dir)
    cf_client = _get_r2_client(photos_cfg) if not dry_run else None

    with tempfile.TemporaryDirectory(prefix="krizky_photos_") as tmp:
        work_dir = Path(tmp)

        for idx, entry in enumerate(changes["to_process"], 1):
            base = _normalize_base_name(entry["title"], entry["row_number"])
            try:
                result = _process_photo(
                    entry, service, photos_cfg, cf_client, work_dir, dry_run,
                    index=idx, total=n_process,
                )
                if not dry_run and result:
                    cf_meta[base] = result
            except Exception as exc:
                click.echo(click.style(f"  CHYBA {base}: {exc}", fg="red"))
                _log.error("Failed to process %s: %s", base, exc)

        for base in changes["to_delete"]:
            click.echo(f"  mazání {base}...")
            if not dry_run and cf_client:
                try:
                    _delete_from_r2(cf_client, photos_cfg["destination"]["bucket"], base, photos_cfg)
                    cf_meta.pop(base, None)
                except Exception as exc:
                    click.echo(click.style(f"  CHYBA mazání {base}: {exc}", fg="red"))
                    _log.error("Failed to delete %s: %s", base, exc)

    if not dry_run:
        photos_dir.mkdir(parents=True, exist_ok=True)
        cf_meta_path.write_text(
            json.dumps(cf_meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        click.echo(click.style(f"Hotovo: {n_process} zpracováno, {n_delete} smazáno.", fg="green"))
