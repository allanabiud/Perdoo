"""Reader robustness patches for metadata written by legacy taggers."""

import zipfile
from pathlib import Path

from shortbox import Comic
from shortbox.metadata import ComicInfo

import perdoo  # noqa: F401  # applies the get_metadata patches on import

MALFORMED_XML = """<?xml version="1.0" encoding="utf-8"?>
<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Series>Superman Red & Blue</Series>
  <Number>1</Number>
</ComicInfo>
"""


def _make_cbz(path: Path, comic_info_xml: str) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("page01.jpg", b"fake-image-bytes")
        zf.writestr("ComicInfo.xml", comic_info_xml)
    return path


def test_get_metadata_repairs_bare_ampersand(tmp_path: Path) -> None:
    """A raw '&' from a legacy tagger must not crash the reader (ParseError)."""
    cbz = _make_cbz(tmp_path / "Superman Red & Blue #001.cbz", MALFORMED_XML)
    with Comic.open(file=cbz) as comic:
        comic_info = comic.get_metadata(ComicInfo)
    assert comic_info is not None
    assert comic_info.series == "Superman Red & Blue"
    assert comic_info.number == "1"


def test_get_metadata_keeps_valid_entities(tmp_path: Path) -> None:
    """Already-escaped entities must not be double-escaped."""
    xml = MALFORMED_XML.replace("Red & Blue", "Red &amp; Blue")
    cbz = _make_cbz(tmp_path / "valid.cbz", xml)
    with Comic.open(file=cbz) as comic:
        comic_info = comic.get_metadata(ComicInfo)
    assert comic_info is not None
    assert comic_info.series == "Superman Red & Blue"


def test_get_metadata_still_reads_wellformed_xml(tmp_path: Path) -> None:
    """The standard decode path keeps working for clean metadata."""
    xml = """<?xml version="1.0" encoding="utf-8"?>
<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Series>Watchmen</Series>
  <Number>1</Number>
  <Format>Trade Paperback</Format>
</ComicInfo>
"""
    cbz = _make_cbz(tmp_path / "watchmen.cbz", xml)
    with Comic.open(file=cbz) as comic:
        comic_info = comic.get_metadata(ComicInfo)
    assert comic_info is not None
    assert comic_info.series == "Watchmen"
    assert comic_info.format == "Trade Paperback"
