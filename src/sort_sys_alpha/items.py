"""The two kinds of thing `scan` can hand downstream: a lone file, or a file
group that must be planned/gated/moved as one unit. See PLAN.md section 4.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileItem:
    path: Path


@dataclass(frozen=True)
class FileGroup:
    kind: str  # "cue_bin" | "gdi" | "m3u" | "ccd"
    primary: Path
    members: tuple[Path, ...]  # includes `primary`


ScanItem = FileItem | FileGroup
