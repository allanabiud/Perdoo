import pytest
from shortbox.metadata.metron_info import Format

from perdoo import format_resolver
from perdoo.format_resolver import detect_format_from_description, resolve_series_format


class TestDetectFormatFromDescription:
    """Ported Mylar3 deck/description detection cases plus fork extensions."""

    @pytest.mark.parametrize(
        ("volume_summary", "issue_summary", "expected"),
        [
            ("Now available in trade paperback", None, (Format.TRADE_PAPERBACK, "TPB")),
            ("Collected in hardcover for the first time", None, (Format.HARDCOVER, "HC")),
            ("An oversized omnibus edition", None, (Format.OMNIBUS, "OB")),
            ("The Walking Dead Compendium", None, (Format.OMNIBUS, "OB")),
            ("A standalone one-shot special", None, (Format.ONE_SHOT, "One-Shot")),
            ("Now in print", None, (None, None)),
            ("", None, (None, None)),
            (None, "A digital-first", (Format.DIGITAL_CHAPTER, "Digital")),
        ],
        ids=[
            "deck-tpb",
            "deck-hc",
            "deck-omnibus",
            "deck-compendium",
            "deck-one-shot",
            "deck-print-is-neutral",
            "deck-empty",
            "issue-deck-digital",
        ],
    )
    def test_deck_is_checked_as_whole_text(
        self,
        volume_summary: str | None,
        issue_summary: str | None,
        expected: tuple[Format | None, str | None],
    ) -> None:
        assert (
            detect_format_from_description(
                volume_summary=volume_summary, issue_summary=issue_summary
            )
            == expected
        )

    @pytest.mark.parametrize(
        ("volume_description", "expected"),
        [
            ("<p>Trade paperback collecting Batman #1-6.</p>", (Format.TRADE_PAPERBACK, "TPB")),
            ("Hardcover collecting the entire saga in one volume.", (Format.HARDCOVER, "HC")),
            ("Collects the first twelve issues of the series.", (Format.TRADE_PAPERBACK, "TPB")),
            ("This omnibus collects thirty years of adventures.", (Format.OMNIBUS, "OB")),
            ("The official compendium collects issues 1-100.", (Format.OMNIBUS, "OB")),
            ("Superman Birthright: The Deluxe Edition.", (Format.HARDCOVER, "HC")),
            ("The digital-first adventures of the hero.", (Format.DIGITAL_CHAPTER, "Digital")),
            ("A one-shot tale set before the main event.", (Format.ONE_SHOT, "One-Shot")),
        ],
        ids=[
            "html-tpb-collecting",
            "hc-collecting",
            "collects-head",
            "omnibus-beats-collects",
            "compendium",
            "deluxe",
            "digital",
            "one-shot",
        ],
    )
    def test_description_uses_first_60_characters(
        self, volume_description: str, expected: tuple[Format | None, str | None]
    ) -> None:
        assert detect_format_from_description(volume_description=volume_description) == expected

    @pytest.mark.parametrize(
        "volume_description",
        [
            pytest.param(
                "This story is collected; a hardcover can be found at your local shop.",
                id="negative-hardcover-can-be-found",
            ),
            pytest.param(
                "A trade paperback can be found wherever books are sold.",
                id="negative-paperback-can-be-found",
            ),
            pytest.param(
                "Following the one-shot, the series continued into volume two.",
                id="negative-one-shot-avoid-word",
            ),
            pytest.param("Batman fights crime in Gotham City.", id="no-descriptor"),
        ],
    )
    def test_negative_phrases_reject_false_positives(self, volume_description: str) -> None:
        assert detect_format_from_description(volume_description=volume_description) == (None, None)

    def test_volume_texts_are_checked_before_issue_texts(self) -> None:
        assert detect_format_from_description(
            volume_summary=None,
            volume_description="Batman fights crime.",
            issue_description="Hardcover collecting the early years.",
        ) == (Format.HARDCOVER, "HC")

    def test_deck_of_volume_beats_description_of_volume(self) -> None:
        assert detect_format_from_description(
            volume_summary="Now in hardcover",
            volume_description="Trade paperback collecting Batman #1-6.",
        ) == (Format.HARDCOVER, "HC")

    def test_no_texts_returns_none(self) -> None:
        assert detect_format_from_description() == (None, None)


