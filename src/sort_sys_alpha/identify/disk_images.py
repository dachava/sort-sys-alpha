"""Disk images: console discs (PLAN.md section 4.9) and generic ISOs.

Checked ahead of the generic archive/text tiers because `.iso`/`.img`/`.gcm`
is exactly the ambiguous case PLAN.md section 4.4 calls out: the extension
alone doesn't say whether this is a PS2 game or a Linux live CD.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Extractor
from .iso9660 import PrimaryVolumeDescriptor, list_root_entries, read_pvd, read_root_file
from .types import Evidence

DISC_EXTENSIONS = {".iso", ".img", ".gcm", ".nrg"}

GC_MAGIC = b"\xc2\x33\x9f\x3d"
WII_MAGIC = b"\x5d\x1c\x9e\xa3"

PS_MARKERS = {"SYSTEM.CNF"}
PSP_MARKERS = {"PSP_GAME", "UMD_DATA.BIN"}


def _ps1_or_ps2(path: Path, pvd: PrimaryVolumeDescriptor) -> str:
    """SYSTEM.CNF's boot line is `BOOT2 = ...` on PS2 discs, `BOOT = ...` on PS1."""
    content = read_root_file(path, pvd, "SYSTEM.CNF") or b""
    text = content.decode("ascii", errors="replace").upper()
    return "ps2" if "BOOT2" in text else "psx"


def _read_at(path: Path, offset: int, length: int) -> bytes:
    try:
        with path.open("rb") as f:
            f.seek(offset)
            return f.read(length)
    except OSError:
        return b""


class DiskImageExtractor(Extractor):
    name = "disk_image"
    priority = 15

    def can_handle(self, evidence: Evidence) -> bool:
        return evidence.extension in DISC_EXTENSIONS

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        if _read_at(path, 0x1C, 4) == GC_MAGIC:
            return {"console": "gc", "disc_kind": "gamecube"}
        if _read_at(path, 0x18, 4) == WII_MAGIC:
            return {"console": "wii", "disc_kind": "wii"}

        pvd = read_pvd(path)
        if pvd is None:
            return {"disc_kind": "unknown"}

        root_entries = list_root_entries(path, pvd)
        result: dict[str, Any] = {"volume_label": pvd.volume_id or None}
        if root_entries & PS_MARKERS:
            result["console"] = _ps1_or_ps2(path, pvd)
            result["disc_kind"] = "playstation"
        elif root_entries & PSP_MARKERS:
            result["console"] = "psp"
            result["disc_kind"] = "psp"
        else:
            result["disc_kind"] = "iso9660"
        return result
