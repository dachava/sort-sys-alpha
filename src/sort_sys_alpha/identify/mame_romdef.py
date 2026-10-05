"""MAME/NeoRageX-style ROM-set definition files. See PLAN.md section 4.3.

Some ROM-set packs bundle one tiny `.rc` text file per game describing which
chip-ROM files make up that game's set (CPU/SFIX/SM1/SOUND1/GFX blocks, hex
offsets, "END" terminators) -- packaging metadata for a ROM-building tool,
not a playable ROM itself. Recognized by content, not just the ".rc"
extension (which is also a generic config-file extension used for other
things), the same way `logs.py` distinguishes a log-shaped ".txt" from a
plain note.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import Extractor
from .types import Evidence

PEEK_BYTES = 4096
_GAME_LINE_RE = re.compile(r'^game\s+\S+\s+\S+\s+"([^"]*)"\s*$', re.MULTILINE)


def _peek(path: Path) -> str:
    try:
        with path.open("rb") as f:
            raw = f.read(PEEK_BYTES)
    except OSError:
        return ""
    return raw.decode("utf-8", errors="replace")


class MameRomdefExtractor(Extractor):
    name = "mame_romdef"
    priority = 45  # before TextExtractor/UnknownExtractor, which would otherwise claim ".rc"

    def can_handle(self, evidence: Evidence) -> bool:
        if evidence.extension != ".rc":
            return False
        text = _peek(evidence.path)
        return bool(_GAME_LINE_RE.search(text)) and "CPU 0x" in text and "\nEND" in text

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        match = _GAME_LINE_RE.search(_peek(path))
        return {"game_title": match.group(1) if match else None}
