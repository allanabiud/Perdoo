"""pipeline forwards its CLI flags to the underlying sub-steps."""

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from perdoo.cli import pipeline
from perdoo.cli import convert
from perdoo.cli._parser import build_parser
from perdoo.cli._results import Failure, RunResult

if TYPE_CHECKING:
    from argparse import Namespace


class _StubSettings:
    class Output:
        webp: bool = False
        format: str = "cbz"

    output = Output()

    @classmethod
    def load(cls) -> "_StubSettings":
        return cls()

    def save(self) -> "_StubSettings":
        return self


def test_pipeline_parser_exposes_force_flag(tmp_path: Path) -> None:
    args = build_parser().parse_args(["pipeline", str(tmp_path), "-f"])

    assert args.force is True
    assert args.func is pipeline.run


def test_pipeline_parser_exposes_reporting_flags(tmp_path: Path) -> None:
    args = build_parser().parse_args(
        [
            "pipeline",
            str(tmp_path),
            "--dry-run",
            "--failure-manifest",
            str(tmp_path / "failures.json"),
            "--resume",
            str(tmp_path / "previous.json"),
        ]
    )

    assert args.dry_run is True
    assert args.failure_manifest == tmp_path / "failures.json"
    assert args.resume == tmp_path / "previous.json"


def test_pipeline_writes_failure_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "Settings", _StubSettings)
    monkeypatch.setattr(
        pipeline,
        "run_convert",
        lambda _args: RunResult(
            stage="convert",
            processed=1,
            failures=[Failure(stage="convert", path=tmp_path / "comic.cbz", error="broken")],
        ),
    )
    monkeypatch.setattr(pipeline, "run_webp", lambda _args: None)
    monkeypatch.setattr(pipeline, "run_clean", lambda _args: RunResult(stage="clean"))
    monkeypatch.setattr(pipeline, "run_sync", lambda _args: RunResult(stage="sync"))
    monkeypatch.setattr(pipeline, "run_rename", lambda _args: RunResult(stage="rename"))

    manifest = tmp_path / "failures.json"
    args = build_parser().parse_args(
        ["pipeline", str(tmp_path), "--dry-run", "--failure-manifest", str(manifest)]
    )
    result = args.func(args)

    assert result.failed == 1
    assert args.dry_run is True
    assert '"error": "broken"' in manifest.read_text()


def test_convert_dry_run_skips_archives_already_in_target_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = tmp_path / "comic.cbz"
    entry.write_bytes(b"archive")
    messages: list[str] = []
    monkeypatch.setattr(convert, "CONSOLE", type("Console", (), {"print": messages.append})())

    convert._convert_single(entry, convert.ZipArchive, dry_run=True)  # noqa: SLF001

    assert messages == ["Already ZipArchive: [cyan]comic.cbz[/cyan]"]


def test_pipeline_forwards_force_to_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Namespace] = {}
    monkeypatch.setattr(pipeline, "Settings", _StubSettings)
    monkeypatch.setattr(pipeline, "run_convert", lambda _args: None)
    monkeypatch.setattr(pipeline, "run_webp", lambda _args: None)
    monkeypatch.setattr(pipeline, "run_clean", lambda _args: None)
    monkeypatch.setattr(pipeline, "run_sync", lambda a: captured.setdefault("sync", a))
    monkeypatch.setattr(pipeline, "run_rename", lambda _args: None)

    args = build_parser().parse_args(["pipeline", str(tmp_path), "-f"])
    args.func(args)

    assert captured["sync"].force is True


def test_pipeline_without_force_does_not_force_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Namespace] = {}
    monkeypatch.setattr(pipeline, "Settings", _StubSettings)
    monkeypatch.setattr(pipeline, "run_convert", lambda _args: None)
    monkeypatch.setattr(pipeline, "run_webp", lambda _args: None)
    monkeypatch.setattr(pipeline, "run_clean", lambda _args: None)
    monkeypatch.setattr(pipeline, "run_sync", lambda a: captured.setdefault("sync", a))
    monkeypatch.setattr(pipeline, "run_rename", lambda _args: None)

    args = build_parser().parse_args(["pipeline", str(tmp_path)])
    args.func(args)

    assert captured["sync"].force is False
