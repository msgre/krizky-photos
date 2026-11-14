# Specifikace: photos-core-helpers

- **Repo:** `krizky-photos`
- **Zdroj:** konsolidace do core, rozhodnuto 2026-11-13. Core v běhu `plugin-helpers` (`/Users/msgre/projects/muzeum/krizky/.swarm/plugin-helpers/spec.md`) přidal modul `krizky.plugin_helpers` s funkcí `resolve_path`. Core má verzi 0.2.0. Kolize jmen `FetchError` pochází z revize `krizky/reports/2026-08-17-2013/` (`summary.md` bod 7) a ze spec běhu `hooks-errors` (vyřešit v photos, ne v core).
- **Předpoklad:** běh `plugin-helpers` je sloučený v `main` repa `msgre/krizky`.

## Cíl

Převod cesty k focal points převezme helper z core a výjimka pluginu přestane mít stejné jméno jako výjimka core. Chování pro uživatele se nemění, kromě jména výjimky v chybové hlášce.

## 1. Závislost na core 0.2

- `pyproject.toml`: `krizky>=0.2`.
- `uv lock --upgrade-package krizky`, aby `uv.lock` obsahoval core s `plugin_helpers`.

**Akceptace:** `uv.lock` obsahuje `krizky` ve verzi 0.2.0 nebo vyšší.

## 2. `resolve_path` pro focal points

- `resolve_focal_points_path` (`krizky_photos/focal.py`) převede `sources.photos.focal_points` přes `resolve_path(configured, config_dir)` místo `(config_dir / configured).resolve()`. Výchozí cesta a příznak `explicit` se nemění.

**Akceptace:** stávající testy focal points projdou. Test: absolutní cesta v `focal_points` se použije beze změny umístění.

## 3. Přejmenování `FetchError` na `PhotosFetchError`

- `krizky_photos/fetch.py`: třída `PhotosFetchError` místo `FetchError`, všechna použití (`plugin.py`, testy) přejmenovat.
- Zpětně kompatibilní alias se nezavádí, výjimku mimo plugin nikdo nepoužívá.

**Akceptace:** `git grep -nw FetchError -- ':!.swarm'` v repu nic nenajde. Testy chyb fetche očekávají `PhotosFetchError`.

## 4. Dokumentace (docs-sync)

- `README.md`: přejmenovat výjimku, pokud ji zmiňuje.

**Akceptace:** `scripts/verify` projde.

## Mimo rozsah

- Fáze 5 a 6 z `krizky/PLAN.md` (zpracování fotek, kompletní build).
