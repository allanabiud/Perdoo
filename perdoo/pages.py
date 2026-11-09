__all__ = ["build_comic_pages", "update_comic_pages_metadata"]

from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
import zipfile

from natsort import humansorted, ns
from PIL import Image
from shortbox import Comic
from shortbox.metadata import ComicInfo, MetronInfo
from shortbox.metadata.comic_info import Page, PageType


def build_comic_pages(
    comic: Comic,
    image_extensions: Sequence[str] = (".png", ".jpg", ".jpeg", ".webp", ".jxl"),
    existing_pages: Sequence[Page] | None = None,
) -> tuple[int, list[Page]]:
    """Inspect archive images and generate detailed Page metadata including:
    - Page index (Image="0", Image="1", ...)
    - Exact uncompressed file size in bytes (ImageSize)
    - Image pixel width and height (ImageWidth, ImageHeight)
    - Double page spread detection (DoublePage="true" when width > height)
    - Page classification (Type="FrontCover", Type="Story", etc.)
    """
    filenames = [
        f
        for f in comic.list_filenames()
        if not f.endswith("/")
        and not f.startswith("__MACOSX/")
        and Path(f).name.lower() not in {"thumbs.db", ".ds_store", "desktop.ini"}
        and Path(f).suffix.lower() in image_extensions
    ]
    sorted_files = humansorted(filenames, alg=ns.NA | ns.G | ns.P)
    page_count = len(sorted_files)
    if page_count == 0:
        return 0, []

    existing_map: dict[int, Page] = {}
    if existing_pages:
        for p in existing_pages:
            existing_map[p.image] = p

    pages: list[Page] = []

    # Fast path: inspect Zip/CBZ entries directly without extracting
    if comic.file.suffix.lower() in {".cbz", ".zip"}:
        try:
            with zipfile.ZipFile(comic.file, mode="r") as zf:
                for idx, fname in enumerate(sorted_files):
                    fsize = 0
                    width, height = None, None
                    is_double = False
                    try:
                        info = zf.getinfo(fname)
                        fsize = info.file_size
                        with zf.open(fname) as fp:
                            with Image.open(fp) as im:
                                width, height = im.size
                        is_double = bool(width and height and width > height)
                    except Exception:
                        pass

                    prev = existing_map.get(idx)
                    page_type = (
                        prev.type
                        if prev and prev.type
                        else (PageType.FRONT_COVER if idx == 0 else PageType.STORY)
                    )
                    bookmark = prev.bookmark if prev else None
                    key = prev.key if prev else None

                    pages.append(
                        Page(
                            image=idx,
                            type=page_type,
                            double_page=is_double,
                            image_size=fsize,
                            image_width=width,
                            image_height=height,
                            bookmark=bookmark,
                            key=key,
                        )
                    )
                return page_count, pages
        except Exception:
            pass

    # Fallback: using comic.read_file()
    for idx, fname in enumerate(sorted_files):
        fsize = 0
        width, height = None, None
        is_double = False
        try:
            data = comic.read_file(filename=fname)
            fsize = len(data)
            with Image.open(BytesIO(data)) as im:
                width, height = im.size
            is_double = bool(width and height and width > height)
        except Exception:
            pass

        prev = existing_map.get(idx)
        page_type = (
            prev.type
            if prev and prev.type
            else (PageType.FRONT_COVER if idx == 0 else PageType.STORY)
        )
        bookmark = prev.bookmark if prev else None
        key = prev.key if prev else None

        pages.append(
            Page(
                image=idx,
                type=page_type,
                double_page=is_double,
                image_size=fsize,
                image_width=width,
                image_height=height,
                bookmark=bookmark,
                key=key,
            )
        )

    return page_count, pages


def update_comic_pages_metadata(
    comic: Comic,
    comic_info: ComicInfo | None,
    metron_info: MetronInfo | None,
    image_extensions: Sequence[str] = (".png", ".jpg", ".jpeg", ".webp", ".jxl"),
) -> bool:
    """Populate or update page count, dimensions, sizes, and double-page flags."""
    existing_pages = comic_info.pages if comic_info else None
    page_count, pages = build_comic_pages(
        comic=comic, image_extensions=image_extensions, existing_pages=existing_pages
    )
    if page_count == 0:
        return False

    updated = False
    if comic_info is not None:
        if comic_info.page_count != page_count:
            comic_info.page_count = page_count
            updated = True
        comic_info.pages = pages
        updated = True

    if metron_info is not None:
        if metron_info.page_count != page_count:
            metron_info.page_count = page_count
            updated = True

    return updated
