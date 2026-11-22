__all__ = [
    "build_local_metadata",
    "parse_local_filename",
    "prompt_format_override",
]

import re
from datetime import date
from pathlib import Path

import questionary
from shortbox.metadata import ComicInfo, MetronInfo
from shortbox.metadata.metron_info import Format, Series

from perdoo.format_resolver import FORMAT_CHOICES, apply_format_to_metadata

_FILE_NAME_PATTERNS = [
    re.compile(
        r"^(?P<series>.+?)\s*#\s*(?P<number>\d+(?:\.\d+)?)\s*\((?P<year>\d{4})\)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<series>.+?)\s*\((?P<year>\d{4})\)\s*#\s*(?P<number>\d+(?:\.\d+)?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<series>.+?)\s*#\s*(?P<number>\d+(?:\.\d+)?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<series>.+?)\s*\((?P<year>\d{4})\)\s*$",
        re.IGNORECASE,
    ),
]


def parse_local_filename(filepath: Path) -> dict[str, str | int | None]:
    """Extract series-name, number, and cover-year from a local comic filename.

    Supports patterns like::

        Batman #001 (2026).cbz
        Batman (2026) #001.cbz
        Batman #1.cbz
        Batman (2026).cbz

    Returns a dict with keys ``series``, ``number``, ``year``.
    """
    stem = filepath.stem
    for pattern in _FILE_NAME_PATTERNS:
        match = pattern.match(stem)
        if match:
            groups = match.groupdict()
            series = (groups.get("series") or "").strip(" -._")
            number = groups.get("number")
            year = groups.get("year")
            return {
                "series": series or None,
                "number": number or None,
                "year": int(year) if year else None,
            }
    return {"series": None, "number": None, "year": None}


def build_local_metadata(
    comic_file: Path,
    parsed: dict[str, str | int | None],
    format_override: Format | None = None,
) -> tuple[ComicInfo, MetronInfo]:
    """Build minimal ComicInfo and MetronInfo from a local filename parse."""
    series_name = str(parsed.get("series") or comic_file.stem)
    number = str(parsed.get("number") or "1")
    year = parsed.get("year")
    cover_year = year if isinstance(year, int) and year >= 1900 else None

    comic_info = ComicInfo(
        series=series_name,
        number=number,
        title=series_name,
        year=cover_year,
        volume=year if isinstance(year, int) and year < 1900 else None,
    )

    metron_series = Series(
        name=series_name,
        start_year=cover_year,
    )
    if format_override is not None:
        metron_series.format = format_override

    cover_date = date(cover_year, 1, 1) if cover_year else None

    metron_info = MetronInfo(
        series=metron_series,
        number=number,
        collection_title=series_name,
        cover_date=cover_date,
    )

    if format_override is not None:
        apply_format_to_metadata(
            comic_info=comic_info,
            metron_info=metron_info,
            fmt_enum=format_override,
            fmt_short=format_override.value,
        )

    return comic_info, metron_info


def prompt_format_override(label: str) -> Format | None:
    """Interactively ask the user to pick a format for a local comic."""
    selected = questionary.select(
        f"Select format for '{label}':",
        choices=FORMAT_CHOICES,
    ).ask()
    if selected:
        _short, fmt_enum = selected
        return fmt_enum
    return None
