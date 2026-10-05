"""Wii WAD files: title install packages. See PLAN.md section 4.3.

Not a disk image (disk_images.py) -- a WAD is Nintendo's installable-title
container, used for channels, IOS, forwarders, and (when it wraps a Virtual
Console title) an emulated game. Classified the same way regardless of what's
inside, by its fixed header-size + type-tag signature (wiibrew.org "WAD
files"): 0x00000020 (header size, big-endian) followed by a two-byte type
tag, "Is" for the installable kind seen in practice or "ib" for boot.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Extractor
from .types import Evidence

_HEADER_SIZE = b"\x00\x00\x00\x20"
_WAD_TYPES = {b"Is", b"ib"}


def _read_at(path: Path, offset: int, length: int) -> bytes:
    try:
        with path.open("rb") as f:
            f.seek(offset)
            return f.read(length)
    except OSError:
        return b""


class WiiWadExtractor(Extractor):
    name = "wii_wad"
    priority = 16  # alongside disk_images.py's console checks, before generic tiers

    def can_handle(self, evidence: Evidence) -> bool:
        if evidence.extension != ".wad":
            return False
        header = _read_at(evidence.path, 0, 6)
        return header[:4] == _HEADER_SIZE and header[4:6] in _WAD_TYPES

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        wad_type = _read_at(path, 4, 2)
        return {"wad_type": wad_type.decode("ascii", errors="replace")}
