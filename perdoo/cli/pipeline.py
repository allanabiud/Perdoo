__all__ = ["register"]

import argparse
from argparse import Namespace, _SubParsersAction
from pathlib import Path

from rich_argparse import HelpPreviewAction

from perdoo.cli._utils import ArchiveType, RichHelpFormatter, enum_arg, existing_file_or_directory
from perdoo.cli.clean import run as run_clean
from perdoo.cli.convert import run as run_convert
from perdoo.cli.rename import run as run_rename
from perdoo.cli.sync import run as run_sync
from perdoo.cli.webp import run as run_webp
from perdoo.settings import Settings


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "pipeline", help="", description="", formatter_class=RichHelpFormatter
    )
    parser.add_argument(
        "target",
        type=existing_file_or_directory,
        help="Comic archive or directory of comic archives to synchronize.",
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
        "-f",
        "--force",
        action="store_true",
        help="Synchronize even if the stored metadata was updated within the configured interval.",
    )
    parser.add_argument(
        "-F",
        "--format",
        dest="format",
        metavar="FORMAT",
        help="Force comic format (e.g. TPB, HC, OB, One-Shot, GN, Annual).",
    )
    parser.add_argument(
        "-w",
        "--webp",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Convert comic archive images to WebP format.",
    )
    parser.add_argument(
        "--generate-help-preview", action=HelpPreviewAction, path="docs/img/perdoo_pipeline.svg"
    )
    parser.set_defaults(func=run)


def run(args: Namespace) -> None:
    settings = Settings.load().save()
    run_convert(args)

    if isinstance(args.target, Path) and not args.target.is_dir():
        converted_path = args.target.with_suffix(f".{settings.output.format}")
        if not args.target.exists() and converted_path.exists():
            args.target = converted_path

    should_webp = args.webp if getattr(args, "webp", None) is not None else settings.output.webp
    if should_webp:
        run_webp(args)

    run_clean(args)
    run_sync(args)
    run_rename(args)
