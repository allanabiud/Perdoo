__all__ = ["register"]

from argparse import Namespace, _SubParsersAction
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from rich_argparse import HelpPreviewAction
from shortbox import Comic
from shortbox.errors import ArchiveCapabilityError, MetadataValidationError, UnsupportedArchiveError
from shortbox.metadata import ComicInfo, MetronInfo
from shortbox.metadata.comic_info import AgeRating as ComicInfoAgeRating, Page, PageType
from shortbox.metadata.metron_info import (
    AgeRating as MetronInfoAgeRating,
    Format,
    InformationSource,
)

from perdoo.cli._results import RunResult
from perdoo.cli._utils import ArchiveType, RichHelpFormatter, enum_arg, existing_file_or_directory
from perdoo.console import CONSOLE
from perdoo.format_resolver import apply_format_to_metadata, parse_format_str
from perdoo.local import build_local_metadata, parse_local_filename, prompt_format_override
from perdoo.pages import update_comic_pages_metadata
from perdoo.services import Comicvine, Metron, Search, Service
from perdoo.services._models import get_comic_info_note_id, get_comic_info_note_modified
from perdoo.settings import Service as ServiceOption, Services, Settings
from perdoo.utils import list_files


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "sync",
        help="Fetch metadata for comic archives from configured services.",
        description="Fetch metadata from configured services and store it in comic archives.",
        formatter_class=RichHelpFormatter,
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
        "-o",
        "--override-cv-format",
        action="store_true",
        help="Override the format provided by Comicvine via an interactive prompt.",
    )
    parser.add_argument(
        "-l",
        "--local",
        action="store_true",
        help="Organize without online services: parse metadata from the filename only.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and resolve metadata without writing archives.",
    )
    parser.add_argument(
        "--generate-help-preview", action=HelpPreviewAction, path="docs/img/perdoo_sync.svg"
    )
    parser.set_defaults(func=run)


def build_services(
    services: Services, cover_hash_distance: int, override_cv_format: bool = False
) -> Sequence[Service]:
    tmp = {}
    if services.comicvine.api_key:
        tmp[ServiceOption.COMICVINE] = Comicvine(
            api_key=services.comicvine.api_key, override_format=override_cv_format
        )
    if services.metron.token:
        tmp[ServiceOption.METRON] = Metron(
            token=services.metron.token, cover_hash_distance=cover_hash_distance
        )
    return [tmp[k] for k in services.order if k in tmp]


def should_sync(metron_info: MetronInfo | None, comic_info: ComicInfo | None, days: int) -> bool:
    last_modified = metron_info.last_modified if metron_info else None
    last_modified = last_modified or get_comic_info_note_modified(
        comic_info.notes if comic_info else None
    )
    if last_modified:
        age = (datetime.now().astimezone().date() - last_modified.date()).days
        return age >= days
    return True


