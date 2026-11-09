__all__ = ["register"]

from argparse import Namespace, _SubParsersAction
from pathlib import Path

from rich_argparse import RichHelpFormatter

from perdoo.cli.clean import run as run_clean
from perdoo.cli.pipeline import run as run_pipeline
from perdoo.cli.rename import run as run_rename
from perdoo.cli.sync import run as run_sync
from perdoo.console import CONSOLE
from perdoo.settings import Settings


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "library",
        help="Manage the configured comic library.",
        description="Run library actions against the configured output.folder.",
        formatter_class=RichHelpFormatter,
    )
    actions = parser.add_subparsers(dest="library_action", required=True)
    for action, handler in (
        ("pipeline", run_pipeline),
        ("sync", run_sync),
        ("rename", run_rename),
        ("clean", run_clean),
    ):
        action_parser = actions.add_parser(
            action,
            help=f"Run the {action} action on the configured library.",
            formatter_class=RichHelpFormatter,
        )
        action_parser.set_defaults(func=_run_library_action, library_handler=handler)
        _add_common_options(action_parser)


def _add_common_options(parser: _SubParsersAction) -> None:
    parser.add_argument(
        "-i",
        "--ignore",
        action="append",
        choices=["cb7", "cbr", "cbt", "cbz", "pdf"],
        metavar="EXT",
        help="Skip archives with this extension. Repeat to ignore multiple extensions.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Synchronize even if stored metadata is recent.",
    )
    parser.add_argument(
        "-F",
        "--format",
        dest="format",
        metavar="FORMAT",
        help="Force comic format (e.g. TPB, HC, OB, One-Shot, GN, Annual).",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=None,
        help="Number of parallel worker threads for local archive operations.",
    )
    parser.add_argument(
        "-w",
        "--webp",
        action="store_true",
        default=None,
        help="Convert comic archive images to WebP during pipeline.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without modifying archives or filesystem paths.",
    )
    parser.add_argument(
        "--refresh-pages",
        action="store_true",
        help="Reinspect archive pages before renaming.",
    )
    parser.add_argument(
        "--failure-manifest",
        type=Path,
        metavar="PATH",
        help="Write pipeline failures to a JSON manifest.",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        metavar="PATH",
        help="Process only paths listed in a previous pipeline failure manifest.",
    )


def _run_library_action(args: Namespace) -> object | None:
    settings = Settings.load()
    target = settings.output.folder.expanduser().resolve()
    if not target.is_dir():
        CONSOLE.print(
            f"Configured library folder does not exist: {target}",
            style="logging.level.error",
        )
        return None
    args.target = target
    return args.library_handler(args)
