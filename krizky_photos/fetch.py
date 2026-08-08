"""Google Drive photo metadata fetching for krizky-photos."""

from __future__ import annotations

import json
import re
from pathlib import Path


class FetchError(Exception):
    """Raised when fetching Google Drive metadata fails."""


def _parse_row_number(filename: str) -> int | None:
    """Return the row number from a photo filename, or None if not a photo file."""
    stem = Path(filename).stem
    m = re.match(r"^(\d+)(-\d+)?$", stem, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _resolve_gdrive_credentials(account_key: str, config_dir: Path, scopes: list[str]):
    """Return Google Drive credentials from a JSON key string or a file path.

    Raises:
        ValueError: If account_key looks like JSON but fails to parse.
    """
    from google.oauth2.service_account import Credentials

    if account_key.strip().startswith("{"):
        try:
            key_data = json.loads(account_key)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"account_key looks like JSON but failed to parse: {exc}\n"
                "Tip: store the JSON in a file and set account_key to the file path instead."
            ) from exc
        return Credentials.from_service_account_info(key_data, scopes=scopes)
    else:
        key_path = Path(account_key)
        if not key_path.is_absolute():
            key_path = (config_dir / account_key).resolve()
        return Credentials.from_service_account_file(str(key_path), scopes=scopes)


def fetch_gdrive_metadata(config: dict, config_dir: Path) -> list[dict]:
    """Fetch the list of photo files from a Google Drive folder.

    Requires: google-api-python-client, google-auth (installed with krizky-photos)

    Reads ``sources.photos.source`` from *config*, lists all files in the
    configured Drive folder, and saves the result to
    ``<sources.output>/photos/gdrive_metadata.json``.

    Args:
        config: Parsed krizky configuration dict.
        config_dir: Directory of the config file.

    Returns:
        List of photo metadata dicts with keys: title, last_modified,
        file_id, row_number.

    Raises:
        FetchError: If Google Drive access fails or optional deps are missing.
    """
    try:
        from googleapiclient.discovery import build as _build
    except ImportError:
        raise FetchError(
            "google-api-python-client and google-auth are required. "
            "Install with: pip install krizky-photos"
        )

    photos_cfg = config.get("sources", {}).get("photos")
    if not photos_cfg:
        raise FetchError("No 'sources.photos' section found in config")

    source_cfg = photos_cfg["source"]
    folder_id: str = source_cfg["folder_id"]
    account_key: str = source_cfg["account_key"]
    scopes = ["https://www.googleapis.com/auth/drive.readonly"]

    try:
        creds = _resolve_gdrive_credentials(account_key, config_dir, scopes)
    except ValueError as exc:
        raise FetchError(str(exc)) from exc

    service = _build("drive", "v3", credentials=creds)

    results: list[dict] = []
    page_token = None
    while True:
        response = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, modifiedTime)",
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=1000,
        ).execute()

        for f in response.get("files", []):
            row_number = _parse_row_number(f["name"])
            if row_number is None:
                continue
            results.append({
                "title": f["name"],
                "last_modified": f["modifiedTime"],
                "file_id": f["id"],
                "row_number": row_number,
            })

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    sources_output = (config_dir / config["sources"]["output"]).resolve()
    out_path = sources_output / "photos" / "gdrive_metadata.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    return results
