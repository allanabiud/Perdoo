__all__ = [
    "parse_format_str",
    "detect_format_from_filename",
    "prompt_format_selection",
    "resolve_series_format",
    "apply_format_to_metadata",
]

import re
import sys
from typing import Optional, Tuple

import questionary
from shortbox.metadata import ComicInfo, MetronInfo
from shortbox.metadata.metron_info import Format

STRING_TO_FORMAT = {
    "tpb": (Format.TRADE_PAPERBACK, "TPB"),
    "trade paperback": (Format.TRADE_PAPERBACK, "TPB"),
    "hc": (Format.HARDCOVER, "HC"),
    "hardcover": (Format.HARDCOVER, "HC"),
    "deluxe": (Format.HARDCOVER, "HC"),
    "deluxe edition": (Format.HARDCOVER, "HC"),
    "ob": (Format.OMNIBUS, "OB"),
    "omnibus": (Format.OMNIBUS, "OB"),
    "omni": (Format.OMNIBUS, "OB"),
    "gn": (Format.GRAPHIC_NOVEL, "GN"),
    "graphic novel": (Format.GRAPHIC_NOVEL, "GN"),
    "one-shot": (Format.ONE_SHOT, "One-Shot"),
    "oneshot": (Format.ONE_SHOT, "One-Shot"),
    "special": (Format.ONE_SHOT, "One-Shot"),
    "annual": (Format.ANNUAL, "Annual"),
    "digital": (Format.DIGITAL_CHAPTER, "Digital"),
    "digital chapter": (Format.DIGITAL_CHAPTER, "Digital"),
    "single issue": (Format.SINGLE_ISSUE, None),
    "single": (Format.SINGLE_ISSUE, None),
    "floppy": (Format.SINGLE_ISSUE, None),
}

FORMAT_CHOICES = [
    questionary.Choice(title="TPB (Trade Paperback)", value=("TPB", Format.TRADE_PAPERBACK)),
    questionary.Choice(title="HC (Hardcover / Deluxe)", value=("HC", Format.HARDCOVER)),
    questionary.Choice(title="Omnibus", value=("OB", Format.OMNIBUS)),
    questionary.Choice(title="One-Shot", value=("One-Shot", Format.ONE_SHOT)),
    questionary.Choice(title="Graphic Novel", value=("GN", Format.GRAPHIC_NOVEL)),
    questionary.Choice(title="Annual", value=("Annual", Format.ANNUAL)),
    questionary.Choice(title="Single Issue (Floppy / None)", value=(None, None)),
]


def detect_format_from_filename(name: str) -> Tuple[Optional[Format], Optional[str]]:
    """Smart heuristic format detection from filename or directory path."""
    clean = name.lower()
    if re.search(r"\b(omnibus|omni)\b|\[ob\]|\(ob\)", clean):
        return Format.OMNIBUS, "OB"
    if re.search(r"\b(hardcover|deluxe|dlx)\b|\[hc\]|\(hc\)", clean):
        return Format.HARDCOVER, "HC"
    if re.search(r"\b(tpb|trade\s*paperback|collection)\b|\[tpb\]|\(tpb\)|\bvol(\.|\s+)\d+", clean):
        return Format.TRADE_PAPERBACK, "TPB"
    if re.search(r"\b(one[\s\-_]*shot|special)\b|\[one[\s\-_]*shot\]", clean):
        return Format.ONE_SHOT, "One-Shot"
    if re.search(r"\bannual\b", clean):
        return Format.ANNUAL, "Annual"
    if re.search(r"\b(graphic\s*novel|gn)\b|\[gn\]|\(gn\)", clean):
        return Format.GRAPHIC_NOVEL, "GN"
    return None, None


def parse_format_str(fmt_str: Optional[str]) -> Tuple[Optional[Format], Optional[str]]:
    if not fmt_str:
        return None, None
    key = str(fmt_str).strip().lower()
    if key in STRING_TO_FORMAT:
        return STRING_TO_FORMAT[key]
    try:
        f = Format.load(value=fmt_str.strip())
        return f, f.value
    except ValueError:
        return None, fmt_str


def prompt_format_selection(
    label: str, default_short: Optional[str] = None
) -> Tuple[Optional[Format], Optional[str]]:
    """Interactively prompt user to pick a format for the series."""
    if not sys.stdin.isatty():
        return None, None
    default_choice = FORMAT_CHOICES[0]
    if default_short:
        for c in FORMAT_CHOICES:
            if c.value[0] == default_short:
                default_choice = c
                break
    try:
        selected = questionary.select(
            f"Select format for '{label}':",
            choices=FORMAT_CHOICES,
            default=default_choice,
        ).ask()
        if selected:
            short, fmt_enum = selected
            return fmt_enum, short
    except (KeyboardInterrupt, EOFError):
        pass
    return None, None


def resolve_series_format(
    series_name: Optional[str],
    filename: str,
    cli_format: Optional[str] = None,
    existing_format_comic: Optional[str] = None,
    existing_format_metron: Optional[Format] = None,
    prompt_if_missing: bool = True,
) -> Tuple[Optional[Format], Optional[str]]:
    # 1. On-demand CLI flag (-F / --format) has highest priority
    if cli_format:
        fmt, short = parse_format_str(cli_format)
        if fmt or short:
            return fmt, short

    # 2. Existing format from metadata (preserves existing format across syncs)
    if existing_format_metron and existing_format_metron != Format.SINGLE_ISSUE:
        return existing_format_metron, existing_format_metron.value
    if existing_format_comic:
        fmt, short = parse_format_str(existing_format_comic)
        if fmt or short:
            return fmt, short

    # 3. Detect format from filename / series name heuristics
    det_fmt, det_short = detect_format_from_filename(f"{series_name or ''} {filename}")

    # 4. If format is missing and interactive prompt is enabled, ask user
    if prompt_if_missing:
        label = series_name or filename
        fmt_enum, fmt_short = prompt_format_selection(label, default_short=det_short)
        if fmt_enum or fmt_short:
            return fmt_enum, fmt_short

    # 5. Non-interactive fallback: use detected format if found
    if det_fmt or det_short:
        return det_fmt, det_short

    return None, None


def apply_format_to_metadata(
    comic_info: Optional[ComicInfo],
    metron_info: Optional[MetronInfo],
    fmt_enum: Optional[Format],
    fmt_short: Optional[str],
) -> None:
    if fmt_short and comic_info is not None:
        comic_info.format = fmt_short
    if fmt_enum and metron_info is not None and metron_info.series is not None:
        metron_info.series.format = fmt_enum