def sync_comic(
    comic: Comic,
    services: Sequence[Service],
    days: int,
    force: bool = False,
    handle_pages: bool = True,
    image_extensions: Sequence[str] = (".png", ".jpg", ".jpeg", ".webp", ".jxl"),
    series_cache: dict[tuple[int, int | None, str | None], object | None] | None = None,
    dry_run: bool = False,
    local: bool = False,
    override_cv_format: bool = False,
) -> str:
    try:
        metron_info = comic.get_metadata(MetronInfo)
    except MetadataValidationError as err:
        CONSOLE.print(str(err), style="logging.level.error")
        metron_info = None
    try:
        comic_info = comic.get_metadata(ComicInfo)
    except MetadataValidationError as err:
        CONSOLE.print(str(err), style="logging.level.error")
        comic_info = None

    # Local mode: build metadata from the filename without online services.
    if local:
        parsed = parse_local_filename(comic.file)
        if not parsed.get("series"):
            CONSOLE.print(
                f"'{comic.file.name}' could not be parsed for local mode; "
                "use a filename like 'Series #001 (2026).cbz'.",
                style="logging.level.error",
            )
            return "skipped"

        format_override = None
        if override_cv_format:
            format_override = prompt_format_override(comic.file.name)

        comic_info, metron_info = build_local_metadata(
            comic_file=comic.file, parsed=parsed, format_override=format_override
        )

        if not dry_run:
            with CONSOLE.status("Writing local metadata to archive"):
                comic.set_metadata(comic_info)
                comic.set_metadata(metron_info)
        CONSOLE.print(
            f"Local metadata built for '{comic.file.name}' from filename",
            style="logging.level.success",
        )
        return "synced"

    if not should_sync(metron_info=metron_info, comic_info=comic_info, days=days) and not force:
        CONSOLE.print(
            f"'{comic.file.name}' was synced within the last {days} days; skipping. Pass -f / --force to re-sync.",
            style="dim",
        )
        return "skipped"
    query = Search.build(comic=comic)
    try:
        found = False
        for svc in services:
            if result := svc.fetch(search=query):
                found = True
                if handle_pages:
                    update_comic_pages_metadata(
                        comic=comic,
                        comic_info=result.comic_info,
                        metron_info=result.metron_info,
                        image_extensions=image_extensions,
                    )

                # Hybrid enrichment: If format is missing and another service (e.g. Metron) is available
                if not (result.comic_info and result.comic_info.format) and not (
                    result.metron_info
                    and result.metron_info.series
                    and result.metron_info.series.format
                    and result.metron_info.series.format != Format.SINGLE_ISSUE
                ):
                    for other_svc in services:
                        if other_svc is not svc and hasattr(other_svc, "session"):
                            try:
                                cv_id = getattr(query.series, "comicvine", None)
                                m_series = None
                                cache_key = (id(other_svc), cv_id, query.series.name)
                                if series_cache is not None and cache_key in series_cache:
                                    m_series = series_cache[cache_key]
                                if cv_id and hasattr(other_svc.session, "series_list"):
                                    if m_series is None:
                                        session = cast("Any", other_svc.session)
                                        m_series_list = session.series_list(
                                            params={"cv_id": cv_id}
                                        )
                                        if m_series_list:
                                            m_series = m_series_list[0]
                                if (
                                    not m_series
                                    and query.series.name
                                    and hasattr(other_svc.session, "series_list")
                                ) and (series_cache is None or cache_key not in series_cache):
                                    session = cast("Any", other_svc.session)
                                    m_series_list = session.series_list(
                                        params={"name": query.series.name}
                                    )
                                    if m_series_list:
                                        m_series = m_series_list[0]
                                if series_cache is not None:
                                    series_cache[cache_key] = m_series
                                if m_series and getattr(m_series, "series_type", None):
                                    series = cast("Any", m_series)
                                    fmt_enum, fmt_short = parse_format_str(
                                        series.series_type.name
                                    )
                                    if fmt_enum or fmt_short:
                                        apply_format_to_metadata(
                                            result.comic_info,
                                            result.metron_info,
                                            fmt_enum,
                                            fmt_short,
                                        )
                                        break
                            except Exception:
                                pass

                # Merge with existing metadata to preserve user-customized fields
                _merge_comic_info(comic_info, result.comic_info)
                _merge_metron_info(metron_info, result.metron_info)

                if not dry_run and (
                    comic_info is None or result.comic_info != comic_info
                ):
                    with CONSOLE.status("Writing ComicInfo.xml to archive"):
                        comic.set_metadata(result.comic_info)
                if not dry_run and (
                    metron_info is None or result.metron_info != metron_info
                ):
                    with CONSOLE.status("Writing MetronInfo.xml to archive"):
                        comic.set_metadata(result.metron_info)
                break
        if not found:
            CONSOLE.print(
                f"No metadata found for '{comic.file.name}'", style="logging.level.warning"
            )
            return "skipped"
        return "synced"
    except ArchiveCapabilityError as err:
        CONSOLE.print(
            f"{err}: Consider converting to another format first", style="logging.level.warning"
        )
        return "skipped"


