"""Local DAT-file matching for exact disc titles. See ADR 0007, PLAN.md M7.

Scoped to the libretro "Data Center" PS1/PS2/PSP DATs: ClrMamePro's
paren-delimited text format (not Logiqx XML), keyed by *serial number*
rather than a CRC/MD5/SHA1 content hash -- this format has no hash fields
at all. A disc's serial is read from its `SYSTEM.CNF` boot line (already
parsed for PS1-vs-PS2 detection in `identify/disk_images.py`) and looked up
here for its canonical title.

A future No-Intro/Redump hash-keyed DAT would need its own parser -- this
module intentionally doesn't try to generalize to that shape yet.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

_GAME_BLOCK_START_RE = re.compile(r"^game\s*\(", re.MULTILINE)
_SERIAL_RE = re.compile(r"([A-Z]{4})[_-]?(\d{3})\.?(\d{2})")


def normalize_serial(raw: str) -> str | None:
    """"SLUS_202.67" (SYSTEM.CNF's path style) and "SLUS-20267" (the DAT's
    own style) both normalize to "SLUS-20267", so either side of a lookup
    can be compared regardless of which separator convention it came from.
    """
    match = _SERIAL_RE.search(raw.upper())
    if not match:
        return None
    prefix, first, last = match.groups()
    return f"{prefix}-{first}{last}"


def _matching_paren_end(text: str, open_paren_index: int) -> int:
    """Index just past the ')' matching the '(' at `open_paren_index`."""
    depth = 1
    i = open_paren_index + 1
    while depth > 0 and i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
        i += 1
    return i


def _field(block: str, name: str) -> str | None:
    # The first match is always the game-level field, not the nested
    # `rom ( ... )` block's own `name`/`serial` -- those come later in the
    # same block, so a plain first-match search is sufficient here.
    match = re.search(rf'{name}\s*"([^"]*)"', block)
    return match.group(1) if match else None


def parse_dat(text: str) -> dict[str, str]:
    """Serial -> canonical title, for every top-level `game ( ... )` block."""
    titles: dict[str, str] = {}
    for start in _GAME_BLOCK_START_RE.finditer(text):
        open_paren = start.end() - 1
        end = _matching_paren_end(text, open_paren)
        block = text[open_paren + 1 : end - 1]
        name = _field(block, "name")
        serial = _field(block, "serial")
        if not name or not serial:
            continue
        normalized = normalize_serial(serial)
        if normalized:
            titles[normalized] = name
    return titles


@cache
def _load_dat(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    return parse_dat(text)


def lookup_title(console: str, serial: str, dat_files: dict[str, Path]) -> str | None:
    path = dat_files.get(console)
    if path is None:
        return None
    normalized = normalize_serial(serial)
    if normalized is None:
        return None
    return _load_dat(path).get(normalized)
