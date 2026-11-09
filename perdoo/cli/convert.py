__all__ = ["register"]

import concurrent.futures
import shutil
import subprocess
import tempfile
from argparse import Namespace, _SubParsersAction
from pathlib import Path

from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn
from rich_argparse import HelpPreviewAction
from shortbox import Comic
from shortbox.archives import Archive, TarArchive, ZipArchive
from shortbox.errors import UnsupportedArchiveError

from perdoo.cli._results import RunResult
from perdoo.cli._utils import ArchiveType, RichHelpFormatter, enum_arg, existing_file_or_directory
from perdoo.console import CONSOLE
from perdoo.settings import Settings
from perdoo.utils import list_files


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "convert",
        help="Convert comic archives to the configured output format.",
        description="Convert comic archives to the format configured in output.format.",
        formatter_class=RichHelpFormatter,
    )
    parser.add_argument(
        "target",
        type=existing_file_or_directory,
        help="Comic archive or directory of comic archives to convert.",
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
        help="Inspect archives without converting them.",
    )
    parser.add_argument(
        "--generate-help-preview", action=HelpPreviewAction, path="docs/img/perdoo_convert.svg"
    )
    parser.set_defaults(func=run)


def determine_format(format_: str) -> type[Archive]:
    formats: dict[str, type[Archive]] = {
        ZipArchive.extension: ZipArchive,
        TarArchive.extension: TarArchive,
    }
    from shortbox import archives  # noqa: PLC0415

    if sevenzip_archive := getattr(archives, "SevenZipArchive", None):
        formats[sevenzip_archive.extension] = sevenzip_archive
    if rar_archive := getattr(archives, "RarArchive", None):
        formats[rar_archive.extension] = rar_archive
    if pdf_archive := getattr(archives, "PdfArchive", None):
        formats[pdf_archive.extension] = pdf_archive
    output = formats.get(f".{format_}")
    if output is None:
        CONSOLE.print(
            f"{format_!r} output requires `perdoo[{format_}]`; install it and retry",
            style="logging.level.warning",
        )
        raise SystemExit(1)
    return output


def _convert_with_7z(entry: Path) -> bool:
    """Extract an unsupported archive with ``7z`` and re-pack it as a ``.cbz``."""
    seven_zip = shutil.which("7z")
    if seven_zip is None:
        CONSOLE.print(
            f"[bold]7z[/bold] not found; skipping [cyan]{entry.name}[/cyan]",
            style="logging.level.warning",
        )
        return False

    CONSOLE.print(
        f"Falling back to [bold]7z[/bold] for [cyan]{entry.name}[/cyan]",
        style="logging.level.info",
    )

    with tempfile.TemporaryDirectory() as tmp:
        extract_dir = Path(tmp) / "extracted"
        extract_dir.mkdir()

        # Extract the archive contents.
        result = subprocess.run(
            [seven_zip, "x", f"-o{extract_dir}", "-y", str(entry)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            CONSOLE.print(
                f"7z extraction failed for [cyan]{entry.name}[/cyan]: {result.stderr.strip()}",
                style="logging.level.error",
            )
            return False

        # Re-pack as a ZIP archive.
        temp_cbz = Path(tmp) / entry.with_suffix(".cbz").name
        result = subprocess.run(
            [seven_zip, "a", "-tzip", str(temp_cbz), "."],
            cwd=str(extract_dir),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            CONSOLE.print(
                f"7z re-pack failed for [cyan]{entry.name}[/cyan]: {result.stderr.strip()}",
                style="logging.level.error",
            )
            return False

        # Verify the newly created archive.
        result = subprocess.run(
            [seven_zip, "t", str(temp_cbz)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            CONSOLE.print(
                f"7z integrity check failed for [cyan]{temp_cbz.name}[/cyan]",
                style="logging.level.error",
            )
            return False

        # Replace the original file.
        output_path = entry.with_suffix(".cbz")
        shutil.move(str(temp_cbz), str(output_path))
        if entry.suffix != ".cbz" and entry.exists():
            entry.unlink()

        CONSOLE.print(
            f"Converted [cyan]{entry.name}[/cyan] → [green]{output_path.name}[/green]",
            style="logging.level.info",
        )
        return True


def _convert_single(
    entry: Path, target_format: type[Archive], dry_run: bool = False
) -> str:
    """Convert a single comic archive. Intended to be submitted to an executor."""
    if entry.suffix.lower() == target_format.extension.lower():
        if dry_run:
            CONSOLE.print(f"Already {target_format.__name__}: [cyan]{entry.name}[/cyan]")
        return "skipped"
    if dry_run:
        CONSOLE.print(f"Would convert [cyan]{entry.name}[/cyan] to {target_format.__name__}")
        return "planned"
    try:
        with Comic.open(file=entry) as comic:
            comic.convert(
                archive_type=target_format, delete_original=True, raise_on_existing=False
            )
        return "converted"
    except UnsupportedArchiveError:
        return "converted" if _convert_with_7z(entry=entry) else "skipped"


def run(args: Namespace) -> RunResult:
    settings = Settings.load().save()
    result = RunResult(stage="convert")

    jobs = args.jobs if getattr(args, "jobs", None) is not None else settings.output.webp_jobs
    target_format = determine_format(format_=settings.output.format)
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
        task_id = progress.add_task("Converting comics", total=len(files))
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
            futures = {
                executor.submit(
                    _convert_single, entry, target_format, getattr(args, "dry_run", False)
                ): entry
                for entry in files
            }
            for future in concurrent.futures.as_completed(futures):
                entry = futures[future]
                result.processed += 1
                try:
                    status = future.result()
                    if status == "planned":
                        result.planned += 1
                    elif status == "skipped":
                        result.skipped += 1
                    else:
                        result.succeeded += 1
                except Exception as err:  # noqa: BLE001
                    result.add_failure(entry, err)
                    CONSOLE.print(
                        f"Failed to convert [cyan]{entry.name}[/cyan]: {err}",
                        style="logging.level.error",
                    )
                progress.advance(task_id)
    return result
