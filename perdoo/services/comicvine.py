__all__ = ["Comicvine"]

import re
import time
from collections.abc import Callable
from datetime import datetime
from functools import wraps
from typing import TypeVar

from natsort import humansorted, ns
from questionary import Choice, confirm, text
from shortbox.metadata import ComicInfo, MetronInfo
from shortbox.metadata.metron_info import InformationSource
from simyan.comicvine import Comicvine as Simyan
from simyan.errors import ServiceError
from simyan.schemas.issue import Issue
from simyan.schemas.volume import Volume

from perdoo import get_cache_home
from perdoo.console import CONSOLE
from perdoo.format_resolver import apply_format_to_metadata, detect_format_from_description
from perdoo.services._base import prompt_select
from perdoo.services._models import (
    IssueSearch,
    MetadataResult,
    Search,
    SeriesSearch,
    set_comic_info_note_id,
)

T = TypeVar("T")

_RATE_LIMIT_PATTERNS = re.compile(r"420|429|rate.?limit|too many requests", re.IGNORECASE)


def comicvine_rate_limit_retry(
    max_retries: int = 5, initial_wait: float = 10.0
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry decorator for ComicVine API calls that hit rate limits.

    Catches :class:`ServiceError` whose message indicates a rate-limit response
    (HTTP 420/429 or ``"rate limit"`` / ``"too many requests"``) and retries with
    exponential backoff.  Non-rate-limit ``ServiceError``s are re-raised immediately
    so they can be handled by the existing per-method error handling.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:  # noqa: ANN002, ANN003
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except ServiceError as err:
                    if not _RATE_LIMIT_PATTERNS.search(str(err)):
                        raise
                    if attempt == max_retries - 1:
                        raise
                    wait = initial_wait * (2**attempt)
                    CONSOLE.print(
                        f"Comicvine rate limited, waiting {wait:.0f} seconds "
                        f"(attempt {attempt + 1}/{max_retries})...",
                        style="logging.level.warning",
                    )
                    time.sleep(wait)
            raise AssertionError("Unreachable")

        return wrapper

    return decorator


ROLE_NORMALIZATION: dict[str, str] = {
    "writer": "Writer",
    "script": "Writer",
    "story": "Writer",
    "plot": "Writer",
    "penciler": "Penciller",
    "penciller": "Penciller",
    "pencils": "Penciller",
    "artist": "Penciller",
    "art": "Penciller",
    "illustrator": "Penciller",
    "inker": "Inker",
    "inks": "Inker",
    "finishes": "Inker",
    "colorist": "Colorist",
    "colors": "Colorist",
    "colourist": "Colorist",
    "colours": "Colorist",
    "letterer": "Letterer",
    "letters": "Letterer",
    "cover": "Cover Artist",
    "cover artist": "Cover Artist",
    "covers": "Cover Artist",
    "variant cover": "Cover Artist",
    "editor": "Editor",
    "assistant editor": "Editor",
    "associate editor": "Editor",
    "group editor": "Editor",
    "managing editor": "Editor",
    "senior editor": "Editor",
}


class Comicvine:
    def __init__(self, api_key: str):
        self.session = Simyan(
            api_key=api_key,
            cache_path=get_cache_home() / "simyan.sqlite",
            ratelimit_path=get_cache_home() / "simyan-rates.sqlite",
        )

    @comicvine_rate_limit_retry()
    def _search_series(
        self, name: str | None, volume: int | None, year: int | None, filename: str
    ) -> int | None:
        name = name or text(message="Volume Name").ask()
        try:
            options = sorted(
                self.session.list_volumes({"filter": f"name:{name}"}),
                key=lambda x: (
                    x.publisher.name if x.publisher and x.publisher.name else "",
                    x.name,
                    x.start_year or 0,
                ),
            )
            if year:
                year_options = [x for x in options if x.start_year == year]
                if year_options:
                    options = year_options

            # Two-pass fallback: if no volume matches exact name with subtitles (e.g. "Batman: Court of Owls"), try base title
            if not options and (":" in name or " - " in name or " Vol" in name):
                base_name = re.split(r"[:\-]|\bVol\b|\bVolume\b", name, maxsplit=1)[0].strip()
                if base_name and base_name.lower() != name.lower():
                    clean_options = sorted(
                        self.session.list_volumes({"filter": f"name:{base_name}"}),
                        key=lambda x: (
                            x.publisher.name if x.publisher and x.publisher.name else "",
                            x.name,
                            x.start_year or 0,
                        ),
                    )
                    if year:
                        clean_year = [x for x in clean_options if x.start_year == year]
                        options = clean_year or clean_options
                    else:
                        options = clean_options
            if options:
                search = name
                if volume:
                    search += f" v{volume}"
                if year:
                    search += f" ({year})"
                choices = [
                    Choice(
                        title=[
                            (
                                "class:dim",
                                f"{x.id} | {x.publisher.name if x.publisher and x.publisher.name else ''} | ",  # noqa: E501
                            ),
                            ("class:title", f"{x.name} ({x.start_year})"),
                        ],
                        description=f"https://comicvine.gamespot.com/volumes/4050-{x.id}",
                        value=x,
                    )
                    for x in options
                ]
                selected = prompt_select(
                    message=f"Searching Comicvine for Volumes matching '{filename}'"
                    if not year
                    else f"Searching Comicvine for Volume '{search}'",
                    choices=choices,
                )
                if selected:
                    return selected.id
            else:
                CONSOLE.print(
                    f"Unable to find any Volumes on Comicvine for the file: {filename!r}",
                    style="logging.level.warning",
                )
            if year:
                CONSOLE.print("Searching again without the StartYear", style="logging.level.info")
                return self._search_series(name=name, volume=volume, year=None, filename=filename)
            if confirm(message="Search Again", default=False).ask():
                return self._search_series(name=None, volume=None, year=None, filename=filename)
        except ServiceError as err:
            CONSOLE.print(err, style="logging.level.error")
        return None

    @comicvine_rate_limit_retry()
    def _fetch_series(self, search: SeriesSearch, filename: str) -> Volume | None:
        series_id = search.comicvine or self._search_series(
            name=search.name, volume=search.volume, year=search.year, filename=filename
        )
        if not series_id:
            return None
        try:
            series = self.session.get_volume(volume_id=series_id)
            search.comicvine = series_id
            return series
        except ServiceError as err:
            CONSOLE.print(err, style="logging.level.error")
        if search.comicvine:
            search.comicvine = None
            return self._fetch_series(search=search, filename=filename)
        return None

    @comicvine_rate_limit_retry()
    def _search_issue(self, series_id: int, number: str | None, filename: str) -> int | None:
        try:
            options = humansorted(
                self.session.list_issues(
                    {"filter": f"volume:{series_id},issue_number:{number}"}
                    if number
                    else {"filter": f"volume:{series_id}"}
                ),
                key=lambda x: (x.number, x.name),
                alg=ns.NA | ns.G,
            )
            if options:
                choices = [
                    Choice(
                        title=[
                            ("class:dim", f"{x.id} | "),
                            ("class:title", f"{x.number} - {x.name or ''}"),
                        ],
                        description=f"https://comicvine.gamespot.com/issues/4000-{x.id}",
                        value=x,
                    )
                    for x in options
                ]
                selected = prompt_select(
                    message=f"Searching Comicvine for Issues matching {filename!r}"
                    if not number
                    else f"Searching Comicvine for Issues with number {number!r}",
                    choices=choices,
                )
                if selected:
                    return selected.id
            else:
                CONSOLE.print(
                    f"Unable to find any Issues on Comicvine for the file: {filename!r}",
                    style="logging.level.warning",
                )
            if number:
                CONSOLE.print("Searching again without the IssueNumber", style="logging.level.info")
                return self._search_issue(series_id=series_id, number=None, filename=filename)
        except ServiceError as err:
            CONSOLE.print(err, style="logging.level.error")
        return None

    @comicvine_rate_limit_retry()
    def _fetch_issue(self, series_id: int, search: IssueSearch, filename: str) -> Issue | None:
        issue_id = search.comicvine or self._search_issue(
            series_id=series_id, number=search.number, filename=filename
        )
        if not issue_id:
            return None
        try:
            issue = self.session.get_issue(issue_id=issue_id)
            search.comicvine = issue_id
            return issue
        except ServiceError as err:
            CONSOLE.print(err, style="logging.level.error")
        if search.comicvine:
            search.comicvine = None
            return self._fetch_issue(series_id=series_id, search=search, filename=filename)
        return None

    def _build_metron_info(self, series: Volume, issue: Issue) -> MetronInfo:
        from shortbox.metadata.metron_info import (  # noqa: PLC0415
            Arc,
            Credit,
            Id,
            Publisher,
            Resource,
            Role,
            Series,
            Url,
        )

        def load_role(value: str) -> Role:
            normalized = ROLE_NORMALIZATION.get(value.strip().lower(), value.strip())
            try:
                return Role.load(value=normalized)
            except ValueError:
                pass
            try:
                return Role.load(value=value.strip())
            except ValueError:
                return Role.OTHER

        return MetronInfo(
            ids=[Id(primary=True, source=InformationSource.COMIC_VINE, value=str(issue.id))],
            publisher=Publisher(id=str(series.publisher.id), name=series.publisher.name)
            if series.publisher and series.publisher.name
            else None,
            series=Series(
                id=str(series.id),
                name=series.name,
                start_year=series.start_year,
                alternative_names=[],
            ),
            collection_title=issue.name,
            number=issue.number,
            summary=issue.summary,
            cover_date=issue.cover_date,
            store_date=issue.store_date,
            arcs=[Arc(id=str(x.id), name=x.name) for x in issue.story_arcs if x.name],
            characters=[
                Resource[str](id=str(x.id), value=x.name) for x in issue.characters if x.name
            ],
            teams=[Resource[str](id=str(x.id), value=x.name) for x in issue.teams if x.name],
            locations=[
                Resource[str](id=str(x.id), value=x.name) for x in issue.locations if x.name
            ],
            urls=[Url(primary=True, value=str(issue.site_url))],
            credits=[
                Credit(
                    creator=Resource[str](id=str(x.id), value=x.name),
                    roles=[
                        Resource[Role](value=load_role(value=r.strip()))
                        for r in re.split(r"[~\r\n,]+", x.roles)
                        if r.strip()
                    ],
                )
                for x in issue.creators
                if x.name
            ],
            last_modified=datetime.now().astimezone(),
            genres=[],
            prices=[],
            reprints=[],
            stories=[],
            tags=[],
            universes=[],
        )

    def _build_comic_info(self, series: Volume, issue: Issue) -> ComicInfo:
        # Fallback to description if summary is missing
        summary = issue.summary
        if (not summary or len(summary.strip()) < 20) and getattr(issue, "description", None):
            clean_desc = re.sub(r"<[^>]+>", " ", issue.description)
            clean_desc = re.sub(r"\s+", " ", clean_desc).strip()
            summary = clean_desc or summary

        comic_info = ComicInfo(
            title=issue.name,
            series=series.name,
            number=issue.number,
            summary=summary,
            publisher=series.publisher.name if series.publisher else None,
            web=str(issue.site_url),
            pages=[],
        )

        if issue.cover_date:
            comic_info.cover_date = issue.cover_date
            comic_info.year = issue.cover_date.year
            comic_info.month = issue.cover_date.month
            comic_info.day = issue.cover_date.day
        elif issue.store_date:
            comic_info.year = issue.store_date.year
            comic_info.month = issue.store_date.month
            comic_info.day = issue.store_date.day

        if series.issue_count:
            comic_info.count = series.issue_count
        if series.start_year:
            comic_info.volume = series.start_year

        # Normalize creator roles so Penciller, Cover Artist, Inker, etc. are populated
        normalized_credits: dict[str, list[str]] = {}
        for x in issue.creators:
            if not x.name:
                continue
            raw_roles = [r.strip() for r in re.split(r"[~\r\n,]+", x.roles) if r.strip()]
            norm_roles = [ROLE_NORMALIZATION.get(r.lower(), r.title()) for r in raw_roles]
            normalized_credits[x.name] = norm_roles

        comic_info.credits = normalized_credits
        comic_info.character_list = [x.name for x in issue.characters if x.name]
        comic_info.team_list = [x.name for x in issue.teams if x.name]
        comic_info.location_list = [x.name for x in issue.locations if x.name]
        comic_info.story_arc_list = [x.name for x in issue.story_arcs if x.name]
        set_comic_info_note_id(comic_info, source=InformationSource.COMIC_VINE, value=issue.id)

        return comic_info

    @comicvine_rate_limit_retry()
    def fetch(self, search: Search) -> MetadataResult | None:
        if not search.series.comicvine and search.issue.comicvine:
            try:
                temp = self.session.get_issue(issue_id=search.issue.comicvine)
                search.series.comicvine = temp.volume.id
            except ServiceError:
                pass

        series = self._fetch_series(search=search.series, filename=search.filename)
        if not series:
            return None

        issue = self._fetch_issue(
            series_id=series.id, search=search.issue, filename=search.filename
        )
        if not issue:
            return None

        comic_info = self._build_comic_info(series=series, issue=issue)
        metron_info = self._build_metron_info(series=series, issue=issue)

        # Mylar3-style format detection: ComicVine stores no series format, so
        # recognise collected editions from descriptors in the description texts.
        fmt_enum, fmt_short = detect_format_from_description(
            volume_summary=series.summary,
            volume_description=series.description,
            issue_summary=issue.summary,
            issue_description=issue.description,
        )
        if fmt_enum or fmt_short:
            apply_format_to_metadata(
                comic_info=comic_info,
                metron_info=metron_info,
                fmt_enum=fmt_enum,
                fmt_short=fmt_short,
            )
            CONSOLE.print(
                f"Format {fmt_short} auto-detected for {series.name!r} "
                "from Comicvine description text",
                style="dim",
            )

        return MetadataResult(comic_info=comic_info, metron_info=metron_info)
