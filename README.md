# Perdoo

[![GitHub - allanabiud/Perdoo](https://img.shields.io/badge/GitHub-allanabiud%2FPerdoo-blue?logo=github&style=flat-square)](https://github.com/allanabiud/Perdoo)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg?logo=python&style=flat-square)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)

Perdoo helps organise comic collections using metadata stored within comic archives. It standardises digital comics into a consistent format and can add or update metadata using supported services.

This repository is an enhanced fork of [Buried-In-Code/Perdoo](https://github.com/Buried-In-Code/Perdoo) adding native WebP conversion, interactive format prompts, `{format-short}` naming, archive page counting, and a WebP-enabled ingest pipeline.

## Installation

Perdoo is installable with [pipx](https://pipx.pypa.io/stable/):

```console
pipx install git+https://github.com/allanabiud/Perdoo.git --force
```

For local development, install in editable mode:

```console
git clone https://github.com/allanabiud/Perdoo.git ~/DEV/Projects/active/perdoo
pipx install --editable ~/DEV/Projects/active/perdoo --force
```

Python 3.11 or newer is required.

### First run - settings

Run `perdoo settings` once to generate your settings file with all defaults (including your naming pattern). The file is created at:

- **Linux/macOS:** `~/.config/perdoo/settings.toml`
- **Windows:** `%USERPROFILE%\.config\perdoo\settings.toml`

Open it and add your API keys:

```toml
[services.comicvine]
api-key = "your-comicvine-key"

[services.metron]
token = "your-metron-token"
```

Also set `output.folder` to your comics library path.

## Quick Start

1. Configure your ComicVine and/or Metron credentials, then inspect the settings:

   ```console
   perdoo settings
   ```

   Settings live in `~/.config/perdoo/settings.toml` and are created automatically on first run.

2. Preview a batch before changing anything:

   ```console
   perdoo pipeline ~/Downloads/Comics/ --dry-run
   ```

3. Run the pipeline when the preview looks correct:

   ```console
   perdoo pipeline ~/Downloads/Comics/
   ```

   The pipeline converts archives, removes unwanted files, optionally converts
   pages to WebP, synchronises metadata, and renames the results.

## Commands

| Command | Purpose |
|---------|---------|
| `pipeline` | Full ingest: convert, clean, WebP, sync metadata, rename |
| `webp` | Batch-compress archive images to WebP |
| `sync` | Fetch metadata from ComicVine/Metron into `ComicInfo.xml` / `MetronInfo.xml` |
| `rename` | Rename and organise archives using your configured naming pattern |
| `archive` | Inspect archive contents and metadata (`comic-info`, `metron-info`, `tree`) |
| `clean` | Remove unwanted files from archives |
| `settings` | Inspect current settings and defaults |
| `library` | Run `pipeline`, `sync`, `rename`, or `clean` on your configured library folder |

Run `perdoo --help` or `perdoo <command> --help` for full options.

## Services

- [Comicvine](https://comicvine.gamespot.com) via [Simyan](https://github.com/Metron-Project/Simyan)
- [Metron](https://metron.cloud) via [Mokkari](https://github.com/Metron-Project/Mokkari)

## License

This project is licensed under the [MIT License](LICENSE).
