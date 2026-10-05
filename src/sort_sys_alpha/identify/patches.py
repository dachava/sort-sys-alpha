"""IPS ROM patch files. See PLAN.md section 4.3.

A binary diff format for patching ROMs, not a ROM itself. Identified by its
fixed 5-byte "PATCH" magic at offset 0 -- the whole IPS spec.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Extractor
from .types import Evidence

_MAGIC = b"PATCH"


def _read_at(path: Path, length: int) -> bytes:
    try:
        with path.open("rb") as f:
            return f.read(length)
    except OSError:
        return b""


class RomPatchExtractor(Extractor):
    name = "rom_patch"
    priority = 44  # before the generic archive/text/unknown tiers

    def can_handle(self, evidence: Evidence) -> bool:
        return evidence.extension == ".ips" and _read_at(evidence.path, 5) == _MAGIC

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        return {"format": "ips"}
