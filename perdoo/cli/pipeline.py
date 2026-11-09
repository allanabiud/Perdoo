__all__ = ["register"]

import argparse
import json
from argparse import Namespace, _SubParsersAction
from pathlib import Path

from rich_argparse import HelpPreviewAction

from perdoo.cli._results import RunResult
from perdoo.cli._utils import ArchiveType, RichHelpFormatter, enum_arg, existing_file_or_directory
from perdoo.cli.clean import run as run_clean
from perdoo.cli.convert import run as run_convert
from perdoo.cli.rename import run as run_rename
from perdoo.cli.sync import run as run_sync
from perdoo.cli.webp import run as run_webp
from perdoo.console import CONSOLE
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
        "--dry-run",
        action="store_true",
        help="Preview all pipeline stages without modifying archives or filesystem paths.",
    )
    parser.add_argument(
        "--failure-manifest",
        type=Path,
        metavar="PATH",
        help="Write failed archive paths and errors to a JSON manifest.",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        metavar="PATH",
        help="Process only paths listed in a previous failure manifest.",
    )
    parser.add_argument(
        "--generate-help-preview", action=HelpPreviewAction, path="docs/img/perdoo_pipeline.svg"
    )
    parser.set_defaults(func=run)


def run(args: Namespace) -> RunResult:
    settings = Settings.load().save()
    if args.resume:
        manifest = json.loads(args.resume.read_text())
        args.resume_paths = {Path(item["path"]).resolve() for item in manifest}

    args.dry_run = getattr(args, "dry_run", False)
    result = RunResult(stage="pipeline")
    stage_results: list[RunResult] = []
    for stage_result in (run_convert(args),):
        if isinstance(stage_result, RunResult):
            stage_results.append(stage_result)
            result.merge(stage_result)

    if isinstance(args.target, Path) and not args.target.is_dir():
        converted_path = args.target.with_suffix(f".{settings.output.format}")
        if not args.target.exists() and converted_path.exists():
            args.target = converted_path

    should_webp = args.webp if getattr(args, "webp", None) is not None else settings.output.webp
    if should_webp:
        run_webp(args)

    for stage_result in (run_clean(args), run_sync(args), run_rename(args)):
        if isinstance(stage_result, RunResult):
            stage_results.append(stage_result)
            result.merge(stage_result)

    if args.failure_manifest:
        args.failure_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.failure_manifest.write_text(
            json.dumps(
                [
                    {"stage": failure.stage, "path": str(failure.path), "error": failure.error}
                    for failure in result.failures
                ],
                indent=2,
            )
            + "\n"
        )
    CONSOLE.print("Pipeline summary:")
    for stage_result in stage_results:
        CONSOLE.print(
            f"  {stage_result.stage}: {stage_result.processed} processed, "
            f"{stage_result.succeeded} completed, {stage_result.planned} planned, "
            f"{stage_result.skipped} skipped, {stage_result.failed} failed",
            style="logging.level.error" if stage_result.failed else "dim",
        )
    CONSOLE.print(
        f"  total failures: {result.failed}",
        style="logging.level.error" if result.failed else "dim",
    )
    return result
