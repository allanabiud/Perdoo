# Perdoo (Enhanced Fork)

[![GitHub Repo](https://img.shields.io/badge/GitHub-allanabiud%2FPerdoo-blue?logo=github&style=flat-square)](https://github.com/allanabiud/Perdoo)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg?logo=python&style=flat-square)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)

> **Notice:** This repository is an enhanced fork of the original [Buried-In-Code/Perdoo](https://github.com/Buried-In-Code/Perdoo) with native WebP batch conversion, on-demand format forcing, interactive format prompts, archive page counting, and `{format-short}` naming support.

Perdoo organizes digital comic collections using metadata stored directly within comic archives. It standardizes archives into consistent CBZ files, removes OS clutter, retrieves rich metadata from ComicVine and Metron, and sorts books into a clean publisher/series directory structure.

---

## Fork Features & Enhancements

- 🚀 **Native WebP Conversion (`perdoo webp`)**:
  - High-performance parallel image compression using `cwebp` (with automatic Pillow fallback).
  - Instant 7z pre-inspection: skips archives that are already 100% WebP CBZ in milliseconds without extracting.
  - Automatically strips OS junk (`.DS_Store`, `__MACOSX`, `Thumbs.db`, `.desktop.ini`).
  - Atomic archive replacement with zip integrity verification.
- 🏷️ **On-Demand Format Forcing (`-F` / `--format`)**:
  - Force publication formats on the fly (`TPB`, `HC`, `OB`, `One-Shot`, `GN`, `Annual`) across `sync`, `rename`, and `pipeline`.
  - When metadata lacks format information (such as ComicVine), Perdoo interactively prompts you to choose the format.
  - Automatically writes the resolved format to both `ComicInfo.xml` and `MetronInfo.xml`.
- 📁 **`{format-short}` Naming Key**:
  - Use `{format-short}` in folder and file naming patterns (e.g. `[TPB]`, `[HC]`, `[OB]`, `[One-Shot]`, `[GN]`).
- 📄 **Archive Page Counting**:
  - Automatically counts archive images and populates `page_count` and the `Pages` list in `ComicInfo.xml` and `MetronInfo.xml`.
- 🔄 **Unified Ingestion Pipeline (`perdoo pipeline`)**:
  - Convert to CBZ, compress to WebP, clean junk, fetch metadata, and rename in one command:
    ```console
    perdoo pipeline ~/Downloads/Comics/ -F TPB --webp
    ```
- ⚡ **Smart Sync Feedback & Forcing (`-f` / `--force`)**:
  - Helpful console warnings when archives are skipped due to the recent sync window, and full force re-sync capability.

---

## Installation

### Via Pipx (Recommended)

Install directly from GitHub:

```console
pipx install git+https://github.com/allanabiud/Perdoo.git --force
```

Or install in editable mode for local development:

```console
git clone https://github.com/allanabiud/Perdoo.git ~/DEV/Projects/active/perdoo
pipx install --editable ~/DEV/Projects/active/perdoo --force
```

Verify installation:

```console
perdoo --version
perdoo --help
```

---

## Commands & Usage

### 1. `perdoo pipeline`
The full ingestion workflow: converts non-CBZ archives, cleans junk files, runs WebP compression (optional), fetches metadata, and renames/moves to the target library.

```console
# Full pipeline with WebP conversion and forced format:
perdoo pipeline ~/Downloads/Comics/ -F TPB --webp

# Ingest without WebP:
perdoo pipeline ~/Downloads/Comics/ -F HC

# Force re-sync even if tagged within last 28 days:
perdoo pipeline ~/Downloads/Comics/ -f -F OB
```

### 2. `perdoo webp`
Batch compress comic archive images to WebP format.

```console
# Convert all comic archives in a directory:
perdoo webp ~/Downloads/Comics/

# Dry run: check which archives need conversion without touching files:
perdoo webp -n ~/Media/Comics/

# Custom quality (0-100) and worker thread count:
perdoo webp ~/Downloads/Comics/ -q 85 -j 8

# Force re-conversion:
perdoo webp ~/Downloads/Comics/ -f
```

### 3. `perdoo sync`
Fetch metadata from ComicVine and/or Metron and write to `ComicInfo.xml` and `MetronInfo.xml`.

```console
# Sync metadata for a folder:
perdoo sync ~/Downloads/Comics/

# Force format and bypass recent sync check:
perdoo sync ~/Media/Comics/Marvel/ -F OB -f
```

### 4. `perdoo rename`
Rename and organize archives using metadata according to your configured pattern.

```console
perdoo rename ~/Downloads/Comics/
perdoo rename ~/Media/Comics/ -F TPB
```

### 5. `perdoo archive`
Inspect and manipulate internal archive contents and metadata.

```console
# View ComicInfo.xml metadata:
perdoo archive comic-info "/path/to/comic.cbz"

# View MetronInfo.xml metadata:
perdoo archive metron-info "/path/to/comic.cbz"

# View archive file tree:
perdoo archive tree "/path/to/comic.cbz"
```

---

## File Renaming and Pattern Keys

Metadata is taken from `MetronInfo.xml` when available, with `ComicInfo.xml` used as a fallback.

### Recommended Pattern

```text
{publisher-name}/{series-name}[ ({series-year})][ \[{format-short}\]]/{series-name}[ \[{format-short}\]][ #{number:3}][ ({cover-year})]
```

**Results in**:
```text
DC Comics/
└── Batman (2012) [TPB]/
    ├── Batman [TPB] #001 (2012).cbz
    └── Batman [TPB] #002 (2013).cbz
Marvel/
└── Daredevil by Chip Zdarsky Omnibus (2024) [OB]/
    ├── Daredevil by Chip Zdarsky Omnibus [OB] #001 (2024).cbz
    └── Daredevil by Chip Zdarsky Omnibus [OB] #002 (2024).cbz
```

### Pattern Keys

| Pattern Key          | Description                                                              |
| -------------------- | ------------------------------------------------------------------------ |
| `{format-short}`     | **(Fork Feature)** Short format abbreviation: `TPB`, `HC`, `OB`, `One-Shot`, `GN`, `Annual`. |
| `{format}`           | Full format name of the series (e.g. `Trade Paperback`, `Hardcover`).   |
| `{publisher-name}`   | The full name of the publisher (e.g. `DC Comics`, `Marvel`, `Image`).    |
| `{series-name}`      | The full name of the series.                                             |
| `{series-year}`      | The year the series began.                                               |
| `{number}`           | The issue number. Supports zero-padding (e.g. `{number:3}` -> `001`).    |
| `{cover-year}`       | The publication year from the issue cover date.                          |
| `{cover-date}`       | Issue cover date in `yyyy-mm-dd` format.                                 |
| `{volume}`           | Volume number of the series.                                             |
| `{title}`            | Title of the issue or collection.                                        |
| `{issue-count}`      | Total number of issues in the series.                                    |
| `{series-sort-name}` | Sort-friendly series name (omitting leading "The", "A", etc.).            |

---

## Configuration (`settings.toml`)

Perdoo's configuration is stored at:
```text
~/.config/perdoo/settings.toml
```

### Complete Example Configuration

```toml
[output]
folder = "/home/allanabiud/Media/Comics"
format = "cbz"
image-extensions = [".png", ".jpg", ".jpeg", ".webp", ".jxl"]
remove-extensions = [".nfo", ".sfv", ".db", ".DS_Store"]
webp = false
webp-quality = 80
webp-lossless = false
webp-jobs = 4

[output.comic-info]
create = true
handle-pages = true

[output.metron-info]
create = true

[output.naming]
pattern = "{publisher-name}/{series-name}[ ({series-year})][ \\[{format-short}\\]]/{series-name}[ \\[{format-short}\\]][ #{number:3}][ ({cover-year})]"
seperator = " "

[services]
order = ["Comicvine", "Metron"]

[services.comicvine]
api-key = "<YOUR_COMICVINE_API_KEY>"

[services.metron]
token = "<YOUR_METRON_TOKEN>"

[sync]
days = 28
cover-hash-distance = 10
```

---

## Supported Formats

| Format | Input | Output |
| ------ | :---: | :----: |
| CBZ    |  ✅   |   ✅   |
| CBR    |  ✅   |   ❌ (converts to CBZ) |
| CB7    |  ✅   |   ✅   |
| CBT    |  ✅   |   ✅   |
| PDF    |  ✅   |   ❌   |

---

## License

This project is licensed under the [MIT License](LICENSE). Original project copyright [BuriedInCode](https://github.com/Buried-In-Code/Perdoo).
