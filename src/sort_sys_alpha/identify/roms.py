"""Cartridge ROM header signatures. See PLAN.md sections 4.3 and 4.9.

Console discs (PS1/PS2/PSP/GameCube/Wii) are handled by `disk_images.py`
instead, since they're identified from an ISO9660 filesystem, not a fixed
header offset. SNES and NDS have no cheap, reliable signature within a small
fixed offset (SNES copier headers shift everything by 512 bytes; NDS's
distinguishing fields aren't a simple magic number), so those two are
extension-only here — `verified` is False, meaning the extension is trusted
but the bytes weren't checked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Extractor
from .types import Evidence

ROM_EXTENSIONS = {
    ".nes", ".gb", ".gbc", ".gba", ".z64", ".n64", ".v64",
    ".md", ".gen", ".sfc", ".smc", ".nds",
}

N64_MAGICS = {
    b"\x80\x37\x12\x40",  # .z64, big-endian
    b"\x37\x80\x40\x12",  # .v64, byte-swapped 16-bit words
    b"\x40\x12\x37\x80",  # .n64, byte-swapped 32-bit words
}


def _read_at(path: Path, offset: int, length: int) -> bytes:
    try:
        with path.open("rb") as f:
            f.seek(offset)
            return f.read(length)
    except OSError:
        return b""


def _gb_console(path: Path) -> str:
    cgb_flag = _read_at(path, 0x143, 1)
    return "gbc" if cgb_flag in (b"\x80", b"\xc0") else "gb"


class RomExtractor(Extractor):
    name = "rom"
    priority = 10

    def can_handle(self, evidence: Evidence) -> bool:
        return evidence.extension in ROM_EXTENSIONS

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        ext = evidence.extension

        if ext == ".nes":
            return {"console": "nes", "verified": _read_at(path, 0, 4) == b"NES\x1a"}

        if ext in (".gb", ".gbc"):
            logo_ok = _read_at(path, 0x104, 4) == b"\xce\xed\x66\x66"
            console = _gb_console(path) if logo_ok else ext.lstrip(".")
            return {"console": console, "verified": logo_ok}

        if ext == ".gba":
            return {"console": "gba", "verified": _read_at(path, 0x04, 4) == b"\x24\xff\xae\x51"}

        if ext in (".z64", ".n64", ".v64"):
            return {"console": "n64", "verified": _read_at(path, 0, 4) in N64_MAGICS}

        if ext in (".md", ".gen"):
            return {"console": "genesis", "verified": _read_at(path, 0x100, 4) == b"SEGA"}

        if ext in (".sfc", ".smc"):
            return {"console": "snes", "verified": False}

        if ext == ".nds":
            return {"console": "nds", "verified": False}

        return {"console": None, "verified": False}
