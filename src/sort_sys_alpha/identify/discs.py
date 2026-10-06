"""Raw CD-ROM sector adapter. See PLAN.md section 4.9.

A `.bin` PSX/PS2/Saturn/Dreamcast dump stores each 2048-byte logical ISO9660
block inside a 2352-byte raw CD sector (12-byte sync + 3-byte address +
1-byte mode, then either 2048 bytes of data (Mode 1) or an 8-byte XA
subheader followed by 2048 bytes of data (Mode 2 Form 1, what PS1/PS2 data
tracks almost always use)). `LogicalSectorView` strips that framing so
`iso9660.py`'s reader -- written for plain 2048-byte-sector images -- works
on a raw dump unmodified. A file with no sync pattern at all is already a
plain ("cooked") 2048-byte-sector image, same as a normal `.iso`, and is
passed through untouched.

`f` here is any object with `.seek(offset)` / `.read(n)` -- an open file
handle for a loose `.bin`, or a zip member's file-like object -- so the same
adapter covers a loose disc dump and one still sitting inside a zip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

LOGICAL_SECTOR_SIZE = 2048
RAW_SECTOR_SIZE = 2352
SYNC_PATTERN = b"\x00" + b"\xff" * 10 + b"\x00"
MODE1_DATA_OFFSET = 16  # 12 sync + 3 address + 1 mode
MODE2_DATA_OFFSET = 24  # ... + 8-byte XA subheader


@dataclass(frozen=True)
class RawSectorLayout:
    sector_size: int
    data_offset: int


COOKED_LAYOUT = RawSectorLayout(LOGICAL_SECTOR_SIZE, 0)


def detect_layout(f: Any) -> RawSectorLayout:
    try:
        f.seek(0)
        first = f.read(RAW_SECTOR_SIZE)
    except OSError:
        return COOKED_LAYOUT
    if len(first) < RAW_SECTOR_SIZE or first[0:12] != SYNC_PATTERN:
        return COOKED_LAYOUT
    mode = first[15]
    data_offset = MODE2_DATA_OFFSET if mode == 2 else MODE1_DATA_OFFSET
    return RawSectorLayout(RAW_SECTOR_SIZE, data_offset)


class LogicalSectorView:
    """Presents `raw` as a contiguous stream of `LOGICAL_SECTOR_SIZE`-byte
    sectors, translating each read across the raw framing in `layout`.
    """

    def __init__(self, raw: Any, layout: RawSectorLayout) -> None:
        self._raw = raw
        self._layout = layout
        self._pos = 0

    def seek(self, offset: int) -> None:
        self._pos = offset

    def read(self, n: int) -> bytes:
        if self._layout.data_offset == 0:
            self._raw.seek(self._pos)
            data = self._raw.read(n)
            self._pos += len(data)
            return data

        out = bytearray()
        pos = self._pos
        remaining = n
        while remaining > 0:
            sector_index, sector_offset = divmod(pos, LOGICAL_SECTOR_SIZE)
            raw_offset = (
                sector_index * self._layout.sector_size + self._layout.data_offset + sector_offset
            )
            self._raw.seek(raw_offset)
            take = min(remaining, LOGICAL_SECTOR_SIZE - sector_offset)
            chunk = self._raw.read(take)
            if not chunk:
                break
            out += chunk
            pos += len(chunk)
            remaining -= len(chunk)
            if len(chunk) < take:
                break
        self._pos = pos
        return bytes(out)


def open_logical_view(f: Any) -> LogicalSectorView:
    """Detect `f`'s sector framing and wrap it for logical-sector access."""
    return LogicalSectorView(f, detect_layout(f))
