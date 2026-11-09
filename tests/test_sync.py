from datetime import UTC, datetime, timezone
from types import SimpleNamespace

import pytest

from perdoo.cli import sync


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz: timezone | None = None) -> datetime:
        return datetime(2026, 9, 4, tzinfo=tz or UTC)


@pytest.fixture(autouse=True)
def freeze_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync, "datetime", FixedDatetime)


@pytest.mark.parametrize(
    ("last_modified", "days", "expected"),
    [
        (datetime(2026, 9, 4, tzinfo=UTC), 28, False),
        (datetime(2026, 8, 7, tzinfo=UTC), 28, True),
        (datetime(2026, 8, 8, tzinfo=UTC), 28, False),
    ],
    ids=["updated-today", "at-sync-threshold", "below-sync-threshold"],
)
def test_should_sync_uses_the_metron_last_modified_date(
    last_modified: datetime, days: int, expected: bool
) -> None:
    metron_info = SimpleNamespace(last_modified=last_modified)

    assert sync.should_sync(metron_info, None, days) is expected


def test_should_sync_uses_the_comic_info_note_when_metron_info_is_missing() -> None:
    comic_info = SimpleNamespace(
        notes=(
            "Tagged with Perdoo v2026.3.0 using info from Metron at 2026-08-07T12:00:00+00:00. [issue_id:123]"  # noqa: E501
        )
    )

    assert sync.should_sync(None, comic_info, 28) is True


def test_should_sync_without_any_previous_metadata() -> None:
    assert sync.should_sync(None, None, 28) is True


@pytest.mark.parametrize(
    ("comic_info", "metron_info", "expected"),
    [
        (SimpleNamespace(count=1, volume=2020), None, True),
        (
            SimpleNamespace(count=1, volume=None),
            SimpleNamespace(series=SimpleNamespace(start_year=2015)),
            True,
        ),
        (
            SimpleNamespace(count=1, volume=1),
            SimpleNamespace(series=SimpleNamespace(start_year=2015)),
            True,
        ),
        (SimpleNamespace(count=1, volume=1), None, False),
        (SimpleNamespace(count=12, volume=2020), None, False),
        (SimpleNamespace(count=1, volume=2026), None, False),
        (SimpleNamespace(count=None, volume=2020), None, False),
        (None, None, False),
    ],
    ids=[
        "single-issue-old-volume-year",
        "start-year-from-metron-series",
        "metron-volume-number-falls-back-to-start-year",
        "no-year-available",
        "multi-issue-volume",
        "started-current-year",
        "missing-count",
        "no-comic-info",
    ],
)
def test_force_one_shot(
    comic_info: SimpleNamespace | None, metron_info: SimpleNamespace | None, expected: bool
) -> None:
    """Mylar3 rule: single-issue volume started before the current year (2026)."""
    assert (
        sync._force_one_shot(  # noqa: SLF001
            comic_info=comic_info, metron_info=metron_info
        )
        is expected
    )
