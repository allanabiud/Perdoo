__all__ = ["apply_patches"]

from io import BytesIO
from pathlib import Path
import re
from typing import TypeVar

from msgspec import ValidationError
from msgspec_xml import decode
from natsort import humansorted, ns
from PIL import Image
from shortbox import Comic
from shortbox.errors import MetadataValidationError, MissingArchiveMemberError
from shortbox.metadata import ComicInfo, Metadata
from shortbox.metadata.comic_info import PageType

MetadataT = TypeVar("MetadataT", bound=Metadata)

_IMAGE_EXTENSIONS: set[str] = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".jxl",
    ".gif",
    ".bmp",
    ".tiff",
}


def _sanitized_get_metadata(self: Comic, metadata_type: type[MetadataT]) -> MetadataT | None:
    cached = self._metadata_cache.get(metadata_type)
    if isinstance(cached, metadata_type):
        return cached

    for filename, metadata_cls in self._iter_metadata_files():
        if metadata_cls is not metadata_type:
            continue

        raw_bytes = self.read_file(filename=filename)
        # 1. Attempt standard decode
        try:
            instance = decode(raw_bytes, type_=metadata_type)
            self._metadata_cache[metadata_type] = instance
            return instance
        except ValidationError:
            pass

        # 2. Decode with XML sanitization for common legacy tagger errors (e.g., spaces or multiple URLs in <Web>)
        try:
            text = raw_bytes.decode("utf-8", errors="replace")

            def _fix_web(match: re.Match[str]) -> str:
                urls = match.group(1).split()
                for u in urls:
                    if u.startswith("http://") or u.startswith("https://"):
                        return f"<Web>{u}</Web>"
                return ""

            cleaned_text = re.sub(r"<Web>(.*?)</Web>", _fix_web, text, flags=re.DOTALL)

            try:
                instance = decode(cleaned_text.encode("utf-8"), type_=metadata_type)
                self._metadata_cache[metadata_type] = instance
                return instance
            except ValidationError as val_err:
                # If validation still fails on a specific tag, strip that tag and retry
                err_msg = str(val_err)
                field_match = re.search(r"at `\$\.([a-zA-Z0-9_]+)`", err_msg)
                if field_match:
                    tag_name = field_match.group(1)
                    stripped_text = re.sub(
                        rf"<{tag_name}>.*?</{tag_name}>",
                        "",
                        cleaned_text,
                        flags=re.DOTALL | re.IGNORECASE,
                    )
                    instance = decode(stripped_text.encode("utf-8"), type_=metadata_type)
                    self._metadata_cache[metadata_type] = instance
                    return instance
                raise MetadataValidationError from val_err
        except Exception as err:
            raise MetadataValidationError from err

    return None


def _robust_get_cover(self: Comic) -> bytes:
    """Find and return the genuine cover image bytes from the comic archive."""
    candidates = [
        f
        for f in self.list_filenames()
        if not f.endswith("/")
        and not f.startswith("__MACOSX/")
        and Path(f).name.lower() not in {"thumbs.db", ".ds_store", "desktop.ini"}
        and Path(f).suffix.lower() in _IMAGE_EXTENSIONS
    ]
    sorted_candidates = humansorted(candidates, alg=ns.NA | ns.G | ns.P)

    # 1. Check ComicInfo for explicit FrontCover page
    try:
        if comic_info := self.get_metadata(ComicInfo):
            for page in getattr(comic_info, "pages", []):
                if getattr(page, "type", None) == PageType.FRONT_COVER:
                    idx = getattr(page, "image", None)
                    if idx is not None and 0 <= idx < len(sorted_candidates):
                        target_file = sorted_candidates[idx]
                        data = self.read_file(filename=target_file)
                        if data:
                            try:
                                with Image.open(BytesIO(data)) as im:
                                    im.verify()
                                return data
                            except Exception:
                                pass
    except Exception:
        pass

    # 2. Iterate candidates in natural order and return the first valid, readable image
    for filename in sorted_candidates:
        try:
            data = self.read_file(filename=filename)
            if data and len(data) > 0:
                with Image.open(BytesIO(data)) as im:
                    im.verify()
                return data
        except Exception:
            continue

    # 3. Fallback: return any readable data if verify failed
    for filename in sorted_candidates:
        try:
            data = self.read_file(filename=filename)
            if data and len(data) > 0:
                return data
        except Exception:
            continue

    raise MissingArchiveMemberError(f"{self.file.name!r} contains no valid image to use as a cover.")


def apply_patches() -> None:
    Comic.get_metadata = _sanitized_get_metadata
    Comic.get_cover = _robust_get_cover