class TestResolveSeriesFormat:
    """Priority: CLI > existing metadata > filename > service > One-Shot rule."""

    def test_cli_flag_beats_everything(self) -> None:
        assert resolve_series_format(
            series_name="Batman",
            filename="Batman [TPB] #001 (2012).cbz",
            cli_format="HC",
            existing_format_comic="TPB",
            fetched_format_comic="Omnibus",
            prompt_if_missing=False,
        ) == (Format.HARDCOVER, "HC")

    def test_existing_metron_format_beats_filename(self) -> None:
        assert resolve_series_format(
            series_name="Batman",
            filename="Batman [TPB] #001 (2012).cbz",
            existing_format_metron=Format.HARDCOVER,
            prompt_if_missing=False,
        ) == (Format.HARDCOVER, "Hardcover")

    def test_existing_comic_format_beats_fetched(self) -> None:
        assert resolve_series_format(
            series_name="Batman",
            filename="Batman #001 (2012).cbz",
            existing_format_comic="HC",
            fetched_format_comic="TPB",
            prompt_if_missing=False,
        ) == (Format.HARDCOVER, "HC")

    def test_filename_tag_beats_fetched_description_format(self) -> None:
        assert resolve_series_format(
            series_name="Watchmen",
            filename="/comics/Watchmen (1987) [TPB]/Watchmen #001 (1987).cbz",
            fetched_format_comic="Hardcover",
            prompt_if_missing=False,
        ) == (Format.TRADE_PAPERBACK, "TPB")

    def test_full_path_uses_parent_folder_tag(self) -> None:
        assert resolve_series_format(
            series_name="Watchmen",
            filename="/comics/Watchmen (1987) [TPB]/Watchmen #001 (1987).cbz",
            prompt_if_missing=False,
        ) == (Format.TRADE_PAPERBACK, "TPB")

    def test_fetched_format_fills_the_gap_when_filename_is_silent(self) -> None:
        assert resolve_series_format(
            series_name="Watchmen",
            filename="Watchmen #001 (1987).cbz",
            fetched_format_comic="Hardcover",
            prompt_if_missing=False,
        ) == (Format.HARDCOVER, "HC")

    def test_fetched_metron_enum_beats_fetched_comic_string(self) -> None:
        assert resolve_series_format(
            series_name="Batman",
            filename="Batman #001 (2012).cbz",
            fetched_format_comic="Trade Paperback",
            fetched_format_metron=Format.OMNIBUS,
            prompt_if_missing=False,
        ) == (Format.OMNIBUS, "Omnibus")

    def test_single_issue_metron_format_is_ignored(self) -> None:
        assert resolve_series_format(
            series_name="Batman",
            filename="Batman #001 (2012).cbz",
            fetched_format_metron=Format.SINGLE_ISSUE,
            prompt_if_missing=False,
        ) == (None, None)

    def test_one_shot_rule_applies_when_nothing_is_known(self) -> None:
        assert resolve_series_format(
            series_name="Batman of Two Worlds",
            filename="Batman of Two Worlds #001 (2026).cbz",
            force_one_shot=True,
            prompt_if_missing=False,
        ) == (Format.ONE_SHOT, "One-Shot")

    def test_one_shot_rule_loses_to_fetched_format(self) -> None:
        assert resolve_series_format(
            series_name="Batman",
            filename="Batman #001 (2012).cbz",
            fetched_format_comic="TPB",
            force_one_shot=True,
            prompt_if_missing=False,
        ) == (Format.TRADE_PAPERBACK, "TPB")

    def test_one_shot_rule_loses_to_filename_tag(self) -> None:
        assert resolve_series_format(
            series_name="Batman",
            filename="Batman [TPB] #001 (2012).cbz",
            force_one_shot=True,
            prompt_if_missing=False,
        ) == (Format.TRADE_PAPERBACK, "TPB")

    def test_returns_none_when_nothing_is_known(self) -> None:
        assert resolve_series_format(
            series_name="Batman", filename="Batman #001 (2012).cbz", prompt_if_missing=False
        ) == (None, None)

    def test_filename_guess_is_confirmed_by_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def choose_one_shot(_label: str, default_short: str | None = None) -> tuple[Format, str]:
            assert default_short == "TPB"
            return Format.ONE_SHOT, "One-Shot"

        monkeypatch.setattr(format_resolver, "prompt_format_selection", choose_one_shot)
        assert resolve_series_format(
            series_name="Batman", filename="Batman [TPB] #001 (2012).cbz", prompt_if_missing=True
        ) == (Format.ONE_SHOT, "One-Shot")

    def test_fetched_format_is_applied_without_prompting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail(*_args: object, **_kwargs: object) -> tuple[None, None]:
            raise AssertionError("prompt must not fire for a service-fetched format")

        monkeypatch.setattr(format_resolver, "prompt_format_selection", fail)
        assert resolve_series_format(
            series_name="Watchmen",
            filename="Watchmen #001 (1987).cbz",
            fetched_format_comic="Hardcover",
            prompt_if_missing=True,
        ) == (Format.HARDCOVER, "HC")

    def test_unknown_format_string_is_passed_through(self) -> None:
        assert resolve_series_format(
            series_name="Batman",
            filename="Batman #001 (2012).cbz",
            fetched_format_comic="Absolute",
            prompt_if_missing=False,
        ) == (None, "Absolute")
