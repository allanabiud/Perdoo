from pathlib import Path

import pytest

from perdoo.cli import library
from perdoo.cli._parser import build_parser


def test_library_parser_exposes_actions() -> None:
    parser = build_parser()

    args = parser.parse_args(["library", "pipeline", "--dry-run"])

    assert args.library_action == "pipeline"
    assert args.dry_run is True
    assert args.func is library._run_library_action  # noqa: SLF001


def test_library_action_targets_configured_output_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Output:
        folder = tmp_path

    class SettingsStub:
        output = Output()

        @classmethod
        def load(cls) -> "SettingsStub":
            return cls()

    captured: dict[str, Path] = {}

    monkeypatch.setattr(library, "Settings", SettingsStub)
    monkeypatch.setattr(
        library,
        "run_rename",
        lambda args: captured.setdefault("target", args.target),
    )

    args = build_parser().parse_args(["library", "rename"])
    args.func(args)

    assert captured["target"] == tmp_path
