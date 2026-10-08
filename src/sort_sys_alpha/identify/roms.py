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

import re
import zlib
from pathlib import Path
from typing import Any

from .base import Extractor
from .types import Evidence

ROM_EXTENSIONS = {
    ".nes", ".gb", ".gbc", ".gba", ".z64", ".n64", ".v64",
    ".md", ".gen", ".sfc", ".smc", ".nds", ".dol", ".fds",
}

N64_MAGICS = {
    b"\x80\x37\x12\x40",  # .z64, big-endian
    b"\x37\x80\x40\x12",  # .v64, byte-swapped 16-bit words
    b"\x40\x12\x37\x80",  # .n64, byte-swapped 32-bit words
}

# fwNES-headered dumps start with this 4-byte magic; headerless dumps (more
# common from modern dumping tools) start directly with the disk's own
# block-1 marker instead -- either one confirms a real FDS image.
FDS_HEADERED_MAGIC = b"FDS\x1a"
FDS_HEADERLESS_MAGIC = b"\x01*NINTENDO-HVC*"

# Extension -> console for files seen only as an archive member listing (no
# header read, since the bytes are still zipped). Cartridge extensions are
# unambiguous by construction, same trust level as the loose-file SNES/NDS
# case below. Disc extensions (.bin/.iso/.cue/...) are deliberately excluded:
# unlike a cartridge extension, they don't imply a console on their own (see
# disk_images.py), so a zip of those stays in Archives rather than guessing.
ZIPPED_ROM_EXTENSION_CONSOLE = {
    ".nes": "nes",
    ".gb": "gb",
    ".gbc": "gbc",
    ".gba": "gba",
    ".z64": "n64",
    ".n64": "n64",
    ".v64": "n64",
    ".md": "genesis",
    ".gen": "genesis",
    ".sfc": "snes",
    ".smc": "snes",
    ".nds": "nds",
    ".fds": "fds",
}


def single_console_from_members(members: list[str]) -> str | None:
    """If every ROM-extension member in an archive's listing belongs to one
    console, return it. Returns None when no member has a recognized ROM
    extension, or when members span more than one console. Non-ROM members
    (readme, scan, cover art) are ignored rather than disqualifying the
    match -- those routinely ride along in ROM-set zips.
    """
    consoles = {
        ZIPPED_ROM_EXTENSION_CONSOLE[Path(name).suffix.lower()]
        for name in members
        if not name.endswith("/") and Path(name).suffix.lower() in ZIPPED_ROM_EXTENSION_CONSOLE
    }
    return consoles.pop() if len(consoles) == 1 else None


# MSX cartridge dumps use the generic ".rom" extension -- unlike every
# extension in ZIPPED_ROM_EXTENSION_CONSOLE above, that alone doesn't imply
# MSX (lots of unrelated things are named *.rom). This only fires when the
# archive's own filename corroborates it, never for a loose .rom file.
_MSX_NAME_HINT_RE = re.compile(r"\bmsx\b", re.IGNORECASE)


def msx_console_from_archive(archive_path: Path, members: list[str]) -> str | None:
    """"MSX" in the archive's own filename, plus at least one ".rom" member,
    is treated as MSX. Either signal alone is too weak on its own.
    """
    if not _MSX_NAME_HINT_RE.search(archive_path.stem):
        return None
    has_rom_member = any(
        not name.endswith("/") and Path(name).suffix.lower() == ".rom" for name in members
    )
    return "msx" if has_rom_member else None


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


def _fds_verified(path: Path) -> bool:
    header = _read_at(path, 0, len(FDS_HEADERLESS_MAGIC))
    return header.startswith(FDS_HEADERED_MAGIC) or header.startswith(FDS_HEADERLESS_MAGIC)


def _crc32_of(path: Path) -> str:
    """Uppercase 8-hex-digit CRC32, matching the libretro-database DAT
    files' own formatting (e.g. "F2EE11F9"), for cartridge-title lookup in
    dat.lookup_title_by_crc. See ADR 0008.
    """
    crc = 0
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                crc = zlib.crc32(chunk, crc)
    except OSError:
        return ""
    return f"{crc & 0xFFFFFFFF:08X}"


class RomExtractor(Extractor):
    name = "rom"
    priority = 10

    def can_handle(self, evidence: Evidence) -> bool:
        return evidence.extension in ROM_EXTENSIONS

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        ext = evidence.extension
        crc32 = _crc32_of(path)

        if ext == ".nes":
            verified = _read_at(path, 0, 4) == b"NES\x1a"
            return {"console": "nes", "verified": verified, "crc32": crc32}

        if ext in (".gb", ".gbc"):
            logo_ok = _read_at(path, 0x104, 4) == b"\xce\xed\x66\x66"
            console = _gb_console(path) if logo_ok else ext.lstrip(".")
            return {"console": console, "verified": logo_ok, "crc32": crc32}

        if ext == ".gba":
            verified = _read_at(path, 0x04, 4) == b"\x24\xff\xae\x51"
            return {"console": "gba", "verified": verified, "crc32": crc32}

        if ext in (".z64", ".n64", ".v64"):
            verified = _read_at(path, 0, 4) in N64_MAGICS
            return {"console": "n64", "verified": verified, "crc32": crc32}

        if ext in (".md", ".gen"):
            verified = _read_at(path, 0x100, 4) == b"SEGA"
            return {"console": "genesis", "verified": verified, "crc32": crc32}

        if ext in (".sfc", ".smc"):
            return {"console": "snes", "verified": False, "crc32": crc32}

        if ext == ".nds":
            return {"console": "nds", "verified": False, "crc32": crc32}

        if ext == ".fds":
            return {"console": "fds", "verified": _fds_verified(path), "crc32": crc32}

        if ext == ".dol":
            # Wii/GameCube homebrew executable (Dolphin Executable) -- no
            # fixed magic bytes to check, same extension-only situation as
            # SNES/NDS above. All homebrew .dol files seen so far are Wii
            # apps, so this assumes "wii" rather than "gc".
            return {"console": "wii", "verified": False, "crc32": crc32}

        return {"console": None, "verified": False, "crc32": crc32}
