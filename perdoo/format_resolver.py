__all__ = [
    "apply_format_to_metadata",
    "detect_format_from_description",
    "detect_format_from_filename",
    "parse_format_str",
    "prompt_format_selection",
    "resolve_series_format",
]

import re
import sys

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


def detect_format_from_filename(name: str) -> tuple[Format | None, str | None]:
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


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace from service description text."""
    clean = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", clean).strip()


_ONE_SHOT_AVOID_WORDS = ("preceding", "after the", "following the", "continued from")


def _detect_one_shot(clean_desc: str) -> bool:
    """Detect a One-Shot descriptor in the first 60 characters of a description.

    Ported from Mylar3's ``get_imprint_volume_and_booktype`` (``mylar/cv.py``):
    the keyword must appear early and must not be preceded by an avoid-word
    (Mylar3's "FAKE NEWS" check), and phrases promoting other editions
    (``can be found``) reject the match anywhere in the text.
    """
    if "can be found" in clean_desc.lower():
        return False
    match = re.search(r"one[\s\-_]*shot", clean_desc[:60], flags=re.IGNORECASE)
    if not match:
        return False
    prefix = clean_desc[: match.start()].lower()
    return not any(word in prefix for word in _ONE_SHOT_AVOID_WORDS)


def _format_from_deck(deck: str) -> tuple[Format | None, str | None]:  # noqa: PLR0911
    """Match format descriptors in a short summary (deck), checked as whole text."""
    text = deck.strip().lower()
    if re.search(r"\b(omnibus|compendium)\b", text):
        return Format.OMNIBUS, "OB"
    if re.search(r"\bdigital\b", text):
        return Format.DIGITAL_CHAPTER, "Digital"
    if re.search(r"\bpaperback\b", text):
        return Format.TRADE_PAPERBACK, "TPB"
    if re.search(r"\bgraphic\s*novel\b", text):
        return Format.GRAPHIC_NOVEL, "GN"
    if re.search(r"\bhardcover\b", text):
        return Format.HARDCOVER, "HC"
    if re.search(r"\bone[\s\-_]*shot\b", text):
        return Format.ONE_SHOT, "One-Shot"
    # "print" / "reprint" decks and decks without descriptors are neutral.
    return None, None


def _format_from_description(clean: str) -> tuple[Format | None, str | None]:  # noqa: PLR0911
    """Match format descriptors in the first 60 characters of a description."""
    head = clean[:60].lower()
    full = clean.lower()
    if re.search(r"\b(omnibus|compendium)\b", head):
        return Format.OMNIBUS, "OB"
    if (
        "digital" in head
        and "graphic novel" not in head
        and "digital edition can be found" not in full
    ):
        return Format.DIGITAL_CHAPTER, "Digital"
    if ("paperback" in head and "paperback can be found" not in full) or (
        "hardcover" not in head and "collects" in head
    ):
        return Format.TRADE_PAPERBACK, "TPB"
    if "graphic novel" in head and "graphic novel can be found" not in full:
        return Format.GRAPHIC_NOVEL, "GN"
    if ("hardcover" in head or "deluxe" in head) and "hardcover can be found" not in full:
        return Format.HARDCOVER, "HC"
    if _detect_one_shot(clean):
        return Format.ONE_SHOT, "One-Shot"
    return None, None


def detect_format_from_description(
    volume_summary: str | None = None,
    volume_description: str | None = None,
    issue_summary: str | None = None,
    issue_description: str | None = None,
) -> tuple[Format | None, str | None]:
    """Detect the series format from service description texts (Mylar3-style).

    Comicvine does not store a series format, so collected editions are
    recognised from descriptors in the metadata text. Ported from Mylar3's
    ``get_imprint_volume_and_booktype`` (``mylar/cv.py``):

    - Short summaries (decks) are checked as whole text.
    - Long descriptions are checked by their first 60 characters only, with
      negative phrases (e.g. ``hardcover can be found``) to avoid false
      positives, and HTML tags stripped first.
    - The volume texts are checked before the issue texts.

    Extended beyond Mylar3 with ``omnibus``/``compendium`` detection and a
    ``deluxe`` hardcover descriptor.

    Returns:
        A ``(Format, short)`` tuple, or ``(None, None)`` when no format was found.
    """
    # Deck pass: whole-text keyword check, volume deck first, then issue deck.
    for deck in (volume_summary, issue_summary):
        if not deck or not deck.strip():
            continue
        fmt, short = _format_from_deck(deck)
        if fmt or short:
            return fmt, short

    # Description pass: first 60 characters, volume description first.
    for desc in (volume_description, issue_description):
        if not desc:
            continue
        clean = _strip_html(desc)
        if not clean:
            continue
        fmt, short = _format_from_description(clean)
        if fmt or short:
            return fmt, short
    return None, None


def _fetched_format(
    fetched_format_comic: str | None, fetched_format_metron: Format | None
) -> tuple[Format | None, str | None]:
    """Best format known from the metadata service that produced the result."""
    if fetched_format_metron and fetched_format_metron != Format.SINGLE_ISSUE:
        return fetched_format_metron, fetched_format_metron.value
    if fetched_format_comic:
        return parse_format_str(fetched_format_comic)
    return None, None


def parse_format_str(fmt_str: str | None) -> tuple[Format | None, str | None]:
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
    label: str, default_short: str | None = None
) -> tuple[Format | None, str | None]:
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
            f"Select format for '{label}':", choices=FORMAT_CHOICES, default=default_choice
        ).ask()
        if selected:
            short, fmt_enum = selected
            return fmt_enum, short
    except (KeyboardInterrupt, EOFError):
        pass
    return None, None


def _prompt_for_guess(
    label: str, det_short: str | None, guess_known: bool, prompt_if_missing: bool
) -> tuple[Format | None, str | None]:
    """Confirm a filename-based guess interactively, or ask when nothing is known.

    Service-fetched guesses (description detection, Metron series type) and the
    One-Shot forcing rule are applied automatically without prompting.
    """
    if not prompt_if_missing:
        return None, None
    if not det_short and guess_known:
        return None, None
    return prompt_format_selection(label, default_short=det_short)


def resolve_series_format(
    series_name: str | None,
    filename: str,
    cli_format: str | None = None,
    existing_format_comic: str | None = None,
    existing_format_metron: Format | None = None,
    fetched_format_comic: str | None = None,
    fetched_format_metron: Format | None = None,
    force_one_shot: bool = False,
    prompt_if_missing: bool = True,
) -> tuple[Format | None, str | None]:
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

    # 3. Detect format from filename / directory path heuristics
    det_fmt, det_short = detect_format_from_filename(f"{series_name or ''} {filename}")

    # 4. Best automatic guess: a filename/directory tag wins over the format
    #    fetched from the service (Metron series type or Mylar3-style
    #    description detection), which in turn wins over the single-issue
    #    One-Shot forcing rule.
    guess_fmt, guess_short = _fetched_format(
        fetched_format_comic=fetched_format_comic, fetched_format_metron=fetched_format_metron
    )
    if det_fmt or det_short:
        guess_fmt, guess_short = det_fmt, det_short
    elif not (guess_fmt or guess_short) and force_one_shot:
        guess_fmt, guess_short = Format.ONE_SHOT, "One-Shot"

    # 5. Confirm a filename-based guess interactively, or ask the user when
    #    nothing is known. Service-fetched guesses are applied automatically.
    fmt_enum, fmt_short = _prompt_for_guess(
        label=series_name or filename,
        det_short=det_short,
        guess_known=bool(guess_fmt or guess_short),
        prompt_if_missing=prompt_if_missing,
    )
    if fmt_enum or fmt_short:
        return fmt_enum, fmt_short

    # 6. Non-interactive fallback: use the best automatic guess
    if guess_fmt or guess_short:
        return guess_fmt, guess_short

    return None, None


def apply_format_to_metadata(
    comic_info: ComicInfo | None,
    metron_info: MetronInfo | None,
    fmt_enum: Format | None,
    fmt_short: str | None,
) -> None:
    if comic_info is not None and (fmt_enum or fmt_short):
        # Metadata always stores the full format name (e.g. "Trade Paperback");
        # short codes (e.g. "TPB") are only used for {format-short} naming.
        comic_info.format = fmt_enum.value if fmt_enum else fmt_short
    if fmt_enum and metron_info is not None and metron_info.series is not None:
        metron_info.series.format = fmt_enum
