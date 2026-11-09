"""Empty-directory cleanup performed by the rename step."""

import zipfile
from pathlib import Path

from perdoo.cli.rename import _cleanup_empty_dirs, rename_entry
from perdoo.settings import ComicInfo, Naming, Output, Settings

COMIC_INFO_XML = """<?xml version="1.0" encoding="utf-8"?>
<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Series>Watchmen</Series>
  <Number>1</Number>
</ComicInfo>
"""


class TestCleanupEmptyDirs:
    def test_removes_emptied_chain_up_to_target(self, tmp_path: Path) -> None:
        target = tmp_path / "library"
        nested = target / "Publisher" / "Series (2020) [TPB]"
        nested.mkdir(parents=True)

        _cleanup_empty_dirs(start=nested, stop=target)

        assert not nested.exists()
        assert not (target / "Publisher").exists()
        assert target.exists()

    def test_keeps_directories_that_still_have_content(self, tmp_path: Path) -> None:
        target = tmp_path / "library"
        keep = target / "Publisher"
        keep.mkdir(parents=True)
        (keep / "other.cbz").write_bytes(b"x")
        nested = keep / "Series"
        nested.mkdir()

        _cleanup_empty_dirs(start=nested, stop=target)

        assert not nested.exists()
        assert keep.exists()

    def test_start_equal_to_stop_removes_nothing(self, tmp_path: Path) -> None:
        target = tmp_path / "library"
        target.mkdir()

        _cleanup_empty_dirs(start=target, stop=target)

        assert target.exists()

    def test_paths_outside_the_target_are_untouched(self, tmp_path: Path) -> None:
        target = tmp_path / "library"
        outside = tmp_path / "unrelated" / "Series"
        outside.mkdir(parents=True)

        _cleanup_empty_dirs(start=outside, stop=target)

        assert outside.exists()


class TestRenameEntryCleanup:
    def test_moved_archive_empties_its_old_directory(self, tmp_path: Path) -> None:
        inbox = tmp_path / "inbox"
        old_dir = inbox / "Old Folder"
        old_dir.mkdir(parents=True)
        entry = old_dir / "old-name.cbz"
        with zipfile.ZipFile(entry, "w") as zf:
            zf.writestr("page01.jpg", b"fake-image-bytes")
            zf.writestr("ComicInfo.xml", COMIC_INFO_XML)

        output = tmp_path / "library"
        settings = Settings(
            output=Output(
                folder=output,
                comic_info=ComicInfo(handle_pages=False),
                naming=Naming(pattern="{series-name} #{number}", seperator=" "),
            )
        )

        rename_entry(entry=entry, target=inbox, settings=settings)

        assert not old_dir.exists()
        assert inbox.exists()
        moved = list(output.glob("*.cbz"))
        assert len(moved) == 1
        assert "Watchmen" in moved[0].name

    def test_directory_with_remaining_archives_is_kept(self, tmp_path: Path) -> None:
        inbox = tmp_path / "inbox"
        old_dir = inbox / "Series"
        old_dir.mkdir(parents=True)
        with zipfile.ZipFile(old_dir / "tagged.cbz", "w") as zf:
            zf.writestr("page01.jpg", b"fake-image-bytes")
            zf.writestr("ComicInfo.xml", COMIC_INFO_XML)
        # No metadata: rename_entry skips it, so it stays behind.
        with zipfile.ZipFile(old_dir / "untagged.cbz", "w") as zf:
            zf.writestr("page01.jpg", b"fake-image-bytes")

        output = tmp_path / "library"
        settings = Settings(
            output=Output(
                folder=output,
                comic_info=ComicInfo(handle_pages=False),
                naming=Naming(pattern="{series-name} #{number}", seperator=" "),
            )
        )

        rename_entry(entry=old_dir / "tagged.cbz", target=inbox, settings=settings)

        assert old_dir.exists()
        assert (old_dir / "untagged.cbz").exists()
        assert len(list(output.glob("*.cbz"))) == 1

    def test_target_directory_is_removed_when_it_is_inside_output(self, tmp_path: Path) -> None:
        output = tmp_path / "library"
        source = output / "Old Folder"
        source.mkdir(parents=True)
        entry = source / "old-name.cbz"
        with zipfile.ZipFile(entry, "w") as zf:
            zf.writestr("page01.jpg", b"fake-image-bytes")
            zf.writestr("ComicInfo.xml", COMIC_INFO_XML)

        settings = Settings(
            output=Output(
                folder=output,
                comic_info=ComicInfo(handle_pages=False),
                naming=Naming(pattern="{series-name} #{number}", seperator=" "),
            )
        )

        rename_entry(entry=entry, target=source, settings=settings)

        assert not source.exists()
        assert output.exists()
        assert len(list(output.glob("*.cbz"))) == 1

    def test_dry_run_does_not_move_or_modify_archive(self, tmp_path: Path) -> None:
        source = tmp_path / "source"
        source.mkdir()
        entry = source / "old-name.cbz"
        with zipfile.ZipFile(entry, "w") as zf:
            zf.writestr("page01.jpg", b"fake-image-bytes")
            zf.writestr("ComicInfo.xml", COMIC_INFO_XML)
        original = entry.read_bytes()

        output = tmp_path / "library"
        settings = Settings(
            output=Output(
                folder=output,
                comic_info=ComicInfo(handle_pages=False),
                naming=Naming(pattern="{series-name} #{number}", seperator=" "),
            )
        )

        rename_entry(entry=entry, target=source, settings=settings, dry_run=True)

        assert entry.exists()
        assert entry.read_bytes() == original
        assert not output.exists()
