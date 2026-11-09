# Perdoo

[![GitHub - allanabiud/Perdoo](https://img.shields.io/badge/GitHub-allanabiud%2FPerdoo-blue?logo=github&style=flat-square)](https://github.com/allanabiud/Perdoo)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg?logo=python&style=flat-square)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![prek](https://img.shields.io/badge/prek-enabled-informational?logo=prek&style=flat-square)](https://github.com/j178/prek)
[![Ruff](https://img.shields.io/badge/ruff-enabled-informational?logo=ruff&style=flat-square)](https://github.com/astral-sh/ruff)
[![Ty](https://img.shields.io/badge/ty-enabled-informational?logo=ruff&style=flat-square)](https://github.com/astral-sh/ty)

Perdoo helps organise comic collections using metadata stored within comic archives.

It standardises digital comics into a consistent format and can add or update metadata using supported services.

This repository is an enhanced fork of [Buried-In-Code/Perdoo](https://github.com/Buried-In-Code/Perdoo) adding native WebP conversion, on-demand format forcing, interactive format prompts, archive image page counting, and `{format-short}` naming support.

## Fork Enhancements

- **Native WebP Conversion (`perdoo webp`)**: Parallel image conversion using `cwebp` (with Pillow fallback). Performs fast 7z archive pre-inspection to skip archives already 100% WebP in milliseconds without extracting. Cleans OS junk files (`.DS_Store`, `__MACOSX`, `Thumbs.db`) automatically and replaces files atomically with archive integrity checking.
- **On-Demand Format Forcing (`-F` / `--format`)**: Specify a series format on the fly (`TPB`, `HC`, `OB`, `One-Shot`, `GN`, `Annual`) when running `sync`, `rename`, or `pipeline`.
- **Interactive Format Prompts**: When metadata from services (such as ComicVine) lacks series format details, Perdoo interactively prompts you to choose the format and writes it directly to `ComicInfo.xml` and `MetronInfo.xml`.
- **Format-Aware Naming (`{format-short}`)**: Adds the `{format-short}` pattern key to generate clean folder and file names (e.g. `[TPB]`, `[HC]`, `[OB]`, `[One-Shot]`).
- **Archive Page Counting & Double-Page Detection**: Inspects image headers inside the archive to populate accurate `page_count`, pixel dimensions (`ImageWidth`, `ImageHeight`), exact byte sizes (`ImageSize`), and automatic double-page spread detection (`DoublePage="true"`) in `ComicInfo.xml`.
- **Pipeline WebP Integration**: Adds `-w` / `--webp` / `--no-webp` flags to `perdoo pipeline` to compress and standardize inbound comics in a single pass.
- **Smart Sync Feedback**: Provides clear console status when archives are skipped due to the recent sync interval, and allows bypassing it with `-f` / `--force`.
- **Creator Role Normalization**: Automatically maps ComicVine's lowercase role strings (`penciler`, `cover`, `script`) to the correct ComicInfo fields (`Penciller`, `Cover Artist`, `Writer`), preventing silently dropped creator credits.
- **Date and Count Population**: Fills `Year`, `Month`, `Day`, `Count`, and `Volume` fields in `ComicInfo.xml` from both ComicVine and Metron issue data, using `cover_date` with `store_date` as a fallback.
- **Rich Synopsis Fallback**: When an issue's `summary` field is empty or very short, falls back to the full `description` field with HTML tags stripped to provide a meaningful summary.
- **Two-Pass Subtitle Search**: When a series name with subtitles (e.g. "Batman: Court of Owls") returns no ComicVine results, automatically retries with the base title ("Batman").
- **Smart Filename Format Detection**: Regex-based heuristic detects format keywords (`Omnibus`, `HC`, `TPB`, `Vol.X`, `Deluxe`, `Annual`) from filenames and directory paths, pre-selecting the correct default in interactive prompts.
- **Hybrid Service Format Merging**: When the primary service (e.g. ComicVine) returns no format data, cross-queries the other configured service (e.g. Metron) for series type information and applies it.
- **Robust 7z Extraction Fallback**: When Python bindings for RAR or 7-Zip archives are not installed, falls back to the system `7z` command-line tool to extract and re-pack as CBZ.
- **Custom Metadata Preservation**: During re-sync, preserves user-customized fields that services do not populate: language, age rating, format, scan information, notes (merged with service IDs), and page-level bookmarks and specific page types.
- **Concurrent Archive Processing**: The `convert` and `clean` commands use a thread pool (`-j` / `--jobs`) to process multiple archives in parallel. Defaults to the `output.webp-jobs` setting.
- **ComicVine Rate Limit Retry**: Adds exponential backoff retry logic for ComicVine API calls, automatically detecting HTTP 420/429 rate-limit responses and waiting before retrying.

## Installation

### Pipx

1. Ensure [Pipx](https://pipx.pypa.io/stable/) is installed:

   ```console
   pipx --version
   ```

2. Install this fork:

   ```console
   pipx install git+https://github.com/allanabiud/Perdoo.git --force
   ```

   Or install in editable mode for local development:

   ```console
   git clone https://github.com/allanabiud/Perdoo.git ~/DEV/Projects/active/perdoo
   pipx install --editable ~/DEV/Projects/active/perdoo --force
   ```

## Usage

### Ingest Pipeline

The `pipeline` command runs the full ingestion workflow: converting archives, cleaning unwanted files, converting images to WebP (optional), fetching metadata, and renaming.

```console
# Full pipeline with WebP conversion and forced format:
perdoo pipeline ~/Downloads/Comics/ -F TPB --webp

# Ingest without WebP:
perdoo pipeline ~/Downloads/Comics/ -F HC

# Force re-sync even if tagged within the last 28 days:
perdoo pipeline ~/Downloads/Comics/ -f -F OB
```

### WebP Batch Conversion

Batch compress comic archive images to WebP format.

```console
# Convert all comic archives in a directory:
perdoo webp ~/Downloads/Comics/

# Dry run to inspect which archives need conversion without modifying files:
perdoo webp -n ~/Media/Comics/

# Custom quality (0-100) and worker thread count:
perdoo webp ~/Downloads/Comics/ -q 85 -j 8

# Force re-conversion of archives already containing WebP:
perdoo webp ~/Downloads/Comics/ -f
```

### Metadata Synchronisation

Fetch metadata from ComicVine and/or Metron and write to `ComicInfo.xml` and `MetronInfo.xml`.

```console
# Sync metadata for a folder:
perdoo sync ~/Downloads/Comics/

# Force format and bypass recent sync interval:
perdoo sync ~/Media/Comics/Marvel/ -F OB -f
```

### File Renaming

Rename and organize archives using metadata according to your configured pattern.

```console
perdoo rename ~/Downloads/Comics/
perdoo rename ~/Media/Comics/ -F TPB
```

### Archive Inspection

Inspect and manipulate internal archive contents and metadata.

```console
# View ComicInfo.xml metadata:
perdoo archive comic-info "/path/to/comic.cbz"

# View MetronInfo.xml metadata:
perdoo archive metron-info "/path/to/comic.cbz"

# View archive file tree:
perdoo archive tree "/path/to/comic.cbz"
```

## Supported Formats

| Format | Input | Output | Notes |
| ------ | :---: | :----: | ----- |
| CB7    |  Yes  |  Yes   | Falls back to system `7z` if Python bindings missing |
| CBR    |  Yes  |  No    | Falls back to system `7z` for input conversion |
| CBT    |  Yes  |  Yes   | |
| CBZ    |  Yes  |  Yes   | |
| PDF    |  Yes  |  No    | |

### Metadata Files

Metadata file support is provided by [shortbox](https://codeberg.org/buriedincode/shortbox), which currently supports:

- ComicInfo v2.0 (with field ordering ignored)
- MetronInfo v1.1

## Services

- [Comicvine](https://comicvine.gamespot.com) using the [Simyan](https://github.com/Metron-Project/Simyan) library.
- [Metron](https://metron.cloud) using the [Mokkari](https://github.com/Metron-Project/Mokkari) library.

## File Renaming and Organization

Perdoo uses a pattern-based approach for naming and organizing files.

Metadata is taken from MetronInfo when available, with ComicInfo used as a fallback.

The default pattern is:

```text
{publisher-name}/{series-name}-v{volume}/{format}/{series-name}-v{volume}_#{number:3}
```

A common pattern with folder-level format tags:

```text
{publisher-name}/{series-name}[ ({series-year})][ \[{format-short}\]]/{series-name}[ \[{format-short}\]][ #{number:3}][ ({cover-year})]
```

### Pattern Options

#### Padding

Integer and integer-like fields, such as `{number}`, support optional zero-padding by specifying a length.

For example: `{number:3}` produces `012` from `12`

#### Sanitization

Metadata values are sanitized to remove characters outside:

```text
0-9a-zA-Z&!-
```

Custom characters can still be added directly to patterns.

### Pattern Keys

| Pattern Key          | Description                                                              |
| -------------------- | ------------------------------------------------------------------------ |
| `{cover-date}`       | The issue cover date in `yyyy-mm-dd` format.                             |
| `{cover-day}`        | The day from the issue cover date.                                       |
| `{cover-month}`      | The month from the issue cover date.                                     |
| `{cover-year}`       | The year from the issue cover date.                                      |
| `{format}`           | The full format name of the series (e.g. `Trade Paperback`, `Hardcover`).|
| `{format-short}`     | The short format abbreviation (`TPB`, `HC`, `OB`, `One-Shot`, `GN`, `Annual`). |
| `{id}`               | The primary ID of the issue.                                             |
| `{imprint}`          | The publisher's imprint.                                                 |
| `{isbn}`             | The issue's ISBN.                                                        |
| `{issue-count}`      | The total number of issues in the series.                                |
| `{lang}`             | The issue's language.                                                    |
| `{number}`           | The issue number.                                                        |
| `{publisher-id}`     | The publisher's unique ID.                                               |
| `{publisher-name}`   | The full name of the publisher.                                          |
| `{series-id}`        | The series' unique ID.                                                   |
| `{series-name}`      | The full name of the series.                                             |
| `{series-sort-name}` | Sort-friendly series name, omitting leading words such as "The" and "A". |
| `{series-year}`      | The year the series started.                                             |
| `{store-date}`       | The issue store date in `yyyy-mm-dd` format.                             |
| `{store-day}`        | The day from the issue store date.                                       |
| `{store-month}`      | The month from the issue store date.                                     |
| `{store-year}`       | The year from the issue store date.                                      |
| `{title}`            | The issue title.                                                         |
| `{upc}`              | The issue's UPC.                                                         |
| `{volume}`           | The volume of the series.                                                |

## Settings

Perdoo's settings are stored in:

```text
~/.config/perdoo/settings.toml
```

The file is created automatically on first run.

### Example

```toml
[output]
folder = "~/.local/share/perdoo/comics"
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
seperator = " "
pattern = "{publisher-name}/{series-name}[ ({series-year})][ \\[{format-short}\\]]/{series-name}[ \\[{format-short}\\]][ #{number:3}][ ({cover-year})]"

[services]
order = ["Comicvine", "Metron"]

[services.comicvine]
api-key = "<Comicvine API Key>"

[services.metron]
token = "<Metron Token>"

[sync]
days = 28
cover-hash-distance = 10
```

### Output

#### `output.folder`

The folder where output files are stored. Defaults to `~/.local/share/perdoo/comics`.

#### `output.format`

The output format used for comic archives. Defaults to `cbz`. See [Supported Formats](#supported-formats) for available formats.

#### `output.image-extensions`

The file extensions Perdoo considers to be images during the clean-up step. Defaults to `[".png", ".jpg", ".jpeg", ".webp", ".jxl"]`.

#### `output.remove-extensions`

The file extensions removed from archives during cleaning. Defaults to `[".nfo", ".sfv", ".db", ".DS_Store"]`.

#### `output.webp`

Whether to run WebP conversion by default during `pipeline`. Defaults to `false`.

#### `output.webp-quality`

Compression quality (0-100) for lossy WebP encoding. Defaults to `80`.

#### `output.webp-lossless`

Whether to use lossless WebP compression. Defaults to `false`.

#### `output.webp-jobs`

Number of worker threads used for parallel page conversion. Defaults to `4`.

### ComicInfo

#### `output.comic-info.create`

Whether to create a `ComicInfo.xml` file in the output archive. Defaults to `true`.

#### `output.comic-info.handle-pages`

Whether to process and write page count and page data in `ComicInfo.xml`. Defaults to `true`.

### MetronInfo

#### `output.metron-info.create`

Whether to create a `MetronInfo.xml` file in the output archive. Defaults to `true`.

### Naming

#### `output.naming.seperator`

The separator used in generated file names. Defaults to `-`. Supported values are `-`, `_`, `.`, and ` ` (space).

#### `output.naming.pattern`

The pattern used to generate output file names and directories. See [File Renaming and Organization](#file-renaming-and-organization) for available pattern fields.

### Services

#### `services.order`

The order in which services are queried for metadata. Perdoo uses the first service that returns a result. Defaults to `["Metron", "Comicvine"]`.

Supported services:
- `Metron`
- `Comicvine`

### Sync

#### `sync.days`

The number of days before an archive with existing metadata is synchronised again. Defaults to `28`. Can be overridden with `-f` / `--force`.

#### `sync.cover-hash-distance`

The maximum Hamming distance accepted when matching an archive cover. Defaults to `10`. Supported values range from `0` to `64`.

## License

This project is licensed under the [MIT License](LICENSE).
