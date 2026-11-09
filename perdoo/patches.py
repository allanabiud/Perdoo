__all__ = ["apply_patches"]

import re
from typing import TypeVar

from msgspec import ValidationError
from msgspec_xml import decode
from shortbox import Comic
from shortbox.errors import MetadataValidationError
from shortbox.metadata import Metadata

MetadataT = TypeVar("MetadataT", bound=Metadata)


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


def apply_patches() -> None:
    Comic.get_metadata = _sanitized_get_metadata
