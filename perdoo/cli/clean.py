__all__ = ["register"]

import concurrent.futures
from argparse import Namespace, _SubParsersAction
from collections.abc import Sequence
from pathlib import Path

from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn
from rich_argparse import HelpPreviewAction
from shortbox import Comic
from shortbox.errors import ArchiveCapabilityError, UnsupportedArchiveError

from perdoo.cli._results import RunResult
from perdoo.cli._utils import ArchiveType, RichHelpFormatter, enum_arg, existing_file_or_directory
from perdoo.console import CONSOLE
from perdoo.settings import Settings
from perdoo.utils import list_files


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "clean",
        help="Remove configured unwanted files from comic archives.",
        description="Remove files with extensions configured in output.remove-extensions from comic archives.",  # noqa: E501
        formatter_class=RichHelpFormatter,
    )
    parser.add_argument(
        "target",
        type=existing_file_or_directory,
        help="Comic archive or directory of comic archives to clean.",
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
        "-j",
        "--jobs",
        type=int,
        default=None,
        help="Number of parallel worker threads. Defaults to output.webp-jobs in settings.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect archives without removing files.",
    )
    parser.add_argument(
        "--generate-help-preview", action=HelpPreviewAction, path="docs/img/perdoo_clean.svg"
    )
    parser.set_defaults(func=run)


def clean_comic(comic: Comic, remove_exts: Sequence[str], dry_run: bool = False) -> None:
    try:
        for filename in comic.list_filenames():
            if Path(filename).suffix in remove_exts:
                CONSOLE.print(f"{'Would remove' if dry_run else 'Removing'} {filename!r}")
                if not dry_run:
                    comic.remove_file(filename=filename)
    except ArchiveCapabilityError as err:
        CONSOLE.print(
            f"{err}: Consider converting to another format first", style="logging.level.warning"
        )


def _clean_single(entry: Path, remove_exts: Sequence[str], dry_run: bool = False) -> None:
    """Clean a single comic archive. Intended to be submitted to an executor."""
    with Comic.open(file=entry) as comic:
        clean_comic(comic=comic, remove_exts=remove_exts, dry_run=dry_run)


def run(args: Namespace) -> RunResult:
    settings = Settings.load().save()
    result = RunResult(stage="clean")

    jobs = args.jobs if getattr(args, "jobs", None) is not None else settings.output.webp_jobs
    files = list_files(args.target) if args.target.is_dir() else [args.target]
    if getattr(args, "resume_paths", None):
        files = [file for file in files if file.resolve() in args.resume_paths]
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
        task_id = progress.add_task("Cleaning comics", total=len(files))
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
            futures = {
                executor.submit(
                    _clean_single,
                    entry,
                    settings.output.remove_extensions,
                    getattr(args, "dry_run", False),
                ): entry
                for entry in files
            }
            for future in concurrent.futures.as_completed(futures):
                entry = futures[future]
                result.processed += 1
                try:
                    future.result()
                    result.succeeded += 1
                except UnsupportedArchiveError:
                    result.skipped += 1
                except Exception as err:  # noqa: BLE001
                    result.add_failure(entry, err)
                    CONSOLE.print(
                        f"Failed to clean [cyan]{entry.name}[/cyan]: {err}",
                        style="logging.level.error",
                    )
                progress.advance(task_id)
    return result
