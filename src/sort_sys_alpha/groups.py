"""File groups: members that only work together, moved as one unit.
See PLAN.md section 4.2.

Raw CD sector formats (the actual bytes inside a .bin/.img track) aren't
parsed here or anywhere in this milestone — grouping only reads the small
text sheets (.cue/.gdi/.m3u) that list which files belong together, and a
.ccd group is just three same-stem files. Console identification for the
member tracks themselves is a later milestone.
"""

from __future__ import annotations

import re
from pathlib import Path

from .items import FileGroup, FileItem, ScanItem

_QUOTED_OR_TOKEN = re.compile(r'"([^"]+)"|(\S+)')


def _tokens(line: str) -> list[str]:
    return [a or b for a, b in _QUOTED_OR_TOKEN.findall(line)]


def _lookup_by_name(paths: list[Path]) -> dict[str, Path]:
    return {p.name.lower(): p for p in paths}


def _referenced_members(definer: Path, lines: list[str], by_name: dict[str, Path]) -> list[Path]:
    members: list[Path] = []
    for line in lines:
        for token in _tokens(line):
            match = by_name.get(Path(token).name.lower())
            if match is not None and match != definer and match not in members:
                members.append(match)
    return members


def _group_from_sheet(definer: Path, kind: str, by_name: dict[str, Path]) -> FileGroup | None:
    try:
        text = definer.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    members = _referenced_members(definer, text.splitlines(), by_name)
    if not members:
        return None
    return FileGroup(kind=kind, primary=definer, members=(definer, *members))


def _ccd_group(definer: Path, by_name: dict[str, Path]) -> FileGroup | None:
    img = by_name.get(definer.with_suffix(".img").name.lower())
    sub = by_name.get(definer.with_suffix(".sub").name.lower())
    members = [m for m in (img, sub) if m is not None]
    if not members:
        return None
    return FileGroup(kind="ccd", primary=definer, members=(definer, *members))


SHEET_KINDS = {".cue": "cue_bin", ".gdi": "gdi", ".m3u": "m3u"}


def detect_groups(paths: list[Path]) -> list[ScanItem]:
    by_name = _lookup_by_name(paths)
    consumed: set[Path] = set()
    items: list[ScanItem] = []

    for path in paths:
        if path in consumed:
            continue

        group: FileGroup | None = None
        if path.suffix.lower() in SHEET_KINDS:
            group = _group_from_sheet(path, SHEET_KINDS[path.suffix.lower()], by_name)
        elif path.suffix.lower() == ".ccd":
            group = _ccd_group(path, by_name)

        if group is not None:
            items.append(group)
            consumed.update(group.members)

    for path in paths:
        if path not in consumed:
            items.append(FileItem(path=path))

    return items
