"""pipeline forwards its CLI flags to the underlying sub-steps."""

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from perdoo.cli import pipeline
from perdoo.cli._parser import build_parser

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
