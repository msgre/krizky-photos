# krizky-photos

Plugin pro zpracování fotek do [krizky](https://github.com/your-org/krizky) generátoru statických webů.

Přidává do krizky kompletní foto pipeline: stahuje metadata fotek z Google Drive, stahuje originály, mění jejich velikost a převádí je do více formátů (JPEG, WebP, AVIF) a rozměrů, a nahrává varianty na Cloudflare R2. V Jinja2 šablonách zpřístupní funkci `photos()` pro vykreslování responzivních `<picture>` elementů.

## Instalace

```bash
pip install krizky-photos
```

## Konfigurace

Přidej sekci `sources.photos` do svého `config.yaml`:

```yaml
sources:
  photos:
    base_url: https://photos.example.com
    source:
      type: gdrive
      folder_id: YOUR_GDRIVE_FOLDER_ID
      account_key: $GDRIVE_ACCOUNT_KEY   # cesta k JSON souboru service accountu
    destination:
      type: cloudflare
      bucket: YOUR_BUCKET_NAME
      account_id: $CF_ACCOUNT_ID
      access_key_id: $CF_ACCESS_KEY_ID
      secret_access_key: $CF_SECRET_ACCESS_KEY
    formats:
      - format: avif
        mime: image/avif
        quality: 60
      - format: webp
        mime: image/webp
        quality: 80
      - format: jpg
        mime: image/jpeg
        quality: 80
    sizes:
      - name: micro
        max_width: 150
      - name: thumb
        max_width: 330
      - name: medium
        max_width: 960
      - name: big
        max_width: 1600
    contexts:
      card:
        src: thumb
        sizes: "(max-width:520px) calc(100vw - 48px), calc(25vw - 30px)"
      detail:
        src: medium
        sizes: "(max-width:860px) calc(100vw - 48px), 650px"
        lazy: false
```

Citlivé hodnoty ulož do `.env`:

```
GDRIVE_ACCOUNT_KEY=/cesta/k/service-account.json
CF_ACCOUNT_ID=tvoje-account-id
CF_ACCESS_KEY_ID=tvuj-klic
CF_SECRET_ACCESS_KEY=tvoje-tajemstvi
```

## CLI příkazy

Po instalaci krizky-photos se v krizky CLI objeví dva nové příkazy:

```bash
# Stáhne seznam fotek z Google Drive → sources/photos/gdrive_metadata.json
krizky fetch photos

# Zpracuje změněné fotky a nahraje je na Cloudflare R2
krizky build photos [--force] [--dry-run]
```

`--force` zpracuje všechny fotky bez ohledu na detekci změn. `--dry-run` zobrazí co by se stalo, aniž by cokoliv stahovalo nebo nahrávalo.

## Konvence pojmenování fotek

Fotky na Google Drive musí být pojmenovány podle čísla řádku: `007.jpg` (hlavní fotka pro řádek 7), `007-1.jpg`, `007-2.jpg` (další fotky ke stejnému řádku). Soubory, které tomuto vzoru neodpovídají, plugin ignoruje.

## Šablony

Po instalaci pluginu je ve všech Jinja2 šablonách dostupná funkce `photos()`:

```jinja2
{% set imgs = photos(record.row_number) %}

{% if imgs.has_photos %}
  {% from "_picture.html" import picture %}
  {{ picture(imgs.primary, "card", alt=record.nazev) }}
{% endif %}

{# Galerie #}
{% for photo in imgs.all %}
  {{ picture(photo, "micro", alt=record.nazev) }}
{% endfor %}
```

### Návratová hodnota `photos(row_number)`

```
imgs.has_photos    → bool
imgs.count         → int (celkový počet fotek pro tento řádek)
imgs.primary       → photo dict nebo None  (007)
imgs.additional    → list photo dictů (007-1, 007-2, …)
imgs.all           → [primary] + additional
```

### Struktura photo dictu

```
photo.src          → URL největší JPEG varianty
photo.srcset       → JPEG srcset string pro <img>
photo.sources      → [{mime, srcset}, …] pro <source> elementy (AVIF, WebP)
photo.variants     → {nazev_velikosti: {url, w, h}, …}
photo.width        → int (šířka největší varianty)
photo.height       → int (výška největší varianty)
photo.focal_point  → "50% 46%" nebo None  (CSS hodnota pro object-position)
```

### Vestavěné makro `_picture.html`

Použij pojmenované kontexty definované v `sources.photos.contexts`:

```jinja2
{% from "_picture.html" import picture %}
{{ picture(imgs.primary, "card", alt=record.nazev) }}
{{ picture(imgs.primary, "detail", alt=record.nazev) }}
```

## Ohniska fotek

Ohniska řídí `object-position` u ořezaných obrázků. Soubor je JSON dict `{base_name: "X% Y%"}`:

```json
{
  "007": "50% 30%",
  "012": "70% 50%"
}
```

Klíče jsou základní názvy bez přípony (`"007"`, nikoli `"007.jpg"`). Legacy klíče s příponou plugin akceptuje, ale při načítání vypíše warning — postupně je přejmenuj.

### Cesta k souboru

Default: `<sources.output>/photos/focal_points.json`.

Chceš-li mít ohniska ve verzovaném adresáři projektu (mimo `sources/`, který je typicky v `.gitignore`), zadej vlastní cestu do configu — je relativní k `config.yaml`:

```yaml
sources:
  photos:
    focal_points: ./data/focal_points.json
```

- Pokud je `focal_points` zadaný a soubor **neexistuje** (nebo je nečitelný JSON) → build spadne s chybou.
- Pokud `focal_points` v configu **není** a default soubor chybí → jen warning a všechny fotky budou bez `focal_point`.

### Aplikace v šablonách

- **SSR renderování**: makro `_picture.html` čte `photo.focal_point` a generuje `<img style="object-position:...">` automaticky.
- **JS klonování (krizky-filters)**: plugin injektuje focal_points jako `window.krizkyPhotos.focalPoints` do `<head>`. Kompatibilní JS runtime (např. krizky-filters) tuto mapu použije pro nastavení `style.objectPosition` na dynamicky vytvářených `<img>` elementech.

## Požadavky

- Python 3.12+
- krizky >= 0.1
- Pillow >= 10.0
- boto3 >= 1.28
- google-api-python-client >= 2.0
- google-auth >= 2.0
