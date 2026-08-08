"""krizky-photos plugin — hookimpl implementations."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import click

from krizky.hooks import hookimpl

_log = logging.getLogger(__name__)


class PhotosPlugin:
    """Adds photo support to krizky.

    Hooks:
    - prepare_jinja2_environment: registers photos() global and photo_contexts
    - register_commands: adds 'fetch photos' and 'build photos' CLI commands
    """

    # ------------------------------------------------------------------
    # prepare_jinja2_environment
    # ------------------------------------------------------------------

    @hookimpl
    def prepare_jinja2_environment(self, env, config, config_dir):
        """Register PhotoContext as photos() global and set photo_contexts."""
        from krizky_photos.context import PhotoContext

        photos_cfg = config.get("sources", {}).get("photos")
        env.globals["photo_contexts"] = photos_cfg.get("contexts", {}) if photos_cfg else {}

        if not photos_cfg:
            return

        sources_output = (config_dir / config["sources"]["output"]).resolve()
        photos_dir = sources_output / "photos"
        cf_meta_path = photos_dir / "cf_metadata.json"
        fp_path = photos_dir / "focal_points.json"

        if not cf_meta_path.exists():
            _log.warning(
                "Photo metadata not found: %s — run 'krizky build photos' first",
                cf_meta_path,
            )
        cf_meta = json.loads(cf_meta_path.read_text(encoding="utf-8")) if cf_meta_path.exists() else {}

        if not fp_path.exists():
            _log.warning(
                "Focal points file not found: %s — focal_point will be None for all photos",
                fp_path,
            )
        focal_points = json.loads(fp_path.read_text(encoding="utf-8")) if fp_path.exists() else {}

        env.globals["photos"] = PhotoContext(
            cf_meta=cf_meta,
            focal_points=focal_points,
            base_url=photos_cfg.get("base_url", ""),
            formats=photos_cfg.get("formats", []),
            sizes=photos_cfg.get("sizes", []),
        )

    # ------------------------------------------------------------------
    # register_commands
    # ------------------------------------------------------------------

    @hookimpl
    def register_commands(self, cli):
        """Add 'fetch photos' and 'build photos' commands to the krizky CLI."""
        from krizky.config import ConfigError, load_config

        @cli.command("fetch-photos")
        @click.pass_context
        def _fetch_photos(ctx: click.Context) -> None:
            """Fetch photo file list from Google Drive and save to sources/photos/gdrive_metadata.json."""
            config_path: str = ctx.obj["config"]
            try:
                config = load_config(config_path)
            except ConfigError as exc:
                click.echo(click.style(f"ERROR: {exc.message}", fg="red"))
                raise SystemExit(1) from None

            from krizky_photos.fetch import FetchError, fetch_gdrive_metadata
            try:
                click.echo("Fetching Google Drive photo metadata...")
                meta = fetch_gdrive_metadata(config, config_dir=Path(config_path).parent)
                click.echo(click.style(f"OK: Fetched metadata for {len(meta)} photos.", fg="green"))
            except FetchError as exc:
                click.echo(click.style(f"ERROR: {exc}", fg="red"))
                raise SystemExit(1) from None

        @cli.command("build-photos")
        @click.option("--force", is_flag=True, default=False, help="Reprocess all photos, ignore change detection.")
        @click.option("--dry-run", is_flag=True, default=False, help="Show what would happen without downloading or uploading.")
        @click.pass_context
        def _build_photos(ctx: click.Context, force: bool, dry_run: bool) -> None:
            """Process changed photos and upload variants to Cloudflare R2."""
            config_path: str = ctx.obj["config"]
            try:
                config = load_config(config_path)
            except ConfigError as exc:
                click.echo(click.style(f"ERROR: {exc.message}", fg="red"))
                raise SystemExit(1) from None

            from krizky_photos.build import PhotoError, build_photos
            try:
                click.echo("Building photos...")
                build_photos(config, config_dir=Path(config_path).parent, force=force, dry_run=dry_run)
                click.echo(click.style("OK: Photos processed successfully.", fg="green"))
            except PhotoError as exc:
                click.echo(click.style(f"ERROR: {exc}", fg="red"))
                raise SystemExit(1) from None

        # Also register under the 'fetch' and 'build' subgroups if they exist.
        # krizky CLI has 'fetch' and 'build' groups — attach commands there too.
        fetch_group = cli.commands.get("fetch")
        build_group = cli.commands.get("build")

        if fetch_group is not None:
            @fetch_group.command("photos")
            @click.pass_context
            def _fetch_photos_sub(ctx: click.Context) -> None:
                """Fetch photo file list from Google Drive."""
                ctx.invoke(_fetch_photos)

        if build_group is not None:
            @build_group.command("photos")
            @click.option("--force", is_flag=True, default=False)
            @click.option("--dry-run", is_flag=True, default=False)
            @click.pass_context
            def _build_photos_sub(ctx: click.Context, force: bool, dry_run: bool) -> None:
                """Process changed photos and upload to Cloudflare R2."""
                ctx.invoke(_build_photos, force=force, dry_run=dry_run)


plugin = PhotosPlugin()
