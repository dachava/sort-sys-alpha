"""Disk images: console discs (PLAN.md section 4.9) and generic ISOs.

Checked ahead of the generic archive/text tiers because `.iso`/`.img`/`.gcm`
is exactly the ambiguous case PLAN.md section 4.4 calls out: the extension
alone doesn't say whether this is a PS2 game or a Linux live CD.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..dat import normalize_serial
from .base import Extractor
from .discs import LOGICAL_SECTOR_SIZE, open_logical_view
from .iso9660 import PrimaryVolumeDescriptor, list_root_entries, read_pvd, read_root_file
from .types import Evidence

# .bin is a raw-sector dump (PLAN.md section 4.9): unlike the others, its
# extension alone doesn't mean "disc image" (plenty of non-disc .bin files
# exist), so it's examined the same way but falls back to a byte preview
# rather than claiming disc_kind when no ISO9660 filesystem turns up.
DISC_EXTENSIONS = {".iso", ".img", ".gcm", ".nrg", ".wbfs", ".rvz", ".bin"}
RAW_SECTOR_CANDIDATE_EXTENSIONS = {".bin"}

# The extensions worth inspecting when they turn up *inside* a zip/tar
# listing (route.py) -- .nrg/.wbfs/.rvz need their own magic-byte checks
# rather than the ISO9660 reader, so they're not included here.
DISC_EXTENSIONS_IN_ARCHIVE = {".iso", ".img", ".gcm", ".bin"}

GC_MAGIC = b"\xc2\x33\x9f\x3d"
WII_MAGIC = b"\x5d\x1c\x9e\xa3"
WBFS_MAGIC = b"WBFS"
RVZ_MAGIC = b"RVZ\x01"

PS_MARKERS = {"SYSTEM.CNF"}
PSP_MARKERS = {"PSP_GAME", "UMD_DATA.BIN"}

# Saturn and PC-Engine CD don't have an ISO9660 filesystem at all -- each
# format has its own fixed boot-sector header, normally right at the start
# of the data track. A rip sometimes keeps that track's 2-second (150
# logical sector) pregap, which would push the header 150 sectors later, so
# a generous prefix is scanned for the marker rather than assuming sector 0
# -- still a deterministic byte signature, just not pinned to one offset.
SATURN_MAGIC = b"SEGA SEGASATURN"
PCE_CD_MAGIC = b"PC Engine CD-ROM SYSTEM"
BOOT_MAGIC_SCAN_SECTORS = 200

PREVIEW_BYTES = 512


def _ps1_or_ps2(f: Any, pvd: PrimaryVolumeDescriptor) -> tuple[str, str | None]:
    """SYSTEM.CNF's boot line is `BOOT2 = ...` on PS2 discs, `BOOT = ...` on
    PS1, and names the boot executable by serial (e.g.
    `cdrom0:\\SLUS_202.67;1`) -- which DAT lookups (dat.py) key on.
    """
    content = read_root_file(f, pvd, "SYSTEM.CNF") or b""
    text = content.decode("ascii", errors="replace").upper()
    console = "ps2" if "BOOT2" in text else "psx"
    return console, normalize_serial(text)


def _boot_magic_console(view: Any) -> str | None:
    try:
        view.seek(0)
        prefix = view.read(BOOT_MAGIC_SCAN_SECTORS * LOGICAL_SECTOR_SIZE)
    except OSError:
        return None
    if SATURN_MAGIC in prefix:
        return "saturn"
    if PCE_CD_MAGIC in prefix:
        return "pcenginecd"
    return None


def _read_at(path: Path, offset: int, length: int) -> bytes:
    try:
        with path.open("rb") as f:
            f.seek(offset)
            return f.read(length)
    except OSError:
        return b""


def console_from_disc_stream(f: Any) -> str | None:
    """PS1/PS2/PSP/Saturn/PC-Engine CD console from an already-open disc
    stream (a loose file handle, or a zip member) -- the same inspection as
    a loose disc file, minus the Nintendo magic-byte checks that only apply
    to a whole file on disk. Returns None for a generic/unrecognized
    ISO9660 volume too (plenty of those aren't game discs), not just a
    non-disc stream.
    """
    view = open_logical_view(f)
    pvd = read_pvd(view)
    if pvd is None:
        return _boot_magic_console(view)
    root_entries = list_root_entries(view, pvd)
    if root_entries & PS_MARKERS:
        console, _serial = _ps1_or_ps2(view, pvd)
        return console
    if root_entries & PSP_MARKERS:
        return "psp"
    return None


class DiskImageExtractor(Extractor):
    name = "disk_image"
    priority = 15

    def can_handle(self, evidence: Evidence) -> bool:
        return evidence.extension in DISC_EXTENSIONS

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        # WBFS wraps sectors in its own container rather than a plain
        # ISO9660 filesystem, so it's checked before the PVD read below
        # would otherwise be tried (and fail) on it.
        if _read_at(path, 0x0, 4) == WBFS_MAGIC:
            return {"console": "wii", "disc_kind": "wbfs"}
        if _read_at(path, 0x0, 4) == RVZ_MAGIC:
            # Dolphin's compressed disc format wraps either a GameCube or a
            # Wii disc -- telling which would mean parsing further into the
            # container, so this is deliberately not claiming a console,
            # same as the generic iso9660 fallback below.
            return {"disc_kind": "rvz"}
        if _read_at(path, 0x1C, 4) == GC_MAGIC:
            return {"console": "gc", "disc_kind": "gamecube"}
        if _read_at(path, 0x18, 4) == WII_MAGIC:
            return {"console": "wii", "disc_kind": "wii"}

        try:
            with path.open("rb") as f:
                is_raw = evidence.extension in RAW_SECTOR_CANDIDATE_EXTENSIONS
                view = open_logical_view(f) if is_raw else f
                pvd = read_pvd(view)
                if pvd is None:
                    console = _boot_magic_console(view)
                    if console:
                        return {"console": console, "disc_kind": console}
                    return self._not_a_disc(path, evidence)

                root_entries = list_root_entries(view, pvd)
                result: dict[str, Any] = {"volume_label": pvd.volume_id or None}
                if root_entries & PS_MARKERS:
                    console, serial = _ps1_or_ps2(view, pvd)
                    result["console"] = console
                    if serial:
                        result["serial"] = serial
                    result["disc_kind"] = "playstation"
                elif root_entries & PSP_MARKERS:
                    result["console"] = "psp"
                    result["disc_kind"] = "psp"
                else:
                    result["disc_kind"] = "iso9660"
                return result
        except OSError:
            return self._not_a_disc(path, evidence)

    def _not_a_disc(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        """`.iso`/`.img`/etc. imply a disc image even without a readable
        filesystem, so they just stay "unknown". `.bin` doesn't -- most
        `.bin` files aren't discs at all -- so it falls back to the same
        byte preview `UnknownExtractor` would give the model, rather than
        losing that evidence to a claimed-but-empty "disk_image" kind.
        """
        if evidence.extension not in RAW_SECTOR_CANDIDATE_EXTENSIONS:
            return {"disc_kind": "unknown"}
        raw = _read_at(path, 0, PREVIEW_BYTES)
        if not raw:
            return {"disc_kind": "unknown"}
        return {"disc_kind": "unknown", "hex_preview": raw.hex()}