def _merge_comic_info(existing: ComicInfo | None, fetched: ComicInfo) -> None:
    """Preserve user-customized ComicInfo fields that the service did not populate."""
    if existing is None:
        return

    # Language: services rarely set this, preserve existing
    if not fetched.language_iso and existing.language_iso:
        fetched.language_iso = existing.language_iso

    # Age rating: preserve existing when fetched is UNKNOWN
    if (
        fetched.age_rating == ComicInfoAgeRating.UNKNOWN
        and existing.age_rating != ComicInfoAgeRating.UNKNOWN
    ):
        fetched.age_rating = existing.age_rating

    # Format: preserve existing when fetched is empty, normalising legacy
    # short codes ("TPB") to the full name ("Trade Paperback")
    if not fetched.format and existing.format:
        fmt_enum, fmt_short = parse_format_str(existing.format)
        fetched.format = fmt_enum.value if fmt_enum else (fmt_short or existing.format)

    # Scan information: preserve existing
    if not fetched.scan_information and existing.scan_information:
        fetched.scan_information = existing.scan_information

    # Notes: merge - keep the fetched service ID tag but also preserve any existing notes content
    if existing.notes and fetched.notes:
        for source in (InformationSource.COMIC_VINE, InformationSource.METRON):
            if get_comic_info_note_id(existing.notes, source) == get_comic_info_note_id(
                fetched.notes, source
            ) and get_comic_info_note_id(existing.notes, source) is not None:
                fetched.notes = existing.notes
                break
        if fetched.notes not in existing.notes:
            fetched.notes = f"{existing.notes}\n{fetched.notes}"
        # else fetched notes are already contained in existing, use fetched as-is (fresher ID)
    elif existing.notes and not fetched.notes:
        fetched.notes = existing.notes

    # Pages: preserve bookmarks and specific page types from existing metadata
    if existing.pages and fetched.pages:
        existing_by_idx: dict[int, Page] = {
            p.image: p for p in existing.pages if p.image is not None
        }
        for page in fetched.pages:
            if page.image is None:
                continue
            old = existing_by_idx.get(page.image)
            if old is None:
                continue
            # Preserve bookmark annotations
            if old.bookmark and not page.bookmark:
                page.bookmark = old.bookmark
            # Preserve specific page types when fetched has only generic Story type
            if (
                old.type is not None
                and old.type != PageType.STORY
                and (page.type is None or page.type == PageType.STORY)
            ):
                page.type = old.type
    elif existing.pages and not fetched.pages:
        fetched.pages = existing.pages


def _merge_metron_info(existing: MetronInfo | None, fetched: MetronInfo) -> None:
    """Preserve user-customized MetronInfo fields that the service did not populate."""
    if existing is None:
        return

    # Age rating: preserve existing when fetched is UNKNOWN
    if (
        fetched.age_rating == MetronInfoAgeRating.UNKNOWN
        and existing.age_rating != MetronInfoAgeRating.UNKNOWN
    ):
        fetched.age_rating = existing.age_rating

    # URLs: merge, dedup by value
    if existing.urls:
        existing_url_values = {u.value for u in fetched.urls}
        for url in existing.urls:
            if url.value not in existing_url_values:
                fetched.urls.append(url)


def run(args: Namespace) -> RunResult:
    settings = Settings.load().save()
    result = RunResult(stage="sync")
    services = build_services(
        services=settings.services,
        cover_hash_distance=settings.sync.cover_hash_distance,
        override_cv_format=args.override_cv_format,
    )
    if not services and not args.local:
        CONSOLE.print("No services configured", style="logging.level.error")
        return result

    files = list_files(args.target) if args.target.is_dir() else [args.target]
    if getattr(args, "resume_paths", None):
        files = [file for file in files if file.resolve() in args.resume_paths]
    if args.ignore:
        ignore_ext = [f".{x}" for x in args.ignore]
        files = [x for x in files if x.suffix not in ignore_ext]

    series_cache: dict[tuple[int, int | None, str | None], object | None] = {}
    for entry in files:
        result.processed += 1
        try:
            with Comic.open(file=entry) as comic:
                status = sync_comic(
                    comic=comic,
                    services=services,
                    days=settings.sync.days,
                    force=args.force,
                    handle_pages=settings.output.comic_info.handle_pages,
                    image_extensions=settings.output.image_extensions,
                    series_cache=series_cache,
                    dry_run=getattr(args, "dry_run", False),
                    local=args.local,
                    override_cv_format=args.override_cv_format,
                )
                if status == "synced":
                    result.succeeded += 1
                else:
                    result.skipped += 1
        except UnsupportedArchiveError:
            result.skipped += 1
        except Exception as err:  # noqa: BLE001
            result.add_failure(entry, err)
            CONSOLE.print(
                f"Failed to sync [cyan]{entry.name}[/cyan]: {err}",
                style="logging.level.error",
            )
    return result
