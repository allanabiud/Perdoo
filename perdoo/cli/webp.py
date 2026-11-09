from __future__ import annotations

__all__ = ["convert_archive", "register", "run"]

import argparse
from argparse import Namespace, _SubParsersAction
import concurrent.futures
import os
import pathlib
import shutil
import subprocess
import tempfile
import time
from typing import Dict, List, Optional, Set, Tuple

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from perdoo.cli._utils import RichHelpFormatter, existing_file_or_directory
from perdoo.console import CONSOLE
from perdoo.settings import Settings
from perdoo.utils import list_files

try:
    from PIL import Image

    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

IMAGE_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".jxl", ".tiff", ".webp"}
CONVERTIBLE_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".jxl", ".tiff"}
COMIC_EXTENSIONS: Set[str] = {".cbz", ".cbr", ".cb7", ".cbt", ".zip", ".rar", ".7z"}
JUNK_FILES: Set[str] = {"thumbs.db", ".ds_store", "desktop.ini"}
JUNK_DIRS: Set[str] = {"__macosx"}


def human_size(bytes_val: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(bytes_val) < 1024.0:
            return f"{bytes_val:3.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} TB"


def inspect_archive(archive_path: pathlib.Path) -> Tuple[Dict[str, int], int]:
    ext_counts: Dict[str, int] = {}
    total_files = 0

    try:
        res = subprocess.run(
            ["7z", "l", "-slt", str(archive_path)],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception as e:
        CONSOLE.print(f"Error inspecting {archive_path.name}: {e}", style="logging.level.error")
        return {}, 0

    for line in res.stdout.splitlines():
        if line.startswith("Path = ") and not line.endswith(str(archive_path)):
            entry_path = line[7:].strip()
            ext = pathlib.Path(entry_path).suffix.lower()
            if ext:
                ext_counts[ext] = ext_counts.get(ext, 0) + 1
                total_files += 1

    return ext_counts, total_files


def is_already_webp(archive_path: pathlib.Path, ext_counts: Dict[str, int]) -> bool:
    if archive_path.suffix.lower() != ".cbz":
        return False

    image_exts = {ext for ext in ext_counts if ext in IMAGE_EXTENSIONS}
    if not image_exts:
        return False

    return image_exts == {".webp"}


def convert_image(src_file: pathlib.Path, dst_file: pathlib.Path, quality: int, lossless: bool) -> bool:
    dst_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["cwebp", "-quiet", "-m", "6", "-mt"]
    if lossless:
        cmd.append("-lossless")
    else:
        cmd.extend(["-q", str(quality)])
    cmd.extend([str(src_file.resolve()), "-o", str(dst_file.resolve())])

    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0 and dst_file.exists() and dst_file.stat().st_size > 0:
            src_file.unlink(missing_ok=True)
            return True
    except FileNotFoundError:
        pass

    if HAS_PILLOW:
        try:
            with Image.open(src_file) as im:
                if im.mode in ("P", "1"):
                    im = im.convert("RGBA" if "transparency" in im.info else "RGB")
                elif im.mode not in ("RGB", "RGBA"):
                    im = im.convert("RGB")
                im.save(dst_file, "WEBP", quality=quality, lossless=lossless, method=6)
            if dst_file.exists() and dst_file.stat().st_size > 0:
                src_file.unlink(missing_ok=True)
                return True
        except Exception:
            pass

    return False


def clean_clutter(root_path: pathlib.Path) -> None:
    for root, dirs, files in os.walk(root_path, topdown=False):
        for f in files:
            if f.lower() in JUNK_FILES or f.startswith("._"):
                (pathlib.Path(root) / f).unlink(missing_ok=True)
        for d in dirs:
            if d.lower() in JUNK_DIRS:
                shutil.rmtree(pathlib.Path(root) / d, ignore_errors=True)


def convert_archive(
    archive_path: pathlib.Path,
    quality: int = 80,
    lossless: bool = False,
    jobs: int = 4,
    force: bool = False,
    dry_run: bool = False,
) -> Tuple[str, int, int]:
    orig_size = archive_path.stat().st_size

    ext_counts, _ = inspect_archive(archive_path)
    if not ext_counts:
        return "FAILED", orig_size, orig_size

    if not force and is_already_webp(archive_path, ext_counts):
        return "SKIPPED", orig_size, orig_size

    if dry_run:
        return "DRY_RUN", orig_size, orig_size

    with tempfile.TemporaryDirectory(prefix="perdoo_webp_") as tmp_dir:
        extract_dir = pathlib.Path(tmp_dir) / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            subprocess.run(
                ["7z", "x", f"-o{extract_dir.resolve()}", "-y", str(archive_path.resolve())],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        except subprocess.CalledProcessError:
            CONSOLE.print(f"Failed to extract {archive_path.name}", style="logging.level.error")
            return "FAILED", orig_size, orig_size

        clean_clutter(extract_dir)

        tasks: List[Tuple[pathlib.Path, pathlib.Path]] = []
        for root, _, files in os.walk(extract_dir):
            for file_name in files:
                file_path = pathlib.Path(root) / file_name
                ext = file_path.suffix.lower()
                if ext in CONVERTIBLE_EXTENSIONS or (force and ext == ".webp"):
                    target_webp = file_path.with_suffix(".webp")
                    tasks.append((file_path, target_webp))

        if tasks:
            with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
                futures = [
                    executor.submit(convert_image, src, dst, quality, lossless)
                    for src, dst in tasks
                ]
                concurrent.futures.wait(futures)

        for root, _, files in os.walk(extract_dir):
            for file_name in files:
                file_path = pathlib.Path(root) / file_name
                if file_path.suffix.lower() in CONVERTIBLE_EXTENSIONS:
                    file_path.unlink(missing_ok=True)

        temp_cbz = pathlib.Path(tmp_dir) / f"packed_{archive_path.stem}.cbz"
        cmd = [
            "7z",
            "a",
            "-tzip",
            "-mx=9",
            str(temp_cbz.resolve()),
            ".",
        ]
        try:
            subprocess.run(
                cmd,
                cwd=str(extract_dir.resolve()),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        except subprocess.CalledProcessError:
            CONSOLE.print(f"Failed to pack CBZ for {archive_path.name}", style="logging.level.error")
            return "FAILED", orig_size, orig_size

        try:
            subprocess.run(
                ["7z", "t", str(temp_cbz.resolve())],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        except subprocess.CalledProcessError:
            CONSOLE.print(f"Integrity check failed for {archive_path.name}", style="logging.level.error")
            return "FAILED", orig_size, orig_size

        final_cbz = archive_path.with_suffix(".cbz")
        new_size = temp_cbz.stat().st_size

        if archive_path.resolve() != final_cbz.resolve() and archive_path.exists():
            archive_path.unlink(missing_ok=True)

        shutil.move(str(temp_cbz), str(final_cbz))
        return "CONVERTED", orig_size, new_size


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "webp",
        help="Convert images within comic archives to WebP format.",
        description="Batch compress comic archive images to WebP, skipping archives already converted.",
        formatter_class=RichHelpFormatter,
    )
    parser.add_argument(
        "target",
        type=existing_file_or_directory,
        help="Comic archive or directory of comic archives to convert to WebP.",
    )
    parser.add_argument(
        "-q",
        "--quality",
        type=int,
        default=None,
        help="WebP compression quality (0-100). Defaults to output.webp-quality in settings (80).",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=None,
        help="Number of parallel worker threads per comic. Defaults to output.webp-jobs in settings.",
    )
    parser.add_argument(
        "--lossless",
        action="store_true",
        default=None,
        help="Use lossless WebP compression.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force re-conversion even if archive is already WebP.",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Scan archives and display what would be converted without modifying files.",
    )
    parser.set_defaults(func=run)


def run(args: Namespace) -> None:
    settings = Settings.load().save()
    quality = args.quality if getattr(args, "quality", None) is not None else settings.output.webp_quality
    jobs = args.jobs if getattr(args, "jobs", None) is not None else settings.output.webp_jobs
    lossless = args.lossless if getattr(args, "lossless", None) is not None else settings.output.webp_lossless
    force = getattr(args, "force", False)
    dry_run = getattr(args, "dry_run", False)

    files = list_files(args.target) if args.target.is_dir() else [args.target]
    comic_files = [x for x in files if x.suffix.lower() in COMIC_EXTENSIONS]

    if not comic_files:
        CONSOLE.print("No comic archives found to process.", style="logging.level.warning")
        return

    table = Table(title="WebP Conversion Results", header_style="bold magenta")
    table.add_column("Archive", style="dim", overflow="fold")
    table.add_column("Status", justify="center")
    table.add_column("Original", justify="right")
    table.add_column("New Size", justify="right")
    table.add_column("Reduction", justify="right")

    stats = {
        "SKIPPED": 0,
        "CONVERTED": 0,
        "FAILED": 0,
        "DRY_RUN": 0,
        "orig_bytes": 0,
        "new_bytes": 0,
    }

    start_time = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=CONSOLE,
        transient=True,
    ) as progress:
        task = progress.add_task("Converting comics to WebP...", total=len(comic_files))
        for item in comic_files:
            progress.update(task, description=f"WebP: [cyan]{item.name[:40]}[/cyan]")
            status, orig_b, new_b = convert_archive(
                item,
                quality=quality,
                lossless=lossless,
                jobs=jobs,
                force=force,
                dry_run=dry_run,
            )

            stats[status] = stats.get(status, 0) + 1
            stats["orig_bytes"] += orig_b
            stats["new_bytes"] += new_b

            if status == "SKIPPED":
                table.add_row(item.name, "[green]Already WebP[/green]", human_size(orig_b), "-", "-")
            elif status == "CONVERTED":
                saved = orig_b - new_b
                pct = (saved / orig_b * 100) if orig_b > 0 else 0
                table.add_row(
                    item.name,
                    "[bold green]Converted[/bold green]",
                    human_size(orig_b),
                    human_size(new_b),
                    f"[cyan]-{pct:.1f}%[/cyan]",
                )
            elif status == "DRY_RUN":
                table.add_row(item.name, "[yellow]Needs Conversion[/yellow]", human_size(orig_b), "-", "-")
            else:
                table.add_row(item.name, "[bold red]Failed[/bold red]", human_size(orig_b), "-", "-")

            progress.advance(task)

    CONSOLE.print(table)
    elapsed = time.time() - start_time
    total_saved = stats["orig_bytes"] - stats["new_bytes"]
    overall_pct = (total_saved / stats["orig_bytes"] * 100) if stats["orig_bytes"] > 0 else 0

    CONSOLE.print(f"[bold]Processed:[/bold] {len(comic_files)} | [green]Converted:[/green] {stats['CONVERTED']} | [dim]Already WebP:[/dim] {stats['SKIPPED']} | [bold green]Saved:[/bold green] {human_size(total_saved)} (-{overall_pct:.1f}%) in {elapsed:.1f}s")
