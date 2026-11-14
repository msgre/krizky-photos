---
id: "01"
slug: core-helpers
title: Core 0.2, resolve_path pro focal points a přejmenování na PhotosFetchError
status: pending
depends_on: []
files:
  - pyproject.toml
  - uv.lock
  - krizky_photos/focal.py
  - krizky_photos/fetch.py
  - krizky_photos/plugin.py
  - tests/test_focal.py
  - tests/test_fetch.py
  - README.md
attempts: 0
pr: ""
---

## Cíl
Plugin přejde na core `krizky>=0.2`. Převod cesty k focal points pak převezme helper `krizky.plugin_helpers.resolve_path` a výjimka `FetchError` se přejmenuje na `PhotosFetchError`, aby se nepletla s výjimkou core. Pro uživatele se chování nemění, jen jméno výjimky v chybové hlášce. Pokrývá body 1–4 specifikace `.swarm/photos-core-helpers/spec.md`. Změny jsou malé, proto jsou v jednom tiketu.

## Akceptační kritéria
- `pyproject.toml` má v `dependencies` `krizky>=0.2`.
- `uv.lock` obsahuje balíček `krizky` ve verzi 0.2.0 nebo vyšší. Lock se obnoví přes `uv lock --upgrade-package krizky`, ostatní balíčky se zbytečně neaktualizují.
- `resolve_focal_points_path` v `krizky_photos/focal.py` počítá konfigurovanou cestu přes `resolve_path(configured, config_dir)` z `krizky.plugin_helpers` místo `(config_dir / configured).resolve()`. Výchozí cesta (`<sources_output>/photos/focal_points.json`) a příznak `explicit` se nemění. Docstring zmíní, že absolutní cesta se použije tak, jak je.
- `krizky_photos/fetch.py` definuje `PhotosFetchError` a všechna použití (`fetch.py`, `plugin.py`, docstringy, testy) jsou přejmenovaná. Alias `FetchError` nevznikne.
- `git grep -nw FetchError -- ':!.swarm'` nic nenajde.
- `README.md` je v souladu se změnami. Pokud výjimku ani resolvování cesty nezmiňuje, zůstane beze změny.
- `scripts/verify` skončí s exit 0.

## Testy
- Nejdřív (TDD) vznikne `tests/test_fetch.py` s testem, že `fetch_gdrive_metadata({}, tmp_path)` (config bez `sources.photos`) vyhodí `PhotosFetchError` s hláškou o chybějící sekci `sources.photos`. Před přejmenováním test selže na importu.
- Do `tests/test_focal.py` přibude test, že absolutní cesta v `focal_points` (třeba `tmp_path / "elsewhere" / "fp.json"`) vrátí stejné umístění a `explicit is True`, i když `config_dir` je jiný adresář. Stávající `test_resolve_explicit_path_absolute` ponech nebo rozšiř, ale chování ověřuj proti `config_dir`, který s cestou nesouvisí.
- Všechny stávající testy focal points musí projít beze změny očekávaných hodnot.

## Poznámky
- Core `0.2.0` s `krizky/plugin_helpers.py` je sloučený v `main` repa `msgre/krizky` (merge `e32694e`). `uv.lock` aktuálně pinuje commit `09af781…` (verze 0.1.0), takže je nutný `uv lock --upgrade-package krizky`. Ten potřebuje síť, protože `tool.uv.sources` míří na GitHub.
- `resolve_path` vrací `Path | None` a pro prázdný řetězec vrací `None`. Větev s `configured` se volá jen pro pravdivou hodnotu, takže `None` nenastane. Typ ale ošetři čitelně, ne přes `assert`.
- Neměň `_resolve_gdrive_credentials` (vlastní převod `account_key`), je mimo rozsah.
- `from __future__ import annotations` je zakázaný (ruff TID251). Guidelines: `/Users/msgre/projects/muzeum/krizky/docs/guidelines/python.md` a `docs-sync.md`.
- `googleapiclient` je mezi závislostmi, takže v testu se import uvnitř `fetch_gdrive_metadata` provede a výjimka padne až na chybějící `sources.photos`. Síť se nevolá.

## Otázky
