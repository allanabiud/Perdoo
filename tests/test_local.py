from pathlib import Path

import pytest
from shortbox.metadata import ComicInfo, MetronInfo
from shortbox.metadata.metron_info import Format

from perdoo.local import build_local_metadata, parse_local_filename


class TestParseLocalFilename:
    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("Batman #001 (2026).cbz", {"series": "Batman", "number": "001", "year": 2026}),
            ("Batman (2026) #001.cbz", {"series": "Batman", "number": "001", "year": 2026}),
            ("Batman #1.cbz", {"series": "Batman", "number": "1", "year": None}),
            ("Batman (2026).cbz", {"series": "Batman", "number": None, "year": 2026}),
            ("Amazing Spider-Man #700 (2012).cbz",
             {"series": "Amazing Spider-Man", "number": "700", "year": 2012}),
            ("Batman - 001 (2026).cbz", {"series": "Batman - 001", "number": None, "year": 2026}),
            ("random-file.cbz", {"series": None, "number": None, "year": None}),
        ],
        ids=[
            "hash-number-year",
            "year-hash-number",
            "hash-number-only",
            "year-only",
            "multi-word-series",
            "dash-separator",
            "no-match",
        ],
    )
    def test_parse_patterns(self, filename: str, expected: dict) -> None:
        result = parse_local_filename(Path(filename))
        assert result == expected


class TestBuildLocalMetadata:
    def test_builds_comic_info_and_metron_info(self) -> None:
        parsed = {"series": "Batman", "number": "001", "year": 2026}
        comic_info, metron_info = build_local_metadata(
            comic_file=Path("Batman #001 (2026).cbz"),
            parsed=parsed,
        )

        assert isinstance(comic_info, ComicInfo)
        assert isinstance(metron_info, MetronInfo)
        assert comic_info.series == "Batman"
        assert comic_info.number == "001"
        assert comic_info.year == 2026
        assert metron_info.series.name == "Batman"
        assert metron_info.number == "001"
        assert metron_info.series.start_year == 2026

    def test_format_override_applied(self) -> None:
        parsed = {"series": "Batman", "number": "001", "year": None}
        comic_info, metron_info = build_local_metadata(
            comic_file=Path("Batman #001.cbz"),
            parsed=parsed,
            format_override=Format.TRADE_PAPERBACK,
        )

        assert comic_info.format == "Trade Paperback"
        assert metron_info.series.format == Format.TRADE_PAPERBACK

    def test_falls_back_to_filename_stem(self) -> None:
        parsed = {"series": None, "number": "1", "year": None}
        comic_info, _ = build_local_metadata(
            comic_file=Path("Some Random Comic #1.cbz"),
            parsed=parsed,
        )

        assert comic_info.series == "Some Random Comic #1"
