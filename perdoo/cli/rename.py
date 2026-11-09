__all__ = ["register"]

import contextlib
from argparse import Namespace, _SubParsersAction
from collections.abc import Sequence
from pathlib import Path

from natsort import humansorted, ns
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn
from rich_argparse import HelpPreviewAction
from shortbox import Comic
from shortbox.errors import ArchiveCapabilityError, UnsupportedArchiveError
from shortbox.metadata import ComicInfo, MetronInfo

from perdoo.cli._utils import ArchiveType, RichHelpFormatter, enum_arg, existing_file_or_directory
from perdoo.console import CONSOLE
from perdoo.format_resolver import apply_format_to_metadata, parse_format_str
from perdoo.naming import build_file
from perdoo.pages import update_comic_pages_metadata
from perdoo.settings import Settings
from perdoo.utils import list_files


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "rename",
        help="Rename and organize comic archives using their metadata.",
        description="Rename and organize comic archives using the configured naming pattern.",
        formatter_class=RichHelpFormatter,
    )
    parser.add_argument(
        "target",
        type=existing_file_or_directory,
        help="Comic archive or directory of comic archives to rename.",
    )
    parser.add_argument(
        "-i",
        "--ignore",
        action="append",
        type=enum_arg(enum_type=ArchiveType),
        choices=list(ArchiveType),
        metavar="EXT",
        help="Skip archives with this extension. Repeat to ignore multiple extensions.",
    )
    parser.add_argument(
        "-F",
        "--format",
        dest="format",
        metavar="FORMAT",
        help="Force comic format (e.g. TPB, HC, OB, One-Shot, GN, Annual).",
    )
    parser.add_argument(
        "--generate-help-preview", action=HelpPreviewAction, path="docs/img/perdoo_rename.svg"
    )
    parser.set_defaults(func=run)


def rename_comic(comic: Comic, image_exts: Sequence[str]) -> None:
    try:
        pad = len(str(len(comic.list_filenames())))
        idx = 0
        for filename in humansorted(comic.list_filenames(), alg=ns.NA | ns.G | ns.P):
            suffix = Path(filename).suffix
            if suffix in image_exts:
                new_name = f"{str(idx).zfill(pad)}{suffix}"
                idx += 1
                if filename != new_name:
                    CONSOLE.print(f"Renaming {filename!r} to {new_name!r}")
                    comic.rename_file(filename=filename, new_name=new_name, override=True)
    except ArchiveCapabilityError as err:
        CONSOLE.print(
            f"{err}: Consider converting to another format first", style="logging.level.warning"
        )


def _cleanup_empty_dirs(start: Path, stop: Path) -> None:
    """Remove directories left empty by a move, walking up from `start` towards `stop`.

    Stops at `stop` (exclusive) or at the first directory that still has content,
    so directories outside the requested target are never touched.
    """
    current = start
    while current != stop and stop in current.parents:
        try:
            if any(current.iterdir()):
                return
            current.rmdir()
        except OSError:
            return
        CONSOLE.print(f"Removed empty directory '{current.relative_to(stop)}'", style="dim")
        current = current.parent


def rename_entry(
    entry: Path, target: Path, settings: Settings, cli_format: str | None = None
) -> None:
    with Comic.open(file=entry) as comic:
        comic_info = None
        metron_info = None
        with contextlib.suppress(Exception):
            comic_info = comic.get_metadata(ComicInfo)
        with contextlib.suppress(Exception):
            metron_info = comic.get_metadata(MetronInfo)

        updated = False
        if cli_format:
            fmt_enum, fmt_short = parse_format_str(cli_format)
            if fmt_enum or fmt_short:
                apply_format_to_metadata(comic_info, metron_info, fmt_enum, fmt_short)
                updated = True

        if (
            settings.output.comic_info.handle_pages
            and (comic_info or metron_info)
            and update_comic_pages_metadata(
                comic=comic,
                comic_info=comic_info,
                metron_info=metron_info,
                image_extensions=settings.output.image_extensions,
            )
        ):
            updated = True

        if updated:
            if comic_info:
                comic.set_metadata(comic_info)
            if metron_info:
                comic.set_metadata(metron_info)

        new_file = build_file(
            comic=comic, folder=settings.output.folder, settings=settings.output.naming
        )
        if not new_file:
            CONSOLE.print(f"'{entry.name}' has no recognised metadata, skipping")
            return
        new_relative = new_file.relative_to(settings.output.folder.resolve())
        if comic.file != new_file and new_file.exists():
            CONSOLE.print(f"'{new_relative}' already exists, skipping")
            return
        rename_comic(comic=comic, image_exts=settings.output.image_extensions)
    if new_file.exists():
        return
    new_file.parent.mkdir(parents=True, exist_ok=True)
    old_relative = entry.relative_to(target) if target.is_dir() else entry.name
    CONSOLE.print(f"'{old_relative}' renamed to '{new_relative}'")
    entry.rename(new_file)
    # When target is a single file the stop path can never appear in
    # entry.parent's parents, so this is a no-op outside directory targets.
    _cleanup_empty_dirs(start=entry.parent, stop=target)


def run(args: Namespace) -> None:
    settings = Settings.load().save()

    files = list_files(args.target) if args.target.is_dir() else [args.target]
    if args.ignore:
        ignore_ext = [f".{x}" for x in args.ignore]
        files = [x for x in files if x.suffix not in ignore_ext]
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=CONSOLE,
        expand=True,
    )

    with progress:
        for entry in progress.track(files, description="Renaming comics"):
            try:
                rename_entry(
                    entry=entry,
                    target=args.target,
                    settings=settings,
                    cli_format=getattr(args, "format", None),
                )
            except UnsupportedArchiveError:
                CONSOLE.print(f"'{entry.name}' is not a supported archive, skipping")
            except Exception as err:  # noqa: BLE001
                CONSOLE.print(
                    f"Failed to rename '{entry.name}': {err}", style="logging.level.error"
                )
